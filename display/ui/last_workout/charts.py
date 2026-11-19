"""The chart slides: workout graph, heart-rate zone bar, muscle groups and the top lift."""
from typing import List

from driver import graphics
from display.display import get_text_width
from .colors import _INSIGHT_GOLD, _LABEL_GREY, _PEAK_WHITE, _WHITE, HR_ZONE_COLORS, _disc_color
from .stats import top_lift_text, strength_tracker
from .text import _centred, _draw_text, _text_width, _truncate, _wrap_two_lines


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


def _draw_zones(matrix, seconds: List[float], font, big_font, label_y: int,  # noqa: PLR0913
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


TOP_LIFT_LABEL = 'TOP LIFT'


def _draw_top_lift(matrix, summary: dict, label_font, name_font, small_name_font, value_fonts, label_y: int) -> None:
    """The movement Peloton tagged as the class's most volume: a label, its name on up to two lines
    (in the smaller font when the bigger one would cut it short), and reps x heaviest weight in gold.

    64 rows: under the discipline title, above the heart-rate row. 32 rows: the whole panel, like the
    graph slide."""
    tracker = strength_tracker(summary)
    top = tracker['top']
    w = matrix.width
    name = top['name'].upper()
    lines = _wrap_two_lines(name_font, name, w - 4)
    if ' '.join(lines) != name:
        name_font = small_name_font
        lines = _wrap_two_lines(name_font, name, w - 4)
    _centred(matrix, label_font, label_y, _LABEL_GREY, TOP_LIFT_LABEL)
    tall = matrix.height >= 64
    step = getattr(name_font, 'height', 6) + 1
    y = label_y + (10 if tall else 7)
    for line in lines:
        _centred(matrix, name_font, y, _PEAK_WHITE, line)
        y += step
    value = top_lift_text(top, tracker['unit'])
    font = next((f for f in value_fonts if get_text_width(f, value) <= w - 4), value_fonts[-1])
    if tall:
        value_y = label_y + (31 if len(lines) > 1 else 22)
    else:
        value_y = matrix.height - 2 if len(lines) > 1 else label_y + 17
    graphics.DrawText(matrix, font, max((w - get_text_width(font, value)) // 2, 2), value_y,
                      graphics.Color(*_INSIGHT_GOLD), value)
