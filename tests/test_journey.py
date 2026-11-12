"""Distance journey: tally, route progress, config, dashboard backfill, screen."""
import json
from unittest.mock import Mock

import pytest

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui import journey_screen
from display.ui.journey_screen import (DONE_COLOR, GROUP_COLORS, TIP_COLOR, JourneyScreen, counted_miles,
                                       group_cents, group_figure, journey_steps, journey_text,
                                       percent, tip_brightness, trip_text)
from peloton.config import load_config
from peloton.journey import (DEFAULT_JOURNEY, DISTANCE_DISCIPLINES, journey_progress,
                             merge_distance_totals, mile_group, uses_metric, workout_miles)
from peloton.selection import normalize_discipline
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix


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


def test_progress_splits_the_miles_into_bike_walk_run_and_row():
    totals = {'cycling': 100, 'bike_bootcamp': 10, 'tread_bootcamp': 5, 'running_outdoor': 3,
              'walking': 1, 'hiking': 2, 'rowing': 20, 'row_bootcamp': 4}
    progress = journey_progress(totals, DEFAULT_JOURNEY)
    assert progress['groups'] == [{'key': 'bike', 'label': 'BIKE', 'miles': 110},
                                  {'key': 'row', 'label': 'ROW', 'miles': 24},
                                  {'key': 'walk_run', 'label': 'WALK/RUN', 'miles': 11}]
    assert sum(g['miles'] for g in progress['groups']) == progress['miles'], 'every mile is in a row'


def test_progress_groups_follow_the_chosen_disciplines_and_skip_empty_ones():
    totals = {'cycling': 100, 'running': 30, 'rowing': 0, 'walking': True}
    assert journey_progress(totals, DEFAULT_JOURNEY)['groups'] == [
        {'key': 'bike', 'label': 'BIKE', 'miles': 100}, {'key': 'walk_run', 'label': 'WALK/RUN', 'miles': 30}]
    only_running = journey_progress(totals, {**DEFAULT_JOURNEY, 'disciplines': ['Running']})
    assert [g['key'] for g in only_running['groups']] == ['walk_run']
    assert journey_progress({}, DEFAULT_JOURNEY)['groups'] == []


@pytest.mark.parametrize('key, group', [
    ('cycling', 'bike'), ('bike_bootcamp', 'bike'), ('rowing', 'row'), ('row_bootcamp', 'row'),
    ('running', 'walk_run'), ('walking_outdoor', 'walk_run'), ('tread_bootcamp', 'walk_run'),
    ('hiking', 'walk_run'), ('something_new', 'walk_run')])
def test_every_discipline_lands_in_a_group(key, group):
    assert mile_group(key)[0] == group


def test_32_rows_share_the_journey_time_between_its_two_steps():
    display = {'rotation': ['journey'], 'last_workout_duration': 15, 'overview_duration': 5,
               'journey': DEFAULT_JOURNEY}
    snapshot = {'summaries': [], 'totals': {}, 'status': 'ready',
                'distance_totals': {'cycling': 400, 'running': 40}}
    (_, state, duration), = build_rotation_pages(snapshot, Mock(), display, 'R', 32)
    assert duration == 8 and state['step_seconds'] == 4, 'raised to 4 s a step'
    display['screen_durations'] = {'journey': 12}
    (_, state, duration), = build_rotation_pages(snapshot, Mock(), display, 'R', 32)
    assert duration == 12 and state['step_seconds'] == 6
    (_, state, duration), = build_rotation_pages(snapshot, Mock(), display, 'R', 64)
    assert duration == 12 and 'step_seconds' not in state, '64 rows: one page'
    snapshot['distance_totals'] = {'cycling': 400}
    display['screen_durations'] = {}
    (_, state, duration), = build_rotation_pages(snapshot, Mock(), display, 'R', 32)
    assert duration == 5 and 'step_seconds' not in state, 'one kind of miles: no split to show'


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


EVERY_GROUP = {'cycling': 0.6, 'running': 0.25, 'rowing': 0.15}


def progress_for(miles, journey=DEFAULT_JOURNEY, split=None):
    return journey_progress({k: miles * v for k, v in (split or {'cycling': 1}).items()}, journey)


# A settled frame: the opening animation done and the bar's tip at full brightness (a whole number
# of pulses after the fill). A 32-row second step settles at STEP + SETTLED.
SETTLED = journey_screen.FILL_SECONDS + journey_screen.PULSE_SECONDS
STEP = 4


def render(height, progress, at=SETTLED):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    screen = JourneyScreen()
    screen.on_enter(matrix, progress)
    screen.update(at)
    assert screen.render(matrix, progress)
    return matrix.image


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('split', [None, EVERY_GROUP])
@pytest.mark.parametrize('miles, journey', [
    (252, DEFAULT_JOURNEY), (3470, DEFAULT_JOURNEY), (1300, DEFAULT_JOURNEY), (12345.6, DEFAULT_JOURNEY),
    (500, {**DEFAULT_JOURNEY, 'from': 'San Francisco', 'to': 'Walt Disney World Resort'}),
    (8.8, {**DEFAULT_JOURNEY, 'miles': 26.2}), (999.9, DEFAULT_JOURNEY), (1879.9, DEFAULT_JOURNEY)])
def test_journey_screen_fits_both_boards(height, split, miles, journey):
    progress = progress_for(miles, journey, split)
    if journey_steps(progress, height) == 2:
        progress['step_seconds'] = STEP
    for at in (SETTLED, STEP + SETTLED):  # both 32-row steps
        image = render(height, progress, at)
        pixels = image.load()
        assert all(pixels[x, y] == (0, 0, 0) for x in (0, 1, 63) for y in range(height))


@pytest.mark.parametrize('height', [32, 64])
def test_journey_bar_fills_with_this_legs_progress(height):
    # 440 of 880: half the bar; the bar's row is clear of everything else.
    image = render(height, progress_for(440))
    bar_y = 37 if height == 64 else 28
    lit = [x for x in range(64) if image.getpixel((x, bar_y)) == DONE_COLOR]
    assert lit[0] == 2 and len(lit) == 29 and image.getpixel((31, bar_y)) == TIP_COLOR, 'the tip ends it' 
    # Heading home, the trip number takes the bar's right end.
    image = render(height, progress_for(880 + 220))
    row = [image.getpixel((x, bar_y)) for x in range(64)]
    assert row.count(DONE_COLOR) < 20 and row[61] == (0, 0, 0)


def test_64_rows_list_each_group_in_its_colour_most_miles_first():
    progress = progress_for(500, split=EVERY_GROUP)
    assert [g['label'] for g in progress['groups']] == ['BIKE', 'WALK/RUN', 'ROW']
    image = render(64, progress)
    # One colour square a row, under the bar, in group order.
    assert [image.getpixel((3, 47 + row * 7 - 3)) for row in range(3)] == [
        GROUP_COLORS['bike'], GROUP_COLORS['walk_run'], GROUP_COLORS['row']]


def test_32_rows_show_the_trip_then_the_miles_by_type():
    progress = progress_for(500, split=EVERY_GROUP)
    progress['step_seconds'] = STEP
    trip, split, later = (render(32, progress, at) for at in (SETTLED, STEP + SETTLED, 30))
    assert trip != split and later == split, 'the split holds to the end, not the trip again'
    found = {c for _, c in split.getcolors(64 * 32)}
    assert set(GROUP_COLORS.values()) <= found and DONE_COLOR not in found
    # Without step_seconds (a page not built by build_rotation_pages) it stays on the trip.
    del progress['step_seconds']
    assert render(32, progress, SETTLED + 14 * journey_screen.PULSE_SECONDS) == trip


def test_32_rows_with_one_kind_of_miles_keep_the_trip_up():
    progress = progress_for(500)
    assert journey_steps(progress, 32) == 1 and journey_steps(progress_for(500, split=EVERY_GROUP), 64) == 1
    progress['step_seconds'] = STEP
    assert render(32, progress) == render(32, progress, SETTLED + 14 * journey_screen.PULSE_SECONDS)


def test_switching_steps_clears_a_board_without_frame_canvases():
    progress = {**progress_for(500, split=EVERY_GROUP), 'step_seconds': STEP}
    initialize_fonts(32)
    matrix, screen = ImageMatrix(height=32), JourneyScreen()
    screen.on_enter(matrix, progress)
    screen.render(matrix, progress)
    screen.update(5)
    screen.render(matrix, progress)
    assert matrix.image == render(32, progress, 5), "no pixels left over from the trip step"


def test_the_opening_animation_is_done_by_intro_seconds():
    js = journey_screen
    assert js.INTRO_SECONDS >= max(js.FILL_SECONDS, js.SPLIT_GROW_SECONDS,
                                   js.ROW_START_SECONDS + 2 * js.ROW_GAP_SECONDS + js.ROW_SLIDE_SECONDS)
    assert js.INTRO_SECONDS <= 1.0, 'a 32-row step has 4 s: at least 3 of them still'
    progress = {**progress_for(1190, split=EVERY_GROUP), 'step_seconds': STEP}
    for height, start in ((64, 0), (32, 0), (32, STEP)):
        # Settled at INTRO_SECONDS; after that only the tip's pulse changes (same phase, same frame).
        assert render(height, progress, start + js.INTRO_SECONDS) == render(height, progress, start + SETTLED)


@pytest.mark.parametrize('height', [32, 64])
def test_the_bar_fills_from_empty(height):
    progress = progress_for(440)
    bar_y = 37 if height == 64 else 28
    orange = [sum(render(height, progress, at).getpixel((x, bar_y)) == DONE_COLOR for x in range(64))
              for at in (0, 0.2, 0.5, SETTLED)]
    assert orange[0] == 0 and orange == sorted(orange) and orange[-1] == 29
    assert render(height, progress, 0).getpixel((2, bar_y)) == TIP_COLOR, 'the tip starts at the left end'


def test_the_miles_count_up_across_this_leg():
    progress = progress_for(1190)  # trip 2: the leg began at 880
    assert counted_miles(progress, 0) == '880.0'
    assert counted_miles(progress, 0.5) not in ('880.0', '1,190.0')
    assert counted_miles(progress, journey_screen.FILL_SECONDS) == '1,190.0'
    assert counted_miles(progress_for(48.3), 0) == '0.0'
    # The heading holds still while the figures count.
    first, last = render(64, progress, 0.5), render(64, progress)
    assert first.crop((0, 0, 64, 8)) == last.crop((0, 0, 64, 8))


def test_the_miles_to_go_and_the_percent_count_with_the_bar():
    progress = progress_for(1190)  # trip 2: 310 of 880 home
    assert trip_text(progress, 0) == ('880.0', '880.0 TO HOME', '0%')
    middle = trip_text(progress, 0.5)
    assert 570 < float(middle[1].split()[0]) < 880 and 0 < int(middle[2][:-1]) < 35
    assert trip_text(progress, journey_screen.FILL_SECONDS) == ('1,190.0', '570.0 TO HOME', '35%')
    # A status that drops its decimal at the end drops it from the start, so the line never changes format.
    whole = lambda text: '.' not in text
    assert trip_text(progress, 0, whole)[1] == '880 TO HOME'
    assert trip_text(progress, 0.5, whole)[1].split()[0].isdigit()
    assert trip_text(progress, 9, whole)[1] == '570 TO HOME' 


def test_the_tip_pulses_after_the_fill():
    js = journey_screen
    assert tip_brightness(0) == tip_brightness(js.FILL_SECONDS) == 1
    assert tip_brightness(js.FILL_SECONDS + js.PULSE_SECONDS / 2) == pytest.approx(js.PULSE_LOW)
    dim = render(64, progress_for(440), js.FILL_SECONDS + js.PULSE_SECONDS / 2).getpixel((31, 37))
    assert dim == tuple(round(c * js.PULSE_LOW) for c in TIP_COLOR)


def test_64_rows_slide_the_groups_in_one_after_another():
    js = journey_screen
    progress = progress_for(500, split=EVERY_GROUP)
    squares = lambda at: [render(64, progress, at).getpixel((3, 43 + row * 7)) for row in range(3)]
    black = (0, 0, 0)
    assert squares(js.ROW_START_SECONDS) == [black] * 3, 'nothing under the bar at first'
    assert squares(js.ROW_START_SECONDS + js.ROW_SLIDE_SECONDS) == [GROUP_COLORS['bike'], black, black]
    assert squares(js.INTRO_SECONDS) == [GROUP_COLORS['bike'], GROUP_COLORS['walk_run'], GROUP_COLORS['row']]


def test_32_rows_grow_the_split_a_colour_at_a_time():
    progress = {**progress_for(500, split=EVERY_GROUP), 'step_seconds': STEP}
    def at(seconds):
        image = render(32, progress, STEP + seconds)
        return ([image.getpixel((x, 8)) for x in (2, 61)],
                [image.getpixel((x, y)) != (0, 0, 0) for y in (14, 21, 28) for x in range(2, 30)])
    bar, _ = at(0)
    assert bar == [(0, 0, 0)] * 2, 'the split starts empty'
    bar, _ = at(0.15)
    assert bar[0] == GROUP_COLORS['bike'] and bar[1] == (0, 0, 0)
    bar, _ = at(journey_screen.SPLIT_GROW_SECONDS)
    assert bar == [GROUP_COLORS['bike'], GROUP_COLORS['row']]


def test_a_row_waits_for_its_colour_to_land():
    progress = {**progress_for(500, split=EVERY_GROUP), 'step_seconds': STEP}
    def rows_lit(seconds):
        image = render(32, progress, STEP + seconds)
        return [any(image.getpixel((x, y)) != (0, 0, 0) for x in range(2, 40) for y in range(top, top + 6))
                for top in (12, 19, 26)]
    assert rows_lit(0) == [False] * 3
    assert rows_lit(journey_screen.SPLIT_GROW_SECONDS) == [True] * 3
    partial = rows_lit(0.3)  # BIKE's colour has landed, ROW's hasn't
    assert partial[0] and not partial[2]


def test_percent_never_says_100_short_of_the_destination():
    assert percent(progress_for(879.9)) == '99%'
    assert percent(progress_for(0.5)) == '0%'
    assert percent(progress_for(440)) == '50%'


def test_journey_screen_renders_nothing_without_progress():
    initialize_fonts(64)
    assert not JourneyScreen().render(ImageMatrix(height=64), None)


def test_the_big_total_shows_one_decimal():
    # Only the groups' rows show hundredths; the big figure keeps one decimal on both boards.
    progress = journey_progress({'cycling': 8.846}, {**DEFAULT_JOURNEY, 'miles': 26.2})
    assert journey_text(progress) == ('8.8', '17.4 TO GO')
    assert journey_text(journey_progress({'cycling': 1300.466}, {**DEFAULT_JOURNEY, 'miles': 2000}))[0] == '1,300.5'


def test_journey_text_drops_decimals_only_as_far_as_the_room_needs():
    progress = journey_progress({'cycling': 1300.466}, {**DEFAULT_JOURNEY, 'miles': 2000})
    assert journey_text(progress, miles_fit=lambda text: len(text) <= 7)[0] == '1,300.5'
    assert journey_text(progress, miles_fit=lambda text: len(text) <= 5)[0] == '1,300'
    assert journey_text(journey_progress({'cycling': 999.996}, DEFAULT_JOURNEY))[0] == '1,000.0'
    # The count-up keeps the final figure's decimals from the first frame.
    assert counted_miles(progress, 0, miles_fit=lambda text: len(text) <= 5) == '0'
    assert counted_miles(progress, journey_screen.FILL_SECONDS, miles_fit=lambda text: len(text) <= 5) == '1,300'


def test_group_figures_add_up_to_the_total():
    # Rounded alone 22.636 + 3.539 is 22.64 + 3.54 = 26.18, but 0.333 x 3 is 0.33 x 3 against a total
    # of 1.00: the rows take the missing hundredths (largest remainder) so they sum to the big figure.
    progress = journey_progress({'cycling': 22.636, 'running': 3.539}, DEFAULT_JOURNEY)
    cents = group_cents(progress['groups'], progress['miles'])
    assert sum(cents) == round(progress['miles'] * 100) == 2618 and cents == [2264, 354]
    for a, b, c in ((0.333, 0.333, 0.333), (1.005, 2.005, 3.005), (5.5, 0.004, 0.004)):
        groups = [{'miles': v} for v in (a, b, c)]
        assert sum(group_cents(groups, a + b + c)) == round((a + b + c) * 100)
    assert group_cents([{'miles': 1.236}], 5) == [124], 'rows that are not part of that total: plain rounding'
    assert group_figure(2264) == '22.64' and group_figure(123456) == '1,234.56'
    assert group_figure(123456, lambda text: '.' not in text) == '1,235'
    assert group_figure(123456, lambda text: len(text) <= 7) == '1,234.6'


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('totals', [
    {'cycling': 12.346}, {'cycling': 123.456, 'running': 99.99, 'rowing': 9.994},
    {'cycling': 1234.5678, 'running': 987.654, 'rowing': 111.111},
    {'cycling': 4444.4444, 'running': 4444.4444, 'rowing': 4444.4444},
    {'cycling': 9999.995, 'running': 1.005, 'rowing': 12345.678}])
def test_decimals_fit_inside_a_one_pixel_margin_and_never_touch_their_labels(height, totals):
    progress = journey_progress(totals, {**DEFAULT_JOURNEY, 'miles': 20000})
    progress['step_seconds'] = STEP
    for at in (SETTLED, STEP + SETTLED):
        if at != SETTLED and journey_steps(progress, height) != 2:
            continue
        image = render(height, progress, at)
        lit = [x for x in range(64) for y in range(height) if image.getpixel((x, y)) != (0, 0, 0)]
        assert min(lit) >= 1 and max(lit) <= 62, 'a 1 px margin at each edge'
        # Each legend row keeps a blank column between its label and its figure.
        if height == 64 and at == SETTLED or height == 32 and at != SETTLED:
            top = 43 if height == 64 else 12
            for row in range(len(progress['groups'])):
                rows = range(top + row * 7, top + row * 7 + 6)
                busy = [x for x in range(8, 62) if any(image.getpixel((x, y)) != (0, 0, 0) for y in rows)]
                assert any(b - a > 1 for a, b in zip(busy, busy[1:])), 'label and figure are apart'


def test_the_big_figure_shows_one_decimal_where_it_fits():
    for height, totals, text in ((64, {'cycling': 26.175, 'running': 0.0004}, '26.2'),
                                 (64, {'cycling': 999.994}, '1,000.0'),
                                 (64, {'cycling': 1234.5678}, '1,234.6'),
                                 (64, {'cycling': 12345.678}, '12,346'),
                                 (32, {'cycling': 1234.5678}, '1,234.6')):
        initialize_fonts(height)
        small = loaded_fonts.get('stats')
        fonts = [loaded_fonts.get('big'), loaded_fonts.get('bold' if height == 64 else 'countdown')]
        unit = get_text_width(small, 'MI')
        fits = lambda t: any(2 + get_text_width(f, t) + 2 + unit <= 62 for f in fonts if f)
        assert journey_text(journey_progress(totals, DEFAULT_JOURNEY), miles_fit=fits)[0] == text


def test_journey_status_drops_the_decimal_when_the_line_is_full():
    progress = journey_progress({'cycling': 880 + 0.1}, DEFAULT_JOURNEY)  # Heading home.
    assert journey_text(progress) == ('880.1', '879.9 TO HOME')
    assert journey_text(progress, fits=lambda text: len(text) <= 12) == ('880.1', '880 TO HOME')


@pytest.mark.parametrize('height', [32, 64])
def test_journey_screen_status_never_truncates(height):
    # The status line shares its row with the percent: it drops the decimal rather than lose TO HOME.
    initialize_fonts(height)
    small = loaded_fonts.get('stats') or loaded_fonts.get('info')
    progress = journey_progress({'cycling': 880 + 879.4}, DEFAULT_JOURNEY)
    room = 64 - 4 - get_text_width(small, percent(progress)) - 3
    _, status = journey_text(progress, fits=lambda text: get_text_width(small, text) <= room)
    assert get_text_width(small, status) <= room
    assert status.endswith('TO HOME')


def test_group_colours_avoid_christmas_and_the_bar():
    """No red beside green (the orange bar makes it Christmas), all distinct from each other
    and from the bar, each bright enough to read as small text."""
    import colorsys
    colours = list(GROUP_COLORS.values())
    assert len(set(colours)) == len(colours) and DONE_COLOR not in colours
    hues = []
    for r, g, b in colours:
        hue, _, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        assert value >= 0.8
        hues.append(hue * 360)
    red = any(h < 20 or h > 345 for h in hues)
    green = any(80 < h < 160 for h in hues)
    assert not (red and green)
    bar_hue = colorsys.rgb_to_hsv(*(c / 255 for c in DONE_COLOR))[0] * 360
    assert all(abs(h - bar_hue) > 40 for h in hues)
    assert all(abs(a - b) > 30 for i, a in enumerate(hues) for b in hues[i + 1:])
