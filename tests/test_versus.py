"""Head-to-head weekly page for households with two or more riders."""
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from display.display import initialize_fonts
from display.ui.versus_screen import (DAY_AHEAD, DAY_DONE, DAY_TODAY, DETAIL_INTERVAL_SECONDS,
                                      VersusScreen, weekly_leader)
from peloton.config import load_config
from peloton.goals import week_day
from peloton_led import build_rotation_pages, run_multi_user_loop, weekly_rivals
from scripts.render_demo import ImageMatrix

JOEL = {'name': 'Joel', 'workouts': 2, 'minutes': 35, 'output_kj': 412}
JEN = {'name': 'Jen', 'workouts': 7, 'minutes': 145, 'output_kj': 1180}
GOLD = (255, 215, 0)


def test_leader_is_decided_by_workouts_then_minutes_then_output():
    assert weekly_leader([JOEL, JEN]) == 1
    assert weekly_leader([{**JEN, 'minutes': 200}, JEN]) == 0
    assert weekly_leader([JEN, {**JEN, 'output_kj': 1181}]) == 1
    assert weekly_leader([JEN, dict(JEN)]) is None
    assert weekly_leader([{'name': 'A'}, {'name': 'B', 'workouts': None}]) is None


def dashboard_with(progress):
    dashboard = Mock()
    dashboard.snapshot.return_value = {'weekly_progress': progress}
    return dashboard


def test_rivals_come_from_every_profile_and_tolerate_missing_progress():
    profiles = [{'name': 'Joel', 'dashboard': dashboard_with({'workouts': 2, 'minutes': 35})},
                {'name': 'Jen', 'dashboard': dashboard_with(None)}]
    assert weekly_rivals(profiles) == [
        {'name': 'Joel', 'workouts': 2, 'minutes': 35, 'output_kj': 0},
        {'name': 'Jen', 'workouts': 0, 'minutes': 0, 'output_kj': 0}]


def test_versus_page_is_shown_once_per_household_cycle():
    profiles = [{'name': 'Joel', 'dashboard': dashboard_with({'workouts': 2})},
                {'name': 'Jen', 'dashboard': dashboard_with({'workouts': 7})}]
    with patch('peloton_led.run_display_loop') as run:
        run_multi_user_loop(Mock(), profiles, {}, {}, cycles=1)
    rivals = [call.kwargs['rivals'] for call in run.call_args_list]
    assert rivals[0] and [r['name'] for r in rivals[0]] == ['Joel', 'Jen']
    assert rivals[1] is None


@pytest.mark.parametrize('rivals, expected', [(None, 0), ([JOEL], 0), ([JOEL, JEN], 1)])
def test_versus_needs_two_riders(rivals, expected):
    display = {'rotation': ['versus'], 'last_workout_duration': 15, 'overview_duration': 5}
    snapshot = {'summaries': [], 'totals': {}, 'status': 'ready'}
    pages = build_rotation_pages(snapshot, Mock(), display, 'R', 64, rivals=rivals)
    assert len(pages) == expected


def test_32_row_versus_page_is_long_enough_for_each_stat():
    display = {'rotation': ['versus'], 'last_workout_duration': 15, 'overview_duration': 5}
    snapshot = {'summaries': [], 'totals': {}, 'status': 'ready'}
    assert build_rotation_pages(snapshot, Mock(), display, 'R', 32, rivals=[JOEL, JEN])[0][2] == \
        3 * DETAIL_INTERVAL_SECONDS
    assert build_rotation_pages(snapshot, Mock(), display, 'R', 64, rivals=[JOEL, JEN])[0][2] == 5


def render(height, riders, elapsed=0.5, weekday=None):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    screen = VersusScreen()
    screen.on_enter(matrix, None)
    screen.update(elapsed)
    assert screen.render(matrix, {'riders': riders, 'weekday': weekday})
    return matrix


def test_week_day_follows_the_weekly_goal_timezone():
    now = datetime(2026, 11, 2, 3, tzinfo=timezone.utc)  # Monday in UTC, still Sunday in New York
    assert week_day('UTC', now) == 0
    assert week_day('America/New_York', now) == 6


def test_versus_page_gets_today_in_the_configured_timezone():
    display = {'rotation': ['versus'], 'last_workout_duration': 15, 'overview_duration': 5,
               'timezone': 'America/New_York'}
    snapshot = {'summaries': [], 'totals': {}, 'status': 'ready', 'me': {'timezone': 'UTC'}}
    with patch('peloton_led.week_day', return_value=4) as day:
        state = build_rotation_pages(snapshot, Mock(), display, 'R', 64, rivals=[JOEL, JEN])[0][1]
    day.assert_called_once_with('America/New_York')
    assert state['weekday'] == 4


@pytest.mark.parametrize('height, top, rows', [(64, 60, 2), (32, 31, 1)])
def test_week_dashes_light_finished_days_and_mark_today(height, top, rows):
    matrix = render(height, [JOEL, JEN], weekday=2)  # Wednesday
    pixels = matrix.image.load()
    # 7-wide dashes with 2-pixel gaps, starting at x=1.
    starts = [1 + day * 9 for day in range(7)]
    for y in range(top, top + rows):
        assert [pixels[x + 3, y] for x in starts] == [DAY_DONE] * 2 + [DAY_TODAY] + [DAY_AHEAD] * 4
        assert pixels[8, y] == (0, 0, 0)
    # A blank row keeps the strip clear of the values above it.
    assert all(pixels[x, top - 1] == (0, 0, 0) for x in range(64))


def test_64_row_week_strip_replaces_the_title():
    def grey_title(matrix):  # THIS WEEK is the only grey text above the names.
        return any(matrix.image.getpixel((x, y)) == (145, 165, 190) for x in range(64) for y in range(8))
    assert grey_title(render(64, [JOEL, JEN]))
    assert not grey_title(render(64, [JOEL, JEN], weekday=0))


@pytest.mark.parametrize('weekday', [None, 7, 'Mon'])
def test_unknown_weekday_draws_no_strip(weekday):
    matrix = render(32, [JOEL, JEN], weekday=weekday)
    assert all(matrix.image.getpixel((x, 31)) == (0, 0, 0) for x in range(64))


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('riders', [
    [JOEL, JEN],
    [{'name': 'Christopher', 'workouts': 12, 'minutes': 1450, 'output_kj': 12345},
     {'name': 'Alexandria', 'workouts': 9, 'minutes': 999, 'output_kj': 9999}]])
def test_versus_fits_both_boards(height, riders):
    for turn in range(3 if height == 32 else 1):
        matrix = render(height, riders, 0.5 + turn * DETAIL_INTERVAL_SECONDS)
        pixels = matrix.image.load()
        # Nothing touches the side edges, and the two halves never run together.
        assert all(pixels[x, y] == (0, 0, 0) for x in (0, 63) for y in range(height))
        assert GOLD in {c for _, c in matrix.image.getcolors(64 * 64)}


def test_versus_tie_has_no_gold():
    matrix = render(64, [JEN, {**JEN, 'name': 'Joel'}])
    assert GOLD not in {c for _, c in matrix.image.getcolors(64 * 64)}


def test_versus_renders_nothing_for_one_rider():
    initialize_fonts(64)
    assert not VersusScreen().render(ImageMatrix(height=64), {'riders': [JOEL]})


def test_config_accepts_versus(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"display": {"rotation": ["versus"], "screen_durations": {"versus": 8}}}')
    assert load_config(str(path))['display']['screen_durations'] == {'versus': 8}
