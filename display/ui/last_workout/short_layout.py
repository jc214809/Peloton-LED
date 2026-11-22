"""The 64x32 layout of the page: discipline, then the intro or one stat frame at a time."""

from display.display import get_text_width, loaded_fonts
from driver import graphics

from .charts import _draw_form_meter, _draw_graph, _draw_muscle_rows, _draw_top_lift, _draw_zones
from .colors import _BLUE, _disc_color
from .fonts import PageFonts
from .insight_frames import draw_insight_slide
from .rotation import LAST_WORKOUT_DETAIL_INTERVAL_SECONDS, detail_at, rotating_details
from .sprites import _TROPHY_H, _TROPHY_W, _draw_trophy
from .stat_rows import _draw_hr_calories, _draw_short_lines
from .stats import _value_color, running_form
from .text import _draw_text, _text_width, _truncate, _wrap_two_lines, title_without_length


def _whole_panel_frame(matrix, summary: dict, discipline: str, fonts: PageFonts, elapsed: float, detail_interval: float) -> bool:
    """The stats phase's frames that take the whole panel, title and bar included: a workout-compare
    frame or the top lift. False when the current detail is neither."""
    if elapsed < detail_interval:
        return False
    if draw_insight_slide(matrix, summary, discipline, elapsed, detail_interval):
        return True
    details = rotating_details(summary, matrix.height)
    if details:
        index, _ = detail_at(details, detail_interval or LAST_WORKOUT_DETAIL_INTERVAL_SECONDS, elapsed - detail_interval)
        if details[index].get('kind') == 'top_lift':
            # The whole panel, like the graph slide: no room for the title or the bar.
            _draw_top_lift(matrix, summary, fonts.text, fonts.text, fonts.text, (fonts.title, fonts.text), 6)
            return True
    return False


def _draw_discipline(matrix, discipline: str, fonts: PageFonts) -> None:
    """Discipline: fixed at the top for both phases."""
    w = matrix.width
    disc_text = discipline.upper()
    disc_font = fonts.title
    if get_text_width(disc_font, disc_text) > w - 2:
        disc_font = fonts.text
    disc_text = _truncate(disc_font, disc_text, w - 2)
    disc_y = 7 if disc_font is fonts.title else 6
    dx = max((w - get_text_width(disc_font, disc_text)) // 2, 1)
    graphics.DrawText(matrix, disc_font, dx, disc_y, _disc_color(discipline), disc_text)


def _draw_intro(matrix, summary: dict, fonts: PageFonts) -> None:
    """Duration, the gold PR trophy and the title on up to two lines, with the bar under a one-line title."""
    w = matrix.width
    dur_min = summary.get('duration_min')
    if isinstance(dur_min, (int, float)):
        dur_text = f'{int(dur_min)} MIN'
        x = max((w - _text_width(fonts.text, dur_text)) // 2, 2)
        _draw_text(matrix, fonts.text, x, 15, _BLUE, dur_text)
    if summary.get('is_pr'):
        _draw_trophy(matrix, w - _TROPHY_W - 2, 9)
    title = title_without_length(summary.get('title'))
    # The full width, edge to edge: a 2 px margin cut titles like "Arms & Shoulders Strength"
    # mid-word (Joel, 2026-11-16).
    title_lines = _wrap_two_lines(fonts.text, title, w)
    _draw_short_lines(matrix, fonts.text, title_lines, 22, summary)
    if len(title_lines) < 2:
        # A one-line title leaves rows 24-31 free for the bar. A two-line one ends on
        # row 29, so the bar waits for the stat frames that follow (an attempt to close
        # the rows up by one each still overlapped the title's descenders).
        _draw_hr_calories(matrix, summary, fonts.stat, matrix.height - 1)


def _draw_stat_value(matrix, summary: dict, detail: dict, phase_seconds: float, fonts: PageFonts) -> bool:
    """A stat's label and large value. False when the value is a long name that takes the bar's rows."""
    w = matrix.width
    grey = graphics.Color(145, 165, 190)
    value_big = loaded_fonts.get('countdown') or fonts.title
    # Rise 2px rather than 3 so the value never brushes the bottom bar.
    offset = max(0, round(2 * (1 - min(1, phase_seconds / 0.3))))
    value = detail['value'].upper()
    value_font = next((f for f in (value_big, fonts.title, fonts.text) if get_text_width(f, value) <= w - 4), fonts.text)
    label = _truncate(fonts.stat, detail['label'].upper(), w - 4)
    lx = max((w - _text_width(fonts.stat, label)) // 2, 2)
    _draw_text(matrix, fonts.stat, lx, 15 + offset, grey, label)
    if value_font is fonts.text and get_text_width(fonts.text, value) > w - 4:
        # Long instructor names wrap into the bar's rows, so this one
        # detail goes without the HR/calories bar.
        _draw_short_lines(matrix, fonts.text, _wrap_two_lines(fonts.text, value, w - 4), 22 + offset, summary, clear_icons=False)
        return False
    value_y = 24 if value_font is value_big else 23
    if ',' in value and value_font is value_big:
        # 6x9's comma hangs 2 rows below the baseline: lift the value 1 row so it
        # leaves the blank row above the HR bar.
        value_y -= 1
    vx = max((w - get_text_width(value_font, value)) // 2, 2)
    graphics.DrawText(matrix, value_font, vx, value_y + offset, _value_color(detail), value)
    if summary.get('is_output_pr') and detail['label'] == 'total output':
        star_x = vx + get_text_width(value_font, value) + 2
        _draw_trophy(matrix, min(star_x, w - _TROPHY_W), value_y + offset - _TROPHY_H)
    return True


def _draw_stat_frame(matrix, summary: dict, detail: dict, phase_seconds: float, fonts: PageFonts) -> bool:
    """One rotating detail below the discipline. False when the frame goes without the HR/calories bar."""
    kind = detail.get('kind')
    # The graph and zone slides use the bar's rows, so they go without it.
    if kind == 'graph':
        _draw_graph(matrix, summary, fonts.stat, 14, 16, matrix.height - 1)
        return False
    if kind == 'zones':
        _draw_zones(matrix, summary['hr_zone_seconds'], fonts.stat, fonts.text, 14, 17, 22, 30)
        return False
    if kind == 'running_form':
        _draw_form_meter(matrix, running_form(summary), fonts.stat, fonts.title, 15, 24)
        return False
    if kind == 'muscles':
        # Three bars fill the space under the discipline; the bar stays.
        _draw_muscle_rows(matrix, summary['muscles'], fonts.text, 8)
        return True
    return _draw_stat_value(matrix, summary, detail, phase_seconds, fonts)


def render_short(matrix, summary: dict, discipline: str, fonts: PageFonts, elapsed: float, detail_interval: float) -> bool:
    """64x32 version of the two-phase layout.

    Same order as 64x64 with the room redistributed:
      intro: discipline / duration (+ gold PR) / title on up to two lines
      stats: discipline / label / one large value / ♥ HR + calories bar
    The instructor leads the stat rotation instead of sitting in the intro.
    The HR/calories bar shows in the stats phase and in the intro under a one-line
    title; a two-line title leaves no rows for it.
    """
    if _whole_panel_frame(matrix, summary, discipline, fonts, elapsed, detail_interval):
        return True
    _draw_discipline(matrix, discipline, fonts)
    if elapsed < detail_interval:
        _draw_intro(matrix, summary, fonts)
        return True

    details = rotating_details(summary, matrix.height)
    if details:
        interval = detail_interval or LAST_WORKOUT_DETAIL_INTERVAL_SECONDS
        index, phase_seconds = detail_at(details, interval, elapsed - detail_interval)
        if not _draw_stat_frame(matrix, summary, details[index], phase_seconds, fonts):
            return True
    _draw_hr_calories(matrix, summary, fonts.stat, matrix.height - 1)
    return True
