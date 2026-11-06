"""The settings server over real HTTP on a free port, with config.json, the PIN file and comitup's
state in a temp folder; systemctl and Pushover are faked."""
import json
import os
from html import unescape
import subprocess
import threading
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

import settings_page.server as server
from settings_page.pins import PinGate
from settings_page.server import Settings, make_server, read_pushover_keys, save_config
from tests.test_settings_form import TWO_RIDERS, posted


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Board:
    def __init__(self, tmp_path, monkeypatch, config=TWO_RIDERS):
        self.config = tmp_path / 'config.json'
        self.config.write_text(json.dumps(config))
        os.chmod(self.config, 0o640)
        self.state = tmp_path / 'comitup-state'
        self.gate = PinGate(str(tmp_path / 'pin'))
        self.restarts, self.sent = [], []
        self.running = True
        self.auth_env = tmp_path / 'auth.env'
        self.settings = Settings(str(self.config), self.gate, state_file=str(self.state),
                                 send_pushover=lambda title, message: self.sent.append((title, message)) or True,
                                 auth_env=str(self.auth_env), default_token=str(tmp_path / 'cookies.txt'),
                                 token_mode_file=str(tmp_path / 'token-mode'))
        self.units = {}  # systemctl show answers, by unit
        monkeypatch.setattr(self.settings, '_unit_properties', lambda unit, *names: self.units.get(unit, {}))
        monkeypatch.setattr(self.settings, 'restart_app', lambda: self.restarts.append(1) or 'restarted')
        monkeypatch.setattr(self.settings, 'display_running', lambda: self.running)
        monkeypatch.delenv('PUSHOVER_APP_TOKEN', raising=False)
        monkeypatch.delenv('PUSHOVER_USER_KEY', raising=False)
        self.monkeypatch = monkeypatch
        self.httpd = make_server(self.settings, '127.0.0.1', 0)
        self.url = f'http://127.0.0.1:{self.httpd.server_address[1]}'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirect)

    def hotspot(self, client_on_it=True):
        """comitup's hotspot is up, and this test's browser (127.0.0.1) counts as on it or not."""
        self.state.write_text('HOTSPOT PelotonPi-setup\n')
        if client_on_it:
            self.monkeypatch.setattr(server.wifi_setup, 'HOTSPOT_NETWORK', '127.0.0.0/8')

    def request(self, path, form=None, headers=None):
        data = urlencode(form, doseq=True).encode() if form is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers=headers or {})
        try:
            with self.opener.open(req, timeout=5) as response:
                return response.status, dict(response.headers), unescape(response.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), unescape(e.read().decode())

    def sign_in(self):
        self.request('/pin/show', {})
        pin = open(self.gate.pin_file).read().split()[0]
        status, headers, _ = self.request('/pin', {'pin': pin})
        assert status == 303 and headers['Location'] == '/'
        return pin

    def saved(self):
        return json.loads(self.config.read_text())


@pytest.fixture
def board(tmp_path, monkeypatch):
    b = Board(tmp_path, monkeypatch)
    yield b
    b.httpd.shutdown()
    b.httpd.server_close()


def test_a_stranger_gets_the_pin_page_and_cannot_save(board):
    status, headers, body = board.request('/')
    assert status == 200 and 'Sign in to this board' in body
    assert headers['X-Frame-Options'] == 'DENY' and headers['Cache-Control'] == 'no-store'
    assert 'Send the PIN to my phone' not in body  # no Pushover keys
    status, headers, _ = board.request('/save', posted(TWO_RIDERS, debug='on'))
    assert status == 303 and headers['Location'] == '/'
    assert board.saved() == TWO_RIDERS and board.restarts == []


def test_the_pin_signs_in_and_saving_restarts_the_display(board):
    board.sign_in()
    assert not os.path.exists(board.gate.pin_file)  # off the board once used
    status, _, body = board.request('/')
    assert status == 200 and 'Save and restart' in body and 'Signed in' in body
    status, headers, _ = board.request('/save', posted(TWO_RIDERS, debug='on', goal_minutes='90'))
    assert status == 303 and headers['Location'] == '/?saved=restarted'
    saved = board.saved()
    assert saved['debug'] is True and saved['display']['weekly_goals'] == {'workouts': 3, 'minutes': 90}
    assert json.loads((board.config.parent / 'config.json.bak').read_text()) == TWO_RIDERS
    assert oct(os.stat(board.config).st_mode & 0o777) == '0o640'
    assert board.restarts == [1]
    _, _, body = board.request('/?saved=restarted')
    assert 'The display is restarting' in body


def test_a_bad_save_shows_the_problem_and_keeps_what_was_typed(board):
    board.sign_in()
    status, _, body = board.request('/save', posted(TWO_RIDERS, refresh_interval='0', goal_minutes='77'))
    assert status == 400 and 'Not saved.' in body and 'refresh_interval must be a positive integer' in body
    assert 'value="77"' in body
    assert board.saved() == TWO_RIDERS and board.restarts == []


def test_a_wrong_pin_and_sign_out(board):
    board.request('/pin/show', {})
    status, headers, _ = board.request('/pin', {'pin': 'nope'})
    assert headers['Location'] == '/signin?wrong'
    assert "That isn't the PIN" in board.request('/signin?wrong')[2]
    board.sign_in()
    status, headers, _ = board.request('/signout', {})
    assert headers['Location'] == '/signin?signedout'
    assert 'Signed out.' in board.request('/signin?signedout')[2]
    board.request('/save', posted(TWO_RIDERS, debug='on'))
    assert board.saved() == TWO_RIDERS


def test_on_the_setup_hotspot_no_pin_is_needed(board):
    board.hotspot()
    status, _, body = board.request('/')
    assert 'Setup mode' in body and 'PelotonPi-setup' in body and 'Sign out' not in body
    status, headers, _ = board.request('/save', posted(TWO_RIDERS, debug='on'))
    assert headers['Location'] == '/?saved=restarted' and board.saved()['debug'] is True


def test_off_the_hotspot_network_a_pin_is_still_needed(board):
    board.hotspot(client_on_it=False)
    assert 'Sign in to this board' in board.request('/')[2]


def test_forms_from_other_sites_and_oversized_posts_are_refused(board):
    board.sign_in()
    status, _, body = board.request('/save', posted(TWO_RIDERS, debug='on'), {'Origin': 'http://evil.example'})
    assert status == 403 and board.saved() == TWO_RIDERS
    req = urllib.request.Request(board.url + '/save', data=b'x', headers={'Content-Length': str(server.MAX_BODY + 1)})
    with pytest.raises(urllib.error.HTTPError) as caught:
        board.opener.open(req, timeout=5)
    assert caught.value.code == 413


def test_unknown_addresses(board):
    assert board.request('/nope')[0] == 404
    assert board.request('/nope', {})[0] == 404


def test_the_pin_page_says_when_the_display_cannot_show_a_pin(board):
    board.running = False
    body = board.request('/')[2]
    assert "The display isn't running" in body and 'sudo systemctl start peloton-led' in body
    board.running = None  # no systemd: no telling, so no warning
    assert "The display isn't running" not in board.request('/')[2]


def test_the_pin_goes_to_a_phone_with_pushover_keys(board):
    board.monkeypatch.setenv('PUSHOVER_APP_TOKEN', 'app-secret-token')
    board.monkeypatch.setenv('PUSHOVER_USER_KEY', 'user-secret-key')
    body = board.request('/')[2]
    assert 'Send the PIN to my phone' in body
    status, headers, _ = board.request('/pin/send', {})
    assert headers['Location'] == '/signin?sent=sent'
    pin = open(board.gate.pin_file).read().split()[0]
    assert len(board.sent) == 1 and pin in board.sent[0][1] and '2 minutes' in board.sent[0][1]
    assert board.request('/pin/send', {})[1]['Location'] == '/signin?sent=wait'
    assert 'on its way to your phone' in board.request('/signin?sent=sent')[2]
    # signed in: no secret reaches the page
    board.sign_in()
    page_html = board.request('/')[2]
    for secret in ('app-secret-token', 'user-secret-key', 'PELOTON_EMAIL_RIDER_ONE', 'PELOTON_PASSWORD_RIDER_ONE'):
        assert secret not in page_html
    # Credential fields are write-only: every one is empty, whatever is saved.
    import re
    fields = re.findall(r'<input type="(?:password|email)"[^>]*>', page_html)
    assert fields and all('value=""' in f for f in fields)


def test_without_pushover_keys_send_does_nothing(board):
    assert board.request('/pin/send', {})[1]['Location'] == '/signin'
    assert board.sent == []


def test_a_failed_send_is_reported(board):
    board.monkeypatch.setenv('PUSHOVER_APP_TOKEN', 't')
    board.monkeypatch.setenv('PUSHOVER_USER_KEY', 'u')
    board.settings.send_pushover = lambda title, message: False
    assert board.request('/pin/send', {})[1]['Location'] == '/signin?sent=failed'
    assert "Couldn't send the PIN" in board.request('/signin?sent=failed')[2]


def test_a_missing_or_broken_config_can_still_be_fixed(tmp_path, monkeypatch):
    b = Board(tmp_path, monkeypatch)
    try:
        b.config.write_text('{not json')
        b.sign_in()
        body = b.request('/')[2]
        assert "can't be read" in body
        status, headers, _ = b.request('/save', posted({}))
        assert headers['Location'] == '/?saved=restarted' and isinstance(b.saved(), dict)
        assert (tmp_path / 'config.json.bak').read_text() == '{not json'
        b.config.write_text('[]')
        assert "isn't a settings object" in b.request('/')[2]
        b.config.unlink()
        assert "doesn't exist yet" in b.request('/')[2]
    finally:
        b.httpd.shutdown()
        b.httpd.server_close()


def test_a_save_that_cannot_be_written_says_so(board):
    board.sign_in()

    def fail(config):
        raise OSError('read-only file system')
    board.settings.save = fail
    status, _, body = board.request('/save', posted(TWO_RIDERS))
    assert status == 500 and "Couldn't save: read-only file system" in body


# --- Settings without HTTP

def _settings(tmp_path, monkeypatch, results, which='/bin/systemctl'):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        result = results.pop(0)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(returncode=result[0], stderr=result[1])
    monkeypatch.setattr(server.shutil, 'which', lambda name: which)
    monkeypatch.setattr(server.subprocess, 'run', run)
    return Settings(str(tmp_path / 'config.json'), PinGate(str(tmp_path / 'pin'))), calls


@pytest.mark.parametrize('results,outcome', [
    ([(0, ''), (0, '')], 'restarted'),
    ([(3, '')], 'not_running'),
    ([(0, ''), (1, 'Unit failed')], 'failed'),
    ([(0, ''), (1, '')], 'failed'),
    ([(0, ''), subprocess.TimeoutExpired('systemctl', 30)], 'failed'),
    ([OSError('no dbus')], 'saved'),
])
def test_restart_outcomes(tmp_path, monkeypatch, results, outcome):
    settings, calls = _settings(tmp_path, monkeypatch, results)
    assert settings.restart_app() == outcome
    assert calls[0] == ['systemctl', 'is-active', '--quiet', 'peloton-led.service']
    if len(calls) > 1:
        assert calls[1] == ['systemctl', 'try-restart', 'peloton-led.service']


def test_no_systemd_means_restart_by_hand(tmp_path, monkeypatch):
    settings, calls = _settings(tmp_path, monkeypatch, [], which=None)
    assert settings.restart_app() == 'saved' and settings.display_running() is None and calls == []


def test_save_config_writes_whole_with_a_backup_and_the_old_mode(tmp_path):
    path = tmp_path / 'config.json'
    save_config({'a': 1}, str(path))
    assert json.loads(path.read_text()) == {'a': 1} and oct(path.stat().st_mode & 0o777) == '0o640'
    assert not (tmp_path / 'config.json.bak').exists()
    os.chmod(path, 0o600)
    save_config({'a': 2}, str(path))
    assert json.loads(path.read_text()) == {'a': 2} and oct(path.stat().st_mode & 0o777) == '0o600'
    assert json.loads((tmp_path / 'config.json.bak').read_text()) == {'a': 1}
    assert not (tmp_path / 'config.json.new').exists()


def test_save_config_as_a_non_root_owner(tmp_path, monkeypatch):
    path = tmp_path / 'config.json'
    path.write_text('{}')

    def denied(*args):
        raise PermissionError
    monkeypatch.setattr(server.os, 'chown', denied)
    save_config({'b': 1}, str(path))
    assert json.loads(path.read_text()) == {'b': 1}


def test_only_the_pushover_keys_are_read_from_auth_env(tmp_path, caplog):
    env = tmp_path / 'auth.env'
    env.write_text('PELOTON_PASSWORD_RIDER_ONE=hunter2\n# comment\nPUSHOVER_APP_TOKEN="tok"\n'
                   "PUSHOVER_USER_KEY='usr'\nnot a line\n")
    assert read_pushover_keys(str(env)) == {'PUSHOVER_APP_TOKEN': 'tok', 'PUSHOVER_USER_KEY': 'usr'}
    assert read_pushover_keys(str(tmp_path / 'missing.env')) == {}
    assert read_pushover_keys(str(tmp_path)) == {}  # a folder: can't be read, logged
    assert "can't read" in caplog.text


def test_main_reads_the_keys_and_serves(tmp_path, monkeypatch):
    env = tmp_path / 'auth.env'
    env.write_text('PUSHOVER_APP_TOKEN=tok\nPUSHOVER_USER_KEY=usr\nPELOTON_PASSWORD_RIDER_ONE=hunter2\n')
    environ = {}  # the process's own is shared with other tests (and may hold a .env's logins)
    monkeypatch.setattr(server.os, 'environ', environ)
    served = []

    class FakeServer:
        def serve_forever(self):
            served.append(True)
    monkeypatch.setattr(server, 'make_server', lambda settings, host, port: served.append((settings, host, port))
                        or FakeServer())
    server.main(['--config', str(tmp_path / 'config.json'), '--auth-env', str(env), '--port', '9999',
                 '--pin-file', str(tmp_path / 'pin')])
    settings, host, port = served[0]
    assert port == 9999 and settings.gate.pin_file == str(tmp_path / 'pin') and served[1] is True
    assert environ == {'PUSHOVER_APP_TOKEN': 'tok', 'PUSHOVER_USER_KEY': 'usr'}
    assert settings.updates.app_dir == server.CODE_DIR, 'run from this checkout: it updates it'
    server.main(['--config', str(tmp_path / 'config.json'), '--checkout', '', '--port', '9999'])
    assert served[2][0].updates is None, 'no checkout: no Updates card'


class FakeUpdates:
    """updates.Updates, recording what the buttons asked for."""
    def __init__(self):
        self.asked, self.is_running = [], False

    def view(self):
        return {'version': '0.1.0', 'sha': 'a' * 40, 'branch': 'main', 'running': self.is_running, 'phase': 'idle',
                'status': None, 'step': None, 'from': None, 'outcome': None, 'check': None, 'channel': 'releases',
                'auto_check': False}

    def running(self):
        return self.is_running

    def status(self):
        return {'running': self.is_running, 'phase': 'Installing the new version' if self.is_running else None,
                'step': 2 if self.is_running else None}

    def check(self, channel):
        self.asked.append(('check', channel))

    def auto_check(self, channel):
        self.asked.append(('auto_check', channel))

    def start(self, command, channel=None):
        self.asked.append((command, channel))
        return 'started'


@pytest.fixture
def updating(board):
    board.settings.updates = FakeUpdates()
    return board


def test_without_a_checkout_there_is_no_updates_card_or_its_routes(board):
    board.sign_in()
    assert 'id="updates"' not in board.request('/')[2]
    assert board.request('/update/check', {'channel': 'beta'})[0] == 404
    assert board.request('/update/status')[0] == 404


def test_the_update_buttons_need_sign_in_and_the_pages_own_origin(updating):
    for path in ('/update/check', '/update/start', '/update/rollback'):
        status, headers, _ = updating.request(path, {'channel': 'beta'})
        assert status == 303 and headers['Location'] == '/'
    status, _, _ = updating.request('/update/rollback', {}, {'Origin': 'http://evil.example'})
    assert status == 403
    status, _, body = updating.request('/update/status')
    assert status == 403 and json.loads(body) == {'running': False, 'phase': None, 'step': None}
    assert updating.settings.updates.asked == []


def test_check_update_and_roll_back_go_to_the_updates_card(updating):
    updating.sign_in()
    assert 'id="updates"' in updating.request('/')[2]
    status, headers, _ = updating.request('/update/check', {'channel': 'beta'})
    assert status == 303 and headers['Location'] == '/#updates'
    status, headers, _ = updating.request('/update/start', {'channel': 'beta'})
    assert headers['Location'] == '/?update=started#updates'
    updating.request('/update/rollback', {'channel': 'beta'})
    assert updating.settings.updates.asked == [('check', 'beta'), ('update', 'beta'), ('rollback', None)]
    assert '<strong>Started.</strong>' in updating.request('/?update=started')[2]
    assert '<strong>Started.</strong>' not in updating.request('/?update=whatever')[2]


def test_the_pages_own_check_answers_with_the_cards_result(updating):
    updating.request('/update/check', {'channel': 'beta'}, {'Accept': 'application/json'})
    assert updating.settings.updates.asked == [], 'signed out: nothing checked'
    updating.sign_in()
    status, _, body = updating.request('/update/check', {'channel': 'beta'}, {'Accept': 'application/json'})
    assert status == 200 and updating.settings.updates.asked == [('auto_check', 'beta')]
    assert json.loads(body) == {'html': ''}, "the fake's view has no check to show"


def test_while_an_update_runs_its_status_is_followed_and_saving_waits(updating):
    updating.sign_in()
    updating.settings.updates.is_running = True
    status, _, body = updating.request('/update/status')
    assert status == 200 and json.loads(body) == {'running': True, 'phase': 'Installing the new version', 'step': 2}
    status, _, html = updating.request('/save', posted(TWO_RIDERS, goal_minutes='77'))
    assert status == 409 and 'An update is running' in html
    assert updating.saved() == TWO_RIDERS and updating.restarts == []
    assert 'value="77"' in html, 'what was typed stays on the page'


def test_the_checkout_is_the_installers_or_this_codes_own(tmp_path):
    checkout = tmp_path / 'Peloton-LED'
    (checkout / '.git').mkdir(parents=True)
    plain = tmp_path / 'opt'
    plain.mkdir()
    assert server.default_checkout({'PELOTON_CHECKOUT': str(checkout)}, str(plain)) == str(checkout)
    assert server.default_checkout({}, str(checkout)) == str(checkout), 'run from a checkout'
    assert server.default_checkout({}, str(plain)) is None, '/opt/peloton-led: no git, no card'
    assert server.default_checkout({'PELOTON_CHECKOUT': str(plain)}, str(plain)) is None, 'not a checkout'
