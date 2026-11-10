"""A name page line wider than the panel scrolls (hold, glide, hold, and back if there's time)."""
import pytest

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.username import (MARGIN, SCROLL_HOLD_END, SCROLL_HOLD_START, SCROLL_SPEED, UsernameScreen)
from scripts.render_demo import ImageMatrix

LONG = 'CHELSEA JACKSON ROBERTS'


def _offsets(overflow, interval, step=0.1):
    return [UsernameScreen.scroll_offset(overflow, n * step, interval) for n in range(int(interval / step) + 1)]


def test_the_line_holds_glides_to_the_end_and_holds_within_a_four_second_highlight():
    offsets = _offsets(32, 4.0)
    assert offsets[0] == 0 and offsets[int(SCROLL_HOLD_START * 10)] == 0       # holds first
    assert offsets == sorted(offsets)                                           # never goes back
    assert offsets[-1] == 32 and max(offsets) == 32                             # the whole name was shown
    assert offsets[int((4.0 - SCROLL_HOLD_END) * 10)] == 32                    # and rests at the end
    # It never moves faster than a few times the nominal speed, so it stays readable.
    assert max(b - a for a, b in zip(offsets, offsets[1:])) <= SCROLL_SPEED * 0.1 * 1.6


def test_with_time_to_spare_it_glides_back_and_ends_where_it_began():
    offsets = _offsets(32, 10.0)
    assert max(offsets) == 32 and offsets[0] == 0 and offsets[-1] == 0
    peak = offsets.index(32)
    assert offsets[:peak + 1] == sorted(offsets[:peak + 1])                  # glides out
    assert offsets[peak:] == sorted(offsets[peak:], reverse=True)            # holds, then glides back


def test_a_short_overflow_or_a_short_highlight_never_divides_by_zero_or_overshoots():
    assert UsernameScreen.scroll_offset(0, 1.0, 4.0) == 0 and UsernameScreen.scroll_offset(-3, 1.0, 4.0) == 0
    for interval in (0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 30.0):
        for overflow in (1, 4, 32, 90):
            offsets = _offsets(overflow, interval, 0.05)
            assert 0 <= min(offsets) and max(offsets) <= overflow


def _frame(height, lines, at, duration=4.0, label='TOP'):
    matrix, screen = ImageMatrix(height=height), UsernameScreen()
    state = {'username': 'Rider', 'details': [{'label': label, 'lines': lines}], 'detail_seconds': duration}
    screen.on_enter(matrix, state)
    screen.update(at)
    screen.render(matrix, state)
    return matrix.image


def _ink_rows(image, x0=0, x1=64):
    return {y for y in range(image.height) for x in range(x0, x1) if image.getpixel((x, y)) != (0, 0, 0)}


def _bands(image):
    """The (first, last) rows of each run of rows with any ink."""
    out = []
    for y in sorted(_ink_rows(image)):
        if out and y == out[-1][1] + 1:
            out[-1][1] = y
        else:
            out.append([y, y])
    return [tuple(band) for band in out]


def test_a_64_row_panel_wraps_a_long_name_and_keeps_the_count():
    initialize_fonts(64)
    # Static from the first settled frame to the last: no scrolling.
    assert len({_frame(64, ['JERMAINE JOHNSON', '12 CLASSES'], at).tobytes() for at in (0.4, 1.5, 3.9)}) == 1
    wrapped = _frame(64, ['JERMAINE JOHNSON', '12 CLASSES'], 2.0)
    # Name, accent, then the label (risen 3 rows), the name on two lines, and the count where it always was.
    assert _bands(wrapped)[2:] == [(30, 34), (40, 44), (47, 51), (54, 58)]
    assert not _ink_rows(wrapped, 0, MARGIN) and not _ink_rows(wrapped, 64 - MARGIN, 64)


def test_a_name_that_fits_or_cannot_be_split_keeps_todays_64_row_layout():
    initialize_fonts(64)
    assert _bands(_frame(64, ['JESS SIMS', '12 CLASSES'], 2.0))[2:] == [(33, 37), (45, 49), (54, 58)]
    # One 20-character word can't wrap: it scrolls as before.
    moving = {_frame(64, ['SUPERCALIFRAGILISTIC', '1 CLASS'], at).tobytes() for at in (0.4, 1.2, 2.4, 3.6)}
    assert len(moving) == 4


def test_wrap_two_lines_prefers_the_longest_first_line_and_refuses_what_cannot_fit():
    initialize_fonts(64)
    font = loaded_fonts['info']
    assert UsernameScreen.wrap_two_lines(font, 'CHELSEA JACKSON ROBERTS', 60) == ['CHELSEA JACKSON', 'ROBERTS']
    assert UsernameScreen.wrap_two_lines(font, 'JOSLYN THOMPSON RULE', 60) == ['JOSLYN THOMPSON', 'RULE']
    assert UsernameScreen.wrap_two_lines(font, 'JERMAINE JOHNSON', 60) == ['JERMAINE', 'JOHNSON']
    assert UsernameScreen.wrap_two_lines(font, 'JESS', 60) is None                      # one word
    assert UsernameScreen.wrap_two_lines(font, 'A B C D E F G H I J K L M N O P Q R S T', 60) is None   # needs three lines


def test_a_32_row_panel_runs_a_64_px_name_edge_to_edge_and_still_scrolls_longer_ones():
    initialize_fonts(32)
    font = loaded_fonts['info']
    assert get_text_width(font, 'JERMAINE JOHNSON') == 64 and get_text_width(font, 'CALLIE GULLICKSON') == 68
    still = {_frame(32, ['JERMAINE JOHNSON', '12 CLASSES'], at).tobytes() for at in (0.4, 1.5, 3.9)}
    assert len(still) == 1                                  # no scrolling
    image = _frame(32, ['JERMAINE JOHNSON', '12 CLASSES'], 2.0)
    assert any(image.getpixel((0, y)) != (0, 0, 0) for y in range(19, 24))      # reaches the left edge
    # The name page keeps its three rows: label, name, count.
    assert _bands(image)[2:] == [(12, 16), (19, 23), (26, 30)]
    # 68 px is 8 px over the room: it slides out and back, so a few of these frames differ.
    moving = {_frame(32, ['CALLIE GULLICKSON', '12 CLASSES'], at).tobytes() for at in (0.4, 1.2, 2.4, 3.6)}
    assert len(moving) >= 2


@pytest.mark.parametrize('height', (64, 32))
def test_a_long_line_moves_a_short_one_stays_and_the_margins_stay_blank(height):
    initialize_fonts(height)
    room = 64 - 2 * MARGIN
    long = LONG if height < 64 else 'SUPERCALIFRAGILISTIC'      # 64 rows wrap any name that can split
    assert get_text_width(loaded_fonts['info'], long) > room
    lines_y = (24, 31) if height < 64 else (50, 59)

    def frame(lines, at):
        return _frame(height, lines, at)

    moving = [frame([long, '12 CLASSES'], at).tobytes() for at in (0.4, 1.2, 2.4, 3.6)]
    assert len(set(moving)) == 4
    assert frame([long, '12 CLASSES'], 2.4).tobytes() == frame([long, '12 CLASSES'], 2.4).tobytes()   # settled frames repeat
    # A line that fits is where it always was.
    still = {frame(['JESS SIMS', '9 CLASSES'], at).tobytes() for at in (0.4, 1.2, 2.4, 3.6)}
    assert len(still) == 1
    # While the long one slides, the 2-px margins of its rows never show a pixel.
    for at in (0.7, 1.5, 2.5, 3.3):
        image = frame([long, '12 CLASSES'], at)
        for y in range(lines_y[0] - 6, lines_y[0] + 2):
            for x in list(range(MARGIN)) + list(range(64 - MARGIN, 64)):
                assert image.getpixel((x, y)) == (0, 0, 0), (at, x, y)


def test_every_name_in_a_top_three_can_be_read_in_full_within_the_highlight():
    initialize_fonts(64)
    names = ['JERMAINE JOHNSON', 'MATTY MAGGIACOMO', 'CHELSEA JACKSON ROBERTS', 'ADRIAN WILLIAMS']
    for name in names:
        overflow = max(0, get_text_width(loaded_fonts['info'], name) - (64 - 2 * MARGIN))
        offsets = _offsets(overflow, 4.0, 0.05) if overflow else [0]
        assert max(offsets) == overflow
