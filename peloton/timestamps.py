"""Shared timestamp handling. Date-only values never imply an exact instant."""
from datetime import date, datetime, timezone
from math import isfinite
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FIELDS = ('start_time', 'start_time_iso8601', 'start_date', 'created_at', 'start_date_local')


def display_timezone(name=None):
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            pass
    # astimezone() without a target uses local rules for the date in question.
    return None


def parse_timestamp(value, tzname=None):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = None
    if number is not None:
        if not isfinite(number):
            return None
        try:
            return datetime.fromtimestamp(number / 1000 if abs(number) >= 1e12 else number, timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    if isinstance(value, str):
        value = value.strip()
        if len(value) == 10:
            return None
        try:
            result = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if result.tzinfo is None:
                zone = display_timezone(tzname)
                result = result.replace(tzinfo=zone) if zone else result.astimezone()
            return result.astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def workout_timestamp(workout, tzname=None):
    for field in FIELDS:
        parsed = parse_timestamp(workout.get(field), tzname or workout.get('timezone'))
        if parsed is not None:
            return parsed
    return None


def workout_date(workout, tzname=None):
    timestamp = workout_timestamp(workout, tzname)
    if timestamp is not None:
        return timestamp.astimezone(display_timezone(tzname)).date()
    for field in FIELDS:
        value = workout.get(field)
        if isinstance(value, str) and len(value.strip()) == 10:
            try:
                return date.fromisoformat(value.strip())
            except ValueError:
                pass
    return None
