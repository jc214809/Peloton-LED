"""Distance journey: tally, route progress, config, dashboard backfill, screen."""
import json
from unittest.mock import Mock

import pytest

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.journey_screen import CASTLE_COLORS, JourneyScreen, journey_text
from peloton.cache import load_snapshot, save_snapshot
from peloton.config import load_config
from peloton.dashboard import TALLY_VERSION
from peloton.journey import (DEFAULT_JOURNEY, DISTANCE_DISCIPLINES, journey_progress,
                             merge_distance_totals, uses_metric, workout_miles)
from peloton.selection import normalize_discipline
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix
from tests.test_dashboard import setup_dashboard


def row(discipline, distance, workout_id='w', status='COMPLETE'):
    return {'id': workout_id, 'status': status, 'fitness_discipline': discipline, 'distance': distance}


def test_workout_miles_handles_units_and_bad_values():
    assert workout_miles(row('cycling', 5.32)) == 5.32
    assert workout_miles(row('cycling', 10), metric=True) == pytest.approx(6.21371)
    # Rowing is reported in meters for everyone.
    assert workout_miles(row('caesar', 1609.344)) == pytest.approx(1)
    assert workout_miles(row('caesar_bootcamp', 1609.344), metric=True) == pytest.approx(1)
    for bad in (None, 0, -3, 'far', True, float('nan')):
        assert workout_miles(row('running', bad)) is None


def test_merge_distance_totals_skips_incomplete_and_distance_less_workouts():
    totals = merge_distance_totals({'cycling': 10}, [
        row('cycling', 5), row('running', 1.25), row('circuit', 0.75),
        row('running', 3, status='IN_PROGRESS'), row('strength', None)])
    assert totals == {'cycling': 15, 'running': 1.25, 'tread_bootcamp': 0.75}


def test_merge_distance_totals_counts_only_from_the_start_date():
    rows = [{**row('cycling', 5, 'new'), 'created_at': 1767268800},    # 2026-01-01 07:00 New York
            {**row('cycling', 7, 'eve'), 'created_at': 1767241800},    # 2025-12-31 23:30 New York
            {**row('running', 2, 'undated')}]
    assert merge_distance_totals({}, rows, since='2026-01-01', tzname='America/New_York') == {'cycling': 5}
    assert merge_distance_totals({}, rows) == {'cycling': 12, 'running': 2}


def test_uses_metric_follows_the_profile_height_unit():
    assert uses_metric({'height_unit': 'metric'})
    assert not uses_metric({'height_unit': 'imperial'})
    assert not uses_metric(None)


def test_progress_counts_only_chosen_disciplines_and_goes_there_and_back():
    journey = {**DEFAULT_JOURNEY, 'miles': 100, 'disciplines': ['Cycling', 'Tread Bootcamp']}
    totals = {'cycling': 130, 'tread_bootcamp': 20, 'running': 999}
    progress = journey_progress(totals, journey)
    assert progress['miles'] == 150
    assert progress['trip'] == 2 and progress['returning']
    assert progress['leg_miles'] == 50 and progress['fraction'] == 0.5
    out_again = journey_progress({'cycling': 230}, journey)
    assert out_again['trip'] == 3 and not out_again['returning']


def test_default_journey_counts_every_discipline_with_distance():
    totals = {'cycling': 100, 'bike_bootcamp': 10, 'tread_bootcamp': 5, 'running_outdoor': 3,
              'rowing': 2, 'walking': 1}
    assert journey_progress(totals, DEFAULT_JOURNEY)['miles'] == 121
    # Listing disciplines still narrows it.
    assert journey_progress(totals, {**DEFAULT_JOURNEY, 'disciplines': ['Cycling', 'Outdoor Run']})['miles'] == 103


def test_every_distance_discipline_name_matches_a_tally_key():
    keys = {'cycling', 'bike_bootcamp', 'running', 'running_outdoor', 'tread_bootcamp',
            'walking', 'walking_outdoor', 'rowing', 'row_bootcamp'}
    assert {normalize_discipline(name) for name in DISTANCE_DISCIPLINES} == keys
    assert merge_distance_totals({}, [row('circuit', 1), row('caesar_bootcamp', 1609.344),
                                      row('outdoor_running', 2)]) == pytest.approx(
        {'tread_bootcamp': 1, 'row_bootcamp': 1, 'running_outdoor': 2})


def test_config_warns_when_a_listed_discipline_has_no_distance(tmp_path, caplog):
    load_config(write_config(tmp_path, {'display': {'journey': {
        **DEFAULT_JOURNEY, 'disciplines': ['Cycling', 'Strength']}}}))
    assert "'Strength' has no distance" in caplog.text and 'Cycling' not in caplog.text.split('distance comes')[0]


def test_config_journey_without_disciplines_counts_everything(tmp_path):
    journey = load_config(write_config(tmp_path, {'display': {'journey': {
        'from': 'A', 'to': 'B', 'miles': 10}}}))['display']['journey']
    assert journey['disciplines'] is None


@pytest.mark.parametrize('journey', [None, {}, {**DEFAULT_JOURNEY, 'miles': 0},
                                     {**DEFAULT_JOURNEY, 'miles': True}])
def test_progress_is_none_for_unusable_routes(journey):
    assert journey_progress({'cycling': 10}, journey) is None


def test_rotation_shows_journey_only_once_there_are_miles():
    display = {'rotation': ['journey'], 'last_workout_duration': 15, 'overview_duration': 5,
               'journey': DEFAULT_JOURNEY}
    snapshot = {'summaries': [], 'totals': {}, 'status': 'ready', 'distance_totals': {'cycling': 440}}
    pages = build_rotation_pages(snapshot, Mock(), display, 'R', 64)
    assert pages[0][0] == 'journey' and pages[0][1]['fraction'] == 0.5
    snapshot['distance_totals'] = {}
    assert build_rotation_pages(snapshot, Mock(), display, 'R', 64) == []
    del snapshot['distance_totals']
    assert build_rotation_pages(snapshot, Mock(), display, 'R', 64) == []


def write_config(tmp_path, data):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(data))
    return str(path)


def test_config_defaults_to_columbus_to_disney_world(tmp_path):
    display = load_config(write_config(tmp_path, {}))['display']
    assert display['journey'] == DEFAULT_JOURNEY
    assert display['journey']['from'] == 'Columbus' and display['journey']['to'] == 'Disney World'


def test_config_accepts_a_custom_route_and_per_rider_override(tmp_path):
    custom = {'from': 'Chicago', 'to': 'Nashville', 'miles': 473, 'disciplines': ['Rowing']}
    config = load_config(write_config(tmp_path, {
        'display': {'journey': custom},
        'users': [{'name': 'Jen', 'journey': {**custom, 'disciplines': ['Running', 'Walking']}}]}))
    assert config['display']['journey'] == {**custom, 'start_date': None}
    assert config['users'][0]['journey']['disciplines'] == ['Running', 'Walking']


def test_config_accepts_a_journey_start_date_for_display_and_riders(tmp_path):
    config = load_config(write_config(tmp_path, {
        'display': {'journey': {**DEFAULT_JOURNEY, 'start_date': ' 2026-01-01 '}},
        'users': [{'name': 'Jen', 'journey': {**DEFAULT_JOURNEY, 'start_date': '2026-06-15'}}]}))
    assert config['display']['journey']['start_date'] == '2026-01-01'
    assert config['users'][0]['journey']['start_date'] == '2026-06-15'


@pytest.mark.parametrize('journey, message', [
    ({'from': 'A', 'to': 'B', 'disciplines': ['Cycling']}, 'needs from, to and miles'),
    ({'from': ' ', 'to': 'B', 'miles': 10, 'disciplines': ['Cycling']}, 'journey.from'),
    ({'from': 'A', 'to': 'B', 'miles': -1, 'disciplines': ['Cycling']}, 'journey.miles'),
    ({'from': 'A', 'to': 'B', 'miles': 10, 'disciplines': []}, 'journey.disciplines'),
    ({'from': 'A', 'to': 'B', 'miles': 10, 'disciplines': [5]}, 'journey.disciplines'),
    ({**DEFAULT_JOURNEY, 'start_date': '2026-13-01'}, 'journey.start_date'),
    ({**DEFAULT_JOURNEY, 'start_date': 'last spring'}, 'journey.start_date'),
    ({**DEFAULT_JOURNEY, 'start_date': 20260101}, 'journey.start_date'),
])
def test_config_rejects_bad_routes(tmp_path, journey, message):
    with pytest.raises(ValueError, match=message):
        load_config(write_config(tmp_path, {'display': {'journey': journey}}))


def test_dashboard_backfills_distance_once_then_reuses_the_instructor_pages(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    history = [row('cycling', 5, 'w2'), row('caesar', 1609.344, 'w1')]
    client.get_all_workouts.return_value = history
    dashboard.refresh()
    # First run: both tallies start empty, so one full-history fetch serves both.
    assert client.get_all_workouts.call_count == 1
    snap = dashboard.snapshot()
    assert snap['distance_totals'] == {'cycling': 5, 'rowing': pytest.approx(1)}
    assert snap['distance_tally_cursor'] == 'w2'
    client.get_all_workouts.return_value = [row('cycling', 2, 'w3')]
    dashboard.refresh()
    assert client.get_all_workouts.call_count == 2  # still one call per refresh
    assert dashboard.snapshot()['distance_totals']['cycling'] == 7


def test_dashboard_backfills_distance_for_caches_from_before_the_journey(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    dashboard._publish(instructor_tally_cursor='w2', instructor_counts={'Cody': 2},
                       tally_version=TALLY_VERSION)
    client.get_all_workouts.side_effect = [
        [],                                              # instructor: nothing new
        [row('cycling', 5, 'w2'), row('running', 1, 'w1')],  # distance: full backfill
    ]
    dashboard.refresh()
    calls = client.get_all_workouts.call_args_list
    assert calls[0].kwargs['stop_at_id'] == 'w2' and calls[1].kwargs['stop_at_id'] is None
    snap = dashboard.snapshot()
    assert snap['distance_totals'] == {'cycling': 5, 'running': 1}
    assert snap['distance_tally_cursor'] == 'w2' == snap['instructor_tally_cursor']


def test_dashboard_recounts_distance_once_when_the_start_date_changes(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    history = [{**row('cycling', 5, 'w2'), 'created_at': 1767268800},   # 2026-01-01
               {**row('cycling', 7, 'w1'), 'created_at': 1735732800}]   # 2025-01-01
    client.get_all_workouts.return_value = history
    dashboard.refresh()
    assert dashboard.snapshot()['distance_totals'] == {'cycling': 12}
    assert dashboard.snapshot()['distance_tally_since'] is None

    dashboard.config['journey'] = {**DEFAULT_JOURNEY, 'start_date': '2025-06-01'}
    client.get_all_workouts.reset_mock()
    client.get_all_workouts.side_effect = [[], history]  # instructor: nothing new; distance: full recount
    dashboard.refresh()
    calls = client.get_all_workouts.call_args_list
    assert calls[0].kwargs['stop_at_id'] == 'w2' and calls[1].kwargs['stop_at_id'] is None
    snap = dashboard.snapshot()
    assert snap['distance_totals'] == {'cycling': 5} and snap['distance_tally_since'] == '2025-06-01'

    # Same date next time: back to sharing the instructor pages, no recount.
    client.get_all_workouts.reset_mock()
    client.get_all_workouts.side_effect = None
    client.get_all_workouts.return_value = [{**row('cycling', 2, 'w3'), 'created_at': 1767355200}]
    dashboard.refresh()
    assert client.get_all_workouts.call_count == 1
    assert dashboard.snapshot()['distance_totals'] == {'cycling': 7}


def test_distance_tally_survives_the_cache_and_bad_entries_rebuild(tmp_path):
    path = tmp_path / 'cache.json'
    base = {'me': None, 'totals': {}, 'summaries': [], 'last_updated': 1.0}
    save_snapshot(path, {**base, 'distance_totals': {'cycling': 5.5}, 'distance_tally_cursor': 'w1'})
    restored = load_snapshot(path)
    assert restored['distance_totals'] == {'cycling': 5.5} and restored['distance_tally_cursor'] == 'w1'
    save_snapshot(path, {**base, 'distance_totals': {'cycling': 5.5}, 'distance_tally_cursor': 'w1',
                         'distance_tally_since': '2026-01-01'})
    assert load_snapshot(path)['distance_tally_since'] == '2026-01-01'
    save_snapshot(path, {**base, 'distance_totals': {'cycling': 5.5}, 'distance_tally_cursor': 'w1',
                         'distance_tally_since': 7})
    assert 'distance_totals' not in load_snapshot(path)
    save_snapshot(path, {**base, 'distance_totals': {'cycling': 'far'}, 'distance_tally_cursor': 'w1'})
    restored = load_snapshot(path)
    assert 'distance_totals' not in restored and 'distance_tally_cursor' not in restored


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('miles, journey', [
    (252, DEFAULT_JOURNEY), (3470, DEFAULT_JOURNEY), (1300, DEFAULT_JOURNEY),
    (500, {**DEFAULT_JOURNEY, 'from': 'San Francisco', 'to': 'Walt Disney World Resort'}),
    (8.8, {**DEFAULT_JOURNEY, 'miles': 26.2}), (999.9, DEFAULT_JOURNEY), (1879.9, DEFAULT_JOURNEY)])
def test_journey_screen_fits_both_boards(height, miles, journey):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    assert JourneyScreen().render(matrix, journey_progress({'cycling': miles}, journey))
    pixels = matrix.image.load()
    assert all(pixels[x, y] == (0, 0, 0) for x in (0, 63) for y in range(height))
    found = {c for _, c in matrix.image.getcolors(64 * 64)}
    assert set(CASTLE_COLORS.values()) <= found


def test_journey_screen_renders_nothing_without_progress():
    initialize_fonts(64)
    assert not JourneyScreen().render(ImageMatrix(height=64), None)


def test_journey_text_shows_tenths_of_a_mile():
    progress = journey_progress({'cycling': 8.84}, {**DEFAULT_JOURNEY, 'miles': 26.2})
    assert journey_text(progress) == ('8.8', '17.4 TO GO')


def test_journey_text_keeps_whole_miles_from_1000_up():
    # "1,300.5" would push the number out of the big font.
    progress = journey_progress({'cycling': 1300.46}, {**DEFAULT_JOURNEY, 'miles': 2000})
    assert journey_text(progress) == ('1,300', '699.5 TO GO')
    assert journey_text(journey_progress({'cycling': 999.96}, DEFAULT_JOURNEY))[0] == '1,000'


def test_journey_status_drops_the_decimal_when_the_line_is_full():
    progress = journey_progress({'cycling': 880 + 0.1}, DEFAULT_JOURNEY)  # Heading home.
    assert journey_text(progress) == ('880.1', '879.9 TO HOME')
    assert journey_text(progress, fits=lambda text: len(text) <= 12) == ('880.1', '880 TO HOME')


@pytest.mark.parametrize('height', [32, 64])
def test_journey_screen_status_never_truncates(height):
    initialize_fonts(height)
    small = loaded_fonts.get('stats') or loaded_fonts.get('info')
    progress = journey_progress({'cycling': 880 + 0.1}, DEFAULT_JOURNEY)
    _, status = journey_text(progress, fits=lambda text: get_text_width(small, text) <= 64 - 14)
    assert get_text_width(small, status) <= 64 - 14
    assert status.endswith('TO HOME')
