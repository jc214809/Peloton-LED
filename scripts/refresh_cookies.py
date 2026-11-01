#!/usr/bin/env python3
"""Fetch a fresh Peloton Auth0 access token and write it to cookies.txt.

Peloton no longer issues peloton_session_id cookies — auth is now Bearer token
(Auth0 JWT stored in localStorage by the members app). A browser login extracts
the access token plus Auth0's refresh token, saved beside it as
<token stem>.refresh.json. After that, --ensure renews with the refresh token
over plain HTTPS, so boards too small for Chromium never need a browser.

Refresh tokens rotate and are single-use: each board needs its own login
(--seed-dir on another computer), never a copy of another machine's file.

Email and password are read from config.json (auth.email / auth.password),
the PELOTON_EMAIL / PELOTON_PASSWORD env vars, or prompted interactively.

Usage:
    python scripts/refresh_cookies.py
    python scripts/refresh_cookies.py --cookies path/to/cookies.txt --config path/to/config.json
    python scripts/refresh_cookies.py --verify-only
    python scripts/refresh_cookies.py --ensure
    python scripts/refresh_cookies.py --status --all-users
    python scripts/refresh_cookies.py --seed-dir ~/peloton-seed-pelotonpi
"""
import argparse
import base64
import binascii
import getpass
import importlib.util
import json
import math
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from peloton.api import make_session
from peloton.config import default_token_path, load_dotenv

LOGIN_URL = "https://www.onepeloton.com/login"
# Generous limits: a Pi Zero 2 W takes minutes to load the members app.
FORM_TIMEOUT_MS = 120_000
TOKEN_TIMEOUT_MS = 180_000
# Peloton's web app (Auth0 SPA) client; the token endpoint renews its sessions.
AUTH0_TOKEN_URL = "https://auth.onepeloton.com/oauth/token"
AUTH0_CLIENT_ID = "WVoJxVDdPoFx4RNewvvg6ch2mZ7bwnsM"
REFRESH_TIMEOUT_SECONDS = 30


class RefreshTokenRejected(RuntimeError):
    """Auth0 refused the refresh token (invalid_grant): the chain is dead and only
    a fresh login can replace it. Retrying, or opening a browser, won't help."""


def _dump_failure_diagnostics(page, token_path: Path) -> str:
    """Best-effort screenshot + HTML dump next to the token file, for debugging
    a headless login failure with no way to watch the browser directly. Never
    raises — a failed dump must not hide the real login error."""
    try:
        screenshot_path = token_path.with_name(f'{token_path.stem}-login-failure.png')
        html_path = token_path.with_name(f'{token_path.stem}-login-failure.html')
        page.screenshot(path=str(screenshot_path), full_page=True)
        html_path.write_text(page.content(), encoding='utf-8')
        return f' Diagnostics saved to {screenshot_path} and {html_path}.'
    except Exception:
        return ''


def browser_login(email: str, password: str, token_path: Path, headless: bool = True) -> str:
    """Drive a browser through Peloton login; save the refresh token, then the access token."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        executable = os.environ.get("PELOTON_CHROMIUM_EXECUTABLE")
        launch_options = {'headless': headless}
        if executable:
            launch_options['executable_path'] = executable
        browser = p.chromium.launch(**launch_options)
        # A bare new_context() has no viewport/locale/timezone at all, which
        # looks nothing like a real desktop visit and is an easy bot-detection
        # signal; a plausible desktop context reduces false positives without
        # pretending to be a specific Chrome version (which just goes stale).
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/New_York',
        )
        page = context.new_page()

        print(f"Opening {LOGIN_URL}...")
        try:
            # Wait for the form itself, not "networkidle": the members app keeps
            # the network busy, and a slow Pi never sees it go quiet.
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=FORM_TIMEOUT_MS)
            page.locator("#usernameOrEmail").fill(email, timeout=FORM_TIMEOUT_MS)
            page.locator("#password").fill(password, timeout=FORM_TIMEOUT_MS)
            page.locator("[data-test-id='loginButton']").click(timeout=FORM_TIMEOUT_MS)
        except Exception as exc:
            location = urlsplit(page.url)
            diagnostics = _dump_failure_diagnostics(page, token_path)
            browser.close()
            raise RuntimeError(
                "Could not reach or fill in the login form; browser was at "
                f"{location.hostname}{location.path}: {exc}.{diagnostics}"
            ) from exc

        try:
            # Successful login can land on pages other than /home. Wait for
            # the credential we need instead of assuming a redirect path.
            token_handle = page.wait_for_function(
                """() => {
                    if (location.hostname !== 'members.onepeloton.com') return false;
                    for (const key of Object.keys(localStorage)) {
                        if (!key.includes('openid')) continue;
                        try {
                            const body = JSON.parse(localStorage.getItem(key))?.body;
                            if (typeof body?.access_token === 'string' && body.access_token) {
                                return {access_token: body.access_token,
                                        refresh_token: body.refresh_token ?? null,
                                        client_id: body.client_id ?? null};
                            }
                        } catch (_) {}
                    }
                    return false;
                }""",
                timeout=TOKEN_TIMEOUT_MS,
            )
            credentials = token_handle.json_value()
        except Exception as exc:
            location = urlsplit(page.url)
            diagnostics = _dump_failure_diagnostics(page, token_path)
            raise RuntimeError(
                "No access token found after login; browser reached "
                f"{location.hostname}{location.path}. The existing token was not changed.{diagnostics}"
            ) from exc
        finally:
            browser.close()

    refresh_token = credentials.get('refresh_token')
    if isinstance(refresh_token, str) and refresh_token:
        client_id = credentials.get('client_id')
        save_refresh_token(refresh_token_path(token_path), refresh_token,
                           client_id if isinstance(client_id, str) and client_id else AUTH0_CLIENT_ID)
    else:
        print(f"Warning: login returned no refresh token; {token_path} will need "
              "another browser login when it expires.", file=sys.stderr)
    return save_verified_token(credentials['access_token'], token_path)


def refresh_token_path(token_path: Path) -> Path:
    """cookies-joel.txt -> cookies-joel.refresh.json, beside the access token."""
    return token_path.with_name(f'{token_path.stem}.refresh.json')


def save_refresh_token(path: Path, refresh_token: str, client_id: str) -> None:
    """Atomically replace the refresh file, fsynced, owner-only. Auth0 rotates
    refresh tokens on every use, so a lost write would strand the board."""
    payload = json.dumps({'client_id': client_id, 'refresh_token': refresh_token,
                          'saved_at': datetime.now(timezone.utc).isoformat()})
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


def renew_with_refresh_token(token_path: Path) -> str:
    """Trade the saved refresh token for a new access token without a browser.

    The rotated refresh token is persisted before anything else, since the old
    one stops working the moment Auth0 answers. The access token is then
    verified and swapped in like a browser login's. Any failure leaves the
    current access token in place."""
    refresh_path = refresh_token_path(token_path)
    refresh_token, client_id = load_refresh_token(refresh_path)
    response = requests.post(AUTH0_TOKEN_URL, timeout=REFRESH_TIMEOUT_SECONDS, json={
        'grant_type': 'refresh_token', 'client_id': client_id, 'refresh_token': refresh_token})
    try:
        data = response.json()
    except ValueError:
        data = None
    if 400 <= response.status_code < 500:
        error = data.get('error') if isinstance(data, dict) else None
        if error == 'invalid_grant':
            raise RefreshTokenRejected(
                f"Peloton rejected the refresh token in {refresh_path} (invalid_grant); "
                "the existing token was not changed. Seed this board again from another "
                "computer: refresh_cookies.py --seed-dir.")
        raise RuntimeError(f"Token endpoint returned HTTP {response.status_code}"
                           f"{f' ({error})' if error else ''}; the existing token was not changed.")
    response.raise_for_status()
    if not isinstance(data, dict):
        raise RuntimeError("Token endpoint returned a non-JSON response; the existing token was not changed.")
    new_refresh = data.get('refresh_token')
    if isinstance(new_refresh, str) and new_refresh:
        save_refresh_token(refresh_path, new_refresh, client_id)
    access_token = data.get('access_token')
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Token endpoint response had no access_token; the existing token was not changed.")
    return save_verified_token(access_token, token_path)


def browser_login_available() -> bool:
    """Playwright is installed and the configured Chromium, if any, exists."""
    if importlib.util.find_spec('playwright') is None:
        return False
    executable = os.environ.get("PELOTON_CHROMIUM_EXECUTABLE")
    return not executable or Path(executable).exists()


def save_verified_token(token: str, token_path: Path) -> str:
    """Verify first; atomically replace the old token using an owner-only file."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                dir=token_path.parent, prefix=".peloton-token-", delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(token)
        username = verify_token(temporary)
        os.replace(temporary, token_path)
        return username
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def verify_token(token_path: Path) -> str:
    """Call /api/me with the saved token and return the username."""
    session = make_session(token_path)
    try:
        resp = session.get("https://api.onepeloton.com/api/me", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("username") or data.get("email") or data.get("id") or "unknown"
    finally:
        session.close()


def load_auth(config_path: Path, interactive: bool = True) -> tuple[str, str]:
    config: dict = {}
    if config_path.exists():
        with config_path.open(encoding="utf-8") as handle:
            config = json.load(handle)
    auth_config = config.get("auth", {})
    email = os.environ.get("PELOTON_EMAIL") or auth_config.get("email") or ""
    password = os.environ.get("PELOTON_PASSWORD") or auth_config.get("password") or ""
    if interactive and not email:
        email = input("Peloton email: ").strip()
    if interactive and not password and email:
        password = getpass.getpass(f"Peloton password for {email}: ")
    return email, password


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


def ensure_token(token_path: Path, config_path: Path, headless: bool = True,
                 renew_before_seconds: float = 12 * 60 * 60,
                 email: str | None = None, password: str | None = None,
                 load_credentials: bool = True) -> tuple[str, bool]:
    """Refresh a rejected token or a valid JWT nearing expiration.

    With a saved refresh token, renewal never opens a browser, even when Auth0
    rejects it: a slow board would only fail the same login every hour. The
    browser is the fallback for tokens that have no refresh file yet."""
    try:
        username = verify_token(token_path)
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 401:
            raise
    except (FileNotFoundError, ValueError):
        # No token file yet (first run) or an empty one: treat like a
        # rejected token and log in fresh, rather than crashing.
        pass
    else:
        expiry = token_expiration(token_path)
        if expiry is None or expiry - time.time() > renew_before_seconds:
            return username, False
    refresh_path = refresh_token_path(token_path)
    if refresh_path.exists():
        return renew_with_refresh_token(token_path), True
    if not browser_login_available():
        raise RuntimeError(
            f"Token needs renewal, but there is no refresh token at {refresh_path} and no "
            "browser login on this machine. Seed this board from another computer: "
            "refresh_cookies.py --seed-dir.")
    if load_credentials and (not email or not password):
        email, password = load_auth(config_path, interactive=False)
    if not email or not password:
        raise RuntimeError("Token needs renewal, but unattended Peloton credentials are not configured.")
    return browser_login(email, password, token_path, headless=headless), True


def profile_env_names(user: dict) -> tuple[str, str]:
    suffix = re.sub(r'[^A-Z0-9]+', '_', user['name'].upper()).strip('_') or 'USER'
    return (user.get('email_env') or f'PELOTON_EMAIL_{suffix}',
            user.get('password_env') or f'PELOTON_PASSWORD_{suffix}')


def ensure_all_tokens(config_path: Path, renew_before_seconds: float = 12 * 60 * 60,
                      fallback_token: Path | None = None):
    """Verify/renew every configured user's token and return result tuples."""
    config = json.loads(config_path.read_text(encoding='utf-8'))
    users = config.get('users')
    if not isinstance(users, list) or not users:
        token_path = fallback_token or Path('cookies.txt')
        username, refreshed = ensure_token(token_path, config_path, headless=True,
            renew_before_seconds=renew_before_seconds)
        return [('default', username, refreshed)]
    results = []
    failures = []
    for user in users:
        token_path = Path(user.get('token_path') or default_token_path(user['name'])).expanduser()
        if not token_path.is_absolute():
            token_path = config_path.parent / token_path
        email_env, password_env = profile_env_names(user)
        try:
            username, refreshed = ensure_token(token_path, config_path, headless=True,
                renew_before_seconds=renew_before_seconds,
                email=os.environ.get(email_env), password=os.environ.get(password_env),
                load_credentials=False)
            results.append((user['name'], username, refreshed))
        except Exception as exc:
            failures.append(f"{user['name']}: {exc}")
    if failures:
        raise RuntimeError('Token maintenance failed for ' + '; '.join(failures))
    return results


def seed_tokens(seed_dir: Path, config_path: Path, headless: bool = True) -> list[tuple[str, Path]]:
    """Log every configured rider in fresh and write each token + refresh pair into
    seed_dir under the board's file names, ready to copy to exactly one board."""
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    users = config.get('users')
    riders = []
    if isinstance(users, list) and users:
        for user in users:
            email_env, password_env = profile_env_names(user)
            token_name = Path(user.get('token_path') or default_token_path(user['name'])).name
            riders.append((user['name'], token_name,
                           os.environ.get(email_env), os.environ.get(password_env)))
    else:
        email, password = load_auth(config_path, interactive=False)
        riders.append(('default', 'cookies.txt', email, password))
    seed_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    seeded = []
    for name, token_name, email, password in riders:
        email = email or input(f"Peloton email for {name}: ").strip()
        password = password or getpass.getpass(f"Peloton password for {email}: ")
        if not email or not password:
            raise RuntimeError(f"No credentials for {name}.")
        token_path = seed_dir / token_name
        print(f"{name}: logging in...")
        username = browser_login(email, password, token_path, headless=headless)
        if not refresh_token_path(token_path).exists():
            raise RuntimeError(f"{name}: login gave no refresh token, so this board couldn't renew it.")
        print(f"{name}: seeded {token_path.name} + {refresh_token_path(token_path).name} "
              f"(logged in as {username})")
        seeded.append((name, token_path))
    return seeded


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Refresh Peloton access token via browser login.")
    parser.add_argument("--cookies", default="cookies.txt", help="Output token file path (default: cookies.txt)")
    parser.add_argument("--config", default="config.json", help="Config file path (default: config.json)")
    parser.add_argument("--verify-only", action="store_true", help="Skip login; just verify the existing token.")
    parser.add_argument("--status", action="store_true",
                        help="Report each token's path, readability, and expiry without any network calls.")
    parser.add_argument("--ensure", action="store_true",
                        help="Refresh headlessly after HTTP 401 or shortly before JWT expiration.")
    parser.add_argument("--all-users", action="store_true",
                        help="With --ensure or --status, cover every user token configured in config.json.")
    parser.add_argument("--renew-before-hours", type=float, default=12,
                        help="With --ensure, renew this many hours before expiry (default: 12).")
    parser.add_argument("--seed-dir", metavar="DIR",
                        help="Log in every rider in --config and write fresh token + refresh-token "
                             "files into DIR, for copying to one board.")
    parser.add_argument("--no-install-hint", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-headless", action="store_true", help="Show the browser window during login.")
    parsed = parser.parse_args()
    if parsed.seed_dir and (parsed.ensure or parsed.verify_only or parsed.status or parsed.all_users):
        parser.error("--seed-dir cannot be combined with --ensure, --verify-only, --status, or --all-users")
    if parsed.ensure and parsed.verify_only:
        parser.error("--ensure and --verify-only cannot be combined")
    if parsed.status and (parsed.ensure or parsed.verify_only):
        parser.error("--status cannot be combined with --ensure or --verify-only")
    if parsed.all_users and not (parsed.ensure or parsed.status):
        parser.error("--all-users requires --ensure or --status")
    if not math.isfinite(parsed.renew_before_hours) or parsed.renew_before_hours < 0:
        parser.error("--renew-before-hours must be a non-negative number")

    token_path = Path(parsed.cookies)

    if parsed.status:
        config_path = Path(parsed.config)
        profiles = (resolve_token_paths(config_path, token_path) if parsed.all_users
                    else [('default', token_path)])
        for name, path in profiles:
            status = token_status(path)
            if not status['ok']:
                print(f"{name}: {status['path']} — {status['reason']}")
                continue
            expires_at = datetime.fromtimestamp(status['expires_at'], tz=timezone.utc)
            state = 'EXPIRED' if status['expired'] else 'valid'
            renewal = ('refresh token saved' if refresh_token_path(path).exists()
                       else 'no refresh token (renewal needs a browser login)')
            print(f"{name}: {status['path']} — {state}, expires {expires_at.isoformat()}; {renewal}")
        return

    if parsed.seed_dir:
        seed_dir = Path(parsed.seed_dir).expanduser()
        try:
            seeded = seed_tokens(seed_dir, Path(parsed.config), headless=not parsed.no_headless)
        except Exception as exc:
            sys.exit(f"Seeding failed: {exc}")
        if parsed.no_install_hint:  # scripts/seed_board.sh installs them itself.
            return
        names = ' '.join(name for _, token in seeded
                         for name in (token.name, refresh_token_path(token).name))
        print(f"""
Seeded {seed_dir}. These files work on ONE board only: refresh tokens rotate, so
a second machine using the same files breaks both. Install them, then delete {seed_dir}:

  cd {seed_dir} && scp {names} <board>:/tmp/
  ssh <board> 'cd /tmp && sudo install -m 0600 -o peloton-led -g peloton-led {names} /var/lib/peloton-led/ && rm -f {names}'
""")
        return

    if parsed.verify_only:
        print(f"Verifying existing token in {token_path}...")
        try:
            username = verify_token(token_path)
        except Exception as exc:
            sys.exit(f"Token verification failed: {exc}")
        print(f"Token is valid — logged in as: {username}")
        return

    config_path = Path(parsed.config)
    if parsed.ensure:
        try:
            if parsed.all_users:
                results = ensure_all_tokens(config_path,
                    renew_before_seconds=parsed.renew_before_hours * 60 * 60,
                    fallback_token=token_path)
                for profile, username, refreshed in results:
                    action = "refreshed" if refreshed else "already valid"
                    print(f"{profile}: token {action} — logged in as: {username}")
                return
            username, refreshed = ensure_token(token_path, config_path, headless=True,
                renew_before_seconds=parsed.renew_before_hours * 60 * 60)
        except Exception as exc:
            sys.exit(f"Token maintenance failed: {exc}")
        action = "refreshed" if refreshed else "already valid"
        print(f"Token {action} — logged in as: {username}")
        return

    email, password = load_auth(config_path)
    if not email:
        sys.exit("Error: no email provided.")
    if not password:
        sys.exit("Error: no password provided.")

    print("Logging in...")
    try:
        username = browser_login(email, password, token_path, headless=not parsed.no_headless)
    except Exception as exc:
        sys.exit(str(exc))

    print(f"Token saved to {token_path}")

    print(f"Token verified — logged in as: {username}")


if __name__ == "__main__":
    main()
