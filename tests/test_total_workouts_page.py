"""Total Workouts: a big gold count under the title, on both panel sizes."""
import unittest  # noqa: F401  (selects emulator graphics)

import pytest

from display.display import initialize_fonts
from display.ui.discipline_page import DisciplinePageScreen
from peloton.config import DEFAULTS
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix

GOLD, WHITE = (255, 215, 0), (255, 255, 255)


def _page(total, height):
    snapshot = {'summaries': [], 'totals': {'Total Workouts': total}, 'me': {}, 'streaks': {}}
    pages = build_rotation_pages(snapshot, None, {**DEFAULTS, 'rotation': ['total_workouts'],
                                                  'color': 'white'}, 'Rider', height)
    return next(state for name, state, _ in pages if name == 'discipline')


def _colors(image, top, bottom):
    return {image.getpixel((x, y)) for x in range(64) for y in range(top, bottom)} - {(0, 0, 0)}


def test_total_page_asks_for_the_big_gold_number():
    state = _page(2123, 64)
    assert state['number_font_key'] == 'big' and state['number_color_key'] == 'gold'
    assert state['color_key'] == 'white'


@pytest.mark.parametrize('height,split', [(64, 38), (32, 19)])
@pytest.mark.parametrize('total', [987, 2123, 12345, 123456])
def test_title_keeps_its_color_and_the_count_is_gold_and_on_screen(height, split, total):
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    assert DisciplinePageScreen().render(matrix, _page(total, height))
    image = matrix.image
    assert _colors(image, 0, split) == {WHITE}
    assert _colors(image, split, height) == {GOLD}
    left, top, right, bottom = image.getbbox()
    assert left >= 1 and right <= 63 and bottom <= height


@pytest.mark.parametrize('height,minimum', [(64, 14), (32, 9)])
def test_count_is_taller_than_the_old_number_font(height, minimum):
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    DisciplinePageScreen().render(matrix, _page(2123, height))
    gold_rows = [y for y in range(height)
                 if any(matrix.image.getpixel((x, y)) == GOLD for x in range(64))]
    assert max(gold_rows) - min(gold_rows) + 1 >= minimum


def test_other_discipline_pages_are_unchanged():
    initialize_fonts(32)
    matrix = ImageMatrix(height=32)
    DisciplinePageScreen().render(matrix, {'discipline': 'Cycling', 'count': 400, 'color_key': 'white'})
    assert _colors(matrix.image, 0, 32) == {WHITE}
