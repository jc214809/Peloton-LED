"""The 'value label' stat, the heart-rate and calories bar, and the 64x32 centred lines."""
from typing import List

from driver import graphics
from .colors import _RED, _WHITE
from .sprites import _HEART_H, _HEART_W, _TROPHY_H, _TROPHY_W, _draw_heart, _draw_trophy
from .stats import _whole
from .text import _draw_text, _text_width, _truncate


def _draw_stat(matrix, font, x: int, y: int, color, text: str, max_px: int, right_align: bool = False, star: bool = False) -> None:  # noqa: PLR0913
    """Draw 'value label' with tight gap between parts, truncating label if needed."""
    parts = text.split(' ', 1)
    val = parts[0]
    label = parts[1] if len(parts) == 2 else None
    val_w = _text_width(font, val)
    _GAP = 2
    star_w = (_TROPHY_W + 1) if star else 0
    label_trunc = _truncate(font, label, max_px - val_w - _GAP - star_w) if label else None
    total_w = val_w + (_GAP + _text_width(font, label_trunc) + star_w if label_trunc else 0)
    if right_align:
        x = x - total_w
    _draw_text(matrix, font, x, y, color, val)
    if label_trunc:
        lx = x + val_w + _GAP
        label_end_x = _draw_text(matrix, font, lx, y, color, label_trunc)
        if star:
            font_h = getattr(font, "height", 6)
            star_top = y - font_h + (font_h - _TROPHY_H) // 2 + 1
            _draw_trophy(matrix, label_end_x + 1, star_top)


def _draw_hr_calories(matrix, summary: dict, stat_font, bottom_y: int) -> None:
    """Bottom bar: ♥ average HR on the left, calories on the right."""
    font_h = getattr(stat_font, "height", 8)
    w = matrix.width
    hr_val = summary.get("hr_avg")
    if isinstance(hr_val, (int, float)):
        heart_top = bottom_y - font_h + (font_h - _HEART_H) // 2 + 1
        _draw_heart(matrix, 2, heart_top, _RED)
        graphics.DrawText(matrix, stat_font, 2 + _HEART_W + 1, bottom_y, _WHITE, str(_whole(hr_val)))

    cal_val = summary.get("calories")
    if isinstance(cal_val, (int, float)):
        # Leave the bottom-right corner free for the login padlock.
        right = w - 1 - (8 if summary.get('login_required') else 0)
        mid = w // 2 + 1
        _draw_stat(matrix, stat_font, right, bottom_y, _WHITE, f"{_whole(cal_val)} cal",
                   max(0, right - mid), right_align=True)


def _draw_short_lines(matrix, font, lines: List[str], top_y: int, summary: dict,
                      clear_icons: bool = True) -> None:
    """Up to two centered 4x6 lines, 7px apart, for the 32-row layout.

    Lines may run the panel's full width (a workout title is wrapped to it). The second line
    sits on the bottom rows, so a workout title narrows it to clear the login padlock (bottom
    right) and stale-data clock (bottom left) when shown. An instructor name passes
    clear_icons=False: it is drawn the same every time and an icon may cover its ends, which
    is the point of the icon.
    """
    w = matrix.width
    for i, line in enumerate(lines[:2]):
        if i == 1 and clear_icons:
            left = 9 if summary.get('data_stale') else 0
            right = 9 if summary.get('login_required') else 0
            line = _truncate(font, line, w - 2 * max(left, right))
        tx = max((w - _text_width(font, line)) // 2, 0)
        _draw_text(matrix, font, tx, top_y + i * 7, _WHITE, line)
