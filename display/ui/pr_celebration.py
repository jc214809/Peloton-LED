# display/ui/pr_celebration.py

import math
from typing import Any, List, Optional, Tuple

from driver import graphics
from display.display import get_text_width, loaded_fonts
from .last_workout_screen import _fmt_split
from .screen import Screen

_GOLD = graphics.Color(255, 215, 0)
_WHITE = graphics.Color(255, 255, 255)
_GREEN = graphics.Color(40, 220, 90)
_BLUE = graphics.Color(0, 120, 255)

BURST_SECONDS = 1.2
SETTLE_SECONDS = 0.3
# Kept in the top band beside the star badge so they never land on text.
_SPARKLE_SPOTS = [(5, 5), (58, 6), (13, 13), (50, 13), (3, 16), (60, 15)]


def _star_points(cx: float, cy: float, outer: float) -> List[Tuple[float, float]]:
    inner = outer * 0.381966
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        r = outer if i % 2 == 0 else inner
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


def _fill_polygon(matrix, poly: List[Tuple[float, float]], color) -> None:
    ys = [y for _, y in poly]
    for y in range(max(0, int(min(ys))), min(matrix.height, int(max(ys)) + 1)):
        yc = y + 0.5
        xs = []
        for i, (x1, y1) in enumerate(poly):
            x2, y2 = poly[(i + 1) % len(poly)]
            if (y1 <= yc < y2) or (y2 <= yc < y1):
                xs.append(x1 + (yc - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for a, b in zip(xs[::2], xs[1::2]):
            for x in range(max(0, round(a)), min(matrix.width, round(b) + 1)):
                matrix.SetPixel(x, y, color.red, color.green, color.blue)


def _centered(matrix, font, y: int, color, text: str) -> None:
    x = max((matrix.width - get_text_width(font, text)) // 2, 1)
    graphics.DrawText(matrix, font, x, y, color, text)


def pr_card_lines(summary: dict) -> Optional[Tuple[str, str, Optional[str]]]:
    """(headline, value, gain) for a PR summary, or None if nothing to show.

    gain is only produced when a previous best is supplied, since Peloton's
    workout payload flags a PR without saying what the old record was.
    """
    if summary.get("is_output_pr") and isinstance(summary.get("total_output_kj"), (int, float)):
        precise = summary.get("total_work_kj")
        value = precise if isinstance(precise, (int, float)) else summary["total_output_kj"]
        previous = summary.get("previous_best_kj")
        gain = None
        if isinstance(previous, (int, float)) and value > previous:
            diff = value - previous
            # Small PRs are common; don't let "+0.8" round away to "+0".
            gain = f"+{diff:.1f} KJ" if diff < 1 else f"+{int(diff)} KJ"
        return "OUTPUT PR", f"{round(value)} KJ", gain
    if summary.get("is_splits_pr") and summary.get("row_split_sec_per_500m"):
        return "SPLITS PR", f"{_fmt_split(summary['row_split_sec_per_500m'])}/500", None
    if summary.get("is_pr"):
        return "NEW PR", "", None
    return None


class PrCelebrationScreen(Screen):
    """Star burst, then a card with the PR type, new value, and class length.

    state is a workout summary from peloton.summaries.summarize_workout().
    """

    animated = True
    atomic_frames = True

    def __init__(self):
        self.elapsed = 0.0

    def on_enter(self, matrix, state=None):
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += max(0, dt)

    def render(self, matrix, state: Optional[Any] = None) -> bool:
        summary = state if isinstance(state, dict) else {}
        lines = pr_card_lines(summary)
        if lines is None:
            return False
        w, h = matrix.width, matrix.height

        if self.elapsed < BURST_SECONDS:
            t = self.elapsed / BURST_SECONDS
            # Ease-out growth, with rays shooting out behind the star.
            grow = 1 - (1 - t) ** 3
            outer = 3 + grow * (min(w, h) * 0.42)
            cx, cy = (w - 1) / 2, (h - 1) / 2
            ray = outer + 2 + t * 10
            for i in range(8):
                angle = i * math.pi / 4 + math.pi / 8
                for step in range(3):
                    r = ray + step * 2
                    x, y = round(cx + r * math.cos(angle)), round(cy + r * math.sin(angle))
                    if 0 <= x < w and 0 <= y < h:
                        matrix.SetPixel(x, y, 255, 240 - step * 60, 120 - step * 40)
            _fill_polygon(matrix, _star_points(cx, cy, outer), _GOLD)
            return True

        headline, value, gain = lines
        card_t = self.elapsed - BURST_SECONDS
        compact = h < 64
        # The star shrinks into a badge at the top as the card appears; on
        # 32-row panels there's no room for the badge, so it shrinks away.
        settle = min(1.0, card_t / SETTLE_SECONDS)
        start = min(w, h) * 0.42
        outer = start - settle * (start if compact else start - 8)
        star_cy = (h - 1) / 2 - (0 if compact else settle * ((h - 1) / 2 - 10))
        if outer >= 1:
            _fill_polygon(matrix, _star_points((w - 1) / 2, star_cy, outer), _GOLD)
        if settle < 1:
            return True

        headline_font = loaded_fonts.get("titles") or loaded_fonts.get("stats")
        value_font = loaded_fonts.get("discipline") or headline_font
        info_font = loaded_fonts.get("info") or headline_font
        dur = summary.get("duration_min")
        if compact:
            _centered(matrix, headline_font, 8, _GOLD, headline)
            if value:
                _centered(matrix, value_font, 20, _WHITE, value)
            if gain:
                _centered(matrix, info_font, 30, _GREEN, gain)
            elif isinstance(dur, (int, float)):
                _centered(matrix, info_font, 30, _BLUE, f"{int(dur)} MIN CLASS")
            return True
        _centered(matrix, headline_font, 29, _GOLD, headline)
        if value:
            if get_text_width(value_font, value) > w - 2:
                value_font = headline_font
            _centered(matrix, value_font, 44, _WHITE, value)
        if gain:
            _centered(matrix, info_font, 54, _GREEN, gain)
        if isinstance(dur, (int, float)):
            _centered(matrix, info_font, 62 if gain else 56, _BLUE, f"{int(dur)} MIN CLASS")

        # Twinkling sparkles around the card.
        for i, (x, y) in enumerate(_SPARKLE_SPOTS):
            if int(card_t * 4 + i) % 3 == 0 and x < w and y < h:
                matrix.SetPixel(x, y, 255, 255, 200)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    matrix.SetPixel(x + dx, y + dy, 150, 130, 40)
        return True
