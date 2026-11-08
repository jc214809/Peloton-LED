"""Weekly goal and lifetime milestone calculations."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .selection import is_completed
from .timestamps import workout_timestamp


def week_day(timezone_name=None, now=None):
    """Today's index in the weekly-goal week: 0 for Monday through 6 for Sunday."""
    zone = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    return (now or datetime.now(timezone.utc)).astimezone(zone).weekday()


def local_date(timestamp, timezone_name=None):
    """The calendar date of a Unix timestamp in the display timezone."""
    zone = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    return datetime.fromtimestamp(timestamp, zone).date()


def week_start(timezone_name=None, now=None):
    """Monday 00:00 of the current week in the display timezone, and now."""
    zone = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    current = (now or datetime.now(timezone.utc)).astimezone(zone)
    monday = (current - timedelta(days=current.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return monday, current


def weekly_progress(workouts, timezone_name=None, now=None):
    """Return completed workouts, minutes and output (kJ) since local Monday."""
    zone = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    monday, current = week_start(timezone_name, now)
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


# Per-discipline milestones pick their own round targets: these, then every 100.
DISCIPLINE_TARGETS = (25, 50, 100)
DISCIPLINE_TARGET_STEP = 100
# The Next Milestone page counts down to a target only this close, at most this many pages.
UPCOMING_WITHIN = 5
MAX_UPCOMING = 3


def discipline_target_after(count):
    """The first round target above count: 25, 50, 100, then every 100."""
    for target in DISCIPLINE_TARGETS:
        if count < target:
            return target
    return (count // DISCIPLINE_TARGET_STEP + 1) * DISCIPLINE_TARGET_STEP


def discipline_target_reached(count):
    """The highest round target at or below count, or None below the first."""
    if count < DISCIPLINE_TARGETS[0]:
        return None
    if count < DISCIPLINE_TARGETS[-1]:
        return max(target for target in DISCIPLINE_TARGETS if target <= count)
    return count // DISCIPLINE_TARGET_STEP * DISCIPLINE_TARGET_STEP


def _discipline_counts(totals):
    """(slug, label, count) for each discipline in Peloton's overview totals, not the total."""
    from .selection import normalize_discipline
    for label, count in (totals or {}).items():
        slug = normalize_discipline(label)
        if (slug and slug != 'total_workouts' and isinstance(count, int)
                and not isinstance(count, bool) and count >= 0):
            yield slug, label, count


def upcoming_discipline_milestones(totals, within=UPCOMING_WITHIN, limit=MAX_UPCOMING):
    """Disciplines within `within` of their next round target, closest first (then the
    bigger target): [{'discipline', 'label', 'count', 'target', 'previous'}], previous being the
    target before (0 before the first), where the progress bar starts. Usually empty."""
    upcoming = []
    for slug, label, count in _discipline_counts(totals):
        target = discipline_target_after(count)
        if target - count <= within:
            upcoming.append({'discipline': slug, 'label': label, 'count': count, 'target': target,
                             'previous': discipline_target_reached(count) or 0})
    upcoming.sort(key=lambda item: (item['target'] - item['count'], -item['target'], item['label']))
    return upcoming[:limit]


def upcoming_milestones(total, thresholds, step, totals, within=UPCOMING_WITHIN, limit=MAX_UPCOMING):
    """Everything within `within` workouts of its next target, closest first: the total (discipline
    None, label 'Workouts'; its target from next_milestone) and each discipline. On a tie the total
    goes first, then the bigger target. Usually empty."""
    upcoming = upcoming_discipline_milestones(totals, within, limit=None)
    around = next_milestone(total, thresholds, step)
    if around and around[1] - total <= within:
        upcoming.append({'discipline': None, 'label': 'Workouts', 'count': total,
                         'target': around[1], 'previous': around[0]})
    upcoming.sort(key=lambda item: (item['target'] - item['count'], item['discipline'] is not None,
                                    -item['target'], item['label']))
    return upcoming[:limit]


def milestone_key(discipline, target):
    """'strength:500': how a per-discipline milestone is stored and acknowledged."""
    return f'{discipline}:{target}'


def parse_milestone_key(key):
    """('strength', 500) from 'strength:500', or None when it isn't one."""
    if not isinstance(key, str):
        return None
    discipline, _, target = key.rpartition(':')
    if not discipline or not target.isdigit():
        return None
    return discipline, int(target)


def reached_discipline_milestones(totals, within=STEP_CELEBRATION_WINDOW):
    """Keys of per-discipline targets crossed within the last `within` workouts of that
    discipline, so one reached long ago isn't celebrated when the feature first runs. Sorted;
    none when within is 0."""
    reached = []
    for slug, _, count in _discipline_counts(totals):
        target = discipline_target_reached(count)
        if target is not None and count - target < within:
            reached.append(milestone_key(slug, target))
    return sorted(reached)
