# display/ui/pr_celebration.py
"""The PR card: confetti and a rising trophy, as on the milestone celebration, then every record the
workout broke, one per turn: its output, a rowing split, each Tread Best Time (1K, 1 Mile, ...).

64x64: the discipline on top in its colour, the trophy under it, then the record, its value and the
class length (or `BEST TIME`), with a dot per turn on the bottom row. 64x32: the discipline across the
top, a 14 px trophy centred on the rows with 2 px either side, and each line centred in the columns to
its right; a line too wide for them moves left only as far as the panel needs, and a wording that would
then touch the trophy gives way to a shorter one (`MARATHON BEST` to `MARATHON`). Joel, 2026-11-22.
"""

from typing import Any

from display.display import get_text_width, loaded_fonts
from driver import graphics
from peloton.selection import normalize_discipline

from .celebration_screen import INTRO_SECONDS, RISE_SECONDS, TROPHY, TROPHY_MID, draw_confetti, draw_trophy
from .last_workout.rotation import LAST_WORKOUT_DETAIL_INTERVAL_SECONDS
from .last_workout.stats import _fmt_split, _whole
from .lifetime_overview import discipline_color
from .screen import Screen

_GOLD = (255, 215, 0)
_WHITE = (255, 255, 255)
_GREEN = (40, 220, 90)
_BLUE = (0, 120, 255)
_DOT_OFF = (70, 70, 90)
_GREY = (150, 150, 170)

# Extra time each record's turn holds on top of one detail interval: a PR is a big moment (Joel, 2026-11-09).
CARD_HOLD_SECONDS = 2.0

# 64 rows: the trophy's column and resting top row; the lines' baselines.
_TALL_TROPHY_LEFT, _TALL_TROPHY_TOP = (64 - len(TROPHY[0])) // 2, 12
_TALL_NAME, _TALL_HEAD, _TALL_VALUE, _TALL_SUB, _TALL_DOTS = 9, 37, 51, 59, 62
# 32 rows: the trophy 2 px in from the left, centred on the 32 rows; the text gets the columns 2 px past it.
_PAD = 2
_SHORT_TROPHY_LEFT = _PAD
_SHORT_TROPHY_TOP = (32 - len(TROPHY_MID)) // 2
_SHORT_TEXT_LEFT = _PAD + len(TROPHY_MID[0]) + _PAD
_SHORT_NAME, _SHORT_HEAD, _SHORT_VALUE, _SHORT_SUB = 6, 13, 23, 30
# Shorter names for a Best Time label whose headline can't fit any other way (Peloton's later distances are guesses).
_SHORT_LABELS = {'HALF MARATHON': 'HALF'}


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def fmt_time(seconds) -> str:
    """A Best Time as the app shows it: M:SS, or H:MM:SS from an hour."""
    total = int(seconds + 0.5)
    hours, rest = divmod(total, 3600)
    return f'{hours}:{rest // 60:02d}:{rest % 60:02d}' if hours else f'{rest // 60}:{rest % 60:02d}'


def best_times(summary: dict) -> list[tuple[str, float, float | None]]:
    """The summary's Best Times as (label, seconds, the time it beat or None), skipping anything damaged: the cache
    can hold anything. A previous time that isn't a slower, whole positive number is dropped, keeping the time."""
    bests = summary.get('best_times')
    out = []
    for b in bests if isinstance(bests, list) else []:
        if not (isinstance(b, dict) and isinstance(b.get('label'), str) and b['label'].strip()):
            continue
        if not (_number(b.get('seconds')) and b['seconds'] > 0):
            continue
        previous = b.get('previous_seconds')
        slower = _number(previous) and int(previous + 0.5) > int(b['seconds'] + 0.5)
        out.append((b['label'].strip().upper(), b['seconds'], previous if slower else None))
    return out


def _time_subs(seconds: float, previous: float | None) -> list[tuple[tuple, list[str]]]:
    """A Best Time's bottom line: how much faster (green), then the time it beat (grey); `BEST TIME` with no saved
    previous one (Joel's pick from real-screen mock-ups, 2026-11-22)."""
    if previous is None:
        return [(_BLUE, ['BEST TIME'])]
    faster = fmt_time(int(previous + 0.5) - int(seconds + 0.5))
    return [(_GREEN, [f'{faster} FASTER', f'-{faster}']), (_GREY, [f'WAS {fmt_time(previous)}'])]


def pr_turns(summary: dict) -> list[tuple[list[str], str, list[tuple[tuple, list[str]]]]]:
    """Every record the workout broke, as (headline wordings, value, bottom lines), output first.

    Wordings run longest first, for the 32-row card to fall back on. The bottom lines share a turn:
    the output's gain (when the app knew the old record) then its class length; a Best Time's `0:32 FASTER`
    then `WAS 10:33` (`_time_subs`).
    """
    dur = summary.get('duration_min')
    length = [(_BLUE, [f'{int(dur)} MIN CLASS', f'{int(dur)} MIN'])] if _number(dur) and dur > 0 else []
    turns = []
    if summary.get('is_output_pr') and _number(summary.get('total_output_kj')):
        precise = summary.get('total_work_kj')
        value = precise if _number(precise) else summary['total_output_kj']
        previous = summary.get('previous_best_kj')
        subs = list(length)
        if _number(previous) and value > previous:
            diff = value - previous
            # Small PRs are common; don't let "+0.8" round away to "+0".
            subs.insert(0, (_GREEN, [f'+{diff:.1f} KJ' if diff < 1 else f'+{_whole(diff):,} KJ']))
        # The app's Total Output, not the precise work: they can round differently.
        turns.append((['OUTPUT PR'], f'{_whole(summary["total_output_kj"]):,} KJ', subs))
    if summary.get('is_splits_pr') and _number(summary.get('row_split_sec_per_500m')):
        turns.append((['SPLITS PR'], f'{_fmt_split(summary["row_split_sec_per_500m"])}/500', length))
    for label, seconds, previous in best_times(summary):
        wordings = [f'{label} BEST', label] + ([_SHORT_LABELS[label]] if label in _SHORT_LABELS else [])
        turns.append((wordings, fmt_time(seconds), _time_subs(seconds, previous)))
    if not turns and summary.get('is_pr'):
        turns.append((['NEW PR'], '', length))
    return turns


def turn_seconds(detail_interval: float) -> float:
    return (detail_interval or LAST_WORKOUT_DETAIL_INTERVAL_SECONDS) + CARD_HOLD_SECONDS


def pr_page_seconds(summary: dict, detail_interval: float) -> float:
    """The card's page: the trophy's entrance, then one turn per record (at least one)."""
    return INTRO_SECONDS + max(1, len(pr_turns(summary))) * turn_seconds(detail_interval)


def _share(t: float, count: int, span: float) -> int:
    """Which of `count` equal shares of `span` seconds t falls in; the last holds past the end."""
    return min(int(max(0.0, t) / (span / count)), count - 1) if count else 0


def _draw(matrix, font, x: int, y: int, color, text: str) -> None:
    graphics.DrawText(matrix, font, x, y, graphics.Color(*color), text)


def _trophy_cells(rows, left: int, top: int) -> set[tuple[int, int]]:
    return {(left + x, top + y) for y, row in enumerate(rows) for x, cell in enumerate(row) if cell == '#'}


_SHORT_TROPHY = _trophy_cells(TROPHY_MID, _SHORT_TROPHY_LEFT, _SHORT_TROPHY_TOP)


def short_line_x(font, text: str) -> int:
    """32 rows: x for a line centred in the columns right of the trophy, moved left only as far as the
    panel's right edge needs."""
    lit = get_text_width(font, text) - 1  # the advance ends in a blank column
    centred = _SHORT_TEXT_LEFT + (64 - _SHORT_TEXT_LEFT - lit) // 2
    return max(0, min(centred, 64 - lit))


def clears_trophy(font, text: str, x: int, baseline: int) -> bool:
    """True when the line's box, with a pixel all round, misses every trophy pixel on 32 rows."""
    top = baseline - font.baseline
    rows = range(top - 1, top + font.height + 1)
    cols = range(x - 1, x + get_text_width(font, text))
    return not any((c, r) in _SHORT_TROPHY for r in rows for c in cols)


def short_wording(font, wordings: list[str], baseline: int) -> tuple[str, int]:
    """The first wording that clears the trophy where it lands, else the last one; with its x."""
    for text in wordings:
        x = short_line_x(font, text)
        if clears_trophy(font, text, x, baseline):
            return text, x
    return wordings[-1], short_line_x(font, wordings[-1])


def _discipline(summary: dict) -> tuple[str, tuple]:
    name = summary.get('discipline')
    if not isinstance(name, str) or not name.strip():
        return '', _WHITE
    return name.strip().upper(), discipline_color(normalize_discipline(name))


class PrCelebrationScreen(Screen):
    """Confetti and a rising trophy, then one turn per record the workout broke.

    state is a workout summary from peloton.stats.summaries.summarize_workout().
    """

    animated = True
    atomic_frames = True
    # 20 fps, as on the milestone celebration: slower makes the confetti jump instead of fall.
    frame_seconds = 0.05

    def __init__(self, detail_interval: float = LAST_WORKOUT_DETAIL_INTERVAL_SECONDS):
        self.elapsed = 0.0
        # The page's own interval (build_rotation_pages sizes the page with it), so the turns fit the page.
        self.detail_interval = detail_interval or LAST_WORKOUT_DETAIL_INTERVAL_SECONDS

    def on_enter(self, matrix, state=None):
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += max(0, dt)

    def render(self, matrix, state: Any | None = None) -> bool:
        summary = state if isinstance(state, dict) else {}
        turns = pr_turns(summary)
        if not turns:
            return False
        short = matrix.height < 64
        draw_confetti(matrix, self.elapsed)
        rise = 1 - (1 - min(1.0, self.elapsed / RISE_SECONDS)) ** 3
        if short:
            top = round(matrix.height - (matrix.height - _SHORT_TROPHY_TOP) * rise)
            draw_trophy(matrix, TROPHY_MID, _SHORT_TROPHY_LEFT, top, self.elapsed)
        else:
            top = round(matrix.height - (matrix.height - _TALL_TROPHY_TOP) * rise)
            draw_trophy(matrix, TROPHY, _TALL_TROPHY_LEFT, top, self.elapsed)
        if self.elapsed < INTRO_SECONDS:
            return True
        span = turn_seconds(self.detail_interval)
        index = _share(self.elapsed - INTRO_SECONDS, len(turns), span * len(turns))
        headlines, value, subs = turns[index]
        sub = subs[_share(self.elapsed - INTRO_SECONDS - index * span, len(subs), span)] if subs else None
        name = _discipline(summary)
        if short:
            self._draw_short(matrix, name, headlines, value, sub)
        else:
            self._draw_tall(matrix, name, headlines, value, sub, index, len(turns))
        return True

    @staticmethod
    def _centred(matrix, font, y: int, color, text: str) -> None:
        _draw(matrix, font, max((matrix.width - get_text_width(font, text)) // 2, 0), y, color, text)

    @staticmethod
    def _fitting(text: str, *fonts):
        """The first font the text fits the panel in (2 px spare), else the last."""
        return next((f for f in fonts if get_text_width(f, text) <= 62), fonts[-1])

    def _draw_tall(self, matrix, name, headlines, value, sub, index: int, count: int) -> None:
        titles, info, big = loaded_fonts['titles'], loaded_fonts['info'], loaded_fonts['discipline']
        text, color = name
        if text:
            self._centred(matrix, self._fitting(text, titles, info), _TALL_NAME, color, text)
        # The full wording in the title font, then the label alone, then the smaller font.
        options = [(h, titles) for h in headlines[:2]] + [(h, info) for h in headlines]
        headline, font = next(((h, f) for h, f in options if get_text_width(f, h) <= 62), options[-1])
        self._centred(matrix, font, _TALL_HEAD, _GOLD, headline)
        if value:
            self._centred(matrix, self._fitting(value, big, titles), _TALL_VALUE, _WHITE, value)
        if sub:
            color, wordings = sub
            line = next((w for w in wordings if get_text_width(info, w) <= 62), wordings[-1])
            self._centred(matrix, info, _TALL_SUB, color, line)
        if count > 1:
            # A dot per record, the current one gold, centred on the bottom row.
            left = (matrix.width - (count * 4 - 2)) // 2
            for i in range(count):
                for dx in (0, 1):
                    matrix.SetPixel(left + i * 4 + dx, _TALL_DOTS, *(_GOLD if i == index else _DOT_OFF))

    def _draw_short(self, matrix, name, headlines, value, sub) -> None:
        info, big = loaded_fonts['info'], loaded_fonts['discipline']
        text, color = name
        if text:
            _draw(matrix, info, short_line_x(info, text), _SHORT_NAME, color, text)
        headline, x = short_wording(info, headlines, _SHORT_HEAD)
        _draw(matrix, info, x, _SHORT_HEAD, _GOLD, headline)
        if value:
            font = self._fitting(value, big, info)
            _draw(matrix, font, short_line_x(font, value), _SHORT_VALUE, _WHITE, value)
        if sub:
            color, wordings = sub
            line, x = short_wording(info, wordings, _SHORT_SUB)
            _draw(matrix, info, x, _SHORT_SUB, color, line)
