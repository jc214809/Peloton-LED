"""Activity heatmap: one cell per day for the last 12 weeks, shaded by minutes."""
from datetime import date, timedelta

from driver import graphics

from display.display import get_text_width, loaded_fonts
from .screen import Screen

EMPTY = (28, 28, 34)
# Minutes thresholds and colors, light to strong.
LEVELS = ((20, (0, 80, 40)), (45, (0, 140, 60)), (90, (30, 200, 80)), (None, (150, 255, 150)))
_GREY = graphics.Color(145, 165, 190)


def level_color(minutes):
    if not minutes:
        return EMPTY
    for limit, color in LEVELS:
        if limit is None or minutes < limit:
            return color


def heatmap_cells(days, today, weeks):
    """[(column, row, (r, g, b))] for every day from the first Monday through today."""
    first = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    cells = []
    for offset in range((today - first).days + 1):
        day = first + timedelta(days=offset)
        cells.append((offset // 7, day.weekday(), level_color(days.get(day.isoformat(), 0))))
    return cells


class HeatmapScreen(Screen):
    """state: {'days': {'YYYY-MM-DD': minutes}, 'today': 'YYYY-MM-DD', 'weeks': 12}"""

    def render(self, matrix, state=None):
        state = state if isinstance(state, dict) else {}
        try:
            today = date.fromisoformat(state.get('today') or '')
        except ValueError:
            return False
        days = state.get('days') if isinstance(state.get('days'), dict) else {}
        weeks = state.get('weeks') or 12
        if matrix.height < 64:
            # 32 rows: no title; 3-pixel-tall cells on a 4-pixel pitch.
            cell_w, cell_h, pitch_x, pitch_y, top = 4, 3, 5, 4, 2
        else:
            title = f'LAST {weeks} WEEKS'
            font = loaded_fonts.get('stats') or loaded_fonts.get('info')
            if font is None:
                return False
            x = max((matrix.width - get_text_width(font, title)) // 2, 1)
            graphics.DrawText(matrix, font, x, 8, _GREY, title)
            cell_w, cell_h, pitch_x, pitch_y, top = 4, 6, 5, 7, 13
        left = (matrix.width - (weeks * pitch_x - (pitch_x - cell_w))) // 2
        for column, row, color in heatmap_cells(days, today, weeks):
            x0, y0 = left + column * pitch_x, top + row * pitch_y
            for y in range(y0, y0 + cell_h):
                for x in range(x0, x0 + cell_w):
                    matrix.SetPixel(x, y, *color)
        return True
