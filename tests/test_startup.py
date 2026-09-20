from unittest.mock import Mock, patch
import pytest
from peloton.config import load_config
from peloton_led import (build_rotation_pages, configured_profiles, main,
                         run_display_loop, run_multi_user_loop, scheduled_brightness)
from peloton.dashboard import Dashboard
from display.ui.manager import ScreenManager
from display.ui.last_workout_screen import LastWorkoutScreen
from display.ui.username import UsernameScreen
from display.ui.discipline_page import DisciplinePageScreen
from display.ui.lifetime_overview import LifetimeOverviewScreen
from display.ui.pr_star import PrStarScreen
from display.ui.status_screen import StatusScreen
from display.display import initialize_fonts
from scripts.render_demo import ImageMatrix


def test_demo_rotation_has_no_network_and_renders_all_screens(tmp_path):
    config = load_config(tmp_path / 'missing', allow_missing=True)['display']
    config.update(duration=0, overview_duration=0, last_workout_duration=0)
    matrix = ImageMatrix()
    initialize_fonts(64)
    dashboard = Dashboard(tmp_path / 'missing', config, demo=True, demo_login_needed=True)
    manager = ScreenManager(matrix, login_required=lambda: dashboard.login_required)
    for name, screen in [('last_workout', LastWorkoutScreen()), ('username', UsernameScreen('info')),
                         ('discipline', DisciplinePageScreen()), ('lifetime', LifetimeOverviewScreen()),
                         ('pr', PrStarScreen()), ('status', StatusScreen())]:
        manager.register(name, screen)
    with patch('requests.Session.request', side_effect=AssertionError('Demo made a network request')):
        run_display_loop(manager, dashboard, config, cycles=1)
    assert matrix.image.getbbox() is not None
    assert any(matrix.image.getpixel((x, y)) == (255, 160, 0) for x in range(57, 64) for y in range(55, 64))


def test_invalid_config_fails_before_matrix_initialization(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text('{bad')
    with patch('sys.argv', ['peloton_led.py', '--config', str(path)]):
        with pytest.raises(SystemExit, match='Could not read config'):
            main()


def test_cli_duration_respects_config_by_default():
    from utils.utils import args
    assert args([]).display_duration is None
    assert args(['--display-duration', '0']).display_duration == 0


def test_empty_token_shows_login_without_request(tmp_path):
    token = tmp_path / 'empty'
    token.write_text(' ')
    dashboard = Dashboard(token, {})
    with patch('requests.Session.request', side_effect=AssertionError('Empty token made a request')):
        dashboard.refresh()
    assert dashboard.login_required


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('discipline', [
    'Cycling', 'Bike Bootcamp', 'Running', 'Walking', 'Outdoor Run', 'Outdoor Walk',
    'Tread Bootcamp', 'Hiking', 'Rowing', 'Row Bootcamp', 'Strength', 'Cardio',
    'Yoga', 'Meditation', 'Stretching', 'Pilates', 'Barre', 'Boxing',
    'Dance Cardio', 'Mobility', 'Unknown Future Workout',
])
def test_every_discipline_renders_on_supported_panels(height, discipline):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    summary = {'discipline': discipline, 'title': '20 min Representative Workout',
               'duration_min': 20, 'calories': 200, 'hr_avg': 130, 'hr_max': 165,
               'strive_score': 22, 'distance': 3.1, 'distance_unit': 'mi',
               'avg_pace': 10, 'avg_pace_unit': 'min/mi', 'avg_output_w': 100,
               'avg_stroke_rate': 24, 'row_split_sec_per_500m': 130,
               'total_output_kj': 200, 'avg_speed': 12, 'avg_speed_unit': 'mph',
               'avg_cadence': 80, 'avg_resistance': 40}
    assert LastWorkoutScreen().render(matrix, summary)
    assert matrix.image.getbbox() is not None


@pytest.mark.parametrize('height', [32, 64])
def test_workout_duration_is_blue_above_white_title_with_gap(height):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    summary = {'discipline': 'Strength', 'title': 'Full Body Strength',
               'duration_min': 20, 'calories': None, 'hr_avg': None}
    assert LastWorkoutScreen().render(matrix, summary)
    pixels = matrix.image.load()
    blue_rows = {y for y in range(height) for x in range(64)
                 if pixels[x, y] == (0, 120, 255)}
    white_rows = {y for y in range(height) for x in range(64)
                  if pixels[x, y] == (255, 255, 255)}
    assert blue_rows and white_rows
    assert max(blue_rows) + 1 < min(white_rows)


def test_bike_bootcamp_uses_larger_two_line_header_without_overlap():
    matrix = ImageMatrix(height=64)
    initialize_fonts(64)
    summary = {'discipline': 'Bike Bootcamp', 'title': '30 min Bootcamp 50/50',
               'duration_min': 30, 'calories': 218, 'hr_avg': 126}
    assert LastWorkoutScreen().render(matrix, summary)
    pixels = matrix.image.load()
    disc_color = (220, 50, 20)
    disc_rows = sorted({y for y in range(64) for x in range(64) if pixels[x, y] == disc_color})
    blue_rows = {y for y in range(64) for x in range(64) if pixels[x, y] == (0, 120, 255)}
    assert disc_rows, 'discipline text did not render'
    # The 5x8 title font renders BIKE and BOOTCAMP as two distinct bands.
    assert disc_rows[-1] - disc_rows[0] >= 8
    assert blue_rows and max(disc_rows) < min(blue_rows)


def test_long_discipline_name_with_max_stat_rows_does_not_collide():
    # Bike Bootcamp's two-line header combined with cycling's 3 stat rows
    # must retain clear separation throughout the screen.
    matrix = ImageMatrix(height=64)
    initialize_fonts(64)
    summary = {'discipline': 'Bike Bootcamp', 'title': '30 min Bootcamp 50/50',
               'duration_min': 30, 'calories': 218, 'hr_avg': 126,
               'total_output_kj': 78, 'strive_score': 19, 'avg_cadence': 76,
               'avg_resistance': 38, 'avg_speed': 15.2, 'avg_speed_unit': 'mph',
               'distance': 3.5, 'distance_unit': 'mi'}
    assert LastWorkoutScreen().render(matrix, summary)
    pixels = matrix.image.load()
    white_rows_with_content = sorted({y for y in range(64) for x in range(64)
                                      if pixels[x, y] == (255, 255, 255)})
    # Consecutive rows of white text should never be adjacent to the point of
    # merging into unreadable noise: there must be at least one gap row
    # between the title line and the first stat row.
    gaps = [b - a for a, b in zip(white_rows_with_content, white_rows_with_content[1:])]
    assert any(gap > 1 for gap in gaps), 'title and stats rows have no separating gap'


def test_rotation_places_pr_after_its_workout():
    from peloton_led import run_display_loop

    dashboard = Mock(login_required=False)
    dashboard.should_celebrate_pr.side_effect = lambda summary: summary.get('is_pr', False)
    dashboard.snapshot.return_value = {
        'me': {'username': 'Rider'},
        'summaries': [
            {'workout_id': 'newest', 'discipline': 'Yoga', 'is_pr': True},
            {'workout_id': 'earlier', 'discipline': 'Strength', 'is_pr': False},
        ],
        'totals': {}, 'status': 'ready',
    }
    manager = Mock()
    display = {'duration': 0, 'overview_duration': 0, 'last_workout_duration': 0,
               'color': 'white'}
    run_display_loop(manager, dashboard, display, cycles=1)
    assert [call.args[0] for call in manager.show.call_args_list] == [
        'last_workout', 'pr', 'last_workout', 'username',
    ]
    dashboard.acknowledge_pr.assert_called_once_with('newest')


def test_multi_user_loop_runs_complete_rotations_in_configured_order():
    first, second = Mock(), Mock()
    profiles = [
        {'name': 'First', 'username': None, 'dashboard': first},
        {'name': 'Second', 'username': 'Second Rider', 'dashboard': second},
    ]
    active = {'dashboard': first}
    with patch('peloton_led.run_display_loop') as run:
        run_multi_user_loop(Mock(), profiles, {}, active, cycles=1)
    assert [(call.args[1], call.args[3], call.kwargs['cycles'])
            for call in run.call_args_list] == [
                (first, None, 1), (second, 'Second Rider', 1)]
    assert active['dashboard'] is second


def test_configured_profiles_isolates_relative_tokens_and_caches(tmp_path):
    options = Mock(config=str(tmp_path / 'household.json'), cookies='legacy.txt',
                   username=None, demo=False, demo_login_needed=False)
    config = {'display': {}, 'users': [
        {'name': 'One', 'token_path': 'one.token', 'cache_path': 'one-cache.json'},
        {'name': 'Two', 'token_path': 'two.token'},
    ]}
    with patch('peloton_led.Dashboard') as dashboard:
        profiles = configured_profiles(config, options)
    assert [profile['name'] for profile in profiles] == ['One', 'Two']
    assert dashboard.call_args_list[0].args[0] == tmp_path / 'one.token'
    assert dashboard.call_args_list[0].args[1]['cache_path'] == str(tmp_path / 'one-cache.json')
    assert dashboard.call_args_list[1].args[1]['cache_path'] == str(tmp_path / 'two-dashboard-cache.json')


def test_configured_profiles_derives_token_path_from_name(tmp_path):
    options = Mock(config=str(tmp_path / 'household.json'), cookies='legacy.txt',
                   username=None, demo=False, demo_login_needed=False)
    config = {'display': {}, 'users': [{'name': 'Joel'}, {'name': 'Jen'}]}
    with patch('peloton_led.Dashboard') as dashboard:
        configured_profiles(config, options)
    assert dashboard.call_args_list[0].args[0] == tmp_path / 'cookies-joel.txt'
    assert dashboard.call_args_list[0].args[1]['cache_path'] == str(tmp_path / 'cookies-joel-dashboard-cache.json')
    assert dashboard.call_args_list[1].args[0] == tmp_path / 'cookies-jen.txt'


def test_configured_profiles_applies_per_user_goals_and_milestones(tmp_path):
    options = Mock(config=str(tmp_path / 'household.json'), cookies='legacy.txt',
                   username=None, demo=False, demo_login_needed=False)
    config = {'display': {'weekly_goals': {'workouts': 0}, 'milestones': []}, 'users': [
        {'name': 'Joel', 'weekly_goals': {'workouts': 5}, 'milestones': [100, 500]},
        {'name': 'Jen'},
    ]}
    with patch('peloton_led.Dashboard') as dashboard:
        configured_profiles(config, options)
    assert dashboard.call_args_list[0].args[1]['weekly_goals'] == {'workouts': 5}
    assert dashboard.call_args_list[0].args[1]['milestones'] == [100, 500]
    assert dashboard.call_args_list[1].args[1]['weekly_goals'] == {'workouts': 0}
    assert dashboard.call_args_list[1].args[1]['milestones'] == []


def test_pr_celebration_only_appears_once_across_rotations(tmp_path):
    from peloton_led import run_display_loop

    dashboard = Dashboard(tmp_path / 'missing-token', {}, demo=True)
    manager = Mock()
    display = {'duration': 0, 'overview_duration': 0, 'last_workout_duration': 0,
               'color': 'white'}
    run_display_loop(manager, dashboard, display, cycles=2)
    assert [call.args[0] for call in manager.show.call_args_list].count('pr') == 1


def test_64_row_rotation_keeps_total_separate_from_compact_lifetime_pages(tmp_path):
    from peloton_led import run_display_loop

    dashboard = Dashboard(tmp_path / 'missing-token', {}, demo=True)
    manager = Mock(matrix=Mock(height=64))
    display = {'duration': 0, 'overview_duration': 0, 'last_workout_duration': 0,
               'color': 'white'}
    run_display_loop(manager, dashboard, display, cycles=1)
    names = [call.args[0] for call in manager.show.call_args_list]
    assert names.count('lifetime') == 2
    assert names.count('discipline') == 1
    total_state = next(call.args[1] for call in manager.show.call_args_list
                       if call.args[0] == 'discipline')
    assert total_state['discipline'] == 'Total Workouts'


def test_64_row_discipline_pages_share_requested_duration():
    dashboard = Mock(login_required=False)
    dashboard.snapshot.return_value = {
        'me': {'username': 'Rider'}, 'summaries': [], 'status': 'ready',
        'totals': {
            'Total Workouts': 100, 'Cycling': 40, 'Strength': 30,
            'Bike Bootcamp': 20, 'Yoga': 10, 'Meditation': 5,
        },
    }
    manager = Mock(matrix=Mock(height=64))
    display = {'duration': 0, 'overview_duration': 1, 'last_workout_duration': 0,
               'color': 'white'}

    with patch('peloton_led.show_and_wait') as show:
        run_display_loop(manager, dashboard, display, cycles=1)

    discipline_calls = [call for call in show.call_args_list
                        if call.args[1] in ('discipline', 'lifetime')]
    assert len(discipline_calls) == 3
    assert {call.args[3] for call in discipline_calls} == {5.0}


def test_configured_rotation_order_and_disabled_sections():
    dashboard = Mock()
    dashboard.should_celebrate_pr.return_value = False
    snapshot = {'me': {'username': 'Rider'}, 'summaries': [{'workout_id': 'one'}],
                'totals': {'Total Workouts': 10, 'Cycling': 10}, 'status': 'ready',
                'weekly_progress': {'workouts': 2, 'minutes': 45}}
    display = {'rotation': ['goals', 'username'], 'weekly_goals': {'workouts': 3},
               'screen_durations': {'goals': 6}, 'last_workout_duration': 30,
               'overview_duration': 4, 'duration': 4, 'color': 'white'}
    pages = build_rotation_pages(snapshot, dashboard, display, 'Rider', 64)
    assert [page[0] for page in pages] == ['goal', 'username']
    assert pages[0][1]['current'] == 2
    assert pages[0][2] == 6


def test_username_profile_details_all_receive_display_time():
    dashboard = Mock()
    snapshot = {'me': {'username': 'Rider'}, 'summaries': [], 'status': 'ready',
                'totals': {'Total Workouts': 100, 'Cycling': 60, 'Yoga': 40},
                'weekly_progress': {'workouts': 3, 'minutes': 75}}
    display = {'rotation': ['username'], 'screen_durations': {'username': 1},
               'duration': 1, 'overview_duration': 1, 'last_workout_duration': 1,
               'color': 'white'}
    page = build_rotation_pages(snapshot, dashboard, display, 'Rider', 64)[0]
    assert [detail['label'] for detail in page[1]['details']] == [
        'TOTAL WORKOUTS', 'THIS WEEK', 'TOP DISCIPLINE']
    assert page[1]['details'][2]['value'] == 'Cycling / 60'
    assert page[1]['details'][1]['lines'] == ['3 WORKOUTS', '75 MINUTES']
    assert page[1]['details'][2]['lines'] == ['CYCLING', '60 WORKOUTS']
    assert page[2] == pytest.approx(12.0)


def test_username_profile_includes_top_three_instructors_when_present():
    dashboard = Mock()
    snapshot = {'me': {'username': 'Rider'}, 'summaries': [], 'status': 'ready',
                'totals': {'Total Workouts': 100, 'Cycling': 60},
                'weekly_progress': {'workouts': 3, 'minutes': 75},
                'instructor_counts': {'Cody Rigsby': 10, 'Robin Arzon': 7, 'Ally Love': 4,
                                      'Denis Morton': 1}}
    display = {'rotation': ['username'], 'screen_durations': {'username': 1},
               'duration': 1, 'overview_duration': 1, 'last_workout_duration': 1,
               'color': 'white'}
    page = build_rotation_pages(snapshot, dashboard, display, 'Rider', 64)[0]
    labels = [detail['label'] for detail in page[1]['details']]
    assert labels == ['TOTAL WORKOUTS', 'THIS WEEK', 'TOP DISCIPLINE',
                      'TOP INSTRUCTOR', '2ND INSTRUCTOR', '3RD INSTRUCTOR']
    initialize_fonts(64)
    from display.display import get_text_width, loaded_fonts
    assert all(get_text_width(loaded_fonts['stats'], label) <= 60
               for label in labels[3:])
    instructor_details = page[1]['details'][3:]
    assert [d['lines'] for d in instructor_details] == [
        ['CODY RIGSBY', '10 CLASSES'], ['ROBIN ARZON', '7 CLASSES'], ['ALLY LOVE', '4 CLASSES']]


def test_username_profile_has_no_instructor_details_when_untallied():
    dashboard = Mock()
    snapshot = {'me': {'username': 'Rider'}, 'summaries': [], 'status': 'ready',
                'totals': {'Total Workouts': 100, 'Cycling': 60},
                'weekly_progress': {'workouts': 3, 'minutes': 75}}
    display = {'rotation': ['username'], 'screen_durations': {'username': 1},
               'duration': 1, 'overview_duration': 1, 'last_workout_duration': 1,
               'color': 'white'}
    page = build_rotation_pages(snapshot, dashboard, display, 'Rider', 64)[0]
    labels = [detail['label'] for detail in page[1]['details']]
    assert 'TOP INSTRUCTOR' not in labels


def test_username_detail_animation_changes_lower_panel_only():
    matrix = ImageMatrix(height=64)
    initialize_fonts(64)
    screen = UsernameScreen()
    state = {'username': 'Rider', 'details': [
        {'label': 'TOTAL WORKOUTS', 'value': '100'},
        {'label': 'THIS WEEK', 'value': '3 WORKOUTS / 75 MIN'},
    ]}
    screen.on_enter(matrix, state)
    screen.update(0.4)
    screen.render(matrix, state)
    first = matrix.image.copy()
    screen.update(4.0)
    matrix.Clear()
    screen.render(matrix, state)
    assert first.crop((0, 0, 64, 24)).tobytes() == matrix.image.crop((0, 0, 64, 24)).tobytes()
    assert first.crop((0, 24, 64, 64)).tobytes() != matrix.image.crop((0, 24, 64, 64)).tobytes()


@pytest.mark.parametrize('height', [32, 64])
def test_long_username_uses_smaller_font_without_truncation(height):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    screen = UsernameScreen()
    username = 'xxjclarksterxx'
    font = screen._username_font(username, matrix.width - 4)
    from display.display import get_text_width
    assert get_text_width(font, username) <= matrix.width - 4
    assert screen.render(matrix, {'username': username, 'details': []})


def test_scheduled_brightness_handles_day_and_overnight_ranges():
    from datetime import datetime
    display = {'brightness_schedule': {'day': 80, 'night': 15,
               'day_start': '07:00', 'night_start': '22:00'}}
    assert scheduled_brightness(display, datetime(2026, 1, 1, 12, 0)) == 80
    assert scheduled_brightness(display, datetime(2026, 1, 1, 23, 0)) == 15
    display['brightness_schedule']['day_start'] = '20:00'
    display['brightness_schedule']['night_start'] = '06:00'
    assert scheduled_brightness(display, datetime(2026, 1, 1, 23, 0)) == 80


def test_32_row_optional_second_workout_page_renders_stats():
    matrix = ImageMatrix(height=32)
    initialize_fonts(32)
    summary = {'discipline': 'Cycling', 'compact_page': 1, 'duration_min': 20,
               'total_output_kj': 200, 'strive_score': 12, 'hr_avg': 130,
               'calories': 250}
    assert LastWorkoutScreen().render(matrix, summary)
    assert matrix.image.getbbox() is not None


def test_lifetime_icon_page_renders_real_pixels():
    from peloton.totals import lifetime_overview_pages

    matrix = ImageMatrix(height=64)
    initialize_fonts(64)
    totals = {'Cycling': 1200, 'Bike Bootcamp': 34, 'Running': 204,
              'Walking': 75, 'Rowing': 18, 'Strength': 300,
              'Yoga': 90, 'Meditation': 50, 'Cardio': 40,
              'Total Workouts': 2011}
    pages = lifetime_overview_pages(totals)
    assert len(pages) == 3
    assert all(item['label'] != 'Total Workouts' for page in pages for item in page)
    assert LifetimeOverviewScreen().render(matrix, {'items': pages[0], 'page': 1, 'pages': 2})
    assert matrix.image.getbbox() is not None
    assert any(matrix.image.getpixel((x, y)) == (240, 70, 25)
               for x in range(64) for y in range(64))


def test_supplied_svg_icons_render_as_distinct_native_pixel_masks():
    from display.ui.discipline_icons import DISCIPLINE_ICON_ROWS
    from display.ui.lifetime_overview import draw_icon
    matrix = ImageMatrix(height=64)
    expected = {'cycling', 'bike_bootcamp', 'running', 'tread_bootcamp',
                'walking', 'rowing', 'row_bootcamp', 'strength', 'cardio',
                'yoga', 'meditation', 'stretching'}
    assert expected <= DISCIPLINE_ICON_ROWS.keys()
    assert len({DISCIPLINE_ICON_ROWS[key] for key in expected}) == len(expected)
    for key in expected:
        assert len(DISCIPLINE_ICON_ROWS[key]) == 24
        assert all(len(row) == 26 for row in DISCIPLINE_ICON_ROWS[key])
        draw_icon(matrix, key, 0, 0, (0, 150, 255))
        assert matrix.image.crop((0, 0, 26, 24)).getbbox() is not None


def test_dance_cardio_uses_the_cardio_svg_mask():
    from display.ui.lifetime_overview import draw_icon
    cardio = ImageMatrix(height=64)
    dance = ImageMatrix(height=64)
    draw_icon(cardio, 'cardio', 0, 0, (255, 65, 90))
    draw_icon(dance, 'dance_cardio', 0, 0, (255, 65, 90))
    assert cardio.image.tobytes() == dance.image.tobytes()


def test_every_discipline_figure_has_a_hollow_square_head():
    from display.ui.discipline_icons import DISCIPLINE_HEAD_SQUARES
    from display.ui.lifetime_overview import draw_icon
    color = (255, 255, 255)
    for key, (_, _, _, _, left, top, size) in DISCIPLINE_HEAD_SQUARES.items():
        matrix = ImageMatrix(height=64)
        draw_icon(matrix, key, 0, 0, color)
        for offset in range(size):
            assert matrix.image.getpixel((left + offset, top)) == color
            assert matrix.image.getpixel((left + offset, top + size - 1)) == color
            assert matrix.image.getpixel((left, top + offset)) == color
            assert matrix.image.getpixel((left + size - 1, top + offset)) == color
        assert matrix.image.getpixel((left + 1, top + 1)) == (0, 0, 0)


def test_directly_edited_pose_icons_keep_their_mask_head_shapes():
    from display.ui.discipline_icons import DISCIPLINE_HEAD_SQUARES
    assert 'yoga' not in DISCIPLINE_HEAD_SQUARES
    assert 'meditation' not in DISCIPLINE_HEAD_SQUARES
    assert 'stretching' not in DISCIPLINE_HEAD_SQUARES


def test_row_bootcamp_custom_rail_connects_to_its_machine():
    from display.ui.lifetime_overview import draw_icon
    bootcamp = ImageMatrix(height=64)
    color = (0, 150, 255)
    draw_icon(bootcamp, 'row_bootcamp', 0, 0, color)
    assert all(bootcamp.image.getpixel((x, 14)) == color for x in range(9, 18))
    assert all(bootcamp.image.getpixel((18, y)) == color for y in range(11, 14))


@pytest.mark.parametrize('discipline', ['bike_bootcamp', 'tread_bootcamp', 'row_bootcamp'])
def test_bootcamp_icons_remain_static(discipline):
    matrix = ImageMatrix(height=64)
    initialize_fonts(64)
    screen = LifetimeOverviewScreen()
    state = {'items': [{'label': discipline, 'icon': discipline, 'count': 41}]}
    screen.render(matrix, state)
    first = matrix.image.copy()
    screen.update(5.0)
    screen.render(matrix, state)
    assert first.tobytes() == matrix.image.tobytes()


def test_bootcamp_tiles_keep_distinct_svg_icons():
    matrix = ImageMatrix(height=64)
    initialize_fonts(64)
    screen = LifetimeOverviewScreen()
    state = {'items': [
        {'label': 'Bike Bootcamp', 'icon': 'bike_bootcamp', 'count': 41},
        {'label': 'Tread Bootcamp', 'icon': 'tread_bootcamp', 'count': 111},
    ]}
    screen.render(matrix, state)
    assert matrix.image.crop((3, 0, 29, 24)).tobytes() != \
           matrix.image.crop((35, 0, 61, 24)).tobytes()


def test_static_lifetime_page_is_still_composed_atomically():
    assert LifetimeOverviewScreen.atomic_frames is True
    assert LifetimeOverviewScreen.animated is False
