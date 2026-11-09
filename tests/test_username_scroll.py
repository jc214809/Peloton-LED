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


@pytest.mark.parametrize('height', (64, 32))
def test_a_long_line_moves_a_short_one_stays_and_the_margins_stay_blank(height):
    initialize_fonts(height)
    room = 64 - 2 * MARGIN
    assert get_text_width(loaded_fonts['info'], LONG) > room
    lines_y = (24, 31) if height < 64 else (50, 59)

    def frame(lines, at, duration=4.0):
        matrix, screen = ImageMatrix(height=height), UsernameScreen()
        state = {'username': 'Rider', 'details': [{'label': 'TOP', 'lines': lines}], 'detail_seconds': duration}
        screen.on_enter(matrix, state)
        screen.update(at)
        screen.render(matrix, state)
        return matrix.image

    moving = [frame([LONG, '12 CLASSES'], at).tobytes() for at in (0.4, 1.2, 2.4, 3.6)]
    assert len(set(moving)) == 4
    assert frame([LONG, '12 CLASSES'], 2.4).tobytes() == frame([LONG, '12 CLASSES'], 2.4).tobytes()   # settled frames repeat
    # A line that fits is where it always was.
    still = {frame(['JESS SIMS', '9 CLASSES'], at).tobytes() for at in (0.4, 1.2, 2.4, 3.6)}
    assert len(still) == 1
    # While the long one slides, the 2-px margins of its rows never show a pixel.
    for at in (0.7, 1.5, 2.5, 3.3):
        image = frame([LONG, '12 CLASSES'], at)
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
