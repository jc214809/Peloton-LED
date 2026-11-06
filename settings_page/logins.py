"""The settings page's Logins card, without HTTP or HTML (server.py and page.py).

Login health: each rider's token, refresh chain, padlock and last browser try, read from the
files token renewal keeps beside each token (scripts/refresh_cookies.py, whose helpers this
uses so the two agree), and nothing over the network. Credentials: the Peloton emails and
passwords and the Pushover keys in auth.env, which the page can set but never shows: only
whether each one is set ever leaves this module.
"""
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from peloton.config import renewal_failed_path, user_token_path
from scripts.refresh_cookies import (ALERT_STATE_NAME, browser_attempt_path, describe_chain, load_refresh_chain,
                                     profile_env_names, refresh_token_path, token_status)

logger = logging.getLogger('peloton-led.settings')

STATE_DIR = '/var/lib/peloton-led'
DEFAULT_TOKEN = f'{STATE_DIR}/cookies.txt'  # a single-rider board's (peloton-led.service's --cookies)
TOKEN_MODE_FILE = '/etc/peloton-led/token-mode'  # the installer's save_token_mode
SINGLE_ENV = ('PELOTON_EMAIL', 'PELOTON_PASSWORD')  # setup_config.py's names for a single rider
PUSHOVER_KEYS = ('PUSHOVER_APP_TOKEN', 'PUSHOVER_USER_KEY')
# What the page says each board's renewal does (the installer's resolve_token_mode).
TOKEN_MODES = ('browser', 'no-browser', 'none')
# How renewal runs, as packaging/systemd's units set it (tests check they agree): the timer checks
# every CHECK_EVERY_S (OnUnitActiveSec=1h), starting up to 10 minutes late (RandomizedDelaySec), and a
# check renews a token only once it's within RENEW_BEFORE_S of expiring (--renew-before-hours 12).
CHECK_EVERY_S = 60 * 60
RENEW_BEFORE_S = 12 * 60 * 60
_EMAIL = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+')
_PUSHOVER = re.compile(r'[A-Za-z0-9]{20,40}')
_ENV_LINE = re.compile(r'\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$')


@dataclass
class RiderLogin:
    key: str  # the form's name for the rider: its index in users, or "default" on a single-rider board
    name: str
    token_path: Path
    email_env: str
    password_env: str
    token: dict  # token_status: ok, expires_at, expired, or reason
    chain: str | None  # describe_chain, or None with no refresh file
    padlock: dict | None  # the renewal-failed marker ({reason, at}) while the display shows the padlock
    browser_attempt: float | None  # when the last fallback browser login started
    email_set: bool
    password_set: bool

    @property
    def healthy(self):
        return self.token.get('ok') and not self.token.get('expired') and not self.padlock


def rider_paths(config, config_dir, default_token=DEFAULT_TOKEN):
    """[(key, name, token path, email variable, password variable)], as the display and token
    renewal find them: users[] with config_dir for relative paths, else the single rider."""
    users = config.get('users')
    users = [u for u in users if isinstance(u, dict) and isinstance(u.get('name'), str)] \
        if isinstance(users, list) else []
    if not users:
        display = config.get('display') if isinstance(config.get('display'), dict) else {}
        name = display.get('username') if isinstance(display.get('username'), str) else 'This board'
        return [('default', name or 'This board', Path(default_token), *SINGLE_ENV)]
    found = []
    for index, user in enumerate(config['users']):
        if user in users:
            found.append((str(index), user['name'], user_token_path(user, config_dir), *profile_env_names(user)))
    return found


def _padlock(token_path):
    """The renewal-failed marker while the display honours it: newer than the token (Dashboard)."""
    marker = renewal_failed_path(token_path)
    try:
        marked = marker.stat().st_mtime_ns
    except OSError:
        return None
    try:
        if token_path.stat().st_mtime_ns > marked:
            return None
    except OSError:
        pass
    try:
        data = json.loads(marker.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    return {'reason': str(data.get('reason') or 'Renewal needs a fresh login.'), 'at': data.get('at')}


def _number_file(path):
    try:
        return float(path.read_text(encoding='utf-8').strip())
    except (OSError, ValueError):
        return None


def rider_logins(config, config_dir, auth, default_token=DEFAULT_TOKEN):
    """Each rider's RiderLogin. auth: read_auth_env's {name: value}, only checked for being set."""
    logins = []
    for key, name, token_path, email_env, password_env in rider_paths(config, config_dir, default_token):
        refresh = refresh_token_path(token_path)
        logins.append(RiderLogin(
            key, name, token_path, email_env, password_env, token_status(token_path),
            describe_chain(load_refresh_chain(refresh)) if refresh.exists() else None,
            _padlock(token_path), _number_file(browser_attempt_path(token_path)),
            bool(auth.get(email_env)), bool(auth.get(password_env))))
    return logins


def alert_state(default_token=DEFAULT_TOKEN):
    """Token renewal's Pushover state (failures in a row, the last failure), or {}."""
    try:
        data = json.loads((Path(default_token).parent / ALERT_STATE_NAME).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def token_mode(path=TOKEN_MODE_FILE):
    """The board's renewal mode as the installer saved it, or None (not installed, or older)."""
    try:
        mode = Path(path).read_text(encoding='utf-8').split()
    except OSError:
        return None
    return mode[0] if mode and mode[0] in TOKEN_MODES else None


# --- auth.env

def _unquote(value):
    """A value as systemd's EnvironmentFile= reads it, for the quoting setup_config.py writes."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
        inner = value[1:-1]
        return re.sub(r'\\(.)', r'\1', inner) if value[0] == '"' else inner
    return value


def _quote(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def read_auth_env(path):
    """auth.env as {name: value}; {} when it's missing (logged when it can't be read). The values
    stay in this process: callers send only whether each is set to a browser."""
    try:
        lines = Path(path).read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError) as exc:
        logger.warning("Settings page: can't read %s: %s", path, exc)
        return {}
    found = {}
    for line in lines:
        match = _ENV_LINE.match(line)
        if match and not line.lstrip().startswith('#'):
            found[match.group(1)] = _unquote(match.group(2))
    return found


def update_auth_env(path, changes):
    """Set ({name: value}) or remove ({name: None}) variables in auth.env, keeping every other
    line as it is. Written whole or not at all, owner-only (root's, 600, as the installer makes
    it); no backup is kept, since that would be a second copy of the passwords."""
    path = Path(path)
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
        old = path.stat()
    except FileNotFoundError:
        lines, old = [], None
    pending = dict(changes)
    kept = []
    for line in lines:
        match = _ENV_LINE.match(line)
        name = match.group(1) if match and not line.lstrip().startswith('#') else None
        if name in pending:
            value = pending.pop(name)
            if value is not None:
                kept.append(f'{name}={_quote(value)}')
        elif name is None or name not in changes:
            kept.append(line)
    kept += [f'{name}={_quote(value)}' for name, value in pending.items() if value is not None]
    temp = path.with_name(f'.{path.name}.new')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write('\n'.join(kept) + ('\n' if kept else ''))
            f.flush()
            os.fsync(f.fileno())
        if old:
            try:
                os.chown(temp, old.st_uid, old.st_gid)
            except PermissionError:  # not root (a dev machine): it's ours already
                pass
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def credential_changes(form, logins):
    """({variable: new value or None to remove}, [problems], [what changed, for the log and the
    page]) from the Logins form. Blank keeps what's saved. Values are checked only for what
    would break auth.env or can't be a login; they never appear in a problem."""
    changes, problems, changed = {}, [], []

    def one(name):
        return (form.get(name) or [''])[0]

    def bad(value):
        return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)

    for login in logins:
        if f'cred_{login.key}_name' in form and one(f'cred_{login.key}_name') != login.name:
            problems.append('The riders in config.json changed since this page loaded: reload it and try again.')
            return {}, problems, []
        email, password = one(f'cred_{login.key}_email').strip(), one(f'cred_{login.key}_password')
        if email:
            if not _EMAIL.fullmatch(email):
                problems.append(f"{login.name}'s email doesn't look like an email address.")
            else:
                changes[login.email_env] = email
                changed.append(f"{login.name}'s email")
        if password:
            if bad(password):
                problems.append(f"{login.name}'s password can't contain line breaks or control characters.")
            else:
                changes[login.password_env] = password
                changed.append(f"{login.name}'s password")
    if one('pushover_clear') == 'on':
        changes.update({name: None for name in PUSHOVER_KEYS})
        changed.append('Pushover keys removed')
    else:
        for name, field, label in ((PUSHOVER_KEYS[0], 'pushover_app_token', 'Pushover app token'),
                                   (PUSHOVER_KEYS[1], 'pushover_user_key', 'Pushover user key')):
            value = one(field).strip()
            if not value:
                continue
            if not _PUSHOVER.fullmatch(value):
                problems.append(f'The {label} should be letters and numbers only, as pushover.net shows it.')
            else:
                changes[name] = value
                changed.append(label)
    return (changes, problems, changed) if not problems else ({}, problems, [])


def renews_at(token, next_check):
    """When renewal will renew this token: the first check once it's within RENEW_BEFORE_S of expiring
    (at once if it already is), counting hourly from next_check (epoch seconds). Without a next check
    (no timer running), from when it becomes due. None when the token has no expiry to go by."""
    expires = token.get('expires_at') if token.get('ok') else None
    if not isinstance(expires, (int, float)) or isinstance(expires, bool):
        return None
    due = expires - RENEW_BEFORE_S
    if not isinstance(next_check, (int, float)) or isinstance(next_check, bool):
        return due
    if due <= next_check:
        return next_check
    return next_check + math.ceil((due - next_check) / CHECK_EVERY_S) * CHECK_EVERY_S


def when(timestamp, zone=None):
    """A time for the page: "Wed Nov 4, 3:05 PM", in the board's zone."""
    try:
        moment = datetime.fromtimestamp(float(timestamp), zone)
    except (TypeError, ValueError, OverflowError, OSError):
        return 'unknown'
    return moment.strftime('%a %b %d, %I:%M %p').replace(' 0', ' ')
