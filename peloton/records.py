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

