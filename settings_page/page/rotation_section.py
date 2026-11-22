"""The Rotation card: which screens play, in what order, for how long, and what each one's time means."""

from html import escape

from peloton.screen_times import HIGHLIGHT_SECONDS, VERSUS_STATS, least_seconds, page_seconds
from settings_page.form import SCREENS, SHARED_DURATION, board_rows, duration_fallback, number_text, rotation_rows, section
from settings_page.page.icons import icon
from settings_page.page.widgets import _attr, _hint, _number, _section, _switch_input, _tip

# The Rotation list's column headings: (CSS class, heading, tooltip or None).
ROTATION_COLUMNS = (
    ('grip-col', '', None),
    ('', '#', 'Switched-on screens play in this order, numbered. Drag a screen by its handle, or use its arrow, to move it.'),
    ('', 'Screen', None),
    (
        'seconds-col',
        'Seconds',
        'How long each page shows; the line under each screen says what that means '
        'for it. Blank uses the setting it falls back on (shown greyed out). To hide a '
        'screen, switch it off.',
    ),
    (
        '',
        'Show',
        'Off takes the screen out of the rotation and moves it to the bottom. A screen with nothing to show yet is skipped either way.',
    ),
    ('', '', None),
)


def _rotation_head():
    """The headings above the rotation's rows, in their columns (decoration for screen readers: each
    row's controls carry their own labels)."""
    cells = ''.join(
        f'<span class="{css}">{escape(heading)}'
        + (_tip(f'tip-rotation-{heading.lower().strip("#") or "order"}', heading if heading != '#' else 'Order', tip) if tip else '')
        + '</span>'
        for css, heading, tip in ROTATION_COLUMNS
    )
    return f'<div class="screens-head" id="screens-head">{cells}</div>'


def _secs(value):
    return f'{number_text(round(value, 1))} s'


# A ride's workout page, for the Latest workouts line: the opening frame, 6 stats and 2 charts.
RIDE_STATS, RIDE_CHARTS = 6, 2


def _shows_latest_workouts(name, t, display, rows):
    stat = display['last_workout_detail_interval']
    ride = stat * (1 + RIDE_STATS) + (stat + 1) * RIDE_CHARTS
    return (
        f'Each workout shows every stat once: {_secs(stat)} each (the stat time under Timing), charts '
        f'1 s longer. A ride is about {_secs(ride)}.'
    )


def _shows_username(name, t, display, rows):
    three = max(t, 3 * HIGHLIGHT_SECONDS)
    return f'Shared by its highlights, at least {_secs(HIGHLIGHT_SECONDS)} each: with 3, {_secs(three / 3)} each ({_secs(three)} in all).'


def _shows_versus(name, t, display, rows):
    if rows < 64:
        return f'{_secs(t)}: {_secs(t / VERSUS_STATS)} for each of its {VERSUS_STATS} stats, one at a time.'
    return f'{_secs(t)}: all {VERSUS_STATS} stats on one page.'


def _shows_lifetime(name, t, display, rows):
    return f'{_secs(t)} a page, {4 if rows >= 64 else 2} disciplines a page.'


def _shows_next_milestone(name, t, display, rows):
    return f'{_secs(t)} a countdown, up to {display.get("milestone_pages", 3)}.'


def _shows_journey(name, t, display, rows):
    if rows < 64:
        both = page_seconds(display, name, rows, 2)
        return (
            f'{_secs(t)}. With miles of more than one type, the trip then the miles by type, {_secs(both / 2)} each ({_secs(both)} in all).'
        )
    return f'{_secs(t)}.'


# The screens whose line is worked out from more than their time: name -> function(name, t, display, rows).
SHOWS = {
    'latest_workouts': _shows_latest_workouts,
    'username': _shows_username,
    'versus': _shows_versus,
    'lifetime': _shows_lifetime,
    'next_milestone': _shows_next_milestone,
    'journey': _shows_journey,
}
# The rest say their time and then this.
SHOWS_AFTER_TIME = {
    'total_workouts': ', like each Lifetime page.',
    'milestones': ': the trophy rises, then the number.',
    'goals': ' a goal.',
    'challenges': ' a challenge.',
    'club': '.',
    'next_class': ', when a class is booked.',
}


def shows_for(name, display, rows):
    """What a screen's time means on this board, worked out as the board works it out
    (peloton.screen_times). display: the config's display over DEFAULTS."""
    t = page_seconds(display, name, rows)
    if name in SHOWS:
        return SHOWS[name](name, t, display, rows)
    return f'{_secs(t)}{SHOWS_AFTER_TIME.get(name, ".")}'


def _screen_row(name, label, hint, on, display, rows=64):
    """One rotation screen: posted as "rotation_order" in page order, with its switch and time.
    display: the config's display over DEFAULTS."""
    durations = section(display, 'screen_durations')
    least = least_seconds(name, rows)
    if name == 'latest_workouts':
        # Each page lasts every stat once: no time of its own to set.
        time = '<span class="time shared" title="Every stat once, at the stat time under Timing">Every stat</span>'
    elif name in SHARED_DURATION:
        other = dict((n, lbl) for n, lbl, _ in SCREENS)[SHARED_DURATION[name]]
        # The column is narrow: the label's first word ("Lifetime"), the full name in the tooltip.
        time = f'<span class="time shared" title="Shown as long as each {_attr(other)} page">Same as {escape(other.split()[0])}</span>'
    else:
        # A saved time under what the screen needs shows as the board plays it (saving keeps that).
        own = durations.get(name)
        if isinstance(own, (int, float)) and not isinstance(own, bool):
            own = max(own, least)
        seconds = _number(
            f'duration_{name}', own, max(duration_fallback(display, name), least), f' aria-label="{_attr(label)} seconds"', 's', least
        )
        time = f'<span class="time">{seconds}</span>'
    switch = _switch_input(f'rotation_on_{name}', on, f' aria-label="Show {_attr(label)}"')
    grip = (
        f'<button type="button" class="grip js-only" hidden aria-label="Drag to reorder {_attr(label)}, '
        f'or use the arrow keys">{icon("grip")}</button>'
    )
    return (
        f'<li class="screen-row{" on" if on else ""}"><input type="hidden" name="rotation_order" value="{name}">'
        f'{grip}'
        f'<div><label class="screen-name" for="rotation_on_{name}">{escape(label)}</label>{_hint(hint)}'
        f'<p class="hint shows">Shows: {escape(shows_for(name, display, rows))}</p></div>'
        f'{time}{switch}'
        f'<button type="button" class="move js-only" hidden aria-label="Move {_attr(label)} earlier">'
        f'{icon("up")}</button></li>'
    )


def _rows(matrix):
    return board_rows(matrix)


def rotation_card(display, merged, matrix):
    """display: the config's display; merged: it over DEFAULTS; matrix: the config's matrix."""
    screen_rows = ''.join(
        _screen_row(name, *dict((n, (lbl, h)) for n, lbl, h in SCREENS)[name], on, merged, _rows(matrix))
        for name, on in rotation_rows(display)
    )
    return _section(
        'rotation',
        'Rotation',
        'Which screens the board shows, in this order, and for how long.',
        (_rotation_head() + f'<ol class="screens" id="screens" aria-label="Screens, in order">{screen_rows}</ol>'),
        'list',
    )
