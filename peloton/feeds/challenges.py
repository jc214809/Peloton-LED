"""Peloton challenges: the slim record the board keeps per joined challenge, and which of them to show.

Raw entries come from GET /api/user/{id}/challenges/current?has_joined=true (docs/PELOTON-API.md). Only what
the challenges page draws is kept, so the cache stays small and an odd response can't reach the screen.
No imports from the app, so the cache can validate with it.
"""

import math
import re

# Peloton's units, as the page writes them.
UNITS = {
    'min': 'MIN',
    'minutes': 'MIN',
    'workouts': 'CLASSES',
    'classes': 'CLASSES',
    'days': 'DAYS',
    'miles': 'MILES',
    'mi': 'MILES',
    'km': 'KM',
    'meters': 'METERS',
    'm': 'METERS',
    'reps': 'REPS',
}
# Before the first tier Peloton calls the current tier this.
UNEARNED = 'UNEARNED'
_MONTH_NAMES = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December')
_MONTHS = '|'.join(_MONTH_NAMES)
# 'NOV': what a monthly challenge's title keeps of its month (the screens never drop it when a title is too long).
MONTH_ABBREVIATIONS = {name.upper(): name[:3].upper() for name in _MONTH_NAMES}
_NUMBER = re.compile(r'^\d{1,3}(,\d{3})*(\.\d+)?$|^\d+(\.\d+)?$')
# Longest text kept from a response; anything longer is cut, never trusted to fit.
MAX_TEXT = 40


def short_title(title):
    """The page's title: 'The Annual 2026' -> 'ANNUAL 2026', 'The Countdown to Turkey Burn Challenge' ->
    'TURKEY BURN'. A monthly challenge keeps its month, abbreviated and first, and drops the year:
    'November 2026 Rep Goal Challenge' -> 'NOV REP GOAL'."""
    text = ' '.join(str(title or '').split())
    text = re.sub(r'^the\s+', '', text, flags=re.I)
    text = re.sub(r'^countdown\s+to\s+', '', text, flags=re.I)
    month = re.search(rf'\b({_MONTHS})\s+\d{{4}}\b\s*', text, flags=re.I)
    if month:  # '<Month> <Year>' wherever it sits: out of the text, in front as the abbreviation
        text = text[: month.start()] + text[month.end() :]
    text = re.sub(r'\s+challenge$', '', text.strip(), flags=re.I)
    if month:
        text = f'{MONTH_ABBREVIATIONS[month.group(1).upper()]} {text}'.strip()
    return text.upper()[:MAX_TEXT].strip()


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def format_number(value):
    """5503 -> '5,503'; 12.5 -> '12.5'."""
    return f'{value:,.0f}' if float(value).is_integer() else f'{value:,.1f}'


def _shown(text, fallback):
    """Peloton's pre-formatted number if it is one ('5,503', '12.5'), else ours."""
    text = text.strip() if isinstance(text, str) else ''
    return text if _NUMBER.match(text) else format_number(fallback)


def _tier(raw):
    if not isinstance(raw, dict):
        return None
    title = ' '.join(str(raw.get('title') or '').split()).upper()[:MAX_TEXT]  # '1K ' -> '1K'
    value = _number(raw.get('metric_value'))
    if not title or value is None:
        return None
    return {'title': title, 'value': value}


def slim_challenge(entry):
    """One entry of challenges/current as the board keeps it, or None when it can't be shown."""
    if not isinstance(entry, dict):
        return None
    summary, progress = entry.get('challenge_summary'), entry.get('progress')
    if not isinstance(summary, dict) or not isinstance(progress, dict):
        return None
    title = short_title(summary.get('title'))
    value = _number(progress.get('metric_value'))
    tier = _tier(progress.get('current_tier')) or {'title': UNEARNED, 'value': 0.0}
    if not title or value is None:
        return None
    unit = str(progress.get('metric_display_unit') or '').strip().lower()
    following = _tier(progress.get('next_tier'))
    end = _number(summary.get('end_time'))
    challenge = {
        'id': str(summary.get('id') or '')[:64],
        'title': title,
        'end_time': end,
        'value': value,
        'shown': _shown(progress.get('metric_display_value'), value),
        'unit': UNITS.get(unit, unit.upper()[:12]),
        'tier': tier,
        'next': following,
        'to_next': None,
    }
    if following:
        challenge['to_next'] = _shown(progress.get('metric_display_value_to_next_tier'), max(0.0, following['value'] - value))
    return challenge


def parse_challenges(payload):
    """Every joined challenge in a challenges/current response, slimmed. Raises ValueError when the response
    isn't one (so a bad response keeps the last good list rather than emptying the page)."""
    if not isinstance(payload, dict) or not isinstance(payload.get('challenges'), list):
        raise ValueError('Malformed challenges response')
    slim = []
    for entry in payload['challenges']:
        if isinstance(entry, dict) and (entry.get('progress') or {}).get('has_joined') is False:
            continue
        challenge = slim_challenge(entry)
        if challenge:
            slim.append(challenge)
    return slim


def _valid_tier(tier):
    return isinstance(tier, dict) and isinstance(tier.get('title'), str) and tier['title'] and _number(tier.get('value')) is not None


def valid_challenge(challenge):
    """A kept challenge the page can draw: the cache can hold anything."""
    return (
        isinstance(challenge, dict)
        and isinstance(challenge.get('title'), str)
        and challenge['title']
        and isinstance(challenge.get('shown'), str)
        and isinstance(challenge.get('unit'), str)
        and _number(challenge.get('value')) is not None
        and _valid_tier(challenge.get('tier'))
        and (challenge.get('next') is None or (_valid_tier(challenge['next']) and isinstance(challenge.get('to_next'), str)))
        and (challenge.get('end_time') is None or _number(challenge['end_time']) is not None)
    )


def shown_challenges(challenges, now):
    """The challenges with a page, soonest-ending first: still running, with some progress and a tier to go
    for. A challenge at its top tier has no next tier, and one at 0 (say, one counting only its own series'
    classes) would only show an empty ring."""
    if not isinstance(challenges, list):
        return []
    shown = [
        c
        for c in challenges
        if valid_challenge(c) and c['next'] is not None and c['value'] > 0 and (c['end_time'] is None or c['end_time'] > now)
    ]
    return sorted(shown, key=lambda c: c['end_time'] if c['end_time'] is not None else math.inf)


def tier_progress(challenge):
    """How far from the current tier to the next one, 0 to 1."""
    low, high = challenge['tier']['value'], challenge['next']['value']
    if high <= low:
        return 0.0
    return min(1.0, max(0.0, (challenge['value'] - low) / (high - low)))
