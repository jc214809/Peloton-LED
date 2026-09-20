"""Consistent completed-workout selection and discipline matching."""
import logging
from datetime import datetime, timezone
from .timestamps import workout_timestamp, workout_date

logger = logging.getLogger('peloton-led.selection')
ALIASES = {'bike': 'cycling', 'ride': 'cycling', 'caesar': 'rowing',
           'caesar_bootcamp': 'row_bootcamp',
           'outdoor_run': 'running_outdoor', 'outdoor_running': 'running_outdoor',
           'outdoor_walk': 'walking_outdoor', 'outdoor_walking': 'walking_outdoor'}


def normalize_discipline(value):
    key = str(value or '').strip().lower().replace(' ', '_')
    return ALIASES.get(key, key)


def discipline_of(workout):
    ride = workout.get('ride') or {}
    return normalize_discipline(ride.get('fitness_discipline') or workout.get('fitness_discipline')
        or ride.get('fitness_discipline_display_name') or workout.get('fitness_discipline_display_name')
        or workout.get('discipline'))


def is_completed(workout):
    # Legacy payloads/fixtures without status remain usable; explicit non-complete
    # statuses must never displace a completed workout on the dashboard.
    status = workout.get('status')
    return status is None or str(status).lower() in ('complete', 'completed')


def ordered_workouts(workouts, tzname=None):
    seen, result = set(), []
    for workout in workouts:
        if not isinstance(workout, dict) or not is_completed(workout):
            continue
        identity = workout.get('id')
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        if workout_date(workout, tzname) is None:
            logger.debug('Skipping workout with no usable date')
            continue
        result.append(workout)
    # Date-only entries participate in active-day groups but not latest-instant selection.
    return sorted(result, key=lambda w: (
        workout_date(w, tzname),
        workout_timestamp(w, tzname) or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)


def latest_workout(workouts, tzname=None):
    candidates = [w for w in ordered_workouts(workouts, tzname) if workout_timestamp(w, tzname)]
    return max(candidates, key=lambda w: workout_timestamp(w, tzname), default=None)


def last_active_day(workouts, tzname=None):
    ordered = ordered_workouts(workouts, tzname)
    if not ordered:
        return []
    day = max(workout_date(w, tzname) for w in ordered)
    return [w for w in ordered if workout_date(w, tzname) == day]


def select_latest(workouts, discipline=None, tzname=None):
    ordered = ordered_workouts(workouts, tzname)
    if discipline:
        wanted = normalize_discipline(discipline)
        matches = [w for w in ordered if discipline_of(w) == wanted]
        match = latest_workout(matches, tzname)
        if match is not None:
            return match
        logger.info('No completed %s workout in available history; using latest completed workout', discipline)
    return latest_workout(ordered, tzname)
