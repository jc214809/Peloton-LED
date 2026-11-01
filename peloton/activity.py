"""Day-by-day activity from workout history: the heatmap and the streak reminder."""
from datetime import timedelta

from .goals import week_start
from .selection import is_completed
from .timestamps import workout_date, workout_timestamp
from .workout_log import length_seconds

HEATMAP_WEEKS = 12


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
