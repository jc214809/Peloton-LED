"""Weekly goal and lifetime milestone calculations."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .selection import is_completed
from .timestamps import workout_timestamp


def weekly_progress(workouts, timezone_name=None, now=None):
    """Return completed workout count and minutes since local Monday."""
    zone = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    current = (now or datetime.now(timezone.utc)).astimezone(zone)
    monday = (current - timedelta(days=current.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    count = 0
    seconds = 0
    for workout in workouts:
        stamp = workout_timestamp(workout, timezone_name)
        if not is_completed(workout) or stamp is None or not monday <= stamp.astimezone(zone) <= current:
            continue
        count += 1
        ride = workout.get('ride') if isinstance(workout.get('ride'), dict) else {}
        duration = workout.get('duration') or workout.get('length') or ride.get('duration') or 0
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            seconds += max(0, duration)
    return {'workouts': count, 'minutes': int(round(seconds / 60))}


def reached_milestones(total, thresholds):
    if not isinstance(total, (int, float)):
        return []
    return [value for value in thresholds if value <= total]
