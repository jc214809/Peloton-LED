"""All-time instructor tally, built incrementally from workout history pages.

Counts are keyed by Peloton instructor ID, with names kept alongside. Workouts
with no class (Just Walk, Just Ride, Lanebreak, ride goals, free outdoor
sessions, ...) carry a placeholder instructor with no ID and are not counted.
A class taught by several instructors ("Jess & Selena") counts once for each
of them; a member whose name hasn't been seen on a solo class yet is counted
by ID and shows up once their name is known.
"""
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
