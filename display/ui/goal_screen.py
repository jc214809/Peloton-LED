"""Compact weekly-goal screen (milestones have their own: celebration_screen)."""
from driver import graphics

from display.display import draw_centered_text, get_text_width, loaded_fonts
from .screen import Screen

_WHITE = graphics.Color(255, 255, 255)
_BLUE = graphics.Color(0, 120, 255)


# 64 rows: the value takes the widest of these that leaves a 1 px margin each side: the advance includes a
# blank column per character, so 62 px of advance is at most 61 lit, centred from x = 1.
MAX_VALUE_WIDTH = 62
_VALUE_FONTS = ('goal_value', 'bold', 'title_bold')  # 8x13B, 7x13B, then 6x13B


def value_font(value):
    """The first 64-row value font whose text fits the panel, else the smallest."""
    fonts = [loaded_fonts[key] for key in _VALUE_FONTS if key in loaded_fonts]
    for font in fonts:
        if get_text_width(font, value) <= MAX_VALUE_WIDTH:
            return font
    return fonts[-1] if fonts else None


class GoalScreen(Screen):
    def render(self, matrix, state=None):
        state = state or {}
        title = str(state.get('title') or 'WEEKLY GOAL').upper()
        current = int(state.get('current') or 0)
        target = max(1, int(state.get('target') or 1))
        unit = str(state.get('unit') or '').upper()
        value = f'{current}/{target}'
        if matrix.height < 64:
            # 32 rows (unchanged): everything moves up so the unit fits between value and bar.
            small = loaded_fonts.get('info') or loaded_fonts.get('stats')
            large = loaded_fonts.get('countdown') or small
            if not small or not large:
                return False
            draw_centered_text(matrix, small, title, 6, _WHITE)
            draw_centered_text(matrix, large, value, 16, _BLUE)
            draw_centered_text(matrix, small, unit, 23, _WHITE)
        else:
            # 64 rows: title and unit in the 5x8 title font around an 8x13B value.
            label = loaded_fonts.get('titles') or loaded_fonts.get('info') or loaded_fonts.get('stats')
            large = value_font(value)
            if not label or not large:
                return False
            draw_centered_text(matrix, label, title, 10, _WHITE)
            draw_centered_text(matrix, large, value, 33, _BLUE)
            draw_centered_text(matrix, label, unit, 46, _WHITE)
        left, right = 3, matrix.width - 4
        top = matrix.height - 7
        filled = round((right - left + 1) * min(1, current / target))
        for x in range(left, right + 1):
            color = _BLUE if x < left + filled else graphics.Color(35, 35, 35)
            matrix.SetPixel(x, top, color.red, color.green, color.blue)
            matrix.SetPixel(x, top + 1, color.red, color.green, color.blue)
        return get_text_width(large, value) > 0
