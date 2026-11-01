"""Weekend reminder: one workout keeps the weekly streak alive."""
from driver import graphics

from display.display import get_text_width, loaded_fonts
from .screen import Screen
from .streak_screen import FLAME_H, FLAME_W, draw_flame

_ORANGE = graphics.Color(255, 140, 0)
_GREY = graphics.Color(145, 165, 190)
_GOLD = graphics.Color(255, 215, 0)
_WHITE = graphics.Color(255, 255, 255)


def days_left_text(days_left):
    return 'LAST DAY' if days_left <= 1 else f'{days_left} DAYS LEFT'


class StreakRiskScreen(Screen):
    """state: {'current': weeks in the streak, 'days_left': days left this week, today included}"""

    def render(self, matrix, state=None):
        state = state if isinstance(state, dict) else {}
        current, days_left = state.get('current'), state.get('days_left')
        if not isinstance(current, int) or current <= 0 or not isinstance(days_left, int):
            return False
        small = loaded_fonts.get('stats') or loaded_fonts.get('info')
        title = loaded_fonts.get('titles') or small
        big = loaded_fonts.get('big')
        if small is None or big is None:
            return False
        w = matrix.width

        def center(font, text, y, color):
            graphics.DrawText(matrix, font, max((w - get_text_width(font, text)) // 2, 1), y, color, text)

        streak = f'{current:,}-WEEK STREAK'
        if matrix.height < 64:
            draw_flame(matrix, 2, 0)
            x = 2 + FLAME_W + 3
            graphics.DrawText(matrix, small, x, 7, _GOLD, '1 WORKOUT')
            graphics.DrawText(matrix, small, x, 15, _GREY, 'KEEPS YOUR')
            if get_text_width(small, streak) > w - 2:
                streak = f'{current:,} WK STREAK'
            center(small, streak, 23, _ORANGE)
            center(small, days_left_text(days_left), 31, _WHITE)
            return True
        draw_flame(matrix, (w - FLAME_W) // 2, 1)
        center(title, '1 WORKOUT', FLAME_H + 10, _GOLD)
        center(small, 'KEEPS YOUR', FLAME_H + 18, _GREY)
        center(big, f'{current:,}', FLAME_H + 34, _WHITE)
        center(small, 'WEEK STREAK', FLAME_H + 41, _ORANGE)
        center(small, days_left_text(days_left), 63, _GREY)
        return True
