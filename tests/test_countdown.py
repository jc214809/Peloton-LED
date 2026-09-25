"""Next-milestone countdown and step milestones."""
from unittest.mock import Mock

import pytest

from display.display import initialize_fonts
from display.ui.countdown_screen import BAR_EMPTY, BAR_FILL, CountdownScreen
from peloton.config import load_config
from peloton.dashboard import Dashboard
from peloton.goals import next_milestone, reached_milestones
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix


@pytest.mark.parametrize('total, thresholds, step, expected', [
    (2111, [100, 250, 500], 100, (2100, 2200)),   # past every configured one: next hundred
    (180, [100, 250, 500], 100, (100, 250)),      # configured milestone comes first
    (240, [250], 100, (200, 250)),                # previous is the nearer step
    (2111, [100, 250, 500], 0, None),             # steps off and nothing configured ahead
    (0, [], 100, (0, 100)),
    (2200, [], 100, (2200, 2300)),                # exactly on a milestone: count to the next
    (None, [], 100, None), (-5, [], 100, None), (True, [], 100, None),
])
def test_next_milestone(total, thresholds, step, expected):
    assert next_milestone(total, thresholds, step) == expected


def test_step_milestones_only_celebrate_when_just_crossed():
    assert reached_milestones(2203, [100], 100) == [100, 2200]
    assert reached_milestones(2111, [100], 100) == [100]   # 2,100 was 11 workouts ago
    assert reached_milestones(2111, [100]) == [100]
    assert reached_milestones(None, [100], 100) == []


def test_dashboard_celebrates_a_fresh_step_milestone_once(tmp_path):
    dashboard = Dashboard(tmp_path / 'token', {'milestones': [], 'milestone_step': 100,
                                               'cache_path': str(tmp_path / 'cache.json')})
    snapshot = {'totals': {'Total Workouts': 2201}, 'celebrated_milestones': []}
    assert dashboard.pending_milestones(snapshot) == [2200]
    snapshot['celebrated_milestones'] = [2200]
    assert dashboard.pending_milestones(snapshot) == []


def test_rotation_adds_countdown_and_step_celebration_without_configured_milestones():
    display = {'rotation': ['next_milestone', 'milestones'], 'last_workout_duration': 15,
               'overview_duration': 5, 'milestones': [], 'milestone_step': 100}
    snapshot = {'summaries': [], 'totals': {'Total Workouts': 2201}, 'status': 'ready'}
    dashboard = Mock()
    dashboard.pending_milestones.return_value = [2200]
    pages = build_rotation_pages(snapshot, dashboard, display, 'R', 64)
    assert pages[0] == ('countdown', {'total': 2201, 'previous': 2200, 'target': 2300}, 5)
    assert pages[1][0] == 'goal' and pages[1][1]['target'] == 2200
    display['milestone_step'] = 0
    assert [p[0] for p in build_rotation_pages(snapshot, dashboard, display, 'R', 64)] == []


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('state', [{'total': 2111, 'previous': 2100, 'target': 2200},
                                   {'total': 12, 'previous': 0, 'target': 10000}])
def test_countdown_fits_and_fills_the_bar_by_progress(height, state):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    assert CountdownScreen().render(matrix, state)
    pixels = matrix.image.load()
    assert all(pixels[x, y] == (0, 0, 0) for x in (0, 63) for y in range(height))
    bar_row = next(y for y in range(height) if pixels[60, y] in (BAR_FILL, BAR_EMPTY))
    filled = sum(pixels[x, bar_row] == BAR_FILL for x in range(64))
    expected = round(58 * (state['total'] - state['previous']) / (state['target'] - state['previous']))
    assert filled == expected


@pytest.mark.parametrize('state', [{}, {'total': 2200, 'previous': 2100, 'target': 2200},
                                   {'total': '5', 'previous': 0, 'target': 100}])
def test_countdown_renders_nothing_for_bad_state(state):
    initialize_fonts(64)
    assert not CountdownScreen().render(ImageMatrix(height=64), state)


def test_config_milestone_step(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"display": {"rotation": ["next_milestone"]}}')
    assert load_config(str(path))['display']['milestone_step'] == 100
    path.write_text('{"display": {"milestone_step": -1}}')
    with pytest.raises(ValueError, match='milestone_step'):
        load_config(str(path))
