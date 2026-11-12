# display/ui/last_workout_screen.py

import re
from typing import Any, List, Optional

from driver import graphics
from display.display import get_text_width, loaded_fonts
from utils import debug
from .logo_art import ZONE_COLORS
from .screen import Screen
from .username import MARGIN as SCROLL_MARGIN, UsernameScreen

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


# The length at the front of a title: "20 min HIIT Ride", and the free workouts Peloton names by their
# exact length, "60 min 11 sec Just Walk" or "41 sec Just Walk". The page shows the length itself.
_TITLE_LENGTH = re.compile(r'^\s*(?:\d+\s*min(?:ute)?s?\b\s*)?(?:\d+\s*sec(?:ond)?s?\b\s*)?', re.IGNORECASE)


def title_without_length(title) -> str:
    """A workout's title without the length it starts with; as it is when that's all there is."""
    title = str(title or '').strip()
    return _TITLE_LENGTH.sub('', title, count=1).strip() or title


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


def _whole(value) -> int:
    """Round half up, as Peloton does (Python's round() sends 0.5 to even)."""
    return int(value + 0.5)


def _fmt_strive(strive) -> str:
    """Strive Score to one decimal, as the Peloton app shows it."""
    return f"{strive:.1f}"


def _fmt_output(output) -> Optional[str]:
    """Total Output in kJ, or None when there is none: outdoor runs and walks
    carry a total_work of 0, which isn't an output to show."""
    return f"{_whole(output)} kj" if isinstance(output, (int, float)) and output > 0 else None


def _fmt_distance(distance, unit) -> str:
    """Miles and km to two decimals, as the Peloton app shows them, with a comma from 1,000."""
    return f"{distance:,.2f} {unit}".rstrip()


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


def _stat_details(summary: dict) -> List[dict]:
    """Discipline-specific stat values with spelled-out labels, one detail per
    stat, for the rotating single-item display (e.g. "output", not "kj")."""
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
        add("total output", f"{_whole(output)} kj" if isinstance(output, (int, float)) else None)
        add("strive score", _fmt_strive(strive) if isinstance(strive, (int, float)) else None)
        add("avg speed", f"{spd:.1f} {spd_unit}" if isinstance(spd, (int, float)) else None)
        add("avg cadence", f"{_whole(cad)} rpm" if isinstance(cad, (int, float)) else None)
        add("avg resistance", f"{_whole(res)}%" if isinstance(res, (int, float)) else None)
        add("distance", _fmt_distance(dist_val, dist_unit) if isinstance(dist_val, (int, float)) else None)
    elif any(d in disc for d in ("running", "walking", "outdoor", "tread", "hiking")):
        dist_val = summary.get("distance")
        dist_unit = summary.get("distance_unit") or ""
        pace_val = summary.get("avg_pace")
        elevation = summary.get("elevation")
        elevation_unit = summary.get("elevation_unit") or ""
        incline = summary.get("avg_incline")
        add("distance", _fmt_distance(dist_val, dist_unit) if isinstance(dist_val, (int, float)) else None)
        add("avg pace", f"{_fmt_pace(pace_val)}{(summary.get('avg_pace_unit') or '').replace('min', '')}"
            if pace_val is not None else None)
        strive = summary.get("strive_score")
        add("strive score", _fmt_strive(strive) if isinstance(strive, (int, float)) else None)
        add("total output", _fmt_output(summary.get("total_output_kj")))
        if elevation is not None or incline is not None:
            add("elevation gain", f"{elevation:g} {elevation_unit}" if isinstance(elevation, (int, float)) else None)
            add("avg incline", f"{incline:.1f}%" if isinstance(incline, (int, float)) else None)
    elif "rowing" in disc or disc.startswith("row "):
        dist_val = summary.get("distance")
        dist_unit = summary.get("distance_unit") or ""
        spm_val = summary.get("avg_stroke_rate")
        split_val = summary.get("row_split_sec_per_500m")
        strive = summary.get("strive_score")
        add("total output", _fmt_output(summary.get("total_output_kj")))
        add("strive score", _fmt_strive(strive) if isinstance(strive, (int, float)) else None)
        add("distance", f"{_whole(dist_val):,}{dist_unit}" if isinstance(dist_val, (int, float)) else None)
        add("stroke rate", f"{_whole(spm_val)} spm" if isinstance(spm_val, (int, float)) else None)
        add("split per 500m", _fmt_split(split_val) if split_val else None)
    else:
        strive = summary.get("strive_score")
        hr_max = summary.get("hr_max")
        distance = summary.get("distance")
        distance_unit = summary.get("distance_unit") or ""
        avg_output = summary.get("avg_output_w")
        add("strive score", _fmt_strive(strive) if isinstance(strive, (int, float)) else None)
        add("max heart rate", f"{_whole(hr_max)}" if isinstance(hr_max, (int, float)) else None)
        add("distance", _fmt_distance(distance, distance_unit) if isinstance(distance, (int, float)) else None)
        add("avg output", f"{_whole(avg_output)}W" if isinstance(avg_output, (int, float)) else None)

    instructor = (summary.get("instructor") or "").strip()
    if instructor:
        add("instructor", instructor)
    return details


# Disciplines whose workout page ends with the muscle-groups slide. Peloton sends
# the data for most workouts; it's only shown where the page is light on stats.
MUSCLE_DISCIPLINES = {'strength'}


def rotating_details(summary: dict, matrix_height: int = 64) -> List[dict]:
    """Details the stats phase cycles through, in order.

    64-row panels show the instructor in the intro, so only stats rotate.
    32-row panels have no room for it there, so it leads the rotation.
    The workout graph and heart-rate zone bar close out the rotation when the
    workout recorded them, then the top muscle groups for MUSCLE_DISCIPLINES.
    """
    details = _stat_details(summary)
    stats = [d for d in details if d['label'] != 'instructor']
    if matrix_height < 64:
        stats = [d for d in details if d['label'] == 'instructor'] + stats
    graph = summary.get('graph')
    if isinstance(graph, dict) and graph.get('values'):
        label = 'output' if graph.get('metric') == 'output' else 'heart rate'
        stats.append({'label': label, 'value': '', 'kind': 'graph'})
    zones = summary.get('hr_zone_seconds')
    if isinstance(zones, list) and len(zones) == 5 and sum(zones) > 0:
        stats.append({'label': 'hr zones', 'value': '', 'kind': 'zones'})
    if summary.get('muscles') and (summary.get('discipline') or '').strip().lower() in MUSCLE_DISCIPLINES:
        stats.append({'label': 'muscles worked', 'value': '', 'kind': 'muscles'})
    for index, view in enumerate(insight_views(summary)):
        # Workout compare: 64 rows show the card then the bars; 32 rows the bars then the sentence pages.
        frames = (['insight_card', 'insight_bars'] if matrix_height >= 64
                  else ['insight_bars'] + ['insight_words'] * len(view['pages32']))
        for page, kind in enumerate(frames):
            detail = {'label': 'insight', 'value': '', 'kind': kind, 'index': index}
            if kind == 'insight_words':
                detail['page'] = page - 1
            stats.append(detail)
    return stats


# Workout compare frames (peloton/insight_lines.board_view), after the chart slides.
INSIGHT_KINDS = ('insight_card', 'insight_bars', 'insight_words')
MAX_INSIGHT_VIEWS = 2
_FIGURE_KEYS = {'bars': ('today', 'usual'), 'share': ('pct',), 'blocks': ('total', 'lit')}


def _strings(lines, most) -> bool:
    return (isinstance(lines, list) and 0 < len(lines) <= most
            and all(isinstance(line, str) and line.strip() for line in lines))


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _good_view(view) -> bool:
    if not isinstance(view, dict):
        return False
    figure, colour, pages = view.get('figure'), view.get('colour'), view.get('pages32')
    if not (isinstance(figure, dict) and figure.get('kind') in _FIGURE_KEYS
            and all(_number(figure.get(key)) for key in _FIGURE_KEYS[figure['kind']])):
        return False
    if figure['kind'] == 'bars' and not all(isinstance(figure.get(k), str) for k in ('today_text', 'usual_text')):
        return False
    if not all(isinstance(figure.get(key, ''), str) for key in ('unit', 'label')):
        return False
    if figure['kind'] == 'share' and figure['pct'] > 100:
        return False
    if figure['kind'] == 'blocks' and not (isinstance(figure['total'], int) and isinstance(figure['lit'], int)
                                           and 0 < figure['total'] <= 30 and figure['lit'] <= figure['total']):
        return False
    reason = view.get('reason')
    return (isinstance(colour, (list, tuple)) and len(colour) == 3
            and all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in colour)
            and all(isinstance(view.get(key), str) and view[key].strip() for key in ('headline', 'footer'))
            and (reason is None or isinstance(reason, str))
            and _strings(view.get('lines64'), 5)
            and isinstance(pages, list) and 0 < len(pages) <= 2 and all(_strings(page, 3) for page in pages))


def insight_views(summary: dict) -> List[dict]:
    """The workout's insight views (workout compare), at most two, skipping damaged ones: the cache could
    hold anything. A version 2 `insight` (one dict) is never drawn."""
    views = summary.get('insights')
    if not isinstance(views, list):
        return []
    return [view for view in views if _good_view(view)][:MAX_INSIGHT_VIEWS]


# Heart-rate zone colors, zone 1 first; also used to color graph columns.
HR_ZONE_COLORS = list(ZONE_COLORS)
_LABEL_GREY = (145, 165, 190)
_PEAK_WHITE = (255, 255, 255)


def _draw_graph(matrix, summary: dict, font, label_y: int, top: int, bottom: int) -> None:
    """Workout graph: label and peak on one row, then one column per sample.

    Columns take the heart-rate zone color of that moment, or the discipline
    color when there's no heart-rate data; the peak column is capped in gold.
    """
    graph = summary['graph']
    w = matrix.width
    values = graph['values']
    zones = graph.get('zones') or [None] * len(values)
    label = 'OUTPUT' if graph.get('metric') == 'output' else 'HEART RATE'
    peak = f"{graph.get('peak', max(values))}{'W' if graph.get('metric') == 'output' else ''}"
    _draw_text(matrix, font, 2, label_y, graphics.Color(*_LABEL_GREY), label)
    _draw_text(matrix, font, w - 2 - _text_width(font, peak), label_y, _WHITE, peak)

    # Output reads best from zero; heart rate sits in a narrow band, so it's
    # scaled from just under its lowest value to show the shape.
    floor = 0 if graph.get('metric') == 'output' else max(0, min(values) - 10)
    ceiling = max(values)
    height = bottom - top + 1
    columns = w - 4
    fallback = _disc_color(summary.get('discipline') or '')
    peak_x = None
    for col in range(columns):
        i = col * len(values) // columns
        value = values[i]
        bar = 0 if ceiling <= floor else round((value - floor) / (ceiling - floor) * (height - 1))
        bar = max(1, bar) if value > floor else 0
        zone = zones[i] if i < len(zones) else None
        r, g, b = (HR_ZONE_COLORS[zone - 1] if zone else
                   (fallback.red, fallback.green, fallback.blue))
        x = 2 + col
        for y in range(bottom - bar + 1, bottom + 1):
            matrix.SetPixel(x, y, r, g, b)
        if value == ceiling and peak_x is None:
            peak_x = x
            matrix.SetPixel(x, bottom - bar, 255, 215, 0)


def _draw_zones(matrix, seconds: List[float], font, big_font, label_y: int,
                bar_top: int, bar_bottom: int, text_y: int) -> None:
    """Stacked zone bar across the panel, then the zone you spent longest in."""
    w = matrix.width
    label = 'HR ZONES'
    _draw_text(matrix, font, max((w - _text_width(font, label)) // 2, 2), label_y,
               graphics.Color(*_LABEL_GREY), label)
    total = sum(seconds)
    span = w - 4
    # Largest-remainder rounding so the segments fill the bar exactly.
    exact = [s / total * span for s in seconds]
    widths = [int(e) for e in exact]
    for i in sorted(range(5), key=lambda i: exact[i] - widths[i], reverse=True)[:span - sum(widths)]:
        widths[i] += 1
    x = 2
    for zone, width in enumerate(widths):
        r, g, b = HR_ZONE_COLORS[zone]
        for dx in range(width):
            for y in range(bar_top, bar_bottom + 1):
                matrix.SetPixel(x + dx, y, r, g, b)
        x += width
    top_zone = max(range(5), key=lambda i: seconds[i])
    name = f'ZONE {top_zone + 1}'
    pct = f' {round(seconds[top_zone] / total * 100)}%'
    total_w = get_text_width(big_font, name) + get_text_width(big_font, pct)
    tx = max((w - total_w) // 2, 2)
    graphics.DrawText(matrix, big_font, tx, text_y, graphics.Color(*HR_ZONE_COLORS[top_zone]), name)
    graphics.DrawText(matrix, big_font, tx + get_text_width(big_font, name), text_y, _WHITE, pct)


# Peloton's muscle-group intensity buckets: 1 some (yellow), 2 more (orange), 3 most (red).
MUSCLE_BUCKET_COLORS = {1: (200, 150, 0), 2: (255, 110, 0), 3: (255, 30, 0)}


def _muscle_row_text(matrix, font, baseline: int, group: dict) -> None:
    """Muscle name on the left, its percent on the right, in white."""
    w = matrix.width
    pct = f"{group['percent']}%"
    pct_w = _text_width(font, pct)
    name = _truncate(font, group['name'].upper(), w - 4 - pct_w - 3)
    _draw_text(matrix, font, 2, baseline, _WHITE, name)
    _draw_text(matrix, font, w - 2 - pct_w, baseline, _WHITE, pct)


def _draw_muscles(matrix, muscles: List[dict], font, label_y: int) -> None:
    """64 rows: a label, then each muscle's name and percent over a 2-px bar
    in its bucket colour, scaled to the top muscle."""
    w = matrix.width
    label = 'MUSCLES WORKED'
    _draw_text(matrix, font, max((w - _text_width(font, label)) // 2, 2), label_y,
               graphics.Color(*_LABEL_GREY), label)
    peak = muscles[0]['percent']
    for i, group in enumerate(muscles):
        baseline = label_y + 10 + i * 9
        _muscle_row_text(matrix, font, baseline, group)
        r, g, b = MUSCLE_BUCKET_COLORS.get(group['bucket'], MUSCLE_BUCKET_COLORS[1])
        for x in range(2, 2 + max(1, round((w - 4) * group['percent'] / peak))):
            matrix.SetPixel(x, baseline + 1, r, g, b)
            matrix.SetPixel(x, baseline + 2, r, g, b)


def _draw_muscle_rows(matrix, muscles: List[dict], font, top: int) -> None:
    """32 rows: no room for a label, so each muscle is a 5-px half-brightness
    bar in its bucket colour, scaled to the top muscle, with the text over it."""
    w = matrix.width
    peak = muscles[0]['percent']
    for i, group in enumerate(muscles):
        y0 = top + i * 6
        r, g, b = MUSCLE_BUCKET_COLORS.get(group['bucket'], MUSCLE_BUCKET_COLORS[1])
        for x in range(1, 1 + max(1, round((w - 2) * group['percent'] / peak))):
            for y in range(y0, y0 + 5):
                matrix.SetPixel(x, y, r // 2, g // 2, b // 2)
        _muscle_row_text(matrix, font, y0 + 5, group)


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


_INSIGHT_GOLD = (255, 200, 0)
# Insight sentences and reasons: full white is glaring on the panel next to the coloured figures.
_INSIGHT_TEXT = (200, 205, 215)
_INSIGHT_DIM = (70, 80, 95)
# The 'usual' bar: navy, so today's bar is the one that stands out (the number and label stay grey).
_USUAL_BAR = (20, 50, 140)
TYPICAL_LABEL = 'TYPICAL'  # the 64x64 bars frame's label for the usual figure (the median of similar workouts)
# The workout-compare lightbulb, 5x7: '#' gold, 'g' the grey base.
_BULB_ROWS = ('.###.', '#####', '#####', '#####', '.###.', '.ggg.', '..g..')


def _rect(matrix, x0: int, y0: int, x1: int, y1: int, rgb) -> None:
    for y in range(max(y0, 0), min(y1, matrix.height - 1) + 1):
        for x in range(max(x0, 0), min(x1, matrix.width - 1) + 1):
            matrix.SetPixel(x, y, *rgb)


def _draw_bulb(matrix, x: int, y: int) -> None:
    for dy, row in enumerate(_BULB_ROWS):
        for dx, cell in enumerate(row):
            if cell != '.':
                matrix.SetPixel(x + dx, y + dy, *(_INSIGHT_GOLD if cell == '#' else _LABEL_GREY))


def _write(matrix, font, x: int, y: int, rgb, text: str) -> int:
    graphics.DrawText(matrix, font, x, y, graphics.Color(*rgb), text)
    return get_text_width(font, text)


# The colon's dot sits mid-cell, which leaves 6 blank columns before the next word against 5 between
# other words: the word after a colon moves this many px closer (Joel, 2026-11-11).
COLON_GAP_TRIM = 3


def _words_width(font, text: str) -> int:
    """`text`'s drawn width with the gap after each colon tightened."""
    return get_text_width(font, text) - COLON_GAP_TRIM * text.count(': ')


def _draw_words(matrix, font, x: int, y: int, text: str, colour_of) -> None:
    """`text` word by word from x, each word in `colour_of(word)`, the gap after a colon tightened."""
    space = get_text_width(font, ' ')
    for word in text.split(' '):
        x += _write(matrix, font, x, y, colour_of(word), word) + space
        if word.endswith(':'):
            x -= COLON_GAP_TRIM


def _centred(matrix, font, y: int, rgb, text: str, left: int = 0, right: Optional[int] = None) -> None:
    """`text` centred between columns `left` and `right` (the panel's width by default)."""
    room = (matrix.width if right is None else right) - left
    _draw_words(matrix, font, left + max((room - _words_width(font, text)) // 2, 0), y, text, lambda _: rgb)


def _rich_line(matrix, font, y: int, line: str, numbers) -> None:
    """A centred sentence line whose words with a digit take `numbers` (the insight's colour), the rest white."""
    x = max((matrix.width - _words_width(font, line)) // 2, 0)
    _draw_words(matrix, font, x, y, line,
                lambda word: numbers if any(ch.isdigit() for ch in word) else _INSIGHT_TEXT)


def _reason_line(matrix, font, y: int, text: str, phase: float, hold: float) -> None:
    """The bars frame's last line, white and centred; a movement name wider than the room scrolls as on the
    name page (hold, glide, hold), the margins blanked so the text slides under them."""
    w = matrix.width
    overflow = get_text_width(font, text) - (w - 2 * SCROLL_MARGIN)
    if overflow <= 0:
        _centred(matrix, font, y, _INSIGHT_TEXT, text)
        return
    _write(matrix, font, SCROLL_MARGIN - UsernameScreen.scroll_offset(overflow, phase, hold), y,
           _INSIGHT_TEXT, text)
    height = getattr(font, 'height', 8)
    for row in range(y - height, min(y + 3, matrix.height)):
        for x in list(range(0, SCROLL_MARGIN)) + list(range(w - SCROLL_MARGIN, w)):
            matrix.SetPixel(x, row, 0, 0, 0)


def _disc_rgb(discipline: str):
    colour = _disc_color(discipline)
    return colour.red, colour.green, colour.blue


def _insight_header(matrix, discipline: str, index: int, count: int) -> None:
    """64 rows: the bulb, INSIGHT in gold, 1/2 on the right when there are two, a discipline-colour rule."""
    stats = loaded_fonts['stats']
    _draw_bulb(matrix, 3, 2)
    _write(matrix, loaded_fonts.get('titles') or stats, 11, 9, _INSIGHT_GOLD, 'INSIGHT')
    if count > 1:
        label = f'{index + 1}/{count}'
        _write(matrix, stats, 62 - get_text_width(stats, label), 9, _LABEL_GREY, label)
    _rect(matrix, 2, 12, 61, 12, _disc_rgb(discipline))


def _draw_insight_card(matrix, view: dict, discipline: str, index: int, count: int) -> None:
    """64x64: the sentence, numbers in the insight's colour (its headline's), and what it was compared with."""
    stats = loaded_fonts['stats']
    _insight_header(matrix, discipline, index, count)
    lines = view['lines64']
    top = 21 + 7 * (5 - len(lines)) // 2
    for k, line in enumerate(lines):
        _rich_line(matrix, stats, top + 7 * k, line, tuple(view['colour']))
    _centred(matrix, stats, 61, _LABEL_GREY, view['footer'])


def _bars_tall(matrix, figure: dict, colour) -> None:
    """64x64 figure: TODAY / TYPICAL bars on baselines 32 and 45, a share bar on 32, or blocks from row 34."""
    stats = loaded_fonts['stats']
    kind = figure['kind']
    if kind == 'bars':
        top = max(figure['today'], figure['usual']) or 1
        for y, label, value, text, rgb, bar in ((32, 'TODAY', figure['today'], figure['today_text'], colour, colour),
                                                (45, TYPICAL_LABEL, figure['usual'], figure['usual_text'], _LABEL_GREY,
                                                 _USUAL_BAR)):
            unit = figure.get('unit', '')
            # Weights read as one word, 40LB, as in the sentence; watts and mph keep their space.
            text = f'{text}{unit}' if unit == 'LB' else f'{text} {unit}'.strip()
            _write(matrix, stats, 2, y, _LABEL_GREY, label)
            _write(matrix, stats, 62 - get_text_width(stats, text), y, rgb, text)
            _rect(matrix, 2, y + 2, 2 + round(59 * min(value, top) / top), y + 5, bar)
    elif kind == 'share':
        pct = figure['pct']
        text = f'{pct:.0f}%'
        _write(matrix, stats, 2, 32, _LABEL_GREY, 'TIME UNDER')
        _write(matrix, stats, 62 - get_text_width(stats, text), 32, colour, text)
        _rect(matrix, 2, 35, 61, 41, _INSIGHT_DIM)
        if pct > 0:
            _rect(matrix, 2, 35, 2 + round(59 * pct / 100), 41, colour)
        _centred(matrix, stats, 49, _LABEL_GREY, 'THE CALLOUT')
    else:
        size, gap = _block_size(figure['total'], 60, ((7, 3), (5, 2), (3, 1), (2, 1), (1, 1)))
        span = figure['total'] * (size + gap) - gap
        x0 = (matrix.width - span) // 2
        for i in range(figure['total']):
            x = x0 + i * (size + gap)
            _rect(matrix, x, 34, x + size - 1, 34 + size - 1, colour if i < figure['lit'] else _INSIGHT_DIM)
        if figure.get('label'):
            _centred(matrix, stats, 34 + size + 9, _LABEL_GREY, f"{figure['lit']} {figure['label']}")


def _block_size(total: int, room: int, sizes):
    """The largest (block, gap) that fits `total` blocks in `room` px, else the smallest."""
    return next(((size, gap) for size, gap in sizes if total * (size + gap) - gap <= room), sizes[-1])


def _bars_short(matrix, figure: dict, colour) -> None:
    """64x32 figure: bars on rows 9-13 and 17-21 with the numbers right-aligned, a share bar on rows 11-18,
    or 5 px blocks from x 4."""
    stats = loaded_fonts['stats']
    kind = figure['kind']
    if kind == 'bars':
        top = max(figure['today'], figure['usual']) or 1
        for y, value, text, rgb, bar in ((13, figure['today'], figure['today_text'], colour, colour),
                                         (21, figure['usual'], figure['usual_text'], _LABEL_GREY, _USUAL_BAR)):
            _rect(matrix, 1, y - 4, 1 + round(40 * min(value, top) / top), y, bar)
            _write(matrix, stats, 63 - get_text_width(stats, text), y, rgb, text)
    elif kind == 'share':
        pct = figure['pct']
        text = f'{pct:.0f}%'
        _rect(matrix, 1, 11, 41, 18, _INSIGHT_DIM)
        if pct > 0:
            _rect(matrix, 1, 11, 1 + round(40 * pct / 100), 18, colour)
        _write(matrix, stats, 63 - get_text_width(stats, text), 17, colour, text)
    else:
        size, gap = _block_size(figure['total'], 59, ((5, 2), (3, 1), (2, 1), (1, 1)))
        for i in range(figure['total']):
            x = 4 + i * (size + gap)
            _rect(matrix, x, 11, x + size - 1, 11 + size - 1, colour if i < figure['lit'] else _INSIGHT_DIM)


def _draw_insight_bars(matrix, view: dict, discipline: str, index: int, count: int,
                       phase: float, hold: float) -> None:
    """The headline in its colour, the figure, and the reason line underneath."""
    stats = loaded_fonts['stats']
    colour = tuple(view['colour'])
    headline = view['headline']
    if matrix.height >= 64:
        _insight_header(matrix, discipline, index, count)
        titles = loaded_fonts.get('titles') or stats
        _centred(matrix, titles if _words_width(titles, headline) <= 62 else stats, 22, colour, headline)
        _bars_tall(matrix, view['figure'], colour)
        reason_y = 61
    else:
        _draw_bulb(matrix, 1, 0)
        # Columns 9-63 hold 14 characters: a longer headline (STRONG BOOTCAMP) keeps its first word.
        if _words_width(stats, headline) > 56:
            headline = headline.split()[0]
        _centred(matrix, stats, 6, colour, headline, left=9)
        _bars_short(matrix, view['figure'], colour)
        reason_y = 30
    if view.get('reason'):
        _reason_line(matrix, stats, reason_y, view['reason'], phase, hold)


def _draw_insight_words(matrix, view: dict, discipline: str, page: int) -> None:
    """64x32: the sentence, three lines a page, under the bulb and INSIGHT."""
    stats = loaded_fonts['stats']
    pages = view['pages32']
    page = min(max(page, 0), len(pages) - 1)
    _draw_bulb(matrix, 1, 0)
    _write(matrix, stats, 9, 6, _INSIGHT_GOLD, 'INSIGHT')
    if len(pages) > 1:
        label = f'{page + 1}/{len(pages)}'
        _write(matrix, stats, 63 - get_text_width(stats, label), 6, _LABEL_GREY, label)
    _rect(matrix, 0, 8, 63, 8, _disc_rgb(discipline))
    for k, line in enumerate(pages[page]):
        _rich_line(matrix, stats, 16 + 7 * k, line, tuple(view['colour']))


def _draw_insight_frame(matrix, summary: dict, discipline: str, detail: dict, phase: float, hold: float) -> bool:
    """One workout-compare frame, in place of the discipline title and heart-rate row."""
    views = insight_views(summary)
    index = detail.get('index', 0)
    if not isinstance(index, int) or not 0 <= index < len(views):
        return False
    view = views[index]
    if detail['kind'] == 'insight_card':
        _draw_insight_card(matrix, view, discipline, index, len(views))
    elif detail['kind'] == 'insight_bars':
        _draw_insight_bars(matrix, view, discipline, index, len(views), phase, hold)
    else:
        _draw_insight_words(matrix, view, discipline, detail.get('page', 0))
    return True


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

    The second line sits on the bottom rows, so a workout title narrows it to clear the
    login padlock (bottom right) and stale-data clock (bottom left) when shown. An instructor
    name passes clear_icons=False: it is drawn the same every time and an icon may cover its
    ends, which is the point of the icon.
    """
    w = matrix.width
    for i, line in enumerate(lines[:2]):
        if i == 1 and clear_icons:
            left = 9 if summary.get('data_stale') else 2
            right = 9 if summary.get('login_required') else 2
            line = _truncate(font, line, w - 2 * max(left, right))
        tx = max((w - _text_width(font, line)) // 2, 2)
        _draw_text(matrix, font, tx, top_y + i * 7, _WHITE, line)


# Default seconds each intro/stat holds for; overridable via the
# `last_workout_detail_interval` display config key.
LAST_WORKOUT_DETAIL_INTERVAL_SECONDS = 4.0
# The graph, zone-bar and muscle frames hold this much longer than a stat:
# there's more to read than one number.
GRAPH_FRAME_EXTRA_SECONDS = 1.0


def detail_hold_seconds(detail: dict, interval: float) -> float:
    """Seconds one rotating detail stays up."""
    if interval > 0 and detail.get('kind') in ('graph', 'zones', 'muscles') + INSIGHT_KINDS:
        return interval + GRAPH_FRAME_EXTRA_SECONDS
    return interval


def stats_phase_seconds(details: List[dict], interval: float) -> float:
    """Seconds for one pass through every rotating detail."""
    return sum(detail_hold_seconds(d, interval) for d in details)


def detail_at(details: List[dict], interval: float, stats_elapsed: float):
    """(index, seconds into it) of the detail showing stats_elapsed seconds
    into the stats phase, wrapping after the last one."""
    remaining = max(0.0, stats_elapsed) % stats_phase_seconds(details, interval)
    for index, detail in enumerate(details):
        hold = detail_hold_seconds(detail, interval)
        if remaining < hold:
            return index, remaining
        remaining -= hold
    return len(details) - 1, remaining  # Float rounding at the very end of a pass.


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

    def _insight_frame(self, matrix, summary: dict, discipline: str) -> bool:
        """Draw the stats phase's current detail when it is a workout-compare frame; False otherwise.

        These frames replace the discipline title and the heart-rate row, so they draw before either."""
        details = rotating_details(summary, matrix.height)
        if not any(d.get('kind') in INSIGHT_KINDS for d in details):
            return False
        interval = self.detail_interval or LAST_WORKOUT_DETAIL_INTERVAL_SECONDS
        index, phase = detail_at(details, interval, self.elapsed - self.detail_interval)
        detail = details[index]
        if detail.get('kind') not in INSIGHT_KINDS:
            return False
        return _draw_insight_frame(matrix, summary, discipline, detail, phase, detail_hold_seconds(detail, interval))

    def _render_short(self, matrix, summary: dict, discipline: str, title_font, text_font, stat_font) -> bool:
        """64x32 version of the two-phase layout.

        Same order as 64x64 with the room redistributed:
          intro: discipline / duration (+ gold PR) / title on up to two lines
          stats: discipline / label / one large value / ♥ HR + calories bar
        The instructor leads the stat rotation instead of sitting in the intro.
        The HR/calories bar shows in the stats phase and in the intro under a one-line
        title; a two-line title leaves no rows for it.
        """
        w = matrix.width
        bottom_y = matrix.height - 1
        value_big = loaded_fonts.get("countdown") or title_font
        grey = graphics.Color(145, 165, 190)

        if self.elapsed >= self.detail_interval and self._insight_frame(matrix, summary, discipline):
            return True

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
            title = title_without_length(summary.get("title"))
            title_lines = _wrap_two_lines(text_font, title, w - 4)
            _draw_short_lines(matrix, text_font, title_lines, 22, summary)
            if len(title_lines) < 2:
                # A one-line title leaves rows 24-31 free for the bar. A two-line one ends on
                # row 29, so the bar waits for the stat frames that follow (an attempt to close
                # the rows up by one each still overlapped the title's descenders).
                _draw_hr_calories(matrix, summary, stat_font, bottom_y)
            return True

        details = rotating_details(summary, matrix.height)
        if details:
            interval = self.detail_interval or LAST_WORKOUT_DETAIL_INTERVAL_SECONDS
            index, phase_seconds = detail_at(details, interval, self.elapsed - self.detail_interval)
            detail = details[index]
            # The graph and zone slides use the bar's rows, so they go without it.
            if detail.get('kind') == 'graph':
                _draw_graph(matrix, summary, stat_font, 14, 16, matrix.height - 1)
                return True
            if detail.get('kind') == 'zones':
                _draw_zones(matrix, summary['hr_zone_seconds'], stat_font, text_font,
                            14, 17, 22, 30)
                return True
            if detail.get('kind') == 'muscles':
                # Three bars fill the space under the discipline; the bar stays.
                _draw_muscle_rows(matrix, summary['muscles'], text_font, 8)
                _draw_hr_calories(matrix, summary, stat_font, bottom_y)
                return True
            # Rise 2px rather than 3 so the value never brushes the bottom bar.
            offset = max(0, round(2 * (1 - min(1, phase_seconds / 0.3))))
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
                                  22 + offset, summary, clear_icons=False)
                return True
            else:
                value_y = 24 if value_font is value_big else 23
                if ',' in value and value_font is value_big:
                    # 6x9's comma hangs 2 rows below the baseline: lift the value 1 row so it
                    # leaves the blank row above the HR bar.
                    value_y -= 1
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
        if matrix.height < 64:
            return self._render_short(matrix, summary, discipline, title_font, text_font, stat_font)

        _BOTTOM_Y = 61
        _STAT_STEP = 6
        last_row_y = _BOTTOM_Y - _STAT_STEP  # Leave room for the HR/cal row below.

        all_details = _stat_details(summary)
        stat_details = rotating_details(summary, matrix.height)
        instructor_detail = next((d for d in all_details if d['label'] == 'instructor'), None)
        in_intro = self.elapsed < self.detail_interval
        if not in_intro and self._insight_frame(matrix, summary, discipline):
            return True

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
            title_stripped = title_without_length(summary.get("title"))
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
            index, phase_seconds = detail_at(stat_details, interval, self.elapsed - self.detail_interval)
            detail = stat_details[index]
            # Each new detail rises into place during its first 0.3 seconds.
            offset = max(0, round(3 * (1 - min(1, phase_seconds / 0.3))))
            available_top = block_y + _STAT_STEP
            mid_y = (available_top + last_row_y) // 2
            label_y = mid_y - 8
            if detail.get('kind') == 'graph':
                _draw_graph(matrix, summary, stat_font, label_y, label_y + 4, last_row_y - 2)
            elif detail.get('kind') == 'zones':
                _draw_zones(matrix, summary['hr_zone_seconds'], stat_font, titles_font or text_font,
                            label_y, label_y + 5, label_y + 13, label_y + 24)
            elif detail.get('kind') == 'muscles':
                # Starts higher than the other slides: three rows need the room.
                _draw_muscles(matrix, summary['muscles'], text_font, block_y + 8)
            else:
                value_font = (title_font if get_text_width(title_font, detail['value'].upper()) <= w - 4
                              else text_font)
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
