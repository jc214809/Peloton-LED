"""Workout-compare insight data: the frame kinds and the checks that keep a damaged cache off the panel."""
from typing import List


# Workout compare frames (peloton/workouts/insight_lines.board_view), after the chart slides.
INSIGHT_KINDS = ('insight_card', 'insight_bars', 'insight_words')


MAX_INSIGHT_VIEWS = 4   # insight_lines.MAX_BOARD_INSIGHTS: every insight a workout has


# In a view's `reason_parts`: the part drawn as a 5x5 arrow (the font has none), in pixels ('#' lit).
ARROW_PART = 'arrow'


_ARROW_ROWS = ('..#..', '...#.', '#####', '...#.', '..#..')


ARROW_GAP = 2   # dark columns between the arrow and the ink either side of it


_FIGURE_KEYS = {'bars': ('today', 'usual'), 'share': ('pct',), 'blocks': ('total', 'lit')}


TYPICAL_LABEL = 'TYPICAL'  # the 64x64 bars frame's label for the usual figure (the median of similar workouts)


def _strings(lines, most) -> bool:
    return (isinstance(lines, list) and 0 < len(lines) <= most
            and all(isinstance(line, str) and line.strip() for line in lines))


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _good_parts(parts) -> bool:
    """A bottom line drawn in parts (`reason_parts`: text, with ARROW_PART standing for the pixel arrow), absent
    or a short list of strings that fits the 63 px a line has once the arrow and its two gaps are counted."""
    if parts is None:
        return True
    if not (isinstance(parts, list) and 0 < len(parts) <= 3 and all(isinstance(p, str) and p for p in parts)
            and parts.count(ARROW_PART) <= 1):
        return False
    return _parts_layout(parts, lambda text: 4 * len(text))[1] <= 63   # the `stats` font is a fixed 4 px


def _trailing_blank(text: str) -> int:
    """Blank columns after `text`'s ink in the `stats` font: its 4 px cells hold 3 px of ink, the 1 only 2
    (BBX in both tom-thumb.bdf and 4x6-legacy.bdf)."""
    return 2 if text.endswith('1') else 1


def _parts_layout(parts, width_of):
    """([(part, x)], the last ink column) for a bottom line drawn in parts from column 1: an ARROW_PART goes
    ARROW_GAP dark columns after the ink before it, and the next word's ink (it starts at its cell's first
    column) ARROW_GAP after the arrow, so the arrow sits centred whatever digit the rating ends in."""
    x, before, places = 1, '', []
    for part in parts:
        if part == ARROW_PART:
            x += ARROW_GAP - _trailing_blank(before)   # x was the column after the word's cell
            places.append((part, x))
            x += len(_ARROW_ROWS[0]) + ARROW_GAP
        else:
            places.append((part, x))
            x += width_of(part)
        before = part
    return places, x - 1 - (_trailing_blank(before) if before != ARROW_PART else ARROW_GAP)


def _good_figure(figure) -> bool:
    if not (isinstance(figure, dict) and figure.get('kind') in _FIGURE_KEYS
            and all(_number(figure.get(key)) for key in _FIGURE_KEYS[figure['kind']])):
        return False
    if figure['kind'] == 'bars' and not all(isinstance(figure.get(k), str) for k in ('today_text', 'usual_text')):
        return False
    if not all(isinstance(figure.get(key, ''), str) for key in ('unit', 'label', 'usual_label')):
        return False
    # The 64x64 bars' label for the usual figure sits left of its number: TYPICAL's 7 characters at most.
    if len(figure.get('usual_label', '')) > len(TYPICAL_LABEL) or not _number(figure.get('top', 0)):
        return False
    if figure['kind'] == 'share' and figure['pct'] > 100:
        return False
    return not (figure['kind'] == 'blocks' and not (
        isinstance(figure['total'], int) and isinstance(figure['lit'], int)
        and 0 < figure['total'] <= 30 and figure['lit'] <= figure['total']))


def _good_view(view) -> bool:
    if not isinstance(view, dict):
        return False
    figure, colour, pages = view.get('figure'), view.get('colour'), view.get('pages32')
    if figure is not None and not _good_figure(figure):  # None: words only (an instructor milestone)
        return False
    if not _strings(view.get('highlight', ['-']), 2):
        return False
    reason = view.get('reason')
    if not _good_parts(view.get('reason_parts')):
        return False
    return (isinstance(colour, (list, tuple)) and len(colour) == 3
            and all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in colour)
            and all(isinstance(view.get(key), str) and view[key].strip() for key in ('headline', 'footer'))
            and (reason is None or isinstance(reason, str))
            and _strings(view.get('lines64'), 5)
            and isinstance(pages, list) and 0 < len(pages) <= 2 and all(_strings(page, 3) for page in pages))


def insight_views(summary: dict) -> List[dict]:
    """The workout's insight views (workout compare), at most MAX_INSIGHT_VIEWS, skipping damaged ones: the cache could
    hold anything. A version 2 `insight` (one dict) is never drawn."""
    views = summary.get('insights')
    if not isinstance(views, list):
        return []
    return [view for view in views if _good_view(view)][:MAX_INSIGHT_VIEWS]
