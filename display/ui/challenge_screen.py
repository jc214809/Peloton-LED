"""The challenges page: one Peloton challenge's progress toward its next tier.

64 rows ("C1", Joel's pick on 2026-11-14): the title in gold, a smooth ring from the current tier to the next
one in the next tier's colour, the number and unit inside it, and `497 TO 6K` along the bottom.
32 rows ("A"): the title, the number, a bar from tier to tier, then the current tier and `497 TO 6K`.
State: one record from peloton.challenges (validated again here: the cache can hold anything).

Each time the page is shown it plays a short intro, like the journey page's (20 fps, settled by INTRO_SECONDS):
the title, unit and bottom line are there from the first frame; the ring (64 rows) or the bar (32 rows) fills
from empty to the real figure with an ease-out while the number counts up with it, and on 64 rows the ring's
leading end then flashes once. After that the page holds still, and that settled frame is the page.
"""
import math
from bisect import bisect_right
from functools import lru_cache

from driver import graphics

from display.display import get_text_width, loaded_fonts
from peloton.challenges import MONTH_ABBREVIATIONS, UNEARNED, tier_progress, valid_challenge
from .journey_screen import ease_out
from .screen import Screen

WHITE = (255, 255, 255)
GOLD = (255, 215, 0)
GREY = (145, 165, 190)
BAR_TRACK = (35, 35, 35)
RING_TRACK = (28, 28, 34)
# Named tiers in their own colour; numbered ones (`6K`) and any other name in gold.
TIER_COLORS = {'BRONZE': (205, 127, 50), 'SILVER': (200, 200, 210), 'GOLD': GOLD}

# The ring (64 rows): centre, outer radius and width in pixels; pixel centres sit at x + 0.5.
RING_CENTRE = (32, 33.5)  # rows 12-54 of 64: 4 blank rows above (under the title) and 3 below (above the line)
RING_RADIUS = 21.5
RING_WIDTH = 3
SUBSAMPLES = 5  # per side: each pixel's coverage is measured at 5 x 5 points
# The intro, in seconds from the page appearing: the sweep (bar and number), then the flash on the ring's end.
FRAME_SECONDS = 0.05      # 20 fps
SWEEP_SECONDS = 0.8
INTRO_SECONDS = 1.0       # the flash is over, the page holds still (a test checks)
SWEEP_FRAMES = round(SWEEP_SECONDS / FRAME_SECONDS)
FLASH_FRAMES = round((INTRO_SECONDS - SWEEP_SECONDS) / FRAME_SECONDS)
FLASH_PEAK = 0.7          # at most this much of the way to white
FLASH_RADIUS = 4.5        # pixels from the ring's end that brighten
# The number inside the ring: the widest advance that clears the ring's inside at its rows.
RING_NUMBER_WIDTH = 33
# The unit under it, in the 4 px `stats` font: the ring's inside is 31 px wide at its row.
RING_UNIT_WIDTH = 31


def tier_color(title):
    return TIER_COLORS.get(str(title or '').strip().upper(), GOLD)


def tier_label(tier):
    """The current tier as the 64x32 page writes it: 0 before the first one."""
    return '0' if tier['title'] == UNEARNED else tier['title']


@lru_cache(maxsize=1)
def _ring_geometry():
    """The part of the ring that never changes, measured once (5 x 5 samples per pixel, the slow part): for each
    pixel the band's samples, their angle round from 12 o'clock and whether the start's round cap covers them.
    Any fraction then takes a bisect per pixel instead of 25 distance checks."""
    cx, cy = RING_CENTRE
    outer, width = RING_RADIUS, RING_WIDTH
    inner, mid = outer - width, outer - width / 2
    start = (cx, cy - mid)
    cells = []
    for y in range(int(cy - outer) - 1, int(cy + outer) + 2):
        for x in range(int(cx - outer) - 1, int(cx + outer) + 2):
            centre = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            if centre < inner - 1 or centre > outer + 1:
                continue  # wholly inside or outside the band (caps stay within it)
            samples, covered, angles = [], 0, []
            for i in range(SUBSAMPLES):
                for j in range(SUBSAMPLES):
                    px, py = x + (i + 0.5) / SUBSAMPLES, y + (j + 0.5) / SUBSAMPLES
                    if not inner <= math.hypot(px - cx, py - cy) <= outer:
                        continue
                    angle = math.atan2(px - cx, cy - py) % math.tau
                    under_start = math.hypot(px - start[0], py - start[1]) <= width / 2
                    samples.append((px, py, angle, under_start))
                    if under_start:
                        covered += 1
                    else:
                        angles.append(angle)
            if samples:
                cells.append((x, y, x + 0.5, y + 0.5, len(samples), covered, sorted(angles), tuple(samples)))
    return tuple(cells)


def ring_end(fraction):
    """Where the arc's round end is centred (the middle of the band, `fraction` of the way round)."""
    mid = RING_RADIUS - RING_WIDTH / 2
    end = math.tau * fraction
    return RING_CENTRE[0] + mid * math.sin(end), RING_CENTRE[1] - mid * math.cos(end)


@lru_cache(maxsize=256)
def ring_pixels(fraction, color):
    """Every lit pixel of the ring as (x, y, r, g, b): the arc runs clockwise from 12 o'clock to `fraction` of
    the way round in `color`, with round ends, over the faint track. Each pixel is shaded by how much of it the
    arc and track cover (5 x 5 samples), so the edges are smooth. Cached: the page draws the same ring often
    (the intro's 17 rings per challenge are the same on every pass)."""
    end = math.tau * fraction
    ex, ey = ring_end(fraction)
    half = RING_WIDTH / 2
    total = SUBSAMPLES * SUBSAMPLES
    pixels = []
    for x, y, mx, my, band, covered, angles, samples in _ring_geometry():
        if fraction <= 0:
            lit = 0
        elif math.hypot(mx - ex, my - ey) <= half + 0.75:  # the end cap reaches into this pixel: sample it
            lit = sum(1 for px, py, angle, under_start in samples
                      if under_start or angle <= end or math.hypot(px - ex, py - ey) <= half)
        else:
            lit = covered + bisect_right(angles, end)
        track = band - lit
        pixels.append((x, y) + tuple(min(255, round(color[k] * lit / total + RING_TRACK[k] * track / total))
                                     for k in range(3)))
    return tuple(pixels)


def intro_frame(elapsed):
    """Whole 20 fps frames since the page appeared (the intro is drawn in steps, so the cached rings repeat)."""
    return int(max(0.0, elapsed) / FRAME_SECONDS + 1e-9)


def sweep(elapsed):
    """How far the ring, bar and number have got: 0 at the start, 1 from SWEEP_SECONDS on (ease-out)."""
    return ease_out(min(intro_frame(elapsed), SWEEP_FRAMES) / SWEEP_FRAMES)


def flash(elapsed):
    """How white the ring's end is: 0 until the sweep lands, a brief swell and fall over the next frames, then 0."""
    frame = intro_frame(elapsed) - SWEEP_FRAMES
    if not 0 <= frame < FLASH_FRAMES:
        return 0.0
    return FLASH_PEAK * math.sin(math.pi * (frame + 0.5) / FLASH_FRAMES)


def flashed(pixels, fraction, strength):
    """`pixels` with those near the arc's end blended toward white by `strength` (less with distance)."""
    if strength <= 0 or fraction <= 0:
        return pixels
    ex, ey = ring_end(fraction)
    track = RING_TRACK
    out = []
    for x, y, r, g, b in pixels:
        weight = strength * (1 - math.hypot(x + 0.5 - ex, y + 0.5 - ey) / FLASH_RADIUS)
        if weight > 0 and (r, g, b) != track:
            r, g, b = (round(c + (255 - c) * weight) for c in (r, g, b))
        out.append((x, y, r, g, b))
    return out


def counted_shown(shown, grown):
    """Peloton's `shown` figure `grown` (0 to 1) of the way up from 0, with the same commas and decimals; `shown`
    itself once grown, or when it isn't a plain number."""
    if grown >= 1:
        return shown
    try:
        value = float(shown.replace(',', ''))
    except ValueError:
        return shown
    if not math.isfinite(value):
        return shown
    decimals = len(shown.split('.')[1]) if '.' in shown else 0
    return f'{value * grown:{"," if "," in shown else ""}.{decimals}f}'


def _text(matrix, font, x, y, color, text):
    graphics.DrawText(matrix, font, x, y, graphics.Color(*color), text)


def _centre(matrix, font, y, color, text):
    _text(matrix, font, max((matrix.width - get_text_width(font, text) + 1) // 2, 0), y, color, text)


def _centre_at(matrix, font, cx, y, color, text):
    _text(matrix, font, cx - (get_text_width(font, text) - 1) // 2, y, color, text)


def fitted_title(title, fonts, width):
    """(font, text) for the title: the first font it fits, else the last one with words dropped from the end
    (never a leading month, `NOV`), else cut to fit."""
    for font in fonts:
        if get_text_width(font, title) <= width:
            return font, title
    font, words = fonts[-1], title.split()
    keep = 2 if words[0] in MONTH_ABBREVIATIONS.values() else 1  # the month stays, and the word after it
    while len(words) > keep:
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
    animated = True
    atomic_frames = True
    frame_seconds = FRAME_SECONDS

    def __init__(self):
        self.elapsed = 0.0
        _ring_geometry()  # measured now, not during the first page's intro

    def on_enter(self, matrix, state=None):
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += max(0, dt)

    def render(self, matrix, state=None):
        if not valid_challenge(state) or state.get('next') is None:
            return False
        if matrix.height < 64:
            return self._render_short(matrix, state)
        fonts = loaded_fonts
        font, title = fitted_title(state['title'], [fonts['titles'], fonts['stats']], matrix.width)
        _centre(matrix, font, 8, GOLD, title)
        fraction = round(tier_progress(state), 3)
        grown = sweep(self.elapsed)
        shown_fraction = round(fraction * grown, 3)
        pixels = ring_pixels(shown_fraction, tier_color(state['next']['title']))
        for x, y, r, g, b in flashed(pixels, fraction, flash(self.elapsed)):
            matrix.SetPixel(x, y, r, g, b)
        cx = RING_CENTRE[0]
        font, final = ring_number(state['shown'])
        number = counted_shown(state['shown'], grown)
        if final != state['shown']:  # the final figure lost its comma, or went to `123K`: the count does too
            number = number.replace(',', '') if final == state['shown'].replace(',', '') else compact_number(number)
        _centre_at(matrix, font, cx, 36, WHITE, number)
        unit = state['unit']
        while unit and get_text_width(fonts['stats'], unit) > RING_UNIT_WIDTH:
            unit = unit[:-1]
        _centre_at(matrix, fonts['stats'], cx, 43, GREY, unit)
        _centre(matrix, fonts['stats'], 63, WHITE, remaining_line(state, fonts['stats'], matrix.width))
        return True

    def _render_short(self, matrix, state):
        small, large = loaded_fonts['info'], loaded_fonts['bold']
        font, title = fitted_title(state['title'], [small], matrix.width)
        _centre(matrix, font, 6, GOLD, title)
        grown = sweep(self.elapsed)
        compact = get_text_width(large, state['shown']) > 62
        number = counted_shown(state['shown'], grown)
        _centre(matrix, large, 18, WHITE, compact_number(number) if compact else number)
        left, right, top = 3, 60, 21
        bar = tier_color(state['next']['title'])
        filled = round((right - left + 1) * tier_progress(state) * grown)
        for x in range(left, right + 1):
            color = bar if x < left + filled else BAR_TRACK
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
