"""All-time instructor tally, built incrementally from workout history pages.

Counts are keyed by Peloton instructor ID, with names kept alongside. Workouts
with no class (Just Walk, Just Ride, Lanebreak, ride goals, free outdoor
sessions, ...) carry a placeholder instructor with no ID and are not counted.
A class taught by several instructors ("Jess & Selena") counts once for each
of them; a member whose name hasn't been seen on a solo class yet is counted
by ID and shows up once their name is known.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .selection import is_completed


def _instructor(workout):
    ride = workout.get('ride') if isinstance(workout.get('ride'), dict) else {}
    return ride.get('instructor') if isinstance(ride.get('instructor'), dict) else {}


def instructor_name(workout):
    instructor = _instructor(workout)
    name = instructor.get('name') or instructor.get('display_name') or ''
    return name.strip()


def merge_instructor_counts(counts, names, workouts):
    """Add newly-seen completed workouts to {instructor_id: count} and {instructor_id: name}.

    Returns new (counts, names) dicts; the inputs are not changed.
    """
    merged, known = dict(counts or {}), dict(names or {})
    for workout in workouts:
        if not is_completed(workout):
            continue
        instructor = _instructor(workout)
        identity = instructor.get('id')
        if not isinstance(identity, str) or not identity:
            continue
        if instructor.get('is_instructor_group'):
            members = instructor.get('individual_instructor_ids')
            members = {m for m in members if isinstance(m, str) and m} if isinstance(members, list) else set()
        else:
            members = {identity}
            name = instructor_name(workout)
            if name:
                known[identity] = name
        for member in members:
            merged[member] = merged.get(member, 0) + 1
    return merged, known


def top_instructors(counts, names, limit=3):
    """Return the top named instructors as [(name, count), ...], most-taken first."""
    named = [(names[identity], count) for identity, count in (counts or {}).items()
             if (names or {}).get(identity)]
    ranked = sorted(named, key=lambda item: (-item[1], item[0].lower()))
    return ranked[:limit]


def _members(row):
    """The instructor IDs a log row counts for (a group class counts for each member)."""
    if isinstance(row.get('group_ids'), list):
        return {m for m in row['group_ids'] if isinstance(m, str) and m}
    identity = row.get('instructor_id')
    return {identity} if isinstance(identity, str) and identity else set()


def _date(stamp, zone_name):
    try:
        zone = ZoneInfo(zone_name) if zone_name else timezone.utc
    except (ZoneInfoNotFoundError, ValueError, OSError):
        zone = timezone.utc
    return datetime.fromtimestamp(stamp, zone).date().isoformat()


def class_numbers(rows, workout_id, row, names):
    """Which class this is with each instructor of `row`, counted from the workout log.

    `rows` is the log's {workout ID: row}; `row` the workout's own log row (workout_log.trim), which may not
    be in the log yet; `names` {instructor ID: name}. Counts completed workouts that started before this one
    (ties by ID), every discipline, plus this one: so the number never moves when later workouts arrive.
    Returns [{'id', 'name', 'n', 'since'}] (`since` the date of the first class with them, ISO, in the
    workout's zone), empty for a workout with no instructor or no start time.
    """
    members, start = _members(row), row.get('start')
    if not members or isinstance(start, bool) or not isinstance(start, (int, float)):
        return []
    count, first = dict.fromkeys(members, 1), dict.fromkeys(members, start)
    for identity, other in rows.items():
        if identity == workout_id or not isinstance(other, dict) or not is_completed({'status': other.get('status')}):
            continue
        stamp = other.get('start')
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or (stamp, identity) >= (start, workout_id):
            continue
        for member in members & _members(other):
            count[member] += 1
            first[member] = min(first[member], stamp)
    return [{'id': m, 'name': (names or {}).get(m) or None, 'n': count[m], 'since': _date(first[m], row.get('tz'))}
            for m in sorted(members)]
