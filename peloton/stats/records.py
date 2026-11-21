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


def parse_personal_records(overview):
    """Current output records from /overview, keyed 'discipline|class length'.

    Peloton lists only the current record, so it can't tell us what a new PR
    beat; merge_personal_records keeps the one it replaced.
    """
    records = {}
    for group in (overview or {}).get('personal_records') or []:
        if not isinstance(group, dict):
            continue
        discipline = group.get('slug') or group.get('name')
        for record in group.get('records') or []:
            if not isinstance(record, dict):
                continue
            raw = record.get('raw_value')
            workout_id = record.get('workout_id')
            # Unset lengths come back as -1 with no workout.
            if (not discipline or not record.get('name') or not isinstance(workout_id, str)
                    or isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0):
                continue
            records[f"{discipline}|{record['name']}"] = {
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
    merged = dict(stored or {})
    for key, record in fresh.items():
        old = merged.get(key)
        if old is None:
            merged[key] = record
        elif old.get('workout_id') != record['workout_id']:
            previous = {k: old[k] for k in ('value_kj', 'workout_id', 'workout_date') if k in old}
            merged[key] = {**record, 'previous': previous}
    return merged


def previous_best_kj(workout_id, records):
    """The output record a PR workout beat, if we saw it before the PR happened."""
    for record in (records or {}).values():
        if record.get('workout_id') == workout_id:
            previous = record.get('previous') or {}
            value = previous.get('value_kj')
            return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return None

