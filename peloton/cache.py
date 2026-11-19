"""Private, atomic persistence for the last successful dashboard snapshot."""
import json
import os
from pathlib import Path

from .booked_classes import valid_bookings
from .challenges import valid_challenge
from .club import valid_club
from .goals import parse_milestone_key


CACHE_VERSION = 1
PERSISTED_KEYS = (
    'me', 'totals', 'summaries', 'last_updated', 'generation',
    'active_day_count', 'celebrated_pr_ids', 'pr_shown_at',
    'weekly_progress', 'celebrated_milestones', 'personal_records', 'streaks',
    'milestone_shown_at', 'celebrated_discipline_milestones', 'discipline_milestone_shown_at',
    'name_facts_passes', 'name_facts_shown', 'challenges', 'booked_classes', 'club',
)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _usable(snapshot):
    """Whether the fields every screen relies on have the right shape. If not, the whole cache goes."""
    if not isinstance(snapshot, dict):
        return False
    if not isinstance(snapshot.get('summaries'), list) or not isinstance(snapshot.get('totals'), dict):
        return False
    if snapshot.get('me') is not None and not isinstance(snapshot.get('me'), dict):
        return False
    celebrated = snapshot.get('celebrated_pr_ids', [])
    if not isinstance(celebrated, list) or not all(isinstance(value, str) for value in celebrated):
        return False
    milestones = snapshot.get('celebrated_milestones', [])
    if not isinstance(milestones, list) or not all(isinstance(value, int) for value in milestones):
        return False
    if not isinstance(snapshot.get('weekly_progress', {}), dict):
        return False
    return _is_number(snapshot.get('last_updated'))


def _unless_none(valid):
    return lambda value: value is None or valid(value)


def _valid_records(records):
    return isinstance(records, dict) and all(
        isinstance(r, dict) and isinstance(r.get('workout_id'), str) for r in records.values())


def _valid_streaks(streaks):
    return isinstance(streaks, dict) and all(_is_int(v) for v in streaks.values())


def _valid_milestone_clock(shown):
    return isinstance(shown, dict) and all(
        key.isdigit() and _is_number(at) for key, at in shown.items())


def _valid_pr_clock(shown):
    return isinstance(shown, dict) and all(
        isinstance(key, str) and _is_number(at) for key, at in shown.items())


def _valid_discipline_milestones(celebrated):
    return isinstance(celebrated, list) and all(parse_milestone_key(key) for key in celebrated)


def _valid_discipline_clock(shown):
    return isinstance(shown, dict) and all(
        parse_milestone_key(key) and _is_number(at) for key, at in shown.items())


def _valid_challenges(challenges):
    return isinstance(challenges, list) and all(valid_challenge(c) for c in challenges)


# A damaged entry is dropped on its own (the cache is kept); the comment says what the loss costs.
_REPAIRS = (
    # A damaged records table only loses PR gains.
    ('personal_records', _unless_none(_valid_records)),
    # A damaged streaks entry only hides the streak screen.
    ('streaks', _unless_none(_valid_streaks)),
    # A damaged celebration clock only restarts a milestone's day of celebrating.
    ('milestone_shown_at', _unless_none(_valid_milestone_clock)),
    # Likewise the PR celebration clock: damage only restarts a PR's day of celebrating.
    ('pr_shown_at', _unless_none(_valid_pr_clock)),
    # Per-discipline milestones ('strength:500'): damage only means one may celebrate again.
    ('celebrated_discipline_milestones', _unless_none(_valid_discipline_milestones)),
    ('discipline_milestone_shown_at', _unless_none(_valid_discipline_clock)),
    # Challenges: a damaged list only hides the page until the next hourly fetch.
    ('challenges', _unless_none(_valid_challenges)),
    # Booked classes: a damaged list only hides the page until the next refresh asks again.
    ('booked_classes', valid_bookings),
    # Club Peloton: a damaged record falls back to the level from the profile until the next fetch.
    ('club', _unless_none(valid_club)),
)


def _valid_name_facts(passes, facts):
    return (_is_int(passes) and passes >= 0 and isinstance(facts, dict)
            and all(_is_int(at) for at in facts.values()))


def load_snapshot(path):
    """Return a validated cached snapshot, or None when it cannot be used."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get('version') != CACHE_VERSION:
        return None
    snapshot = payload.get('snapshot')
    if not _usable(snapshot):
        return None
    restored = {key: snapshot[key] for key in PERSISTED_KEYS if key in snapshot}
    for key, valid in _REPAIRS:
        if key in restored and not valid(restored[key]):
            del restored[key]
    # The name page's cool-down: damage only means facts may repeat sooner.
    if 'name_facts_passes' in restored or 'name_facts_shown' in restored:
        if not _valid_name_facts(restored.get('name_facts_passes'), restored.get('name_facts_shown')):
            restored.pop('name_facts_passes', None)
            restored.pop('name_facts_shown', None)
    return restored


def save_snapshot(path, snapshot):
    """Atomically save the display data with owner-only permissions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.tmp')
    payload = {'version': CACHE_VERSION,
               'snapshot': {key: snapshot[key] for key in PERSISTED_KEYS if key in snapshot}}
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, separators=(',', ':'), allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
