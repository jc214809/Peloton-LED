"""Streaks: a pixel flame over the weekly streak and the best one, or the
daily streak and the day it started (one per rotation pass)."""
import math
from datetime import date

from driver import graphics

from display.display import get_text_width, loaded_fonts
from .screen import Screen

# The flame is drawn, not stored: three teardrop tongues (FLAME_LOBES) whose
# tips rise, fall and lean on smooth noise, with turbulence rising through
# them and a colour ramp from a deep-red rim to a pale-yellow core. The base
# stays put, so it flickers without wobbling. It fills a 12 x 16 box.
FLAME_W, FLAME_H = 12, 16
FLAME_FRAME_SECONDS = 0.05  # 20 fps, like the celebration
# (centre offset, bulb centre row, bulb half-width, bulb half-height,
#  highest tip row, how far the tip falls, noise seed): the middle tongue,
# then the left and right ones.
FLAME_LOBES = ((0.0, 10.4, 4.2, 6.0, -1.6, 2.4, 0.0),
               (-3.0, 11.2, 2.5, 4.2, 1.6, 3.4, 5.1),
               (3.0, 11.2, 2.5, 4.2, 1.0, 3.6, 9.7))
# Heat (0 to 1) to colour: deep red, red, orange, amber, yellow, pale yellow.
FLAME_RAMP = ((0.00, (90, 8, 0)), (0.22, (200, 30, 5)), (0.45, (245, 90, 0)),
              (0.70, (255, 170, 10)), (0.88, (255, 230, 70)), (1.00, (255, 250, 190)))
# A spark drifts up beside the tongues in some of these spans.
SPARK_SECONDS = 1.6
SPARK_RISE_SECONDS = 0.8
# A one-day "streak" is just today's workout; show the daily view from two.
MIN_DAILY_STREAK = 2
_ORANGE = graphics.Color(255, 140, 0)
_GREY = graphics.Color(145, 165, 190)
_GOLD = graphics.Color(255, 215, 0)
_WHITE = graphics.Color(255, 255, 255)


def _hash(ix, iy):
    """A repeatable 0..1 for a pair of whole numbers."""
    n = (ix * 374761393 + iy * 668265263) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 0xFFFF


def _noise(x, y):
    """Smooth 2D value noise, 0..1."""
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _hash(ix, iy), _hash(ix + 1, iy)
    c, d = _hash(ix, iy + 1), _hash(ix + 1, iy + 1)
    return (a + (b - a) * sx) * (1 - sy) + (c + (d - c) * sx) * sy


def flame_color(heat):
    heat = max(0.0, min(1.0, heat))
    for (h0, c0), (h1, c1) in zip(FLAME_RAMP, FLAME_RAMP[1:]):
        if heat <= h1:
            f = (heat - h0) / (h1 - h0)
            return tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
    return FLAME_RAMP[-1][1]


def _lobe_shapes(t):
    """Each lobe's (centre x, bulb row, half-width, half-height, tip row, lean) at time t."""
    shapes = []
    for ox, cy, rx, ry, tip, travel, seed in FLAME_LOBES:
        tip += travel * _noise(t * 1.9 + seed, seed) ** 1.6
        lean = 2.2 * (_noise(t * 1.4 + seed, seed + 3.3) - 0.5)
        shapes.append(((FLAME_W - 1) / 2 + ox, cy, rx, ry, tip, lean))
    return shapes


def _inside(x, yc, shape):
    """(1 on the lobe's axis down to 0 at its edge, negative outside; how far up its tongue, 0..1)."""
    centre, cy, rx, ry, tip, lean = shape
    if yc >= cy:
        k = (yc - cy) / ry
        if k >= 1:
            return -1.0, 0.0
        width, up = rx * math.sqrt(1 - k * k), 0.0
    else:
        up = (cy - yc) / (cy - tip)
        if up >= 1:
            return -1.0, 1.0
        width = rx * (1 - up) ** 1.2
    d = abs(x - centre - lean * up * up) / max(width, 0.01)
    return 1 - d * d, up


def _spark(t):
    """(x, y, heat) of the spark rising at time t, or None."""
    span = math.floor(t / SPARK_SECONDS)
    rise = (t - span * SPARK_SECONDS) / SPARK_RISE_SECONDS
    if rise >= 1 or _hash(span, 77) < 0.35:
        return None
    x = 2 + int(_hash(span, 91) * (FLAME_W - 4))
    return x, round(6 - 6 * rise), 0.75 - 0.6 * rise


def flame_pixels(t=0.0):
    """{(dx, dy): (r, g, b)} for the flame `t` seconds into a page."""
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0:
        t = 0.0
    t %= 3600  # a page never runs this long; keeps the noise inputs small
    shapes = _lobe_shapes(t)
    pixels = {}
    for y in range(FLAME_H):
        yc = y + 0.5
        for x in range(FLAME_W):
            inside, up = max(_inside(x, yc, shape) for shape in shapes)
            if inside <= -0.5:
                continue
            # Rising turbulence eats into the edges, more so up the tongues.
            n = _noise(x * 0.7, y * 0.5 + t * 7.0) * 0.6 + _noise(x * 1.4 + 7, y * 1.2 + t * 12.0) * 0.4
            edge = inside - (n - 0.45) * (0.25 + 0.8 * up)
            if edge <= 0.07:
                continue
            # Hottest low in the middle; the rim and the tips stay red.
            core = max(0.0, 1 - math.hypot((x - (FLAME_W - 1) / 2) / 4.0, (yc - 11.2) / 4.5))
            pixels[(x, y)] = flame_color(0.05 + edge * 0.5 + core * 0.65 - 0.2 * up)
    spark = _spark(t)
    if spark and (spark[0], spark[1]) not in pixels:
        pixels[(spark[0], spark[1])] = flame_color(spark[2])
    return pixels


def draw_flame(matrix, x, y, t=0.0):
    for (dx, dy), rgb in flame_pixels(t).items():
        matrix.SetPixel(x + dx, y + dy, *rgb)


class FlickeringFlame:
    """Mixin for a screen with a flame: animated, and the time on the page
    the flame is drawn at (`self.flame`)."""

    animated = True
    atomic_frames = True
    frame_seconds = FLAME_FRAME_SECONDS

    def __init__(self):
        self.elapsed = 0.0

    def on_enter(self, matrix, state=None):
        self.elapsed = 0.0

    def update(self, dt):
        if isinstance(dt, (int, float)) and dt > 0:
            self.elapsed += dt

    @property
    def flame(self):
        return self.elapsed


def streak_lines(streaks):
    """(current, label, footer, footer_is_record) or None when there's no streak."""
    current = (streaks or {}).get('current_weekly')
    if not isinstance(current, int) or current <= 0:
        return None
    best = streaks.get('best_weekly')
    label = 'WEEK STREAK'
    if isinstance(best, int) and current >= best:
        return current, label, 'PERSONAL BEST', True
    if isinstance(best, int):
        return current, label, f'BEST {best:,} WEEKS', False
    return current, label, '', False


def since_text(start, today):
    """'SINCE OCT 30' within the last year, 'SINCE DEC 2024' before that."""
    month = start.strftime('%b').upper()
    if (today - start).days < 365:
        return f'SINCE {month} {start.day}'
    return f'SINCE {month} {start.year}'


def daily_streak_lines(streaks):
    """(current, label, footer, False) for a daily streak of MIN_DAILY_STREAK
    days or more, else None. The footer needs 'daily_start' and 'today'
    (ISO dates) in the dict; Peloton reports no best daily streak."""
    current = (streaks or {}).get('current_daily')
    if not isinstance(current, int) or isinstance(current, bool) or current < MIN_DAILY_STREAK:
        return None
    footer = ''
    try:
        footer = since_text(date.fromisoformat(streaks['daily_start']),
                            date.fromisoformat(streaks['today']))
    except (KeyError, TypeError, ValueError):
        pass
    return current, 'DAY STREAK', footer, False


def streak_views(streaks):
    """[(view, lines)] for the views there is something to show: 'weekly'
    first, then 'daily'. The rotation shows one per pass, alternating."""
    views = (('weekly', streak_lines(streaks)), ('daily', daily_streak_lines(streaks)))
    return [(view, lines) for view, lines in views if lines]


class StreakScreen(FlickeringFlame, Screen):
    """state is the snapshot's 'streaks' dict (see peloton.stats.totals.parse_streaks),
    plus 'daily_start' and 'today' for the daily footer and 'view' ('weekly'
    or 'daily'). Without a 'view', or when that one has nothing to show, the
    first available view is drawn. The flame burns (`flame_pixels`)."""

    def render(self, matrix, state=None):
        state = state if isinstance(state, dict) else {}
        views = dict(streak_views(state))
        lines = views.get(state.get('view')) or next(iter(views.values()), None)
        big = loaded_fonts.get('big')
        small = loaded_fonts.get('stats') or loaded_fonts.get('info')
        label_font = loaded_fonts.get('titles') or small
        if lines is None or big is None or small is None:
            return False
        current, label, footer, record = lines
        w = matrix.width
        number = f'{current:,}'
        if matrix.height < 64:
            # Flame and number side by side on top, then label and footer.
            gap = 3
            group = FLAME_W + gap + get_text_width(big, number)
            left = max((w - group) // 2, 1)
            draw_flame(matrix, left, 0, self.flame)
            graphics.DrawText(matrix, big, left + FLAME_W + gap, 13, _WHITE, number)
            y_label, y_footer = 23, 30
        else:
            draw_flame(matrix, (w - FLAME_W) // 2, 3, self.flame)
            x = max((w - get_text_width(big, number)) // 2, 1)
            graphics.DrawText(matrix, big, x, 39, _WHITE, number)
            y_label, y_footer = 50, 60
        x = max((w - get_text_width(label_font, label)) // 2, 1)
        graphics.DrawText(matrix, label_font, x, y_label, _ORANGE, label)
        if footer:
            if get_text_width(small, footer) > w - 2:
                footer = footer.replace(' WEEKS', '').replace('SINCE ', '')
            x = max((w - get_text_width(small, footer)) // 2, 1)
            graphics.DrawText(matrix, small, x, y_footer, _GOLD if record else _GREY, footer)
        return True
