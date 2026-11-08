"""The celebration splash: ordinals, nouns, trophy and confetti, the text, and its place in the rotation."""
import json
from unittest.mock import Mock

import pytest

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.celebration_screen import (INTRO_SECONDS, MIN_CARD_SECONDS, RISE_SECONDS, TEXT_LEFT_32,
                                           CelebrationScreen, milestone_noun, number_text, ordinal)
from peloton.cache import CACHE_VERSION, load_snapshot
import peloton_led
from peloton_led import build_rotation_pages, run_display_loop
from scripts.render_demo import ImageMatrix
from scripts.render_rotation import frame_times

GOLD, WHITE, BLUE = (255, 215, 0), (255, 255, 255), (0, 120, 255)
STATE = {'number': 600, 'noun': 'WORKOUT', 'subtitle': 'Joel'}


@pytest.mark.parametrize('number, expected', [
    (1, '1ST'), (2, '2ND'), (3, '3RD'), (4, '4TH'), (11, '11TH'), (12, '12TH'), (13, '13TH'),
    (21, '21ST'), (22, '22ND'), (23, '23RD'), (100, '100TH'), (101, '101ST'), (111, '111TH'),
    (112, '112TH'), (600, '600TH'), (1002, '1002ND'), (0, '0TH')])
def test_ordinals(number, expected):
    assert ordinal(number) == expected


def test_number_text_skips_what_is_not_a_count():
    assert number_text(600) == '600TH'
    for bad in (None, '600', True, -1, 2.5):
        assert number_text(bad) == ''


@pytest.mark.parametrize('discipline, noun', [
    (None, 'WORKOUT'), ('', 'WORKOUT'), ('cycling', 'RIDE'), ('Cycling', 'RIDE'), ('bike_bootcamp', 'RIDE'),
    ('running', 'RUN'), ('walking', 'WALK'), ('rowing', 'ROW'), ('caesar', 'ROW'),
    ('caesar_bootcamp', 'ROW'), ('strength', 'CLASS'), ('yoga', 'CLASS')])
def test_milestone_noun_by_discipline(discipline, noun):
    assert milestone_noun(discipline) == noun


def _render(height, elapsed, state):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    screen = CelebrationScreen()
    screen.on_enter(matrix, state)
    screen.update(elapsed)
    assert screen.render(matrix, state)
    return matrix.image


def _lit(image, color=None):
    return {(x, y) for y in range(image.height) for x in range(image.width)
            if image.getpixel((x, y)) != (0, 0, 0) and (color is None or image.getpixel((x, y)) == color)}


TROPHY_GOLD = (230, 170, 0)


def _lit_colors(image):
    raw = image.tobytes()
    return {tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)}


def _text_box(image, color):
    pixels = _lit(image, color)
    xs, ys = [x for x, _ in pixels], [y for _, y in pixels]
    return min(xs), min(ys), max(xs), max(ys)


@pytest.mark.parametrize('height', [32, 64])
def test_trophy_rises_through_confetti_before_the_text(height):
    start, risen = _render(height, 0.0, STATE), _render(height, RISE_SECONDS, STATE)
    # The trophy starts below the panel and rises; confetti falls from the first frame.
    assert not _lit(start, TROPHY_GOLD) and _lit(risen, TROPHY_GOLD)
    assert len(_lit(start)) > 10
    before = _render(height, INTRO_SECONDS - 0.05, STATE)
    assert not _lit(before, WHITE) and not _lit(before, BLUE)
    # Repeatable: the same moment draws the same frame.
    assert _render(height, 1.2, STATE).tobytes() == _render(height, 1.2, STATE).tobytes()


@pytest.mark.parametrize('height', [32, 64])
def test_confetti_keeps_moving_and_never_lands_on_the_text(height):
    frames = [_render(height, INTRO_SECONDS + i * 0.05, STATE) for i in range(40)]
    assert len({f.tobytes() for f in frames}) > 30
    confetti = {(255 * 4 // 5, 60 * 4 // 5, 60 * 4 // 5)}  # any confetti colour would do: red here
    for frame in frames:
        for color in (WHITE, BLUE):
            x0, y0, x1, y1 = _text_box(frame, color)
            inside = {frame.getpixel((x, y)) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
            assert inside <= {(0, 0, 0), color}, (color, inside - {(0, 0, 0), color})
    assert any(confetti & _lit_colors(f) for f in frames)


def test_64_row_lines_under_the_trophy_in_order():
    image = _render(64, INTRO_SECONDS + 0.1, STATE)
    trophy = sorted({y for _, y in _lit(image, TROPHY_GOLD)})
    white = sorted({y for _, y in _lit(image, WHITE)})
    gold = sorted({y for _, y in _lit(image, GOLD)})
    blue = sorted({y for _, y in _lit(image, BLUE)})
    # Trophy, then 600TH (white), WORKOUT (gold) and the name (blue), all on the panel.
    assert trophy[-1] < white[0] and white[-1] < gold[0] and gold[-1] < blue[0] and blue[-1] <= 63


def test_32_row_text_sits_beside_the_trophy_with_the_name_on_top():
    image = _render(32, INTRO_SECONDS + 0.1, STATE)
    trophy_right = max(x for x, _ in _lit(image, TROPHY_GOLD))
    for color in (WHITE, GOLD, BLUE):
        assert min(x for x, _ in _lit(image, color)) > trophy_right
    assert _text_box(image, BLUE)[3] < _text_box(image, WHITE)[1]
    assert _text_box(image, WHITE)[3] < _text_box(image, GOLD)[1] and _text_box(image, GOLD)[3] <= 31


@pytest.mark.parametrize('number', [600, 2000, 10000, 123456])
@pytest.mark.parametrize('height', [32, 64])
def test_number_always_fits_inside_the_panel(height, number):
    image = _render(height, INTRO_SECONDS + 0.1, {**STATE, 'number': number})
    xs = [x for x, _ in _lit(image, WHITE)]
    left = TEXT_LEFT_32 if height < 64 else 0
    assert xs and min(xs) >= left and max(xs) <= 63
    # On 64 columns, up to four digits keep the big font.
    if number < 10000:
        assert get_text_width(loaded_fonts['big'], ordinal(number)) <= 62


@pytest.mark.parametrize('height', [32, 64])
def test_a_name_too_long_to_fit_is_left_off(height):
    image = _render(height, INTRO_SECONDS + 0.1, {**STATE, 'subtitle': 'Christopher Longname-Smith'})
    assert not _lit(image, BLUE) and _lit(image, WHITE)


def test_without_a_number_the_headline_takes_the_big_line():
    image = _render(64, INTRO_SECONDS + 0.1, {'headline': 'Goal hit', 'noun': '5 workouts'})
    assert _lit(image, WHITE) and _lit(image, GOLD) and not _lit(image, BLUE)
    for state in (None, {}):
        assert _lit(_render(64, INTRO_SECONDS + 0.1, state), WHITE)  # CONGRATS by default


def _display(**changes):
    return {'rotation': ['username', 'milestones', 'goals'], 'duration': 4, 'last_workout_duration': 15,
            'overview_duration': 5, 'milestones': [100, 500], 'milestone_step': 0, 'color': 'white',
            **changes}


def _snapshot():
    return {'summaries': [], 'totals': {'Total Workouts': 600}, 'status': 'ready'}


def test_rotation_leads_with_the_newest_milestone_only():
    dashboard = Mock()
    dashboard.pending_milestones.return_value = [100, 500]
    pages = build_rotation_pages(_snapshot(), dashboard, _display(), 'Joel', 64)
    assert [name for name, _, _ in pages] == ['celebration', 'username']
    name, state, duration = pages[0]
    assert state == {'number': 500, 'noun': 'WORKOUT', 'subtitle': 'Joel', 'milestone': 500}
    # Long enough for the trophy and a readable card.
    assert duration == INTRO_SECONDS + MIN_CARD_SECONDS
    long = build_rotation_pages(_snapshot(), dashboard,
                                _display(screen_durations={'milestones': 20}), 'Joel', 64)
    assert long[0][2] == 20
    off = build_rotation_pages(_snapshot(), dashboard,
                               _display(screen_durations={'milestones': 0}), 'Joel', 64)
    assert off[0][2] == 0


def test_rotation_has_no_celebration_when_none_pending_or_section_off():
    dashboard = Mock()
    dashboard.pending_milestones.return_value = []
    assert 'celebration' not in [p[0] for p in build_rotation_pages(_snapshot(), dashboard, _display(), 'J', 64)]
    dashboard.pending_milestones.return_value = [500]
    without = _display(rotation=['username'])
    assert 'celebration' not in [p[0] for p in build_rotation_pages(_snapshot(), dashboard, without, 'J', 64)]
    unset = _display(milestones=[], milestone_step=0)
    assert 'celebration' not in [p[0] for p in build_rotation_pages(_snapshot(), dashboard, unset, 'J', 64)]


def test_display_loop_acknowledges_the_celebration_after_showing_it():
    dashboard = Mock(login_required=False)
    dashboard.snapshot.return_value = {'me': {'username': 'Rider'}, **_snapshot()}
    dashboard.pending_milestones.return_value = [500]
    manager = Mock()
    run_display_loop(manager, dashboard, _display(duration=0, overview_duration=0,
                                                  screen_durations={'milestones': 0}), cycles=1)
    assert manager.show.call_args_list[0].args[0] == 'celebration'
    dashboard.acknowledge_milestone.assert_called_once_with(500)


def test_preview_captures_the_rise_and_the_card():
    times = frame_times('celebration', {}, 8, 4)
    assert times[-1] > INTRO_SECONDS > times[0]


def _cache(tmp_path, **changes):
    snapshot = {'me': {'id': 'u'}, 'totals': {}, 'summaries': [], 'last_updated': 1.0, **changes}
    path = tmp_path / 'cache.json'
    path.write_text(json.dumps({'version': CACHE_VERSION, 'snapshot': snapshot}))
    return path


def test_celebration_clock_loads_and_a_damaged_one_is_dropped_not_the_cache(tmp_path):
    assert load_snapshot(_cache(tmp_path, milestone_shown_at={'600': 12.5}))['milestone_shown_at'] == {'600': 12.5}
    for bad in ([], {'x': 1.0}, {'600': 'soon'}, {'600': True}):
        snapshot = load_snapshot(_cache(tmp_path, milestone_shown_at=bad))
        assert snapshot is not None and 'milestone_shown_at' not in snapshot


def test_show_and_wait_ticks_faster_for_the_confetti(monkeypatch):
    sleeps = []
    clock = iter(range(1000))
    monkeypatch.setattr(peloton_led.time, 'monotonic', lambda: next(clock) * 0.05)
    monkeypatch.setattr(peloton_led.time, 'sleep', sleeps.append)
    monkeypatch.setattr(peloton_led, 'shown_pin', lambda: None)
    manager = Mock(current=CelebrationScreen())
    peloton_led.show_and_wait(manager, 'celebration', STATE, 0.5)
    assert sleeps and max(sleeps) <= 0.05
    # Other screens keep the usual tick, and a bad value can't stall or spin the loop.
    for current in (None, Mock(), Mock(frame_seconds=0), Mock(frame_seconds=True), Mock(frame_seconds=5)):
        assert peloton_led._tick_seconds(Mock(current=current)) == peloton_led.TICK_SECONDS


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('number', [600, 21, 102, 10000])
def test_ordinal_ending_is_small_and_raised_to_the_top_of_the_digits(height, number):
    from display.ui.celebration_screen import _CAP_HEIGHTS, _ordinal_line
    initialize_fonts(height)
    digits_font = loaded_fonts['big']
    suffix_font = loaded_fonts['titles' if height >= 64 else 'info']
    for font in (digits_font, suffix_font):
        assert (font.height, font.baseline) in _CAP_HEIGHTS  # the board's fonts are all measured
    left = TEXT_LEFT_32 if height < 64 else 0
    parts = _ordinal_line(number, [digits_font], suffix_font, 30, (255, 255, 255), left, 64)
    (_, dx, dy, _, digits), (_, sx, sy, _, suffix) = parts
    assert (digits, suffix) == (str(number), ordinal(number)[len(str(number)):])
    assert sx > dx + get_text_width(digits_font, digits) and sy < dy  # after the digits, raised
    # Drawn: the ending's top row is the digits' top row, and it ends well above their baseline.
    image = _render(height, INTRO_SECONDS + 0.1, {**STATE, 'number': number})
    white = _lit(image, WHITE)
    digit_rows = {y for x, y in white if x < sx}
    suffix_rows = {y for x, y in white if x >= sx}
    assert min(suffix_rows) == min(digit_rows) and max(suffix_rows) < max(digit_rows) - 2


def test_ordinal_that_fits_no_font_is_left_off():
    from display.ui.celebration_screen import _ordinal_line
    initialize_fonts(64)
    assert _ordinal_line(10 ** 12, [loaded_fonts['big']], loaded_fonts['titles'], 41, (1, 1, 1), 0, 64) is None
    no_suffix_font = _ordinal_line(600, [loaded_fonts['big']], None, 41, (1, 1, 1), 0, 64)
    assert [part[4] for part in no_suffix_font] == ['600']


@pytest.mark.parametrize('height, number, digits', [
    (64, 600, '600'), (64, 2000, '2,000'), (64, 2500, '2,500'), (64, 10000, '10000'),
    (32, 2000, '2,000'), (32, 10000, '10000')])
def test_comma_unless_dropping_it_keeps_the_big_font(height, number, digits):
    from display.ui.celebration_screen import _ordinal_line
    initialize_fonts(height)
    left = TEXT_LEFT_32 if height < 64 else 0
    fonts = [loaded_fonts['big'], loaded_fonts['countdown']]
    parts = _ordinal_line(number, fonts, loaded_fonts['info'], 30, (1, 1, 1), left, 64)
    # The last part is the raised ending; the rest are the number (in pieces round a comma).
    assert ''.join(part[4] for part in parts[:-1]) == digits and parts[0][0] is loaded_fonts['big']


@pytest.mark.parametrize('height', [32, 64])
def test_comma_is_spaced_like_the_digits(height):
    from display.ui.celebration_screen import _COMMA_INK, _number_runs
    initialize_fonts(height)
    font = loaded_fonts['big']
    assert (font.height, font.baseline, font.CharacterWidth(ord('0'))) in _COMMA_INK
    runs, width = _number_runs(font, '2,000')
    assert [text for _, text in runs] == ['2', ',', '000'] and width < get_text_width(font, '2,000')
    # Drawn: every blank gap between inked columns of the number is the same width.
    image = _render(height, INTRO_SECONDS + 0.1, {**STATE, 'number': 2000})
    white = _lit(image, WHITE)
    digit_top = min(y for _, y in white)
    suffix_left = min(x for x, y in white if y == digit_top and x > 30)  # the raised TH starts at the top row
    columns = sorted({x for x, _ in white if x < suffix_left - 1})
    gaps = {b - a - 1 for a, b in zip(columns, columns[1:]) if b - a > 1}
    assert len(gaps) == 1


def test_number_runs_leave_fonts_without_measurements_alone():
    from display.ui.celebration_screen import _number_runs
    font = Mock(height=99, baseline=1, CharacterWidth=lambda code: 5)
    assert _number_runs(font, '2,000') == ([(0, '2,000')], 25)
    initialize_fonts(64)
    assert _number_runs(loaded_fonts['big'], '600') == ([(0, '600')], 30)
