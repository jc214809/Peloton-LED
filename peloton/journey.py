"""Lifetime distance as a trip between two places (default: Columbus to Disney World)."""
from datetime import date
from math import isfinite

from .selection import discipline_of, is_completed, normalize_discipline
from .timestamps import workout_date

KM_TO_MI = 0.621371
M_TO_MI = 1 / 1609.344
# Peloton reports rowing distance in meters regardless of the member's units.
METER_DISCIPLINES = {'rowing', 'row_bootcamp'}

DEFAULT_JOURNEY = {'from': 'Columbus', 'to': 'Disney World', 'miles': 880,
                   'disciplines': ['Cycling', 'Running', 'Walking'], 'start_date': None}


def workout_miles(workout, metric=False):
    """Miles covered in one workout history row, or None when it has no distance."""
    value = workout.get('distance')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        return None
    if discipline_of(workout) in METER_DISCIPLINES:
        return value * M_TO_MI
    return value * KM_TO_MI if metric else value


def merge_distance_totals(totals, workouts, metric=False, since=None, tzname=None):
    """Add newly-seen completed workouts to a {discipline_key: miles} tally.

    With since (a YYYY-MM-DD string), only workouts on or after that day in
    the display timezone count; workouts with no readable date are skipped.
    """
    merged = dict(totals or {})
    start = date.fromisoformat(since) if since else None
    for workout in workouts:
        if not is_completed(workout):
            continue
        if start is not None:
            day = workout_date(workout, tzname)
            if day is None or day < start:
                continue
        miles = workout_miles(workout, metric)
        if miles is not None:
            key = discipline_of(workout)
            merged[key] = round(merged.get(key, 0) + miles, 3)
    return merged


def uses_metric(me):
    """Peloton has no explicit distance unit on the profile; height follows it."""
    return str((me or {}).get('height_unit') or '').lower() == 'metric'


def journey_progress(distance_totals, journey):
    """Where the rider is on the route, going there and back as many times as needed.

    Returns {'from', 'to', 'route_miles', 'miles', 'trip', 'leg_miles',
    'fraction', 'returning'} or None when the route or data is unusable.
    'trip' counts one-way legs started (1 = first trip out); 'fraction' is
    progress along the current leg, measured from where that leg began.
    """
    if not isinstance(journey, dict) or not isinstance(distance_totals, dict):
        return None
    route = journey.get('miles')
    if isinstance(route, bool) or not isinstance(route, (int, float)) or route <= 0:
        return None
    wanted = {normalize_discipline(d) for d in journey.get('disciplines') or []}
    miles = sum(v for k, v in distance_totals.items()
                if k in wanted and isinstance(v, (int, float)) and not isinstance(v, bool))
    leg, into = divmod(miles, route)
    return {'from': str(journey.get('from') or 'Start'), 'to': str(journey.get('to') or 'Finish'),
            'route_miles': route, 'miles': miles, 'trip': int(leg) + 1,
            'leg_miles': into, 'fraction': into / route, 'returning': int(leg) % 2 == 1}
