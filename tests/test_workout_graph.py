"""Workout output graph and heart-rate zone slides (both board sizes)."""
from unittest.mock import Mock

import pytest

from display.display import initialize_fonts
from display.ui.last_workout_screen import HR_ZONE_COLORS, LastWorkoutScreen, rotating_details
from peloton.demo import demo_data
from peloton.summaries import heart_rate_zone_seconds, performance_graph, summarize_workout
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix

ZONES = [{'slug': f'zone{i + 1}', 'min_value': low, 'duration': 60}
         for i, low in enumerate((0, 120, 138, 157, 175))]


def perf(output=None, heart=None, zones=ZONES, durations=None):
    metrics = []
    if output is not None:
        metrics.append({'slug': 'output', 'values': output})
    if heart is not None:
        metrics.append({'slug': 'heart_rate', 'values': heart, 'zones': zones})
    result = {'metrics': metrics}
    if durations is not None:
        result['effort_zones'] = {'heart_rate_zone_durations': durations}
    return result


def test_graph_prefers_output_and_colors_buckets_by_heart_rate_zone():
    graph = performance_graph(perf(output=[100] * 60 + [300] * 60, heart=[110] * 60 + [160] * 60))
    assert graph['metric'] == 'output' and graph['unit'] == 'W'
    assert len(graph['values']) == 60
    assert graph['values'][0] == 100 and graph['values'][-1] == 300
    assert graph['zones'][0] == 1 and graph['zones'][-1] == 4
    assert graph['peak'] == 300


def test_graph_falls_back_to_heart_rate_without_output():
    graph = performance_graph(perf(output=[0, 0, 0], heart=[100, 150, 170]))
    assert graph['metric'] == 'heart_rate'
    assert graph['values'] == [100, 150, 170]
    assert graph['zones'] == [1, 3, 4]


@pytest.mark.parametrize('bad', [
    {}, {'metrics': None}, {'metrics': [{'slug': 'output', 'values': None}]},
    {'metrics': [{'slug': 'output', 'values': ['x', None]}]},
    {'metrics': [{'slug': 'heart_rate', 'values': [120]}]},  # a single sample isn't a graph
])
def test_graph_is_none_for_missing_or_malformed_series(bad):
    assert performance_graph(bad) is None


def test_graph_skips_gaps_and_works_without_zone_bounds():
    graph = performance_graph(perf(output=[None, 200, None, 220], heart=None))
    assert graph['values'] == [0, 200, 0, 220]
    assert graph['zones'] == [None] * 4


def test_zone_seconds_from_effort_zones_then_heart_rate_metric():
    durations = {f'heart_rate_z{i}_duration': i * 10 for i in range(1, 6)}
    assert heart_rate_zone_seconds(perf(durations=durations)) == [10, 20, 30, 40, 50]
    assert heart_rate_zone_seconds(perf(heart=[120, 130])) == [60] * 5
    assert heart_rate_zone_seconds(perf(durations={})) is None
    assert heart_rate_zone_seconds(perf(heart=[120], zones=ZONES[:3])) is None
    assert heart_rate_zone_seconds({}) is None


def demo_ride():
    data = demo_data()
    return summarize_workout(data['workouts'][0], data['performance']['demo-cycling'])


@pytest.mark.parametrize('height', [32, 64])
def test_graph_and_zones_close_out_the_rotation(height):
    kinds = [d.get('kind') for d in rotating_details(demo_ride(), height)]
    assert kinds[-2:] == ['graph', 'zones']
    assert kinds.count('graph') == kinds.count('zones') == 1
    no_data = {**demo_ride(), 'graph': None, 'hr_zone_seconds': None}
    assert not any(d.get('kind') for d in rotating_details(no_data, height))


def test_rotation_page_duration_counts_the_new_slides():
    dashboard = Mock()
    dashboard.should_celebrate_pr.return_value = False
    ride = demo_ride()
    snapshot = {'summaries': [ride], 'totals': {}, 'status': 'ready'}
    display = {'rotation': ['latest_workouts'], 'last_workout_duration': 15,
               'last_workout_detail_interval': 4, 'overview_duration': 4}
    for height in (32, 64):
        expected = 4 * (1 + len(rotating_details(ride, height)))
        assert build_rotation_pages(snapshot, dashboard, display, 'R', height)[0][2] == expected


def render_slide(summary, height, kind):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    turn = [d.get('kind') for d in rotating_details(summary, height)].index(kind)
    screen = LastWorkoutScreen()
    screen.on_enter(matrix, summary)
    screen.update(4 * (turn + 1) + 0.5)
    assert screen.render(matrix, summary)
    return matrix


def colors(matrix):
    return {c for _, c in matrix.image.getcolors(64 * 64)}


@pytest.mark.parametrize('height', [32, 64])
def test_graph_slide_draws_zone_colored_columns(height):
    matrix = render_slide(demo_ride(), height, 'graph')
    found = colors(matrix)
    assert {HR_ZONE_COLORS[1], HR_ZONE_COLORS[2], HR_ZONE_COLORS[3]} <= found
    assert (255, 215, 0) in found  # the gold peak marker
    heart = (220, 20, 20)
    # 32 rows give the bar's space to the graph; 64 rows keep the bar.
    assert (heart in found) == (height == 64)


@pytest.mark.parametrize('height', [32, 64])
def test_zone_slide_fills_the_bar_and_names_the_top_zone(height):
    ride = demo_ride()
    matrix = render_slide(ride, height, 'zones')
    seconds = ride['hr_zone_seconds']
    top = max(range(5), key=lambda i: seconds[i])
    pixels = matrix.image.load()
    bar_row = next(y for y in range(height) if pixels[2, y] in HR_ZONE_COLORS
                   and pixels[61, y] in HR_ZONE_COLORS)
    # The stacked bar spans the full 60 px with no gaps.
    assert all(pixels[x, bar_row] in HR_ZONE_COLORS for x in range(2, 62))
    # "ZONE n" is written in the top zone's color below the bar.
    assert any(pixels[x, y] == HR_ZONE_COLORS[top]
               for y in range(bar_row + 3, height) for x in range(64))
