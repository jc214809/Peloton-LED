"""Pixel art the page draws: the PR trophy, the heart, the insight lightbulb and filled rectangles."""
from driver import graphics
from .colors import _INSIGHT_GOLD, _LABEL_GREY


# 7-wide × 7-tall pixel trophy marking PRs: 'C' gold cup, 'B' darker stem/base.
_TROPHY_ROWS = (
    "CCCCCCC",
    "C.CCC.C",
    ".CCCCC.",
    "..CCC..",
    "...B...",
    "...B...",
    "..BBB..",
)


_TROPHY_W = 7


_TROPHY_H = 7


_TROPHY_COLORS = {'C': (255, 215, 0), 'B': (205, 145, 0)}


def _draw_trophy(matrix, x: int, y: int) -> None:
    """Draw the PR trophy with its top-left at (x, y)."""
    for dy, row in enumerate(_TROPHY_ROWS):
        for dx, cell in enumerate(row):
            if cell in _TROPHY_COLORS:
                matrix.SetPixel(x + dx, y + dy, *_TROPHY_COLORS[cell])


# 7-wide × 6-tall pixel heart (offsets from top-left)
_HEART_PIXELS = [
    (1,0),(2,0),(4,0),(5,0),
    (0,1),(1,1),(2,1),(3,1),(4,1),(5,1),(6,1),
    (0,2),(1,2),(2,2),(3,2),(4,2),(5,2),(6,2),
    (1,3),(2,3),(3,3),(4,3),(5,3),
    (2,4),(3,4),(4,4),
    (3,5),
]


_HEART_W = 7


_HEART_H = 6


def _draw_heart(matrix, x: int, y: int, color: graphics.Color) -> None:
    """Draw a small pixel-art heart with its top-left at (x, y)."""
    r, g, b = color.red, color.green, color.blue
    for dx, dy in _HEART_PIXELS:
        matrix.SetPixel(x + dx, y + dy, r, g, b)


# The workout-compare lightbulb, 5x7: '#' gold, 'g' the grey base.
_BULB_ROWS = ('.###.', '#####', '#####', '#####', '.###.', '.ggg.', '..g..')


def _rect(matrix, x0: int, y0: int, x1: int, y1: int, rgb) -> None:
    for y in range(max(y0, 0), min(y1, matrix.height - 1) + 1):
        for x in range(max(x0, 0), min(x1, matrix.width - 1) + 1):
            matrix.SetPixel(x, y, *rgb)


def _draw_bulb(matrix, x: int, y: int) -> None:
    for dy, row in enumerate(_BULB_ROWS):
        for dx, cell in enumerate(row):
            if cell != '.':
                matrix.SetPixel(x + dx, y + dy, *(_INSIGHT_GOLD if cell == '#' else _LABEL_GREY))
