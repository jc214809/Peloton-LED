"""The Workout insights card: the switch, and each rider's workout-compare history on this board."""
from datetime import date as calendar_date
from html import escape

from settings_page.history import RECENT_DAYS
from settings_page.page.widgets import _at, _notice, _pill, _section, _switch

# A rider's workout-compare history (settings_page.history), by state: the pill and what to do.
HISTORY_TEXT = {
    'missing': ('bad', 'Not copied yet', 'Copy it from the Mac (below).'),
    'old': ('bad', 'Out of date', 'Copied by an older version, so the board ignores it: copy it again.'),
    'unreadable': ('bad', "Can't be read", 'Copy it again.'),
}


def _workout_day(date):
    """'2026-09-02' (the workout's own day, from its row) as 'Sep 2'; anything else as it is."""
    try:
        found = calendar_date.fromisoformat(date)
    except (TypeError, ValueError):
        return str(date or 'Unknown day')
    return f'{found:%b} {found.day}'


def _incomplete(workouts):
    """The last RECENT_DAYS' workouts saved without all their data (settings_page.history), as a
    closed list under the count; a line saying so when there are none."""
    if not workouts:
        return f'<span class="hint whole">Every workout in the last {RECENT_DAYS} days has its full data.</span>'
    items = ''.join(
        f'<li>{escape(_workout_day(w.get("date")))} &middot; {escape(w.get("title") or "Untitled workout")}'
        f' <span class="hint">&middot; no {escape(", no ".join(w["missing"]))}</span></li>' for w in workouts)
    count = len(workouts)
    return (f'<details class="incomplete whole"><summary>{_pill("warn", f"{count} missing data")}'
            f'<span class="hint">in the last {RECENT_DAYS} days</span></summary><ul>{items}</ul>'
            '<p class="hint">Peloton didn\'t send this when the workout was saved; older workouts '
            'aren\'t checked, since Peloton used to send less.</p></details>')


def _history_row(rider, zone):
    if rider['state'] == 'ready':
        workouts = rider['workouts']
        value = _pill('ok', f'{workouts:,} workout{"" if workouts == 1 else "s"}')
        if rider.get('updated'):
            value += f'<span class="hint">to compare with &middot; updated {escape(_at(rider["updated"], zone))}</span>'
        return rider['name'], value + _incomplete(rider.get('incomplete') or [])
    kind, label, advice = HISTORY_TEXT.get(rider['state'], HISTORY_TEXT['unreadable'])
    return rider['name'], _pill(kind, label) + f'<span class="hint">{escape(advice)}</span>'


def insights_card(display, history=None, zone=None):
    """The workout_insights switch, and each rider's history on this board (settings_page.history:
    None leaves it off). display: the config's display over DEFAULTS."""
    on = display.get('workout_insights') is True
    body = _switch('workout_insights', 'Show workout insights', on,
                   "After the latest workout's charts, comparisons with your similar earlier "
                   'workouts, such as "Output down: 124 W vs your typical 188".')
    if history is not None:
        waiting = [rider['name'] for rider in history if rider['state'] != 'ready']
        if on and waiting:
            body += _notice('warn', f'<strong>{escape(", ".join(waiting))}</strong>: no insights until '
                                    f'{"its" if len(waiting) == 1 else "their"} history is copied to this board.')
        items = ''.join(f'<dt>{escape(name)}</dt><dd>{value}</dd>'
                        for name, value in (_history_row(rider, zone) for rider in history))
        body += (f'<h3>History on this board</h3><dl class="facts" id="insight-history">{items}</dl>'
                 '<p class="hint">The workouts each rider is compared with: the last two years of rides, runs, '
                 'walks, rows, strength and bootcamps. It is copied from the Mac once, with '
                 '<code>scripts/push_workout_rows.sh</code>; after that the board adds each new workout itself.</p>')
    return _section('insights', 'Workout insights',
                    'Comparisons with your similar earlier workouts, after your latest workout.', body, 'bulb')
