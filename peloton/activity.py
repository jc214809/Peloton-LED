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
# A rank (3RD BEST 30 DAYS) compares the current block of days with the equal blocks before it, so it
# needs this many blocks (the current one included) to mean anything.
MIN_RANK_BLOCKS = 6
# Frames that get a rank, with the block length in days.
RANKED_FRAMES = {'30d': 30, '90d': 90}
# Frames whose busiest month is worth naming (a month inside a 30-day window isn't a "best").
MONTH_FRAMES = ('year', 'last_year', 'all')
# Biggest output is a bike figure (the rower's and the tread's aren't comparable with it).
OUTPUT_DISCIPLINES = ('cycling',)
# How many of the most-seen instructors event_stats keeps a last class for.
EVENT_INSTRUCTORS = 5


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
        stats.update(_bests(inside, zone, start, key in MONTH_FRAMES))
        if key in RANKED_FRAMES:
            stats['rank'] = block_rank(rows, RANKED_FRAMES[key], current.date(), zone)
        before = comparison_window(key, start, current)
        if before:
            stats['before'] = _totals([row for row in rows if _in_window(row[0], before[0], before[1], current)])
        stats['days'] = None if start is None else (
            ((end.date() if end is not None else current.date() + timedelta(days=1)) - start.date()).days)
        if key in ('year', 'last_year'):
            stats['year'] = start.year
        result[key] = stats
    return result


def comparison_window(key, start, current):
    """The (start, end) of the window a frame is compared with, or None for a frame with no fair
    comparison. The 30- and 90-day frames compare with the same number of days just before; the year
    with the same stretch of last year (1 January up to today's date and time), so a part-year is
    never set against a whole one."""
    if key in RANKED_FRAMES:
        return start - timedelta(days=RANKED_FRAMES[key]), start
    if key == 'year':
        try:
            same_day = current.replace(year=current.year - 1)
        except ValueError:      # 29 February
            same_day = current.replace(year=current.year - 1, day=28)
        return start.replace(year=start.year - 1), same_day
    return None


def _totals(rows):
    """Workouts and minutes of (timestamp, workout, ...) rows, all a comparison needs."""
    seconds = sum(max(0, length_seconds(row[1])) for row in rows)
    return {'workouts': len(rows), 'minutes': int(round(seconds / 60))}


def _best(counts):
    """The (count, day) with the highest count, the most recent day on a tie; None when empty."""
    return max(((count, day) for day, count in counts.items()), default=None)


def _entry(best):
    return {'count': best[0], 'date': best[1].isoformat()} if best else None


def _class_id(workout):
    ride = workout.get('ride') if isinstance(workout.get('ride'), dict) else {}
    return ride.get('id') if isinstance(ride.get('id'), str) and ride['id'] else None


def _bests(rows, zone, start, months):
    """The biggest pieces inside a frame, from its (timestamp, workout, discipline, instructors) rows:
    the busiest day, the busiest Monday-to-Sunday week (only weeks that start inside the frame, so a
    window's cut-off first week isn't undercounted), the busiest month (`months`; likewise whole
    months), the longest class, the highest bike output (kJ) and the best Strive score (these three only from
    real classes, never a no-class workout like Just Ride). Each is None when the frame has nothing for it."""
    days, weeks, months_seen = {}, {}, {}
    longest = output = strive = None
    first = start.date() if start is not None else None
    for stamp, workout, discipline, _ in rows:
        day = stamp.astimezone(zone).date()
        days[day] = days.get(day, 0) + 1
        monday = day - timedelta(days=day.weekday())
        if first is None or monday >= first:
            weeks[monday] = weeks.get(monday, 0) + 1
        month = day.replace(day=1)
        if months and (first is None or month >= first):
            months_seen[month] = months_seen.get(month, 0) + 1
        # Just Ride, Just Walk and the like have no class, so they never set a longest or best class.
        if not _class_id(workout):
            continue
        seconds = max(0, length_seconds(workout))
        if seconds and (longest is None or seconds >= longest['seconds']):
            longest = {'seconds': seconds, 'minutes': int(round(seconds / 60)), 'discipline': discipline}
        work = workout.get('total_work')
        if (discipline in OUTPUT_DISCIPLINES and isinstance(work, (int, float)) and not isinstance(work, bool)
                and work > 0 and (output is None or work >= output['joules'])):
            output = {'joules': work, 'kj': work / 1000, 'minutes': int(round(seconds / 60)), 'discipline': discipline}
        points = workout.get('effort_points')
        if (isinstance(points, (int, float)) and not isinstance(points, bool) and points > 0
                and (strive is None or points >= strive['points'])):
            strive = {'points': points, 'discipline': discipline}
    return {'busiest_day': _entry(_best(days)), 'busiest_week': _entry(_best(weeks)),
            'busiest_month': _entry(_best(months_seen)),
            'longest': longest and {k: v for k, v in longest.items() if k != 'seconds'},
            'best_output': output and {k: v for k, v in output.items() if k != 'joules'},
            'best_strive': strive}


def block_rank(rows, days, today, zone):
    """How this block of `days` days (ending today) ranks among every equal block before it, going
    back from today (non-overlapping, so the 2nd best isn't just yesterday's window): {'rank': 1 is the
    most workouts, 'of': blocks, 'best': the biggest block's workouts}. Ties share the better rank.
    None with fewer than MIN_RANK_BLOCKS blocks of history. Each row is counted once, however many
    frames ask."""
    counts = {}
    for stamp, *_ in rows:
        age = (today - stamp.astimezone(zone).date()).days
        if age >= 0:
            counts[age // days] = counts.get(age // days, 0) + 1
    oldest = max(counts, default=-1)
    if oldest + 1 < MIN_RANK_BLOCKS:
        return None
    totals = [counts.get(block, 0) for block in range(oldest + 1)]
    return {'rank': 1 + sum(1 for total in totals[1:] if total > totals[0]), 'of': len(totals),
            'best': max(totals)}


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


def _local_date(value, zone):
    """A profile timestamp (created_at) as a date in the display timezone, or None."""
    stamp = parse_timestamp(value)
    return stamp.astimezone(zone).date() if stamp is not None else None


def anniversary(member_since, timezone_name=None, now=None):
    """Whole years on Peloton when today (display timezone) is the day the account was made, else
    None. `member_since` is the profile's created_at."""
    _, current = week_start(timezone_name, now)
    since = _local_date(member_since, current.tzinfo)
    today = current.date()
    if since is None or (since.month, since.day) != (today.month, today.day) or today.year <= since.year:
        return None
    return today.year - since.year


def event_stats(workouts, timezone_name=None, now=None, member_since=None):
    """Dates the name page measures from, all from the log (dates are ISO, in the display timezone):
    `today`; `anniversary` (years, only on the day); `on_this_day` (the workouts of earlier years on
    today's month and day, nearest year first: {years_ago, minutes, discipline}); `first_ever` (the
    first workout's date); `disciplines` ({slug: {workouts, first, last, before_last}}, before_last the
    day of the workout before the latest, None with one) and `instructors` ({id: {workouts, last}} for
    the EVENT_INSTRUCTORS most-seen). Which of these is worth saying is for the facts module."""
    _, current = week_start(timezone_name, now)
    zone, today = current.tzinfo, current.date()
    per_discipline, per_instructor, ever, same_day = {}, {}, [], []
    for stamp, workout in _stamped(workouts, timezone_name):
        day = stamp.astimezone(zone).date()
        if day > today:
            continue
        ever.append(day)
        discipline = discipline_of(workout)
        if discipline:
            per_discipline.setdefault(discipline, []).append(day)
        for identity in _instructor_ids(workout):
            per_instructor.setdefault(identity, []).append(day)
        if (day.month, day.day) == (today.month, today.day) and day.year < today.year:
            same_day.append((day.year, max(0, length_seconds(workout)), discipline))
    disciplines = {}
    for slug, days in per_discipline.items():
        days.sort()
        disciplines[slug] = {'workouts': len(days), 'first': days[0].isoformat(), 'last': days[-1].isoformat(),
                             'before_last': days[-2].isoformat() if len(days) > 1 else None}
    instructors = {identity: {'workouts': len(per_instructor[identity]),
                              'last': max(per_instructor[identity]).isoformat()}
                   for identity in _top(per_instructor, EVENT_INSTRUCTORS)}
    # The longest workout of the nearest earlier year that has one.
    on_this_day = []
    for year in sorted({year for year, _, _ in same_day}, reverse=True):
        longest = max((row for row in same_day if row[0] == year), key=lambda row: row[1])
        on_this_day.append({'years_ago': today.year - year, 'minutes': int(round(longest[1] / 60)),
                            'discipline': longest[2]})
    return {'today': today.isoformat(), 'anniversary': anniversary(member_since, timezone_name, now),
            'on_this_day': on_this_day, 'first_ever': min(ever).isoformat() if ever else None,
            'disciplines': disciplines, 'instructors': instructors}
