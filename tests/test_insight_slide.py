"""The workout-compare insight slide on the latest-workout page (both board sizes)."""
import pytest

from display.display import initialize_fonts
from display.ui.last_workout_screen import (GRAPH_FRAME_EXTRA_SECONDS, LastWorkoutScreen, detail_hold_seconds,
                                           insight_lines, rotating_details)
from peloton.demo import demo_data
from peloton.summaries import summarize_workout
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix
from tests.test_workout_graph import demo_ride, demo_strength, render_slide

ORANGE = (255, 140, 0)
GREY = (145, 165, 190)


def with_insight(summary, lines):
    return {**summary, 'insight': {'code': 'go_up_lighter', 'lines': lines, 'facts': {}}}


def lit(matrix, colour, rows, columns):
    pixels = matrix.image.load()
    return [(x, y) for y in rows for x in columns if pixels[x, y] == colour]


def test_the_insight_slide_comes_last_and_only_with_two_good_lines():
    ride = with_insight(demo_ride(), ['STRONG RIDE', '205 VS 180 W'])
    for height in (32, 64):
        details = rotating_details(ride, height)
        assert details[-1] == {'label': 'insight', 'value': '', 'kind': 'insight'}
        assert [d.get('kind') for d in details].count('insight') == 1
        strength = with_insight(demo_strength(), ['GO UP A WEIGHT', 'ROW'])
        assert [d.get('kind') for d in rotating_details(strength, height)][-2:] == ['muscles', 'insight']


@pytest.mark.parametrize('insight', [
    None, 'text', [], {}, {'lines': None}, {'lines': 'AB'}, {'lines': ['ONE']}, {'lines': ['A', 'B', 'C']},
    {'lines': ['A', '']}, {'lines': ['  ', 'B']}, {'lines': ['A', 7]}, {'lines': ('A', 'B')},
])
def test_a_damaged_insight_is_ignored(insight):
    summary = {**demo_ride(), 'insight': insight}
    assert insight_lines(summary) is None
    assert 'insight' not in [d.get('kind') for d in rotating_details(summary, 64)]
    assert rotating_details(summary, 64) == rotating_details(demo_ride(), 64)


def test_the_slide_holds_like_the_other_chart_slides_and_sizes_the_page():
    assert detail_hold_seconds({'kind': 'insight'}, 4) == 4 + GRAPH_FRAME_EXTRA_SECONDS
    ride = with_insight(demo_ride(), ['STRONG RIDE', '205 VS 180 W'])
    data = demo_data()
    snapshot = {'me': data['me'], 'summaries': [ride], 'totals': {}, 'weekly_progress': {}}

    class Dash:
        pending_milestones = pending_discipline_milestones = lambda self, *_: []
        should_celebrate_pr = lambda self, *_: False

    display = {'rotation': ['latest_workouts'], 'last_workout_detail_interval': 4.0, 'screen_durations': {}}
    plain = build_rotation_pages({**snapshot, 'summaries': [demo_ride()]}, Dash(), display, 'R', 64)
    shown = build_rotation_pages(snapshot, Dash(), display, 'R', 64)
    assert shown[0][2] == pytest.approx(plain[0][2] + 4 + GRAPH_FRAME_EXTRA_SECONDS)


@pytest.mark.parametrize('height', [32, 64])
def test_the_slide_draws_both_lines_and_keeps_the_heart_rate_row(height):
    summary = with_insight(demo_strength(), ['GO UP A WEIGHT', 'ROW'])
    matrix = render_slide(summary, height, 'insight')
    assert lit(matrix, GREY, range(height), range(64))        # headline in the label grey
    assert lit(matrix, ORANGE, range(14, height - 8), range(64))  # detail in the discipline colour
    assert lit(matrix, (220, 20, 20), range(height - 8, height), range(12))  # heart


def render_at(summary, height, seconds):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    details = rotating_details(summary, height)
    start = 4 + sum(detail_hold_seconds(d, 4) for d in details[:-1])
    screen = LastWorkoutScreen()
    screen.on_enter(matrix, summary)
    screen.update(start + seconds)
    assert screen.render(matrix, summary)
    return matrix


@pytest.mark.parametrize('height', [32, 64])
def test_a_long_movement_name_scrolls_under_blank_margins(height):
    summary = with_insight(demo_strength(), ['GO UP A WEIGHT', 'WIDE GRIP BENT OVER ROW'])
    frames = [render_at(summary, height, t) for t in (0.1, 2.0, 4.5)]
    assert len({f.image.tobytes() for f in frames}) == 3
    rows = range(16, height - 8)
    margins = list(range(0, 2)) + list(range(62, 64))
    for frame in frames:
        assert not lit(frame, ORANGE, rows, margins)
        assert lit(frame, ORANGE, rows, range(2, 62))
    # Held at the start, then at the end.
    assert render_at(summary, height, 0.1).image.tobytes() == render_at(summary, height, 0.3).image.tobytes()
    assert render_at(summary, height, 4.5).image.tobytes() == render_at(summary, height, 4.9).image.tobytes()


def test_a_short_second_line_does_not_scroll():
    summary = with_insight(demo_ride(), ['STRONG RIDE', '205 VS 180 W'])
    for height in (32, 64):
        assert render_at(summary, height, 0.1).image.tobytes() == render_at(summary, height, 4.5).image.tobytes()


def test_the_demo_shows_the_slide_only_with_the_switch_on():
    from peloton.dashboard import Dashboard
    off = Dashboard('unused', {}, demo=True).snapshot()['summaries']
    on = Dashboard('unused', {'workout_insights': True}, demo=True).snapshot()['summaries']
    assert not any('insight' in s for s in off)
    assert {s['workout_id'] for s in on if 'insight' in s} == {'demo-cycling', 'demo-strength'}
    assert all(insight_lines(s) for s in on if 'insight' in s)
