"""Normalize API metrics for screens and reports without inventing missing values."""
from math import isfinite
from models import get_model_for_discipline
from .timestamps import parse_timestamp, display_timezone, workout_timestamp
from .selection import discipline_of
from .records import pr_types


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if isfinite(result) and result >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def unit(value):
    key = str(value or '').strip().lower()
    return {'miles': 'mi', 'mile': 'mi', 'kilometers': 'km', 'kilometres': 'km',
            'meters': 'm', 'metres': 'm', 'meter': 'm', 'kph': 'km/h', 'km/hr': 'km/h',
            'watts': 'w', 'watt': 'w', 'joules': 'j', 'kilojoules': 'kj',
            'minutes/mile': 'min/mi', 'minutes/km': 'min/km'}.get(key, key) or None


def ts_to_local_str(ts, tzname=None, fmt='%b %d, %Y %I:%M %p %Z'):
    stamp = parse_timestamp(ts, tzname)
    return stamp.astimezone(display_timezone(tzname)).strftime(fmt) if stamp else ''


def extract_summary_from_perf(perf, allowed_slugs):
    result = {}

    def put(slug, value, units=None):
        parsed = number(value)
        if slug in allowed_slugs and parsed is not None and slug not in result:
            result[slug] = parsed
            result[slug + '__unit'] = unit(units)

    for field in ('summaries', 'average_summaries'):
        for entry in perf.get(field) or []:
            if isinstance(entry, dict):
                put(entry.get('slug'), entry.get('value'), entry.get('display_unit'))
    aliases = {'heart_rate': ('hr_avg', 'hr_max', 'bpm'),
               'cadence': ('avg_cadence', None, 'rpm'),
               'resistance': ('avg_resistance', None, '%'),
               'incline': ('avg_incline', 'max_incline', '%'),
               'speed': ('avg_speed', 'max_speed', None),
               'pace': ('avg_pace', None, None),
               'output': ('avg_output', None, 'w'),
               'split_pace': ('avg_split_pace', None, None),
               'stroke_rate': ('avg_stroke_rate', None, 'spm')}
    for metric in perf.get('metrics') or []:
        if not isinstance(metric, dict):
            continue
        mapping = aliases.get(str(metric.get('slug', '')).lower())
        if mapping:
            avg, maximum, fallback = mapping
            units = metric.get('display_unit') or fallback
            put(avg, metric.get('average_value'), units)
            if maximum:
                put(maximum, metric.get('max_value'), units)
    return result


GRAPH_POINTS = 60  # one column each across a 64-px panel, leaving a 2-px margin


def _metric(perf, slug):
    return next((m for m in perf.get('metrics') or []
                 if isinstance(m, dict) and m.get('slug') == slug), None)


def _series(metric):
    values = (metric or {}).get('values')
    return [number(v) for v in values] if isinstance(values, list) else []


def heart_rate_zone_seconds(perf):
    """Seconds spent in HR zones 1-5, or None when the workout has no zone data."""
    durations = (perf.get('effort_zones') or {}).get('heart_rate_zone_durations')
    if isinstance(durations, dict):
        seconds = [number(durations.get(f'heart_rate_z{i}_duration')) or 0 for i in range(1, 6)]
    else:
        zones = (_metric(perf, 'heart_rate') or {}).get('zones')
        if not isinstance(zones, list) or len(zones) != 5:
            return None
        seconds = [number(z.get('duration')) or 0 if isinstance(z, dict) else 0 for z in zones]
    return [round(s) for s in seconds] if sum(seconds) > 0 else None


def _zone_of(bpm, lower_bounds):
    """1-5 zone for a heart rate, given each zone's min bpm (zone 1 first)."""
    zone = None
    for index, bound in enumerate(lower_bounds, start=1):
        if bound is not None and bpm >= bound:
            zone = index
    return zone


def performance_graph(perf, points=GRAPH_POINTS):
    """Downsampled series for the workout graph: output when recorded, else HR.

    Returns {'metric', 'unit', 'values', 'zones', 'peak'} or None. 'values'
    are bucket averages (at most `points` of them, rounded); 'zones' gives the
    HR zone (1-5, or None) during each bucket, for coloring the columns.
    """
    output = _series(_metric(perf, 'output'))
    heart = _series(_metric(perf, 'heart_rate'))
    metric, unit, raw = ('output', 'W', output) if any(output) else ('heart_rate', 'BPM', heart)
    if not any(raw) or len(raw) < 2:
        return None
    zones_meta = (_metric(perf, 'heart_rate') or {}).get('zones')
    bounds = ([number(z.get('min_value')) if isinstance(z, dict) else None for z in zones_meta]
              if isinstance(zones_meta, list) and len(zones_meta) == 5 else None)
    count = min(points, len(raw))
    values, zones = [], []
    for i in range(count):
        start, end = i * len(raw) // count, (i + 1) * len(raw) // count
        bucket = [v for v in raw[start:end] if v is not None]
        values.append(round(sum(bucket) / len(bucket)) if bucket else 0)
        beats = [v for v in heart[start:end] if v]
        zones.append(_zone_of(sum(beats) / len(beats), bounds) if beats and bounds else None)
    return {'metric': metric, 'unit': unit, 'values': values, 'zones': zones,
            'peak': round(max(v for v in raw if v is not None))}


def _display_discipline(workout, ride=None):
    key = discipline_of(workout)
    return {'running_outdoor': 'Outdoor Run', 'walking_outdoor': 'Outdoor Walk'}.get(
        key, key.replace('_', ' ').title())


def summarize_workout(workout, perf=None):
    perf = perf or {}
    ride = workout.get('ride') or {}
    discipline = _display_discipline(workout)
    metrics = extract_summary_from_perf(perf, get_model_for_discipline(discipline).perf_slugs())
    # Prefer recorded workout duration over the class's scheduled duration.
    duration = next((v for v in (number(perf.get('duration')), number(workout.get('duration')),
                               number(ride.get('duration'))) if v is not None and v > 0), None)
    distance, distance_unit = metrics.get('distance'), metrics.get('distance__unit')
    factor = {'m': 1, 'km': 1000, 'mi': 1609.344}.get(distance_unit)
    metres = distance * factor if distance is not None and factor else None
    speed, speed_unit = metrics.get('avg_speed'), metrics.get('avg_speed__unit')
    pace, pace_unit = metrics.get('avg_pace'), metrics.get('avg_pace__unit')
    if pace is not None and pace_unit in ('sec/mi', 's/mi', 'sec/km', 's/km'):
        pace /= 60
        pace_unit = 'min/' + pace_unit.split('/')[1]
    if duration and metres is not None and metres > 0:
        metric = distance_unit in ('km', 'm')
        base_distance = metres / (1000 if metric else 1609.344)
        if speed is None:
            speed = base_distance / (duration / 3600)
            speed_unit = 'km/h' if metric else 'mph'
        if pace is None:
            pace = duration / 60 / base_distance
            pace_unit = 'min/km' if metric else 'min/mi'
    split = metrics.get('avg_split_pace')
    split_unit = metrics.get('avg_split_pace__unit')
    if split is not None and split_unit == 'min/500m':
        split *= 60
    elif split_unit not in ('s/500m', 'sec/500m'):
        split = None
    if split is None and duration and metres and metres > 0:
        split = duration / (metres / 500)
    total_output = metrics.get('total_output')
    output_unit = metrics.get('total_output__unit')
    if output_unit == 'j' and total_output is not None:
        total_output /= 1000
    elif output_unit not in ('kj', None):
        total_output = None
    joules = number(workout.get('total_work'))
    # The graph's Total Output is rounded to whole kJ; PR gains need the raw work.
    total_work_kj = round(joules / 1000, 1) if joules is not None and joules > 0 else None
    if total_output is None:
        total_output = joules / 1000 if joules is not None else None
    avg_output = metrics.get('avg_output')
    avg_unit = metrics.get('avg_output__unit')
    if avg_output is not None and avg_unit == 'kw':
        avg_output *= 1000
    elif avg_unit not in ('w', None):
        avg_output = None
    kinds = pr_types(workout)
    stamp = workout_timestamp(workout)
    instructor = ride.get('instructor') or {}
    result = {
        'workout_id': workout.get('id'),
        'date_time': ts_to_local_str(stamp.timestamp(), workout.get('timezone')) if stamp else '',
        'tz': workout.get('timezone') or '', 'discipline': discipline,
        'title': ride.get('title') or workout.get('title') or workout.get('name') or 'Workout',
        'instructor': instructor.get('name') or instructor.get('display_name') or '',
        'duration_min': round(duration / 60) if duration else None,
        'distance': distance, 'distance_unit': distance_unit,
        'avg_speed': speed, 'avg_speed_unit': speed_unit,
        'avg_pace': pace, 'avg_pace_unit': pace_unit,
        'row_split_sec_per_500m': split,
        'total_output_kj': total_output, 'total_work_kj': total_work_kj, 'avg_output_w': avg_output,
        'is_pr': bool(kinds), 'is_output_pr': 'output' in kinds, 'is_splits_pr': 'splits' in kinds,
        'strive_score': number((perf.get('effort_zones') or {}).get('total_effort_points')),
        'graph': performance_graph(perf),
        'hr_zone_seconds': heart_rate_zone_seconds(perf),
    }
    for key in ('calories', 'max_speed', 'avg_incline', 'max_incline', 'elevation',
                'avg_cadence', 'avg_resistance', 'avg_stroke_rate', 'hr_avg', 'hr_max'):
        result[key] = metrics.get(key)
        result[key + '_unit'] = metrics.get(key + '__unit')
    return result
