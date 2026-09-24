# display/ui/last_workout_screen.py

import re
from typing import Any, List, Optional, Tuple

from driver import graphics
from display.display import get_text_width, loaded_fonts
from utils import debug
from .screen import Screen

_WHITE = graphics.Color(255, 255, 255)
_GOLD  = graphics.Color(255, 215,   0)
_RED   = graphics.Color(220,  20,  20)
_BLUE  = graphics.Color(  0, 120, 255)

_DISCIPLINE_COLORS = {
    "cycling":       graphics.Color(220, 50,  20),
    "bike bootcamp": graphics.Color(220, 50,  20),
    "tread bootcamp": graphics.Color(20, 200, 80),
    "row bootcamp":  graphics.Color(0, 140, 255),
    "running":       graphics.Color(20,  200, 80),
    "walking":       graphics.Color(20,  180, 60),
    "outdoor run":   graphics.Color(20,  200, 80),
    "outdoor walk":  graphics.Color(20,  180, 60),
    "strength":      graphics.Color(255, 140,  0),
    "bootcamp":      graphics.Color(255, 140,  0),
    "rowing":        graphics.Color(0,   140, 255),
    "yoga":          graphics.Color(160,   0, 220),
    "meditation":    graphics.Color(120,   0, 180),
    "stretching":    graphics.Color(0,   200, 180),
    "cardio":        graphics.Color(255,  80,   0),
    "pilates":       graphics.Color(200, 100, 200),
    "barre":         graphics.Color(220,  80, 160),
    "boxing":        graphics.Color(255,  80,  0),
    "dance cardio":  graphics.Color(255,  80, 120),
    "mobility":      graphics.Color(0,  200, 180),
}


def _disc_color(discipline: str) -> graphics.Color:
    return _DISCIPLINE_COLORS.get(discipline.strip().lower(), _WHITE)


_SQUEEZE = {'.', ','}   # characters that get tight spacing on both sides
_SQUEEZE_ADV = 3        # advance used for the squeeze char itself
_SQUEEZE_PRE = 3        # advance used for the char immediately before a squeeze char


def _char_advance(font, ch: str, next_ch: str = '') -> int:
    if ch in _SQUEEZE:
        return _SQUEEZE_ADV
    if next_ch in _SQUEEZE:
        return _SQUEEZE_PRE
    return font.CharacterWidth(ord(ch))


def _draw_text(matrix, font, x: int, y: int, color, text: str) -> int:
    """Draw text with tight spacing on both sides of periods/commas. Returns final x."""
    for i, ch in enumerate(text):
        graphics.DrawText(matrix, font, x, y, color, ch)
        x += _char_advance(font, ch, text[i + 1] if i + 1 < len(text) else '')
    return x


def _text_width(font, text: str) -> int:
    return sum(_char_advance(font, ch, text[i + 1] if i + 1 < len(text) else '')
               for i, ch in enumerate(text))


def _truncate(font, text: str, max_px: int) -> str:
    while text and _text_width(font, text) > max_px:
        text = text[:-1]
    return text.rstrip()


def _draw_stat(matrix, font, x: int, y: int, color, text: str, max_px: int, right_align: bool = False, star: bool = False) -> None:
    """Draw 'value label' with tight gap between parts, truncating label if needed."""
    parts = text.split(' ', 1)
    val = parts[0]
    label = parts[1] if len(parts) == 2 else None
    val_w = _text_width(font, val)
    _GAP = 2
    star_w = (_STAR_W + 1) if star else 0
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
            star_top = y - font_h + (font_h - _STAR_H) // 2 + 1
            _draw_star(matrix, label_end_x + 1, star_top)


def _fmt_duration(minutes) -> str:
    if not isinstance(minutes, (int, float)):
        return ""
    m = int(minutes)
    h, rem = divmod(m, 60)
    return f"{h}h{rem}m" if h and rem else (f"{h}hr" if h else f"{m}m")


def _fmt_pace(pace_min_per_mile) -> str:
    if not isinstance(pace_min_per_mile, (int, float)):
        return ""
    total_sec = round(pace_min_per_mile * 60)
    return f"{total_sec // 60}:{total_sec % 60:02d}"


def _fmt_split(split_sec) -> str:
    """Format seconds-per-500m as M:SS."""
    if not isinstance(split_sec, (int, float)):
        return ""
    total_sec = round(split_sec)
    return f"{total_sec // 60}:{total_sec % 60:02d}"


def _wrap_two_lines(font, text: str, max_px: int) -> List[str]:
    """Split text into at most two lines that each fit within max_px."""
    words = text.split()
    if not words:
        return []
    line1 = ""
    for i, word in enumerate(words):
        test = (line1 + " " + word).strip()
        if get_text_width(font, test) <= max_px:
            line1 = test
        else:
            line2 = _truncate(font, " ".join(words[i:]), max_px)
            return [line1, line2] if line2 else [line1]
    return [line1]


def _middle_stats(summary: dict) -> List[Tuple[Optional[str], Optional[str]]]:
    """Return discipline-specific stat pairs for the middle of the screen."""
    disc = (summary.get("discipline") or "").strip().lower()

    if any(d in disc for d in ("cycling", "bike")):
        output = summary.get("total_output_kj")
        strive = summary.get("strive_score")
        spd = summary.get("avg_speed")
        spd_unit = summary.get("avg_speed_unit") or ""
        cad = summary.get("avg_cadence")
        res = summary.get("avg_resistance")
        dist_val = summary.get("distance")
        dist_unit = summary.get("distance_unit") or ""
        return [
            (
                f"{int(output)} kj" if isinstance(output, (int, float)) else None,
                f"{int(strive)} pts" if isinstance(strive, (int, float)) else None,
            ),
            (
                f"{spd:.1f} {spd_unit}" if isinstance(spd, (int, float)) else None,
                f"{int(cad)} rpm" if isinstance(cad, (int, float)) else None,
            ),
            (
                f"{int(res)}% res" if isinstance(res, (int, float)) else None,
                f"{dist_val:.1f} {dist_unit}" if isinstance(dist_val, (int, float)) else None,
            ),
        ]
    if any(d in disc for d in ("running", "walking", "outdoor", "tread", "hiking")):
        dist_val = summary.get("distance")
        dist_unit = summary.get("distance_unit") or ""
        pace_val = summary.get("avg_pace")
        elevation = summary.get("elevation")
        elevation_unit = summary.get("elevation_unit") or ""
        incline = summary.get("avg_incline")
        rows = [(
            f"{dist_val:.1f} {dist_unit}" if isinstance(dist_val, (int, float)) else None,
            f"{_fmt_pace(pace_val)}{(summary.get('avg_pace_unit') or '').replace('min', '')}" if pace_val is not None else None,
        )]
        if elevation is not None or incline is not None:
            rows.append((
                f"{elevation:g} {elevation_unit}" if isinstance(elevation, (int, float)) else None,
                f"{incline:g}% inc" if isinstance(incline, (int, float)) else None,
            ))
        return rows
    if "rowing" in disc or disc.startswith("row "):
        dist_val = summary.get("distance")
        dist_unit = summary.get("distance_unit") or ""
        spm_val = summary.get("avg_stroke_rate")
        split_val = summary.get("row_split_sec_per_500m")
        out_val = summary.get("avg_output_w")
        return [
            (
                f"{dist_val:g}{dist_unit}" if isinstance(dist_val, (int, float)) else None,
                f"{int(spm_val)} spm" if isinstance(spm_val, (int, float)) else None,
            ),
            (
                _fmt_split(split_val) + "/500" if split_val else None,
                f"{int(out_val)}W" if isinstance(out_val, (int, float)) else None,
            ),
        ]
    strive = summary.get("strive_score")
    hr_max = summary.get("hr_max")
    distance = summary.get("distance")
    distance_unit = summary.get("distance_unit") or ""
    avg_output = summary.get("avg_output_w")
    rows = []
    if strive is not None or hr_max is not None:
        rows.append((
            f"{strive:g} pts" if isinstance(strive, (int, float)) else None,
            f"{int(hr_max)} max" if isinstance(hr_max, (int, float)) else None,
        ))
    if distance is not None or avg_output is not None:
        rows.append((
            f"{distance:g} {distance_unit}" if isinstance(distance, (int, float)) else None,
            f"{int(avg_output)}W" if isinstance(avg_output, (int, float)) else None,
        ))
    return rows


# 5-wide × 5-tall pixel star (offsets from top-left)
_STAR_PIXELS = [
    (2,0),                          # top point
    (0,1),(1,1),(2,1),(3,1),(4,1),  # left point — center — right point
    (1,2),(2,2),(3,2),              # middle body
    (0,3),(2,3),(4,3),              # lower body with side points
    (1,4),(3,4),                    # two bottom points angled inward
]
_STAR_W = 5
_STAR_H = 5
_GOLD_COLOR = graphics.Color(255, 215, 0)


def _draw_star(matrix, x: int, y: int) -> None:
    for dx, dy in _STAR_PIXELS:
        matrix.SetPixel(x + dx, y + dy, 255, 215, 0)


# 7-wide × 6-tall pixel heart (offsets from top-left)
_HEART_PIXELS = [
    (1,0),(2,0),(4,0),(5,0),
    (0,1),(1,1),(2,1),(3,1),(4,1),(5,1),(6,1),
    (0,2),(1,2),(2,2),(3,2),(4,2),(5,2),(6,2),
    (1,3),(2,3),(3,3),(4,3),(5,3),
    (2,4),(3,4),(4,4),
    (3,5),
]
_HEART_W = 7
_HEART_H = 6


def _draw_heart(matrix, x: int, y: int, color: graphics.Color) -> None:
    """Draw a small pixel-art heart with its top-left at (x, y)."""
    r, g, b = color.red, color.green, color.blue
    for dx, dy in _HEART_PIXELS:
        matrix.SetPixel(x + dx, y + dy, r, g, b)


STAT_TIER_INTERVAL_SECONDS = 5.0


class LastWorkoutScreen(Screen):
    """Displays key stats from a workout summary on a 64x64 LED matrix.

    state should be the dict returned by peloton.summaries.summarize_workout().

    The discipline/title/duration header and the bottom HR/calories bar stay
    fixed for the whole screen. The middle stat block rotates through tiers
    (performance stats, then instructor) when there's more than one tier to
    show, on the same "hold, then flip" pattern as UsernameScreen's details.
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
        summary = state or {}
        if not summary:
            return False

        title_font  = loaded_fonts.get("discipline")
        titles_font = loaded_fonts.get("titles")
        stat_font   = loaded_fonts.get("stats")

        if not title_font or not stat_font:
            debug.error("Fonts not loaded; call initialize_fonts() first")
            return False

        text_font = loaded_fonts.get("info") or titles_font or stat_font  # fallback if titles not loaded

        discipline = (summary.get("discipline") or "Workout").strip()
        font_h = getattr(stat_font, "height", 8)
        w = matrix.width
        if matrix.height < 64:
            if summary.get('compact_page') == 1:
                stats = []
                for left, right in _middle_stats(summary):
                    stats.extend(value for value in (left, right) if value)
                hr = summary.get('hr_avg')
                calories = summary.get('calories')
                if isinstance(hr, (int, float)):
                    stats.append(f'{int(hr)} avg HR')
                if isinstance(calories, (int, float)):
                    stats.append(f'{int(calories)} cal')
                lines = [(7, 'WORKOUT STATS', _disc_color(discipline))]
                lines += [(16 + index * 8, value, _WHITE)
                          for index, value in enumerate(stats[:2])]
            else:
                lines = [
                    (7, str(summary.get('discipline') or 'Workout'), _disc_color(discipline)),
                    (16, _fmt_duration(summary.get('duration_min')), _BLUE),
                    (26, str(summary.get('title') or ''), _WHITE),
                ]
            for y, text, color in lines:
                text = _truncate(text_font, text, w - (10 if summary.get('login_required') and y == 27 else 4))
                graphics.DrawText(matrix, text_font, 2, y, color, text)
            return True

        # ── Line 1: discipline ────────────────────────────────────────────
        disc_text = discipline.upper()
        disc_font = title_font
        # Bike Bootcamp is clearer as two 5x8 lines than one tiny 4x6 line.
        # Starting the two-line header higher recovers the added vertical
        # space and keeps the title plus all three cycling stat rows legible.
        if discipline.lower() == 'bike bootcamp' and titles_font:
            disc_font = titles_font
        elif get_text_width(disc_font, disc_text) > w - 2 and text_font and (
                get_text_width(text_font, disc_text) <= w - 2):
            disc_font = text_font
        disc_lines = _wrap_two_lines(disc_font, disc_text, w - 2)[:2] or [""]
        disc_font_h = getattr(disc_font, "height", 9)
        disc_y = 8 if len(disc_lines) > 1 else 12
        for i, line in enumerate(disc_lines):
            dx = max((w - get_text_width(disc_font, line)) // 2, 1)
            graphics.DrawText(matrix, disc_font, dx, disc_y + i * disc_font_h,
                              _disc_color(discipline), line)
        block_y = disc_y + (len(disc_lines) - 1) * disc_font_h

        # ── Line 2: duration (centered) ───────────────────────────────────
        dur_min = summary.get("duration_min")
        # Tighten the gap when the discipline wraps to 2 lines, to leave room for stats below.
        dur_y = block_y + (7 if len(disc_lines) > 1 else 10)
        if isinstance(dur_min, (int, float)):
            dur_val = str(int(dur_min))
            dur_label = "min"
            dur_val_w = _text_width(text_font, dur_val)
            dur_label_w = _text_width(text_font, dur_label)
            dur_total_w = dur_val_w + 1 + dur_label_w
            dur_x = max((w - dur_total_w) // 2, 2)
            _draw_text(matrix, text_font, dur_x, dur_y, _BLUE, dur_val)
            _draw_text(matrix, text_font, dur_x + dur_val_w + 1, dur_y, _BLUE, dur_label)

        # ── Lines 3–4: title below the duration with a visible gap ────────
        title = (summary.get("title") or "").strip()
        title_stripped = re.sub(r'^\d+\s*min\s*', '', title, flags=re.IGNORECASE).strip() or title
        title_lines = _wrap_two_lines(text_font, title_stripped, w - 4)
        for i, line in enumerate(title_lines[:2]):
            tx = max((w - _text_width(text_font, line)) // 2, 2)
            _draw_text(matrix, text_font, tx, dur_y + 7 + i * 7, _WHITE, line)
        header_bottom = dur_y + 7 + max(len(title_lines[:2]) - 1, 0) * 7

        # ── Stats: stacked between the header and the HR/cal bar ──────────
        # The middle block rotates through tiers (stats, then instructor) when
        # there's more than one tier to show; header and HR/cal stay fixed.
        instructor = (summary.get("instructor") or "").strip()
        tiers = ["stats"]
        if instructor:
            tiers.append("instructor")
        tier = tiers[int(self.elapsed / STAT_TIER_INTERVAL_SECONDS) % len(tiers)]

        _BOTTOM_Y = 61
        _STAT_STEP = 6
        mid = w // 2 + 1
        _half = mid - 2 - 2
        last_row_y = _BOTTOM_Y - _STAT_STEP  # Leave room for the HR/cal row below the last stat.

        if tier == "instructor":
            instr_font = text_font
            instr_text = _truncate(instr_font, instructor.upper(), w - 4)
            instr_y = header_bottom + (last_row_y - header_bottom) // 2 + 3
            ix = max((w - _text_width(instr_font, instr_text)) // 2, 2)
            label = "INSTRUCTOR"
            label_font = stat_font
            label_y = instr_y - 8
            lx = max((w - _text_width(label_font, label)) // 2, 2)
            _draw_text(matrix, label_font, lx, label_y, graphics.Color(145, 165, 190), label)
            _draw_text(matrix, instr_font, ix, instr_y, _WHITE, instr_text)
        else:
            stats = _middle_stats(summary)
            default_top = last_row_y - _STAT_STEP * (len(stats) - 1)
            if default_top >= header_bottom + _STAT_STEP or len(stats) <= 1:
                top, step = default_top, _STAT_STEP
            else:
                # Not enough room at the normal step; compress rows to fit between
                # the header and the HR/cal bar instead of overlapping either one.
                top = header_bottom + _STAT_STEP
                step = max(1, (last_row_y - top) // (len(stats) - 1))
            stat_ys = [top + step * i for i in range(len(stats))]
            for row_y, (left, right) in zip(stat_ys, stats):
                if left:
                    _draw_stat(matrix, stat_font, 2, row_y, _WHITE, left, _half,
                               star=bool(summary.get("is_output_pr")) and left.endswith("kj"))
                if right:
                    _draw_stat(matrix, stat_font, w - 1, row_y, _WHITE, right, w - mid - 2, right_align=True)

        # ── Bottom left: ♥ HR ─────────────────────────────────────────────
        hr_val = summary.get("hr_avg")
        if isinstance(hr_val, (int, float)):
            heart_top = _BOTTOM_Y - font_h + (font_h - _HEART_H) // 2 + 1
            _draw_heart(matrix, 2, heart_top, _RED)
            graphics.DrawText(matrix, stat_font, 2 + _HEART_W + 1, _BOTTOM_Y, _WHITE, str(int(hr_val)))

        # ── Bottom right: calories ─────────────────────────────────────────
        cal_val = summary.get("calories")
        if isinstance(cal_val, (int, float)):
            right = w - 1 - (8 if summary.get('login_required') else 0)
            _draw_stat(matrix, stat_font, right, _BOTTOM_Y, _WHITE, f"{int(cal_val)} cal",
                       max(0, right - mid), right_align=True)

        # ── PR badge ──────────────────────────────────────────────────────
        if summary.get("is_pr"):
            pr_text = "PR"
            pr_x = w - get_text_width(stat_font, pr_text) - 2
            graphics.DrawText(matrix, stat_font, pr_x, 22, _GOLD, pr_text)

        return True
