"""Startup logo: the Peloton mark, PELOTON, a heart-rate zone bar and LED, drawn pixel by pixel
with the board's own fonts (no image decoding).

A 64-row panel stacks them; a shorter one puts the mark on the left and the rest beside it.
Without fonts loaded (initialize_fonts) the words are left out.
"""
from driver import graphics

from display.display import get_text_width, loaded_fonts

from .logo_art import LABEL_GREY, MARK_WIDTH, PELOTON_RED, mark_pixels, zone_color
from .screen import Screen

WHITE = (255, 255, 255)
# The panel the layouts are drawn for; a wider one centres them.
LAYOUT_WIDTH = 64
TALL = 64


class LogoMaskScreen(Screen):
    # One static frame, composed off-screen so it appears all at once.
    animated = False
    atomic_frames = True

    def render(self, matrix, state=None):
        left = max(0, (matrix.width - LAYOUT_WIDTH) // 2)
        if matrix.height >= TALL:
            self._tall(matrix, left)
        else:
            self._wide(matrix, left)
        return True

    @staticmethod
    def _tall(matrix, left):
        _mark(matrix, left + (LAYOUT_WIDTH - MARK_WIDTH) // 2, 2)
        _words(matrix, 'discipline', left, LAYOUT_WIDTH, 41, WHITE, 'PELOTON')
        _zone_bar(matrix, left + 9, 45, 46, 3)
        _words(matrix, 'titles', left, LAYOUT_WIDTH, 59, LABEL_GREY, 'L E D')

    @staticmethod
    def _wide(matrix, left):
        _mark(matrix, left + 1, 2)
        # Beside the mark: columns 27 to 63.
        _words(matrix, 'discipline', left + 27, 37, 12, WHITE, 'PELOTON')
        _zone_bar(matrix, left + 27, 15, 35, 2)
        _words(matrix, 'info', left + 27, 37, 26, LABEL_GREY, 'L E D')


def _mark(matrix, left, top):
    for x, y in mark_pixels(left, top):
        if 0 <= x < matrix.width and 0 <= y < matrix.height:
            matrix.SetPixel(x, y, *PELOTON_RED)


def _zone_bar(matrix, left, top, width, height):
    for i in range(width):
        for j in range(height):
            matrix.SetPixel(left + i, top + j, *zone_color(i, width))


def _words(matrix, font_key, left, width, baseline, rgb, text):
    """Text centred in the `width` columns from `left`, in the loaded font font_key; nothing if it isn't loaded."""
    font = loaded_fonts.get(font_key)
    if font is None:
        return
    graphics.DrawText(matrix, font, left + (width - get_text_width(font, text)) // 2, baseline, graphics.Color(*rgb), text)
