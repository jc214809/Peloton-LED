"""Pushover alerts for unattended failures, rate-limited through a small state file.

Configured by PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY (on the Pi, in
/etc/peloton-led/auth.env). Without both, alerts are logged and skipped.
"""
import json
import logging
import os
import tempfile
from pathlib import Path

import requests

logger = logging.getLogger('peloton-led.notify')

PUSHOVER_URL = 'https://api.pushover.net/1/messages.json'
PUSHOVER_TIMEOUT_SECONDS = 15
# An unchanged failure is repeated at most this often (the timer runs hourly).
REPEAT_ALERT_SECONDS = 24 * 60 * 60
CONSECUTIVE_FAILURES_TO_ALERT = 2


def pushover_configured() -> bool:
    return bool(os.environ.get('PUSHOVER_APP_TOKEN') and os.environ.get('PUSHOVER_USER_KEY'))


def send_pushover(title: str, message: str) -> bool:
    """Send one Pushover message. Returns True when Pushover accepted it; every
    failure is logged, never raised, so an alert can't break the job it reports on."""
    token = os.environ.get('PUSHOVER_APP_TOKEN')
    user = os.environ.get('PUSHOVER_USER_KEY')
    if not token or not user:
        logger.info('Pushover not configured; alert not sent: %s', title)
        return False
    try:
        response = requests.post(PUSHOVER_URL, timeout=PUSHOVER_TIMEOUT_SECONDS, data={
            'token': token, 'user': user, 'title': title[:250], 'message': message[:1024]})
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('Pushover alert failed: %s', exc)
        return False
    if response.status_code != 200 or not isinstance(body, dict) or body.get('status') != 1:
        errors = body.get('errors') if isinstance(body, dict) else None
        logger.warning('Pushover rejected the alert (HTTP %s): %s', response.status_code, errors)
        return False
    return True


def plan_alert(state: dict, failure: str | None, now: float) -> tuple[tuple[str, str] | None, dict]:
    """Decide what to send for this run's outcome. Returns ((title, message) or
    None, new state).

    A failure alerts on its second run in a row (one Wi-Fi blip shouldn't page
    anyone), or at once for invalid_grant, which never heals by itself; then at
    most once a day while it lasts, whatever its wording (network errors embed
    changing object addresses). The first success after an alert sends one
    recovery notice. `last_alert_at` is only advanced by record_sent()."""
    last_alert = state.get('last_alert_at')
    alerted = isinstance(last_alert, (int, float)) and not isinstance(last_alert, bool)
    if failure is None:
        if not alerted:
            return None, {}
        return ('Peloton token renewal recovered', 'Token renewal is working again.'), {}
    failures = state.get('failures')
    failures = failures + 1 if isinstance(failures, int) and not isinstance(failures, bool) else 1
    new_state = {'failures': failures, 'last_message': failure,
                 'last_alert_at': last_alert if alerted else None}
    if alerted:
        due = now - last_alert >= REPEAT_ALERT_SECONDS
    else:
        due = failures >= CONSECUTIVE_FAILURES_TO_ALERT or 'invalid_grant' in failure
    return (('Peloton token renewal failed', failure) if due else None), new_state


def record_sent(state: dict, now: float) -> dict:
    return {**state, 'last_alert_at': now} if state else state


def load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning('Ignoring unreadable alert state %s: %s', path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: dict) -> None:
    if not state:
        path.unlink(missing_ok=True)
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.peloton-alert-', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(state, handle)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def report_outcome(state_path: Path, failure: str | None, now: float, source: str = '') -> None:
    """Alert on a failed or recovered run, rate-limited by the state file. Never raises."""
    try:
        state = load_state(state_path)
        alert, new_state = plan_alert(state, failure, now)
        if alert is not None:
            title, message = alert
            if send_pushover(title, f'{source}: {message}' if source else message):
                new_state = record_sent(new_state, now)
            elif failure is None:
                # Keep the failure on record so the recovery notice is retried.
                new_state = state
        if new_state != state:
            save_state(state_path, new_state)
    except Exception:
        logger.exception('Could not process the renewal alert for %s', state_path)
