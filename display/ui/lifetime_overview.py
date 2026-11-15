"""Four separate discipline totals with larger, native pixel icons."""
from driver import graphics
from display.display import get_text_width, loaded_fonts
from .discipline_icons import DISCIPLINE_HEAD_SQUARES, DISCIPLINE_ICON_ROWS
from .screen import Screen

COLORS = {
    'cycling': (240, 70, 25), 'running': (30, 220, 90),
    'walking': (90, 210, 160), 'rowing': (0, 150, 255),
    'strength': (255, 150, 0), 'stretching': (0, 210, 190),
    'yoga': (185, 70, 230), 'meditation': (135, 110, 255),
    'cardio': (255, 65, 90),
}


# A bootcamp takes its machine's colour.
_COLOR_FAMILY = {'bike_bootcamp': 'cycling', 'tread_bootcamp': 'running', 'row_bootcamp': 'rowing'}


def discipline_color(key):
    """The (r, g, b) a discipline's icon is drawn in."""
    return COLORS.get(_COLOR_FAMILY.get(key, key), (200, 200, 235))


def draw_icon(matrix, key, left, top, color):
    """Draw a Peloton-inspired silhouette in a 26×24 pixel canvas."""
    def pixel(x, y):
        if 0 <= x < 26 and 0 <= y < 24:
            matrix.SetPixel(left + x, top + y, *color)

    def line(x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        error = dx + dy
        while True:
            pixel(x0, y0)
            if (x0, y0) == (x1, y1):
                break
            twice = 2 * error
            if twice >= dy:
                error += dy
                x0 += sx
            if twice <= dx:
                    error += dx
                    y0 += sy

    def thick_line(x0, y0, x1, y1, thickness=2):
        line(x0, y0, x1, y1)
        if thickness > 1:
            if abs(x1 - x0) >= abs(y1 - y0):
                line(x0, y0 + 1, x1, y1 + 1)
            else:
                line(x0 + 1, y0, x1 + 1, y1)

    def fill_rect(x0, y0, x1, y1):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                pixel(x, y)

    svg_key = {
        'dance_cardio': 'cardio',
        'running_outdoor': 'running',
        'walking_outdoor': 'walking',
    }.get(key, key)
    rows = DISCIPLINE_ICON_ROWS.get(svg_key)
    if rows:
        head = DISCIPLINE_HEAD_SQUARES.get(svg_key)
        for y, row in enumerate(rows):
            for x, value in enumerate(row):
                inside_head_clear = head and (
                    head[0] <= x <= head[2] and head[1] <= y <= head[3])
                if value == '#' and not inside_head_clear:
                    pixel(x, y)
        if head:
            _, _, _, _, square_x, square_y, size = head
            for offset in range(size):
                pixel(square_x + offset, square_y)
                pixel(square_x + offset, square_y + size - 1)
                pixel(square_x, square_y + offset)
                pixel(square_x + size - 1, square_y + offset)
        return

    def circle(cx, cy, radius, thickness=1):
        for r in range(radius, radius - thickness, -1):
            x, y, error = r, 0, 1 - r
            while x >= y:
                for dx, dy in ((x,y),(y,x),(-y,x),(-x,y),(-x,-y),(-y,-x),(y,-x),(x,-y)):
                    pixel(cx + dx, cy + dy)
                y += 1
                if error < 0:
                    error += 2 * y + 1
                else:
                    x -= 1
                    error += 2 * (y - x) + 1

    # Every discipline with bitmap rows returned above; these line drawings
    # cover the rest.
    if key in ('hiking', 'outdoor'):
        circle(8, 2, 2, thickness=2)
        thick_line(8, 5, 7, 12); thick_line(7, 7, 2, 11)
        thick_line(8, 7, 14, 10); thick_line(7, 12, 4, 20)
        thick_line(7, 12, 13, 19); thick_line(13, 19, 18, 19)
        thick_line(17, 7, 21, 0)
    elif key == 'boxing':
        circle(9, 3, 2, thickness=2)
        thick_line(9, 6, 8, 13); thick_line(8, 8, 14, 12)
        thick_line(8, 13, 3, 19); thick_line(3, 19, 10, 19)
        thick_line(8, 13, 16, 17); thick_line(16, 17, 21, 17)
        thick_line(14, 12, 19, 8)
        fill_rect(17, 6, 21, 8); fill_rect(16, 5, 17, 9); fill_rect(21, 5, 22, 9)
    elif key == 'mobility':
        circle(16, 4, 2, thickness=2)
        thick_line(15, 7, 11, 13); thick_line(11, 13, 4, 18)
        thick_line(11, 13, 19, 18); thick_line(15, 8, 8, 5)
        thick_line(8, 5, 3, 1)
        line(3, 1, 10, 0); line(10, 0, 18, 2); line(18, 2, 22, 7)
        line(1, 20, 23, 20)
    elif key in ('pilates', 'barre'):
        circle(13, 3, 2, thickness=2)
        thick_line(13, 6, 10, 14); thick_line(10, 14, 3, 19)
        thick_line(10, 14, 22, 19)
    else:
        for x in (2, 10, 18):
            for y in (1, 10):
                line(x,y,x+5,y)
                line(x,y,x,y+5)
                line(x+5,y,x+5,y+5)
                line(x,y+5,x+5,y+5)


def centered(matrix, font, text, left, width, y, color):
    graphics.DrawText(matrix, font, left + max(0, (width-get_text_width(font,text))//2),
                      y, graphics.Color(*color), text)


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
        white = (255,255,255)
        for index, item in enumerate(items[:4]):
            left, top = (index % 2)*32, (index//2)*30
            key = item.get('icon','')
            color = discipline_color(key)
            # Clear the icon area (labels are omitted so the icon can use
            # the full tile height) so counts remain steady across frames.
            for y in range(top, top+24):
                for x in range(left+3, left+29):
                    matrix.SetPixel(x,y,0,0,0)
            draw_icon(matrix,key,left+3,top,color)
            count = str(item['count'])
            if get_text_width(font,count) > 30:
                count = f"{item['count']/1000000:.1f}M" if item['count'] >= 1000000 else f"{item['count']/1000:.1f}K"
            centered(matrix,font,count,left,32,top+29,white)
        pages = state.get('pages',1)
        for index in range(pages):
            matrix.SetPixel(32 - (pages*3)//2 + index*3,matrix.height-1,
                            *((255,255,255) if index+1 == state.get('page',1) else (45,45,45)))
        return True
