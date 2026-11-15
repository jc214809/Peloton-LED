"""The next-class page: the soonest live or encore class the rider booked ("ride at 6:30 AM with Jess").

64 rows (layout "A, tag where the bar was", Joel's pick on 2026-11-14), all centred: the discipline icon,
the LIVE / ENCORE tag, the time, the day in gold, the class in the discipline's colour and the instructor.
32 rows: the icon on the left and a text column from x 28 (tag, time, day, first name).
In the last hour the time is `45 MIN` (and the day `AT 2:15 PM`); from the start, `NOW` and `STARTING`.
State: {'booking': one record from peloton.booked_classes (validated again here: the cache can hold anything),
'now': the timestamp to count from, 'timezone': the board's zone name or None}.
"""
import math

from driver import graphics

from display.display import get_text_width, loaded_fonts, plain_letters
from peloton.booked_classes import ENCORE, LIVE, class_lines, instructor_lines, valid_booking, when
from .discipline_icons import DISCIPLINE_ICON_ROWS
from .lifetime_overview import discipline_color, draw_icon
from .screen import Screen

WHITE = (255, 255, 255)
GOLD = (255, 215, 0)
GREY = (145, 165, 190)
TAG_COLORS = {LIVE: (220, 30, 40), ENCORE: (60, 90, 230)}
# The tag pulses (its colour only, 100% down to PULSE_FLOOR and back) from this long before the start until
# the page stops showing, so it flags that class is starting; outside that the page is still and not animated.
PULSE_WINDOW = 600
PULSE_FLOOR = 0.55
PULSE_PERIOD = 1.0
PULSE_FRAME_SECONDS = 0.05  # 20 fps
ICON_WIDTH = 26
# The widest a centred 4 px line may be (64 rows): `20 MIN STRENGTH` fits, `120 MIN STRENGTH` doesn't.
LINE_WIDTH = 62
# 64 rows: the tag block's top row (7 rows: the 4x6 capitals on rows 24-28), and each line's baseline.
TAG_TOP = 23
TIME_BASELINE, DAY_BASELINE, CLASS_BASELINE, INSTRUCTOR_BASELINE = 40, 49, 56, 63
# 32 rows: the text column, the tag at the top, then each line's baseline.
COLUMN_LEFT = 28
SHORT_ICON_TOP = 5
SHORT_TIME_BASELINE, SHORT_DAY_BASELINE, SHORT_NAME_BASELINE = 17, 24, 31
SHORT_BIG_BASELINE = 18  # 7x13B (`45`, `NOW`) is 9 rows tall, the 5x8 time 6


def _text(matrix, font, x, y, color, text):
    graphics.DrawText(matrix, font, x, y, graphics.Color(*color), text)


def _centre_in(matrix, font, left, width, y, color, text):
    _text(matrix, font, left + max((width - get_text_width(font, text) + 1) // 2, 0), y, color, text)


def fitted(font, candidates, width):
    """The first candidate that fits `width`, else the last one cut to fit."""
    for text in candidates:
        if get_text_width(font, text) <= width:
            return text
    text = candidates[-1] if candidates else ''
    while text and get_text_width(font, text) > width:
        text = text[:-1]
    return text


def pulse_level(elapsed):
    """The tag colour's brightness (PULSE_FLOOR to 1.0) `elapsed` seconds into a showing: full at 0, a whole
    cycle every PULSE_PERIOD, stepped to the frame so every drawn level is one of a few."""
    frame = int(max(0.0, elapsed) / PULSE_FRAME_SECONDS + 1e-9)
    phase = (frame * PULSE_FRAME_SECONDS / PULSE_PERIOD) % 1.0
    return PULSE_FLOOR + (1 - PULSE_FLOOR) * (1 + math.cos(2 * math.pi * phase)) / 2


def pulses(state):
    """Whether a page in `state` is inside the pulse window: its class starts within PULSE_WINDOW (or has
    started) and it has a tag to pulse."""
    booking = state.get('booking') if isinstance(state, dict) else None
    now = state.get('now') if isinstance(state, dict) else None
    if not valid_booking(booking) or booking['tag'] not in TAG_COLORS:
        return False
    if isinstance(now, bool) or not isinstance(now, (int, float)):
        return False
    return booking['start'] - now <= PULSE_WINDOW


def draw_tag(matrix, tag, left, width, top, level=1.0):
    """`LIVE` white on red or `ENCORE` white on blue in 4x6 on a 7-row block, 2 px of colour each side,
    centred in the `width` columns from `left`. Nothing for a class that is neither."""
    if tag not in TAG_COLORS:
        return
    font = loaded_fonts['info']
    lit = get_text_width(font, tag) - 1  # the advance ends in a blank column
    block = lit + 4
    x0 = left + (width - block + 1) // 2
    colour = tuple(round(channel * level) for channel in TAG_COLORS[tag])  # `level` dims the block, not the text
    for y in range(top, top + 7):
        for x in range(x0, x0 + block):
            matrix.SetPixel(x, y, *colour)
    _text(matrix, font, x0 + 2, top + 6, WHITE, tag)


def draw_class_icon(matrix, discipline, left, top):
    """The 26x24 discipline icon in its colour; a discipline with no icon draws none."""
    if discipline in DISCIPLINE_ICON_ROWS:
        draw_icon(matrix, discipline, left, top, discipline_color(discipline))


class NextClassScreen(Screen):
    # Per showing: on_enter turns `animated` on only inside the pulse window, so outside it nothing ticks.
    animated = False
    atomic_frames = True
    frame_seconds = PULSE_FRAME_SECONDS

    def __init__(self):
        self.elapsed = 0.0

    def on_enter(self, matrix, state=None):
        self.elapsed = 0.0
        self.animated = pulses(state)

    def update(self, dt):
        self.elapsed += max(0, dt)

    def _level(self):
        """The tag's brightness now: always full on a still page, whatever the elapsed time."""
        return pulse_level(self.elapsed) if self.animated else 1.0

    def render(self, matrix, state=None):
        booking = state.get('booking') if isinstance(state, dict) else None
        now = state.get('now') if isinstance(state, dict) else None
        if not valid_booking(booking) or isinstance(now, bool) or not isinstance(now, (int, float)):
            return False
        moment = when(booking, now, state.get('timezone'))
        if matrix.height < 64:
            return self._render_short(matrix, booking, moment)
        fonts, width = loaded_fonts, matrix.width
        draw_class_icon(matrix, booking['discipline'], (width - ICON_WIDTH) // 2, 0)
        draw_tag(matrix, booking['tag'], 0, width, TAG_TOP, self._level())
        if moment['mode'] == 'now':
            time_line, day_line = 'NOW', 'STARTING'
        elif moment['mode'] == 'minutes':
            time_line, day_line = f"{moment['minutes']} MIN", f"AT {moment['time']} {moment['meridiem']}"
        else:
            time_line, day_line = f"{moment['time']} {moment['meridiem']}", moment['day']
        _centre_in(matrix, fonts['bold'], 0, width, TIME_BASELINE, WHITE, time_line)
        _centre_in(matrix, fonts['titles'], 0, width, DAY_BASELINE, GOLD,
                   fitted(fonts['titles'], [day_line], width))
        small = fonts['stats']
        _centre_in(matrix, small, 0, width, CLASS_BASELINE, discipline_color(booking['discipline']),
                   fitted(small, class_lines(booking), LINE_WIDTH))
        names = instructor_lines(plain_letters(booking['instructor']))
        if names:
            _centre_in(matrix, small, 0, width, INSTRUCTOR_BASELINE, GREY, fitted(small, names, LINE_WIDTH))
        return True

    def _render_short(self, matrix, booking, moment):
        small, medium, big = loaded_fonts['info'], loaded_fonts['discipline'], loaded_fonts['bold']
        left, width = COLUMN_LEFT, matrix.width - COLUMN_LEFT
        draw_class_icon(matrix, booking['discipline'], 0, SHORT_ICON_TOP)
        draw_tag(matrix, booking['tag'], left, width, 0, self._level())
        if moment['mode'] == 'now':
            self._pair(matrix, left, width, (big, 'NOW', SHORT_BIG_BASELINE))
            day_line = 'STARTING'
        elif moment['mode'] == 'minutes':
            self._pair(matrix, left, width, (big, str(moment['minutes']), SHORT_BIG_BASELINE),
                       (small, 'MIN', SHORT_BIG_BASELINE))
            day_line = f"{moment['time']} {moment['meridiem']}"
        else:
            self._pair(matrix, left, width, (medium, moment['time'], SHORT_TIME_BASELINE),
                       (small, moment['meridiem'], SHORT_TIME_BASELINE))
            day_line = moment['day']
        _centre_in(matrix, small, left, width, SHORT_DAY_BASELINE, GOLD, fitted(small, [day_line], width))
        names = instructor_lines(plain_letters(booking['instructor']))
        if names:
            _centre_in(matrix, small, left, width, SHORT_NAME_BASELINE, GREY, fitted(small, names[-1:], width))
        return True

    @staticmethod
    def _pair(matrix, left, width, *parts):
        """Text in more than one font on one line, centred together in the column (each advance already
        ends in a blank column, which spaces them)."""
        total = sum(get_text_width(font, text) for font, text, _ in parts)
        x = left + max((width - total + 1) // 2, 0)
        for font, text, baseline in parts:
            _text(matrix, font, x, baseline, WHITE, text)
            x += get_text_width(font, text)
