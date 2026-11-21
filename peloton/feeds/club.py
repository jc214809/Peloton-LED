"""Club Peloton: the rider's level and points as the board keeps them, and what the club page shows.

Raw data comes from GET https://members-score.onepeloton.com/v2/user/{id}/score (docs/PELOTON-API.md), an
undocumented host the Peloton web app calls, and, until that first answers, `badge_level` from GET /api/me.
Only what the page draws is kept, so the cache stays small and an odd response can't reach the screen.
Standard library only, so the cache can validate with it.
"""
import math
from datetime import datetime, timezone

# `badge_level` in /api/me, 0 to 10, and the names the score calls them (upper case).
LEVELS = ('BRONZE I', 'BRONZE II', 'BRONZE III', 'SILVER I', 'SILVER II', 'SILVER III',
          'GOLD I', 'GOLD II', 'GOLD III', 'CHAMPION', 'LEGEND')
# The gem's kind is the level's first word; anything else is drawn as gold.
KINDS = ('BRONZE', 'SILVER', 'GOLD', 'CHAMPION', 'LEGEND')
# Peloton answers 404 for a rider with no score (free trial, cancelled): the record says so, and no page shows.
NOT_A_MEMBER = {'member': False}
# Longest text kept from a response; anything longer is cut, never trusted to fit.
MAX_TEXT = 20


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def _points(value):
    """A whole, non-negative points figure, or None."""
    value = _number(value)
    return int(value) if value is not None and value >= 0 else None


def _name(value):
    return ' '.join(value.split()).upper()[:MAX_TEXT] if isinstance(value, str) else ''


def _epoch(text):
    """'2026-12-01T04:59:00Z' -> seconds since 1970, or None."""
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.fromisoformat(text.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def _segment(segments, level, points):
    """The progress bar's segment for this level: the one it names, else the one the points fall in."""
    rows = [s for s in segments if isinstance(s, dict)]
    for row in rows:
        if _name(row.get('label')) == level:
            return row
    for row in rows:
        low, high = _points(row.get('min_points')), _points(row.get('max_points'))
        if low is not None and low <= points and (high is None or points < high):
            return row
    return None


def _boost_until(boost, now):
    """When a running double-points boost ends, or None: Peloton sends `boost` null when there's none."""
    if not isinstance(boost, dict) or str(boost.get('status') or '').lower() != 'active':
        return None
    until = _epoch(boost.get('expires_at'))
    return until if until is not None and until > now else None


def parse_score(payload, now):
    """A members-score v2 response as the board keeps it. Raises ValueError when it isn't one (so a bad
    response keeps the last figures rather than emptying the page)."""
    if not isinstance(payload, dict) or not isinstance(payload.get('progress_bar'), dict):
        raise ValueError('Malformed Club Peloton score')
    bar = payload['progress_bar']
    level = _name(payload.get('badge_level_name') or bar.get('badge_level_name'))
    points = _points(payload.get('total_earned_points'))
    if points is None:
        points = _points(bar.get('score'))
    if not level or points is None:
        raise ValueError('Club Peloton score has no level or points')
    low, high = _points(bar.get('tier_base_points')), _points(bar.get('tier_max_points'))
    if low is None or low > points:
        low = 0
    if high is not None and (high <= low or high < points):
        high = None  # a top under the base or the points can't be drawn
    segments = bar.get('segment_tiers_max_points')
    segments = segments if isinstance(segments, list) else []
    segment = _segment(segments, level, points)
    following = _name(segment.get('next_level_name')) if segment else ''
    target = _points(segment.get('max_points')) if segment else None
    if target is None or target <= points:
        target = high if high is not None and high > points else None
    marks = []
    if bar.get('ignore_segments_on_profile') is not True:
        # Where one level of the tier ends and the next begins: Gold I | Gold II | Gold III.
        marks = sorted({m for m in (_points(s.get('min_points')) for s in segments if isinstance(s, dict))
                        if m is not None and low < m < (high if high is not None else -1)})
    return {'level': level, 'points': points, 'tier_min': low, 'tier_max': high, 'marks': marks[:8],
            'next': following or None, 'to_next': target - points if following and target else None,
            'boost_until': _boost_until(payload.get('boost'), now)}


def level_from_me(me):
    """The level from /api/me's `badge_level` (0 to 10) while the score hasn't arrived, or None."""
    rank = (me or {}).get('badge_level') if isinstance(me, dict) else None
    if isinstance(rank, int) and not isinstance(rank, bool) and 0 <= rank < len(LEVELS):
        return LEVELS[rank]
    return None


def valid_club(club):
    """A kept record the page can draw (or NOT_A_MEMBER): the cache can hold anything."""
    if club == NOT_A_MEMBER:
        return True
    if not isinstance(club, dict) or not isinstance(club.get('level'), str) or not club['level']:
        return False
    points, low, high = club.get('points'), club.get('tier_min'), club.get('tier_max')
    if _points(points) is None or _points(low) is None or low > points:
        return False
    if high is not None and (_points(high) is None or high <= low):
        return False
    marks = club.get('marks')
    if not isinstance(marks, list) or not all(_points(m) is not None for m in marks):
        return False
    following, to_next = club.get('next'), club.get('to_next')
    if following is not None and (not isinstance(following, str) or not following):
        return False
    if to_next is not None and (_points(to_next) is None or following is None):
        return False
    until = club.get('boost_until')
    return until is None or _number(until) is not None


def gem_kind(level):
    """'GOLD III' -> 'GOLD'; an unknown name is drawn as gold."""
    first = level.split()[0] if isinstance(level, str) and level.split() else ''
    return first if first in KINDS else 'GOLD'


def club_page(club, me, now):
    """The club page's state, or None when there's nothing to show: the score's figures; else, before the
    first score, the level from /api/me alone; nothing for a rider Peloton says has no score."""
    if club == NOT_A_MEMBER:
        return None
    if valid_club(club):
        boost = club['boost_until'] is not None and club['boost_until'] > now
        return {**club, 'kind': gem_kind(club['level']), 'boost': boost}
    level = level_from_me(me)
    if level is None:
        return None
    return {'level': level, 'kind': gem_kind(level), 'points': None, 'boost': False}


def tier_fraction(club, points=None):
    """How far `points` (the rider's, by default) are across the tier, 0 to 1; a tier with no top is full."""
    low, high = club['tier_min'], club['tier_max']
    value = club['points'] if points is None else points
    if high is None:
        return 1.0
    return min(1.0, max(0.0, (value - low) / (high - low)))
