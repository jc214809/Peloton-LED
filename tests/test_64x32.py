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
            if detail.get('kind'):
                continue  # graph and zone slides have no label/value pair
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


def test_32_row_username_detail_lines_have_a_blank_row_between_them():
    from display.ui.username import UsernameScreen
    matrix = ImageMatrix(height=32)
    initialize_fonts(32)
    screen = UsernameScreen()
    state = {'username': 'Joel', 'details': [
        {'label': 'THIS WEEK', 'lines': ['2 WORKOUTS', '35 MINUTES']}]}
    screen.on_enter(matrix, state)
    screen.update(0.5)
    assert screen.render(matrix, state)
    white = [y for y in rows_of(matrix, WHITE) if y > rows_of(matrix, GREY)[-1]]
    gaps = [b - a for a, b in zip(white, white[1:]) if b - a > 1]
    assert gaps, 'the two value lines run together'
    assert white[-1] <= 31


def test_32_row_two_line_discipline_name_clears_the_count():
    from display.ui.discipline_page import DisciplinePageScreen
    matrix = ImageMatrix(height=32)
    initialize_fonts(32)
    assert DisciplinePageScreen().render(matrix, {'discipline': 'Tread Bootcamp', 'count': 112,
                                                  'color_key': 'white'})
    lit = rows_of(matrix, WHITE)
    # The wrapped name's descenders ("p") used to sit one row above the count.
    gaps = [b - a - 1 for a, b in zip(lit, lit[1:]) if b - a > 1]
    assert len(gaps) == 2 and gaps[-1] >= 3


@pytest.mark.parametrize('state', [
    {'title': 'Weekly Goal', 'current': 2, 'target': 5, 'unit': 'workouts'},
    {'title': 'Milestone', 'current': 2000, 'target': 2000, 'unit': 'Total Workouts', 'milestone': True}])
def test_32_row_goal_screens_say_what_they_count(state):
    from display.display import loaded_fonts, get_text_width
    from display.ui.goal_screen import GoalScreen
    matrix = ImageMatrix(height=32)
    initialize_fonts(32)
    assert GoalScreen().render(matrix, state)
    # The unit is drawn in the small font on its own band; find its rows.
    lit = sorted({y for y in range(32) for x in range(64) if matrix.image.getpixel((x, y)) != (0, 0, 0)
                  and matrix.image.getpixel((x, y)) != (35, 35, 35)})
    bands = [[lit[0]]]
    for y in lit[1:]:
        (bands[-1].append(y) if y - bands[-1][-1] == 1 else bands.append([y]))
    # Title, value, unit (and the progress bar for weekly goals).
    assert len(bands) == (3 if state.get('milestone') else 4)
    assert bands[-1][-1] <= 31


def test_32_row_workout_without_stats_shows_hr_in_intro():
    summary = {'discipline': 'Meditation', 'title': '10 min Calm', 'duration_min': 10,
               'hr_avg': 70, 'calories': 20}
    assert rotating_details(summary, 32) == []
    assert rows_of(frame(summary, 0.5), HEART)


def test_32_row_lifetime_uses_icon_pages_of_two():
    from display.ui.lifetime_overview import LifetimeOverviewScreen
    totals = {'Total Workouts': 100, 'Cycling': 40, 'Running': 30, 'Strength': 20, 'Yoga': 10,
              'Rowing': 5}
    snapshot = {'summaries': [], 'totals': totals, 'status': 'ready'}
    display = {'rotation': ['lifetime'], 'last_workout_duration': 15, 'overview_duration': 5,
               'color': 'white'}
    pages = build_rotation_pages(snapshot, Mock(), display, 'R', 32)
    assert [name for name, _, _ in pages] == ['lifetime'] * 3
    assert [len(state['items']) for _, state, _ in pages] == [2, 2, 1]
    assert len(build_rotation_pages(snapshot, Mock(), display, 'R', 64)) == 2

    matrix = ImageMatrix(height=32)
    initialize_fonts(32)
    assert LifetimeOverviewScreen().render(matrix, pages[1][1])
    # Current-page dot is on the bottom row, not off the panel at row 63.
    assert WHITE in [matrix.image.getpixel((x, 31)) for x in range(64)]


@pytest.mark.parametrize('height', [32, 64])
def test_pr_is_marked_with_a_trophy_on_both_boards(height):
    summary = next(s for s in demo_summaries() if s.get('is_output_pr'))
    base = (205, 145, 0)  # the trophy's stem/base; nothing else uses this color
    intro = frame(summary, 0.5, height)
    assert rows_of(intro, base, range(48, 64)), 'corner trophy missing in the intro'
    output = frame(summary, 4.5, height)  # total output is the first cycling stat
    assert rows_of(output, base), 'trophy missing beside the PR output value'
    later = frame(summary, 8.5, height)  # strive score: no PR trophy
    assert rows_of(later, base) == []


@pytest.mark.parametrize('height', [32, 64])
def test_startup_logo_is_peloton_red(height):
    from display.ui.logo_mask_screen import LogoMaskScreen, PELOTON_RED
    matrix = ImageMatrix(height=height)
    assert LogoMaskScreen().render(matrix)
    colors = {c for _, c in matrix.image.getcolors(64 * 64)}
    assert colors == {(0, 0, 0), PELOTON_RED}
