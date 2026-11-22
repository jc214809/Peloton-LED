"""Parsers for what `systemctl show` prints (times and timespans), for the settings page."""

import re


def unix_time(value):
    """systemctl show's time ("@1762390801", with --timestamp=unix) as epoch seconds; None when
    blank or "n/a"; any other text as it is (an older systemd ignores the flag's format)."""
    value = (value or '').strip()
    if not value or value == 'n/a':
        return None
    if value.startswith('@'):
        try:
            return float(value[1:])
        except ValueError:
            return value
    return value


# systemd's timespan units ("1d 2h 3min 4.5s"), in seconds.
TIMESPAN_UNITS = {'y': 31557600, 'M': 2629800, 'w': 604800, 'd': 86400, 'h': 3600, 'min': 60, 's': 1, 'ms': 1e-3, 'us': 1e-6, 'μs': 1e-6}
TIMESPAN_PART = re.compile(r'(\d+(?:\.\d+)?)\s*(min|ms|us|μs|[yMwdhs])(?![a-z])')


def timespan_seconds(value):
    """systemctl show's timespan ("2h 5min 3.5s") in seconds, or None when blank, 0, "infinity" or
    not a timespan."""
    text = (value or '').strip()
    parts = TIMESPAN_PART.findall(text)
    if not parts or TIMESPAN_PART.sub('', text).strip():
        return None
    total = sum(float(number) * TIMESPAN_UNITS[unit] for number, unit in parts)
    return total if total > 0 else None
