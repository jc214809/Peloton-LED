"""Extract unique non-negative discipline counts from overview variants."""
from math import isfinite
from .selection import normalize_discipline

RANGE_KEYS = ('discipline_totals', 'workouts', 'workouts_per_discipline', 'workout_counts',
              'workout_counts_by_discipline', 'discipline_counts')



LABEL_KEYS = ('discipline_display_name', 'discipline_name', 'name', 'title', 'discipline')
COUNT_KEYS = ('workout_count', 'total_workouts', 'count', 'workouts')
NESTED_FIELDS = ('workouts', 'items', 'disciplines', 'workout_counts')


def _whole_count(value):
    """The value as a non-negative whole number, else None."""
    if isinstance(value, bool):
        return None
    try:
        count = float(value)
        if not isfinite(count) or count < 0 or not count.is_integer():
            return None
    except (ValueError, TypeError):
        return None
    return int(count)


def _add(totals, seen, label, value):
    if not isinstance(label, str):
        return
    count = _whole_count(value)
    if count is None:
        return
    key = normalize_discipline(label)
    if key and key not in seen:
        seen.add(key)
        totals[key.replace('_', ' ').title()] = count


def _count_of(entry):
    return next((entry[k] for k in COUNT_KEYS
                 if entry.get(k) is not None and not isinstance(entry[k], (dict, list))), None)


def _visit_list(totals, seen, entries):
    for entry in entries:
        if isinstance(entry, dict):
            label = next((entry[k] for k in LABEL_KEYS if entry.get(k)), '')
            _add(totals, seen, label, _count_of(entry))


def _visit_dict(totals, seen, data):
    for key, value in data.items():
        if isinstance(value, dict):
            _add(totals, seen, key, _count_of(value))
            for field in NESTED_FIELDS:
                _visit(totals, seen, value.get(field))
        elif isinstance(value, list):
            _visit(totals, seen, value)
        else:
            _add(totals, seen, key, value)


def _visit(totals, seen, data):
    if isinstance(data, list):
        _visit_list(totals, seen, data)
    elif isinstance(data, dict):
        _visit_dict(totals, seen, data)


def extract_discipline_totals(overview):
    totals, seen = {}, set()
    for key in RANGE_KEYS:
        _visit(totals, seen, overview.get(key))
    return totals


def lifetime_overview_pages(totals, page_size=4):
    """Paginate independent discipline counts without combining activities."""
    items = [{'label': label, 'count': count, 'icon': normalize_discipline(label)}
             for label, count in (totals or {}).items()
             if normalize_discipline(label) != 'total_workouts'
             and isinstance(count, int) and not isinstance(count, bool) and count >= 0]
    return [items[index:index + page_size] for index in range(0, len(items), page_size)]


# start_date_of_current_daily is a Unix timestamp: the daily streak's first day.
STREAK_KEYS = ('current_weekly', 'best_weekly', 'current_daily', 'start_date_of_current_daily')


def parse_streaks(overview):
    """Weekly/daily streak counts (and the daily start) from the profile overview; {} when absent.

    Only non-negative whole numbers are kept, so a malformed field just
    drops that one count instead of the whole screen.
    """
    streaks = (overview or {}).get('streaks')
    if not isinstance(streaks, dict):
        return {}
    result = {}
    for key in STREAK_KEYS:
        value = streaks.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            result[key] = value
    return result


def total_workout_count(totals):
    """Return Peloton's overall workout count when present."""
    return next((count for label, count in (totals or {}).items()
                 if normalize_discipline(label) == 'total_workouts'
                 and isinstance(count, int) and not isinstance(count, bool) and count >= 0), None)
