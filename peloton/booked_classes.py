"""Booked classes: the slim record the board keeps per live or encore class the rider booked, which one the
next-class page shows, and the words it says.

Raw data comes from two calls (docs/PELOTON-API.md): GET /api/user/{id}/reservations lists the booked classes'
IDs, and GET /api/peloton/{id}?joins=ride,ride.instructor gives each one's start, tag, class and instructor.
Only what the page draws is kept, so the cache stays small and an odd response can't reach the screen.
Standard library only, so the cache can validate with it.
"""
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Peloton's class disciplines under the board's names (peloton.workout_features.DISCIPLINE_ALIAS).
ALIAS = {'caesar': 'rowing', 'caesar_bootcamp': 'row_bootcamp', 'circuit': 'tread_bootcamp'}
# What the class line calls a class of each discipline: `20 MIN RIDE`.
NOUNS = {'cycling': 'RIDE', 'running': 'RUN', 'walking': 'WALK', 'rowing': 'ROW', 'strength': 'STRENGTH',
         'yoga': 'YOGA', 'meditation': 'MEDITATION', 'stretching': 'STRETCH', 'cardio': 'CARDIO',
         'bike_bootcamp': 'BIKE BOOTCAMP', 'tread_bootcamp': 'TREAD BOOTCAMP', 'row_bootcamp': 'ROW BOOTCAMP'}
# First names more than one Peloton instructor has (all 57 in GET /api/instructor, 2026-11-14): these
# show the full name, so `JESS` can't be the wrong Jess.
SHARED_FIRST_NAMES = frozenset({'ALEX', 'HANNAH', 'JESS', 'MARCEL'})
LIVE, ENCORE = 'LIVE', 'ENCORE'
# The page stays up this long after the start (`NOW` / `STARTING`), then the next booking takes its place.
SHOWN_AFTER_START = 600
# Within this long of the start the page counts down in minutes (`45 MIN` / `AT 2:15 PM`).
MINUTES_WITHIN = 3600
# Longest text kept from a response; anything longer is cut, never trusted to fit.
MAX_TEXT = 40
WEEKDAYS = ('MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY')
MONTHS = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _text(value):
    return ' '.join(str(value).split())[:MAX_TEXT] if isinstance(value, str) else ''


def reservation_ids(payload):
    """The booked classes' IDs (`peloton_id`) in a reservations response, each once. Raises ValueError when
    the response isn't one, so a bad response keeps the last list rather than emptying the page."""
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
        raise ValueError('Malformed reservations response')
    ids = []
    for row in payload['data']:
        identity = row.get('peloton_id') if isinstance(row, dict) else None
        if isinstance(identity, str) and identity.strip() and identity.strip() not in ids:
            ids.append(identity.strip()[:64])
    return ids


def slim_class(payload, identity=None):
    """One GET /api/peloton/{id}?joins=ride,ride.instructor response as the board keeps it, or None when it
    can't be shown (no start, no class, no length)."""
    if not isinstance(payload, dict) or not isinstance(payload.get('ride'), dict):
        return None
    ride = payload['ride']
    start = _number(payload.get('scheduled_start_time'))
    seconds = _number(ride.get('duration'))
    discipline = _text(ride.get('fitness_discipline')).lower()
    if start is None or not seconds or seconds <= 0 or not discipline:
        return None
    instructor = ride.get('instructor')
    tag = ENCORE if payload.get('is_encore') is True else LIVE if payload.get('is_live') is True else None
    return {'id': _text(identity or payload.get('id'))[:64], 'start': start, 'tag': tag,
            'discipline': ALIAS.get(discipline, discipline), 'minutes': max(1, round(seconds / 60)),
            'instructor': _text(instructor.get('name')) if isinstance(instructor, dict) else ''}


def valid_booking(booking):
    """A kept booking the page can draw: the cache can hold anything."""
    return (isinstance(booking, dict) and isinstance(booking.get('id'), str)
            and _number(booking.get('start')) is not None and booking.get('tag') in (LIVE, ENCORE, None)
            and isinstance(booking.get('discipline'), str) and booking['discipline']
            and isinstance(booking.get('minutes'), int) and not isinstance(booking['minutes'], bool)
            and 0 < booking['minutes'] < 1000 and isinstance(booking.get('instructor'), str))


def valid_bookings(bookings):
    return isinstance(bookings, list) and all(valid_booking(b) for b in bookings)


def next_booking(bookings, now):
    """The booking the page shows: the soonest one that hasn't been going for SHOWN_AFTER_START, or None."""
    if not isinstance(bookings, list):
        return None
    upcoming = [b for b in bookings if valid_booking(b) and b['start'] + SHOWN_AFTER_START > now]
    return min(upcoming, key=lambda b: b['start']) if upcoming else None


def class_lines(booking):
    """The class line, longest first: `20 MIN RIDE`, then the noun alone. A discipline the board doesn't
    know is named by Peloton's key (`OUTDOOR`)."""
    noun = NOUNS.get(booking['discipline'], booking['discipline'].replace('_', ' ').upper())
    return [f"{booking['minutes']} MIN {noun}", noun]


def instructor_lines(name):
    """The instructor line, longest first: `WITH BEN`, then `BEN`; a shared first name is the full name
    (`JESS SIMS`), then the first name. Empty when there's no instructor."""
    words = name.upper().split()
    if not words:
        return []
    if words[0] in SHARED_FIRST_NAMES and len(words) > 1:
        return [' '.join(words), words[0]]
    return [f'WITH {words[0]}', words[0]]


def _zone(name):
    try:
        return ZoneInfo(name) if name else timezone.utc
    except (ValueError, KeyError):  # a bad name never stops the page: UTC
        return timezone.utc


def clock_parts(moment):
    """('10:00', 'AM') for a local datetime."""
    hour = moment.hour % 12 or 12
    return f'{hour}:{moment.minute:02d}', 'AM' if moment.hour < 12 else 'PM'


def day_word(start, now):
    """TODAY, TOMORROW, the weekday within the week, else the date (`NOV 21`), for local datetimes."""
    days = (start.date() - now.date()).days
    if days <= 0:
        return 'TODAY'
    if days == 1:
        return 'TOMORROW'
    if days < 7:
        return WEEKDAYS[start.weekday()]
    return f'{MONTHS[start.month - 1]} {start.day}'


def when(booking, now, zone_name=None):
    """What the page says about the start, in the board's zone:
    - `clock`: more than an hour away: the clock time (`10:00` `AM`) and the day (`TOMORROW`);
    - `minutes`: within the hour: the minutes left (45, rounded up) and the clock time;
    - `now`: from the start."""
    zone = _zone(zone_name)
    start = datetime.fromtimestamp(booking['start'], zone)
    local_now = datetime.fromtimestamp(now, zone)
    time_text, meridiem = clock_parts(start)
    left = booking['start'] - now
    if left <= 0:
        mode = 'now'
    elif left <= MINUTES_WITHIN:
        mode = 'minutes'
    else:
        mode = 'clock'
    return {'mode': mode, 'time': time_text, 'meridiem': meridiem, 'minutes': max(1, math.ceil(left / 60)),
            'day': day_word(start, local_now)}

