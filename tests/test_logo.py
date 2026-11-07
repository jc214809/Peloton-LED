"""The board's logo: the startup screen, the settings page's icons and the docs images, all drawn
from display/ui/logo_art.py."""
import io
import re

import pytest
from PIL import Image

from display import display as display_module
from display.display import initialize_fonts
from display.ui.last_workout_screen import HR_ZONE_COLORS
from display.ui.logo_art import LABEL_GREY, MARK_HEIGHT, MARK_WIDTH, PELOTON_RED, ZONE_COLORS, mark_pixels, zone_color
from display.ui.logo_mask_screen import WHITE, LogoMaskScreen
from scripts import render_logo
from scripts.render_demo import ImageMatrix
from settings_page import logo, page

BLACK = (0, 0, 0)
# Where each layout puts the mark, and the zone bar's left, top, width and height.
LAYOUTS = {64: ((20, 2), (9, 45, 46, 3)), 32: ((1, 2), (27, 15, 35, 2))}


def drawn(width, height):
    matrix = ImageMatrix(width, height)
    assert LogoMaskScreen().render(matrix)
    return matrix.image


def colours_at(image, xs, ys):
    return {image.getpixel((x, y)) for x in xs for y in ys}


@pytest.mark.parametrize('height', [32, 64])
def test_the_startup_logo_is_the_mark_words_and_zone_bar(height):
    initialize_fonts(height)
    image = drawn(64, height)
    (mark_x, mark_y), (bar_x, bar_y, bar_w, bar_h) = LAYOUTS[height]
    mark = set(mark_pixels(mark_x, mark_y))
    assert {image.getpixel(xy) for xy in mark} == {PELOTON_RED}
    red = {(x, y) for x in range(64) for y in range(height) if image.getpixel((x, y)) == PELOTON_RED}
    assert red == mark, 'nothing else is red'
    for i in range(bar_w):
        assert colours_at(image, [bar_x + i], range(bar_y, bar_y + bar_h)) == {zone_color(i, bar_w)}
    assert [image.getpixel((bar_x + i, bar_y)) for i in (0, bar_w - 1)] == [ZONE_COLORS[0], ZONE_COLORS[4]]
    colours = {colour for _, colour in image.getcolors(64 * 64)}
    assert colours == {BLACK, PELOTON_RED, WHITE, LABEL_GREY, *ZONE_COLORS}, 'PELOTON white, L E D grey'


def test_the_tall_layout_stacks_and_the_short_one_sits_beside_the_mark():
    initialize_fonts(64)
    tall = drawn(64, 64)
    words = {y for x in range(64) for y in range(64) if tall.getpixel((x, y)) in (WHITE, LABEL_GREY)}
    assert min(words) > 2 + MARK_HEIGHT, 'below the mark'
    initialize_fonts(32)
    short = drawn(64, 32)
    words = {x for x in range(64) for y in range(32) if short.getpixel((x, y)) in (WHITE, LABEL_GREY)}
    assert min(words) > 1 + MARK_WIDTH and max(words) <= 63, 'beside the mark, on the panel'


def test_a_wider_panel_centres_the_logo():
    initialize_fonts(64)
    wide, narrow = drawn(128, 64), drawn(64, 64)
    assert wide.crop((32, 0, 96, 64)).tobytes() == narrow.tobytes()
    assert colours_at(wide, range(32), range(64)) == {BLACK}


def test_without_fonts_the_mark_and_bar_still_show(monkeypatch):
    monkeypatch.setattr(display_module, 'loaded_fonts', {})
    monkeypatch.setattr('display.ui.logo_mask_screen.loaded_fonts', {})
    image = drawn(64, 64)
    assert {colour for _, colour in image.getcolors(64 * 64)} == {BLACK, PELOTON_RED, *ZONE_COLORS}


def test_the_zone_bar_is_five_equal_bands_in_the_workout_pages_colours():
    assert HR_ZONE_COLORS == list(ZONE_COLORS)
    assert [zone_color(i, 5) for i in range(5)] == list(ZONE_COLORS)
    assert [zone_color(i, 10) for i in range(10)] == [c for c in ZONE_COLORS for _ in range(2)]


def test_the_settings_icon_svg_has_every_pixel_once():
    svg = logo.svg()
    lit = set()
    for x, y, w, fill in re.findall(r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="1" fill="(#\w+)"/>', svg):
        for i in range(int(w)):
            xy = (int(x) + i, int(y))
            assert xy not in lit
            lit.add(xy)
    assert lit == {xy for xy, _ in logo.pixels()}
    colours = dict(logo.pixels())
    for x, y, _, fill in re.findall(r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="1" fill="(#\w+)"/>', svg):
        assert fill == '#%02x%02x%02x' % colours[(int(x), int(y))]
    assert all(0 <= x < logo.SIZE and 0 <= y < logo.SIZE for x, y in lit)
    assert 'rx=' not in svg and 'rx="7"' in logo.svg(rounded=True)


def test_the_favicon_is_the_rounded_svg_as_a_data_url():
    href = logo.favicon_href()
    assert href.startswith('data:image/svg+xml,%3Csvg') and '"' not in href and ' ' not in href


def test_the_home_screen_icon_is_a_180_pixel_png_of_the_same_pixels():
    image = Image.open(io.BytesIO(logo.touch_icon_png()))
    assert image.format == 'PNG' and image.size == (180, 180)
    scale = logo.TOUCH_ICON_SCALE
    for (x, y), rgb in logo.pixels():
        assert image.getpixel((x * scale + 2, y * scale + 2)) == rgb
    assert image.getpixel((0, 0)) == logo.BACKGROUND


def test_every_settings_page_shows_the_icon():
    html = page.message_page('Not found', 'Nothing here.')
    assert f'<link rel="icon" type="image/svg+xml" href="{logo.favicon_href()}">' in html
    assert f'<link rel="apple-touch-icon" href="{page.TOUCH_ICON}">' in html
    pin = page.pin_page()
    assert f'<span class="mark">{logo.svg()}</span>' in pin
    rule = re.search(r'^\.mark svg \{[^}]*\}', page.STYLE, re.M).group()
    assert 'stroke: none' in rule, "the page's line icons are stroked: the logo mustn't be"


def test_render_logo_writes_the_docs_images(tmp_path, capsys):
    wordmark, startup = tmp_path / 'logo.png', tmp_path / 'startup.png'
    render_logo.main(['--wordmark', str(wordmark), '--startup', str(startup)])
    image = Image.open(wordmark).convert('RGB')
    assert image.width % render_logo.WORDMARK_SCALE == 0 and image.width > image.height
    assert PELOTON_RED in {c for _, c in image.getcolors(image.width * image.height)}
    sheet = Image.open(startup).convert('RGB')
    assert sheet.width == render_logo.LABEL_WIDTH + 64 * 3 + render_logo.GAP
    top = render_logo.GAP
    initialize_fonts(64)
    panel = sheet.crop((render_logo.LABEL_WIDTH, top, render_logo.LABEL_WIDTH + 192, top + 192))
    assert panel.tobytes() == drawn(64, 64).resize((192, 192), Image.NEAREST).tobytes()
    assert 'Wrote' in capsys.readouterr().out
