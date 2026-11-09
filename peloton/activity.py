"""Activity from workout history: the heatmap, the streak reminder and the name page's time-frame and
per-discipline figures."""
from datetime import date, datetime, timedelta

from .goals import week_start
from .instructors import merge_instructor_counts
from .selection import discipline_of, is_completed
from .timestamps import display_timezone, parse_timestamp, workout_date, workout_timestamp
from .workout_log import length_seconds

HEATMAP_WEEKS = 12
# How many of a frame's most-done disciplines and instructors get their own figures (frame_stats).
SUBJECT_DISCIPLINES = 5
SUBJECT_INSTRUCTORS = 3


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


def frame_bounds(timezone_name=None, now=None):
    """Each time frame's (start, end) in the display timezone: start inclusive, end exclusive, and
    None when open (no start: all time; no end: up to now). Calendar months are deliberately not
    here (a month is nearly empty on the 1st): the windows are rolling days, weeks and years."""
    monday, current = week_start(timezone_name, now)
    zone = current.tzinfo
    today = current.date()

    def midnight(day):
        return datetime(day.year, day.month, day.day, tzinfo=zone)

    this_year, last_year = midnight(date(today.year, 1, 1)), midnight(date(today.year - 1, 1, 1))
    return {'week': (monday, None),
            'last_week': (midnight(monday.date() - timedelta(days=7)), monday),
            '30d': (midnight(today - timedelta(days=29)), None),
            '90d': (midnight(today - timedelta(days=89)), None),
            'year': (this_year, None),
            'last_year': (last_year, this_year),
            'all': (None, None)}


def _stamped(workouts, timezone_name):
    """[(local timestamp, workout)] for completed workouts that have a time."""
    rows = []
    for workout in workouts:
        stamp = workout_timestamp(workout, timezone_name)
        if is_completed(workout) and stamp is not None:
            rows.append((stamp, workout))
    return rows


def _in_window(stamp, start, end, current):
    if start is not None and stamp < start:
        return False
    return stamp < end if end is not None else stamp <= current


def _stats(rows, zone):
    """Totals and distinct counts for already-filtered (timestamp, workout) rows."""
    done = [workout for _, workout in rows]
    seconds, disciplines, classes = 0, {}, set()
    for workout in done:
        seconds += max(0, length_seconds(workout))
        discipline = discipline_of(workout)
        if discipline:
            disciplines[discipline] = disciplines.get(discipline, 0) + 1
        ride = workout.get('ride') if isinstance(workout.get('ride'), dict) else {}
        if isinstance(ride.get('id'), str) and ride['id']:
            classes.add(ride['id'])
    counts, _ = merge_instructor_counts({}, {}, done)
    return {'workouts': len(done), 'minutes': int(round(seconds / 60)), 'disciplines': disciplines,
            'instructor_counts': counts, 'instructors': len(counts), 'classes': len(classes),
            'active_days': len({stamp.astimezone(zone).date() for stamp, _ in rows})}


def _instructor_ids(workout):
    """The instructors a workout counts for (a group class counts for each member)."""
    return set(merge_instructor_counts({}, {}, [workout])[0])


def period_stats(workouts, start=None, end=None, timezone_name=None, now=None, discipline=None, instructor=None):
    """Completed workouts from `start` (inclusive) to `end` (exclusive; None is now): how many,
    their minutes, how many of each discipline ({'strength': 12}), each instructor's classes
    ({instructor_id: count}), how many different instructors and classes (by class ID: workouts
    with no class, like Just Ride, don't count) and how many days had a workout.
    `discipline` (a slug) or `instructor` (an ID) keeps only those workouts."""
    _, current = week_start(timezone_name, now)
    rows = [(stamp, workout) for stamp, workout in _stamped(workouts, timezone_name)
            if _in_window(stamp, start, end, current)
            and (discipline is None or discipline_of(workout) == discipline)
            and (instructor is None or instructor in _instructor_ids(workout))]
    return _stats(rows, current.tzinfo)


def _top(groups, limit):
    """The `limit` biggest groups of rows, most workouts first (ties by key)."""
    return sorted(groups, key=lambda key: (-len(groups[key]), key))[:limit]


def frame_stats(workouts, timezone_name=None, now=None):
    """period_stats for every frame in frame_bounds, from one pass of timestamp parsing, each with
    `days` (how many days the frame spans so far; None for all time) and, for the two year
    frames, `year`. Also the same stats for the frame's most-done disciplines (`by_discipline`,
    {slug: stats}, SUBJECT_DISCIPLINES of them) and instructors (`by_instructor`, {id: stats},
    SUBJECT_INSTRUCTORS), split in the same pass rather than by looping the log again."""
    _, current = week_start(timezone_name, now)
    rows = [(stamp, workout, discipline_of(workout), _instructor_ids(workout))
            for stamp, workout in _stamped(workouts, timezone_name)]
    result = {}
    zone = current.tzinfo
    for key, (start, end) in frame_bounds(timezone_name, now).items():
        inside = [row for row in rows if _in_window(row[0], start, end, current)]
        stats = _stats([row[:2] for row in inside], zone)
        disciplines, instructors = {}, {}
        for row in inside:
            if row[2]:
                disciplines.setdefault(row[2], []).append(row[:2])
            for identity in row[3]:
                instructors.setdefault(identity, []).append(row[:2])
        stats['by_discipline'] = {slug: _stats(disciplines[slug], zone)
                                  for slug in _top(disciplines, SUBJECT_DISCIPLINES)}
        stats['by_instructor'] = {identity: _stats(instructors[identity], zone)
                                  for identity in _top(instructors, SUBJECT_INSTRUCTORS)}
        stats['days'] = None if start is None else (
            ((end.date() if end is not None else current.date() + timedelta(days=1)) - start.date()).days)
        if key in ('year', 'last_year'):
            stats['year'] = start.year
        result[key] = stats
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
