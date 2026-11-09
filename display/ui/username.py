# python file: display/ui/username.py

from .screen import Screen
from display.display import loaded_fonts, color_dict, get_text_width
from utils import debug
from driver import graphics

DETAIL_INTERVAL_SECONDS = 4.0
# A value line wider than the panel's room scrolls: hold, glide to the end, hold; and when the highlight
# lasts long enough, back again. SCROLL_SPEED is pixels per second; the holds are seconds.
SCROLL_SPEED = 14.0
SCROLL_HOLD_START = 0.6
SCROLL_HOLD_END = 0.6
MARGIN = 2


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

    @staticmethod
    def scroll_offset(overflow, phase, interval):
        """How many pixels a line `overflow` px too wide has scrolled `phase` seconds into a highlight that
        lasts `interval`: hold, glide to the end, hold, and back again only if there is time for the whole
        trip. A one-way glide slows down or speeds up (never below the time left) to be done with the hold
        at the end still ahead."""
        if overflow <= 0:
            return 0
        glide = overflow / SCROLL_SPEED
        both_ways = interval >= 2 * (SCROLL_HOLD_START + glide + SCROLL_HOLD_END)
        if not both_ways:
            glide = max(0.5, interval - SCROLL_HOLD_START - SCROLL_HOLD_END)
        t = phase - SCROLL_HOLD_START
        if t <= 0:
            return 0
        if t < glide:
            return round(overflow * t / glide)
        t -= glide + SCROLL_HOLD_END
        if not both_ways or t <= 0:
            return overflow
        return round(overflow * max(0.0, 1 - t / glide))

    def _scrolling(self, matrix, font, text, baseline, color, phase, interval):
        """Draw a line wider than the room, scrolled to where `phase` puts it; the margins are blanked so
        the text slides under them instead of off the panel's edge."""
        room = matrix.width - 2 * MARGIN
        offset = self.scroll_offset(get_text_width(font, text) - room, phase, interval)
        graphics.DrawText(matrix, font, MARGIN - offset, baseline, color, text)
        for y in range(baseline - 6, baseline + 2):
            for x in list(range(0, MARGIN)) + list(range(matrix.width - MARGIN, matrix.width)):
                matrix.SetPixel(x, y, 0, 0, 0)

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
            # build_rotation_pages shares the page's time out (detail_seconds), each highlight once;
            # without it, each gets the standard 4 s and the list repeats.
            interval = state.get('detail_seconds') or DETAIL_INTERVAL_SECONDS
            index = int(self.elapsed / interval)
            index = min(index, len(details) - 1) if state.get('detail_seconds') else index % len(details)
            phase_seconds = self.elapsed % interval
            detail = details[index]
            # Each new detail rises into place during its first 0.3 seconds.
            # 32-row panels rise 2px so the second line never drops off the bottom.
            rise = 2 if compact else 3
            offset = max(0, round(rise * (1 - min(1, phase_seconds / 0.3))))
            label = str(detail.get('label', '')).upper()
            if get_text_width(small_font, label) > matrix.width - 4 and detail.get('short_label'):
                label = str(detail['short_label']).upper()
            label = self._fit(small_font, label, matrix.width - 4)
            self._center(matrix, small_font, label, (17 if compact else 38) + offset,
                         graphics.Color(145, 165, 190))
            lines = detail.get('lines') or [detail.get('value', '')]
            line_color = color_dict.get(detail.get('color_key'), graphics.Color(255, 255, 255))
            big_font = loaded_fonts.get(detail.get('font_key'))
            if big_font and len(lines) == 1 and get_text_width(big_font, str(lines[0])) <= matrix.width - 4:
                # A single headline number (e.g. total workouts) fills the space below the label.
                self._center(matrix, big_font, str(lines[0]), (30 if compact else 58) + offset, line_color)
                return True
            # 32 rows: 7px line pitch leaves a blank row between the two 4x6 lines.
            baselines = (24, 31) if compact else (50, 59)
            for line, baseline in zip(lines[:2], baselines):
                line = str(line).upper().strip()
                if get_text_width(value_font, line) > matrix.width - 2 * MARGIN:
                    self._scrolling(matrix, value_font, line, baseline + offset, line_color, phase_seconds, interval)
                else:
                    self._center(matrix, value_font, line, baseline + offset, line_color)
        return True
