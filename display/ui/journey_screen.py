"""Lifetime miles as a trip on a little map: start dot, route, castle at the end."""
from driver import graphics

from display.display import get_text_width, loaded_fonts
from .screen import Screen

# 7x7 castle for the destination: gold walls, pink tower tips.
CASTLE_ROWS = (
    "P..P..P",
    "G.GGG.G",
    "GGGGGGG",
    "GG.G.GG",
    "GGGGGGG",
    "GGG.GGG",
    "GGG.GGG",
)
CASTLE_COLORS = {'G': (255, 215, 0), 'P': (255, 110, 180)}
START_COLOR = (0, 150, 255)
ROUTE_COLOR = (60, 60, 70)
DONE_COLOR = (255, 140, 0)
YOU_COLOR = (255, 255, 255)
_GREY = graphics.Color(145, 165, 190)
_GOLD = graphics.Color(255, 215, 0)
_WHITE = graphics.Color(255, 255, 255)
_ORANGE = graphics.Color(255, 140, 0)


def draw_castle(matrix, x, y):
    for dy, row in enumerate(CASTLE_ROWS):
        for dx, cell in enumerate(row):
            if cell in CASTLE_COLORS:
                matrix.SetPixel(x + dx, y + dy, *CASTLE_COLORS[cell])


def _dot(matrix, cx, cy, color):
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            matrix.SetPixel(cx + dx, cy + dy, *color)


def _fit(font, text, width):
    while text and get_text_width(font, text) > width:
        text = text[:-1]
    return text.rstrip()


def _wrap(font, text, width):
    """Up to two lines of whole words; the second is trimmed if it overflows."""
    words, lines = text.split(), ['']
    for word in words:
        trial = f'{lines[-1]} {word}'.strip()
        if get_text_width(font, trial) <= width or not lines[-1]:
            lines[-1] = trial
        elif len(lines) < 2:
            lines.append(word)
        else:
            lines[-1] = trial
    return [_fit(font, line, width) for line in lines]


def _route_points(start, end, fraction, returning):
    """Pixel position of the rider between start and end (inclusive)."""
    along = 1 - fraction if returning else fraction
    return round(start + (end - start) * along)


def journey_text(progress):
    """(miles, status) strings shared by both layouts."""
    miles = f"{round(progress['miles']):,}"
    remaining = round(progress['route_miles'] - progress['leg_miles'])
    status = f'{remaining:,} TO HOME' if progress['returning'] else f'{remaining:,} TO GO'
    return miles, status


class JourneyScreen(Screen):
    """state: the dict from peloton.journey.journey_progress()."""

    def render(self, matrix, state=None):
        progress = state if isinstance(state, dict) else None
        small = loaded_fonts.get('stats') or loaded_fonts.get('info')
        big = loaded_fonts.get('big') or small
        if not progress or small is None or 'fraction' not in progress:
            return False
        miles, status = journey_text(progress)
        trip = progress.get('trip', 1)
        if matrix.height < 64:
            return self._render_short(matrix, progress, small, big, miles, status, trip)

        # Vertical route on the left: start at the top, castle at the bottom.
        x, top, bottom = 5, 4, 54
        for y in range(top, bottom + 1, 2):
            matrix.SetPixel(x, y, *ROUTE_COLOR)
        you = _route_points(top, bottom, progress['fraction'], progress['returning'])
        for y in range(top, you + 1) if not progress['returning'] else range(you, bottom + 1):
            matrix.SetPixel(x, y, *DONE_COLOR)
        _dot(matrix, x, top, START_COLOR)
        draw_castle(matrix, x - 3, bottom + 2)
        _dot(matrix, x, you, YOU_COLOR)

        # Text column to the right of the route.
        left, width = 13, matrix.width - 13 - 1
        graphics.DrawText(matrix, small, left, 8, _GREY, _fit(small, progress['from'].upper(), width))
        if trip > 1:
            graphics.DrawText(matrix, small, left, 15, _GREY, _fit(small, f'TRIP {trip}', width))
        graphics.DrawText(matrix, big if get_text_width(big, miles) <= width else small,
                          left, 35, _WHITE, miles)
        graphics.DrawText(matrix, small, left, 42, _WHITE, 'MILES')
        graphics.DrawText(matrix, small, left, 49, _ORANGE, _fit(small, status, width))
        lines = _wrap(small, progress['to'].upper(), width)
        for i, line in enumerate(lines):
            graphics.DrawText(matrix, small, left, 63 - (len(lines) - 1 - i) * 7, _GOLD, line)
        return True

    def _render_short(self, matrix, progress, small, big, miles, status, trip):
        w = matrix.width
        # Destination across the top (with trip number once past the first).
        # Heading names where you're headed: the destination, or home on the way back.
        place = progress['from'] if progress['returning'] else progress['to']
        graphics.DrawText(matrix, small, 2, 6, _GOLD, _fit(small, f'TO {place.upper()}', w - 4))
        # Miles big on the left; trip number (or percent) on the right if it fits.
        graphics.DrawText(matrix, big, 2, 17, _WHITE, miles)
        mi_x = 2 + get_text_width(big, miles) + 2
        graphics.DrawText(matrix, small, mi_x, 17, _WHITE, 'MI')
        right = f'TRIP {trip}' if trip > 1 else f"{round(progress['fraction'] * 100)}%"
        right_x = w - 2 - get_text_width(small, right)
        if right_x >= mi_x + get_text_width(small, 'MI') + 3:
            graphics.DrawText(matrix, small, right_x, 17, _GREY, right)
        graphics.DrawText(matrix, small, 2, 23, _ORANGE, _fit(small, status, w - 14))
        # Horizontal route along the bottom: start dot, castle at the right.
        y, start, end = 27, 3, w - 12
        for x in range(start, end + 1, 2):
            matrix.SetPixel(x, y, *ROUTE_COLOR)
        you = _route_points(start, end, progress['fraction'], progress['returning'])
        for x in range(start, you + 1) if not progress['returning'] else range(you, end + 1):
            matrix.SetPixel(x, y, *DONE_COLOR)
        _dot(matrix, start, y, START_COLOR)
        draw_castle(matrix, end + 3, y - 4)
        _dot(matrix, you, y, YOU_COLOR)
        return True
