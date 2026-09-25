# python file: display/ui/username.py

from .screen import Screen
from display.display import loaded_fonts, color_dict, get_text_width
from utils import debug
from driver import graphics

DETAIL_INTERVAL_SECONDS = 4.0


class UsernameScreen(Screen):
    animated = True
    atomic_frames = True

    def __init__(self, font_key="discipline", color_key="white"):
        self.font_key = font_key
        self.color_key = color_key
        self.elapsed = 0.0

    def on_enter(self, matrix, state=None):
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += max(0, dt)

    @staticmethod
    def _fit(font, text, width):
        while text and get_text_width(font, text) > width:
            text = text[:-1]
        return text.rstrip()

    def _username_font(self, text, width):
        """Use the largest loaded font that preserves the complete username."""
        candidates = ('discipline', 'titles', 'info', 'stats')
        fonts = [loaded_fonts.get(key) for key in candidates]
        fonts = [font for font in fonts if font is not None]
        return next((font for font in fonts if get_text_width(font, text) <= width),
                    fonts[-1] if fonts else None)

    @staticmethod
    def _center(matrix, font, text, y, color, x_offset=0):
        x = max(1, (matrix.width - get_text_width(font, text)) // 2 + x_offset)
        graphics.DrawText(matrix, font, x, y, color, text)

    def render(self, matrix, state=None):
        username = (state or {}).get("username") if isinstance(state, dict) else state
        text = (username or "").strip() or "Peloton Member"
        title_font = self._username_font(text, matrix.width - 4)
        small_font = loaded_fonts.get('stats') or loaded_fonts.get('info')
        value_font = loaded_fonts.get('info') or small_font
        if not title_font or not small_font or not value_font:
            debug.error("Font %s is not loaded", self.font_key)
            return False
        color = color_dict.get(self.color_key, color_dict["white"])
        # Only pathological names wider than the smallest font are trimmed.
        text = self._fit(title_font, text, matrix.width - 4)
        details = (state or {}).get('details', []) if isinstance(state, dict) else []
        compact = matrix.height < 64
        title_y = 8 if compact else 17
        self._center(matrix, title_font, text, title_y, color)

        # The accent arrives immediately, then remains fixed under the username.
        blue = graphics.Color(0, 120, 255)
        line_width = min(matrix.width - 12, max(8, round((matrix.width - 12) * min(1, self.elapsed / 0.35))))
        line_left = (matrix.width - line_width) // 2
        line_y = 10 if compact else 23
        for x in range(line_left, line_left + line_width):
            matrix.SetPixel(x, line_y, blue.red, blue.green, blue.blue)

        if details:
            interval = DETAIL_INTERVAL_SECONDS
            index = int(self.elapsed / interval) % len(details)
            phase_seconds = self.elapsed % interval
            detail = details[index]
            # Each new detail rises into place during its first 0.3 seconds.
            # 32-row panels rise 2px so the second line never drops off the bottom.
            rise = 2 if compact else 3
            offset = max(0, round(rise * (1 - min(1, phase_seconds / 0.3))))
            label = self._fit(small_font, str(detail.get('label', '')).upper(), matrix.width - 4)
            self._center(matrix, small_font, label, (17 if compact else 38) + offset,
                         graphics.Color(145, 165, 190))
            lines = detail.get('lines') or [detail.get('value', '')]
            # 32 rows: 7px line pitch leaves a blank row between the two 4x6 lines.
            baselines = (24, 31) if compact else (50, 59)
            for line, baseline in zip(lines[:2], baselines):
                line = self._fit(value_font, str(line).upper(), matrix.width - 4)
                self._center(matrix, value_font, line, baseline + offset,
                             graphics.Color(255, 255, 255))
        return True
