"""The settings page's Logins card: login health from renewal's files, the write-only credentials in
auth.env, and the Renew now and test alert buttons. No network; systemctl and Pushover are faked."""
import base64
import json
import os
import re
import time
from html import unescape
from types import SimpleNamespace

import pytest

import settings_page.server as server
from settings_page import logins, page
from settings_page.logins import (alert_state, credential_changes, read_auth_env, rider_logins, rider_paths,
                                  token_mode, update_auth_env, when)
from tests.test_settings_form import TWO_RIDERS
from tests.test_settings_server import Board


def jwt(expires):
    payload = base64.urlsafe_b64encode(json.dumps({'exp': expires}).encode()).decode().rstrip('=')
    return f'header.{payload}.signature'


def touch(path, mtime):
    os.utime(path, (mtime, mtime))


@pytest.fixture
def state(tmp_path):
    """Joel: a good token with a refresh chain. Jen: an expired token, a padlock, a browser try."""
    joel, jen = tmp_path / 'cookies-joel.txt', tmp_path / 'cookies-jen.txt'
    joel.write_text(jwt(time.time() + 3 * 86400))
    (tmp_path / 'cookies-joel.refresh.json').write_text(json.dumps(
        {'refresh_token': 'rt-secret', 'chain_started_at': '2026-11-01T00:00:00+00:00',
         'chain_start_exact': True, 'renewals': 4}))
    jen.write_text(jwt(time.time() - 60))
    marker = tmp_path / 'cookies-jen.renewal-failed'
    marker.write_text(json.dumps({'reason': 'invalid_grant: chain is dead', 'at': '2026-11-03T10:00:00+00:00'}))
    touch(jen, 1000)
    touch(marker, 2000)
    (tmp_path / 'cookies-jen.browser-attempt').write_text('1793800000')
    return tmp_path


def test_rider_paths_follow_the_app(tmp_path):
    single = rider_paths({'display': {'username': 'Joel'}}, tmp_path, '/var/lib/peloton-led/cookies.txt')
    assert single == [('default', 'Joel', __import__('pathlib').Path('/var/lib/peloton-led/cookies.txt'),
                       'PELOTON_EMAIL', 'PELOTON_PASSWORD')]
    assert rider_paths({}, tmp_path)[0][1] == 'This board'
    riders = rider_paths(TWO_RIDERS, tmp_path)
    assert [(k, n, p.name, e, w) for k, n, p, e, w in riders] == [
        ('0', 'Joel', 'cookies-joel.txt', 'PELOTON_EMAIL_RIDER_ONE', 'PELOTON_PASSWORD_RIDER_ONE'),
        ('1', 'Jen', 'cookies-jen.txt', 'PELOTON_EMAIL_JEN', 'PELOTON_PASSWORD_JEN')]
    assert riders[1][2] == tmp_path / 'cookies-jen.txt'  # relative to the config the display reads
    assert [k for k, *_ in rider_paths({'users': ['junk', {'name': 'A'}]}, tmp_path)] == ['1']


def test_rider_logins_read_renewals_files(state):
    joel, jen = rider_logins(TWO_RIDERS, state, {'PELOTON_EMAIL_RIDER_ONE': 'j@x.com', 'PELOTON_PASSWORD_JEN': ''})
    assert joel.healthy and joel.token['ok'] and not joel.token['expired']
    assert joel.chain.startswith('refresh chain') and '4 renewals' in joel.chain
    assert (joel.email_set, joel.password_set, joel.padlock, joel.browser_attempt) == (True, False, None, None)
    assert not jen.healthy and jen.token['expired'] and jen.chain is None
    assert jen.padlock == {'reason': 'invalid_grant: chain is dead', 'at': '2026-11-03T10:00:00+00:00'}
    assert jen.browser_attempt == 1793800000 and not jen.password_set


def test_a_padlock_older_than_the_token_is_over(state):
    touch(state / 'cookies-jen.txt', 3000)
    assert rider_logins(TWO_RIDERS, state, {})[1].padlock is None
    (state / 'cookies-jen.txt').unlink()  # no token at all: the marker stands
    (state / 'cookies-jen.renewal-failed').write_text('not json')
    jen = rider_logins(TWO_RIDERS, state, {})[1]
    assert jen.padlock['reason'] == 'Renewal needs a fresh login.' and jen.token['reason'] == 'file does not exist'


def test_alert_state_and_token_mode(tmp_path):
    token = tmp_path / 'cookies.txt'
    assert alert_state(token) == {}
    (tmp_path / 'token-alert-state.json').write_text(json.dumps({'failures': 2, 'last_message': 'boom'}))
    assert alert_state(token) == {'failures': 2, 'last_message': 'boom'}
    (tmp_path / 'token-alert-state.json').write_text('[1]')
    assert alert_state(token) == {}
    mode = tmp_path / 'token-mode'
    assert token_mode(mode) is None
    for text, expected in (('no-browser flag\n', 'no-browser'), ('browser auto', 'browser'), ('none', 'none'),
                           ('weird', None), ('', None)):
        mode.write_text(text)
        assert token_mode(mode) == expected


AUTH = '''# Written by setup_config.py
PELOTON_EMAIL_RIDER_ONE="joel@example.com"
PELOTON_PASSWORD_RIDER_ONE="pa\\"ss\\\\word"
export PUSHOVER_APP_TOKEN='abc'

PUSHOVER_USER_KEY=plain
'''


def test_auth_env_is_read_as_systemd_reads_it(tmp_path):
    path = tmp_path / 'auth.env'
    path.write_text(AUTH)
    assert read_auth_env(path) == {'PELOTON_EMAIL_RIDER_ONE': 'joel@example.com',
                                   'PELOTON_PASSWORD_RIDER_ONE': 'pa"ss\\word',
                                   'PUSHOVER_APP_TOKEN': 'abc', 'PUSHOVER_USER_KEY': 'plain'}
    assert read_auth_env(tmp_path / 'missing') == {}


def test_an_unreadable_auth_env_is_logged(tmp_path, caplog):
    assert read_auth_env(tmp_path) == {}
    assert "can't read" in caplog.text


def test_updating_auth_env_keeps_everything_else(tmp_path):
    path = tmp_path / 'auth.env'
    path.write_text(AUTH)
    os.chmod(path, 0o600)
    update_auth_env(path, {'PELOTON_PASSWORD_RIDER_ONE': 'new "one" \\ here', 'PUSHOVER_USER_KEY': None,
                           'PELOTON_EMAIL_JEN': 'jen@example.com'})
    text = path.read_text()
    assert text.startswith('# Written by setup_config.py\nPELOTON_EMAIL_RIDER_ONE="joel@example.com"\n')
    assert 'PUSHOVER_USER_KEY' not in text and "export PUSHOVER_APP_TOKEN='abc'" in text
    assert read_auth_env(path)['PELOTON_PASSWORD_RIDER_ONE'] == 'new "one" \\ here'
    assert read_auth_env(path)['PELOTON_EMAIL_JEN'] == 'jen@example.com'
    assert oct(path.stat().st_mode & 0o777) == '0o600'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['auth.env']  # no backup copy of the passwords


def test_updating_a_missing_auth_env_makes_it_owner_only(tmp_path, monkeypatch):
    path = tmp_path / 'auth.env'
    update_auth_env(path, {'PUSHOVER_APP_TOKEN': 'x' * 30, 'GONE': None})
    assert path.read_text() == f'PUSHOVER_APP_TOKEN="{"x" * 30}"\n'
    assert oct(path.stat().st_mode & 0o777) == '0o600'

    def denied(*args):
        raise PermissionError
    monkeypatch.setattr(logins.os, 'chown', denied)  # not root: it's ours already
    update_auth_env(path, {'PUSHOVER_APP_TOKEN': None})
    assert path.read_text() == ''


def _riders(tmp_path):
    return rider_logins(TWO_RIDERS, tmp_path, {})


def test_credential_changes(tmp_path):
    form = {'cred_0_name': ['Joel'], 'cred_0_email': [' joel@new.com '], 'cred_0_password': [''],
            'cred_1_name': ['Jen'], 'cred_1_email': [''], 'cred_1_password': [' sp ace '],
            'pushover_app_token': ['a' * 30], 'pushover_user_key': ['']}
    changes, problems, changed = credential_changes(form, _riders(tmp_path))
    assert problems == []
    assert changes == {'PELOTON_EMAIL_RIDER_ONE': 'joel@new.com', 'PELOTON_PASSWORD_JEN': ' sp ace ',
                       'PUSHOVER_APP_TOKEN': 'a' * 30}
    assert changed == ["Joel's email", "Jen's password", 'Pushover app token']
    assert credential_changes({}, _riders(tmp_path)) == ({}, [], [])


@pytest.mark.parametrize('form,message', [
    ({'cred_0_email': ['not-an-email']}, "Joel's email doesn't look like an email address."),
    ({'cred_1_password': ['line\nbreak']}, "Jen's password can't contain line breaks"),
    ({'pushover_user_key': ['short']}, 'The Pushover user key should be letters and numbers only'),
    ({'pushover_app_token': ['a' * 29 + '!']}, 'The Pushover app token should be letters and numbers only'),
    ({'cred_0_name': ['Joe'], 'cred_0_email': ['a@b.co']}, 'The riders in config.json changed'),
])
def test_bad_credentials_change_nothing_and_never_echo_the_value(tmp_path, form, message):
    changes, problems, changed = credential_changes(form, _riders(tmp_path))
    assert changes == {} and changed == [] and len(problems) == 1 and problems[0].startswith(message)
    for values in form.values():
        if values[0] not in ('Joe',):
            assert values[0] not in problems[0]


def test_clearing_pushover_wins_over_typed_keys(tmp_path):
    form = {'pushover_clear': ['on'], 'pushover_app_token': ['a' * 30]}
    changes, problems, changed = credential_changes(form, _riders(tmp_path))
    assert changes == {'PUSHOVER_APP_TOKEN': None, 'PUSHOVER_USER_KEY': None} and changed == ['Pushover keys removed']


def test_when():
    from datetime import timezone
    assert when(0, timezone.utc) == 'Thu Jan 1, 12:00 AM'
    assert when('soon') == 'unknown'


# --- Over HTTP

SECRETS = {'PELOTON_EMAIL_RIDER_ONE': 'joel@example.com', 'PELOTON_PASSWORD_RIDER_ONE': 'hunter2-secret',
           'PUSHOVER_APP_TOKEN': 'a' * 30, 'PUSHOVER_USER_KEY': 'u' * 30}


@pytest.fixture
def board(tmp_path, monkeypatch, state):
    b = Board(tmp_path, monkeypatch)
    b.settings.token_base = str(state)
    b.auth_env.write_text(''.join(f'{k}="{v}"\n' for k, v in SECRETS.items()))
    yield b
    b.httpd.shutdown()
    b.httpd.server_close()


def test_the_card_shows_health_and_never_a_secret(board, tmp_path):
    board.units = {server.RENEW_UNIT: {'ActiveState': 'inactive', 'Result': 'exit-code',
                                       'ExecMainExitTimestamp': 'Wed 2026-11-04 09:00:00 EST'},
                   server.RENEW_TIMER: {'ActiveState': 'active', 'NextElapseUSecRealtime': 'Wed 2026-11-04 10:00:00'}}
    (tmp_path / 'token-mode').write_text('no-browser flag\n')
    (tmp_path / 'token-alert-state.json').write_text(json.dumps({'failures': 3, 'last_message': 'Jen: invalid_grant'}))
    board.sign_in()
    html = board.request('/')[2]
    card = html.split('id="logins"', 1)[1].split('</section>', 1)[0]
    assert 'Valid until' in card and 'Expired' in card and 'Padlock on' in card
    assert 'Renewal says: invalid_grant: chain is dead' in card
    assert 'Email and password set' in card and 'Email not set, password not set' in card
    assert 'refresh tokens only' in card and 'Last renewal run: Wed 2026-11-04 09:00:00 EST, failed (exit-code)' in card
    assert 'Next scheduled check: Wed 2026-11-04 10:00:00' in card
    assert '3 failed runs in a row; last: Jen: invalid_grant' in card
    assert 'scripts/seed_board.sh' in card and card.count('seed_board.sh') == 1  # Jen only
    assert 'Send a test alert' in card and 'Save logins' in card
    for secret in list(SECRETS.values()) + ['rt-secret']:
        assert secret not in html


def test_a_browser_board_needs_no_seed_command(board, tmp_path):
    (tmp_path / 'token-mode').write_text('browser auto\n')
    board.units = {server.RENEW_UNIT: {'ActiveState': 'activating'}}
    board.sign_in()
    card = board.request('/')[2].split('id="logins"', 1)[1].split('</section>', 1)[0]
    assert 'seed_board.sh' not in card and 'one browser login a day' in card
    assert 'Renewal is running now.' in card and 'No check is scheduled right now' in card


def test_saving_logins_takes_a_pin_session_even_on_the_hotspot(board):
    board.hotspot()
    html = board.request('/')[2]
    assert 'sign in with the PIN' in html and 'action="/credentials"' not in html
    status, headers, _ = board.request('/credentials', {'cred_0_name': 'Joel', 'cred_0_password': 'new-one'})
    assert headers['Location'] == '/signin'
    assert read_auth_env(board.auth_env) == SECRETS
    status, _, body = board.request('/signin')
    assert status == 200 and 'Sign in to this board' in body  # the PIN page, hotspot or not
    board.sign_in()
    assert board.request('/signin')[1]['Location'] == '/'


def test_saving_logins_writes_auth_env_and_updates_pushover_at_once(board, monkeypatch, caplog):
    environ = {}
    monkeypatch.setattr(server.os, 'environ', environ)
    import logging
    settings_log = logging.getLogger('peloton-led.settings')  # "peloton-led" may not propagate to caplog's root
    settings_log.addHandler(caplog.handler)
    monkeypatch.setattr(settings_log, 'level', logging.INFO)
    board.sign_in()
    status, headers, _ = board.request('/credentials', {
        'cred_0_name': 'Joel', 'cred_0_password': 'brand-new-pass', 'cred_1_name': 'Jen',
        'cred_1_email': 'jen@example.com', 'pushover_user_key': 'k' * 30})
    assert headers['Location'] == '/?logins=logins_saved#logins'
    saved = read_auth_env(board.auth_env)
    assert saved['PELOTON_PASSWORD_RIDER_ONE'] == 'brand-new-pass' and saved['PELOTON_EMAIL_JEN'] == 'jen@example.com'
    assert saved['PELOTON_EMAIL_RIDER_ONE'] == 'joel@example.com' and saved['PUSHOVER_USER_KEY'] == 'k' * 30
    assert environ == {'PUSHOVER_USER_KEY': 'k' * 30}
    assert "Joel's password, Jen's email, Pushover user key" in caplog.text
    assert 'brand-new-pass' not in caplog.text and 'jen@example.com' not in caplog.text
    settings_log.removeHandler(caplog.handler)
    assert 'Logins saved' in board.request('/?logins=logins_saved')[2]
    board.request('/credentials', {'pushover_clear': 'on'})
    assert 'PUSHOVER_APP_TOKEN' not in read_auth_env(board.auth_env) and environ == {}
    assert board.request('/credentials', {})[1]['Location'] == '/?logins=logins_unchanged#logins'


def test_bad_logins_are_not_saved(board):
    board.sign_in()
    status, _, body = board.request('/credentials', {'cred_0_email': 'nope', 'cred_0_password': 'typed-secret'})
    assert status == 400 and 'Logins not saved.' in body and "Joel's email doesn't look like" in body
    assert 'typed-secret' not in body and read_auth_env(board.auth_env) == SECRETS


def test_logins_that_cannot_be_written_say_so(board, monkeypatch):
    board.sign_in()

    def fail(path, changes):
        raise OSError('read-only file system')
    monkeypatch.setattr(logins, 'update_auth_env', fail)
    status, _, body = board.request('/credentials', {'cred_0_password': 'x'})
    assert status == 400 and "Couldn't save the logins: read-only file system" in body


def test_strangers_can_not_renew_or_test(board):
    assert board.request('/renew', {})[1]['Location'] == '/'
    assert board.request('/alert/test', {})[1]['Location'] == '/'
    assert board.sent == []


def test_test_alert_outcomes(board, monkeypatch):
    board.sign_in()
    monkeypatch.delenv('PUSHOVER_APP_TOKEN', raising=False)
    assert board.request('/alert/test', {})[1]['Location'] == '/?logins=test_off#logins'
    monkeypatch.setenv('PUSHOVER_APP_TOKEN', 't')
    monkeypatch.setenv('PUSHOVER_USER_KEY', 'u')
    assert board.request('/alert/test', {})[1]['Location'] == '/?logins=test_sent#logins'
    assert len(board.sent) == 1 and 'test alert' in board.sent[0][0]
    assert board.request('/alert/test', {})[1]['Location'] == '/?logins=test_wait#logins'
    board.settings._last_test -= server.TEST_ALERT_EVERY_S
    board.settings.send_pushover = lambda title, message: False
    assert board.request('/alert/test', {})[1]['Location'] == '/?logins=test_failed#logins'
    for outcome in page.LOGIN_OUTCOMES:
        assert page.LOGIN_OUTCOMES[outcome][1].split('<')[0][:10] in unescape(board.request(f'/?logins={outcome}')[2])


def test_renew_now(board):
    board.sign_in()
    calls = []
    board.settings._systemctl = lambda *args, unit=None: calls.append((args, unit)) or SimpleNamespace(
        returncode=0, stderr='')
    assert board.request('/renew', {})[1]['Location'] == '/?logins=renew_started#logins'
    assert calls == [(('start', '--no-block'), server.RENEW_UNIT)]
    board.units = {server.RENEW_UNIT: {'ActiveState': 'activating'}}
    assert board.request('/renew', {})[1]['Location'] == '/?logins=renew_running#logins'


@pytest.mark.parametrize('result,outcome', [
    (SimpleNamespace(returncode=1, stderr='Unit not found'), 'renew_failed'),
    (SimpleNamespace(returncode=5, stderr=''), 'renew_failed'),
    (OSError('no dbus'), 'renew_failed'),
    (None, 'renew_unavailable'),
])
def test_renew_problems(tmp_path, monkeypatch, result, outcome):
    settings = server.Settings(str(tmp_path / 'config.json'))
    monkeypatch.setattr(settings, '_unit_properties', lambda unit, *names: {})

    def systemctl(*args, unit=None):
        if isinstance(result, Exception):
            raise result
        return result
    settings._systemctl = systemctl
    assert settings.renew() == outcome


def test_unit_properties_are_read_from_systemctl_show(tmp_path, monkeypatch):
    settings = server.Settings(str(tmp_path / 'config.json'))
    runs = []
    answers = [SimpleNamespace(returncode=0, stdout='ActiveState=active\nNextElapseUSecRealtime=Wed 10:00\nnoise\n'),
               SimpleNamespace(returncode=1, stdout=''), OSError('boom')]

    def run(cmd, **kwargs):
        runs.append(cmd)
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(server.shutil, 'which', lambda name: '/bin/systemctl')
    monkeypatch.setattr(server.subprocess, 'run', run)
    assert settings._unit_properties('x.timer', 'ActiveState', 'NextElapseUSecRealtime') == {
        'ActiveState': 'active', 'NextElapseUSecRealtime': 'Wed 10:00'}
    assert runs[0] == ['systemctl', 'show', '--property=ActiveState', '--property=NextElapseUSecRealtime', 'x.timer']
    assert settings._unit_properties('x.timer', 'ActiveState') == {}
    assert settings._unit_properties('x.timer', 'ActiveState') == {}
    settings.restart_unit = ''
    assert settings._unit_properties('x.timer', 'ActiveState') == {}


def test_seed_command_names_the_checkout_owner(tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    config.write_text('{}')
    settings = server.Settings(str(config))
    import pwd
    me = pwd.getpwuid(os.getuid()).pw_name
    assert settings.checkout_owner() == (me if me != 'root' else '<user>')
    assert server.Settings(str(tmp_path / 'missing.json')).checkout_owner() == '<user>'
    monkeypatch.setattr(pwd, 'getpwuid', lambda uid: SimpleNamespace(pw_name='root'))
    assert settings.checkout_owner() == '<user>'


def test_the_card_on_a_fresh_board(tmp_path):
    html = page.logins_card({'riders': [], 'mode': None, 'seed': 'x'})
    assert 'Renewal mode unknown' in html and 'Save logins' in html
    assert page.logins_card(None) == ''
    assert re.search(r'id="logins"', page.settings_page({}, logins={'riders': [], 'seed': 'x'}))
