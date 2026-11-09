"""Celebration splash: a gold trophy rises through falling confetti, then 600 (with a small raised TH) / WORKOUT / JOEL.

One screen for any event worth a party. state:
    number    the count being celebrated: 600 big, with a small raised TH; optional
    headline  the big line instead when there's no number (e.g. 'GOAL HIT'); default 'CONGRATS'
    noun      what was counted ('WORKOUT', 'RIDE', ...), under the big line
    subtitle  a last line, e.g. the rider's name; optional
"""
import math
import random
from typing import Any, Optional

from driver import graphics
from display.display import get_text_width, loaded_fonts
from .screen import Screen

# The trophy rises for RISE_SECONDS; the text appears at INTRO_SECONDS.
RISE_SECONDS = 0.6
INTRO_SECONDS = 0.8
# The card then holds at least this long, so it's readable on a short page.
MIN_CARD_SECONDS = 5.0

_GOLD = graphics.Color(255, 215, 0)
_WHITE = graphics.Color(255, 255, 255)
_BLUE = graphics.Color(0, 120, 255)
_CONFETTI = ((255, 60, 60), (255, 215, 0), (60, 160, 255), (60, 230, 110), (230, 90, 255), (255, 140, 0))
_TROPHY_DARK, _TROPHY_LIGHT, _TROPHY_GLINT = (230, 170, 0), (255, 235, 120), (255, 255, 230)
# Discipline slugs (the workout log's and Peloton's fitness_discipline) to the word the app uses.
_NOUNS = {'cycling': 'RIDE', 'bike_bootcamp': 'RIDE', 'running': 'RUN', 'walking': 'WALK',
          'rowing': 'ROW', 'caesar': 'ROW', 'caesar_bootcamp': 'ROW'}

TROPHY = (
    '..##############..',
    '##.############.##',
    '#..############..#',
    '#..############..#',
    '#..############..#',
    '.#.############.#.',
    '..##.########.##..',
    '....##########....',
    '.....########.....',
    '......######......',
    '.......####.......',
    '........##........',
    '........##........',
    '......######......',
    '.....########.....',
    '.....########.....',
)
TROPHY_SMALL = (
    '.##########.',
    '#.########.#',
    '#.########.#',
    '.#.######.#.',
    '...######...',
    '....####....',
    '.....##.....',
    '.....##.....',
    '...######...',
    '...######...',
)
# 32 rows: the small trophy on the left, the text centred in the columns after it.
TEXT_LEFT_32 = 16


def ordinal(number: int) -> str:
    """1ST, 2ND, 3RD, 4TH, 11TH, 12TH, 13TH, 21ST, 600TH."""
    suffix = 'TH' if 10 <= number % 100 <= 20 else {1: 'ST', 2: 'ND', 3: 'RD'}.get(number % 10, 'TH')
    return f'{number}{suffix}'


def milestone_noun(discipline: Optional[str]) -> str:
    """What a milestone counts: WORKOUT for the total, RIDE/RUN/WALK/ROW, else CLASS."""
    if not discipline:
        return 'WORKOUT'
    return _NOUNS.get(str(discipline).strip().lower().replace(' ', '_'), 'CLASS')


# One discipline's milestone: these say what was counted in a word; the rest use their name.
_DISCIPLINE_NOUNS = {'cycling': 'RIDE', 'running': 'RUN', 'walking': 'WALK', 'rowing': 'ROW'}


def discipline_noun(discipline: Optional[str], label: Optional[str] = None) -> str:
    """What one discipline's milestone counts: 600TH RIDE, 500TH STRENGTH, 25TH ROW BOOTCAMP.
    Unlike milestone_noun, a bootcamp keeps its own name: its count isn't the rides' or rows'."""
    slug = str(discipline or '').strip().lower().replace(' ', '_')
    return _DISCIPLINE_NOUNS.get(slug) or str(label or slug.replace('_', ' ')).upper() or 'CLASS'


def _noun_line(noun, fonts, room, baseline, left, right):
    """The noun centred in the first font it fits, else its last word (TREAD BOOTCAMP is
    too wide beside the trophy on 32 rows; BOOTCAMP isn't)."""
    for text in dict.fromkeys((noun, noun.split()[-1] if noun.split() else noun)):
        line = _placed(_fit(text, fonts, room), text, baseline, _GOLD, left, right)
        if line:
            return line
    return None


def number_text(number) -> str:
    """'600TH', '2000TH': no comma, so four digits still fit the big font on 64 columns."""
    if not isinstance(number, int) or isinstance(number, bool) or number < 0:
        return ''
    return ordinal(number)


def _set(matrix, x, y, color, fade=1.0):
    x, y = round(x), round(y)
    if 0 <= x < matrix.width and 0 <= y < matrix.height:
        matrix.SetPixel(x, y, *(max(0, min(255, round(c * fade))) for c in color))


def draw_confetti(matrix, elapsed: float) -> None:
    """Flecks drifting down and swaying, looping for as long as the page shows. Drawn first, so the
    trophy and text paint over them: any pixel they leave off is fair game. Fixed seed: always the same."""
    rng = random.Random(7)
    for i in range(40 if matrix.height >= 64 else 24):
        x0, speed, phase = rng.uniform(0, matrix.width), rng.uniform(9, 18), rng.uniform(0, matrix.height + 8)
        y = round((phase + speed * elapsed) % (matrix.height + 8) - 4)
        x = round(x0 + 2 * math.sin(elapsed * 3 + i))
        for px in ((x, x + 1) if i % 2 else (x,)):
            _set(matrix, px, y, _CONFETTI[i % len(_CONFETTI)], 0.8)


def draw_trophy(matrix, rows, left, top, elapsed: float) -> None:
    """The trophy, with a glint sweeping across it about every second and a half."""
    glint = (elapsed * 30) % (len(rows[0]) + 30) - 6
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell == '#':
                distance = abs((x + y * 0.5) - glint)
                color = _TROPHY_GLINT if distance < 1.5 else (_TROPHY_LIGHT if distance < 3 else _TROPHY_DARK)
                _set(matrix, left + x, top + y, color)


def _fit(text, fonts, room):
    """The first font the text fits in, or None when it fits none of them."""
    for font in fonts:
        if font is not None and get_text_width(font, text) <= room:
            return font
    return None


# Rows from the baseline up to the top of a digit or capital, by (font height, baseline): the
# board's fonts (10x20, 7x13, 6x9, 5x8, 4x6). The Pi's fonts can't be measured by drawing.
_CAP_HEIGHTS = {(20, 16): 13, (13, 11): 9, (9, 7): 6, (8, 7): 6, (6, 5): 5}


def _cap_height(font):
    return _CAP_HEIGHTS.get((font.height, font.baseline), font.baseline - 1)


def _placed(font, text, baseline, color, left, right):
    """One line: [(font, x, baseline, colour, text)] centred between left and right, or None."""
    if font is None or not text:
        return None
    x = left + max((right - left - get_text_width(font, text)) // 2, 0)
    return [(font, x, baseline, color, text)]


# Where the ink sits in a fixed-width cell, by (font height, baseline, cell width): the comma's
# first and last inked columns, then a digit's. Measured from the board's fonts, like _CAP_HEIGHTS.
_COMMA_INK = {(20, 16, 10): ((3, 6), (1, 8)), (13, 11, 7): ((1, 4), (0, 5)), (13, 11, 6): ((1, 3), (0, 4)),
              (9, 7, 6): ((2, 3), (1, 4)), (6, 5, 4): ((0, 1), (0, 2))}


def _number_runs(font, digits):
    """([(x offset, text)], width) for digits like '2,000', with the comma closed up so the gaps
    either side of it match the gap between digits. A font not in _COMMA_INK keeps its spacing."""
    cell = font.CharacterWidth(ord('0'))
    ink = _COMMA_INK.get((font.height, font.baseline, cell))
    if ink is None or ',' not in digits:
        return [(0, digits)], get_text_width(font, digits)
    (comma_left, comma_right), (digit_left, digit_right) = ink
    gap = cell - (digit_right - digit_left + 1)
    runs, pen = [], 0
    groups = digits.split(',')
    for index, group in enumerate(groups):
        runs.append((pen, group))
        pen += get_text_width(font, group)
        if index < len(groups) - 1:
            comma = pen - cell + digit_right + gap + 1 - comma_left
            runs.append((comma, ','))
            pen = comma + comma_right + gap + 1 - digit_left
    return runs, pen


def ordinal_line(number, digit_fonts, suffix_font, baseline, color, left, right):
    """2,000 big with a small TH raised to the digits' top, like a superscript; centred as one piece.
    With a comma like the board's other totals, unless dropping it keeps the number in a bigger font
    (10000 on 64 columns). None when it fits in none of the digit fonts."""
    plain, suffix = str(number), ordinal(number)[len(str(number)):]
    suffix_width = get_text_width(suffix_font, suffix) if suffix_font else 0
    for font, digits in ((font, digits) for font in digit_fonts if font is not None
                         for digits in dict.fromkeys((f'{number:,}', plain))):
        runs, digits_width = _number_runs(font, digits)
        width = digits_width + 1 + suffix_width
        if width <= right - left - 1:
            x = left + max((right - left - width) // 2, 0)
            parts = [(font, x + dx, baseline, color, text) for dx, text in runs]
            if suffix_font:
                raised = baseline - _cap_height(font) + _cap_height(suffix_font)
                parts.append((suffix_font, x + width - suffix_width, raised, color, suffix))
            return parts
    return None


class CelebrationScreen(Screen):
    """Confetti throughout; the trophy rises, then the text appears under (or beside) it."""

    animated = True
    atomic_frames = True
    # 20 fps: show_and_wait's usual 5 fps makes the confetti jump instead of fall.
    frame_seconds = 0.05

    def __init__(self):
        self.elapsed = 0.0

    def on_enter(self, matrix, state=None):
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += max(0, dt)

    def render(self, matrix, state: Optional[Any] = None) -> bool:
        state = state if isinstance(state, dict) else {}
        number = state.get('number') if number_text(state.get('number')) else None
        big = number if number is not None else str(state.get('headline') or 'CONGRATS').upper()
        noun = str(state.get('noun') or '').upper()
        subtitle = str(state.get('subtitle') or '').upper()
        short = matrix.height < 64
        lines = []
        if self.elapsed >= INTRO_SECONDS:
            lines = (self._lines_32 if short else self._lines_64)(matrix, big, noun, subtitle)
        draw_confetti(matrix, self.elapsed)
        rise = 1 - (1 - min(1.0, self.elapsed / RISE_SECONDS)) ** 3
        if short:
            draw_trophy(matrix, TROPHY_SMALL, 3, round(matrix.height - (matrix.height - 11) * rise),
                        self.elapsed)
        else:
            draw_trophy(matrix, TROPHY, (matrix.width - len(TROPHY[0])) // 2,
                        round(matrix.height - (matrix.height - 3) * rise), self.elapsed)
        for parts in lines:
            for font, x, y, color, text in parts:
                graphics.DrawText(matrix, font, x, y, color, text)
        return True

    @staticmethod
    def _big_line(big, fonts, suffix_font, baseline, left, right):
        if isinstance(big, int):
            return ordinal_line(big, fonts, suffix_font, baseline, _WHITE, left, right)
        return _placed(_fit(big, fonts, right - left - 1), big, baseline, _WHITE, left, right)

    @staticmethod
    def _lines_64(matrix, big, noun, subtitle):
        w = matrix.width
        small = [loaded_fonts.get('titles'), loaded_fonts.get('info')]
        lines = [
            CelebrationScreen._big_line(big, [loaded_fonts.get('big'), loaded_fonts.get('countdown'),
                                              loaded_fonts.get('discipline')], loaded_fonts.get('titles'),
                                        41, 0, w),
            _noun_line(noun, small, w - 2, 51, 0, w),
            _placed(_fit(subtitle, small, w - 2), subtitle, 61, _BLUE, 0, w),
        ]
        return [line for line in lines if line]

    @staticmethod
    def _lines_32(matrix, big, noun, subtitle):
        # The name goes on top, over the number, beside the trophy.
        w = matrix.width
        room = w - TEXT_LEFT_32 - 1
        info = [loaded_fonts.get('info')]
        lines = [
            _placed(_fit(subtitle, info, room), subtitle, 7, _BLUE, TEXT_LEFT_32, w),
            CelebrationScreen._big_line(big, [loaded_fonts.get('big'), loaded_fonts.get('countdown'),
                                              loaded_fonts.get('info')], loaded_fonts.get('info'),
                                        20, TEXT_LEFT_32, w),
            _noun_line(noun, info, room, 28, TEXT_LEFT_32, w),
        ]
        return [line for line in lines if line]
