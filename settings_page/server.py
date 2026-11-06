"""The settings page's web server: python -m settings_page.server, run by the installer's
peloton-settings.service from /opt/peloton-led, as root (it writes config.json, whoever owns it,
and restarts the display).

Its own service, not part of peloton_led.py, so a config.json that stops the display can still be
fixed here, and it runs whether or not the display does. While comitup's Wi-Fi setup hotspot is
up, anyone on it gets the page (they're in the room, with the board); otherwise it asks for the
PIN the board shows (pins.py), which Pushover can also send to a phone when auth.env has its
keys. Changing logins always takes the PIN, hotspot or not.

The Logins card (logins.py) shows each rider's login health, renews on demand and sets the
credentials in auth.env, write-only: nothing secret is ever sent to the browser. The Updates card
(updates.py) checks for, starts and rolls back updates of the checkout the board installs from
(--checkout, the installer's PELOTON_CHECKOUT). Standard library and requests (for Pushover, via
peloton.notify) only.
"""
import argparse
import json
import logging
import os
import shutil
import socket
import subprocess
import threading
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address, ip_network
from urllib.parse import parse_qs, urlsplit

from peloton import notify
from settings_page import logins, page
from settings_page.form import apply_form
from settings_page.pins import PIN_FILE, PIN_SHOWN_S, SESSION_S, PinGate
from settings_page.updates import STARTS, Updates
from utils import wifi_setup

logger = logging.getLogger('peloton-led.settings')

# comitup's own page has port 80 while the hotspot is up; LightningLane-Live-LED's settings page
# also uses 8080, and board-setup.sh turns that off on a board running another app.
PORT = 8080
CONFIG = '/etc/peloton-led/config.json'
AUTH_ENV = '/etc/peloton-led/auth.env'
APP_UNIT = 'peloton-led.service'
RENEW_UNIT = 'peloton-token-refresh.service'
RENEW_TIMER = 'peloton-token-refresh.timer'
PUSHOVER_KEYS = logins.PUSHOVER_KEYS
TEST_ALERT_EVERY_S = 60
MAX_BODY = 64 * 1024
COOKIE = 'peloton_settings'
SYSTEMCTL_TIMEOUT_S = 30
# The checkout to update: the installer's drop-in sets it (this service runs from /opt/peloton-led,
# which has no git); run from a checkout (development), that checkout.
CHECKOUT_ENV = 'PELOTON_CHECKOUT'
CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_checkout(environ=os.environ, code_dir=CODE_DIR):
    """The checkout the Updates card updates, or None (no card): PELOTON_CHECKOUT, else the code's
    own folder when it's a git checkout."""
    found = environ.get(CHECKOUT_ENV) or (code_dir if os.path.isdir(os.path.join(code_dir, '.git')) else None)
    return found if found and os.path.isdir(os.path.join(found, '.git')) else None


def save_config(config, path):
    """Write config.json whole or not at all, keeping the last one as config.json.bak, with the
    old file's owner and mode (the checkout owner's, or root:peloton-led 640), even as root."""
    temp = f'{path}.new'
    try:
        old = os.stat(path)
    except FileNotFoundError:
        old = None
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, old.st_mode & 0o777 if old else 0o640)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    if old:
        try:
            os.chown(temp, old.st_uid, old.st_gid)
        except PermissionError:  # not root (a dev machine): it's ours already
            pass
        shutil.copy2(path, f'{path}.bak')
    os.replace(temp, path)


def read_pushover_keys(path):
    """Only the Pushover keys from auth.env, never the Peloton logins beside them: {name: value}."""
    return {name: value for name, value in logins.read_auth_env(path).items() if name in PUSHOVER_KEYS and value}


class Settings:
    """What the handlers share: where config.json is, the PIN gate, one save at a time, and the
    Updates card's updates.Updates (None: no card)."""

    def __init__(self, config_path=CONFIG, gate=None, restart_unit=APP_UNIT, state_file=wifi_setup.STATE_FILE,
                 send_pushover=notify.send_pushover, auth_env=AUTH_ENV, token_base=None,
                 default_token=logins.DEFAULT_TOKEN, token_mode_file=logins.TOKEN_MODE_FILE,
                 renew_unit=RENEW_UNIT, clock=time.time, updates=None):
        self.updates = updates
        self.config_path, self.restart_unit, self.state_file = config_path, restart_unit, state_file
        self.send_pushover, self.auth_env, self.default_token = send_pushover, auth_env, default_token
        # Where relative token paths start: the folder of the config the display reads (/etc/peloton-led).
        self.token_base = token_base or os.path.dirname(os.path.abspath(config_path))
        self.token_mode_file, self.renew_unit, self.clock = token_mode_file, renew_unit, clock
        self.gate = gate or PinGate()
        self.save_lock = threading.Lock()
        self._last_test = None

    def hotspot(self):
        return wifi_setup.hotspot_name(self.state_file)

    def load(self):
        """config.json, or {} with the reason when it's missing or broken (the page can still fix it)."""
        try:
            with open(self.config_path, encoding='utf-8') as f:
                config = json.load(f)
        except FileNotFoundError:
            return {}, f"{self.config_path} doesn't exist yet: saving makes it."
        except (OSError, ValueError) as exc:
            return {}, f"{self.config_path} can't be read ({exc}): saving replaces it (the old one is kept as .bak)."
        if not isinstance(config, dict):
            return {}, f"{self.config_path} isn't a settings object: saving replaces it (the old one is kept as .bak)."
        return config, None

    def save(self, config):
        save_config(config, self.config_path)

    def _systemctl(self, *args, unit=None):
        """systemctl's CompletedProcess for the display's unit (or unit), or None with no unit set
        or no systemd (a dev machine)."""
        unit = unit or self.restart_unit
        if not unit or not shutil.which('systemctl'):
            return None
        return subprocess.run(['systemctl', *args, unit], capture_output=True, text=True,
                              timeout=SYSTEMCTL_TIMEOUT_S)

    def _unit_properties(self, unit, *names):
        """{property: value} from systemctl show, or {} when there's no telling."""
        if not self.restart_unit:  # no systemd units at all (development)
            return {}
        try:
            done = self._systemctl('show', *(f'--property={n}' for n in names), unit=unit)
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Settings page: can't ask systemd about %s: %s", unit, exc)
            return {}
        if done is None or done.returncode:
            return {}
        return dict(line.partition('=')[::2] for line in done.stdout.splitlines() if '=' in line)

    def display_running(self):
        """Whether the display is running: True, False, or None when there's no telling (no systemd)."""
        try:
            done = self._systemctl('is-active', '--quiet')
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Settings page: can't tell whether %s is running: %s", self.restart_unit, exc)
            return None
        return None if done is None else done.returncode == 0

    def restart_app(self):
        """"restarted"; "not_running" (a manual board with the display off: it reads the new config
        when it starts); "saved" (no systemd: restart it by hand); or "failed" (logged)."""
        running = self.display_running()
        if running is None:
            return 'saved'
        if not running:
            return 'not_running'
        try:
            done = self._systemctl('try-restart')
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.error('Settings page: restarting %s failed: %s', self.restart_unit, exc)
            return 'failed'
        if done.returncode:
            problem = done.stderr.strip() or f'systemctl exited {done.returncode}'
            logger.error('Settings page: restarting %s failed: %s', self.restart_unit, problem)
            return 'failed'
        logger.info('Settings page: restarted %s.', self.restart_unit)
        return 'restarted'

    def phone(self):
        """Whether the sign-in page can send the PIN by Pushover."""
        return notify.pushover_configured()

    # --- logins

    def logins(self):
        """What the Logins card shows (page.logins_card): nothing secret, only whether each is set."""
        config, _ = self.load()
        auth = logins.read_auth_env(self.auth_env)
        renew = self._unit_properties(self.renew_unit, 'ActiveState', 'Result', 'ExecMainExitTimestamp')
        timer = self._unit_properties(RENEW_TIMER, 'ActiveState', 'NextElapseUSecRealtime')
        return {
            'riders': logins.rider_logins(config, self.token_base, auth, self.default_token),
            'mode': logins.token_mode(self.token_mode_file),
            'renewing': renew.get('ActiveState') in ('activating', 'reloading'),
            'last_result': renew.get('Result') if renew.get('ExecMainExitTimestamp') else None,
            'last_run': renew.get('ExecMainExitTimestamp') or None,
            'timer_next': (timer.get('NextElapseUSecRealtime') or None) if timer.get('ActiveState') == 'active'
            else None,
            'alerts': logins.alert_state(self.default_token),
            'pushover': all(auth.get(name) for name in PUSHOVER_KEYS),
            'seed': f'scripts/seed_board.sh {self.checkout_owner()}@{board_name()}.local',
        }

    def checkout_owner(self):
        """Who to seed the board as: the config's owner when that's a person (the checkout's)."""
        try:
            import pwd
            owner = pwd.getpwuid(os.stat(self.config_path).st_uid).pw_name
        except (ImportError, KeyError, OSError):
            return '<user>'
        return owner if owner != 'root' else '<user>'

    def renew(self):
        """Start token renewal now, not waiting for it (it can take minutes with a browser
        login): "renew_started", "renew_running", "renew_failed" (logged) or "renew_unavailable"."""
        if self._unit_properties(self.renew_unit, 'ActiveState').get('ActiveState') in ('activating', 'reloading'):
            return 'renew_running'
        try:
            done = self._systemctl('start', '--no-block', unit=self.renew_unit) if self.restart_unit else None
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.error('Settings page: starting %s failed: %s', self.renew_unit, exc)
            return 'renew_failed'
        if done is None:
            return 'renew_unavailable'
        if done.returncode:
            logger.error('Settings page: starting %s failed: %s', self.renew_unit,
                         done.stderr.strip() or f'systemctl exited {done.returncode}')
            return 'renew_failed'
        logger.info('Settings page: started %s.', self.renew_unit)
        return 'renew_started'

    def test_alert(self):
        """Send a test Pushover alert: "test_sent", "test_wait" (one less than a minute ago),
        "test_failed" (logged by notify) or "test_off" (no keys)."""
        if not self.phone():
            return 'test_off'
        now = self.clock()
        if self._last_test is not None and now - self._last_test < TEST_ALERT_EVERY_S:
            return 'test_wait'
        self._last_test = now
        sent = self.send_pushover(f'{board_name()} test alert',
                                  'Pushover works: token renewal problems will be sent here.')
        return 'test_sent' if sent else 'test_failed'

    def save_credentials(self, form):
        """(outcome, [problems]) for the Logins form: "logins_saved" or "logins_unchanged"."""
        with self.save_lock:
            config, _ = self.load()
            riders = logins.rider_logins(config, self.token_base, {}, self.default_token)
            changes, problems, changed = logins.credential_changes(form, riders)
            if problems:
                return None, problems
            if not changes:
                return 'logins_unchanged', []
            try:
                logins.update_auth_env(self.auth_env, changes)
            except OSError as exc:
                logger.error("Settings page: can't save %s: %s", self.auth_env, exc)
                return None, [f"Couldn't save the logins: {exc}"]
        for name in PUSHOVER_KEYS:  # the PIN and test buttons use the new keys at once
            if name in changes:
                if changes[name]:
                    os.environ[name] = changes[name]
                else:
                    os.environ.pop(name, None)
        logger.info('Settings page: updated %s in %s.', ', '.join(changed), self.auth_env)
        return 'logins_saved', []

    def send_pin(self):
        """The sign-in page's Send button: PinGate.send_pin's outcome, or "off" with no keys."""
        if not self.phone():
            return 'off'
        board = board_name()

        def send(pin, left):
            minutes = max(1, round(left / 60))
            return self.send_pushover(f'{board} settings', f"PIN for {board}'s settings page: {pin}\n"
                                      f"It works for {minutes} minute{'s' if minutes > 1 else ''}.")
        return self.gate.send_pin(send)


class Handler(BaseHTTPRequestHandler):
    settings: Settings  # set on the subclass make_server builds
    timeout = 15  # a client that stalls mid-request doesn't hold a thread

    def log_message(self, fmt, *args):
        logger.debug('Settings page: %s %s', self.address_string(), fmt % args)

    # --- who may see the page

    def _in_setup(self):
        """The hotspot's name while it's up and this browser is on it, else None."""
        name = self.settings.hotspot()
        try:
            on_hotspot = ip_address(self.client_address[0]) in ip_network(wifi_setup.HOTSPOT_NETWORK)
        except ValueError:
            on_hotspot = False
        return name if name and on_hotspot else None

    def _token(self):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
        except cookies.CookieError:
            return None
        return jar[COOKIE].value if COOKIE in jar else None

    def _allowed(self):
        return bool(self._in_setup()) or self._signed_in()

    def _signed_in(self):
        """A PIN session: changing logins takes one, even on the setup hotspot."""
        return self.settings.gate.signed_in(self._token())

    def _same_origin(self):
        """A form posted from another site (a page open in the same browser) is turned away."""
        origin = self.headers.get('Origin')
        return origin is None or urlsplit(origin).netloc.lower() == (self.headers.get('Host') or '').lower()

    # --- responses

    def _send(self, status, html, headers=()):
        body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        # Not no-referrer: with it, browsers send "Origin: null" with the page's own forms, which
        # _same_origin then turns away.
        self.send_header('Referrer-Policy', 'same-origin')
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status, data):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, where, headers=()):
        self.send_response(303)
        self.send_header('Location', where)
        self.send_header('Content-Length', '0')
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()

    def _form(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
        except ValueError:
            length = 0
        if not 0 <= length <= MAX_BODY:
            return None
        return parse_qs(self.rfile.read(length).decode('utf-8', 'replace'), keep_blank_values=True)

    def _page(self, problems=(), saved=None, config=None, login_outcome=None, login_problems=(), started=None):
        loaded, problem = self.settings.load()
        updates = self.settings.updates
        return page.settings_page(config if config is not None else loaded, self._in_setup(), problems, saved,
                                  board_name(), problem, self.settings.logins(), self._signed_in(),
                                  login_outcome, login_problems, updates.view() if updates else None, started)

    # --- routes

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/update/status' and self.settings.updates:  # the page's script, following an update
            if not self._allowed():
                return self._send_json(403, {'running': False, 'phase': None, 'step': None})
            return self._send_json(200, self.settings.updates.status())
        if url.path not in ('/', '/signin'):
            return self._send(404, page.message_page('Not found', "There's nothing at this address."))
        query = parse_qs(url.query, keep_blank_values=True)  # "?wrong", "?shown", "?sent=...", "?signedout"
        if url.path == '/signin' and self._signed_in():
            return self._redirect('/')
        if url.path == '/signin' or not self._allowed():
            sent = query.get('sent', [None])[0]
            return self._send(200, page.pin_page(PIN_SHOWN_S if 'shown' in query else None, 'wrong' in query,
                                                 board_name(), self.settings.phone(),
                                                 sent if sent in page.SENT else None, 'signedout' in query,
                                                 self.settings.display_running() is not False))
        saved = query.get('saved', [None])[0]
        outcome = query.get('logins', [None])[0]
        started = query.get('update', [None])[0]
        self._send(200, self._page(saved=saved if saved in page.SAVED else None,
                                   login_outcome=outcome if outcome in page.LOGIN_OUTCOMES else None,
                                   started=started if started in STARTS else None))

    def do_POST(self):
        path = urlsplit(self.path).path
        if not self._same_origin():
            return self._send(403, page.message_page('Not allowed', 'That form came from another site.'))
        form = self._form()
        if form is None:
            return self._send(413, page.message_page('Too big', "That's too much to save."))
        if path == '/pin/show':
            self.settings.gate.show_pin()
            return self._redirect('/signin?shown')
        if path == '/pin/send':
            outcome = self.settings.send_pin()
            return self._redirect('/signin' if outcome == 'off' else f'/signin?sent={outcome}')
        if path == '/pin':
            token = self.settings.gate.try_pin((form.get('pin') or [''])[0])
            if not token:
                return self._redirect('/signin?wrong')
            return self._redirect('/', [('Set-Cookie', f'{COOKIE}={token}; Max-Age={SESSION_S}; Path=/; '
                                                       f'HttpOnly; SameSite=Strict')])
        if path == '/signout':
            self.settings.gate.sign_out(self._token())
            return self._redirect('/signin?signedout', [('Set-Cookie', f'{COOKIE}=; Max-Age=0; Path=/; '
                                                                       f'HttpOnly; SameSite=Strict')])
        updating = ('/update/check', '/update/start', '/update/rollback') if self.settings.updates else ()
        if path not in ('/save', '/credentials', '/renew', '/alert/test', *updating):
            return self._send(404, page.message_page('Not found', "There's nothing at this address."))
        if not self._allowed():
            return self._redirect('/')
        if path in updating:
            return self._update(path, (form.get('channel') or [''])[0])
        if path == '/renew':
            return self._redirect(f'/?logins={self.settings.renew()}#logins')
        if path == '/alert/test':
            return self._redirect(f'/?logins={self.settings.test_alert()}#logins')
        if path == '/credentials':
            if not self._signed_in():  # the hotspot alone isn't enough to change logins
                return self._redirect('/signin')
            outcome, problems = self.settings.save_credentials(form)
            if problems:
                logger.info('Settings page: logins not saved: %s', '; '.join(problems))
                return self._send(400, self._page(login_problems=problems))
            return self._redirect(f'/?logins={outcome}#logins')
        if self.settings.updates and self.settings.updates.running():
            # A rollback would put back config.json as it was, losing the save.
            loaded, _ = self.settings.load()
            return self._send(409, self._page(["An update is running: save once it's done (see Updates)."],
                                              config=apply_form(loaded, form)[0]))
        with self.settings.save_lock:
            config, _ = self.settings.load()
            new, problems = apply_form(config, form)
            if problems:
                logger.info('Settings page: not saved: %s', '; '.join(problems))
                return self._send(400, self._page(problems, config=new))
            try:
                self.settings.save(new)
            except OSError as exc:
                logger.error("Settings page: can't save %s: %s", self.settings.config_path, exc)
                return self._send(500, self._page([f"Couldn't save: {exc}"], config=new))
        logger.info('Settings page: saved %s (from %s).', self.settings.config_path, self.client_address[0])
        self._redirect(f'/?saved={self.settings.restart_app()}')

    def _update(self, path, channel):
        """POST /update/check, /update/start (channel) and /update/rollback, the Updates card's buttons.
        /update/check asking for JSON is the page's own check as it loads: a fresh one is reused, and
        the answer is {"html": what it found, for the card}."""
        updates = self.settings.updates
        if path == '/update/check' and 'application/json' in (self.headers.get('Accept') or ''):
            updates.auto_check(channel)
            config, _ = self.settings.load()
            zone = page._zone(config.get('display') if isinstance(config.get('display'), dict) else {})
            return self._send_json(200, {'html': page.check_result(updates.view(), zone)})
        if path == '/update/check':
            updates.check(channel)
            return self._redirect('/#updates')
        started = updates.start('update', channel) if path == '/update/start' else updates.start('rollback')
        self._redirect(f'/?update={started}#updates')


def board_name():
    """The board's hostname, for the page's header."""
    return socket.gethostname().split('.')[0]


def make_server(settings, host='', port=PORT):
    handler = type('SettingsHandler', (Handler,), {'settings': settings})
    return ThreadingHTTPServer((host, port), handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="The board's settings page.")
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--host', default='', help='address to listen on (default: all)')
    parser.add_argument('--config', default=CONFIG, help=f'the config.json to edit (default: {CONFIG})')
    parser.add_argument('--auth-env', default=AUTH_ENV,
                        help="the riders' logins and the Pushover keys, set (never shown) on the Logins card")
    parser.add_argument('--token-base', default=None,
                        help="where riders' relative token paths start (default: the config's folder)")
    parser.add_argument('--cookies', default=logins.DEFAULT_TOKEN, help="a single-rider board's token file")
    parser.add_argument('--restart-unit', default=APP_UNIT, help="the display's systemd unit, restarted after a "
                                                                 "save; '' for none")
    parser.add_argument('--pin-file', default=PIN_FILE, help='where the display reads the PIN')
    parser.add_argument('--checkout', default=default_checkout(),
                        help=f'the git checkout the Updates card updates (default: ${CHECKOUT_ENV}, or this '
                             "code's own checkout; none: no Updates card)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    for name, value in read_pushover_keys(args.auth_env).items():
        os.environ.setdefault(name, value)
    settings = Settings(args.config, PinGate(args.pin_file), restart_unit=args.restart_unit,
                        auth_env=args.auth_env, token_base=args.token_base, default_token=args.cookies,
                        updates=Updates(args.checkout) if args.checkout else None)
    server = make_server(settings, args.host, args.port)
    logger.info('Settings page on port %s, for %s.', args.port, os.path.abspath(args.config))
    server.serve_forever()


if __name__ == '__main__':
    main()
