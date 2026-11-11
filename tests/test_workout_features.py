"""Workout compare rows: build_row, bike plan and strength asks from hand-made raw responses."""
from datetime import datetime, timezone

import pytest

from peloton.workout_features import (BIKE_CURVE, bike_plan, build_row, discipline, planned_watts,
                                      strength_asks)

START = 1_700_000_000


def detail(**over):
    base = {'id': 'w1', 'start_time': START, 'end_time': START + 1200, 'status': 'COMPLETE',
            'fitness_discipline': 'cycling', 'timezone': 'UTC',
            'ride': {'id': 'r1', 'title': 'Ride', 'duration': 1200, 'instructor': {'name': 'Ann'}}}
    base.update(over)
    return base


def graph(metrics=None, n=0, **extra):
    """n samples, 5 seconds apart; metrics is {slug: values}."""
    g = {'seconds_since_pedaling_start': [5 * i for i in range(n)], 'duration': 5 * n,
         'metrics': [{'slug': k, 'values': v} for k, v in (metrics or {}).items()]}
    g.update(extra)
    return g


def seg(slug, start, length, **extra):
    return {'icon_slug': slug, 'start_time_offset': start, 'length': length, **extra}


def test_heart_rate_zeros_are_dropped():
    row = build_row(detail(), graph({'heart_rate': [0, 100, 120, 0], 'output': [10, 20, 30, 40]}, 4))
    assert row['hr_avg'] == 110.0
    assert row['hr_max'] == 120
    assert row['work']['heart_rate'] == 110.0
    assert row['work']['output'] == 25.0


@pytest.mark.parametrize('slug', ['warmup', 'cooldown'])
def test_class_of_one_rest_block_counts_whole_as_work(slug):
    row = build_row(detail(), graph({'output': [10, 20, 30, 40]}, 4, segment_list=[seg(slug, 0, 20)]))
    assert row['work_secs'] == 20
    assert row['work']['output'] == 25.0
    assert row['mix'] == {'rest': 20}
    assert row['mode'] == 'plain'


def test_freestyle_counts_whole_as_work():
    row = build_row(detail(), graph({'output': [10, 20, 30, 40]}, 4))
    assert row['work_secs'] == 20
    assert row['work']['output'] == 25.0
    assert row['mix'] == {} and row['mode'] == 'plain'


@pytest.mark.parametrize('raw, expected', [('caesar', 'rowing'), ('caesar_bootcamp', 'row_bootcamp'),
                                           ('circuit', 'tread_bootcamp'), ('cycling', 'cycling')])
def test_discipline_alias(raw, expected):
    assert discipline(raw) == expected
    assert build_row(detail(fitness_discipline=raw))['disc'] == expected


def test_callouts_count_only_inside_work_segments():
    cadence = [70, 70, 70, 90, 90, 90] + [0] * 6
    cadence = [50] * 12 + cadence  # 18 samples: warm-up 0-60 then work from 60
    g = graph({'cadence': cadence}, 18, segment_list=[seg('warmup', 0, 60), seg('cycling', 60, 30)])
    g['target_metrics_performance_data'] = {'target_metrics': [
        {'offsets': {'start': 10, 'end': 29}, 'metrics': [{'name': 'cadence', 'lower': 60, 'upper': 80}]},
        {'offsets': {'start': 60, 'end': 89}, 'metrics': [
            {'name': 'cadence', 'lower': 80, 'upper': 100}, {'name': 'resistance', 'lower': 5, 'upper': 5}]}]}
    row = build_row(detail(), g)
    assert row['target'] == {'cadence': 90.0, 'resistance': 5.0}  # the warm-up callout (mid 70) is ignored
    assert row['target_pos'] == {'cadence': 0.0}  # 70 -> -0.5, 90 -> +0.5 against 80..100
    assert row['target_in'] == {'cadence': 50}
    assert row['target_under'] == {'cadence': 50}


def test_graph_none_gives_a_bare_row():
    row = build_row(detail(), None)
    assert row['has_graph'] is False
    assert row['work'] == {} and row['hr_avg'] is None and row['hr_max'] is None
    assert row['dur'] == 1200
    assert row['elapsed'] == 1200
    assert row['hr_zone'] is None and 'eff' not in row and 'plan' not in row


def test_ctype_from_ride_details():
    assert build_row(detail(), None, None)['ctype'] is None
    assert build_row(detail(), None, {'class_types': []})['ctype'] is None
    assert build_row(detail(), None, {'class_types': [{'name': 'Rhythm'}, {'name': 'Climb'}]})['ctype'] == 'Rhythm/Climb'


def test_strength_tracker_without_repetition_data():
    d = detail(fitness_discipline='strength',
               movement_tracker_data={'completed_movements_summary_data': {'total_volume': 100}})
    row = build_row(d)
    assert row['tracker']['volume'] == 100
    assert row['sets'] == []
    assert row['tracker']['weights'] == {}


def test_strength_tracker_sets_and_weights():
    summary = {
        'total_volume': 900, 'total_repetitions': 30, 'num_movements': 2, 'num_targets_reached': 1,
        'repetition_summary_data': [
            {'movement_name': 'Squat', 'movement_id': 'm1', 'tracking_type': 'repetition', 'offset': 10,
             'length': 40, 'completed_number': 10, 'target_number': 10, 'is_target_reached': True,
             'is_hold': 1, 'total_volume': 200,
             'weight': [{'weight_data': {'weight_value': 20}, 'weight_category': 'heavy_weight'}]},
            {'movement_name': 'Plank', 'is_target_reached': False}],
        'weight_info_summary_data': {'heavy_weight': [{'weight_value': 20}, {'weight_value': 15}],
                                     'light_weight': [], 'medium_weight': [{'weight_value': 10}]}}
    row = build_row(detail(fitness_discipline='strength',
                           movement_tracker_data={'completed_movements_summary_data': summary}))
    first, second = row['sets']
    assert (first['lb'], first['cat'], first['hit'], first['hold']) == (20, 'heavy_weight', True, True)
    assert first['name'] == 'Squat' and first['done'] == 10 and first['len'] == 40
    assert (second['lb'], second['cat'], second['hit'], second['hold']) == (None, None, False, False)
    assert row['tracker']['weights'] == {'heavy': [15, 20], 'medium': [10]}
    assert row['tracker']['reps'] == 30 and row['tracker']['targets_hit'] == 1


def test_timezone_falls_back_to_utc_and_real_zone_gives_local_date():
    ts = int(datetime(2026, 11, 11, 0, 30, tzinfo=timezone.utc).timestamp())
    assert build_row(detail(start_time=ts, end_time=ts + 10, timezone='No/Such_Zone'))['date'] == '2026-11-11'
    assert build_row(detail(start_time=ts, end_time=ts + 10, timezone=None))['date'] == '2026-11-11'
    assert build_row(detail(start_time=ts, end_time=ts + 10, timezone='America/New_York'))['date'] == '2026-11-10'


@pytest.mark.parametrize('status, elapsed, expected', [
    ('COMPLETE', 799, False), ('COMPLETE', 800, True), ('COMPLETE', 1000, True), ('CANCELLED', 1000, False)])
def test_complete_needs_status_and_eighty_percent(status, elapsed, expected):
    d = detail(status=status, end_time=START + elapsed)
    d['ride']['duration'] = 1000
    assert build_row(d)['complete'] is expected


def test_mode_floor_arms_plain_and_floor_heart_rate():
    heart = [100] * 12 + [150] * 12
    floor = graph({'heart_rate': heart}, 24, segment_list=[seg('run', 0, 60), seg('floor', 60, 60, metrics_type='floor')])
    row = build_row(detail(), floor)
    assert row['mode'] == 'floor' and row['mix'] == {'work': 60, 'floor': 60}
    assert row['floor_hr'] == 150.0
    assert row['work_secs'] == 60 and row['work']['heart_rate'] == 100.0

    arms = build_row(detail(), graph(n=24, segment_list=[seg('cycling', 0, 60), seg('upper_body', 60, 60)]))
    assert arms['mode'] == 'arms' and arms['arms_sections'] == 1

    plain = build_row(detail(), graph(n=24, segment_list=[seg('cycling', 0, 120)]))
    assert plain['mode'] == 'plain' and plain['arms_sections'] == 0


def _eff_graph(n, speed=10, output=100):
    return {'seconds_since_pedaling_start': [5 * i for i in range(n)], 'duration': 5 * n, 'metrics': [
        {'slug': 'output', 'values': [output] * n, 'alternatives': [{'slug': 'speed', 'values': [speed] * n}]},
        {'slug': 'heart_rate', 'values': [100] * n}]}


def test_foot_disciplines_use_speed_and_eff_needs_24_samples():
    short = build_row(detail(fitness_discipline='running'), _eff_graph(23))
    assert short['main'] == 'speed' and 'eff' not in short
    full = build_row(detail(fitness_discipline='running'), _eff_graph(24))
    assert full['main'] == 'speed' and full['eff'] == 0.1
    bike = build_row(detail(fitness_discipline='cycling'), _eff_graph(24))
    assert bike['main'] == 'output' and bike['eff'] == 1.0


def test_pace_plan_level_fit_and_form_score():
    g = graph(n=24, segment_list=[seg('rowing', 0, 120)])
    g['target_metrics_performance_data'] = {'target_metrics': [
        {'offsets': {'start': 0, 'end': 59}, 'metrics': [{'name': 'pace_intensity', 'lower': 2, 'upper': 3}]},
        {'offsets': {'start': 60, 'end': 119}, 'metrics': [{'name': 'pace_intensity', 'lower': 4, 'upper': 5}]}]}
    g['target_metrics_compliance'] = {
        'workout_pace_level': 3,
        'pace_intensities_target_compliance_percentage': {
            'overall': {'below_target': 10, 'in_target': 80, 'above_target': 10}}}
    g['caesar_metrics'] = {'detail': {'score': 85}}
    row = build_row(detail(fitness_discipline='caesar'), g)
    assert row['pace_plan'] == {'2': 50, '4': 50}
    assert row['pace_level'] == 3
    assert row['pace_fit'] == [10, 80, 10]
    assert row['form_score'] == 85
    assert 'target' not in row and 'plan' not in row

    g['target_metrics_compliance'] = {'workout_pace_level': 2}
    row = build_row(detail(fitness_discipline='caesar'), g)
    assert row['pace_level'] == 2 and 'pace_fit' not in row


def test_leaderboard_percentile():
    assert build_row(detail(leaderboard_rank=10, total_leaderboard_users=100))['lb_pct'] == 90.0
    assert build_row(detail(leaderboard_rank=10))['lb_pct'] is None
    assert build_row(detail())['lb_pct'] is None


def test_summaries_zones_and_effort_fields():
    g = graph({'output': [1, 2]}, 2, summaries=[{'slug': 'total_output', 'value': 200},
                                                {'slug': 'distance', 'value': 5.5},
                                                {'slug': 'elevation', 'value': 30}],
              effort_zones={'heart_rate_zone_durations': {'heart_rate_z1_duration': 10, 'heart_rate_z3_duration': 5}})
    d = detail(hr_total_points=12.34, is_outdoor=True, workout_type='class')
    d['ride']['difficulty_estimate'] = 7.456
    row = build_row(d, g)
    assert (row['total_kj'], row['distance'], row['elevation']) == (200, 5.5, 30)
    assert row['hr_zone'] == [10, 0, 5, 0, 0]
    assert row['strive'] == 12.3 and row['difficulty'] == 7.46
    assert row['outdoor'] is True and row['instructor'] == 'Ann' and row['ride_id'] == 'r1'
    assert build_row(detail(), g)['strive'] is None


def test_planned_watts_clamps_low_cadence_and_resistance():
    assert planned_watts(10, 3) == planned_watts(20, 5)
    assert planned_watts(30, 5) > planned_watts(20, 5)
    assert planned_watts(60, 30) == pytest.approx(
        pow(2.718281828459045, BIKE_CURVE[0]) * 60 ** BIKE_CURVE[1] * 30 ** BIKE_CURVE[2])


def bike_graph(burst=True, n=84):
    """12 warm-up samples, 60 riding samples (cadence 80-90, resistance 40-50), 12 arms samples."""
    cad_hi, cad_lo, res_hi, res_lo = [90] * n, [80] * n, [50] * n, [40] * n
    for i in range(12):
        cad_hi[i], cad_lo[i], res_hi[i], res_lo[i] = 40, 30, 20, 10
    for i in range(72, n):
        cad_hi[i], cad_lo[i], res_hi[i], res_lo[i] = 200, 200, 90, 90
    if burst:
        for i in (32, 33, 52):  # a 10 s stretch and a lone 5 s sample
            res_hi[i], res_lo[i] = 70, 60
    return {'duration': 420,
            'segment_list': [seg('warmup', 0, 60), seg('cycling', 60, 300), seg('upper_body', 360, 60)],
            'target_performance_metrics': {'target_graph_metrics': [
                {'type': 'cadence', 'graph_data': {'upper': cad_hi, 'lower': cad_lo}},
                {'type': 'resistance', 'graph_data': {'upper': res_hi, 'lower': res_lo}}]}}


def test_bike_plan_constant_ride():
    plan = bike_plan(bike_graph(burst=False))
    assert plan['ride_min'] == 5.0 and plan['arms_min'] == 1.0
    assert plan['planned_watts'] == round(planned_watts(85, 45), 3)
    assert plan['planned_watts_high'] == plan['planned_watts']
    assert plan['effort_share'] == 0 and plan['efforts_per_10min'] == 0 and plan['effort_length_s'] == 0
    assert plan['cadence_mean'] == 85 and plan['resistance_mean'] == 45
    assert set(plan) == {'ride_min', 'arms_min', 'planned_watts', 'planned_watts_high', 'effort_share',
                         'efforts_per_10min', 'effort_length_s', 'cadence_mean', 'resistance_mean'}


def test_bike_plan_counts_ten_second_effort_not_a_single_sample():
    plan = bike_plan(bike_graph())
    assert plan['effort_length_s'] == 10
    assert plan['efforts_per_10min'] == 2.0  # one effort in five minutes
    assert plan['effort_share'] == round(10 / 300, 3)
    assert plan['resistance_mean'] == 46.0  # arms and warm-up samples left out
    assert plan['planned_watts'] > round(planned_watts(85, 45), 3)
    assert plan['planned_watts_high'] == round(planned_watts(85, 45), 3)


def test_bike_plan_none_cases():
    g = bike_graph()
    lines = g['target_performance_metrics']['target_graph_metrics']
    assert bike_plan({}) is None
    assert bike_plan({**g, 'target_performance_metrics': {'target_graph_metrics': lines[:1]}}) is None
    assert bike_plan({**g, 'segment_list': g['segment_list'] + [seg('floor', 420, 60, metrics_type='floor')]}) is None
    # 24 samples, one dropped (None) -> 23 riding samples
    short = {'target_performance_metrics': {'target_graph_metrics': [
        {'type': 'cadence', 'graph_data': {'upper': [90] * 24, 'lower': [80] * 24}},
        {'type': 'resistance', 'graph_data': {'upper': [50] * 23 + [None], 'lower': [40] * 24}}]}}
    assert bike_plan(short) is None
    short['target_performance_metrics']['target_graph_metrics'][1]['graph_data']['upper'][-1] = 50
    assert bike_plan(short)['ride_min'] == 2.0  # no segments: every sample rides


def test_build_row_plan_on_cycling_only_when_a_plan_exists():
    assert 'plan' in build_row(detail(), bike_graph())
    assert 'plan' in build_row(detail(fitness_discipline='bike_bootcamp'), bike_graph())
    assert 'plan' not in build_row(detail(fitness_discipline='caesar'), bike_graph())
    assert 'plan' not in build_row(detail(), graph(n=10))


def mv(name, **extra):
    return {'name': name, **extra}


def sub(kind, offset, length, *movements):
    return {'type': kind, 'offset': offset, 'length': length, 'movements': list(movements)}


def strength_ride():
    subs = [
        sub('normal', 0, 120, mv('Warm Up Flow')),
        sub('normal', 120, 60, mv('Squat', target_number=10, tracking_type='repetition', weight_level='heavy',
                                  muscle_groups=[{'muscle_group': 'Quads', 'ranking': 2}])),
        sub('normal', 180, 60, mv('Plank', tracking_type='time_based', weight_level='light',
                                  muscle_groups=[{'muscle_group': 'Core'}])),
        sub('rest', 240, 30, mv('Rest')),
        sub('normal', 270, 30, mv('Pause', is_rest=True)),
        sub('emom_group', 300, 120, mv('Burpee', target_number=5, tracking_type='repetition')),
        sub('complex_group', 420, 60, mv('Clean', target_number=5, tracking_type='repetition')),
        {'type': 'normal', 'scheduled_offset': 480, 'length': 30,
         'movements': [mv('Curl', target_number=8, tracking_type='repetition', weight_level='medium',
                          muscle_groups=[{'muscle_group': None}])]},
        sub('normal', 510, 30, mv('Stretch', tracking_type='repetition')),
        {'type': 'normal', 'length': 30, 'movements': [mv('No offset', target_number=3)]},
    ]
    return {'segments': {'segment_list': [{'subsegments_v2': subs[:5]}, {'subsegments_v2': subs[5:]}],
                         'movement_patterns': [{'slug': 'push', 'percentage': 40}]}}


def test_strength_asks_summary():
    asks = strength_asks(strength_ride())
    assert asks['work_min'] == 6.0  # warm-up, rest and no-offset blocks dropped
    assert asks['counted_sets'] == 2 and asks['reps_asked'] == 18
    assert asks['timed_sets'] == 2 and asks['timed_min'] == 1.5
    assert asks['blocks_min'] == {'compound': 1.0, 'emom': 2.0}
    assert asks['levels'] == {'not_stated': 58, 'heavy': 17, 'light': 17, 'medium': 8}
    assert asks['muscles'] == {'Quads': 67, 'Core': 33}


def test_strength_asks_none_without_movements():
    assert strength_asks(None) is None
    assert strength_asks({}) is None
    assert strength_asks({'segments': {'segment_list': [{'subsegments_v2': [
        sub('normal', 0, 60, mv('Warm-up')), sub('rest', 60, 30, mv('Rest'))]}]}}) is None


def test_build_row_asks_only_on_strength_rows():
    d = detail(fitness_discipline='strength')
    d['ride']['muscle_group_score'] = [{'muscle_group': 'Quads', 'percentage': 50}, {'muscle_group': 'Core', 'percentage': 0}]
    row = build_row(d, None, strength_ride())
    assert row['asks']['counted_sets'] == 2
    assert row['muscles'] == {'Quads': 50}
    assert row['patterns'] == {'push': 40}
    assert 'tracker' not in row
    assert 'asks' not in build_row(d, None, None)
    assert 'asks' not in build_row(detail(), None, strength_ride())
    g = graph(n=2, muscle_group_score=[{'muscle_group': 'Back', 'percentage': 30}])
    assert build_row(d, g, None)['muscles'] == {'Back': 30}


@pytest.mark.parametrize('bad', [None, {}, {'id': 'x'}, {'start_time': 1}, {'id': '', 'start_time': 1}, 'nope'])
def test_build_row_requires_id_and_start_time(bad):
    with pytest.raises(ValueError):
        build_row(bad)
