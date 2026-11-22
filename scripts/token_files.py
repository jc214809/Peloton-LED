"""Token-file helpers for refresh_cookies.py: the refresh-token file (and its chain history) and
reading a token's expiry. File reads and writes only, no network; refresh_cookies re-exports every name."""
import base64
import binascii
import json
import math
import os
import re
import tempfile
import time
from datetime import datetime, UTC
from pathlib import Path

from peloton.config import default_token_path

# Peloton's web app (Auth0 SPA) client; the token endpoint renews its sessions.
AUTH0_CLIENT_ID = "WVoJxVDdPoFx4RNewvvg6ch2mZ7bwnsM"


def refresh_token_path(token_path: Path) -> Path:
    """cookies-joel.txt -> cookies-joel.refresh.json, beside the access token."""
    return token_path.with_name(f'{token_path.stem}.refresh.json')


def save_refresh_token(path: Path, refresh_token: str, client_id: str,
                       chain: dict | None = None) -> None:
    """Atomically replace the refresh file, fsynced, owner-only. Auth0 rotates
    refresh tokens on every use, so a lost write would strand the board.

    `chain` carries the login's history forward through rotations (see
    load_refresh_chain); without it, this token starts a new chain."""
    now = datetime.now(UTC).isoformat()
    chain = chain or {'chain_started_at': now, 'chain_start_exact': True, 'renewals': 0}
    payload = json.dumps({'client_id': client_id, 'refresh_token': refresh_token,
                          'saved_at': now, **chain})
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                dir=path.parent, prefix=".peloton-refresh-", delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_refresh_token(path: Path) -> tuple[str, str]:
    """Return (refresh_token, client_id) from a refresh file, or raise RuntimeError."""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot read refresh token file {path}: {exc}") from exc
    refresh_token = data.get('refresh_token') if isinstance(data, dict) else None
    if not isinstance(refresh_token, str) or not refresh_token:
        raise RuntimeError(f"Refresh token file {path} has no refresh_token.")
    client_id = data.get('client_id')
    return refresh_token, client_id if isinstance(client_id, str) and client_id else AUTH0_CLIENT_ID


def load_refresh_chain(path: Path) -> dict:
    """How long this login's refresh chain has lived, to learn Auth0's real
    lifetime: {'chain_started_at', 'chain_start_exact', 'renewals'}. Files written
    before chains were tracked fall back to their last save time, an upper bound
    on the start (so the age is "at least"). Never raises."""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        data = {}
    started = data.get('chain_started_at')
    renewals = data.get('renewals')
    renewals = renewals if isinstance(renewals, int) and not isinstance(renewals, bool) and renewals >= 0 else None
    if isinstance(started, str) and _parse_time(started) is not None:
        return {'chain_started_at': started, 'chain_start_exact': data.get('chain_start_exact') is True,
                'renewals': renewals}
    saved = data.get('saved_at')
    return {'chain_started_at': saved if isinstance(saved, str) and _parse_time(saved) is not None else None,
            'chain_start_exact': False, 'renewals': renewals}


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def describe_chain(chain: dict, now: datetime | None = None) -> str:
    """'refresh chain 3.2 days old, 14 renewals' (or 'at least ...' / 'age unknown')."""
    started = _parse_time(chain.get('chain_started_at') or '')
    if started is None:
        age = 'refresh chain age unknown'
    else:
        days = max(0.0, ((now or datetime.now(UTC)) - started).total_seconds() / 86400)
        age = f"refresh chain {'' if chain.get('chain_start_exact') else 'at least '}{days:.1f} days old"
    renewals = chain.get('renewals')
    if renewals is None:
        return age
    more = '' if chain.get('chain_start_exact') else '+'
    return f"{age}, {renewals}{more} renewal{'' if renewals == 1 and not more else 's'}"


def token_expiration(token_path: Path) -> float | None:
    """Read a JWT expiry as a scheduling hint without treating it as verification."""
    try:
        encoded = token_path.read_text(encoding='utf-8').strip().split('.')[1]
        payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        expiry = payload.get('exp')
        if isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or not math.isfinite(expiry):
            return None
        return float(expiry)
    except (OSError, IndexError, UnicodeError, ValueError, TypeError, binascii.Error):
        return None


def token_status(token_path: Path) -> dict:
    """Diagnose why a token's expiry can't be read, instead of collapsing every
    failure (missing file, no read permission, malformed JWT, no exp claim) into
    one unexplained 'unknown' the way token_expiration() does for schedulers."""
    if not token_path.exists():
        return {'path': str(token_path), 'ok': False, 'reason': 'file does not exist'}
    try:
        raw = token_path.read_text(encoding='utf-8')
    except OSError as exc:
        return {'path': str(token_path), 'ok': False, 'reason': f'cannot read file: {exc}'}
    text = raw.strip()
    if not text:
        return {'path': str(token_path), 'ok': False, 'reason': 'file is empty'}
    parts = text.split('.')
    if len(parts) != 3:
        return {'path': str(token_path), 'ok': False,
                'reason': f'not a 3-part JWT ({len(parts)} dot-separated part(s))'}
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
    except (UnicodeError, ValueError, TypeError, binascii.Error) as exc:
        return {'path': str(token_path), 'ok': False, 'reason': f'JWT payload did not decode: {exc}'}
    expiry = payload.get('exp')
    if isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or not math.isfinite(expiry):
        return {'path': str(token_path), 'ok': False, 'reason': 'JWT payload has no usable exp claim'}
    expiry = float(expiry)
    return {'path': str(token_path), 'ok': True, 'expires_at': expiry,
            'expired': expiry <= time.time()}


def resolve_token_paths(config_path: Path, fallback_token: Path) -> list[tuple[str, Path]]:
    """Map each configured profile name to its token path, the way ensure_all_tokens does,
    so callers don't have to hand-reconstruct default_token_path() to find a file."""
    if not config_path.exists():
        return [('default', fallback_token)]
    config = json.loads(config_path.read_text(encoding='utf-8'))
    users = config.get('users')
    if not isinstance(users, list) or not users:
        return [('default', fallback_token)]
    resolved = []
    for user in users:
        token_path = Path(user.get('token_path') or default_token_path(user['name'])).expanduser()
        if not token_path.is_absolute():
            token_path = config_path.parent / token_path
        resolved.append((user['name'], token_path))
    return resolved


def browser_attempt_path(token_path: Path) -> Path:
    """cookies-joel.txt -> cookies-joel.browser-attempt: when the last fallback login started."""
    return token_path.with_name(f'{token_path.stem}.browser-attempt')


def profile_env_names(user: dict) -> tuple[str, str]:
    suffix = re.sub(r'[^A-Z0-9]+', '_', user['name'].upper()).strip('_') or 'USER'
    return (user.get('email_env') or f'PELOTON_EMAIL_{suffix}',
            user.get('password_env') or f'PELOTON_PASSWORD_{suffix}')
