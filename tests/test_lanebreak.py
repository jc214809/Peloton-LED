"""Lanebreak workouts: named on the workout page and the PR card, since the title is only the track."""

import pytest

import display.ui.pr_celebration as pr
from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.last_workout.screen import LastWorkoutScreen
from display.ui.last_workout.stats import page_heading
from display.ui.pr_celebration import pr_turns
from peloton.stats.summaries import is_lanebreak, summarize_workout
from scripts.render_demo import ImageMatrix

PLACEHOLDER = {'name': 'LANEBREAK', 'image_url': 'https://s3.amazonaws.com/peloton-ride-images/odyssey-instructor.png'}


def lanebreak(name='Lanebreak Walk', discipline='walking', title='15 min Pop Punk'):
    """Shaped like Joel's first Tread Lanebreak (2026-11-23); the bike's differ only in name, discipline and title."""
    return {
        'id': 'df62d7cb',
        'name': name,
        'title': title,
        'status': 'COMPLETE',
        'fitness_discipline': discipline,
        'workout_type': 'freestyle',
        'start_time': 1795480902,
        'end_time': 1795481809,
        'timezone': 'America/New_York',
        'total_work': 110101.37,
        'is_total_work_personal_record': True,
        'ride': {'id': '0' * 32, 'title': title, 'duration': 907, 'instructor': dict(PLACEHOLDER)},
    }


CLASS = {
    'id': 'c1',
    'name': 'Walking Workout',
    'fitness_discipline': 'walking',
    'status': 'COMPLETE',
    'start_time': 1795480902,
    'ride': {'id': 'r1', 'title': '20 min Walk', 'instructor': {'id': 'i1', 'name': 'Jess Sims'}},
}


@pytest.mark.parametrize(
    'workout',
    [
        lanebreak(),
        lanebreak('Lanebreak Ride', 'cycling', '20 min Red Hot Chili Peppers Vol. 2'),
        lanebreak(name=None),  # the placeholder instructor alone
        lanebreak(name='lanebreak walk') | {'ride': {}},  # the name alone
    ],
)
def test_a_lanebreak_is_known_by_its_name_or_placeholder_instructor(workout):
    assert is_lanebreak(workout)


@pytest.mark.parametrize(
    'workout',
    [
        CLASS,
        {},
        {'name': 'Just Walk', 'ride': {'instructor': {'name': 'Just Walk'}}},
        # An instructor with an ID is a real one, whatever the name says.
        {'ride': {'instructor': {'id': 'i9', 'name': 'Lanebreak'}}},
    ],
)
def test_anything_else_is_not_a_lanebreak(workout):
    assert not is_lanebreak(workout)


def test_only_a_lanebreak_summary_carries_the_flag():
    summary = summarize_workout(lanebreak())
    assert summary['lanebreak'] is True
    assert summary['title'] == '15 min Pop Punk' and summary['instructor'] == '' and summary['discipline'] == 'Walking'
    # Absent, not False, elsewhere: other summaries and the cache's bytes stay as they were.
    assert 'lanebreak' not in summarize_workout(CLASS)


@pytest.mark.parametrize(
    'discipline, heading',
    [('Cycling', 'Bike Lanebreak'), ('Walking', 'Tread Lanebreak'), ('Running', 'Tread Lanebreak'), ('Rowing', 'Lanebreak')],
)
def test_the_heading_says_which_lanebreak_it_was(discipline, heading):
    # Joel, 2026-11-24: tie it to the machine, as Bike / Tread Bootcamp do.
    assert page_heading({'lanebreak': True}, discipline) == heading


@pytest.mark.parametrize('flag', [None, 'yes', 1, False])
def test_the_heading_is_a_lanebreak_only_for_a_true_flag(flag):
    # The cache can hold anything: only a real True renames the page.
    assert page_heading({'lanebreak': flag}, 'Walking') == 'Walking'


def page(summary, height):
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    screen = LastWorkoutScreen()
    screen.on_enter(matrix, summary)
    screen.update(0.5)
    assert screen.render(matrix, summary)
    return matrix.image


def header_rows(height):
    return range(0, 14 if height == 64 else 8)


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('discipline', ['walking', 'cycling'])
def test_the_page_names_a_lanebreak_in_its_disciplines_colour_inside_the_panel(height, discipline):
    summary = summarize_workout(lanebreak(discipline=discipline))
    plain = {k: v for k, v in summary.items() if k != 'lanebreak'}
    named, unnamed = page(summary, height), page(plain, height)
    rows = header_rows(height)
    lit = {(x, y) for y in rows for x in range(64) if named.getpixel((x, y)) != (0, 0, 0)}
    assert lit and min(x for x, _ in lit) >= 1 and max(x for x, _ in lit) <= 62
    assert lit != {(x, y) for y in rows for x in range(64) if unnamed.getpixel((x, y)) != (0, 0, 0)}
    # Same colour as the discipline's own header.
    assert {named.getpixel(p) for p in lit} == {unnamed.getpixel((x, y)) for y in rows for x in range(64)} - {(0, 0, 0)}


def test_the_pr_card_names_a_lanebreak_and_calls_it_no_class():
    summary = summarize_workout(lanebreak()) | {'total_output_kj': 110.0, 'duration_min': 15}
    assert pr_turns(summary)[0][2] == [(pr._BLUE, ['15 MIN'])]
    assert pr._discipline(summary) == ('TREAD LANEBREAK', pr._discipline({'discipline': 'Walking'})[1])
    bike = summarize_workout(lanebreak('Lanebreak Ride', 'cycling'))
    assert pr._discipline(bike) == ('BIKE LANEBREAK', pr._discipline({'discipline': 'Cycling'})[1])
    plain = {k: v for k, v in summary.items() if k != 'lanebreak'}
    assert pr_turns(plain)[0][2] == [(pr._BLUE, ['15 MIN CLASS', '15 MIN'])]
    assert pr._discipline(plain)[0] == 'WALKING'


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('discipline', ['walking', 'cycling'])
def test_the_pr_card_fits_a_lanebreak(height, discipline, monkeypatch):
    monkeypatch.setattr(pr, 'draw_confetti', lambda matrix, elapsed: None)
    summary = summarize_workout(lanebreak(discipline=discipline)) | {'total_output_kj': 110.0, 'duration_min': 15}
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    screen = pr.PrCelebrationScreen(detail_interval=4.0)
    screen.on_enter(matrix, summary)
    screen.update(pr.INTRO_SECONDS + 0.5)
    assert screen.render(matrix, summary)
    lit = [(x, y) for y in range(height) for x in range(64) if matrix.image.getpixel((x, y)) != (0, 0, 0)]
    assert lit and min(x for x, _ in lit) >= 0 and max(x for x, _ in lit) <= 63
    # 32 rows put the name right of the trophy, ending at the panel's edge when it must (`short_line_x`):
    # TREAD LANEBREAK is 60 px in the 4x6 font, as wide as OUTDOOR WALKING, so it runs to column 63, uncut.
    if height < 64:
        name, font = pr._discipline(summary)[0], loaded_fonts['info']
        x = pr.short_line_x(font, name)
        assert x >= 0 and x + get_text_width(font, name) - 1 <= 64
