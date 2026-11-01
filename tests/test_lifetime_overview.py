"""Line-drawn icons for disciplines without bitmap masks, and count formatting."""
import unittest  # noqa: F401  (selects emulator graphics)

import pytest

from display.display import initialize_fonts
from display.ui.discipline_icons import DISCIPLINE_ICON_ROWS
from display.ui.lifetime_overview import LifetimeOverviewScreen, draw_icon
from scripts.render_demo import ImageMatrix

LINE_DRAWN = ['hiking', 'outdoor', 'boxing', 'mobility', 'pilates', 'barre']


def _icon(key):
    matrix = ImageMatrix(height=64)
    draw_icon(matrix, key, 0, 0, (255, 255, 255))
    return matrix.image.crop((0, 0, 26, 24))


@pytest.mark.parametrize('key', LINE_DRAWN)
def test_line_drawn_icons_draw_inside_their_tile(key):
    assert key not in DISCIPLINE_ICON_ROWS
    icon = _icon(key)
    assert icon.getbbox() is not None
    # Nothing spills outside the 26x24 canvas.
    matrix = ImageMatrix(height=64)
    draw_icon(matrix, key, 0, 0, (255, 255, 255))
    assert matrix.image.crop((26, 0, 64, 64)).getbbox() is None
    assert matrix.image.crop((0, 24, 64, 64)).getbbox() is None


def test_line_drawn_icons_are_distinct_except_aliases():
    shapes = {key: _icon(key).tobytes() for key in LINE_DRAWN}
    assert shapes['hiking'] == shapes['outdoor']
    assert shapes['pilates'] == shapes['barre']
    assert len({shapes[k] for k in ('hiking', 'boxing', 'mobility', 'pilates')}) == 4


def test_unknown_discipline_gets_the_grid_placeholder():
    icon = _icon('underwater_basket_weaving')
    assert icon.getbbox() == (2, 1, 24, 16)
    assert icon.tobytes() == _icon('').tobytes()


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('count,expected', [(42, '42'), (999999, '999999'), (2500000, '2500000'), (12345678, '12.3M')])
def test_large_counts_are_abbreviated_to_fit(height, count, expected):
    initialize_fonts(height)
    shown = []
    from display.ui import lifetime_overview
    original = lifetime_overview.centered
    lifetime_overview.centered = lambda m, f, text, *a: shown.append(text)
    try:
        assert LifetimeOverviewScreen().render(ImageMatrix(height=height),
                                               {'items': [{'icon': 'cycling', 'count': count}]})
    finally:
        lifetime_overview.centered = original
    assert shown == [expected]


def test_only_four_tiles_and_a_page_dot_per_page():
    initialize_fonts(64)
    matrix = ImageMatrix(height=64)
    items = [{'icon': key, 'count': 1} for key in ('cycling', 'running', 'yoga', 'boxing', 'pilates')]
    assert LifetimeOverviewScreen().render(matrix, {'items': items, 'page': 2, 'pages': 3})
    dots = [matrix.image.getpixel((32 - 9 // 2 + i * 3, 63)) for i in range(3)]
    assert dots == [(45, 45, 45), (255, 255, 255), (45, 45, 45)]


@pytest.mark.parametrize('state', [None, {}, {'items': []}])
def test_nothing_to_draw_returns_false(state):
    initialize_fonts(64)
    assert LifetimeOverviewScreen().render(ImageMatrix(height=64), state) is False
