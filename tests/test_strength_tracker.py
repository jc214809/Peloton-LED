"""Strength pages: what Peloton's movement tracker counted (reps, volume, targets, the top lift)."""
import copy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
import requests

from display.display import initialize_fonts
from display.ui.last_workout_screen import (TRACKER_TIER_COLORS, LastWorkoutScreen, detail_hold_seconds,
                                           rotating_details, stats_phase_seconds, strength_tracker as screen_tracker,
                                           top_lift_text)
from peloton.dashboard import Dashboard
from peloton.demo import demo_data
from peloton.summaries import strength_tracker, summarize_workout
from scripts.render_demo import ImageMatrix
from tests.test_dashboard import setup_dashboard

GOLD = TRACKER_TIER_COLORS['gold']


def movement(name, reps, volume, weights, tags=()):
    return {'movement_name': name, 'tags': list(tags),
            'stats': [{'slug': 'total_reps', 'completed_number': reps},
                      {'slug': 'total_volume', 'completed_number': volume}],
            'weight_info_summary_data': {'light_weights': None,
                                         'medium_weights': [{'weight_value': w, 'weight_unit': 'lb'} for w in weights]}}


def detail(tier='gold', **summary):
    """The workout detail's tracker part, shaped like Peloton's (GET /api/workout/<id>)."""
    tracked = {'total_repetitions': 195, 'total_volume': 8930, 'weight_unit': 'lb', 'num_movements': 17,
               'completion_percentage': 100, 'longest_streak': 17,
               'movement_aggregate_data': [
                   movement('Goblet Squat', 40, 1600, [40.0], ['most_reps']),
                   movement('Neutral Grip Chest Press', 33, 2640, [30.0, 40.0], ['most_volume'])]}
    tracked.update(summary)
    return {'id': 'w1', 'status': 'COMPLETE', 'movement_tracker_tier': tier,
            'movement_tracker_data': {'completed_movements_summary_data': tracked}}


# --- peloton.summaries.strength_tracker ---

def test_tracker_figures_come_from_the_workout_detail():
    assert strength_tracker(detail()) == {
        'reps': 195, 'volume': 8930, 'unit': 'lb', 'movements': 17, 'targets_pct': 100, 'streak': 17,
        'tier': 'gold', 'top': {'name': 'Neutral Grip Chest Press', 'reps': 33, 'volume': 2640, 'weight': 40.0}}


def test_the_top_lift_falls_back_to_the_most_reps_and_needs_a_tag():
    aggregates = [movement('Goblet Squat', 40, None, [], ['most_reps']), movement('Plank', None, None, [])]
    assert strength_tracker(detail(movement_aggregate_data=aggregates))['top'] == {
        'name': 'Goblet Squat', 'reps': 40, 'volume': None, 'weight': None}
    assert strength_tracker(detail(movement_aggregate_data=[movement('Plank', 3, 0, [])]))['top'] is None


def test_a_bodyweight_class_has_no_volume_and_odd_values_are_dropped():
    figures = strength_tracker(detail(tier='inprogress', total_volume=None, completion_percentage=140,
                                      longest_streak=True, total_repetitions='lots'))
    assert figures['volume'] is None and figures['targets_pct'] is None and figures['streak'] is None
    assert figures['reps'] is None and figures['tier'] is None   # "inprogress" isn't a medal
    assert figures['movements'] == 17


def test_volume_needs_a_known_weight_unit():
    assert strength_tracker(detail(weight_unit='kg'))['unit'] == 'kg'
    odd = strength_tracker(detail(weight_unit='stone'))
    assert odd['volume'] is None and odd['top'] is None and odd['reps'] == 195


@pytest.mark.parametrize('value', [None, {}, {'movement_tracker_data': None},
                                   {'movement_tracker_data': {'completed_movements_summary_data': None}},
                                   {'movement_tracker_data': {'completed_movements_summary_data': {}}}, 'junk'])
def test_an_untracked_class_has_no_tracker_figures(value):
    assert strength_tracker(value) is None


def test_the_summary_carries_the_tracker_only_with_a_detail():
    workout = demo_data()['workouts'][-1]
    assert summarize_workout(workout)['strength'] is None
    assert summarize_workout(workout, None, detail())['strength']['reps'] == 195


# --- The workout page ---

def strength_page(figures=None):
    data = demo_data()
    summary = summarize_workout(data['workouts'][-1], data['performance']['demo-strength'], detail())
    if figures is not None:
        summary['strength'] = figures
    return {**summary, 'hr_avg': 118, 'calories': 92, 'strive_score': 12.5,
            'hr_zone_seconds': [60, 60, 60, 0, 0]}


@pytest.mark.parametrize('height', [32, 64])
def test_a_tracked_class_shows_reps_volume_targets_and_the_top_lift_instead_of_muscles(height):
    labels = [d['label'] for d in rotating_details(strength_page(), height) if d['label'] != 'instructor']
    assert labels[:4] == ['strive score', 'total reps', 'total volume', 'targets hit']
    assert labels[-1] == 'top lift' and 'muscles worked' not in labels
    values = {d['label']: d['value'] for d in rotating_details(strength_page(), height)}
    assert values['total volume'] == '8,930 lb' and values['targets hit'] == '100%'


@pytest.mark.parametrize('height', [32, 64])
def test_an_untracked_class_keeps_the_muscles_slide(height):
    labels = [d['label'] for d in rotating_details(strength_page(None) | {'strength': None}, height)]
    assert labels[-1] == 'muscles worked'
    assert not {'total reps', 'total volume', 'targets hit', 'top lift'} & set(labels)


@pytest.mark.parametrize('bad', ['junk', 7, {'reps': '195', 'volume': -1, 'unit': 'lb', 'targets_pct': 101,
                                             'tier': 'platinum', 'top': {'name': '', 'reps': 3}},
                                 {'top': 'Squat'}, {'top': {'name': 'Squat', 'reps': None, 'weight': True}}])
def test_a_malformed_cache_entry_shows_nothing_new(bad):
    assert screen_tracker({'strength': bad}).get('top') is None
    labels = [d['label'] for d in rotating_details(strength_page(bad), 64)]
    assert labels[-1] == 'muscles worked'
    assert not {'total reps', 'total volume', 'targets hit', 'top lift'} & set(labels)


def test_a_partial_tracker_shows_only_what_it_has():
    figures = {'reps': 23, 'volume': None, 'unit': 'lb', 'targets_pct': 0, 'tier': None, 'top': None}
    details = rotating_details(strength_page(figures), 64)
    assert [d['label'] for d in details if d['label'] in ('total reps', 'total volume', 'targets hit')] == [
        'total reps', 'targets hit']
    assert next(d for d in details if d['label'] == 'targets hit').get('color') is None
    # No top lift, but the tracker's stats are there, so the muscles slide still makes way.
    assert details[-1]['label'] == 'hr zones'


@pytest.mark.parametrize('top, text', [({'reps': 33, 'weight': 40.0}, '33 X 40 LB'),
                                       ({'reps': 79, 'weight': None}, '79 REPS'),
                                       ({'reps': None, 'weight': 12.5}, '12.5 LB')])
def test_top_lift_text(top, text):
    assert top_lift_text(top, 'lb') == text


def test_the_new_slide_holds_as_long_as_the_other_slides_and_the_page_counts_it():
    details = rotating_details(strength_page(), 64)
    top = next(d for d in details if d['kind' if 'kind' in d else 'label'] == 'top_lift')
    assert detail_hold_seconds(top, 4) == detail_hold_seconds({'kind': 'muscles'}, 4) == 5
    assert stats_phase_seconds(details, 4) == sum(detail_hold_seconds(d, 4) for d in details)


def frame(summary, height, label):
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    details = rotating_details(summary, height)
    turn = [d['label'] for d in details].index(label)
    screen = LastWorkoutScreen()
    screen.on_enter(matrix, summary)
    screen.update(4 + sum(detail_hold_seconds(d, 4) for d in details[:turn]) + 0.5)
    assert screen.render(matrix, summary)
    return matrix.image


def pixels_of(image, rgb):
    return [(x, y) for y in range(image.height) for x in range(image.width) if image.getpixel((x, y)) == rgb]


@pytest.mark.parametrize('height', [32, 64])
def test_targets_hit_is_drawn_in_the_tier_colour(height):
    assert pixels_of(frame(strength_page(), height, 'targets hit'), GOLD)
    plain = strength_page() | {'strength': {**strength_page()['strength'], 'tier': None}}
    assert not pixels_of(frame(plain, height, 'targets hit'), GOLD)


@pytest.mark.parametrize('height', [32, 64])
def test_the_top_lift_slide_shows_the_lift_in_gold_inside_the_panel(height):
    image = frame(strength_page(), height, 'top lift')
    gold = pixels_of(image, (255, 200, 0))
    assert gold and max(y for _, y in gold) < height and min(x for x, _ in gold) >= 2
    heart = pixels_of(image, (220, 20, 20))
    # 64 rows keep the heart-rate row under it; 32 rows give it the whole panel, like the graph.
    assert bool(heart) is (height == 64)
    if height == 64:
        assert max(y for _, y in gold) < min(y for _, y in heart)


@pytest.mark.parametrize('height', [32, 64])
def test_a_long_or_short_movement_name_fits(height):
    for name in ('Crunch', 'Dumbbell Single Leg Romanian Deadlift'):
        figures = {**strength_page()['strength'], 'top': {'name': name, 'reps': 12, 'volume': None, 'weight': 25.0}}
        image = frame(strength_page(figures), height, 'top lift')
        lit = [(x, y) for y in range(height) for x in range(64) if image.getpixel((x, y)) != (0, 0, 0)]
        assert lit and min(x for x, _ in lit) >= 1 and max(x for x, _ in lit) <= 62


# --- The Dashboard fetches a strength class's detail ---

def strength_setup(tmp_path, config=None, discipline='strength'):
    dashboard, client, token = setup_dashboard(tmp_path, config)
    start = datetime.now(timezone.utc) - timedelta(days=2)
    client.history = [{'id': 'w1', 'status': 'COMPLETE', 'start_time': start.timestamp(),
                       'fitness_discipline': discipline}]
    client.get_perf_graph.return_value = {'duration': 1200}
    client.get_workout_detail.return_value = detail() | {'start_time': 1}
    return dashboard, client, token


def test_a_strength_class_is_fetched_once_and_its_tracker_shown(tmp_path):
    dashboard, client, _ = strength_setup(tmp_path)
    dashboard.refresh()
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['strength']['reps'] == 195
    client.get_workout_detail.assert_called_once_with('w1')


def test_other_disciplines_make_no_detail_call(tmp_path):
    dashboard, client, _ = strength_setup(tmp_path, discipline='yoga')
    dashboard.refresh()
    client.get_workout_detail.assert_not_called()
    assert dashboard.snapshot()['summaries'][0]['strength'] is None


def test_the_insights_reuse_the_fetched_detail(tmp_path):
    from unittest.mock import patch
    dashboard, client, _ = strength_setup(tmp_path, {'workout_insights': True})
    client.get_ride_details.return_value = None
    with patch('peloton.dashboard.build_row', side_effect=ValueError('no row')) as build:
        dashboard.refresh()
    assert client.get_workout_detail.call_count == 1
    assert build.call_args.args[0]['movement_tracker_data']   # the same detail went to the row


@pytest.mark.parametrize('reply', [None, {'id': 'other', 'status': 'COMPLETE'}, {'id': 'w1', 'status': 'IN_PROGRESS'}])
def test_a_bad_detail_shows_no_tracker_and_is_retried_after_the_window(tmp_path, reply):
    dashboard, client, _ = strength_setup(tmp_path)
    client.get_workout_detail.return_value = reply
    dashboard.refresh()
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['strength'] is None
    assert client.get_workout_detail.call_count == 1
    signature, kept, fetched = dashboard._details['w1']
    dashboard._details['w1'] = (signature, kept, fetched - 3601)
    client.get_workout_detail.return_value = detail() | {'id': 'w1'}
    dashboard.refresh()
    assert client.get_workout_detail.call_count == 2
    assert dashboard.snapshot()['summaries'][0]['strength']['reps'] == 195


@pytest.mark.parametrize('error', [requests.ConnectionError('down'), requests.HTTPError(response=Mock(status_code=500)),
                                   ValueError('bad json')])
def test_a_failed_detail_never_fails_the_refresh(tmp_path, caplog, error):
    dashboard, client, _ = strength_setup(tmp_path)
    client.get_workout_detail.side_effect = error
    dashboard.refresh()
    snapshot = dashboard.snapshot()
    assert snapshot['status'] == 'ready' and snapshot['summaries'][0]['strength'] is None
    assert f'Workout detail failed ({type(error).__name__})' in caplog.text


def test_an_unauthorized_detail_is_a_login_problem(tmp_path):
    dashboard, client, _ = strength_setup(tmp_path)
    client.get_workout_detail.side_effect = requests.HTTPError(response=Mock(status_code=401))
    dashboard.refresh()
    assert dashboard.login_required


def test_a_changed_workout_is_fetched_again_and_the_cache_stays_bounded(tmp_path):
    dashboard, client, _ = strength_setup(tmp_path)
    dashboard._performance_cache_size = 1
    dashboard.refresh()
    client.history = [dict(client.history[0], updated_at=12345)]   # Peloton revised the workout
    dashboard.refresh()
    assert client.get_workout_detail.call_count == 2
    client.history = [dict(client.history[0], id='w2')]
    client.get_workout_detail.return_value = detail() | {'id': 'w2'}
    dashboard.refresh()
    assert list(dashboard._details) == ['w2']


def test_a_restarted_board_reads_the_tracker_from_its_cache(tmp_path):
    dashboard, client, token = strength_setup(tmp_path)
    dashboard.refresh()
    again = Dashboard(token, {}, client_factory=lambda _: client)
    assert copy.deepcopy(again.snapshot()['summaries'][0]['strength']) == dashboard.snapshot()['summaries'][0]['strength']
