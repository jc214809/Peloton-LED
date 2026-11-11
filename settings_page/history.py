"""Workout compare's history on this board, for the settings page: no HTTP, no HTML.

Each rider's row store (`peloton/workout_rows.py`, seeded from the Mac by `scripts/push_workout_rows.sh`)
is counted as the display counts it: rows of this ROW_VERSION, of a compared discipline, from the last
BOARD_DAYS. The count is kept until the file changes, so the page doesn't re-read megabytes each load.
"""
import json
import logging
import time
from pathlib import Path

from peloton.config import user_cache_path
from peloton.workout_rows import current_board_rows, default_rows_path

log = logging.getLogger(__name__)

# Rider history states, in the words the page uses for them.
MISSING, OLD, READY, UNREADABLE = 'missing', 'old', 'ready', 'unreadable'

_counted = {}  # path -> ((mtime_ns, size), result)


def rows_paths(config, config_dir, default_token):
    """[(name, row store path)] for each rider, as the display names them (peloton_led.configured_profiles)."""
    users = config.get('users')
    users = [u for u in users if isinstance(u, dict) and isinstance(u.get('name'), str)] \
        if isinstance(users, list) else []
    if users:
        return [(user['name'], default_rows_path(user_cache_path(user, config_dir))) for user in users]
    display = config.get('display') if isinstance(config.get('display'), dict) else {}
    name = display.get('username') if isinstance(display.get('username'), str) and display['username'] \
        else 'This board'
    configured = display.get('cache_path')
    if isinstance(configured, str) and configured:
        cache = Path(configured).expanduser()
        cache = cache if cache.is_absolute() else Path(config_dir) / cache
    else:
        cache = Path(default_token).with_name('dashboard-cache.json')
    return [(name, default_rows_path(cache))]


def _count(path, now):
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {'state': MISSING, 'workouts': 0, 'updated': None}
    except OSError:
        return {'state': UNREADABLE, 'workouts': 0, 'updated': None}
    stamp = (stat.st_mtime_ns, stat.st_size)
    cached = _counted.get(path)
    if cached and cached[0] == stamp:
        return cached[1]
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        rows = payload['rows'] if isinstance(payload, dict) and isinstance(payload.get('rows'), dict) else None
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        log.warning('Could not read workout history %s (%s)', path, type(exc).__name__)
        rows = None
    if rows is None:
        result = {'state': UNREADABLE, 'workouts': 0, 'updated': stat.st_mtime}
    else:
        workouts = len(current_board_rows(rows, now))
        # Rows of an older ROW_VERSION are ignored on the board: it has no raw files to rebuild them.
        result = {'state': READY if workouts else (OLD if rows else MISSING), 'workouts': workouts,
                  'updated': stat.st_mtime}
    _counted[path] = (stamp, result)
    return result


def rider_histories(config, config_dir, default_token, now=None):
    """[{'name', 'state', 'workouts', 'updated'}] per rider: MISSING (nothing copied yet), OLD (only rows of
    an older ROW_VERSION: copy it again), UNREADABLE, or READY with the number of workouts to compare
    with. updated: the file's time (epoch seconds), which also moves when the board adds a workout."""
    now = time.time() if now is None else now
    return [{'name': name, **_count(Path(path), now)}
            for name, path in rows_paths(config, config_dir, default_token)]

