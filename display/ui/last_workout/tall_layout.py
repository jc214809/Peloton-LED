"""The 64x64 layout of the page: discipline, the intro (duration, title, instructor) or one stat at a time."""

from display.display import get_text_width
from driver import graphics

from .charts import _draw_form_graph, _draw_form_meter, _draw_graph, _draw_muscles, _draw_top_lift, _draw_zones
from .colors import _BLUE, _WHITE, _disc_color
from .fonts import PageFonts
from .insight_frames import draw_insight_slide
from .rotation import LAST_WORKOUT_DETAIL_INTERVAL_SECONDS, detail_at, rotating_details
from .sprites import _TROPHY_H, _TROPHY_W, _draw_trophy
from .stat_rows import _draw_hr_calories
from .stats import _stat_details, _value_color, page_heading, running_form
from .text import _draw_text, _text_width, _truncate, _wrap_two_lines, title_without_length

_BOTTOM_Y = 61
_STAT_STEP = 6
_LAST_ROW_Y = _BOTTOM_Y - _STAT_STEP  # Leave room for the HR/cal row below.


def _draw_discipline(matrix, discipline: str, fonts: PageFonts, heading: str | None = None) -> tuple[int, int]:
    """Line 1: the discipline (or `heading` in its colour), on screen for both intro and stats.
    Returns (block_y, line count)."""
    w = matrix.width
    disc_text = (heading or discipline).upper()
    disc_font = fonts.title
    # Bike Bootcamp is clearer as two 5x8 lines than one tiny 4x6 line.
    # Starting the two-line header higher recovers the added vertical
    # space and keeps the title plus all three cycling stat rows legible.
    if discipline.lower() == 'bike bootcamp' and fonts.titles:
        disc_font = fonts.titles
    elif get_text_width(disc_font, disc_text) > w - 2 and fonts.text and (get_text_width(fonts.text, disc_text) <= w - 2):
        disc_font = fonts.text
    disc_lines = _wrap_two_lines(disc_font, disc_text, w - 2)[:2] or ['']
    disc_font_h = getattr(disc_font, 'height', 9)
    disc_y = 8 if len(disc_lines) > 1 else 12
    for i, line in enumerate(disc_lines):
        dx = max((w - get_text_width(disc_font, line)) // 2, 1)
        graphics.DrawText(matrix, disc_font, dx, disc_y + i * disc_font_h, _disc_color(discipline), line)
    return disc_y + (len(disc_lines) - 1) * disc_font_h, len(disc_lines)


def _draw_duration(matrix, summary: dict, text_font, dur_y: int) -> None:
    """Line 2: the duration, centred."""
    w = matrix.width
    dur_min = summary.get('duration_min')
    if isinstance(dur_min, (int, float)):
        dur_val = str(int(dur_min))
        dur_label = 'min'
        dur_val_w = _text_width(text_font, dur_val)
        dur_label_w = _text_width(text_font, dur_label)
        dur_total_w = dur_val_w + 1 + dur_label_w
        dur_x = max((w - dur_total_w) // 2, 2)
        _draw_text(matrix, text_font, dur_x, dur_y, _BLUE, dur_val)
        _draw_text(matrix, text_font, dur_x + dur_val_w + 1, dur_y, _BLUE, dur_label)


def _draw_title(matrix, summary: dict, text_font, dur_y: int) -> list[str]:
    """Lines 3-4: the title below the duration with a visible gap. Returns the lines drawn."""
    w = matrix.width
    title_stripped = title_without_length(summary.get('title'))
    # Edge to edge, as on 32 rows (Joel, 2026-11-16).
    title_lines = _wrap_two_lines(text_font, title_stripped, w)
    for i, line in enumerate(title_lines[:2]):
        tx = max((w - _text_width(text_font, line)) // 2, 0)
        _draw_text(matrix, text_font, tx, dur_y + 7 + i * 7, _WHITE, line)
    return title_lines[:2]


def _draw_instructor(matrix, instructor_detail: dict, header_bottom: int, title_line_count: int, fonts: PageFonts, elapsed: float) -> bool:
    """The instructor, underneath the title. Returns True when the heart-rate row has to go (intro_without_hr)."""
    w = matrix.width
    intro_without_hr = False
    offset = max(0, round(3 * (1 - min(1, elapsed / 0.3))))
    # Two-line titles need extra clearance below their second
    # line before the instructor block starts.
    two_line_extra = 2 if title_line_count > 1 else 0
    available_top = header_bottom + _STAT_STEP
    available_bottom = _LAST_ROW_Y
    min_top = header_bottom + 5
    value_font = fonts.text
    value_lines = _wrap_two_lines(value_font, instructor_detail['value'].upper(), w - 4)[:2]
    mid_y = available_top + (available_bottom - available_top) // 2 - 3
    show_label = True
    block_lines = 1 + len(value_lines)
    y = max(mid_y - 3 * (block_lines - 1), min_top) + two_line_extra
    if len(value_lines) > 1:
        # Top to bottom: discipline, duration, title, the whole instructor block (caption
        # 2 blank rows under the title), then the heart-rate row, which is the first to go:
        # when the name's last line doesn't clear it (rows 56 on) by 2, the intro drops the
        # row, as 64x32 does under a two-line title; the stat frames keep it (Joel, 2026-11-17).
        y = max(y, header_bottom + 8)
        intro_without_hr = y + 8 + 7 > _BOTTOM_Y - 8
    if show_label:
        label_text = _truncate(fonts.stat, 'INSTRUCTOR', w - 4)
        lx = max((w - _text_width(fonts.stat, label_text)) // 2, 2)
        _draw_text(matrix, fonts.stat, lx, y + offset, graphics.Color(145, 165, 190), label_text)
        y += 8
    for line in value_lines:
        vx = max((w - _text_width(value_font, line)) // 2, 2)
        _draw_text(matrix, value_font, vx, y + offset, _WHITE, line)
        y += 7
    return intro_without_hr


def _draw_intro(matrix, summary: dict, instructor_detail, block_y: int, disc_line_count: int, fonts: PageFonts, elapsed: float) -> bool:
    """Duration, title and the instructor under them. Returns True when the heart-rate row has to go."""
    # Tighten the gap when the discipline wraps to 2 lines, to leave room for the title below.
    dur_y = block_y + (7 if disc_line_count > 1 else 10)
    _draw_duration(matrix, summary, fonts.text, dur_y)
    title_lines = _draw_title(matrix, summary, fonts.text, dur_y)
    header_bottom = dur_y + 7 + max(len(title_lines) - 1, 0) * 7
    if instructor_detail:
        return _draw_instructor(matrix, instructor_detail, header_bottom, len(title_lines), fonts, elapsed)
    return False


def _draw_stat_value(matrix, summary: dict, detail: dict, label_y: int, offset: int, fonts: PageFonts) -> None:
    """A stat's label and large value, with the PR trophy after a total output PR."""
    w = matrix.width
    value_font = fonts.title if get_text_width(fonts.title, detail['value'].upper()) <= w - 4 else fonts.text
    value_y = label_y + 15
    label_text = _truncate(fonts.stat, detail['label'].upper(), w - 4)
    lx = max((w - _text_width(fonts.stat, label_text)) // 2, 2)
    _draw_text(matrix, fonts.stat, lx, label_y + offset, graphics.Color(145, 165, 190), label_text)

    value_text = _truncate(value_font, detail['value'].upper(), w - 4)
    vx = max((w - get_text_width(value_font, value_text)) // 2, 2)
    star = bool(summary.get('is_output_pr')) and detail['label'] == 'total output'
    graphics.DrawText(matrix, value_font, vx, value_y + offset, _value_color(detail), value_text)
    if star:
        star_x = vx + get_text_width(value_font, value_text) + 2
        _draw_trophy(matrix, min(star_x, w - _TROPHY_W), value_y + offset - _TROPHY_H)


def _draw_running_form(matrix, summary: dict, block_y: int, fonts: PageFonts) -> None:
    """The efficiency graph between the discipline and the heart-rate row, or the 64x32 meter when the
    workout has no series to graph."""
    form = running_form(summary)
    label_y = block_y + 12
    if form['series']:
        _draw_form_graph(matrix, form, fonts.stat, label_y, label_y + 3, _LAST_ROW_Y - 9)
    else:
        _draw_form_meter(matrix, form, fonts.stat, fonts.title, label_y, label_y + 14)


def _draw_stats(
    matrix, summary: dict, stat_details: list[dict], block_y: int, fonts: PageFonts, elapsed: float, detail_interval: float
) -> None:
    """Stats phase: the discipline title stays; everything below it (duration/workout-title/instructor)
    is replaced by one rotating stat at a time, using the space freed up below the title."""
    interval = detail_interval or LAST_WORKOUT_DETAIL_INTERVAL_SECONDS
    index, phase_seconds = detail_at(stat_details, interval, elapsed - detail_interval)
    detail = stat_details[index]
    # Each new detail rises into place during its first 0.3 seconds.
    offset = max(0, round(3 * (1 - min(1, phase_seconds / 0.3))))
    available_top = block_y + _STAT_STEP
    mid_y = (available_top + _LAST_ROW_Y) // 2
    label_y = mid_y - 8
    kind = detail.get('kind')
    if kind == 'graph':
        _draw_graph(matrix, summary, fonts.stat, label_y, label_y + 4, _LAST_ROW_Y - 2)
    elif kind == 'zones':
        _draw_zones(
            matrix, summary['hr_zone_seconds'], fonts.stat, fonts.titles or fonts.text, label_y, label_y + 5, label_y + 13, label_y + 24
        )
    elif kind == 'running_form':
        _draw_running_form(matrix, summary, block_y, fonts)
    elif kind == 'muscles':
        # Starts higher than the other slides: three rows need the room.
        _draw_muscles(matrix, summary['muscles'], fonts.text, block_y + 8)
    elif kind == 'top_lift':
        _draw_top_lift(
            matrix, summary, fonts.stat, fonts.titles or fonts.text, fonts.text, (fonts.title, fonts.titles or fonts.text), block_y + 10
        )
    else:
        _draw_stat_value(matrix, summary, detail, label_y, offset, fonts)


def render_tall(matrix, summary: dict, discipline: str, fonts: PageFonts, elapsed: float, detail_interval: float) -> bool:
    """64x64 version of the two-phase layout: the discipline, then the intro or one stat, then the bar."""
    w = matrix.width
    all_details = _stat_details(summary)
    stat_details = rotating_details(summary, matrix.height)
    instructor_detail = next((d for d in all_details if d['label'] == 'instructor'), None)
    in_intro = elapsed < detail_interval
    intro_without_hr = False  # set below when the instructor block needs the heart-rate row's rows
    if not in_intro and draw_insight_slide(matrix, summary, discipline, elapsed, detail_interval):
        return True

    block_y, disc_line_count = _draw_discipline(matrix, discipline, fonts, page_heading(summary, discipline))
    if in_intro:
        intro_without_hr = _draw_intro(matrix, summary, instructor_detail, block_y, disc_line_count, fonts, elapsed)
    elif stat_details:
        _draw_stats(matrix, summary, stat_details, block_y, fonts, elapsed, detail_interval)

    if not intro_without_hr:
        _draw_hr_calories(matrix, summary, fonts.stat, _BOTTOM_Y)

    # ── PR trophy, where the "PR" letters used to sit ─────────────────
    # Intro only: in the stats phase it would touch wide labels, and the
    # output value carries its own trophy there.
    if summary.get('is_pr') and in_intro:
        _draw_trophy(matrix, w - _TROPHY_W - 2, 16)

    return True
