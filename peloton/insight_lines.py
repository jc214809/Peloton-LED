"""Workout compare on the board: the two short lines for one insight. Standard library only.

`board_lines(code, facts)` turns an insight's code and facts (peloton/workout_insights.py) into two upper-case
lines for the `stats` font (15 characters, 60 px). Only a movement name may run longer: the display scrolls it.
"""
LINE_MAX = 15
HIDDEN_CODES = ('too_few', 'nothing', 'freestyle', 'incomplete', 'unsupported', 'no_tracker')


def number(value, unit):
    """A value as printed everywhere: watts and pounds whole, mph to one decimal."""
    return f'{value:.1f}' if unit == 'mph' else f'{value:.0f}'


def versus(value, usual, unit):
    """'124 VS 188 W', or without the unit when that is wider than a line, or just the value with its unit."""
    a, b = number(value, unit), number(usual, unit)
    unit = unit.upper()
    for line in (f'{a} VS {b} {unit}', f'{a} VS {b}'):
        if len(line) <= LINE_MAX:
            return line
    return f'{a} {unit}'


def _pair(facts):
    return versus(facts['value'], facts['usual'], facts['unit'])


def _output_up(facts):
    return [f"STRONG {facts['noun'].upper()}", _pair(facts)]


def _output_down(facts):
    return ['PACE DOWN' if facts['foot'] else 'OUTPUT DOWN', _pair(facts)]


def _of_the_time(facts):
    line = f"{facts['pct']}% OF THE TIME"
    return line if len(line) <= LINE_MAX else f"{facts['pct']}% OF TIME"


def _go_up_streak(facts):
    return [f"GO UP: {facts['category'].upper()}", f"FROM {number(facts['lb'], 'lb')} LB"]


_RULES = {
    'output_down': _output_down,
    'output_up': _output_up,
    'in_line': lambda f: ['ON YOUR USUAL', _pair(f)],
    'resistance_low': lambda f: ['RESISTANCE LOW', f"{f['pct']}% UNDER"],
    'cadence_low': lambda f: ['CADENCE LOW', f"{f['pct']}% UNDER"],
    'pace_low': lambda f: ['UNDER PACE', _of_the_time(f)],
    'go_up_lighter': lambda f: ['GO UP A WEIGHT', f['movement']],
    'go_up_streak': _go_up_streak,
    'went_heavier': lambda f: ['HEAVIER: KEEP', versus(f['lb'], f['usual'], 'lb')],
    'missed_targets': lambda f: ['DROP A WEIGHT', f['movement']],
    'effort_high': lambda f: ['HARDEST BY HR', f"OF YOUR LAST {f['n']}"],
    'effort_low': lambda f: ['EASIEST BY HR', f"OF YOUR LAST {f['n']}"],
}


def board_lines(code, facts):
    """[line 1, line 2] upper case, or None for a hidden or unknown code or facts that lack a number."""
    rule = _RULES.get(code)
    if code in HIDDEN_CODES or rule is None:
        return None
    try:
        return [line.upper() for line in rule(facts or {})]
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def first_board_insight(messages):
    """{'code', 'lines', 'facts'} for the first (code, text, facts) the board shows, else None."""
    for code, _text, facts in messages:
        lines = board_lines(code, facts)
        if lines:
            return {'code': code, 'lines': lines, 'facts': facts}
    return None
