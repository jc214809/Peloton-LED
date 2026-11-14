"""Next milestone: 3 TO GO / TILL YOUR / 600TH / RIDE, or NEXT ONE / IS YOUR / 600TH / RIDE when one is left, with a progress bar (32 rows: 3 AWAY FROM / YOUR 600TH / RIDE, no bar).

One page per target within a few workouts, the total's or a discipline's.
state: {'total': 597, 'target': 600, 'previous': 500, 'title': 'Cycling', 'discipline': 'cycling'};
previous is where the bar starts. The name is drawn in the discipline's Lifetime-page colour
(discipline None, the total: the default one).
"""
from driver import graphics

from display.display import get_text_width, loaded_fonts
from .celebration_screen import _cap_height, discipline_noun, ordinal_line
from .lifetime_overview import discipline_color
from .screen import Screen

_WHITE = (255, 255, 255)
_GOLD = (255, 215, 0)
_GREY = (145, 165, 190)
BAR_FILL = (0, 120, 255)
BAR_EMPTY = (35, 35, 35)


def _bar(matrix, top, height, fraction):
    left, right = 3, matrix.width - 4
    filled = round((right - left + 1) * max(0.0, min(1.0, fraction)))
    for x in range(left, right + 1):
        color = BAR_FILL if x < left + filled else BAR_EMPTY
        for y in range(top, top + height):
            matrix.SetPixel(x, y, *color)


def _fonts(*keys):
    return [loaded_fonts[key] for key in keys if loaded_fonts.get(key) is not None]


def _draw_runs(matrix, runs, baseline):
    """runs: [(font, text, colour, gap after)] centred as one line on a baseline."""
    width = sum(get_text_width(font, text) + gap for font, text, _, gap in runs)
    x = max((matrix.width - width) // 2, 0)
    for font, text, color, gap in runs:
        graphics.DrawText(matrix, font, x, baseline, graphics.Color(*color), text)
        x += get_text_width(font, text) + gap


# A two-word name too wide for the bold font is drawn in the 8 px `titles` font with a tighter space: 3 px
# between the words, 2 if it must (TREAD BOOTCAMP is 64 columns edge to edge), and BOO 2 px right of where
# it falls, closing the hole before the T. Every width counts the font's blank column after each word.
WORD_GAPS = (3, 2)
KERNS = {'BOOTCAMP': 3}     # word: where to split it, so BOO can be drawn on its own
WORD_NUDGE = {'TREAD': -1}  # first word: px its second word moves (TREAD BOOTCAMP: BOOTCAMP 1 px left)
B_SHIFT = {'BIKE': 1}       # a word whose first letter is drawn this many px right (BIKE: the gap after its B)
WORD_SHIFT = {'BIKE': 1}    # a first word drawn this many px right, its second word staying put
BOO_SHIFT = 2               # BOO is drawn 2 px right of where it falls, TCAMP and the rest where they were


# Where the lit pixels of the bootcamp names fall when drawn from x = 0: (first lit column, lit width). Measured
# once on the emulator (the Pi's fonts can't be measured by drawing; test_countdown_ink_table re-checks it) so
# each name is centred by its lit pixels, an odd spare column going to the left.
NAME_INK = {'ROW BOOTCAMP': (0, 56), 'BIKE BOOTCAMP': (2, 59), 'TREAD BOOTCAMP': (1, 63)}


# Every 7x13B letter and digit, and the 4x6 and 5x8 letters a 32-row line starts or ends with (YOUR, TH, FROM),
# is lit from its first column, with one blank column after it; of the 5x8 digits the count starts with, 0 and 1
# start with a blank column. Measured once, like NAME_INK (test_countdown_line_edge_ink re-checks it).
LINE_TRAILING_BLANK = 1
LEAD_DIGIT_BLANK = {'0': 1, '1': 1}
LEAD_WORD_GAP = 3   # px added between the top line's words (the 5x8 space is wider than it needs)
_COUNT = _GOLD   # 32 rows: the count is gold like the milestone (Joel, 2026-11-14: it was cyan)


def _lit_centre_x(matrix, runs, lead_blank=0):
    """Where the first lit column goes so the runs' lit pixels are centred, an odd spare column going left."""
    lit = sum(get_text_width(font, text) + gap for font, text, _, gap in runs) - LINE_TRAILING_BLANK - lead_blank
    return max((matrix.width - lit + 1) // 2, 0)


def _draw_runs_at(matrix, runs, baseline, x):
    for font, text, color, gap in runs:
        graphics.DrawText(matrix, font, x, baseline, graphics.Color(*color), text)
        x += get_text_width(font, text) + gap


def _word_runs(word, font, color, gap_after):
    split = KERNS.get(word)
    if split and font is not None:
        return [(font, word[:split], color, 0), (font, word[split:], color, gap_after)]
    if (word in B_SHIFT or word in WORD_SHIFT) and font is not None:
        # An empty run pushes the word right, and the gaps after its letters shrink by as much, so nothing
        # after the word moves: the whole word by WORD_SHIFT, its first letter further by B_SHIFT.
        b, w = B_SHIFT.get(word, 0), WORD_SHIFT.get(word, 0)
        return [(font, '', color, b + w), (font, word[0], color, -b), (font, word[1:], color, gap_after - w)]
    return [(font, word, color, gap_after)]


def tight_name_runs(name, font, color, room):
    """Runs drawing a two-word `name` in `font` with the narrowest space that fits `room`, else None."""
    words = name.split()
    if font is None or len(words) != 2:
        return None
    for gap in WORD_GAPS:
        runs = _word_runs(words[0], font, color, gap - 1) + _word_runs(words[1], font, color, 0)
        for i, run in enumerate(runs):
            if run[1] == 'BOO' and i:   # BOO 2 px right: the gap before it grows, the one after it shrinks
                runs[i - 1] = runs[i - 1][:3] + (runs[i - 1][3] + BOO_SHIFT,)
                runs[i] = run[:3] + (run[3] - BOO_SHIFT,)
        if sum(get_text_width(f, t) + g for f, t, _, g in runs) - len(words) <= room:   # each word's blank column
            nudge = WORD_NUDGE.get(words[0], 0)   # after the fit, so the gap chosen is the one that fits
            if nudge:
                runs[0] = runs[0][:3] + (runs[0][3] + nudge,)
            return runs
    return None


def _fit(text, fonts, room):
    """The first font the text fits in, else the last (smallest) one."""
    return next((font for font in fonts if get_text_width(font, text) <= room), fonts[-1])


class CountdownScreen(Screen):

    @staticmethod
    def _render_short(matrix, left_to_go, target, name, color, bold):
        """32 rows: 3 AWAY FROM / YOUR 600TH / RIDE, no bar. The top line in 5x8 (the count gold, the words
        white), then YOUR (4x6, white, floating mid-line: 2 rows either side) and the gold 7x13B number with its
        raised TH, then the name in 7x13B in its Lifetime colour. Lines on rows 3-8, 12-20, 23-31; a name in a
        smaller font (a bootcamp's 5x8, STRETCHING) closes up to 4-9, 12-20, 23-28 so the gaps match. Every line is centred by
        its lit pixels."""
        small = (_fonts('stats', 'info') or [bold])[0]
        lead_font = (_fonts('discipline') or [bold])[0]
        raise_by = (_cap_height(bold) - _cap_height(small)) // 2
        tight = name in NAME_INK and tight_name_runs(name, loaded_fonts.get('discipline'), color, matrix.width)
        name_font = None if tight else _fit(name, [bold] + _fonts('discipline', 'info'),
                                                          matrix.width + LINE_TRAILING_BLANK)
        top, number_y, name_y = (9, 21, 32) if name_font is bold else (10, 21, 29)
        count = str(left_to_go)
        lead = [(lead_font, count, _COUNT, LEAD_WORD_GAP), (lead_font, 'AWAY', _WHITE, LEAD_WORD_GAP),
                (lead_font, 'FROM', _WHITE, 0)]
        blank = LEAD_DIGIT_BLANK.get(count[0], 0) if lead_font is loaded_fonts.get('discipline') else 0
        _draw_runs_at(matrix, lead, top, _lit_centre_x(matrix, lead, blank) - blank)
        your = get_text_width(small, 'YOUR') + 2
        gold = graphics.Color(*_GOLD)
        # The number beside YOUR (its comma dropped if that's what fits); too wide for that, on its own.
        parts = ordinal_line(target, [bold], small, number_y, gold, 0, matrix.width + LINE_TRAILING_BLANK - your)
        with_your = parts is not None
        parts = parts or ordinal_line(target, [bold], small, number_y, gold, 0, matrix.width + LINE_TRAILING_BLANK)
        if parts:
            first = min(x for _, x, _, _, _ in parts)
            end = max(x + get_text_width(font, text) for font, x, _, _, text in parts)
            lit = end - first - LINE_TRAILING_BLANK + (your if with_your else 0)
            x = max((matrix.width - lit + 1) // 2, 0)
            if with_your:
                _draw_runs_at(matrix, [(small, 'YOUR', _WHITE, 0)], number_y - raise_by, x)
                x += your
            for font, part_x, y, part_color, text in parts:
                graphics.DrawText(matrix, font, x + part_x - first, y, part_color, text)
        if tight:   # drawn as on 64 rows: 5x8 with the tight space and kerning
            left, lit = NAME_INK[name]
            _draw_runs_at(matrix, tight, name_y, (matrix.width - lit + 1) // 2 - left)
        else:   # discipline_noun always gives a word
            runs = [(name_font, name, color, 0)]
            _draw_runs_at(matrix, runs, name_y, _lit_centre_x(matrix, runs))
        return True

    def render(self, matrix, state=None):
        state = state if isinstance(state, dict) else {}
        total, target, previous = state.get('total'), state.get('target'), state.get('previous', 0)
        if (not all(isinstance(v, int) and not isinstance(v, bool) for v in (total, target, previous))
                or target <= total):
            return False
        big, bold = _fonts('big'), _fonts('bold', 'big')
        if not big or not bold:
            return False
        big, bold = big[0], bold[0]
        color = discipline_color(state.get('discipline'))
        fraction = (total - previous) / (target - previous) if target > previous else 0
        # The same noun the celebration uses (the discipline's name only where it has no word of its own).
        name = discipline_noun(state.get('discipline'), state.get('title')) if state.get('discipline') else 'WORKOUT'
        if matrix.height < 64:
            return self._render_short(matrix, target - total, target, name, color, bold)
        more = [(big, str(target - total), _WHITE, 3), (bold, 'TO GO', _WHITE, 0)]
        # The 7x13B 'bold' where the name fits (6x13B squashed STRENGTH and WORKOUT), 6x13B for the two widest
        # (STRETCHING, MEDITATION).
        names = _fonts('bold', 'title_bold', 'titles', 'info')
        titles = loaded_fonts.get('titles')
        # Four lines and the bar, spaced evenly: 3 TO GO / TILL YOUR / 600TH / RIDE, or with one left
        # (the next workout is the milestone) NEXT ONE / IS YOUR / 600TH / RIDE in the same places.
        lead, link = (([(bold, 'NEXT ONE', _WHITE, 0)], 'IS YOUR') if target - total == 1 else (more, 'TILL YOUR'))
        _draw_runs(matrix, lead, 16)
        _draw_runs(matrix, [(_fonts('stats', 'info')[0], link, _GREY, 0)], 25)
        number_y, name_y, bar_top, bar_height = 42, 54, 58, 3
        parts = ordinal_line(target, [big, bold], titles, number_y, graphics.Color(*_GOLD), 0, matrix.width)
        for font, x, y, line_color, text in parts or ():
            graphics.DrawText(matrix, font, x, y, line_color, text)
        if name and names:
            font = _fit(name, names, matrix.width - 2)
            tight = None
            if font is not names[0] and get_text_width(names[0], name) > matrix.width - 2:
                tight = tight_name_runs(name, loaded_fonts.get('titles'), color, matrix.width)
            if tight and name in NAME_INK:
                left, lit = NAME_INK[name]
                _draw_runs_at(matrix, tight, name_y, (matrix.width - lit + 1) // 2 - left)
            else:
                _draw_runs(matrix, tight or [(font, name, color, 0)], name_y)
        _bar(matrix, bar_top, bar_height, fraction)
        return True
