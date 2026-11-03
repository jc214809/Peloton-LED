"""Streaks: a pixel flame over the weekly streak and the best one, or the
daily streak and the day it started (one per rotation pass)."""
from datetime import date

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
# A one-day "streak" is just today's workout; show the daily view from two.
MIN_DAILY_STREAK = 2
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


def since_text(start, today):
    """'SINCE OCT 30' within the last year, 'SINCE DEC 2024' before that."""
    month = start.strftime('%b').upper()
    if (today - start).days < 365:
        return f'SINCE {month} {start.day}'
    return f'SINCE {month} {start.year}'


def daily_streak_lines(streaks):
    """(current, label, footer, False) for a daily streak of MIN_DAILY_STREAK
    days or more, else None. The footer needs 'daily_start' and 'today'
    (ISO dates) in the dict; Peloton reports no best daily streak."""
    current = (streaks or {}).get('current_daily')
    if not isinstance(current, int) or isinstance(current, bool) or current < MIN_DAILY_STREAK:
        return None
    footer = ''
    try:
        footer = since_text(date.fromisoformat(streaks['daily_start']),
                            date.fromisoformat(streaks['today']))
    except (KeyError, TypeError, ValueError):
        pass
    return current, 'DAY STREAK', footer, False


def streak_views(streaks):
    """[(view, lines)] for the views there is something to show: 'weekly'
    first, then 'daily'. The rotation shows one per pass, alternating."""
    views = (('weekly', streak_lines(streaks)), ('daily', daily_streak_lines(streaks)))
    return [(view, lines) for view, lines in views if lines]


class StreakScreen(Screen):
    """state is the snapshot's 'streaks' dict (see peloton.totals.parse_streaks),
    plus 'daily_start' and 'today' for the daily footer and 'view' ('weekly'
    or 'daily'). Without a 'view', or when that one has nothing to show, the
    first available view is drawn."""

    def render(self, matrix, state=None):
        state = state if isinstance(state, dict) else {}
        views = dict(streak_views(state))
        lines = views.get(state.get('view')) or next(iter(views.values()), None)
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
                footer = footer.replace(' WEEKS', '').replace('SINCE ', '')
            x = max((w - get_text_width(small, footer)) // 2, 1)
            graphics.DrawText(matrix, small, x, y_footer, _GOLD if record else _GREY, footer)
        return True
