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


def _stat_details(summary: dict) -> List[dict]:
    """Discipline-specific stat values with spelled-out labels, one detail per
    stat, for the rotating single-item display. Mirrors _middle_stats' field
    selection and discipline routing exactly, but builds a full label instead
    of the abbreviated unit that fits _middle_stats' packed side-by-side rows
    (e.g. "output" instead of "kj") since only one detail is shown at a time.
    """
    disc = (summary.get("discipline") or "").strip().lower()
    details = []

    def add(label, value):
        if value is not None:
            details.append({'label': label, 'value': value})

    if any(d in disc for d in ("cycling", "bike")):
        output = summary.get("total_output_kj")
        strive = summary.get("strive_score")
        spd = summary.get("avg_speed")
        spd_unit = summary.get("avg_speed_unit") or ""
        cad = summary.get("avg_cadence")
        res = summary.get("avg_resistance")
        dist_val = summary.get("distance")
        dist_unit = summary.get("distance_unit") or ""
        add("total output", f"{int(output)} kj" if isinstance(output, (int, float)) else None)
        add("strive score", f"{int(strive)}" if isinstance(strive, (int, float)) else None)
        add("avg speed", f"{spd:.1f} {spd_unit}" if isinstance(spd, (int, float)) else None)
        add("avg cadence", f"{int(cad)} rpm" if isinstance(cad, (int, float)) else None)
        add("avg resistance", f"{int(res)}%" if isinstance(res, (int, float)) else None)
        add("distance", f"{dist_val:.1f} {dist_unit}" if isinstance(dist_val, (int, float)) else None)
    elif any(d in disc for d in ("running", "walking", "outdoor", "tread", "hiking")):
        dist_val = summary.get("distance")
        dist_unit = summary.get("distance_unit") or ""
        pace_val = summary.get("avg_pace")
        elevation = summary.get("elevation")
        elevation_unit = summary.get("elevation_unit") or ""
        incline = summary.get("avg_incline")
        add("distance", f"{dist_val:.1f} {dist_unit}" if isinstance(dist_val, (int, float)) else None)
        add("avg pace", f"{_fmt_pace(pace_val)}{(summary.get('avg_pace_unit') or '').replace('min', '')}"
            if pace_val is not None else None)
        if elevation is not None or incline is not None:
            add("elevation gain", f"{elevation:g} {elevation_unit}" if isinstance(elevation, (int, float)) else None)
            add("avg incline", f"{incline:g}%" if isinstance(incline, (int, float)) else None)
    elif "rowing" in disc or disc.startswith("row "):
        dist_val = summary.get("distance")
        dist_unit = summary.get("distance_unit") or ""
        spm_val = summary.get("avg_stroke_rate")
        split_val = summary.get("row_split_sec_per_500m")
        out_val = summary.get("avg_output_w")
        add("distance", f"{dist_val:g}{dist_unit}" if isinstance(dist_val, (int, float)) else None)
        add("stroke rate", f"{int(spm_val)} spm" if isinstance(spm_val, (int, float)) else None)
        add("split per 500m", _fmt_split(split_val) if split_val else None)
        add("avg output", f"{int(out_val)}W" if isinstance(out_val, (int, float)) else None)
    else:
        strive = summary.get("strive_score")
        hr_max = summary.get("hr_max")
        distance = summary.get("distance")
        distance_unit = summary.get("distance_unit") or ""
        avg_output = summary.get("avg_output_w")
        add("strive score", f"{strive:g}" if isinstance(strive, (int, float)) else None)
        add("max heart rate", f"{int(hr_max)}" if isinstance(hr_max, (int, float)) else None)
        add("distance", f"{distance:g} {distance_unit}" if isinstance(distance, (int, float)) else None)
        add("avg output", f"{int(avg_output)}W" if isinstance(avg_output, (int, float)) else None)

    instructor = (summary.get("instructor") or "").strip()
    if instructor:
        add("instructor", instructor)
    return details


def rotating_details(summary: dict, matrix_height: int = 64) -> List[dict]:
    """Details the stats phase cycles through, in order.

    64-row panels show the instructor in the intro, so only stats rotate.
    32-row panels have no room for it there, so it leads the rotation.
    """
    details = _stat_details(summary)
    stats = [d for d in details if d['label'] != 'instructor']
    if matrix_height < 64:
        return [d for d in details if d['label'] == 'instructor'] + stats
    return stats


# 7-wide × 7-tall pixel trophy marking PRs: 'C' gold cup, 'B' darker stem/base.
_TROPHY_ROWS = (
    "CCCCCCC",
    "C.CCC.C",
    ".CCCCC.",
    "..CCC..",
    "...B...",
    "...B...",
    "..BBB..",
)
_TROPHY_W = 7
_TROPHY_H = 7
_TROPHY_COLORS = {'C': (255, 215, 0), 'B': (205, 145, 0)}


def _draw_trophy(matrix, x: int, y: int) -> None:
    """Draw the PR trophy with its top-left at (x, y)."""
    for dy, row in enumerate(_TROPHY_ROWS):
        for dx, cell in enumerate(row):
            if cell in _TROPHY_COLORS:
                matrix.SetPixel(x + dx, y + dy, *_TROPHY_COLORS[cell])


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


def _draw_hr_calories(matrix, summary: dict, stat_font, bottom_y: int) -> None:
    """Bottom bar: ♥ average HR on the left, calories on the right."""
    font_h = getattr(stat_font, "height", 8)
    w = matrix.width
    hr_val = summary.get("hr_avg")
    if isinstance(hr_val, (int, float)):
        heart_top = bottom_y - font_h + (font_h - _HEART_H) // 2 + 1
        _draw_heart(matrix, 2, heart_top, _RED)
        graphics.DrawText(matrix, stat_font, 2 + _HEART_W + 1, bottom_y, _WHITE, str(int(hr_val)))

    cal_val = summary.get("calories")
    if isinstance(cal_val, (int, float)):
        # Leave the bottom-right corner free for the login padlock.
        right = w - 1 - (8 if summary.get('login_required') else 0)
        mid = w // 2 + 1
        _draw_stat(matrix, stat_font, right, bottom_y, _WHITE, f"{int(cal_val)} cal",
                   max(0, right - mid), right_align=True)


def _draw_short_lines(matrix, font, lines: List[str], top_y: int, summary: dict) -> None:
    """Up to two centered 4x6 lines, 7px apart, for the 32-row layout.

    The second line sits on the bottom rows, so it is narrowed to clear the
    login padlock (bottom right) and stale-data clock (bottom left) when shown.
    """
    w = matrix.width
    for i, line in enumerate(lines[:2]):
        if i == 1:
            left = 9 if summary.get('data_stale') else 2
            right = 9 if summary.get('login_required') else 2
            line = _truncate(font, line, w - 2 * max(left, right))
        tx = max((w - _text_width(font, line)) // 2, 2)
        _draw_text(matrix, font, tx, top_y + i * 7, _WHITE, line)


# Default seconds each intro/stat holds for; overridable via the
# `last_workout_detail_interval` display config key.
LAST_WORKOUT_DETAIL_INTERVAL_SECONDS = 4.0


class LastWorkoutScreen(Screen):
    """Displays key stats from a workout summary on a 64x64 LED matrix.

    state should be the dict returned by peloton.summaries.summarize_workout().

    The bottom HR/calories bar stays fixed for the whole screen. Everything
    above it goes through two phases:
      1. Intro (first detail_interval seconds): discipline/duration/title,
         plus the instructor's name underneath if there is one.
      2. Stats: the discipline title stays fixed at the top; duration/title/
         instructor clear and one stat at a time, large, cycles through the
         freed-up space below it, on the same "hold, then rise into place"
         pattern as UsernameScreen's details, instead of bundling every stat
         into small rows at once.
    """

    animated = True
    atomic_frames = True

    def __init__(self, detail_interval: float = LAST_WORKOUT_DETAIL_INTERVAL_SECONDS):
        self.elapsed = 0.0
        self.detail_interval = detail_interval

    def on_enter(self, matrix, state=None):
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += max(0, dt)

    def _render_short(self, matrix, summary: dict, discipline: str, title_font, text_font, stat_font) -> bool:
        """64x32 version of the two-phase layout.

        Same order as 64x64 with the room redistributed:
          intro: discipline / duration (+ gold PR) / title on up to two lines
          stats: discipline / label / one large value / ♥ HR + calories bar
        The instructor leads the stat rotation instead of sitting in the intro,
        and the HR/calories bar only shows during stats; there is no room for
        either under a two-line title.
        """
        w = matrix.width
        bottom_y = matrix.height - 1
        value_big = loaded_fonts.get("countdown") or title_font
        grey = graphics.Color(145, 165, 190)

        # ── Discipline: fixed at the top for both phases ────────────────────
        disc_text = discipline.upper()
        disc_font = title_font
        if get_text_width(disc_font, disc_text) > w - 2:
            disc_font = text_font
        disc_text = _truncate(disc_font, disc_text, w - 2)
        disc_y = 7 if disc_font is title_font else 6
        dx = max((w - get_text_width(disc_font, disc_text)) // 2, 1)
        graphics.DrawText(matrix, disc_font, dx, disc_y, _disc_color(discipline), disc_text)

        if self.elapsed < self.detail_interval:
            dur_min = summary.get("duration_min")
            if isinstance(dur_min, (int, float)):
                dur_text = f"{int(dur_min)} MIN"
                x = max((w - _text_width(text_font, dur_text)) // 2, 2)
                _draw_text(matrix, text_font, x, 15, _BLUE, dur_text)
            if summary.get("is_pr"):
                _draw_trophy(matrix, w - _TROPHY_W - 2, 9)
            title = (summary.get("title") or "").strip()
            title = re.sub(r'^\d+\s*min\s*', '', title, flags=re.IGNORECASE).strip() or title
            title_lines = _wrap_two_lines(text_font, title, w - 4)
            _draw_short_lines(matrix, text_font, title_lines, 22, summary)
            if len(title_lines) < 2 and not rotating_details(summary, matrix.height):
                # No stats phase to carry the bar (e.g. meditation), and a
                # one-line title leaves its rows free.
                _draw_hr_calories(matrix, summary, stat_font, bottom_y)
            return True

        details = rotating_details(summary, matrix.height)
        if details:
            interval = self.detail_interval or LAST_WORKOUT_DETAIL_INTERVAL_SECONDS
            stats_elapsed = self.elapsed - self.detail_interval
            detail = details[int(stats_elapsed / interval) % len(details)]
            # Rise 2px rather than 3 so the value never brushes the bottom bar.
            offset = max(0, round(2 * (1 - min(1, (stats_elapsed % interval) / 0.3))))
            value = detail['value'].upper()
            value_font = next((f for f in (value_big, title_font, text_font)
                               if get_text_width(f, value) <= w - 4), text_font)
            label = _truncate(stat_font, detail['label'].upper(), w - 4)
            lx = max((w - _text_width(stat_font, label)) // 2, 2)
            _draw_text(matrix, stat_font, lx, 15 + offset, grey, label)
            if value_font is text_font and get_text_width(text_font, value) > w - 4:
                # Long instructor names wrap into the bar's rows, so this one
                # detail goes without the HR/calories bar.
                _draw_short_lines(matrix, text_font, _wrap_two_lines(text_font, value, w - 4),
                                  22 + offset, summary)
                return True
            else:
                value_y = 24 if value_font is value_big else 23
                vx = max((w - get_text_width(value_font, value)) // 2, 2)
                graphics.DrawText(matrix, value_font, vx, value_y + offset, _WHITE, value)
                if summary.get("is_output_pr") and detail['label'] == 'total output':
                    star_x = vx + get_text_width(value_font, value) + 2
                    _draw_trophy(matrix, min(star_x, w - _TROPHY_W), value_y + offset - _TROPHY_H)

        _draw_hr_calories(matrix, summary, stat_font, bottom_y)
        return True

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
        w = matrix.width
        if matrix.height < 64 and 'compact_page' not in summary:
            return self._render_short(matrix, summary, discipline, title_font, text_font, stat_font)
        if matrix.height < 64:
            # Legacy two-page layout, kept for display.compact_workout_pages.
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

        _BOTTOM_Y = 61
        _STAT_STEP = 6
        last_row_y = _BOTTOM_Y - _STAT_STEP  # Leave room for the HR/cal row below.

        all_details = _stat_details(summary)
        stat_details = [d for d in all_details if d['label'] != 'instructor']
        instructor_detail = next((d for d in all_details if d['label'] == 'instructor'), None)
        in_intro = self.elapsed < self.detail_interval

        # ── Line 1: discipline ── stays on screen for both intro and stats ──
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

        if in_intro:
            # ── Line 2: duration (centered) ─────────────────────────────────
            dur_min = summary.get("duration_min")
            # Tighten the gap when the discipline wraps to 2 lines, to leave room for the title below.
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

            # ── Lines 3–4: title below the duration with a visible gap ──────
            title = (summary.get("title") or "").strip()
            title_stripped = re.sub(r'^\d+\s*min\s*', '', title, flags=re.IGNORECASE).strip() or title
            title_lines = _wrap_two_lines(text_font, title_stripped, w - 4)
            for i, line in enumerate(title_lines[:2]):
                tx = max((w - _text_width(text_font, line)) // 2, 2)
                _draw_text(matrix, text_font, tx, dur_y + 7 + i * 7, _WHITE, line)
            header_bottom = dur_y + 7 + max(len(title_lines[:2]) - 1, 0) * 7

            # ── Instructor, if any, underneath the title ────────────────────
            if instructor_detail:
                offset = max(0, round(3 * (1 - min(1, self.elapsed / 0.3))))
                # Two-line titles need extra clearance below their second
                # line before the instructor block starts.
                two_line_extra = 2 if len(title_lines[:2]) > 1 else 0
                available_top = header_bottom + _STAT_STEP
                available_bottom = last_row_y
                min_top = header_bottom + 5
                value_font = text_font
                value_lines = _wrap_two_lines(value_font, instructor_detail['value'].upper(), w - 4)[:2]
                mid_y = available_top + (available_bottom - available_top) // 2 - 3
                show_label = len(value_lines) == 1
                block_lines = (1 if show_label else 0) + len(value_lines)
                y = max(mid_y - 3 * (block_lines - 1), min_top) + two_line_extra
                if show_label:
                    label_text = _truncate(stat_font, "INSTRUCTOR", w - 4)
                    lx = max((w - _text_width(stat_font, label_text)) // 2, 2)
                    _draw_text(matrix, stat_font, lx, y + offset, graphics.Color(145, 165, 190), label_text)
                    y += 8
                for line in value_lines:
                    vx = max((w - _text_width(value_font, line)) // 2, 2)
                    _draw_text(matrix, value_font, vx, y + offset, _WHITE, line)
                    y += 7
        elif stat_details:
            # ── Stats phase: discipline title stays; everything below it ────
            # (duration/workout-title/instructor) is replaced by one rotating
            # stat at a time, using the space freed up below the title.
            interval = self.detail_interval or LAST_WORKOUT_DETAIL_INTERVAL_SECONDS
            stats_elapsed = self.elapsed - self.detail_interval
            index = int(stats_elapsed / interval) % len(stat_details)
            phase_seconds = stats_elapsed % interval
            detail = stat_details[index]
            # Each new detail rises into place during its first 0.3 seconds.
            offset = max(0, round(3 * (1 - min(1, phase_seconds / 0.3))))
            available_top = block_y + _STAT_STEP
            mid_y = (available_top + last_row_y) // 2
            value_font = (title_font if get_text_width(title_font, detail['value'].upper()) <= w - 4
                          else text_font)
            label_y = mid_y - 8
            value_y = label_y + 15
            label_text = _truncate(stat_font, detail['label'].upper(), w - 4)
            lx = max((w - _text_width(stat_font, label_text)) // 2, 2)
            _draw_text(matrix, stat_font, lx, label_y + offset, graphics.Color(145, 165, 190), label_text)

            value_text = _truncate(value_font, detail['value'].upper(), w - 4)
            vx = max((w - get_text_width(value_font, value_text)) // 2, 2)
            star = bool(summary.get("is_output_pr")) and detail['label'] == 'total output'
            graphics.DrawText(matrix, value_font, vx, value_y + offset, _WHITE, value_text)
            if star:
                star_x = vx + get_text_width(value_font, value_text) + 2
                _draw_trophy(matrix, min(star_x, w - _TROPHY_W), value_y + offset - _TROPHY_H)

        _draw_hr_calories(matrix, summary, stat_font, _BOTTOM_Y)

        # ── PR trophy, where the "PR" letters used to sit ─────────────────
        # Intro only: in the stats phase it would touch wide labels, and the
        # output value carries its own trophy there.
        if summary.get("is_pr") and in_intro:
            _draw_trophy(matrix, w - _TROPHY_W - 2, 16)

        return True
