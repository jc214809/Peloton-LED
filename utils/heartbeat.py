"""The display's heartbeat, for the updater (self_update): HEARTBEAT_FILE holds JSON with when the
display last finished a screen ("at", epoch seconds) and its pid.

systemd's Restart=on-failure hides a crash loop, so an update counts as healthy only once the new
display has written a heartbeat since it was restarted. Its folder is peloton-led.service's
RuntimeDirectory (root:peloton-led, group-writable, so the display can still write after dropping
root), made when the display starts and removed when it stops, so a heartbeat never outlives the
display's run. Without the folder (a dev machine, the emulator) nothing is written. Written
atomically (a temp file renamed over it) and never raises: a board that can't write it only fails
its health check.
"""
import json
import logging
import os
import time

logger = logging.getLogger('peloton-led.heartbeat')

HEARTBEAT_FILE = '/run/peloton-led/health'

_last_problem = None


def beat(path=None, clock=time.time):
    """Say the display is alive now. Returns whether it wrote the heartbeat."""
    global _last_problem
    path = path or HEARTBEAT_FILE
    if not os.path.isdir(os.path.dirname(path)):
        return False
    temp = f'{path}.{os.getpid()}.new'
    try:
        with open(temp, 'w', encoding='utf-8') as f:
            json.dump({'at': clock(), 'pid': os.getpid()}, f)
        os.replace(temp, path)
    except OSError as exc:
        problem = f"Can't write the heartbeat {path}: {exc}"
        if problem != _last_problem:  # written every screen: say it once
            logger.warning(problem)
        _last_problem = problem
        return False
    _last_problem = None
    return True


def read(path=None):
    """The last heartbeat as a dict, or None (none yet, or unreadable)."""
    try:
        with open(path or HEARTBEAT_FILE, encoding='utf-8') as f:
            found = json.load(f)
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) and isinstance(found.get('at'), (int, float)) else None
