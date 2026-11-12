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


ONE_LINE = {**STRENGTH, 'title': '30 min Pop Ride', 'instructor': 'Ben Alldis'}


def test_32_row_intro_with_a_one_line_title_shows_the_bar_even_with_stats():
    # Regression: the bar was left off the intro whenever the workout had stats to rotate through.
    assert rotating_details(ONE_LINE, 32)
    matrix = frame(ONE_LINE, 0.5)
    heart = rows_of(matrix, HEART)
    assert heart and heart[0] >= BAR_TOP and heart[-1] <= 31
    # Title (baseline 22) and bar are separated by a blank row.
    title = [y for y in rows_of(matrix, WHITE) if y < BAR_TOP]
    assert title and title[-1] < BAR_TOP - 1
    assert rows_of(matrix, WHITE, range(32, 64))[-1] >= 30  # calories on the bottom rows


@pytest.mark.parametrize('missing, shown', [('calories', 'hr_avg'), ('hr_avg', 'calories')])
@pytest.mark.parametrize('elapsed', [0.5, 4.5])
def test_32_row_bar_shows_whichever_of_hr_and_calories_exists(missing, shown, elapsed):
    summary = {**ONE_LINE, missing: None}
    matrix = frame(summary, elapsed)
    heart = rows_of(matrix, HEART)
    left = [y for y in rows_of(matrix, WHITE, range(0, 20)) if y >= BAR_TOP]
    right = [y for y in rows_of(matrix, WHITE, range(32, 64)) if y >= BAR_TOP]
    assert bool(heart) == (shown == 'hr_avg')
    assert bool(left) == (shown == 'hr_avg')
    assert bool(right) == (shown == 'calories')


@pytest.mark.parametrize('elapsed', [0.5, 4.5])
def test_32_row_bar_is_absent_without_hr_or_calories(elapsed):
    matrix = frame({**ONE_LINE, 'hr_avg': None, 'calories': None}, elapsed)
    assert rows_of(matrix, HEART) == []
    assert [y for y in rows_of(matrix, WHITE) if y >= BAR_TOP] == []


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


def test_32_row_comma_in_a_long_row_distance_leaves_a_blank_row_above_the_bar():
    # 6x9's comma hangs below the baseline; the value is lifted a row so it doesn't touch the bar.
    summary = {'discipline': 'Rowing', 'title': '45 min Row', 'duration_min': 45, 'distance': 3929.83,
               'distance_unit': 'm', 'calories': 300, 'hr_avg': 130}
    turn = [d['label'] for d in rotating_details(summary, 32)].index('distance')
    matrix = frame(summary, 4 * (turn + 1) + 0.5)
    value = [y for y in rows_of(matrix, WHITE, range(12, 52)) if rows_of(matrix, GREY)[-1] < y < BAR_TOP]
    assert value and value[-1] < BAR_TOP - 1


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


def test_32_row_instructor_name_is_drawn_the_same_with_or_without_corner_icons():
    # The icons may cover the name's ends; the name itself never changes to dodge them.
    name = 'Leanne Hainsby-Alldis'
    plain = frame({**STRENGTH, 'instructor': name}, 4.5)
    for flags in ({'login_required': True}, {'data_stale': True}, {'login_required': True, 'data_stale': True}):
        assert frame({**STRENGTH, 'instructor': name, **flags}, 4.5).image.tobytes() == plain.image.tobytes()


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


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('total, big', [('2,126', True), ('123,456,789', False)])
def test_username_total_workouts_is_big_and_gold_when_it_fits(height, total, big):
    from display.ui.username import UsernameScreen
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    screen = UsernameScreen()
    state = {'username': 'Joel', 'details': [
        {'label': 'TOTAL WORKOUTS', 'lines': [total], 'font_key': 'big', 'color_key': 'gold'}]}
    screen.on_enter(matrix, state)
    screen.update(0.5)
    assert screen.render(matrix, state)
    gold = rows_of(matrix, (255, 215, 0))
    assert gold and gold[0] > rows_of(matrix, GREY)[-1] and gold[-1] < height
    # Too wide for the big font: falls back to the normal value line, still gold.
    assert (gold[-1] - gold[0] + 1 > 7) is big


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


def test_32_row_goal_screen_says_what_it_counts():
    state = {'title': 'Weekly Goal', 'current': 2, 'target': 5, 'unit': 'workouts'}
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
    # Title, value, unit and the progress bar.
    assert len(bands) == 4
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


@pytest.mark.parametrize('title,expected', [
    ('60 min 11 sec Just Walk', 'Just Walk'),           # was "11 sec Just Walk"
    ('41 sec Just Walk', 'Just Walk'),                  # was left whole
    ('162 min 49 sec Outdoor Walking', 'Outdoor Walking'),
    ('20 min HIIT Ride', 'HIIT Ride'),
    ('45 Min Power Zone Endurance Ride', 'Power Zone Endurance Ride'),
    ('30 minutes Full Body', 'Full Body'),
    ('10 min', '10 min'),                               # nothing but the length: kept
    ('Minimalist Flow', 'Minimalist Flow'),
    ('5 Minute Mindset', 'Mindset'),                    # the old pattern left "ute Mindset"
    ('', ''), (None, ''),
])
def test_titles_lose_the_length_the_page_shows(title, expected):
    from display.ui.last_workout_screen import title_without_length
    assert title_without_length(title) == expected
