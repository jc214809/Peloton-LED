"""Private, atomic persistence for the last successful dashboard snapshot."""
import json
import os
from pathlib import Path

from .goals import parse_milestone_key


CACHE_VERSION = 1
PERSISTED_KEYS = (
    'me', 'totals', 'summaries', 'last_updated', 'generation',
    'active_day_count', 'celebrated_pr_ids', 'pr_shown_at',
    'weekly_progress', 'celebrated_milestones', 'personal_records', 'streaks',
    'milestone_shown_at', 'celebrated_discipline_milestones', 'discipline_milestone_shown_at',
    'name_facts_passes', 'name_facts_shown',
)


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
    if not isinstance(snapshot, dict):
        return None
    if not isinstance(snapshot.get('summaries'), list) or not isinstance(snapshot.get('totals'), dict):
        return None
    if snapshot.get('me') is not None and not isinstance(snapshot.get('me'), dict):
        return None
    celebrated = snapshot.get('celebrated_pr_ids', [])
    if not isinstance(celebrated, list) or not all(isinstance(value, str) for value in celebrated):
        return None
    milestones = snapshot.get('celebrated_milestones', [])
    if not isinstance(milestones, list) or not all(isinstance(value, int) for value in milestones):
        return None
    progress = snapshot.get('weekly_progress', {})
    if not isinstance(progress, dict):
        return None
    last_updated = snapshot.get('last_updated')
    if isinstance(last_updated, bool) or not isinstance(last_updated, (int, float)):
        return None
    restored = {key: snapshot[key] for key in PERSISTED_KEYS if key in snapshot}
    # A damaged records table only loses PR gains, so drop it, not the cache.
    records = restored.get('personal_records')
    if records is not None and (not isinstance(records, dict) or not all(
            isinstance(r, dict) and isinstance(r.get('workout_id'), str) for r in records.values())):
        del restored['personal_records']
    # Likewise a damaged streaks entry only hides the streak screen.
    streaks = restored.get('streaks')
    if streaks is not None and (not isinstance(streaks, dict) or not all(
            isinstance(v, int) and not isinstance(v, bool) for v in streaks.values())):
        del restored['streaks']
    # A damaged celebration clock only restarts a milestone's day of celebrating.
    shown = restored.get('milestone_shown_at')
    if shown is not None and (not isinstance(shown, dict) or not all(
            key.isdigit() and isinstance(at, (int, float)) and not isinstance(at, bool)
            for key, at in shown.items())):
        del restored['milestone_shown_at']
    # Likewise the PR celebration clock: damage only restarts a PR's day of celebrating.
    shown = restored.get('pr_shown_at')
    if shown is not None and (not isinstance(shown, dict) or not all(
            isinstance(key, str) and isinstance(at, (int, float)) and not isinstance(at, bool)
            for key, at in shown.items())):
        del restored['pr_shown_at']
    # Per-discipline milestones ('strength:500'): damage only means one may celebrate again.
    celebrated = restored.get('celebrated_discipline_milestones')
    if celebrated is not None and (not isinstance(celebrated, list) or not all(
            parse_milestone_key(key) for key in celebrated)):
        del restored['celebrated_discipline_milestones']
    shown = restored.get('discipline_milestone_shown_at')
    if shown is not None and (not isinstance(shown, dict) or not all(
            parse_milestone_key(key) and isinstance(at, (int, float)) and not isinstance(at, bool)
            for key, at in shown.items())):
        del restored['discipline_milestone_shown_at']
    # The name page's cool-down: damage only means facts may repeat sooner.
    passes, facts = restored.get('name_facts_passes'), restored.get('name_facts_shown')
    if 'name_facts_passes' in restored or 'name_facts_shown' in restored:
        if (isinstance(passes, bool) or not isinstance(passes, int) or passes < 0 or not isinstance(facts, dict)
                or not all(isinstance(at, int) and not isinstance(at, bool) for at in facts.values())):
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
