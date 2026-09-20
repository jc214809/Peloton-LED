"""Startup logo drawn straight from a pixel mask, with no image decoding."""
from .logo_art import LOGO_ROWS, LOGO_ROWS_32
from .screen import Screen


class LogoMaskScreen(Screen):
    # One static frame, composed off-screen so it appears all at once.
    animated = False
    atomic_frames = True

    def __init__(self, rows=None, color=(255, 255, 255)):
        self.rows = rows
        self.color = color

    def _rows_for(self, matrix):
        if self.rows is not None:
            return self.rows
        # Prefer the tallest hand-drawn mask that fits, so a short panel uses
        # art drawn for it rather than a downsample of the 64-row version.
        for candidate in (LOGO_ROWS, LOGO_ROWS_32):
            if len(candidate) <= matrix.height:
                return candidate
        return LOGO_ROWS_32

    def render(self, matrix, state=None):
        rows = self._rows_for(matrix)
        if not rows:
            return False
        art_h = len(rows)
        art_w = max(len(row) for row in rows)
        # Whole-number downscale keeps the mask crisp on shorter panels;
        # a 64-row mask becomes every other pixel on a 32-row board.
        step = max(1, -(-art_h // matrix.height), -(-art_w // matrix.width))
        draw_h = -(-art_h // step)
        draw_w = -(-art_w // step)
        left = max(0, (matrix.width - draw_w) // 2)
        top = max(0, (matrix.height - draw_h) // 2)
        red, green, blue = self.color
        for y in range(draw_h):
            row = rows[y * step]
            for x in range(draw_w):
                sx = x * step
                if sx < len(row) and row[sx] == '#':
                    px, py = left + x, top + y
                    if 0 <= px < matrix.width and 0 <= py < matrix.height:
                        matrix.SetPixel(px, py, red, green, blue)
        return True
