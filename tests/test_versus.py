"""Head-to-head weekly page for households with two or more riders."""
from unittest.mock import Mock, patch

import pytest

from display.display import initialize_fonts
from display.ui.versus_screen import DETAIL_INTERVAL_SECONDS, VersusScreen, weekly_leader
from peloton.config import load_config
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


def render(height, riders, elapsed=0.5):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    screen = VersusScreen()
    screen.on_enter(matrix, None)
    screen.update(elapsed)
    assert screen.render(matrix, {'riders': riders})
    return matrix


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
