"""Lifetime miles as a trip: where you're headed, how far you've come, a progress bar for this leg,
and the miles split by how they were covered (BIKE / WALK/RUN / ROW, peloton.journey.MILE_GROUPS).

64 rows show it all on one page. 32 rows show the trip, then the split ("MILES BY TYPE"), sharing
the page's time (state['step_seconds'], from build_rotation_pages); with one group there's no split
to show, so the trip stays up the whole time.

Each step opens with a short animation, then holds still to be read: the bar fills while the miles
count up across this leg (the total up, the miles to go down, the percent up), the bar's tip then
pulses gently, and the groups come in one after another
(64 rows: each row slides in from the left; 32 rows: the split bar grows a colour at a time, each
row appearing as its colour lands). Everything settles within INTRO_SECONDS of the step starting.
"""
import math

from driver import graphics

from display.display import get_text_width, loaded_fonts
from .lifetime_overview import discipline_color
from .screen import Screen

TRACK_COLOR = (30, 30, 38)
DONE_COLOR = (255, 140, 0)
TIP_COLOR = (255, 255, 255)
# Each group in its Lifetime-page colour: the bike's red, running's green, the rower's blue.
GROUP_COLORS = {'bike': discipline_color('cycling'), 'walk_run': discipline_color('running'),
                'row': discipline_color('rowing')}
_GREY = graphics.Color(145, 165, 190)
_GOLD = graphics.Color(255, 215, 0)
_WHITE = graphics.Color(255, 255, 255)
_ORANGE = graphics.Color(*DONE_COLOR)
SPLIT_TITLE = 'MILES BY TYPE'
MAX_GROUPS = 3

# The animation, in seconds from the start of a step. A 32-row step has at least 4 s (FRAME_SECONDS),
# so the intro leaves 3 s of still page.
FILL_SECONDS = 1.0           # the bar fills and the miles count up
ROW_START_SECONDS = 0.3      # 64 rows: the first group row starts sliding in
ROW_GAP_SECONDS = 0.15       # ... and each next one this much later
ROW_SLIDE_SECONDS = 0.25     # ... taking this long to arrive
SPLIT_GROW_SECONDS = 0.8     # 32 rows: the split bar grows to full width
INTRO_SECONDS = 1.0          # all of the above are done by now (a test checks)
PULSE_SECONDS = 2.0          # the bar's tip: bright to dim and back
PULSE_LOW = 0.35             # the tip's dimmest, as a share of full brightness


def _fit(font, text, width):
    while text and get_text_width(font, text) > width:
        text = text[:-1]
    return text.rstrip()


DECIMAL_STEPS = (2, 1, 0)  # the groups' miles: most decimals first; a figure takes the first its room allows
TOTAL_DECIMAL_STEPS = (1, 0)  # the big total: one decimal on both boards (Joel, 2026-11-11), none if it won't fit


def _miles(value, decimals=2):
    """The miles as 1,234.56, with `decimals` places."""
    return f'{value:,.{decimals}f}'


def group_cents(groups, total):
    """Each group's miles in hundredths, rounded so they add up to the total's hundredths (largest
    remainder): rounding each alone can leave the rows a cent off the big figure."""
    values = [max(0.0, g.get('miles') or 0) * 100 for g in groups]
    cents = [int(v) for v in values]
    short = round(total * 100) - sum(cents)
    if not 0 <= short <= len(cents):  # rows that don't belong to this total: plain rounding
        return [round(v) for v in values]
    order = sorted(range(len(values)), key=lambda i: values[i] - cents[i], reverse=True)
    for i in order[:short]:
        cents[i] += 1
    return cents


def group_figure(cents, fits=lambda text: True):
    """A group's miles from its hundredths: two decimals, else one, else none, the first that fits."""
    texts = [_miles(cents / 100, d) for d in DECIMAL_STEPS]
    return next((t for t in texts if fits(t)), texts[-1])


def percent(progress):
    """Whole percent of this leg, rounded down so it never says 100% short of the destination."""
    return f"{min(99, int(progress['fraction'] * 100))}%"


def journey_text(progress, fits=lambda text: True, miles_fit=lambda text: True):
    """(miles, status) strings shared by both layouts. The miles keep one decimal if
    miles_fit(text) allows, else none; the status keeps its one decimal only
    when fits(status) says the line has room for it."""
    remaining = progress['route_miles'] - progress['leg_miles']
    suffix = 'TO HOME' if progress['returning'] else 'TO GO'
    status = f'{remaining:,.1f} {suffix}'
    if not fits(status):
        status = f'{round(remaining):,} {suffix}'
    texts = [_miles(progress['miles'], d) for d in TOTAL_DECIMAL_STEPS]
    return next((t for t in texts if miles_fit(t)), texts[-1]), status


def groups_of(progress):
    groups = progress.get('groups')
    return [g for g in groups if isinstance(g, dict)][:MAX_GROUPS] if isinstance(groups, list) else []


def journey_steps(progress, matrix_height):
    """How many steps the page shows: 2 on 32 rows when there's a split to show, else 1."""
    return 2 if matrix_height < 64 and len(groups_of(progress)) >= 2 else 1


def ease_out(t):
    """0 to 1 over t in [0, 1], fast then settling (cubic)."""
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def at_moment(progress, t):
    """progress as the opening animation shows it t seconds into a step: this leg's miles, and so
    the total, the miles to go and the percent, run from where the leg began to where you are, in
    step with the bar. From FILL_SECONDS on, progress itself."""
    grown = ease_out(t / FILL_SECONDS)
    if grown >= 1:
        return progress
    leg = progress['leg_miles'] * grown
    return {**progress, 'leg_miles': leg, 'miles': progress['miles'] - progress['leg_miles'] + leg,
            'fraction': progress['fraction'] * grown}


def counted_miles(progress, t, miles_fit=lambda text: True):
    """The big figure t seconds into a step; its decimals are decided once, from the final figure."""
    final = journey_text(progress, miles_fit=miles_fit)[0]
    return _miles(at_moment(progress, t)['miles'], len(final.partition('.')[2]))


def trip_text(progress, t, fits=lambda text: True, miles_fit=lambda text: True):
    """(miles, status, percent) t seconds into a step. Whether the status keeps its decimal, and how
    many the miles keep, is decided once, from the final figures, so neither changes format while
    it counts."""
    keeps_decimal = journey_text(progress, fits)[1] == journey_text(progress)[1]
    moment = at_moment(progress, t)
    status = journey_text(moment, fits=lambda text: keeps_decimal)[1]
    return counted_miles(progress, t, miles_fit), status, percent(moment)


def tip_brightness(t):
    """The bar tip's brightness t seconds into a step: full while the bar fills, then a slow pulse."""
    if t < FILL_SECONDS:
        return 1.0
    wave = (1 + math.cos(2 * math.pi * (t - FILL_SECONDS) / PULSE_SECONDS)) / 2
    return PULSE_LOW + (1 - PULSE_LOW) * wave


def _rect(matrix, x0, x1, y0, height, color):
    for x in range(x0, x1 + 1):
        for y in range(y0, y0 + height):
            matrix.SetPixel(x, y, *color)


def _right(matrix, font, right, y, color, text):
    graphics.DrawText(matrix, font, right - get_text_width(font, text), y, color, text)


class JourneyScreen(Screen):
    """state: the dict from peloton.journey.journey_progress(), plus step_seconds on 32 rows."""
    animated = True
    atomic_frames = True
    frame_seconds = 0.05  # 20 fps, smooth enough for the fill and the slide

    def __init__(self):
        self.elapsed = 0.0
        self._step = 0

    def on_enter(self, matrix, state=None):
        self.elapsed = 0.0
        self._step = 0

    def update(self, dt):
        self.elapsed += max(0, dt)

    def render(self, matrix, state=None):
        progress = state if isinstance(state, dict) else None
        small = loaded_fonts.get('stats') or loaded_fonts.get('info')
        if not progress or small is None or 'fraction' not in progress:
            return False
        big = loaded_fonts.get('big') or small
        if matrix.height >= 64:
            # Heading, miles, status and bar take the top 40 rows; the split fills the rest.
            self._trip(matrix, progress, small, (big, loaded_fonts.get('bold') or small), self.elapsed,
                       miles_y=24, status_y=32, bar_y=36, bar_h=4, trip_y=40)
            self._legend(matrix, progress, small, self.elapsed)
            return True
        step, since = 0, self.elapsed
        if journey_steps(progress, matrix.height) == 2:
            share = progress.get('step_seconds')
            if isinstance(share, (int, float)) and not isinstance(share, bool) and share > 0:
                step = min(1, int(self.elapsed / share))
                since = self.elapsed - step * share
        if step != self._step:
            matrix.Clear()  # a board without frame canvases keeps the last step's pixels otherwise
            self._step = step
        if step == 0:
            self._trip(matrix, progress, small, (big, loaded_fonts.get('countdown') or small), since,
                       miles_y=17, status_y=23, bar_y=27, bar_h=3, trip_y=31)
        else:
            self._split(matrix, progress, small, since)
        return True

    def _trip(self, matrix, progress, small, big_fonts, t, miles_y, status_y, bar_y, bar_h, trip_y):
        w = matrix.width
        # Where you're headed: the destination, or home on the way back.
        place = progress['from'] if progress['returning'] else progress['to']
        graphics.DrawText(matrix, small, 2, 6, _GOLD, _fit(small, f'TO {place.upper()}', w - 4))
        # Room, font and MI's place come from the final figures, so nothing moves while they count.
        room = w - 4 - get_text_width(small, percent(progress)) - 3
        unit_w = get_text_width(small, 'MI')

        def big_font(text):
            return next((f for f in big_fonts if 2 + get_text_width(f, text) + 2 + unit_w <= w - 2), None)
        # One decimal if a big font has room for it beside MI, else none.
        miles = journey_text(progress, miles_fit=lambda text: big_font(text) is not None)[0]
        font = big_font(miles) or small
        shown, status, pct = trip_text(progress, t, fits=lambda text: get_text_width(small, text) <= room,
                                       miles_fit=lambda text: big_font(text) is not None)
        graphics.DrawText(matrix, font, 2, miles_y, _WHITE, shown)
        graphics.DrawText(matrix, small, 2 + get_text_width(font, miles) + 2, miles_y, _WHITE, 'MI')
        graphics.DrawText(matrix, small, 2, status_y, _ORANGE, _fit(small, status, room))
        _right(matrix, small, w - 2, status_y, _GREY, pct)
        # This leg's progress; past the first leg, the trip number shortens the bar.
        bar_end = w - 3
        if progress.get('trip', 1) > 1:
            tag = f"TRIP {progress['trip']}"
            _right(matrix, small, w - 2, trip_y, _GREY, tag)
            bar_end = w - 2 - get_text_width(small, tag) - 3
        _rect(matrix, 2, bar_end, bar_y, bar_h, TRACK_COLOR)
        filled = round((bar_end - 1) * progress['fraction'] * ease_out(t / FILL_SECONDS))
        if filled:
            _rect(matrix, 2, 1 + filled, bar_y, bar_h, DONE_COLOR)
        if progress['fraction'] > 0:
            # You are here: the bar's leading edge, white while it fills, then pulsing.
            level = tip_brightness(t)
            tip = tuple(round(c * level) for c in TIP_COLOR)
            _rect(matrix, 1 + max(1, filled), 1 + max(1, filled), bar_y, bar_h, tip)

    def _legend(self, matrix, progress, small, t):
        """64 rows: one row a group under the bar, a colour square, the name, the miles; each slides
        in from the left in turn."""
        w = matrix.width
        groups = groups_of(progress)
        cents = group_cents(groups, progress['miles'])
        for row, group in enumerate(groups):
            arrived = ease_out((t - ROW_START_SECONDS - row * ROW_GAP_SECONDS) / ROW_SLIDE_SECONDS)
            if arrived <= 0:
                continue
            dx = -round(w * (1 - arrived))
            y = 47 + row * 7
            color = GROUP_COLORS.get(group.get('key'), (200, 200, 235))
            _rect(matrix, 2 + dx, 4 + dx, y - 4, 3, color)
            name = str(group.get('label', ''))
            # Two decimals unless the whole label then wouldn't fit beside them (WALK/RUN at 100+ miles).
            value = group_figure(cents[row], lambda text: 7 + get_text_width(small, name) + 3
                                 <= w - 2 - get_text_width(small, text))
            label = _fit(small, name, w - 2 - get_text_width(small, value) - 3 - 7)
            graphics.DrawText(matrix, small, 7 + dx, y, graphics.Color(*color), label)
            _right(matrix, small, w - 2 + dx, y, _WHITE, value)

    def _split(self, matrix, progress, small, t):
        """32 rows, second step: the split as one bar in the groups' colours, grown a colour at a
        time, then a row each, shown once its colour has landed."""
        w = matrix.width
        graphics.DrawText(matrix, small, 2, 6, _GOLD, SPLIT_TITLE)
        groups = groups_of(progress)
        total = sum(g.get('miles') or 0 for g in groups) or 1
        cents = group_cents(groups, progress['miles'])
        span = w - 4
        reach = 2 + round(span * ease_out(t / SPLIT_GROW_SECONDS))  # the grown bar ends before this
        x = 2
        for row, group in enumerate(groups):
            color = GROUP_COLORS.get(group.get('key'), (200, 200, 235))
            n = span - (x - 2) if row == len(groups) - 1 else round(span * (group.get('miles') or 0) / total)
            if n > 0 and reach > x:
                _rect(matrix, x, min(x + n, reach) - 1, 8, 2, color)
            x += n
            if reach < x:
                continue  # this colour hasn't landed: its row waits
            y = 17 + row * 7
            name = str(group.get('label', ''))
            value = group_figure(cents[row], lambda text: 2 + get_text_width(small, name) + 3
                                 <= w - 2 - get_text_width(small, text))
            label = _fit(small, name, w - 4 - get_text_width(small, value) - 3)
            graphics.DrawText(matrix, small, 2, y, graphics.Color(*color), label)
            _right(matrix, small, w - 2, y, _WHITE, value)
