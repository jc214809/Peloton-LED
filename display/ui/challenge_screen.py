"""The challenges page: one Peloton challenge's progress toward its next tier.

64 rows ("C1", Joel's pick on 2026-11-14): the title in gold, a smooth ring from the current tier to the next
one in the next tier's colour, the number and unit inside it, and `497 TO 6K` along the bottom.
32 rows ("A"): the title, the number, a bar from tier to tier, then the current tier and `497 TO 6K`.
State: one record from peloton.challenges (validated again here: the cache can hold anything).
"""
import math
from functools import lru_cache

from driver import graphics

from display.display import get_text_width, loaded_fonts
from peloton.challenges import UNEARNED, tier_progress, valid_challenge
from .screen import Screen

WHITE = (255, 255, 255)
GOLD = (255, 215, 0)
GREY = (145, 165, 190)
BLUE = (0, 120, 255)
BAR_TRACK = (35, 35, 35)
RING_TRACK = (28, 28, 34)
# Named tiers in their own colour; numbered ones (`6K`) and any other name in gold.
TIER_COLORS = {'BRONZE': (205, 127, 50), 'SILVER': (200, 200, 210), 'GOLD': GOLD}

# The ring (64 rows): centre, outer radius and width in pixels; pixel centres sit at x + 0.5.
RING_CENTRE = (32, 35.5)
RING_RADIUS = 21.5
RING_WIDTH = 3
SUBSAMPLES = 5  # per side: each pixel's coverage is measured at 5 x 5 points
# The number inside the ring: the widest advance that clears the ring's inside at its rows.
RING_NUMBER_WIDTH = 33
# The unit under it, in the 4 px `stats` font: the ring's inside is 31 px wide at its row.
RING_UNIT_WIDTH = 31


def tier_color(title):
    return TIER_COLORS.get(str(title or '').strip().upper(), GOLD)


def tier_label(tier):
    """The current tier as the 64x32 page writes it: 0 before the first one."""
    return '0' if tier['title'] == UNEARNED else tier['title']


@lru_cache(maxsize=64)
def ring_pixels(fraction, color):
    """Every lit pixel of the ring as (x, y, r, g, b): the arc runs clockwise from 12 o'clock to `fraction` of
    the way round in `color`, with round ends, over the faint track. Each pixel is shaded by how much of it the
    arc and track cover (5 x 5 samples), so the edges are smooth. Cached: the page draws the same ring often."""
    cx, cy = RING_CENTRE
    outer, width = RING_RADIUS, RING_WIDTH
    inner, mid = outer - width, outer - width / 2
    end = math.tau * fraction
    caps = [(cx + mid * math.sin(a), cy - mid * math.cos(a)) for a in (0, end)] if fraction > 0 else []
    total = SUBSAMPLES * SUBSAMPLES
    pixels = []
    for y in range(int(cy - outer) - 1, int(cy + outer) + 2):
        for x in range(int(cx - outer) - 1, int(cx + outer) + 2):
            centre = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            if centre < inner - 1 or centre > outer + 1:
                continue  # wholly inside or outside the band (caps stay within it)
            lit = track = 0
            for i in range(SUBSAMPLES):
                for j in range(SUBSAMPLES):
                    px, py = x + (i + 0.5) / SUBSAMPLES, y + (j + 0.5) / SUBSAMPLES
                    in_band = inner <= math.hypot(px - cx, py - cy) <= outer
                    in_arc = in_band and math.atan2(px - cx, cy - py) % math.tau <= end
                    if in_arc or any(math.hypot(px - qx, py - qy) <= width / 2 for qx, qy in caps):
                        lit += 1
                    elif in_band:
                        track += 1
            if lit or track:
                pixels.append((x, y) + tuple(min(255, round(color[k] * lit / total + RING_TRACK[k] * track / total))
                                             for k in range(3)))
    return tuple(pixels)


def _text(matrix, font, x, y, color, text):
    graphics.DrawText(matrix, font, x, y, graphics.Color(*color), text)


def _centre(matrix, font, y, color, text):
    _text(matrix, font, max((matrix.width - get_text_width(font, text) + 1) // 2, 0), y, color, text)


def _centre_at(matrix, font, cx, y, color, text):
    _text(matrix, font, cx - (get_text_width(font, text) - 1) // 2, y, color, text)


def fitted_title(title, fonts, width):
    """(font, text) for the title: the first font it fits, else the last one with words dropped from the end,
    else cut to fit."""
    for font in fonts:
        if get_text_width(font, title) <= width:
            return font, title
    font, words = fonts[-1], title.split()
    while len(words) > 1:
        words.pop()
        if get_text_width(font, ' '.join(words)) <= width:
            return font, ' '.join(words)
    text = title
    while text and get_text_width(font, text) > width:
        text = text[:-1]
    return font, text


def compact_number(shown):
    """A number too wide for the ring: '123,456' -> '123K'."""
    try:
        value = float(shown.replace(',', ''))
    except ValueError:
        return shown
    return f'{value / 1000:.0f}K' if value >= 1000 else shown


def ring_number(shown):
    """(font, text) for the number inside the ring: with its comma in 6x13B, without it, smaller, else 123K."""
    bold, small = loaded_fonts['title_bold'], loaded_fonts['titles']
    plain = shown.replace(',', '')
    for font, text in ((bold, shown), (bold, plain), (small, plain)):
        if get_text_width(font, text) <= RING_NUMBER_WIDTH:
            return font, text
    return bold, compact_number(shown)


def remaining_line(challenge, font, width):
    """`497 TO 6K`; `497 TO GO` when the tier's name makes it too wide; else just the number."""
    to_next = challenge['to_next']
    for line in (f"{to_next} TO {challenge['next']['title']}", f'{to_next} TO GO'):
        if get_text_width(font, line) <= width:
            return line
    return to_next


class ChallengeScreen(Screen):
    def render(self, matrix, state=None):
        if not valid_challenge(state) or state.get('next') is None:
            return False
        if matrix.height < 64:
            return self._render_short(matrix, state)
        fonts = loaded_fonts
        font, title = fitted_title(state['title'], [fonts['titles'], fonts['stats']], matrix.width)
        _centre(matrix, font, 8, GOLD, title)
        fraction = round(tier_progress(state), 3)
        for x, y, r, g, b in ring_pixels(fraction, tier_color(state['next']['title'])):
            matrix.SetPixel(x, y, r, g, b)
        cx = RING_CENTRE[0]
        font, number = ring_number(state['shown'])
        _centre_at(matrix, font, cx, 38, WHITE, number)
        unit = state['unit']
        while unit and get_text_width(fonts['stats'], unit) > RING_UNIT_WIDTH:
            unit = unit[:-1]
        _centre_at(matrix, fonts['stats'], cx, 45, GREY, unit)
        _centre(matrix, fonts['stats'], 63, WHITE, remaining_line(state, fonts['stats'], matrix.width))
        return True

    def _render_short(self, matrix, state):
        small, large = loaded_fonts['info'], loaded_fonts['bold']
        font, title = fitted_title(state['title'], [small], matrix.width)
        _centre(matrix, font, 6, GOLD, title)
        number = state['shown'] if get_text_width(large, state['shown']) <= 62 else compact_number(state['shown'])
        _centre(matrix, large, 18, WHITE, number)
        left, right, top = 3, 60, 21
        filled = round((right - left + 1) * tier_progress(state))
        for x in range(left, right + 1):
            color = BLUE if x < left + filled else BAR_TRACK
            for y in range(top, top + 3):
                matrix.SetPixel(x, y, *color)
        line = remaining_line(state, small, 60)
        tier = tier_label(state['tier'])
        if get_text_width(small, tier) + get_text_width(small, line) + 4 <= 60:
            _text(matrix, small, 2, 31, tier_color(state['tier']['title']), tier)
            _text(matrix, small, 61 - get_text_width(small, line) + 1, 31, WHITE, line)
        else:
            _centre(matrix, small, 31, WHITE, line)
        return True
