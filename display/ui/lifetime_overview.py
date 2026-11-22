"""Four separate discipline totals with larger, native pixel icons."""

from display.display import get_text_width, loaded_fonts
from driver import graphics

from .discipline_icons import DISCIPLINE_HEAD_SQUARES, DISCIPLINE_ICON_ROWS
from .screen import Screen

COLORS = {
    'cycling': (240, 70, 25),
    'running': (30, 220, 90),
    'walking': (90, 210, 160),
    'rowing': (0, 150, 255),
    'strength': (255, 150, 0),
    'stretching': (0, 210, 190),
    'yoga': (185, 70, 230),
    'meditation': (135, 110, 255),
    'cardio': (255, 65, 90),
}


# A bootcamp takes its machine's colour.
_COLOR_FAMILY = {'bike_bootcamp': 'cycling', 'tread_bootcamp': 'running', 'row_bootcamp': 'rowing'}


def discipline_color(key):
    """The (r, g, b) a discipline's icon is drawn in."""
    return COLORS.get(_COLOR_FAMILY.get(key, key), (200, 200, 235))


class _Pen:
    """Pixel, line, rectangle and circle drawing clipped to one 26x24 icon canvas."""

    def __init__(self, matrix, left, top, color):
        self.matrix, self.left, self.top, self.color = matrix, left, top, color

    def pixel(self, x, y):
        if 0 <= x < 26 and 0 <= y < 24:
            self.matrix.SetPixel(self.left + x, self.top + y, *self.color)

    def line(self, x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        error = dx + dy
        while True:
            self.pixel(x0, y0)
            if (x0, y0) == (x1, y1):
                break
            twice = 2 * error
            if twice >= dy:
                error += dy
                x0 += sx
            if twice <= dx:
                error += dx
                y0 += sy

    def thick_line(self, x0, y0, x1, y1, thickness=2):
        self.line(x0, y0, x1, y1)
        if thickness > 1:
            if abs(x1 - x0) >= abs(y1 - y0):
                self.line(x0, y0 + 1, x1, y1 + 1)
            else:
                self.line(x0 + 1, y0, x1 + 1, y1)

    def fill_rect(self, x0, y0, x1, y1):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.pixel(x, y)

    def circle(self, cx, cy, radius, thickness=1):
        for r in range(radius, radius - thickness, -1):
            x, y, error = r, 0, 1 - r
            while x >= y:
                for dx, dy in ((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)):
                    self.pixel(cx + dx, cy + dy)
                y += 1
                if error < 0:
                    error += 2 * y + 1
                else:
                    x -= 1
                    error += 2 * (y - x) + 1


# A discipline whose bitmap lives under another key.
_BITMAP_ALIAS = {
    'dance_cardio': 'cardio',
    'running_outdoor': 'running',
    'walking_outdoor': 'walking',
}


def _draw_bitmap(pen, rows, head):
    """Draw a bitmap icon; a head square gets its box cleared, then outlined."""
    for y, row in enumerate(rows):
        for x, value in enumerate(row):
            inside_head_clear = head and (head[0] <= x <= head[2] and head[1] <= y <= head[3])
            if value == '#' and not inside_head_clear:
                pen.pixel(x, y)
    if head:
        _, _, _, _, square_x, square_y, size = head
        for offset in range(size):
            pen.pixel(square_x + offset, square_y)
            pen.pixel(square_x + offset, square_y + size - 1)
            pen.pixel(square_x, square_y + offset)
            pen.pixel(square_x + size - 1, square_y + offset)


def _draw_hiking(pen):
    pen.circle(8, 2, 2, thickness=2)
    pen.thick_line(8, 5, 7, 12)
    pen.thick_line(7, 7, 2, 11)
    pen.thick_line(8, 7, 14, 10)
    pen.thick_line(7, 12, 4, 20)
    pen.thick_line(7, 12, 13, 19)
    pen.thick_line(13, 19, 18, 19)
    pen.thick_line(17, 7, 21, 0)


def _draw_boxing(pen):
    pen.circle(9, 3, 2, thickness=2)
    pen.thick_line(9, 6, 8, 13)
    pen.thick_line(8, 8, 14, 12)
    pen.thick_line(8, 13, 3, 19)
    pen.thick_line(3, 19, 10, 19)
    pen.thick_line(8, 13, 16, 17)
    pen.thick_line(16, 17, 21, 17)
    pen.thick_line(14, 12, 19, 8)
    pen.fill_rect(17, 6, 21, 8)
    pen.fill_rect(16, 5, 17, 9)
    pen.fill_rect(21, 5, 22, 9)


def _draw_mobility(pen):
    pen.circle(16, 4, 2, thickness=2)
    pen.thick_line(15, 7, 11, 13)
    pen.thick_line(11, 13, 4, 18)
    pen.thick_line(11, 13, 19, 18)
    pen.thick_line(15, 8, 8, 5)
    pen.thick_line(8, 5, 3, 1)
    pen.line(3, 1, 10, 0)
    pen.line(10, 0, 18, 2)
    pen.line(18, 2, 22, 7)
    pen.line(1, 20, 23, 20)


def _draw_pilates(pen):
    pen.circle(13, 3, 2, thickness=2)
    pen.thick_line(13, 6, 10, 14)
    pen.thick_line(10, 14, 3, 19)
    pen.thick_line(10, 14, 22, 19)


def _draw_placeholder(pen):
    """The grid of four boxes an unknown discipline gets."""
    for x in (2, 10, 18):
        for y in (1, 10):
            pen.line(x, y, x + 5, y)
            pen.line(x, y, x, y + 5)
            pen.line(x + 5, y, x + 5, y + 5)
            pen.line(x, y + 5, x + 5, y + 5)


# Disciplines with no bitmap rows are line drawings.
_LINE_DRAWINGS = {
    'hiking': _draw_hiking,
    'outdoor': _draw_hiking,
    'boxing': _draw_boxing,
    'mobility': _draw_mobility,
    'pilates': _draw_pilates,
    'barre': _draw_pilates,
}


def draw_icon(matrix, key, left, top, color):
    """Draw a Peloton-inspired silhouette in a 26×24 pixel canvas."""
    pen = _Pen(matrix, left, top, color)
    bitmap_key = _BITMAP_ALIAS.get(key, key)
    rows = DISCIPLINE_ICON_ROWS.get(bitmap_key)
    if rows:
        _draw_bitmap(pen, rows, DISCIPLINE_HEAD_SQUARES.get(bitmap_key))
        return
    _LINE_DRAWINGS.get(key, _draw_placeholder)(pen)


def centered(matrix, font, text, left, width, y, color):
    graphics.DrawText(matrix, font, left + max(0, (width - get_text_width(font, text)) // 2), y, graphics.Color(*color), text)


class LifetimeOverviewScreen(Screen):
    # Compose the complete static page off-screen, then swap it in at once.
    animated = False
    atomic_frames = True

    def render(self, matrix, state=None):
        state = state or {}
        items = state.get('items') or []
        font = loaded_fonts.get('stats')
        if not items or font is None:
            return False
        white = (255, 255, 255)
        for index, item in enumerate(items[:4]):
            left, top = (index % 2) * 32, (index // 2) * 30
            key = item.get('icon', '')
            color = discipline_color(key)
            # Clear the icon area (labels are omitted so the icon can use
            # the full tile height) so counts remain steady across frames.
            for y in range(top, top + 24):
                for x in range(left + 3, left + 29):
                    matrix.SetPixel(x, y, 0, 0, 0)
            draw_icon(matrix, key, left + 3, top, color)
            count = str(item['count'])
            if get_text_width(font, count) > 30:
                count = f'{item["count"] / 1000000:.1f}M' if item['count'] >= 1000000 else f'{item["count"] / 1000:.1f}K'
            centered(matrix, font, count, left, 32, top + 29, white)
        pages = state.get('pages', 1)
        for index in range(pages):
            matrix.SetPixel(
                32 - (pages * 3) // 2 + index * 3,
                matrix.height - 1,
                *((255, 255, 255) if index + 1 == state.get('page', 1) else (45, 45, 45)),
            )
        return True
