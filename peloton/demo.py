"""Synthetic API-shaped data for offline screen previews."""

import math
from copy import deepcopy
from datetime import UTC, datetime

from .workouts.insight_lines import board_view

_HR_ZONES = [(0, 119), (120, 137), (138, 156), (157, 174), (175, 185)]


def _ride_series(points=360):
    """Deterministic power-zone-style intervals: warm up, three efforts, cool down."""
    output, heart = [], []
    for i in range(points):
        t = i / points
        effort = 0.35 + 0.25 * t if t < 0.15 else 0.4 if t > 0.88 else (0.95 if math.sin(t * 6 * math.pi) > 0.3 else 0.6)
        output.append(round(90 + 190 * effort + 8 * math.sin(i / 3)))
        heart.append(round(100 + 70 * effort + 4 * math.sin(i / 7)))
    return output, heart


def demo_insights(*messages):
    """The board's views of canned (code, facts) pairs, as the dashboard would store them."""
    return [board_view(code, facts) for code, facts in messages]


def demo_data():
    workouts, performance = [], {}
    for i, (discipline, title, distance, units) in enumerate(
        [
            ('cycling', '30 min Power Zone Endurance Ride', 9.5, 'mi'),
            ('running', '20 min A Very Long Outdoor Endurance Run Title', 4, 'km'),
            ('walking', '20 min Recovery Walk', 1, 'mi'),
            ('rowing', '20 min Endurance Row', 4000, 'm'),
            ('strength', '20 min Full Body Strength', None, None),
        ]
    ):
        identity = 'demo-' + discipline
        workouts.append(
            {
                'id': identity,
                'status': 'COMPLETE',
                'start_time': 1773496800 - i * 3600,
                'timezone': 'America/New_York',
                'is_total_work_personal_record': i == 0,
                'ride': {'fitness_discipline': discipline, 'title': title, 'duration': 1800 if i == 0 else 1200},
            }
        )
        summaries = [{'slug': 'calories', 'value': 210 + i * 15, 'display_unit': 'kcal'}]
        if distance is not None:
            summaries.append({'slug': 'distance', 'value': distance, 'display_unit': units})
        if i == 0:
            summaries.append({'slug': 'total_output', 'value': 250, 'display_unit': 'kj'})
        metrics = [{'slug': 'heart_rate', 'average_value': 135, 'max_value': 161, 'display_unit': 'bpm'}]
        if i == 0:
            metrics += [
                {'slug': 'cadence', 'average_value': 84, 'display_unit': 'rpm'},
                {'slug': 'resistance', 'average_value': 42, 'display_unit': '%'},
            ]
        if i == 3:
            metrics += [
                {'slug': 'stroke_rate', 'average_value': 24, 'display_unit': 'spm'},
                {'slug': 'output', 'average_value': 115, 'display_unit': 'w'},
            ]
        effort_zones = {'total_effort_points': 32}
        if i == 0:
            output, heart = _ride_series()
            metrics[0].update(
                values=heart,
                zones=[
                    {'slug': f'zone{z + 1}', 'min_value': low, 'max_value': high, 'duration': 5 * sum(low <= bpm <= high for bpm in heart)}
                    for z, (low, high) in enumerate(_HR_ZONES)
                ],
            )
            metrics.append({'slug': 'output', 'average_value': 190, 'max_value': max(output), 'display_unit': 'watts', 'values': output})
            effort_zones['heart_rate_zone_durations'] = {
                f'heart_rate_z{z + 1}_duration': zone['duration'] for z, zone in enumerate(metrics[0]['zones'])
            }
        performance[identity] = {
            'duration': 1800 if i == 0 else 1200,
            'summaries': summaries,
            'metrics': metrics,
            'effort_zones': effort_zones,
        }
    # A Tread run's running form: scored only on the running stretches, walks in between left empty.
    performance['demo-running']['running_form_summary'] = {
        'running_efficiency_score': 71,
        'avg_rate_spm': 152.4,
        'avg_stride_length_cm': 118.6,
    }
    performance['demo-running']['metrics'].append(
        {
            'slug': 'running_efficiency_score',
            'values': [round(70 + 6 * math.sin(i / 4)) if i % 48 < 30 else None for i in range(240)],
        }
    )
    # Deliberately omit strength metrics to exercise missing-data rendering,
    # but keep muscle groups so the demo shows that slide.
    performance['demo-strength'] = {
        'duration': 1200,
        'muscle_group_score': [
            {'muscle_group': slug, 'display_name': name, 'percentage': pct, 'bucket': bucket}
            for slug, name, pct, bucket in [
                ('biceps', 'Biceps', 9, 1),
                ('quads', 'Quads', 24, 3),
                ('glutes', 'Glutes', 17, 3),
                ('hamstrings', 'Hamstrings', 14, 2),
                ('core', 'Core', 6, 1),
            ]
        ],
    }
    # Workout compare (display.workout_insights): what the board would say about two of the workouts.
    insights = {
        'demo-cycling': demo_insights(
            (
                'tough_class',
                {
                    'value': 124,
                    'usual': 188,
                    'unit': 'W',
                    'foot': False,
                    'noun': 'ride',
                    'n': 9,
                    'real': 9,
                    'reason': None,
                    'difficulty': 9.1,
                    'usual_difficulty': 7.0,
                    'rated': 12,
                },
            ),
            ('effort_high', {'n': 12, 'value': 29.4, 'noun': 'ride', 'rate': 0.98, 'usual_rate': 0.76}),
        ),
        # An instructor milestone (words only, gold): no figure, so one card / one page.
        'demo-rowing': demo_insights(('instructor_milestone', {'n': 200, 'name': 'Jess Sims', 'since': '2019-03-02'})),
        'demo-strength': demo_insights(
            (
                'go_up_lighter',
                {'movement': 'Bent Over Row', 'lb': 20, 'usual': 30, 'unit': 'lb', 'category': 'medium', 'on_movement': True, 'pct': 35},
            ),
            ('go_up_streak', {'lb': 40, 'unit': 'lb', 'category': 'heavy', 'n': 3, 'pct': 20}),
        ),
    }
    return deepcopy(
        {
            'me': {'id': 'demo', 'username': 'Demo Rider', 'timezone': 'America/New_York'},
            'overview': {
                'streaks': {'current_weekly': 23, 'best_weekly': 41, 'current_daily': 3},
                'workout_counts': [
                    {'name': label, 'count': count}
                    for label, count in [
                        ('Total Workouts', 1531),
                        ('Cycling', 1234),
                        ('Running', 204),
                        ('Walking', 75),
                        ('Rowing', 22),
                        ('Strength', 0),
                    ]
                ],
            },
            'workouts': workouts,
            'performance': performance,
            # Lifetime miles by discipline, as the dashboard's distance tally holds them.
            'distance_totals': {'cycling': 612.4, 'running': 88.2, 'walking': 41.0},
            'insights': insights,
            # GET challenges/current?has_joined=true: one challenge on a numbered tier, one between named tiers.
            'challenges': {
                'challenges': [
                    _demo_challenge('The Annual 2026', 5503, '5,503', 'min', ('5K', 5000), ('6K', 6000), '497'),
                    _demo_challenge('November 2026 Rep Goal Challenge', 1640, '1,640', 'reps', ('Bronze', 1500), ('Silver', 3000), '1,360'),
                ]
            },
        }
    )


def demo_bookings(now):
    """Two booked classes as the board keeps them (peloton.feeds.booked_classes.slim_class): a live ride in 45
    minutes, so the page counts down, and an encore Tread Bootcamp tomorrow."""
    return [
        {
            'id': 'demo-live-ride',
            'start': float(now + 45 * 60),
            'tag': 'LIVE',
            'discipline': 'cycling',
            'minutes': 20,
            'instructor': 'Ben Alldis',
        },
        {
            'id': 'demo-encore-bootcamp',
            'start': float(now + 26 * 3600),
            'tag': 'ENCORE',
            'discipline': 'tread_bootcamp',
            'minutes': 45,
            'instructor': 'Jess Sims',
        },
    ]


def demo_club_score(now):
    """GET members-score .../v2/user/{id}/score, cut to what the board reads: Gold III, 1,341 points from
    Champion, with a double-points boost running for another week."""
    expires = datetime.fromtimestamp(now + 7 * 86400, UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
    return {
        'badge_level_name': 'Gold III',
        'total_earned_points': 13659,
        'boost': {'status': 'active', 'expires_at': expires, 'title': 'Double Club Peloton points'},
        'progress_bar': {
            'badge_level_name': 'Gold III',
            'score': 13659,
            'ignore_segments_on_profile': False,
            'tier_base_points': 2000,
            'tier_max_points': 15000,
            'segment_tiers_max_points': [
                {'label': 'Gold I', 'min_points': 2000, 'max_points': 4000, 'next_level_name': 'Gold II'},
                {'label': 'Gold II', 'min_points': 4000, 'max_points': 6000, 'next_level_name': 'Gold III'},
                {'label': 'Gold III', 'min_points': 6000, 'max_points': 15000, 'next_level_name': 'Champion'},
            ],
        },
    }


def demo_club(now):
    """The demo rider's Club Peloton record as the board keeps it (peloton.feeds.club.parse_score)."""
    from .feeds.club import parse_score

    return parse_score(demo_club_score(now), now)


def _demo_challenge(title, value, shown, unit, tier, following, to_next):
    def level(name, at):
        return {'title': name, 'metric_value': float(at), 'metric_display_value': f'{at:,}', 'metric_display_unit': unit}

    return {
        'challenge_summary': {'id': title.lower().replace(' ', '-'), 'title': title, 'start_time': 1767225600, 'end_time': 4102444799},
        'progress': {
            'has_joined': True,
            'metric_value': value,
            'metric_display_value': shown,
            'metric_display_unit': unit,
            'metric_display_value_to_next_tier': to_next,
            'current_tier': level(*tier),
            'next_tier': level(*following),
        },
    }
