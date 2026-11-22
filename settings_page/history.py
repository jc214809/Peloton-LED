"""Workout compare's history on this board, for the settings page: no HTTP, no HTML.

Each rider's row store (`peloton/workouts/workout_rows.py`, seeded from the Mac by `scripts/push_workout_rows.sh`)
is counted as the display counts it: rows of this ROW_VERSION, of a compared discipline, from the last
BOARD_DAYS. The count is kept until the file changes, so the page doesn't re-read megabytes each load.
It also lists the last RECENT_DAYS' workouts that were saved without all their data (`missing`), so a
failed fetch shows; older rows are left out, since Peloton sent less before and the board has caught up.
"""

import json
import logging
import time
from pathlib import Path

from peloton.config import user_cache_path
from peloton.workouts.workout_rows import DAY, current_board_rows, default_rows_path

log = logging.getLogger(__name__)

# Rider history states, in the words the page uses for them.
MISSING, OLD, READY, UNREADABLE = 'missing', 'old', 'ready', 'unreadable'

# Only workouts this recent are checked for missing data.
RECENT_DAYS = 30
# What a row can be missing, in the words the page uses.
NO_GRAPH, NO_CLASS, NO_MOVEMENTS = 'performance graph', 'class details', 'movement list'

_counted = {}  # path -> ((mtime_ns, size), result)


def missing_data(row):
    """What a row lacks that Peloton should have sent: [] when it's whole. A freestyle workout has no
    class, so no class details or movements; heart rate and the movement tracker depend on the rider."""
    missing = [] if row.get('has_graph') else [NO_GRAPH]
    if row.get('wtype') == 'class':
        if not row.get('ctype'):
            missing.append(NO_CLASS)
        elif row.get('disc') == 'strength' and not row.get('asks'):
            missing.append(NO_MOVEMENTS)
    return missing


def incomplete_workouts(rows, now):
    """[{'id', 'start', 'date', 'disc', 'title', 'missing'}], newest first, of the rows from the last
    RECENT_DAYS that miss data (missing_data)."""
    since = now - RECENT_DAYS * DAY
    found = [
        {
            'id': row['id'],
            'start': row['start'],
            'date': row.get('date'),
            'disc': row.get('disc'),
            'title': row.get('title'),
            'missing': missing_data(row),
        }
        for row in rows
        if row['start'] >= since
    ]
    return sorted((w for w in found if w['missing']), key=lambda w: w['start'], reverse=True)


def rows_paths(config, config_dir, default_token):
    """[(name, row store path)] for each rider, as the display names them (peloton_led.configured_profiles)."""
    users = config.get('users')
    users = [u for u in users if isinstance(u, dict) and isinstance(u.get('name'), str)] if isinstance(users, list) else []
    if users:
        return [(user['name'], default_rows_path(user_cache_path(user, config_dir))) for user in users]
    display = config.get('display') if isinstance(config.get('display'), dict) else {}
    name = display.get('username') if isinstance(display.get('username'), str) and display['username'] else 'This board'
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
        return {'state': MISSING, 'workouts': 0, 'updated': None, 'incomplete': []}
    except OSError:
        return {'state': UNREADABLE, 'workouts': 0, 'updated': None, 'incomplete': []}
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
        result = {'state': UNREADABLE, 'workouts': 0, 'updated': stat.st_mtime, 'incomplete': []}
    else:
        current = current_board_rows(rows, now)
        # Rows of an older ROW_VERSION are ignored on the board: it has no raw files to rebuild them.
        result = {
            'state': READY if current else (OLD if rows else MISSING),
            'workouts': len(current),
            'updated': stat.st_mtime,
            'incomplete': incomplete_workouts(current, now),
        }
    _counted[path] = (stamp, result)
    return result


def rider_histories(config, config_dir, default_token, now=None):
    """[{'name', 'state', 'workouts', 'updated'}] per rider: MISSING (nothing copied yet), OLD (only rows of
    an older ROW_VERSION: copy it again), UNREADABLE, or READY with the number of workouts to compare
    with. updated: the file's time (epoch seconds), which also moves when the board adds a workout.
    incomplete: incomplete_workouts(), the last RECENT_DAYS' workouts saved without all their data."""
    now = time.time() if now is None else now
    histories = []
    for name, path in rows_paths(config, config_dir, default_token):
        counted = _count(Path(path), now)
        # The count is kept until the file changes, so drop what has since aged out of RECENT_DAYS.
        since = now - RECENT_DAYS * DAY
        histories.append({'name': name, **counted, 'incomplete': [w for w in counted['incomplete'] if w['start'] >= since]})
    return histories
