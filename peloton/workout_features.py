"""Workout compare: one slim row per workout from three raw Peloton responses.

Spec: WORKOUT-COMPARE-SPEC.md (kept outside this repo), section 3. `build_row` is a pure function of
  detail = GET /api/workout/<id>?joins=ride,ride.instructor
  graph  = GET /api/workout/<id>/performance_graph?every_n=5   (may be None)
  ride   = GET /api/ride/<ride_id>/details                      (may be None)

Standard library only and import-free of the display code. Bumping ROW_VERSION makes every stored
row stale (peloton/workout_rows.py rebuilds them from the saved raw files).
"""
import collections
import logging
import math
import statistics
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

ROW_VERSION = 1
# Peloton's raw fitness_discipline -> the name the workout log uses.
DISCIPLINE_ALIAS = {'caesar': 'rowing', 'caesar_bootcamp': 'row_bootcamp', 'circuit': 'tread_bootcamp'}
REST_SLUGS = {'warmup', 'cooldown', 'transition'}
FOOT = {'running', 'walking', 'tread_bootcamp'}  # speed, not treadmill watts, is the main series
BIKE = {'cycling', 'bike_bootcamp'}
SERIES = ('output', 'speed', 'cadence', 'resistance', 'stroke_rate', 'incline', 'heart_rate')
# A target metric name -> the rider series it is compared with.
TARGET_SERIES = {'resistance': 'resistance', 'cadence': 'cadence', 'stroke_rate': 'stroke_rate',
                 'incline': 'incline', 'speed': 'speed'}
MIN_EFF_SAMPLES = 24  # two minutes of 5-second samples

# Watts a bike makes at a cadence and resistance: log W = A + B log cadence + C log resistance.
# Fitted 2026-11-11 on 29,842 samples from both riders (R squared 0.982). The bike's physics, not
# anyone's fitness: a constant, never refitted at run time.
BIKE_CURVE = (-11.157, 1.702, 2.280)
EFFORT_RATIO = 1.15  # a stretch is an effort at this many times the class's median planned watts
MIN_EFFORT_SECS = 10
MIN_PLAN_SAMPLES = 24
# The nine plan descriptors the fill-in distance uses (spec section 4.1).
PLAN_KEYS = ('ride_min', 'arms_min', 'planned_watts', 'planned_watts_high', 'effort_share',
             'efforts_per_10min', 'effort_length_s', 'cadence_mean', 'resistance_mean')

WEIGHT_LEVELS = ('body_weight', 'light', 'medium', 'heavy')
# Ride-details subsegment types -> the block kind `asks` reports in minutes.
GROUP_KINDS = {'emom_group': 'emom', 'amrap_group': 'amrap', 'compound_group': 'compound',
               'complex_group': 'compound', 'generic_group': 'circuit'}
TIMED_TRACKING = ('time_based', 'time_tracked_rep', None)
TOP_MUSCLES = 5


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _round(value, places=2):
    return None if value is None else round(value, places)


def discipline(raw):
    """The workout log's name for Peloton's raw fitness_discipline."""
    return DISCIPLINE_ALIAS.get(raw, raw)


def _series(graph):
    times = graph.get('seconds_since_pedaling_start') or []
    out = {}
    for metric in graph.get('metrics') or []:
        out[metric['slug']] = metric.get('values') or []
        for alt in metric.get('alternatives') or []:
            out[alt['slug']] = alt.get('values') or []
    if 'heart_rate' in out:  # 0 is a dropped strap reading, not a heart rate
        out['heart_rate'] = [v or None for v in out['heart_rate']]
    return times, out


def segment_kind(segment):
    """work | arms | floor | rest for one segment_list entry."""
    slug = segment.get('icon_slug') or segment.get('icon_name')
    if slug in REST_SLUGS:
        return 'rest'
    if segment.get('metrics_type') == 'floor':
        return 'floor'
    if slug == 'upper_body':  # seated arms block on a bike/rower class: pedalling optional
        return 'arms'
    return 'work'


def _in_windows(t, windows):
    return any(lo <= t < hi for lo, hi in windows)


def _window_mean(times, values, windows):
    return _mean([values[i] for i in range(min(len(times), len(values)))
                  if values[i] is not None and _in_windows(times[i], windows)])


def _strength(detail):
    summary = ((detail.get('movement_tracker_data') or {}).get('completed_movements_summary_data')) or {}
    if not summary:
        return None, None
    sets = []
    for entry in summary.get('repetition_summary_data') or []:
        weight = (entry.get('weight') or [{}])[0] or {}
        sets.append({
            'name': entry.get('movement_name'), 'movement_id': entry.get('movement_id'),
            'type': entry.get('tracking_type'), 'offset': entry.get('offset'), 'len': entry.get('length'),
            'done': entry.get('completed_number'), 'target': entry.get('target_number'),
            'hit': entry.get('is_target_reached'), 'hold': bool(entry.get('is_hold')),
            'lb': (weight.get('weight_data') or {}).get('weight_value'),
            'cat': weight.get('weight_category'), 'volume': entry.get('total_volume'),
        })
    weights = summary.get('weight_info_summary_data') or {}
    tracker = {
        'volume': summary.get('total_volume'), 'reps': summary.get('total_repetitions'),
        'movements': summary.get('num_movements'), 'targets_hit': summary.get('num_targets_reached'),
        'weights': {k.split('_')[0]: sorted(x['weight_value'] for x in v) for k, v in weights.items() if v},
    }
    return tracker, sets


def planned_watts(cadence, resistance, curve=BIKE_CURVE):
    a, b, c = curve
    return math.exp(a + b * math.log(max(cadence, 20)) + c * math.log(max(resistance, 5)))


def bike_plan(graph, ride_meta=None):
    """The nine plan descriptors of a bike class (PLAN_KEYS), or None without callout lines.

    Built from the 5-second cadence and resistance callout lines over riding segments only.
    """
    ride_meta = ride_meta or {}
    lines = {m.get('type'): m.get('graph_data') or {} for m in
             (graph.get('target_performance_metrics') or {}).get('target_graph_metrics') or []}
    if 'cadence' not in lines or 'resistance' not in lines:
        return None
    segments = graph.get('segment_list') or []
    if any(s.get('metrics_type') == 'floor' for s in segments):
        return None
    kind_at = {}
    arms_secs = 0
    for s in segments:
        slug = s.get('icon_slug')
        kind = 'arms' if slug == 'upper_body' else 'rest' if slug in REST_SLUGS else 'ride'
        if kind == 'arms':
            arms_secs += s['length']
        for t in range(s['start_time_offset'], s['start_time_offset'] + s['length'], 5):
            kind_at[t // 5] = kind
    cadence, resistance = lines['cadence'], lines['resistance']
    cad, res, watts = [], [], []
    count = min(len(cadence.get('upper') or []), len(cadence.get('lower') or []),
                len(resistance.get('upper') or []), len(resistance.get('lower') or []))
    for i in range(count):
        if kind_at.get(i, 'ride' if not segments else None) != 'ride':
            continue
        c_hi, c_lo = cadence['upper'][i], cadence['lower'][i]
        r_hi, r_lo = resistance['upper'][i], resistance['lower'][i]
        if None in (c_hi, c_lo, r_hi, r_lo) or not c_hi or not r_hi:
            continue
        cad.append((c_hi + c_lo) / 2)
        res.append((r_hi + r_lo) / 2)
        watts.append(planned_watts(cad[-1], res[-1]))
    if len(watts) < MIN_PLAN_SAMPLES:
        return None
    median = statistics.median(watts)
    high = [w >= EFFORT_RATIO * median for w in watts]
    runs, i = [], 0
    while i < len(high):
        j = i
        while j < len(high) and high[j] == high[i]:
            j += 1
        if high[i] and (j - i) * 5 >= MIN_EFFORT_SECS:
            runs.append((j - i) * 5)
        i = j
    ride_secs = len(watts) * 5
    plan = {
        'ride_min': ride_secs / 60,
        'arms_min': arms_secs / 60,
        'planned_watts': statistics.mean(watts),
        'planned_watts_high': sorted(watts)[int(0.9 * len(watts))],
        'effort_share': sum(runs) / ride_secs,
        'efforts_per_10min': len(runs) / (ride_secs / 600),
        'effort_length_s': statistics.median(runs) if runs else 0,
        'cadence_mean': statistics.mean(cad),
        'resistance_mean': statistics.mean(res),
    }
    return {key: round(value, 3) for key, value in plan.items()}


def _strength_blocks(ride):
    """The class's subsegments with movements, from the ride details (rest blocks dropped)."""
    blocks = []
    for segment in ((ride or {}).get('segments') or {}).get('segment_list') or []:
        for sub in segment.get('subsegments_v2') or []:
            moves = [m for m in sub.get('movements') or [] if not m.get('is_rest')]
            begin = sub.get('offset') if sub.get('offset') is not None else sub.get('scheduled_offset')
            if sub.get('type') == 'rest' or not moves or begin is None or not sub.get('length'):
                continue
            levels = [m.get('weight_level') for m in moves if m.get('weight_level') in WEIGHT_LEVELS]
            group = GROUP_KINDS.get(sub.get('type'))
            blocks.append({
                'secs': sub['length'], 'group': group,
                'names': [m.get('name') or '' for m in moves],
                'target': moves[0].get('target_number'),
                'timed': not group and all(m.get('tracking_type') in TIMED_TRACKING for m in moves),
                'muscles': [(g.get('muscle_group'), g.get('ranking') or 1)
                            for m in moves for g in m.get('muscle_groups') or []],
                'level': max(levels, key=WEIGHT_LEVELS.index) if levels else None,
            })
    return blocks


def strength_asks(ride):
    """What a strength class asks for, from its movement list; None without one.

    Stored for display; no rule reads it (spec section 3).
    """
    blocks = _strength_blocks(ride)
    work = [b for b in blocks if not all(n.lower().startswith('warm') for n in b['names'])]
    if not work:
        return None
    work_secs = sum(b['secs'] for b in work)
    counted = [b for b in work if not b['group'] and not b['timed'] and b['target']]
    timed = [b for b in work if not b['group'] and (b['timed'] or not b['target'])]
    grouped = collections.Counter()
    levels = collections.Counter()
    muscles = collections.Counter()
    for b in work:
        if b['group']:
            grouped[b['group']] += b['secs']
        levels[b['level'] or 'not_stated'] += b['secs']
        for name, rank in b['muscles']:
            if name:
                muscles[name] += rank * b['secs']
    muscle_total = sum(muscles.values()) or 1
    return {
        'work_min': round(work_secs / 60, 1),
        'counted_sets': len(counted),
        'reps_asked': sum(b['target'] for b in counted),
        'timed_sets': len(timed),
        'timed_min': round(sum(b['secs'] for b in timed) / 60, 1),
        'blocks_min': {kind: round(secs / 60, 1) for kind, secs in sorted(grouped.items())},
        'levels': {level: round(100 * secs / work_secs) for level, secs in levels.most_common()},
        'muscles': {name: round(100 * value / muscle_total) for name, value in muscles.most_common(TOP_MUSCLES)},
    }


def build_row(detail, graph=None, ride=None):
    """One row (spec section 3). Raises ValueError when the detail lacks an id or start time."""
    if not isinstance(detail, dict) or not detail.get('id') or detail.get('start_time') is None:
        raise ValueError('workout detail without id or start_time')
    graph = graph if isinstance(graph, dict) else {}
    ride = ride if isinstance(ride, dict) else {}
    ride_meta = detail.get('ride') or {}
    times, series = _series(graph)
    duration = graph.get('duration') or ride_meta.get('duration') or 0
    elapsed = (detail.get('end_time') or detail['start_time']) - detail['start_time']
    tz = detail.get('timezone') or 'UTC'
    try:
        local = datetime.fromtimestamp(detail['start_time'], ZoneInfo(tz))
    except Exception:  # unknown zone name: fall back rather than lose the row
        log.warning('workout %s: unknown timezone %r, using UTC', detail['id'], tz)
        local = datetime.fromtimestamp(detail['start_time'], timezone.utc)

    segments = [{'kind': segment_kind(s), 'a': s['start_time_offset'],
                 'b': s['start_time_offset'] + s['length']} for s in graph.get('segment_list') or []]
    mix = {}
    windows = {}
    for seg in segments:
        mix[seg['kind']] = mix.get(seg['kind'], 0) + seg['b'] - seg['a']
        windows.setdefault(seg['kind'], []).append((seg['a'], seg['b']))
    if 'floor' in mix and 'work' in mix:
        mode = 'floor'
    elif 'arms' in mix:
        mode = 'arms'
    else:
        mode = 'plain'
    if not segments or not ({'work', 'floor', 'arms'} & set(windows)):
        # Freestyle, or a class that is one warm-up / cool-down block: the whole thing is the work.
        windows['work'] = [(0, 10 ** 9)]
    work_windows = windows.get('work') or []

    disc = discipline(detail.get('fitness_discipline'))
    row = {
        'v': ROW_VERSION, 'id': detail['id'], 'disc': disc,
        'start': detail['start_time'], 'date': local.strftime('%Y-%m-%d'),
        'ride_id': ride_meta.get('id'), 'title': ride_meta.get('title'),
        'dur': duration, 'elapsed': elapsed,
        'complete': bool(detail.get('status') == 'COMPLETE' and duration and elapsed >= 0.8 * duration),
        'wtype': detail.get('workout_type'), 'outdoor': bool(detail.get('is_outdoor')),
        'device': detail.get('device_type_display_name'),
        'instructor': (ride_meta.get('instructor') or {}).get('name'),
        'ctype': '/'.join(c.get('name') or '' for c in ride.get('class_types') or []) or None,
        'difficulty': _round(ride_meta.get('difficulty_estimate')),
        'mode': mode, 'mix': mix,
        'arms_sections': sum(1 for seg in segments if seg['kind'] == 'arms'),
        'has_graph': bool(graph),
    }

    # Heart rate: effort, the same for every discipline.
    heart = series.get('heart_rate') or []
    zones = (graph.get('effort_zones') or {}).get('heart_rate_zone_durations') or {}
    row['hr_avg'] = _round(_mean(heart), 1)
    row['hr_max'] = max((v for v in heart if v), default=None)
    row['strive'] = _round(detail.get('hr_total_points'), 1) or None
    row['hr_zone'] = [zones.get(f'heart_rate_z{i}_duration') or 0 for i in range(1, 6)] if zones else None

    # What the rider produced, in the work segments only (warm-up, cool-down, arms, floor excluded).
    work = {name: _round(_window_mean(times, series[name], work_windows))
            for name in SERIES if name in series and work_windows}
    row['work'] = {k: v for k, v in work.items() if v is not None}
    row['work_secs'] = sum(max(0, min(hi, duration or hi) - lo) for lo, hi in work_windows)
    if 'floor' in windows and heart:
        row['floor_hr'] = _round(_window_mean(times, heart, windows['floor']), 1)
    summaries = {s.get('slug'): s.get('value') for s in graph.get('summaries') or []}
    row['total_kj'] = summaries.get('total_output')
    row['distance'] = summaries.get('distance')
    row['elevation'] = summaries.get('elevation')
    rank, field = detail.get('leaderboard_rank'), detail.get('total_leaderboard_users')
    row['lb_pct'] = round(100 * (1 - rank / field), 1) if rank and field else None

    # Output (or speed) per heartbeat over the work samples.
    order = ('speed', 'output') if disc in FOOT else ('output', 'speed')
    main = next((name for name in order if name in series), None)
    row['main'] = main
    if main and heart:
        pairs = [(series[main][i], heart[i]) for i in range(min(len(times), len(series[main]), len(heart)))
                 if series[main][i] and heart[i] and _in_windows(times[i], work_windows)]
        if len(pairs) >= MIN_EFF_SAMPLES:
            row['eff'] = _round(_mean([a for a, _ in pairs]) / _mean([b for _, b in pairs]), 3)

    _callouts(row, graph, times, series, work_windows)
    if disc in BIKE and graph:
        plan = bike_plan(graph, ride_meta)
        if plan:
            row['plan'] = plan

    # Strength: what the class works, and what the tracker saw.
    if disc == 'strength':
        muscles = graph.get('muscle_group_score') or ride_meta.get('muscle_group_score') or []
        row['muscles'] = {m['muscle_group']: m['percentage'] for m in muscles if m.get('percentage')}
        patterns = (ride.get('segments') or {}).get('movement_patterns') or []
        row['patterns'] = {p['slug']: p['percentage'] for p in patterns}
        asks = strength_asks(ride)
        if asks:
            row['asks'] = asks
        tracker, sets = _strength(detail)
        if tracker:
            row['tracker'], row['sets'] = tracker, sets
    return row


def _overlap(a, b, windows):
    """Seconds of [a, b) inside the windows."""
    return sum(max(0, min(b, hi) - max(a, lo)) for lo, hi in windows)


def _callouts(row, graph, times, series, work_windows):
    """The instructor's callouts inside work segments: their level, and where the rider sat in them.

    Only the seconds inside work segments count: a callout that runs on into an arms section (pedalling
    optional), a floor block or the cool-down never counts those seconds against the rider.
    """
    callouts = (graph.get('target_metrics_performance_data') or {}).get('target_metrics') or []
    level, position, inside, under, pace = {}, {}, {}, {}, {}
    for callout in callouts:
        a, b = callout['offsets']['start'], callout['offsets']['end'] + 1
        seconds = _overlap(a, b, work_windows)
        if not seconds:
            continue
        for metric in callout.get('metrics') or []:
            name, lo, hi = metric['name'], metric['lower'], metric['upper']
            if name == 'pace_intensity':
                pace[str(int(lo))] = pace.get(str(int(lo)), 0) + seconds
                continue
            level.setdefault(name, []).append(((lo + hi) / 2, seconds))
            source = TARGET_SERIES.get(name)
            if source in series and hi > lo:
                for i in range(min(len(times), len(series[source]))):
                    value = series[source][i]
                    if value is not None and a <= times[i] < b and _in_windows(times[i], work_windows):
                        position.setdefault(name, []).append((value - lo) / (hi - lo))
                        inside.setdefault(name, []).append(lo <= value <= hi)
                        under.setdefault(name, []).append(value < lo)
    if level:
        row['target'] = {n: _round(sum(v * w for v, w in pairs) / sum(w for _, w in pairs))
                         for n, pairs in level.items()}
        row['target_pos'] = {n: _round(_mean(v)) for n, v in position.items()}
        row['target_in'] = {n: round(100 * sum(v) / len(v)) for n, v in inside.items()}
        row['target_under'] = {n: round(100 * sum(v) / len(v)) for n, v in under.items()}
    if pace:
        total = sum(pace.values())
        row['pace_plan'] = {k: round(100 * v / total) for k, v in sorted(pace.items())}
    compliance = graph.get('target_metrics_compliance') or {}
    if compliance:
        row['pace_level'] = compliance.get('workout_pace_level')
        overall = (compliance.get('pace_intensities_target_compliance_percentage') or {}).get('overall') or {}
        if overall:
            row['pace_fit'] = [overall.get('below_target'), overall.get('in_target'), overall.get('above_target')]
    form = ((graph.get('caesar_metrics') or {}).get('detail') or {}).get('score')
    if form is not None:
        row['form_score'] = form
