"""Compact weekly-goal and lifetime-milestone screens."""
from driver import graphics

from display.display import draw_centered_text, get_text_width, loaded_fonts
from .screen import Screen

_WHITE = graphics.Color(255, 255, 255)
_BLUE = graphics.Color(0, 120, 255)
_GOLD = graphics.Color(255, 215, 0)


class GoalScreen(Screen):
    def render(self, matrix, state=None):
        state = state or {}
        small = loaded_fonts.get('info') or loaded_fonts.get('stats')
        large = loaded_fonts.get('countdown') or small
        if not small or not large:
            return False
        title = str(state.get('title') or 'WEEKLY GOAL').upper()
        current = int(state.get('current') or 0)
        target = max(1, int(state.get('target') or 1))
        unit = str(state.get('unit') or '')
        short = matrix.height < 64
        if state.get('milestone'):
            draw_centered_text(matrix, small, 'MILESTONE', 8 if short else 14, _GOLD)
            draw_centered_text(matrix, large, f'{target:,}', 21 if short else 36, _WHITE)
            # 32 rows: the unit goes on the bottom rows, under the number.
            draw_centered_text(matrix, small, unit.upper(), 29 if short else 49, _GOLD)
            return True
        # 32 rows: everything moves up so the unit fits between value and bar.
        draw_centered_text(matrix, small, title, 6 if short else 12, _WHITE)
        value = f'{current}/{target}'
        draw_centered_text(matrix, large, value, 16 if short else 33, _BLUE)
        draw_centered_text(matrix, small, unit.upper(), 23 if short else 43, _WHITE)
        left, right = 3, matrix.width - 4
        top = matrix.height - 7
        filled = round((right - left + 1) * min(1, current / target))
        for x in range(left, right + 1):
            color = _BLUE if x < left + filled else graphics.Color(35, 35, 35)
            matrix.SetPixel(x, top, color.red, color.green, color.blue)
            matrix.SetPixel(x, top + 1, color.red, color.green, color.blue)
        return get_text_width(large, value) > 0
