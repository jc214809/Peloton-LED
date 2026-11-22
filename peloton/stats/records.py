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


# The /overview group holding the Tread's distance records (1K, 1 Mile, ...) as times in seconds.
BEST_TIMES_GROUP = 'running_metric_splits'


def _record_groups(overview):
    for group in (overview or {}).get('personal_records') or []:
        if isinstance(group, dict):
            yield group


def _is_positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def parse_personal_records(overview):
    """Current output records from /overview, keyed 'discipline|class length'.

    Peloton lists only the current record, so it can't tell us what a new PR
    beat; merge_personal_records keeps the one it replaced. Best Times are
    seconds, not output, so they're left to best_times_for.
    """
    records = {}
    for group in _record_groups(overview):
        discipline = group.get('slug') or group.get('name')
        if discipline == BEST_TIMES_GROUP:
            continue
        for record in group.get('records') or []:
            if not isinstance(record, dict):
                continue
            raw = record.get('raw_value')
            workout_id = record.get('workout_id')
            # Unset lengths come back as -1 with no workout.
            if (
                not discipline
                or not record.get('name')
                or not isinstance(workout_id, str)
                or isinstance(raw, bool)
                or not isinstance(raw, (int, float))
                or raw <= 0
            ):
                continue
            records[f'{discipline}|{record["name"]}'] = {
                'value_kj': round(raw / 1000, 1),
                'workout_id': workout_id,
                'workout_date': record.get('workout_date'),
            }
    return records


def merge_personal_records(stored, fresh):
    """Fold a fresh records table into the stored one.

    When a record's workout ID changes, a new PR replaced it, so the stored
    entry becomes that record's 'previous'. The same workout ID means nothing
    changed and the earlier 'previous' is kept. Records missing from the fresh
    table (a partial API response) are kept rather than forgotten.
    """
    # Before Best Times were parsed apart, their seconds were stored as output ('0.6 kJ' for 10:33).
    merged = {key: record for key, record in (stored or {}).items() if not key.startswith(f'{BEST_TIMES_GROUP}|')}
    for key, record in fresh.items():
        old = merged.get(key)
        if old is None:
            merged[key] = record
        elif old.get('workout_id') != record['workout_id']:
            previous = {k: old[k] for k in ('value_kj', 'workout_id', 'workout_date') if k in old}
            merged[key] = {**record, 'previous': previous}
    return merged


def best_times_for(workout_id, overview):
    """The Best Times this workout holds, in Peloton's order: [{'label': '1 MILE', 'seconds': 1005.0}].

    The label is the record's own slug ('1K', '1 Mile'), so a distance the board hasn't seen yet
    still gets a name. Empty when the workout holds none, or the overview is missing or damaged.
    """
    if not isinstance(workout_id, str) or not workout_id:
        return []
    bests = []
    for group in _record_groups(overview):
        if group.get('slug') != BEST_TIMES_GROUP:
            continue
        records = group.get('records')
        for record in records if isinstance(records, list) else []:
            if not isinstance(record, dict) or record.get('workout_id') != workout_id:
                continue
            label = record.get('slug') or record.get('name')
            if isinstance(label, str) and label.strip() and _is_positive(record.get('raw_value')):
                bests.append({'label': label.strip().upper(), 'seconds': float(record['raw_value'])})
    return bests


def previous_best_kj(workout_id, records):
    """The output record a PR workout beat, if we saw it before the PR happened."""
    for record in (records or {}).values():
        if record.get('workout_id') == workout_id:
            previous = record.get('previous') or {}
            value = previous.get('value_kj')
            return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return None
