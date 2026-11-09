"""Activity from workout history: the heatmap, the streak reminder and the name page's last-30-days and
per-discipline figures."""
from datetime import timedelta

from .goals import week_start
from .instructors import merge_instructor_counts
from .selection import discipline_of, is_completed
from .timestamps import display_timezone, parse_timestamp, workout_date, workout_timestamp
from .workout_log import length_seconds

HEATMAP_WEEKS = 12
# The name page's "LAST 30 DAYS" facts.
RECENT_DAYS = 30


def counts_for_streaks(workout):
    """Peloton leaves workouts synced from other apps out of streaks."""
    return workout.get('is_3p_fit_feed_workout_excluded_from_streaks') is not True


def streak_week_workouts(workouts, timezone_name=None, now=None):
    """Completed, streak-eligible workouts since Monday 00:00 in the display timezone."""
    monday, current = week_start(timezone_name, now)
    count = 0
    for workout in workouts:
        stamp = workout_timestamp(workout, timezone_name)
        if (is_completed(workout) and counts_for_streaks(workout) and stamp is not None
                and monday <= stamp.astimezone(monday.tzinfo) <= current):
            count += 1
    return count


def daily_minutes(workouts, timezone_name=None, now=None, weeks=HEATMAP_WEEKS):
    """{'YYYY-MM-DD': minutes} for completed workouts in the last `weeks` weeks
    (Monday-aligned, through today). Days without workouts are left out."""
    monday, current = week_start(timezone_name, now)
    first = (monday - timedelta(weeks=weeks - 1)).date()
    today = current.date()
    seconds = {}
    for workout in workouts:
        if not is_completed(workout):
            continue
        day = workout_date(workout, timezone_name)
        if day is None or not first <= day <= today:
            continue
        seconds[day] = seconds.get(day, 0) + max(0, length_seconds(workout))
    return {day.isoformat(): int(round(total / 60)) for day, total in sorted(seconds.items())}


def recent_start(timezone_name=None, now=None, days=RECENT_DAYS):
    """00:00 in the display timezone on the first of the last `days` days (today is one), and now."""
    _, current = week_start(timezone_name, now)
    first = current.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    return first, current


def recent_activity(workouts, timezone_name=None, now=None, days=RECENT_DAYS):
    """The last `days` days' completed workouts (rolling, so never thin the way the 1st of a month
    is): how many, their minutes, how many of each discipline ({'strength': 12}) and each
    instructor's classes ({instructor_id: count})."""
    first, current = recent_start(timezone_name, now, days)
    done, seconds, disciplines = [], 0, {}
    for workout in workouts:
        stamp = workout_timestamp(workout, timezone_name)
        if not is_completed(workout) or stamp is None or not first <= stamp.astimezone(first.tzinfo) <= current:
            continue
        done.append(workout)
        seconds += max(0, length_seconds(workout))
        discipline = discipline_of(workout)
        if discipline:
            disciplines[discipline] = disciplines.get(discipline, 0) + 1
    counts, _ = merge_instructor_counts({}, {}, done)
    return {'workouts': len(done), 'minutes': int(round(seconds / 60)),
            'disciplines': disciplines, 'instructor_counts': counts}


def discipline_instructor_counts(workouts):
    """All-time classes per instructor within each discipline: {'strength': {instructor_id: count}}."""
    by_discipline = {}
    for workout in workouts:
        discipline = discipline_of(workout)
        if discipline:
            by_discipline.setdefault(discipline, []).append(workout)
    result = {}
    for discipline, group in by_discipline.items():
        counts, _ = merge_instructor_counts({}, {}, group)
        if counts:
            result[discipline] = counts
    return result


def daily_streak_start(current_daily, today, days=None, started_at=None, timezone_name=None):
    """First day of a `current_daily`-day streak: Peloton's own start
    (`started_at`, a timestamp) on the display calendar when it has one.
    Otherwise counted back from today, or from yesterday when the workout
    log has nothing for today yet (Peloton keeps the streak until the day is
    over); without a log, today is assumed to count."""
    stamp = parse_timestamp(started_at)
    if stamp is not None:
        zone = display_timezone(timezone_name)
        start = (stamp.astimezone(zone) if zone else stamp.astimezone()).date()
        if start <= today:
            return start
    ends = today
    if days and not days.get(today.isoformat()):
        ends = today - timedelta(days=1)
    return ends - timedelta(days=current_daily - 1)
