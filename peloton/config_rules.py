"""The pieces peloton/config.py's validation tables are built from: a Rule row, a runner, and the
small checks ("is a whole number from 1 to 3", "is HH:MM") that the rows share. Standard library only."""
import math
import re
from datetime import date, datetime
from typing import NamedTuple
from collections.abc import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# What a good value looks like. Each takes the value as the config holds it (anything JSON can
# carry) and says whether it passes; bools are never numbers here.

def int_in(value, low, high=None):
    return (not isinstance(value, bool) and isinstance(value, int) and value >= low
            and (high is None or value <= high))


def whole_number(low, high=None):
    return lambda value: int_in(value, low, high)


def or_none(check):
    return lambda value: value is None or check(value)


def is_str(value):
    return isinstance(value, str)


def is_bool(value):
    return isinstance(value, bool)


def is_nonblank_str(value):
    return isinstance(value, str) and bool(value.strip())


def finite_number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def positive_number(value):
    return finite_number(value) and value > 0


def non_negative_number(value):
    return finite_number(value) and value >= 0


def is_env_name(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Z_][A-Z0-9_]*', value) is not None


def is_timezone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        return False
    return True


def is_time_of_day(value):
    try:
        datetime.strptime(value, '%H:%M')
    except (TypeError, ValueError):
        return False
    return True


def is_iso_date(value):
    try:
        date.fromisoformat(value.strip())
    except (AttributeError, ValueError):
        return False
    return True



class Rule(NamedTuple):
    """One check: the value at `key` in a section must pass `ok`, else raise `message`. The message
    is the error text after "<path>: "; {value} is the offending value and {prefix} the section's
    place in the config ("display.", "users[0]."), for rules shared by sections."""
    key: str
    ok: Callable
    message: str

    def __call__(self, path, section, prefix=''):
        value = section.get(self.key)
        if not self.ok(value):
            raise ValueError(f'{path}: ' + self.message.format(value=value, prefix=prefix))


def run(steps, path, section, prefix=''):
    """Apply each step to the section in order; the first one that fails raises. A step is a Rule or
    a function taking (path, section, prefix): the checks that don't fit a row, and the rewrites."""
    for step in steps:
        step(path, section, prefix)
