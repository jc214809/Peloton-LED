"""Synthetic API-shaped data for offline screen previews."""
from copy import deepcopy


def demo_data():
    workouts, performance = [], {}
    for i, (discipline, title, distance, units) in enumerate([
        ('cycling', '30 min Power Zone Endurance Ride', 9.5, 'mi'),
        ('running', '20 min A Very Long Outdoor Endurance Run Title', 4, 'km'),
        ('walking', '20 min Recovery Walk', 1, 'mi'),
        ('rowing', '20 min Endurance Row', 4000, 'm'),
        ('strength', '20 min Full Body Strength', None, None),
    ]):
        identity = 'demo-' + discipline
        workouts.append({'id': identity, 'status': 'COMPLETE', 'start_time': 1773496800 - i * 3600,
            'timezone': 'America/New_York', 'is_total_work_personal_record': i == 0,
            'ride': {'fitness_discipline': discipline, 'title': title, 'duration': 1800 if i == 0 else 1200}})
        summaries = [{'slug': 'calories', 'value': 210 + i * 15, 'display_unit': 'kcal'}]
        if distance is not None:
            summaries.append({'slug': 'distance', 'value': distance, 'display_unit': units})
        if i == 0:
            summaries.append({'slug': 'total_output', 'value': 250, 'display_unit': 'kj'})
        metrics = [{'slug': 'heart_rate', 'average_value': 135, 'max_value': 161, 'display_unit': 'bpm'}]
        if i == 0:
            metrics += [{'slug': 'cadence', 'average_value': 84, 'display_unit': 'rpm'},
                        {'slug': 'resistance', 'average_value': 42, 'display_unit': '%'}]
        if i == 3:
            metrics += [{'slug': 'stroke_rate', 'average_value': 24, 'display_unit': 'spm'},
                        {'slug': 'output', 'average_value': 115, 'display_unit': 'w'}]
        performance[identity] = {'duration': 1800 if i == 0 else 1200, 'summaries': summaries,
                                'metrics': metrics, 'effort_zones': {'total_effort_points': 32}}
    # Deliberately omit strength metrics to exercise missing-data rendering.
    performance['demo-strength'] = {'duration': 1200}
    return deepcopy({'me': {'id': 'demo', 'username': 'Demo Rider', 'timezone': 'America/New_York'},
        'overview': {'workout_counts': [{'name': label, 'count': count} for label, count in
            [('Total Workouts', 1531), ('Cycling', 1234), ('Running', 204),
             ('Walking', 75), ('Rowing', 18), ('Strength', 0)]]},
        'workouts': workouts, 'performance': performance})
