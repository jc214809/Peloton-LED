"""Next milestone: 3 TO GO / 600TH / RIDE (32 rows: 3 MORE / TO 600 / CYCLING), with a progress bar.

One page per target within a few workouts, the total's or a discipline's.
state: {'total': 597, 'target': 600, 'previous': 500, 'title': 'Cycling', 'discipline': 'cycling'};
previous is where the bar starts. The name is drawn in the discipline's Lifetime-page colour
(discipline None, the total: the default one).
"""
from driver import graphics

from display.display import get_text_width, loaded_fonts
from .celebration_screen import discipline_noun, ordinal_line
from .lifetime_overview import discipline_color
from .screen import Screen

_WHITE = (255, 255, 255)
_GOLD = (255, 215, 0)
_GREY = (145, 165, 190)
BAR_FILL = (0, 120, 255)
BAR_EMPTY = (35, 35, 35)


def _bar(matrix, top, height, fraction):
    left, right = 3, matrix.width - 4
    filled = round((right - left + 1) * max(0.0, min(1.0, fraction)))
    for x in range(left, right + 1):
        color = BAR_FILL if x < left + filled else BAR_EMPTY
        for y in range(top, top + height):
            matrix.SetPixel(x, y, *color)


def _fonts(*keys):
    return [loaded_fonts[key] for key in keys if loaded_fonts.get(key) is not None]


def _draw_runs(matrix, runs, baseline):
    """runs: [(font, text, colour, gap after)] centred as one line on a baseline."""
    width = sum(get_text_width(font, text) + gap for font, text, _, gap in runs)
    x = max((matrix.width - width) // 2, 0)
    for font, text, color, gap in runs:
        graphics.DrawText(matrix, font, x, baseline, graphics.Color(*color), text)
        x += get_text_width(font, text) + gap


def _fit(text, fonts, room):
    """The first font the text fits in, else the last (smallest) one."""
    return next((font for font in fonts if get_text_width(font, text) <= room), fonts[-1])


class CountdownScreen(Screen):

    def render(self, matrix, state=None):
        state = state if isinstance(state, dict) else {}
        total, target, previous = state.get('total'), state.get('target'), state.get('previous', 0)
        if (not all(isinstance(v, int) and not isinstance(v, bool) for v in (total, target, previous))
                or target <= total):
            return False
        big, bold = _fonts('big'), _fonts('bold', 'big')
        if not big or not bold:
            return False
        big, bold = big[0], bold[0]
        name = str(state.get('title') or '').upper()
        color = discipline_color(state.get('discipline'))
        fraction = (total - previous) / (target - previous) if target > previous else 0
        # 64 rows: 3 TO GO / 600TH / RIDE, the same noun the celebration uses (the discipline's name only where
        # it has no word of its own); 32 rows keep 3 MORE / TO 600 / CYCLING.
        more = [(big if matrix.height >= 64 else bold, str(target - total), _WHITE, 3 if matrix.height >= 64 else 2),
                (bold, 'TO GO' if matrix.height >= 64 else 'MORE', _WHITE, 0)]
        if matrix.height >= 64:
            name = (discipline_noun(state.get('discipline'), state.get('title')) if state.get('discipline')
                    else 'WORKOUT')
        # 32 rows: 6x9 ('countdown'), since 5x8's narrow G and T leave gaps (S TRENG TH).
        names = _fonts('title_bold', 'titles', 'info') if matrix.height >= 64 else _fonts('countdown', 'info')
        if matrix.height < 64:
            # No room to stack a big 600TH: TO 600 in one line, and no bar.
            _draw_runs(matrix, more, 11)
            _draw_runs(matrix, [(loaded_fonts.get('countdown') or bold, 'TO', _GREY, 2),
                                (bold, f'{target:,}', _GOLD, 0)], 22)
            if name and names:
                font = _fit(name, names, matrix.width - 2)
                _draw_runs(matrix, [(font, name, color, 0)], 30)
            return True
        _draw_runs(matrix, more, 16)
        parts = ordinal_line(target, [big, bold], loaded_fonts.get('titles'), 36, graphics.Color(*_GOLD),
                             0, matrix.width)
        for font, x, y, line_color, text in parts or ():
            graphics.DrawText(matrix, font, x, y, line_color, text)
        if name and names:
            font = _fit(name, names, matrix.width - 2)
            _draw_runs(matrix, [(font, name, color, 0)], 50)
        _bar(matrix, 56, 4, fraction)
        return True
