"""Weekly streak: a pixel flame, the current streak, and the best one."""
from driver import graphics

from display.display import get_text_width, loaded_fonts
from .screen import Screen

# 12 wide x 16 tall: R red edge, O orange, Y yellow core.
FLAME_ROWS = (
    ".....R......",
    ".....RR.....",
    "....RRR.....",
    "....RRRR..R.",
    "...RRORRR.R.",
    "...RROORRRR.",
    "..RROOORRRR.",
    "..RROOOORRR.",
    ".RRROOYOORRR",
    ".RROOYYOOORR",
    ".RROOYYYOORR",
    ".RROYYYYOORR",
    ".RROYYYYYORR",
    "..RROYYYORR.",
    "...RROOORR..",
    "....RRRRR...",
)
FLAME_W, FLAME_H = 12, 16
FLAME_COLORS = {'R': (235, 45, 20), 'O': (255, 140, 0), 'Y': (255, 225, 60)}
_ORANGE = graphics.Color(255, 140, 0)
_GREY = graphics.Color(145, 165, 190)
_GOLD = graphics.Color(255, 215, 0)
_WHITE = graphics.Color(255, 255, 255)


def draw_flame(matrix, x, y):
    for dy, row in enumerate(FLAME_ROWS):
        for dx, cell in enumerate(row):
            if cell in FLAME_COLORS:
                matrix.SetPixel(x + dx, y + dy, *FLAME_COLORS[cell])


def streak_lines(streaks):
    """(current, label, footer, footer_is_record) or None when there's no streak."""
    current = (streaks or {}).get('current_weekly')
    if not isinstance(current, int) or current <= 0:
        return None
    best = streaks.get('best_weekly')
    label = 'WEEK STREAK'
    if isinstance(best, int) and current >= best:
        return current, label, 'PERSONAL BEST', True
    if isinstance(best, int):
        return current, label, f'BEST {best:,} WEEKS', False
    return current, label, '', False


class StreakScreen(Screen):
    """state is the snapshot's 'streaks' dict (see peloton.totals.parse_streaks)."""

    def render(self, matrix, state=None):
        lines = streak_lines(state if isinstance(state, dict) else {})
        big = loaded_fonts.get('big')
        small = loaded_fonts.get('stats') or loaded_fonts.get('info')
        label_font = loaded_fonts.get('titles') or small
        if lines is None or big is None or small is None:
            return False
        current, label, footer, record = lines
        w = matrix.width
        number = f'{current:,}'
        if matrix.height < 64:
            # Flame and number side by side on top, then label and footer.
            gap = 3
            group = FLAME_W + gap + get_text_width(big, number)
            left = max((w - group) // 2, 1)
            draw_flame(matrix, left, 0)
            graphics.DrawText(matrix, big, left + FLAME_W + gap, 13, _WHITE, number)
            y_label, y_footer = 23, 30
        else:
            draw_flame(matrix, (w - FLAME_W) // 2, 3)
            x = max((w - get_text_width(big, number)) // 2, 1)
            graphics.DrawText(matrix, big, x, 39, _WHITE, number)
            y_label, y_footer = 50, 60
        x = max((w - get_text_width(label_font, label)) // 2, 1)
        graphics.DrawText(matrix, label_font, x, y_label, _ORANGE, label)
        if footer:
            if get_text_width(small, footer) > w - 2:
                footer = footer.replace(' WEEKS', '')
            x = max((w - get_text_width(small, footer)) // 2, 1)
            graphics.DrawText(matrix, small, x, y_footer, _GOLD if record else _GREY, footer)
        return True
