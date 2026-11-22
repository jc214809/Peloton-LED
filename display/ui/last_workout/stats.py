"""The workout page's stat figures: number formats, the strength tracker and each discipline's stats."""

from driver import graphics

from .colors import _WHITE


def _fmt_duration(minutes) -> str:
    if not isinstance(minutes, (int, float)):
        return ''
    m = int(minutes)
    h, rem = divmod(m, 60)
    return f'{h}h{rem}m' if h and rem else (f'{h}hr' if h else f'{m}m')


def _whole(value) -> int:
    """Round half up, as Peloton does (Python's round() sends 0.5 to even)."""
    return int(value + 0.5)


def _fmt_strive(strive) -> str:
    """Strive Score to one decimal, as the Peloton app shows it."""
    return f'{strive:.1f}'


def _fmt_output(output) -> str | None:
    """Total Output in kJ, or None when there is none: outdoor runs and walks
    carry a total_work of 0, which isn't an output to show."""
    return f'{_whole(output)} kj' if isinstance(output, (int, float)) and output > 0 else None


def _fmt_distance(distance, unit) -> str:
    """Miles and km to two decimals, as the Peloton app shows them, with a comma from 1,000."""
    return f'{distance:,.2f} {unit}'.rstrip()


def _fmt_pace(pace_min_per_mile) -> str:
    if not isinstance(pace_min_per_mile, (int, float)):
        return ''
    total_sec = round(pace_min_per_mile * 60)
    return f'{total_sec // 60}:{total_sec % 60:02d}'


def _fmt_split(split_sec) -> str:
    """Format seconds-per-500m as M:SS."""
    if not isinstance(split_sec, (int, float)):
        return ''
    total_sec = round(split_sec)
    return f'{total_sec // 60}:{total_sec % 60:02d}'


# The value colour of TARGETS HIT by Peloton's movement-tracker tier; no tier (or "inprogress") stays white.
TRACKER_TIER_COLORS = {'gold': (255, 200, 0), 'silver': (200, 205, 215), 'bronze': (205, 127, 50)}


def _count(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def strength_tracker(summary: dict) -> dict:
    """The movement tracker's figures (peloton.stats.summaries.strength_tracker), checked, since the cache
    can hold anything: {'reps', 'volume', 'unit', 'targets_pct', 'tier', 'top'}, each None when
    missing or malformed; {} for an untracked workout."""
    tracker = summary.get('strength')
    if not isinstance(tracker, dict):
        return {}
    unit = tracker.get('unit') if tracker.get('unit') in ('lb', 'kg') else None
    pct = tracker.get('targets_pct')
    top = tracker.get('top')
    name = top.get('name') if isinstance(top, dict) else None
    if isinstance(name, str) and name.strip():
        weight = top.get('weight')
        weight = weight if isinstance(weight, (int, float)) and not isinstance(weight, bool) and weight > 0 and unit else None
        top = {'name': name.strip(), 'reps': _count(top.get('reps')), 'weight': weight}
        top = top if top['reps'] or top['weight'] else None
    else:
        top = None
    return {
        'reps': _count(tracker.get('reps')),
        'volume': _count(tracker.get('volume')) if unit else None,
        'unit': unit,
        'targets_pct': pct if isinstance(pct, int) and not isinstance(pct, bool) and 0 <= pct <= 100 else None,
        'tier': tracker.get('tier') if tracker.get('tier') in TRACKER_TIER_COLORS else None,
        'top': top,
    }


def _score(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 100


def running_form(summary: dict) -> dict:
    """The Tread's running-form figures (peloton.stats.summaries.running_form), checked, since the cache
    can hold anything: {'score', 'spm', 'stride_m', 'series'}, or {} without a 0-100 score. spm and
    stride_m are None when missing or malformed; series is [] unless it has two scored points."""
    form = summary.get('running_form')
    if not isinstance(form, dict) or not _score(form.get('score')):
        return {}
    spm, stride = form.get('spm'), form.get('stride_m')
    series = form.get('series')
    series = [round(v) if _score(v) else None for v in series] if isinstance(series, list) else []
    return {
        'score': round(form['score']),
        'spm': round(spm) if isinstance(spm, (int, float)) and not isinstance(spm, bool) and 0 < spm < 1000 else None,
        'stride_m': stride if isinstance(stride, (int, float)) and not isinstance(stride, bool) and 0 < stride < 10 else None,
        'series': series if sum(v is not None for v in series) >= 2 else [],
    }


def _tracker_details(summary: dict) -> list[dict]:
    """A tracked strength class's reps, volume (weight x reps) and share of movements on target."""
    tracker = strength_tracker(summary)
    details = []
    if tracker.get('reps'):
        details.append({'label': 'total reps', 'value': f'{tracker["reps"]:,}'})
    if tracker.get('volume'):
        details.append({'label': 'total volume', 'value': f'{tracker["volume"]:,} {tracker["unit"]}'})
    if tracker.get('targets_pct') is not None:
        detail = {'label': 'targets hit', 'value': f'{tracker["targets_pct"]}%'}
        if tracker['tier']:
            detail['color'] = TRACKER_TIER_COLORS[tracker['tier']]
        details.append(detail)
    return details


def _value_color(detail: dict):
    """A stat's value colour: white, or the detail's own (TARGETS HIT in its tier colour)."""
    rgb = detail.get('color')
    return graphics.Color(*rgb) if rgb else _WHITE


def top_lift_text(top: dict, unit: str) -> str:
    """The top lift's figure: reps x the heaviest weight (`33 X 40 LB`), or whichever of the two there is."""
    weight = f'{top["weight"]:g} {unit}'.upper() if top.get('weight') else ''
    if weight and top.get('reps'):
        return f'{top["reps"]} X {weight}'
    return weight or f'{top["reps"]} REPS'


def _add(details: list[dict], label, value) -> None:
    """Append a detail unless it has no value."""
    if value is not None:
        details.append({'label': label, 'value': value})


def _cycling_details(summary: dict, details: list[dict]) -> None:
    output = summary.get('total_output_kj')
    strive = summary.get('strive_score')
    spd = summary.get('avg_speed')
    spd_unit = summary.get('avg_speed_unit') or ''
    cad = summary.get('avg_cadence')
    res = summary.get('avg_resistance')
    dist_val = summary.get('distance')
    dist_unit = summary.get('distance_unit') or ''
    _add(details, 'total output', f'{_whole(output)} kj' if isinstance(output, (int, float)) else None)
    _add(details, 'strive score', _fmt_strive(strive) if isinstance(strive, (int, float)) else None)
    _add(details, 'avg speed', f'{spd:.1f} {spd_unit}' if isinstance(spd, (int, float)) else None)
    _add(details, 'avg cadence', f'{_whole(cad)} rpm' if isinstance(cad, (int, float)) else None)
    _add(details, 'avg resistance', f'{_whole(res)}%' if isinstance(res, (int, float)) else None)
    _add(details, 'distance', _fmt_distance(dist_val, dist_unit) if isinstance(dist_val, (int, float)) else None)


def _tread_details(summary: dict, details: list[dict]) -> None:
    dist_val = summary.get('distance')
    dist_unit = summary.get('distance_unit') or ''
    pace_val = summary.get('avg_pace')
    elevation = summary.get('elevation')
    elevation_unit = summary.get('elevation_unit') or ''
    incline = summary.get('avg_incline')
    _add(details, 'distance', _fmt_distance(dist_val, dist_unit) if isinstance(dist_val, (int, float)) else None)
    _add(
        details,
        'avg pace',
        f'{_fmt_pace(pace_val)}{(summary.get("avg_pace_unit") or "").replace("min", "")}' if pace_val is not None else None,
    )
    strive = summary.get('strive_score')
    _add(details, 'strive score', _fmt_strive(strive) if isinstance(strive, (int, float)) else None)
    _add(details, 'total output', _fmt_output(summary.get('total_output_kj')))
    # A flat workout's 0 ft and 0.0% are a screen each with nothing to say, so they go (Joel, 2026-11-22).
    if isinstance(elevation, (int, float)) and elevation > 0:
        _add(details, 'elevation gain', f'{elevation:g} {elevation_unit}')
    if isinstance(incline, (int, float)) and f'{incline:.1f}' != '0.0':
        _add(details, 'avg incline', f'{incline:.1f}%')


def _rowing_details(summary: dict, details: list[dict]) -> None:
    dist_val = summary.get('distance')
    dist_unit = summary.get('distance_unit') or ''
    spm_val = summary.get('avg_stroke_rate')
    split_val = summary.get('row_split_sec_per_500m')
    strive = summary.get('strive_score')
    _add(details, 'total output', _fmt_output(summary.get('total_output_kj')))
    _add(details, 'strive score', _fmt_strive(strive) if isinstance(strive, (int, float)) else None)
    _add(details, 'distance', f'{_whole(dist_val):,}{dist_unit}' if isinstance(dist_val, (int, float)) else None)
    _add(details, 'stroke rate', f'{_whole(spm_val)} spm' if isinstance(spm_val, (int, float)) else None)
    _add(details, 'split per 500m', _fmt_split(split_val) if split_val else None)


def _other_details(summary: dict, details: list[dict]) -> None:
    strive = summary.get('strive_score')
    hr_max = summary.get('hr_max')
    distance = summary.get('distance')
    distance_unit = summary.get('distance_unit') or ''
    avg_output = summary.get('avg_output_w')
    _add(details, 'strive score', _fmt_strive(strive) if isinstance(strive, (int, float)) else None)
    details.extend(_tracker_details(summary))
    _add(details, 'max heart rate', f'{_whole(hr_max)}' if isinstance(hr_max, (int, float)) else None)
    _add(details, 'distance', _fmt_distance(distance, distance_unit) if isinstance(distance, (int, float)) else None)
    _add(details, 'avg output', f'{_whole(avg_output)}W' if isinstance(avg_output, (int, float)) else None)


def _stat_details(summary: dict) -> list[dict]:
    """Discipline-specific stat values with spelled-out labels, one detail per
    stat, for the rotating single-item display (e.g. "output", not "kj")."""
    disc = (summary.get('discipline') or '').strip().lower()
    details = []

    if any(d in disc for d in ('cycling', 'bike')):
        _cycling_details(summary, details)
    elif any(d in disc for d in ('running', 'walking', 'outdoor', 'tread', 'hiking')):
        _tread_details(summary, details)
    elif 'rowing' in disc or disc.startswith('row '):
        _rowing_details(summary, details)
    else:
        _other_details(summary, details)

    instructor = (summary.get('instructor') or '').strip()
    if instructor:
        _add(details, 'instructor', instructor)
    return details
