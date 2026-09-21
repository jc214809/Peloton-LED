#!/usr/bin/env python3
"""Fetch a fresh Peloton Auth0 access token via browser automation and write it to cookies.txt.

Peloton no longer issues peloton_session_id cookies — auth is now Bearer token
(Auth0 JWT stored in localStorage by the members app). This script logs in
through the website, extracts the access token, and saves it so the main app
can use it for API calls.

Email and password are read from config.json (auth.email / auth.password),
the PELOTON_EMAIL / PELOTON_PASSWORD env vars, or prompted interactively.

Usage:
    python scripts/refresh_cookies.py
    python scripts/refresh_cookies.py --cookies path/to/cookies.txt --config path/to/config.json
    python scripts/refresh_cookies.py --verify-only
    python scripts/refresh_cookies.py --ensure
"""
import argparse
import base64
import binascii
import getpass
import json
import math
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from peloton.api import make_session
from peloton.config import default_token_path, load_dotenv

LOGIN_URL = "https://www.onepeloton.com/login"


def browser_login(email: str, password: str, token_path: Path, headless: bool = True) -> str:
    """Drive a browser through Peloton login and save the Auth0 access token."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        executable = os.environ.get("PELOTON_CHROMIUM_EXECUTABLE")
        launch_options = {'headless': headless}
        if executable:
            launch_options['executable_path'] = executable
        browser = p.chromium.launch(**launch_options)
        context = browser.new_context()
        page = context.new_page()

        print(f"Opening {LOGIN_URL}...")
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
        page.locator("#usernameOrEmail").fill(email)
        page.locator("#password").fill(password)
        page.locator("[data-test-id='loginButton']").click()

        try:
            # Successful login can land on pages other than /home. Wait for
            # the credential we need instead of assuming a redirect path.
            token_handle = page.wait_for_function(
                """() => {
                    if (location.hostname !== 'members.onepeloton.com') return false;
                    for (const key of Object.keys(localStorage)) {
                        if (!key.includes('openid')) continue;
                        try {
                            const token = JSON.parse(localStorage.getItem(key))?.body?.access_token;
                            if (typeof token === 'string' && token) return token;
                        } catch (_) {}
                    }
                    return false;
                }""",
                timeout=60_000,
            )
            access_token = token_handle.json_value()
        except Exception as exc:
            location = urlsplit(page.url)
            raise RuntimeError(
                "No access token found after login; browser reached "
                f"{location.hostname}{location.path}. The existing token was not changed."
            ) from exc
        finally:
            browser.close()

    return save_verified_token(access_token, token_path)


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


def ensure_token(token_path: Path, config_path: Path, headless: bool = True,
                 renew_before_seconds: float = 12 * 60 * 60,
                 email: str | None = None, password: str | None = None,
                 load_credentials: bool = True) -> tuple[str, bool]:
    """Refresh a rejected token or a valid JWT nearing expiration."""
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
            failures.append(f"{user['name']}: {type(exc).__name__}")
    if failures:
        raise RuntimeError('Token maintenance failed for ' + ', '.join(failures))
    return results


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Refresh Peloton access token via browser login.")
    parser.add_argument("--cookies", default="cookies.txt", help="Output token file path (default: cookies.txt)")
    parser.add_argument("--config", default="config.json", help="Config file path (default: config.json)")
    parser.add_argument("--verify-only", action="store_true", help="Skip login; just verify the existing token.")
    parser.add_argument("--ensure", action="store_true",
                        help="Refresh headlessly after HTTP 401 or shortly before JWT expiration.")
    parser.add_argument("--all-users", action="store_true",
                        help="With --ensure, maintain every user token configured in config.json.")
    parser.add_argument("--renew-before-hours", type=float, default=12,
                        help="With --ensure, renew this many hours before expiry (default: 12).")
    parser.add_argument("--no-headless", action="store_true", help="Show the browser window during login.")
    parsed = parser.parse_args()
    if parsed.ensure and parsed.verify_only:
        parser.error("--ensure and --verify-only cannot be combined")
    if parsed.all_users and not parsed.ensure:
        parser.error("--all-users requires --ensure")
    if not math.isfinite(parsed.renew_before_hours) or parsed.renew_before_hours < 0:
        parser.error("--renew-before-hours must be a non-negative number")

    token_path = Path(parsed.cookies)

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
