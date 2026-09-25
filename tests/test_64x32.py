"""64x32 panel layout: everything must fit in 32 rows without collisions."""
from unittest.mock import Mock

import pytest

from display.display import initialize_fonts
from display.ui.last_workout_screen import LastWorkoutScreen, rotating_details
from peloton.demo import demo_data
from peloton.summaries import summarize_workout
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix

GREY = (145, 165, 190)
WHITE = (255, 255, 255)
HEART = (220, 20, 20)
BAR_TOP = 26  # first row of the HR/calories bar on a 32-row panel


def rows_of(matrix, color, x_range=range(64)):
    pixels = matrix.image.load()
    return sorted({y for y in range(matrix.height) for x in x_range if pixels[x, y] == color})


def frame(summary, elapsed, height=32):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    screen = LastWorkoutScreen()
    screen.on_enter(matrix, summary)
    screen.update(elapsed)
    assert screen.render(matrix, summary)
    return matrix


STRENGTH = {'discipline': 'Strength', 'title': '30 min Full Body Strength',
            'duration_min': 30, 'strive_score': 11.3, 'hr_max': 142,
            'hr_avg': 109, 'calories': 162, 'instructor': 'Matty Maggiacomo'}


def demo_summaries():
    data = demo_data()
    return [summarize_workout(w, data['performance'][w['id']]) for w in data['workouts']]


def test_32_rows_lead_the_rotation_with_the_instructor():
    labels = [d['label'] for d in rotating_details(STRENGTH, 32)]
    assert labels == ['instructor', 'strive score', 'max heart rate']
    assert [d['label'] for d in rotating_details(STRENGTH, 64)] == ['strive score', 'max heart rate']


def test_32_row_page_duration_includes_the_instructor_turn():
    dashboard = Mock()
    dashboard.should_celebrate_pr.return_value = False
    snapshot = {'summaries': [{**STRENGTH, 'workout_id': 'one'}], 'totals': {}, 'status': 'ready'}
    display = {'rotation': ['latest_workouts'], 'last_workout_duration': 15,
               'last_workout_detail_interval': 4, 'overview_duration': 4}
    assert build_rotation_pages(snapshot, dashboard, display, 'R', 32)[0][2] == 4 * (1 + 3)
    assert build_rotation_pages(snapshot, dashboard, display, 'R', 64)[0][2] == 4 * (1 + 2)


def test_32_row_intro_shows_title_without_the_bar():
    matrix = frame(STRENGTH, 0.5)
    assert rows_of(matrix, HEART) == []
    white = rows_of(matrix, WHITE)
    assert white and white[-1] <= 31
    # "Full Body Strength" wraps to two lines on 64 px of 4x6 text.
    assert len({y // 7 for y in white}) >= 2


def test_32_row_stats_show_label_value_and_bar_without_overlap():
    for summary in demo_summaries() + [STRENGTH]:
        for turn, detail in enumerate(rotating_details(summary, 32)):
            matrix = frame(summary, 4 * (turn + 1) + 0.5)
            label = rows_of(matrix, GREY)
            assert label, (summary['discipline'], detail)
            heart = rows_of(matrix, HEART, range(0, 10))
            value = [y for y in rows_of(matrix, WHITE, range(12, 52)) if label[-1] < y < BAR_TOP]
            assert value, (summary['discipline'], detail)
            if heart:
                # A blank row must separate the value from the bar.
                assert heart[0] >= BAR_TOP
                assert value[-1] < BAR_TOP - 1, (summary['discipline'], detail['label'])


def test_32_row_long_instructor_name_keeps_caption_and_drops_bar():
    summary = {**STRENGTH, 'instructor': 'Jermaine Johnson'}
    matrix = frame(summary, 4.5)  # first stats turn is the instructor
    assert rows_of(matrix, GREY)
    assert rows_of(matrix, HEART) == []


@pytest.mark.parametrize('flag, columns', [('login_required', range(55, 64)),
                                           ('data_stale', range(0, 9))])
def test_32_row_bottom_title_line_clears_corner_icons(flag, columns):
    summary = {**STRENGTH, 'title': '45 min Advanced Power Zone Endurance Ride', flag: True}
    matrix = frame(summary, 0.5)
    assert [y for y in rows_of(matrix, WHITE, columns) if y >= 23] == []


def test_32_row_output_pr_star_stays_on_the_panel():
    summary = next(s for s in demo_summaries() if s.get('is_output_pr'))
    matrix = frame(summary, 4.5)  # total output is the first cycling stat
    gold = rows_of(matrix, (255, 215, 0))
    assert gold and gold[-1] < BAR_TOP
