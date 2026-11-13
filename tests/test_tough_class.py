"""Workout insights: a tough class. The rule (peloton/workout_insights.py), its board view (insight_lines) and the
frames (the pixel arrow in the bars frame's bottom line, display/ui/last_workout_screen.py)."""
import pytest

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.last_workout_screen import _good_view, insight_views, rotating_details
from peloton.insight_lines import GREEN, LINE_MAX, board_insights, board_view
from peloton.workout_insights import insights
from tests.test_insight_slide import lit, render_detail, view, with_views
from tests.test_insight_slide import demo_ride
from tests.test_workout_insights import codes, foot, ride, text

TOUGH = {'value': 124, 'usual': 188, 'unit': 'W', 'foot': False, 'noun': 'ride', 'n': 9, 'real': 9,
         'reason': None, 'difficulty': 9.1, 'usual_difficulty': 7.0}
ARROW = ['..#..', '...#.', '#####', '...#.', '..#..']


def tough(target_rating, peer_ratings, target_output=124, peer_output=188, **target_kw):
    target = ride(0, target_output, difficulty=target_rating, **target_kw)
    peers = [ride(1 + i, peer_output, difficulty=r) for i, r in enumerate(peer_ratings)]
    return insights(target, [target] + peers)


# The rule

def test_a_class_a_point_harder_replaces_the_output_insight():
    result = tough(9.1, [7.0] * 5)
    assert codes(result) == ['tough_class']
    assert text(result, 'tough_class') == 'Tough ride: rated 9.1 against your typical 7.0 for rides like this.'
    facts = result[0][2]
    assert (facts['difficulty'], facts['usual_difficulty'], facts['value'], facts['usual'], facts['n']) == \
        (9.1, 7.0, 124, 188, 5)


def test_the_threshold_is_exactly_one_point_over_the_median():
    assert codes(tough(8.1, [7.1] * 5)) == ['tough_class']      # 8.1 - 7.1 is 0.9999... in floating point
    assert codes(tough(8.0, [7.0] * 5)) == ['tough_class']
    assert codes(tough(7.99, [7.0] * 5)) == ['output_down']
    assert codes(tough(8.0, [7.0, 7.0, 7.0, 9.0, 9.0])) == ['tough_class']      # the median, not the mean


def test_an_easier_class_gets_nothing_about_the_class():
    assert codes(tough(5.5, [7.0] * 5)) == ['output_down']
    assert codes(tough(3.0, [7.0] * 5, target_output=190)) == ['in_line']


def test_a_tough_class_replaces_a_strong_or_in_line_output_too():
    assert codes(tough(9.1, [7.0] * 5, target_output=230)) == ['tough_class']
    assert codes(tough(9.1, [7.0] * 5, target_output=188)) == ['tough_class']


def test_a_tough_class_drops_the_effort_insight_with_the_output_one():
    t = ride(0, 124, difficulty=9.1, strive=30, dur=1200)
    peers = [ride(1 + i, 188, difficulty=7.0, strive=20 - i, dur=1200) for i in range(5)]
    assert codes(insights(t, [t] + peers)) == ['tough_class']


@pytest.mark.parametrize('rating', [None, 0, 11, -1, 'hard', True])
def test_a_class_without_a_usable_rating_is_not_tough(rating):
    assert codes(tough(rating, [7.0] * 5)) == ['output_down']


def test_peers_without_ratings_or_too_few_of_them_mean_no_tough_class():
    assert codes(tough(9.1, [7.0, 7.0, None, None, None])) == ['output_down']     # 2 rated: under MIN_RATED
    assert codes(tough(9.1, [7.0, 7.0, 7.0, None, 'x'])) == ['tough_class']       # 3 rated is enough
    assert codes(tough(9.1, [None] * 5)) == ['output_down']


def test_a_tough_class_needs_the_output_figures_behind_it():
    assert codes(tough(9.1, [7.0] * 4)) == ['too_few']                           # under MIN_PEERS


def test_a_tough_run_keeps_its_speed():
    target = foot(0, 4.0, difficulty=9.0)
    result = insights(target, [target] + [foot(i, 5.0, difficulty=7.0) for i in range(1, 6)])
    assert codes(result) == ['tough_class']
    assert (result[0][2]['unit'], result[0][2]['foot']) == ('mph', True)
    assert result[0][1].startswith('Tough run: rated 9.0 against your typical 7.0 for runs')


# The board view

def test_the_view_is_the_chosen_mock_up():
    v = board_view('tough_class', TOUGH)
    assert v['colour'] == list(GREEN) and v['headline'] == 'TOUGH CLASS'
    assert v['lines64'] == ['WAY TO CHALLENGE', 'YOURSELF!', 'YOU TOOK ON A', '9.1 CLASS, YOUR', 'TYPICAL IS 7.0.']
    assert v['pages32'] == [['WAY TO', 'CHALLENGE', 'YOURSELF!']]
    assert v['footer'] == '9 SIMILAR RIDES'
    assert v['reason'] == '9.1 TO USUALLY 7.0' and v['reason_parts'] == ['9.1', 'arrow', 'USUALLY 7.0']
    assert (v['figure']['today_text'], v['figure']['usual_text'], v['figure']['unit']) == ('124', '188', 'W')
    run = board_view('tough_class', {**TOUGH, 'unit': 'mph', 'value': 4.0, 'usual': 5.0, 'foot': True})
    assert (run['figure']['today_text'], run['figure']['unit']) == ('4.0', 'MPH')


def test_a_ten_point_oh_class_still_fits_five_lines():
    v = board_view('tough_class', {**TOUGH, 'difficulty': 10.0})
    assert v['lines64'][3:] == ['10.0 CLASS.', 'TYPICAL 7.0.']
    # the bottom line draws `10`: `10.0 → USUALLY 9.0` would overrun and the frame would be dropped
    worst = board_view('tough_class', {**TOUGH, 'difficulty': 10.0, 'usual_difficulty': 9.0})
    assert worst['reason_parts'] == ['10', 'arrow', 'USUALLY 9.0'] and _good_view(worst)
    assert insight_views({'insights': [worst]}) == [worst]


@pytest.mark.parametrize('height', (64, 32))
def test_every_line_fits_the_font_with_tread_bootcamp(height):
    initialize_fonts(height)
    font = loaded_fonts['stats']
    for noun, unit, n in (('bootcamp', 'mph', 12), ('ride', 'W', 9)):
        v = board_view('tough_class', {**TOUGH, 'noun': noun, 'unit': unit, 'foot': unit == 'mph', 'n': n, 'real': n})
        assert get_text_width(font, v['lines64'][0]) == 64                  # the one line allowed edge to edge
        for line in v['lines64'][1:] + v['pages32'][0] + [v['headline'], v['footer']]:
            assert len(line) <= LINE_MAX and get_text_width(font, line) <= 60, line
        # '9.1', a gap, the 5 px arrow, a gap and 'USUALLY 7.0' end at column 63
        assert 1 + get_text_width(font, '9.1') + 7 + get_text_width(font, 'USUALLY 7.0') <= 64
    assert board_view('tough_class', {**TOUGH, 'noun': 'bootcamp', 'n': 12, 'real': 12})['footer'] == 'VS 12 SIMILAR'


def test_missing_or_bad_facts_give_no_view():
    assert board_view('tough_class', {k: v for k, v in TOUGH.items() if k != 'difficulty'}) is None
    assert board_view('tough_class', {k: v for k, v in TOUGH.items() if k != 'usual_difficulty'}) is None
    assert board_view('tough_class', {**TOUGH, 'difficulty': 'hard'}) is None


def test_a_real_tough_class_makes_its_view_from_its_own_facts():
    v = board_insights(tough(9.1, [7.0] * 5))[0]
    assert v['code'] == 'tough_class' and v['reason_parts'] == ['9.1', 'arrow', 'USUALLY 7.0']
    assert v['footer'] == '5 SIMILAR RIDES'


# The frames

def arrow_pixels(matrix, rows):
    """The lit pixels of columns 13-17 (the arrow's) in `rows`, as 5 strings."""
    pixels = matrix.image.load()
    return [''.join('#' if pixels[x, y] == GREEN else '.' for x in range(13, 18)) for y in rows]


@pytest.mark.parametrize('height, baseline', [(64, 61), (32, 30)])
def test_the_bars_frame_draws_the_arrow_in_pixels(height, baseline):
    matrix = render_detail(with_views(demo_ride(), board_view('tough_class', TOUGH)), height, 'insight_bars')
    pixels = matrix.image.load()
    lit_at = lambda x, y: pixels[x, y] != (0, 0, 0)
    line = range(baseline - 6, baseline + 2)
    # On the text's own rows (its ink is baseline-5 to baseline-1), not a row below them.
    text_rows = [y for y in line if any(lit_at(x, y) for x in range(1, 11))]
    assert text_rows == list(range(baseline - 5, baseline))
    assert arrow_pixels(matrix, text_rows) == ARROW
    # Centred between the inks: 9.1 ends at column 10, USUALLY starts at 20, 2 dark columns each side.
    assert any(lit_at(10, y) for y in line) and any(lit_at(20, y) for y in line)
    for x in (11, 12, 18, 19):
        assert not any(lit_at(x, y) for y in line), x
    assert lit(matrix, GREEN, text_rows, range(1, 11))                              # 9.1 from column 1
    assert lit(matrix, (200, 205, 215), text_rows, range(20, 64))                   # USUALLY 7.0
    assert not any(lit_at(0, y) for y in line)


@pytest.mark.parametrize('height, baseline', [(64, 61), (32, 30)])
@pytest.mark.parametrize('rating, usual', [(9.1, 7.0), (9.0, 7.0), (8.7, 7.1), (10.0, 9.0)])
def test_the_arrow_is_centred_whatever_digit_the_rating_ends_in(height, baseline, rating, usual):
    """The 1 has 2 px of ink, every other digit 3: the arrow keeps 2 dark columns each side either way."""
    v = board_view('tough_class', {**TOUGH, 'difficulty': rating, 'usual_difficulty': usual})
    matrix = render_detail(with_views(demo_ride(), v), height, 'insight_bars')
    pixels = matrix.image.load()
    rows = range(baseline - 5, baseline)
    columns = [x for x in range(64) if any(pixels[x, y] != (0, 0, 0) for y in rows)]
    arrow = [x for x in columns if any(pixels[x, y] == GREEN for y in rows) and
             [''.join('#' if pixels[c, y] == GREEN else '.' for c in range(x, x + 5)) for y in rows] == ARROW]
    assert len(arrow) == 1, columns
    start = arrow[0]
    left = max(x for x in columns if x < start)
    right = min(x for x in columns if x > start + 4)
    assert (start - left - 1, right - start - 5) == (2, 2)
    assert max(columns) <= 63


def test_the_card_and_words_page_show_the_cheer():
    ride_summary = with_views(demo_ride(), board_view('tough_class', TOUGH))
    card = render_detail(ride_summary, 64, 'insight_card')
    assert lit(card, (200, 205, 215), range(14, 27), range(64))
    assert lit(card, GREEN, range(28, 50), range(64))                       # the class figures
    words = render_detail(ride_summary, 32, 'insight_words', page=0)
    assert lit(words, (200, 205, 215), range(10, 31), range(64))
    assert [d.get('kind') for d in rotating_details(ride_summary, 32)][-2:] == ['insight_bars', 'insight_words']


def test_damaged_reason_parts_skip_the_view():
    good = board_view('tough_class', TOUGH)
    assert _good_view(good)
    for parts in (['9.1', 'arrow', 'arrow'], [], 'x', [1, 2], ['', 'arrow'], ['A' * 15, 'arrow', 'B' * 15],
                  ['a', 'b', 'c', 'd']):
        assert not _good_view({**good, 'reason_parts': parts}), parts
    assert _good_view({**good, 'reason_parts': None})
    assert insight_views({'insights': [{**good, 'reason_parts': ['x'] * 4}, good]}) == [good]


def test_a_view_without_parts_still_draws_its_reason_line():
    matrix = render_detail(with_views(demo_ride(), view('output_down', reason='easier')), 64, 'insight_bars')
    assert lit(matrix, (200, 205, 215), range(54, 62), range(64))
