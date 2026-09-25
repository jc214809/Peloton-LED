"""Countdown to the next lifetime-workouts milestone, with a progress bar."""
from driver import graphics

from display.display import get_text_width, loaded_fonts
from .screen import Screen

_GREY = graphics.Color(145, 165, 190)
_GOLD = graphics.Color(255, 215, 0)
_WHITE = graphics.Color(255, 255, 255)
_ORANGE = graphics.Color(255, 140, 0)
BAR_FILL = (0, 120, 255)
BAR_EMPTY = (35, 35, 35)


def _center(matrix, font, y, color, text):
    graphics.DrawText(matrix, font, max((matrix.width - get_text_width(font, text)) // 2, 1),
                      y, color, text)


def _bar(matrix, top, height, fraction):
    left, right = 3, matrix.width - 4
    filled = round((right - left + 1) * max(0.0, min(1.0, fraction)))
    for x in range(left, right + 1):
        color = BAR_FILL if x < left + filled else BAR_EMPTY
        for y in range(top, top + height):
            matrix.SetPixel(x, y, *color)


class CountdownScreen(Screen):
    """state: {'total': int, 'target': int, 'previous': int}."""

    def render(self, matrix, state=None):
        state = state if isinstance(state, dict) else {}
        total, target, previous = state.get('total'), state.get('target'), state.get('previous', 0)
        if not all(isinstance(v, int) for v in (total, target, previous)) or target <= total:
            return False
        small = loaded_fonts.get('stats') or loaded_fonts.get('info')
        mid = loaded_fonts.get('titles') or small
        big = loaded_fonts.get('big') or mid
        if small is None:
            return False
        remaining = f'{target - total:,}'
        fraction = (total - previous) / (target - previous) if target > previous else 0
        if matrix.height < 64:
            _center(matrix, small, 6, _GREY, f'NEXT: {target:,}')
            # Remaining count and "TO GO" side by side.
            gap = 3
            width = get_text_width(big, remaining) + gap + get_text_width(small, 'TO GO')
            x = max((matrix.width - width) // 2, 1)
            graphics.DrawText(matrix, big, x, 19, _WHITE, remaining)
            graphics.DrawText(matrix, small, x + get_text_width(big, remaining) + gap, 19, _ORANGE, 'TO GO')
            _bar(matrix, 21, 3, fraction)
            _center(matrix, small, 31, _GREY, f'{total:,} WORKOUTS')
            return True
        _center(matrix, small, 8, _GREY, 'NEXT MILESTONE')
        _center(matrix, mid, 18, _GOLD, f'{target:,}')
        _center(matrix, big, 40, _WHITE, remaining)
        _center(matrix, mid, 49, _ORANGE, 'TO GO')
        _bar(matrix, 53, 3, fraction)
        _center(matrix, small, 63, _GREY, f'{total:,} WORKOUTS')
        return True
