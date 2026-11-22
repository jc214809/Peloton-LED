# display/ui/pr_celebration.py

import math
from typing import Any

from driver import graphics
from display.display import get_text_width, loaded_fonts
from peloton.selection import normalize_discipline
from .last_workout.rotation import LAST_WORKOUT_DETAIL_INTERVAL_SECONDS
from .last_workout.stats import _fmt_split, _whole
from .lifetime_overview import discipline_color
from .screen import Screen

_GOLD = graphics.Color(255, 215, 0)
_WHITE = graphics.Color(255, 255, 255)
_GREEN = graphics.Color(40, 220, 90)
_BLUE = graphics.Color(0, 120, 255)

BURST_SECONDS = 1.2
SETTLE_SECONDS = 0.3
# Extra time the finished card holds on top of one detail interval: a PR is a big moment (Joel, 2026-11-09).
CARD_HOLD_SECONDS = 2.0
# Kept in the top band beside the star badge so they never land on text.
_SPARKLE_SPOTS = [(5, 5), (58, 6), (13, 13), (50, 13), (3, 16), (60, 15)]
# 32 rows: the outer ends of the blank rows above the bottom line; the value row's margins are added per card.
_COMPACT_SPARKLE_SPOTS = [(2, 22), (61, 22)]
_COMPACT_BADGE_RADIUS = 4.5


def _star_points(cx: float, cy: float, outer: float) -> list[tuple[float, float]]:
    inner = outer * 0.381966
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        r = outer if i % 2 == 0 else inner
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


def _fill_polygon(matrix, poly: list[tuple[float, float]], color) -> None:
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


def _label_color(discipline: str):
    """The discipline's icon colour, so it reads as a label rather than a second value; white when
    that's too close to the gain's green or the class length's blue (running, rowing) to tell apart."""
    rgb = discipline_color(normalize_discipline(discipline))
    for other in (_GREEN, _BLUE):
        if abs(rgb[0] - other.red) + abs(rgb[1] - other.green) + abs(rgb[2] - other.blue) < 100:
            return _WHITE
    return graphics.Color(*rgb)


def compact_turn(card_t: float, count: int, detail_interval: float) -> int:
    """Which of `count` bottom-line turns shows card_t seconds after the burst (32 rows).

    The settled card is up for one detail interval plus CARD_HOLD_SECONDS (as build_rotation_pages
    times the page); the turns share that evenly and the last one holds to the end, so none comes
    back for a flicker as the page ends.
    """
    share = (detail_interval + CARD_HOLD_SECONDS) / count
    return min(int(max(0.0, card_t - SETTLE_SECONDS) / share), count - 1)


def pr_card_lines(summary: dict) -> tuple[str, str, str | None] | None:
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
            gain = f"+{diff:.1f} KJ" if diff < 1 else f"+{_whole(diff)} KJ"
        # The app's Total Output, not the precise work: they can round differently.
        return "OUTPUT PR", f"{_whole(summary['total_output_kj'])} KJ", gain
    if summary.get("is_splits_pr") and summary.get("row_split_sec_per_500m"):
        return "SPLITS PR", f"{_fmt_split(summary['row_split_sec_per_500m'])}/500", None
    if summary.get("is_pr"):
        return "NEW PR", "", None
    return None


class PrCelebrationScreen(Screen):
    """Star burst, then a card with the PR type, new value, and class length.

    state is a workout summary from peloton.stats.summaries.summarize_workout().
    """

    animated = True
    atomic_frames = True

    def __init__(self, detail_interval: float = LAST_WORKOUT_DETAIL_INTERVAL_SECONDS):
        self.elapsed = 0.0
        # The page's own interval (build_rotation_pages sizes the card with it), so 32-row turns fit the card.
        self.detail_interval = detail_interval or LAST_WORKOUT_DETAIL_INTERVAL_SECONDS

    def on_enter(self, matrix, state=None):
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += max(0, dt)

    def render(self, matrix, state: Any | None = None) -> bool:
        summary = state if isinstance(state, dict) else {}
        lines = pr_card_lines(summary)
        if lines is None:
            return False
        if self.elapsed < BURST_SECONDS:
            self._draw_burst(matrix)
            return True
        card_t = self.elapsed - BURST_SECONDS
        settle = min(1.0, card_t / SETTLE_SECONDS)
        self._draw_settling_star(matrix, settle)
        if settle < 1:
            return True
        if matrix.height < 64:
            self._draw_compact_card(matrix, summary, card_t, *lines)
        else:
            self._draw_full_card(matrix, summary, *lines)
            self._draw_sparkles(matrix, card_t, _SPARKLE_SPOTS)
        return True

    def _draw_burst(self, matrix) -> None:
        w, h = matrix.width, matrix.height
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

    @staticmethod
    def _draw_settling_star(matrix, settle: float) -> None:
        """The star shrinks into a badge at the top as the card appears; on
        32-row panels there's no room for the badge, so it shrinks away."""
        w, h = matrix.width, matrix.height
        compact = h < 64
        start = min(w, h) * 0.42
        outer = start - settle * (start if compact else start - 8)
        star_cy = (h - 1) / 2 - (0 if compact else settle * ((h - 1) / 2 - 10))
        if outer >= 1:
            _fill_polygon(matrix, _star_points((w - 1) / 2, star_cy, outer), _GOLD)

    @staticmethod
    def _card_fonts():
        headline_font = loaded_fonts.get("titles") or loaded_fonts.get("stats")
        value_font = loaded_fonts.get("discipline") or headline_font
        info_font = loaded_fonts.get("info") or headline_font
        return headline_font, value_font, info_font

    def _draw_compact_card(self, matrix, summary: dict, card_t: float, headline: str, value: str,
                           gain: str | None) -> None:
        """32 rows: headline between two star badges, the value (or the discipline for a plain
        NEW PR), and a bottom line that takes turns between gain, class length and discipline."""
        headline_font, value_font, info_font = self._card_fonts()
        _centered(matrix, headline_font, 8, _GOLD, headline)
        self._draw_badges(matrix, get_text_width(headline_font, headline))
        middle = value
        if not middle and isinstance(summary.get("discipline"), str):
            middle = summary["discipline"].upper()
        value_width = 0
        if middle:
            if get_text_width(value_font, middle) > matrix.width - 2:
                value_font = info_font
            value_width = get_text_width(value_font, middle)
            _centered(matrix, value_font, 20, _WHITE, middle)
        turns = self._compact_bottom_turns(summary, gain, middle)
        if turns:
            _centered(matrix, info_font, 30, *turns[compact_turn(card_t, len(turns), self.detail_interval)])
        margin = (matrix.width - value_width) // 2
        spots = list(_COMPACT_SPARKLE_SPOTS)
        if margin >= 6:
            spots += [(margin // 2, 15), (matrix.width - 1 - margin // 2, 18)]
        self._draw_sparkles(matrix, card_t, spots)

    @staticmethod
    def _compact_bottom_turns(summary: dict, gain: str | None, middle: str) -> list[tuple[Any, str]]:
        """The bottom line's turns: gain, class length, discipline (unless the middle line has it)."""
        turns = [(_GREEN, gain)] if gain else []
        dur = summary.get("duration_min")
        if isinstance(dur, (int, float)):
            turns.append((_BLUE, f"{int(dur)} MIN CLASS"))
        discipline = summary.get("discipline")
        if isinstance(discipline, str) and discipline.strip() and discipline.upper() != middle:
            turns.append((_label_color(discipline), discipline.upper()))
        return turns

    @staticmethod
    def _draw_badges(matrix, headline_width: int) -> None:
        """A small gold star in each margin beside the headline, where there's room."""
        margin = (matrix.width - headline_width) // 2
        if margin < 2 * _COMPACT_BADGE_RADIUS + 2:
            return
        cy = 4.5
        for cx in ((margin - 1) / 2, matrix.width - 1 - (margin - 1) / 2):
            _fill_polygon(matrix, _star_points(cx, cy, _COMPACT_BADGE_RADIUS), _GOLD)

    def _draw_full_card(self, matrix, summary: dict, headline: str, value: str, gain: str | None) -> None:
        headline_font, value_font, info_font = self._card_fonts()
        dur = summary.get("duration_min")
        _centered(matrix, headline_font, 29, _GOLD, headline)
        if value:
            if get_text_width(value_font, value) > matrix.width - 2:
                value_font = headline_font
            _centered(matrix, value_font, 44, _WHITE, value)
        if gain:
            _centered(matrix, info_font, 54, _GREEN, gain)
        if isinstance(dur, (int, float)):
            _centered(matrix, info_font, 62 if gain else 56, _BLUE, f"{int(dur)} MIN CLASS")

    @staticmethod
    def _draw_sparkles(matrix, card_t: float, spots: list[tuple[int, int]]) -> None:
        """Twinkling sparkles around the card."""
        w, h = matrix.width, matrix.height
        for i, (x, y) in enumerate(spots):
            if int(card_t * 4 + i) % 3 == 0 and x < w and y < h:
                matrix.SetPixel(x, y, 255, 255, 200)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    matrix.SetPixel(x + dx, y + dy, 150, 130, 40)
