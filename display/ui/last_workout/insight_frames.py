"""The workout-compare frames: the 64x64 card and bars, the 64x32 bars and sentence pages."""
from typing import List

from display.display import get_text_width, loaded_fonts
from .colors import _INSIGHT_DIM, _INSIGHT_GOLD, _INSIGHT_TEXT, _LABEL_GREY, _USUAL_BAR, _disc_rgb
from .insight_data import ARROW_PART, INSIGHT_KINDS, TYPICAL_LABEL, _ARROW_ROWS, _parts_layout, insight_views
from .rotation import LAST_WORKOUT_DETAIL_INTERVAL_SECONDS, detail_at, detail_hold_seconds, rotating_details
from .sprites import _draw_bulb, _rect
from .text import _centred, _draw_words, _words_width, _write
from ..username import MARGIN as SCROLL_MARGIN, UsernameScreen


def _rich_line(matrix, font, y: int, line: str, numbers, highlight=()) -> None:
    """A centred sentence line whose words with a digit (or in `highlight`: FIRST) take `numbers` (the
    insight's colour), the rest white."""
    x = max((matrix.width - _words_width(font, line)) // 2, 0)
    _draw_words(matrix, font, x, y, line,
                lambda word: numbers if word in highlight or any(ch.isdigit() for ch in word) else _INSIGHT_TEXT)


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


def _parts_line(matrix, font, y: int, parts: List[str], colour) -> None:
    """The bars frame's bottom line drawn in parts from column 1, with an ARROW_PART between: the text before
    the arrow (the class rating) and the arrow in the insight's colour, the text after it soft white. The arrow
    sits on the text's rows (y-5 to y-1), centred between the inks (`_parts_layout`; Joel, 2026-11-12)."""
    places, _ = _parts_layout(parts, lambda text: get_text_width(font, text))
    seen_arrow = False
    for part, x in places:
        if part == ARROW_PART:
            for dy, row in enumerate(_ARROW_ROWS):
                for dx, cell in enumerate(row):
                    if cell == '#':
                        matrix.SetPixel(x + dx, y - 5 + dy, *colour)
            seen_arrow = True
        else:
            _write(matrix, font, x, y, _INSIGHT_TEXT if seen_arrow else colour, part)


def _insight_header(matrix, discipline: str, index: int, count: int) -> None:
    """64 rows: the bulb, INSIGHT in gold, 1/3 on the right when there are several, a discipline-colour rule."""
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
        _rich_line(matrix, stats, top + 7 * k, line, tuple(view['colour']), view.get('highlight', ()))
    _centred(matrix, stats, 61, _LABEL_GREY, view['footer'])


def _bars_top(figure: dict):
    """The value a full bar stands for: the figure's own `top` (a 0-10 rating scale), else the larger of the two."""
    return max(figure.get('top') or 0, figure['today'], figure['usual']) or 1


def _bars_tall(matrix, figure: dict, colour) -> None:
    """64x64 figure: TODAY / TYPICAL bars on baselines 32 and 45, a share bar on 32, or blocks from row 34."""
    stats = loaded_fonts['stats']
    kind = figure['kind']
    if kind == 'bars':
        top = _bars_top(figure)
        usual_label = figure.get('usual_label') or TYPICAL_LABEL
        for y, label, value, text, rgb, bar in ((32, 'TODAY', figure['today'], figure['today_text'], colour, colour),
                                                (45, usual_label, figure['usual'], figure['usual_text'], _LABEL_GREY,
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
        top = _bars_top(figure)
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
    if view.get('reason_parts'):
        _parts_line(matrix, stats, reason_y, view['reason_parts'], colour)
    elif view.get('reason'):
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
        _rich_line(matrix, stats, 16 + 7 * k, line, tuple(view['colour']), view.get('highlight', ()))


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


def draw_insight_slide(matrix, summary: dict, discipline: str, elapsed: float, detail_interval: float) -> bool:
    """Draw the stats phase's current detail when it is a workout-compare frame; False otherwise.

    These frames replace the discipline title and the heart-rate row, so they draw before either."""
    details = rotating_details(summary, matrix.height)
    if not any(d.get('kind') in INSIGHT_KINDS for d in details):
        return False
    interval = detail_interval or LAST_WORKOUT_DETAIL_INTERVAL_SECONDS
    index, phase = detail_at(details, interval, elapsed - detail_interval)
    detail = details[index]
    if detail.get('kind') not in INSIGHT_KINDS:
        return False
    return _draw_insight_frame(matrix, summary, discipline, detail, phase, detail_hold_seconds(detail, interval))
