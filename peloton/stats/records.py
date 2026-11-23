"""PR flags shared by summaries and display selection."""


def pr_types(workout):
    kinds = set()
    if workout.get('is_total_work_personal_record') is True:
        kinds.add('output')
    if workout.get('is_splits_personal_record') is True:
        kinds.add('splits')
    for template in workout.get('achievement_templates') or []:
        if isinstance(template, dict) and str(template.get('slug', '')).strip().lower() == 'output_pr':
            kinds.add('output')
    return kinds


def is_pr_workout(workout):
    return bool(pr_types(workout or {}))


# Best Times groups hold distance records as times in seconds: the Tread's `running_metric_splits` (1K, 1 Mile, ...)
# and the Row's `rowing_metric_splits` (500M, 1K, 2K, 5K; only /personal_records has these).
BEST_TIMES_SUFFIX = '_metric_splits'


def is_best_times_group(slug):
    return isinstance(slug, str) and slug.endswith(BEST_TIMES_SUFFIX)


def _record_groups(records):
    """The groups of a /personal_records (or /overview) response."""
    for group in (records or {}).get('personal_records') or []:
        if isinstance(group, dict):
            yield group


def _is_positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _output_record(record):
    """An output record's saved entry (kJ), or None for an unset length (-1, no workout) or a damaged one."""
    raw = record.get('raw_value')
    if not record.get('name') or not isinstance(record.get('workout_id'), str) or not _is_positive(raw):
        return None
    return {'value_kj': round(raw / 1000, 1), 'workout_id': record['workout_id'], 'workout_date': record.get('workout_date')}


def _time_record(record):
    """A Best Time's saved entry (seconds and its label), or None for an unset or damaged one."""
    raw, label = record.get('raw_value'), record.get('slug') or record.get('name')
    if not isinstance(record.get('workout_id'), str) or not _is_positive(raw):
        return None
    if not isinstance(label, str) or not label.strip():
        return None
    entry = {'seconds': float(raw), 'label': label.strip().upper()}
    return {**entry, 'workout_id': record['workout_id'], 'workout_date': record.get('workout_date')}


def parse_personal_records(records):
    """Current records from /personal_records (or /overview), keyed 'group|record name': output per discipline and
    class length ('cycling|30 min', `value_kj`) and Best Times ('running_metric_splits|DISTANCE_1K', `seconds`).

    Peloton lists only the current record, so it can't tell us what a new one beat; merge_personal_records keeps
    the one it replaced.
    """
    table = {}
    for group in _record_groups(records):
        slug = group.get('slug') or group.get('name')
        entry_for = _time_record if is_best_times_group(slug) else _output_record
        for record in group.get('records') or []:
            entry = entry_for(record) if isinstance(record, dict) and slug and record.get('name') else None
            if entry is not None:
                table[f'{slug}|{record["name"]}'] = entry
    return table


_PREVIOUS_KEYS = ('value_kj', 'seconds', 'workout_id', 'workout_date')


def merge_personal_records(stored, fresh):
    """Fold a fresh records table into the stored one.

    When a record's workout ID changes, a new PR replaced it, so the stored
    entry becomes that record's 'previous'. The same workout ID means nothing
    changed and the earlier 'previous' is kept. Records missing from the fresh
    table (a partial API response) are kept rather than forgotten.
    """
    # Before 2026-11-22 a Best Time's seconds were stored as output ('0.6 kJ' for 10:33): drop those.
    merged = {
        key: record
        for key, record in (stored or {}).items()
        if not is_best_times_group(key.split('|', 1)[0]) or _is_positive(record.get('seconds'))
    }
    for key, record in fresh.items():
        old = merged.get(key)
        if old is None:
            merged[key] = record
        elif old.get('workout_id') != record['workout_id']:
            merged[key] = {**record, 'previous': {k: old[k] for k in _PREVIOUS_KEYS if k in old}}
    return merged


def best_times_for(workout_id, records, table=None):
    """The Best Times this workout holds, in Peloton's order: [{'label': '1 MILE', 'seconds': 1005.0}], each with
    `previous_seconds` when the saved table (merge_personal_records) knew the time it beat.

    The label is the record's own slug ('1K', '1 Mile'), so a distance the board hasn't seen yet
    still gets a name. Empty when the workout holds none, or the response is missing or damaged.
    """
    if not isinstance(workout_id, str) or not workout_id:
        return []
    bests = []
    for group in _record_groups(records):
        if not is_best_times_group(group.get('slug')):
            continue
        rows = group.get('records')
        for record in rows if isinstance(rows, list) else []:
            if not isinstance(record, dict) or record.get('workout_id') != workout_id:
                continue
            entry = _time_record(record)
            if entry is None:
                continue
            best = {'label': entry['label'], 'seconds': entry['seconds']}
            saved = (table or {}).get(f'{group["slug"]}|{record.get("name")}') or {}
            previous = (saved.get('previous') or {}).get('seconds') if saved.get('workout_id') == workout_id else None
            if _is_positive(previous) and previous > best['seconds']:
                best['previous_seconds'] = float(previous)
            bests.append(best)
    return bests


def previous_best_kj(workout_id, records):
    """The output record a PR workout beat, if we saw it before the PR happened."""
    for record in (records or {}).values():
        if record.get('workout_id') == workout_id and 'value_kj' in record:
            previous = record.get('previous') or {}
            value = previous.get('value_kj')
            return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return None
