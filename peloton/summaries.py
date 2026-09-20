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
    if total_output is None:
        joules = number(workout.get('total_work'))
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
        'total_output_kj': total_output, 'avg_output_w': avg_output,
        'is_pr': bool(kinds), 'is_output_pr': 'output' in kinds, 'is_splits_pr': 'splits' in kinds,
        'strive_score': number((perf.get('effort_zones') or {}).get('total_effort_points')),
    }
    for key in ('calories', 'max_speed', 'avg_incline', 'max_incline', 'elevation',
                'avg_cadence', 'avg_resistance', 'avg_stroke_rate', 'hr_avg', 'hr_max'):
        result[key] = metrics.get(key)
        result[key + '_unit'] = metrics.get(key + '__unit')
    return result
