"""Weekly goal and lifetime milestone calculations."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .selection import is_completed
from .timestamps import workout_timestamp


def weekly_progress(workouts, timezone_name=None, now=None):
    """Return completed workouts, minutes and output (kJ) since local Monday."""
    zone = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    current = (now or datetime.now(timezone.utc)).astimezone(zone)
    monday = (current - timedelta(days=current.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    count = 0
    seconds = 0
    joules = 0
    for workout in workouts:
        stamp = workout_timestamp(workout, timezone_name)
        if not is_completed(workout) or stamp is None or not monday <= stamp.astimezone(zone) <= current:
            continue
        count += 1
        ride = workout.get('ride') if isinstance(workout.get('ride'), dict) else {}
        duration = workout.get('duration') or workout.get('length') or ride.get('duration') or 0
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            seconds += max(0, duration)
        work = workout.get('total_work')
        if isinstance(work, (int, float)) and not isinstance(work, bool) and work > 0:
            joules += work
    return {'workouts': count, 'minutes': int(round(seconds / 60)),
            'output_kj': int(round(joules / 1000))}


# A step milestone only celebrates if it was crossed this recently, so the
# first run after enabling steps doesn't celebrate one reached long ago.
STEP_CELEBRATION_WINDOW = 10


def reached_milestones(total, thresholds, step=0):
    """Configured milestones at or below total, plus the latest step multiple
    (every `step` workouts) when it was crossed within the last few workouts."""
    if not isinstance(total, (int, float)) or isinstance(total, bool):
        return []
    reached = {value for value in thresholds if value <= total}
    if step and total >= step:
        latest = int(total) // step * step
        if total - latest < STEP_CELEBRATION_WINDOW:
            reached.add(latest)
    return sorted(reached)


def next_milestone(total, thresholds, step=0):
    """(previous, target) around total for the countdown, or None.

    target is the next configured milestone above total, else the next
    multiple of step; previous is the last milestone reached (or 0), so the
    progress bar covers just the current stretch.
    """
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        return None
    upcoming = [value for value in thresholds if value > total]
    stepped = (total // step + 1) * step if step else None
    if upcoming:
        target = min(upcoming)
    elif stepped:
        target = stepped
    else:
        return None
    below = [value for value in thresholds if value <= total]
    if step:
        below.append(total // step * step)
    previous = max([value for value in below if value < target] or [0])
    return previous, target
