"""The settings page's icon, drawn from the board's logo (display/ui/logo_art.py): the Peloton mark
over a heart-rate zone bar, on a 36x36 pixel grid with room for rounded corners.

As SVG for the page header and the browser tab (inline, so no request), and as a PNG for a phone's
home screen (/apple-touch-icon.png: iOS won't take an SVG there).
"""
import functools
import io
from urllib.parse import quote

from display.ui.logo_art import PELOTON_RED, mark_pixels, zone_color

SIZE = 36
BACKGROUND = (11, 13, 18)
TOUCH_ICON_SCALE = 5  # 180x180, the size iOS asks for
MARK_AT = (6, 2)
BAR_AT, BAR_WIDTH, BAR_HEIGHT = (7, 32), 22, 2


def pixels():
    """Each lit pixel as ((x, y), rgb)."""
    found = [(xy, PELOTON_RED) for xy in mark_pixels(*MARK_AT)]
    left, top = BAR_AT
    found += [((left + i, top + j), zone_color(i, BAR_WIDTH))
              for i in range(BAR_WIDTH) for j in range(BAR_HEIGHT)]
    return found


def _hex(rgb):
    return '#%02x%02x%02x' % rgb


@functools.lru_cache(maxsize=None)
def svg(rounded=False):
    """The icon as SVG, one rect per run of same-coloured pixels in a row. rounded: its own rounded
    background, for the browser tab (the page header rounds it with CSS)."""
    by_row = {}
    for (x, y), rgb in pixels():
        by_row.setdefault(y, {})[x] = rgb
    rects = []
    for y, row in sorted(by_row.items()):
        xs = sorted(row)
        start = xs[0]
        for i, x in enumerate(xs):
            following = xs[i + 1] if i + 1 < len(xs) else None
            if following != x + 1 or row[following] != row[x]:
                rects.append(f'<rect x="{start}" y="{y}" width="{x - start + 1}" height="1" fill="{_hex(row[x])}"/>')
                start = following
    corner = ' rx="7"' if rounded else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" shape-rendering="crispEdges" '
            f'aria-hidden="true"><rect width="{SIZE}" height="{SIZE}"{corner} fill="{_hex(BACKGROUND)}"/>'
            + ''.join(rects) + '</svg>')


def favicon_href():
    """The browser-tab icon as a data: URL."""
    return 'data:image/svg+xml,' + quote(svg(rounded=True))


@functools.lru_cache(maxsize=None)
def touch_icon_png():
    """The home-screen icon: a square PNG (the phone rounds its corners), each pixel 5x5."""
    from PIL import Image  # only this route needs Pillow

    image = Image.new('RGB', (SIZE, SIZE), BACKGROUND)
    for xy, rgb in pixels():
        image.putpixel(xy, rgb)
    image = image.resize((SIZE * TOUCH_ICON_SCALE,) * 2, Image.NEAREST)
    out = io.BytesIO()
    image.save(out, 'PNG')
    return out.getvalue()
