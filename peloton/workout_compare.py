"""Workout compare: which earlier workouts are similar (spec sections 4 and 6).

"Similar" is a set of hard rules, not a score. Works on the rows of peloton/workout_features.py.
Standard library only.
"""
import math
import statistics

MAX_PEERS = 12
MIN_PEERS = 5
BASELINE_DAYS = 365
FALLBACK_DAYS = 730
LENGTH_RATIO = 0.7
ARMS_SECTIONS_GAP = 1  # rule 4b: bike arms rides within this many arms sections of each other
DAY = 86400
DISCIPLINES = ('cycling', 'bike_bootcamp', 'rowing', 'row_bootcamp', 'running', 'walking',
               'tread_bootcamp', 'strength')
BIKE = ('cycling', 'bike_bootcamp')
# Fill-in (section 4.1): bike only in version 1. A discipline joins only by passing the same
# measured check as the bike did, not by being added here.
FILL_IN_DISCIPLINES = BIKE
FILL_IN_MIN_REAL = 2
FILL_IN_DAYS = 730
PLAN_KEYS = ('ride_min', 'arms_min', 'planned_watts', 'planned_watts_high', 'effort_share',
             'efforts_per_10min', 'effort_length_s', 'cadence_mean', 'resistance_mean')


def _near_length(a, b):
    if not a['dur'] or not b['dur']:
        return False
    return min(a['dur'], b['dur']) / max(a['dur'], b['dur']) >= LENGTH_RATIO


def is_peer(target, row):
    """True when `row` is the same kind of workout as `target` (order and dates not checked)."""
    if row['id'] == target['id'] or not row['complete']:
        return False
    if target['wtype'] != 'class' or not target['ctype']:
        return False  # freestyle and untyped classes have no peers in version 1
    if not (row['disc'] == target['disc'] and row['wtype'] == 'class'
            and row['ctype'] == target['ctype'] and row['mode'] == target['mode']
            and row['outdoor'] == target['outdoor'] and _near_length(target, row)):
        return False
    if target['disc'] in BIKE and target['mode'] == 'arms':
        gap = abs((row.get('arms_sections') or 0) - (target.get('arms_sections') or 0))
        return gap <= ARMS_SECTIONS_GAP
    return True


def peers(target, rows, days=BASELINE_DAYS):
    """The most recent MAX_PEERS similar workouts in the `days` before the target, newest first."""
    start = target['start'] - days * DAY
    found = [r for r in rows if start <= r['start'] < target['start'] and is_peer(target, r)]
    found.sort(key=lambda r: -r['start'])
    return found[:MAX_PEERS]


def baseline(target, rows):
    """(peers, window days): the last year, or the last two when the last year has under MIN_PEERS."""
    found = peers(target, rows, BASELINE_DAYS)
    if len(found) >= MIN_PEERS:
        return found, BASELINE_DAYS
    wider = peers(target, rows, FALLBACK_DAYS)
    return (wider, FALLBACK_DAYS) if len(wider) > len(found) else (found, BASELINE_DAYS)


def stat(target_value, peer_values):
    """{'value','median','pct','below','n'} or None when either side is missing."""
    values = [v for v in peer_values if v is not None]
    if target_value is None or not values:
        return None
    median = statistics.median(values)
    if not median:
        return None
    return {'value': target_value, 'median': median, 'n': len(values),
            'pct': round(100 * (target_value / median - 1), 1),
            'below': sum(1 for v in values if v < target_value)}


def standardise(plans, keys=PLAN_KEYS):
    """Each plan's descriptors as z-scores over the given plans (a missing value counts as 0)."""
    z = [{} for _ in plans]
    for key in keys:
        values = [plan.get(key) or 0.0 for plan in plans]
        mean, spread = statistics.mean(values), statistics.pstdev(values) or 1.0
        for i, value in enumerate(values):
            z[i][key] = (value - mean) / spread
    return z


def distance(a, b, keys=PLAN_KEYS):
    """Root mean square of the standardised differences: every descriptor weighs the same."""
    return math.sqrt(sum((a[k] - b[k]) ** 2 for k in keys) / len(keys))


def fill_in(target, rows, real):
    """Plan-nearest bike classes that bring `real` peers up to MIN_PEERS (section 4.1).

    Returns copies flagged `fill_in: True`, nearest first; [] when the rule does not apply.
    """
    if (target['disc'] not in FILL_IN_DISCIPLINES or not target.get('plan')
            or not FILL_IN_MIN_REAL <= len(real) < MIN_PEERS):
        return []
    taken = {r['id'] for r in real}
    start = target['start'] - FILL_IN_DAYS * DAY
    candidates = [r for r in rows
                  if start <= r['start'] < target['start'] and r['id'] != target['id']
                  and r['id'] not in taken and r['complete'] and r.get('plan')
                  and r['disc'] == target['disc'] and r['wtype'] == 'class'
                  and r['mode'] == target['mode'] and _near_length(target, r)]
    if not candidates:
        return []
    z = standardise([target['plan']] + [r['plan'] for r in candidates])
    ranked = sorted(zip(candidates, z[1:]), key=lambda pair: (distance(z[0], pair[1]), -pair[0]['start']))
    return [dict(row, fill_in=True) for row, _ in ranked[:MIN_PEERS - len(real)]]


def comparison_group(target, rows):
    """(peers, window days, real peer count): baseline peers plus any bike fill-in, flagged."""
    found, window = baseline(target, rows)
    return found + fill_in(target, rows, found), window, len(found)
