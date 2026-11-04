"""Whether the board is in comitup's Wi-Fi setup hotspot, and the hotspot's name.

LightningLane-Live-LED's board-setup.sh installs comitup on every board, with a callback that
writes "<STATE> <hotspot name>" to STATE_FILE on each change of state: HOTSPOT (no known network
in range, so the setup hotspot is up), CONNECTING or CONNECTED. /run is cleared at boot, so the
file never outlives comitup's run. No comitup, no file: never in setup.
"""
import logging

logger = logging.getLogger('peloton-led.wifi')

STATE_FILE = '/run/comitup-state'
# comitup's hotspot hands out addresses here, and is at HOTSPOT_ADDRESS on it.
HOTSPOT_NETWORK = '10.41.0.0/16'
HOTSPOT_ADDRESS = '10.41.0.1'

_last_problem = None


def hotspot_name(path=STATE_FILE):
    """The setup hotspot's name while it's up, else None (also with no comitup, or a bad file)."""
    global _last_problem
    try:
        with open(path, encoding='utf-8') as f:
            state, _, name = f.read().strip().partition(' ')
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        problem = f"Can't read {path}: {exc}"
        if problem != _last_problem:  # polled every few seconds: say it once
            logger.warning(problem)
            _last_problem = problem
        return None
    _last_problem = None
    if state != 'HOTSPOT':
        return None
    return name.strip() or None
