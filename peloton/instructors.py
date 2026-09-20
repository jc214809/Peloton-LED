"""All-time instructor tally, built incrementally from workout history pages."""
from .selection import is_completed


def instructor_name(workout):
    ride = workout.get('ride') if isinstance(workout.get('ride'), dict) else {}
    instructor = ride.get('instructor') if isinstance(ride.get('instructor'), dict) else {}
    name = instructor.get('name') or instructor.get('display_name') or ''
    return name.strip()


def merge_instructor_counts(counts, workouts):
    """Add newly-seen completed workouts to an existing {name: count} tally."""
    merged = dict(counts or {})
    for workout in workouts:
        if not is_completed(workout):
            continue
        name = instructor_name(workout)
        if name:
            merged[name] = merged.get(name, 0) + 1
    return merged


def top_instructors(counts, limit=3):
    """Return the top instructors as [(name, count), ...], most-ridden first."""
    if not counts:
        return []
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    return ranked[:limit]
