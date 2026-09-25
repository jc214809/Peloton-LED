"""Quiet-hours refresh scheduling: poll Peloton less often overnight."""
from datetime import datetime
from zoneinfo import ZoneInfo


def _minutes(hhmm):
    hour, minute = map(int, hhmm.split(':'))
    return hour * 60 + minute


def in_quiet_hours(schedule, now=None, timezone_name=None):
    """True when `now` falls inside the configured quiet window.

    schedule is display.refresh_schedule: {'quiet_start', 'quiet_end', ...}.
    The window can wrap midnight (e.g. 23:00 -> 05:00).
    """
    if not schedule:
        return False
    zone_name = schedule.get('timezone') or timezone_name
    zone = ZoneInfo(zone_name) if zone_name else None
    current = now or datetime.now(zone)
    minute = current.hour * 60 + current.minute
    start = _minutes(schedule['quiet_start'])
    end = _minutes(schedule['quiet_end'])
    if start == end:
        return False  # a zero-width window never applies
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def scheduled_refresh_interval(schedule, default_interval, now=None, timezone_name=None):
    """The refresh interval to use right now: the quiet interval during the
    quiet window, else the normal default_interval. Falls back to
    default_interval whenever scheduling is disabled or misconfigured."""
    if not schedule or not in_quiet_hours(schedule, now, timezone_name):
        return default_interval
    return schedule.get('quiet_interval', default_interval)
