"""Extract unique non-negative discipline counts from overview variants."""
from math import isfinite
from .selection import normalize_discipline

RANGE_KEYS = ('discipline_totals', 'workouts', 'workouts_per_discipline', 'workout_counts',
              'workout_counts_by_discipline', 'discipline_counts')



def extract_discipline_totals(overview):
    totals, seen = {}, set()

    def add(label, value):
        if not isinstance(label, str) or isinstance(value, bool):
            return
        try:
            count = float(value)
            if not isfinite(count) or count < 0 or not count.is_integer():
                return
        except (ValueError, TypeError):
            return
        key = normalize_discipline(label)
        if key and key not in seen:
            seen.add(key)
            totals[key.replace('_', ' ').title()] = int(count)

    def count_of(entry):
        return next((entry[k] for k in ('workout_count', 'total_workouts', 'count', 'workouts')
                     if entry.get(k) is not None and not isinstance(entry[k], (dict, list))), None)

    def visit(data):
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    label = next((entry[k] for k in ('discipline_display_name', 'discipline_name',
                        'name', 'title', 'discipline') if entry.get(k)), '')
                    add(label, count_of(entry))
        elif isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    add(key, count_of(value))
                    for field in ('workouts', 'items', 'disciplines', 'workout_counts'):
                        visit(value.get(field))
                elif isinstance(value, list):
                    visit(value)
                else:
                    add(key, value)
    for key in RANGE_KEYS:
        visit(overview.get(key))
    return totals


def lifetime_overview_pages(totals, page_size=4):
    """Paginate independent discipline counts without combining activities."""
    items = [{'label': label, 'count': count, 'icon': normalize_discipline(label)}
             for label, count in (totals or {}).items()
             if normalize_discipline(label) != 'total_workouts'
             and isinstance(count, int) and not isinstance(count, bool) and count >= 0]
    return [items[index:index + page_size] for index in range(0, len(items), page_size)]


def total_workout_count(totals):
    """Return Peloton's overall workout count when present."""
    return next((count for label, count in (totals or {}).items()
                 if normalize_discipline(label) == 'total_workouts'
                 and isinstance(count, int) and not isinstance(count, bool) and count >= 0), None)
