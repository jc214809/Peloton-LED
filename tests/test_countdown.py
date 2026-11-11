"""Next-milestone countdown and step milestones."""
from unittest.mock import Mock

import pytest

from display.display import initialize_fonts
from display.ui.countdown_screen import BAR_EMPTY, BAR_FILL, CountdownScreen
from peloton.config import load_config
from peloton.dashboard import Dashboard
from peloton.goals import next_milestone, reached_milestones, upcoming_milestones
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


def _total_rotation(total, **display):
    display = {'rotation': ['next_milestone', 'milestones'], 'last_workout_duration': 15,
               'overview_duration': 5, 'milestones': [], 'milestone_step': 100, **display}
    snapshot = {'summaries': [], 'totals': {'Total Workouts': total}, 'status': 'ready'}
    dashboard = Mock()
    dashboard.pending_discipline_milestones.return_value = []
    dashboard.pending_milestones.return_value = []
    return build_rotation_pages(snapshot, dashboard, display, 'R', display.pop('height', 64))


def test_total_countdown_shows_only_within_a_few_workouts_like_a_disciplines():
    # 2,123 is 77 from 2,200: no page, the same rule as a discipline's.
    assert _total_rotation(2123) == []
    assert _total_rotation(2195) == [('countdown', {'total': 2195, 'target': 2200, 'previous': 2100,
                                                    'title': 'Workout', 'discipline': None}, 5)]
    assert _total_rotation(2195, height=32)[0][1]['title'] == 'Workouts'  # TO 2,200 / WORKOUTS
    assert _total_rotation(2190, milestone_within=10)[0][1]['target'] == 2200
    # A configured milestone comes first; with neither list nor step there is nothing to count to.
    assert _total_rotation(248, milestones=[250])[0][1]['target'] == 250
    assert _total_rotation(2195, milestone_step=0) == []


def test_rotation_celebrates_a_step_milestone_without_configured_milestones():
    snapshot = {'summaries': [], 'totals': {'Total Workouts': 2201}, 'status': 'ready'}
    dashboard = Mock()
    dashboard.pending_discipline_milestones.return_value = []
    dashboard.pending_milestones.return_value = [2200]
    display = {'rotation': ['next_milestone', 'milestones'], 'last_workout_duration': 15,
               'overview_duration': 5, 'milestones': [], 'milestone_step': 100}
    pages = build_rotation_pages(snapshot, dashboard, display, 'R', 64)
    assert [page[0] for page in pages] == ['celebration']
    assert pages[0][1]['milestone'] == 2200


def test_total_and_disciplines_share_the_page_limit_nearest_first():
    totals = {'Total Workouts': 2197, 'Strength': 496, 'Cycling': 598, 'Yoga': 23}
    snapshot = {'summaries': [], 'totals': totals, 'status': 'ready'}
    dashboard = Mock()
    dashboard.pending_discipline_milestones.return_value = []
    dashboard.pending_milestones.return_value = []
    display = {'rotation': ['next_milestone'], 'last_workout_duration': 15, 'overview_duration': 5,
               'milestones': [], 'milestone_step': 100}
    titles = [p[1]['title'] for p in build_rotation_pages(snapshot, dashboard, display, 'R', 64)]
    # Cycling 2 away and Yoga 2 (bigger target first), then the total 3 away; Strength (4) is the fourth.
    assert titles == ['Cycling', 'Yoga', 'Workout']
    display['milestone_pages'] = 4
    assert [p[1]['title'] for p in build_rotation_pages(snapshot, dashboard, display, 'R', 64)][-1] == 'Strength'


def test_upcoming_milestones_put_the_total_first_on_a_tie():
    totals = {'Total Workouts': 2196, 'Strength': 496}
    upcoming = upcoming_milestones(2196, [], 100, totals)
    assert [u['discipline'] for u in upcoming] == [None, 'strength']
    assert upcoming[0] == {'discipline': None, 'label': 'Workouts', 'count': 2196, 'target': 2200,
                           'previous': 2100}
    assert upcoming_milestones(None, [], 100, totals) == upcoming_milestones(2123, [], 100, totals)[:1]


@pytest.mark.parametrize('height', [32, 64])
def test_total_countdown_reads_3_more_2200th_workout(height, monkeypatch):
    import display.ui.countdown_screen as screen
    drawn = []
    original = screen.graphics.DrawText
    def record(matrix, font, x, y, color, text):
        drawn.append(text)
        return original(matrix, font, x, y, color, text)
    monkeypatch.setattr(screen.graphics, 'DrawText', record)
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    title = 'Workout' if height == 64 else 'Workouts'
    assert CountdownScreen().render(matrix, {'total': 2197, 'previous': 2100, 'target': 2200,
                                             'title': title, 'discipline': None})
    expected = (['3', 'TO GO', '2', ',', '200', 'TH', 'WORKOUT'] if height == 64
                else ['3', 'MORE', 'TO', '2,200', 'WORKOUTS'])
    assert drawn == expected
    pixels = matrix.image.load()
    assert all(pixels[x, y] == (0, 0, 0) for x in (0, 63) for y in range(height))
    if height == 64:
        bar_row = next(y for y in range(height) if pixels[3, y] in (BAR_FILL, BAR_EMPTY))
        assert sum(pixels[x, bar_row] == BAR_FILL for x in range(64)) == round(58 * 97 / 100)


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
    path.write_text('{"display": {"rotation": ["next_milestone"], "screen_durations": {"next_milestone": 6}}}')
    assert load_config(str(path))['display']['screen_durations'] == {'next_milestone': 6}
