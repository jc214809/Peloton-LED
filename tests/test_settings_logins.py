"""The settings page's Logins card: login health from renewal's files, the write-only credentials in
auth.env, and the Renew now and test alert buttons. No network; systemctl and Pushover are faked."""
import base64
import json
import os
import pathlib
import re
import time
from html import unescape
from types import SimpleNamespace
from zoneinfo import ZoneInfo

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


# The page shows times in the board's zone (TWO_RIDERS' display.timezone), whatever the machine's.
ZONE = ZoneInfo(TWO_RIDERS['display']['timezone'])


def test_the_card_shows_health_and_never_a_secret(board, tmp_path):
    board.units = {server.RENEW_UNIT: {'ActiveState': 'inactive', 'Result': 'exit-code',
                                       'ExecMainExitTimestamp': '@1762264800'},
                   server.RENEW_TIMER: {'ActiveState': 'active', 'NextElapseUSecRealtime': '@1762268400'}}
    (tmp_path / 'token-mode').write_text('no-browser flag\n')
    (tmp_path / 'token-alert-state.json').write_text(json.dumps({'failures': 3, 'last_message': 'Jen: invalid_grant'}))
    board.sign_in()
    html = board.request('/')[2]
    card = html.split('id="logins"', 1)[1].split('</section>', 1)[0]
    joel, jen = card.split('<details class="rider-card"')[1:3]
    # Joel works: his card stays closed. Jen needs a login: hers opens by itself, saying why.
    assert joel.startswith('><summary><strong>Joel</strong>') and '<span class="pill ok">Working</span>' in joel
    assert '<span class="k">Token</span><span>Valid until' in joel
    assert jen.startswith(' open><summary><strong>Jen</strong>') and '<span class="pill bad">Expired</span>' in jen
    assert '<span class="k">Renewal says</span><span>invalid_grant: chain is dead</span>' in jen
    assert '<span>Set <span class="change">' in joel and '<span>Email not set, password not set ' in jen
    # Labelled rows, times in the page's own style (systemd gives them as epoch seconds).
    assert '<dt>Renewal</dt><dd><span class="pill bad">Last run failed (exit-code)</span></dd>' in card
    assert f'<dt>Last run</dt><dd>{logins.when(1762264800, ZONE)} \u00b7 failed</dd>' in card  # the page, unescaped
    assert f'<dt>Next check</dt><dd>{logins.when(1762268400, ZONE)}</dd>' in card
    assert '<dt>Interval</dt><dd>Every hour' in card
    assert '<span class="pill bad">3 in a row</span><span class="hint">Jen: invalid_grant</span>' in card
    assert 'Automatic, with refresh tokens only.' in card
    assert 'scripts/seed_board.sh' in card and card.count('seed_board.sh') == 1  # Jen only
    assert card.count('<details class="cred"') == 2 and 'Send a test alert' not in card
    assert 'This board has no browser, so it never signs in with these' in card, 'a no-browser board says so'
    alerts = html.split('id="alerts"', 1)[1].split('</section>', 1)[0]
    assert 'Send a test alert' in alerts and 'Save alert keys' in alerts and 'name="pushover_clear"' in alerts
    remove = alerts.split('action="/credentials" data-busy="Removing', 1)[1].split('</form>', 1)[0]
    assert 'data-confirm="Remove the Pushover keys?' in remove and '<span>Remove keys</span>' in remove
    assert 'Remove the Pushover keys</label>' not in alerts, 'a button now, not a switch'
    for secret in list(SECRETS.values()) + ['rt-secret']:
        assert secret not in html


def test_a_browser_board_needs_no_seed_command(board, tmp_path):
    (tmp_path / 'token-mode').write_text('browser auto\n')
    board.units = {server.RENEW_UNIT: {'ActiveState': 'activating'}}
    board.sign_in()
    card = board.request('/')[2].split('id="logins"', 1)[1].split('</section>', 1)[0]
    assert 'seed_board.sh' not in card and 'trying at most once a day' in card
    assert 'id="renewal" aria-live="polite" data-running>' in card, 'the script follows it'
    assert '<span class="pill now">Running now</span>' in card
    assert 'Not scheduled' in card and "the hourly timer isn't running" in card, 'the display is on'
    board.running = False
    card = board.request('/')[2].split('id="logins"', 1)[1].split('</section>', 1)[0]
    assert 'When the display starts' in card and 'only while the display is on' in card


def test_a_running_renewal_is_followed_until_it_is_done(board):
    assert json.loads(board.request('/renew/status')[2]) == {'renewing': False, 'html': ''}, 'signed out'
    board.sign_in()
    board.units = {server.RENEW_UNIT: {'ActiveState': 'activating'}}
    now = json.loads(board.request('/renew/status')[2])
    assert now['renewing'] is True and 'Running now' in now['html'] and now['html'].startswith('<dl class="facts" id="renewal"')
    board.units = {server.RENEW_UNIT: {'ActiveState': 'inactive', 'Result': 'success',
                                       'ExecMainExitTimestamp': '@1762264800'}}
    now = json.loads(board.request('/renew/status')[2])
    assert now['renewing'] is False and 'Last run worked' in now['html'] and 'data-running' not in now['html']


def test_each_riders_login_changes_from_their_own_email_and_password_row(board):
    board.sign_in()
    html = board.request('/')[2]
    card = html.split('id="logins"', 1)[1].split('</section>', 1)[0]
    assert 'Change logins' not in card and '<dialog' not in card, 'no separate button or window'
    joel = card.split('<details class="cred" id="cred-0">', 1)[1].split('</details>', 1)[0]
    assert '<span class="k">Email & password</span>' in joel and 'Change</span>' in joel  # the page, unescaped
    assert 'name="cred_0_email"' in joel and 'name="cred_1_email"' not in joel, "only this rider's fields"
    assert '<input type="hidden" name="cred_0_name" value="Joel">' in joel
    assert 'data-cancel' in joel and "closest('details.cred')" in html, 'Cancel clears and closes it'
    # A save with problems opens that rider's card and form again, the problems inside.
    status, _, body = board.request('/credentials', {'cred_1_name': 'Jen', 'cred_1_email': 'nope'})
    assert status == 400
    jen = body.split('<details class="cred" id="cred-1" open>', 1)[1].split('</details>', 1)[0]
    assert "Jen's email doesn't look like" in jen and '<details class="cred" id="cred-0" open>' not in body


def test_saving_one_riders_login_leaves_the_others(board):
    board.sign_in()
    status, headers, _ = board.request('/credentials', {'cred_1_name': 'Jen', 'cred_1_password': 'jens-new-one'})
    assert headers['Location'] == '/?logins=logins_saved#logins'
    saved = read_auth_env(board.auth_env)
    assert saved['PELOTON_PASSWORD_JEN'] == 'jens-new-one'
    assert saved['PELOTON_PASSWORD_RIDER_ONE'] == SECRETS['PELOTON_PASSWORD_RIDER_ONE']


def test_the_alert_keys_save_from_their_own_card(board):
    board.sign_in()
    status, headers, _ = board.request('/credentials', {'card': 'alerts', 'pushover_user_key': 'k' * 30})
    assert headers['Location'] == '/?alerts=alerts_saved#alerts'
    assert read_auth_env(board.auth_env)['PUSHOVER_USER_KEY'] == 'k' * 30
    assert read_auth_env(board.auth_env)['PELOTON_PASSWORD_RIDER_ONE'] == SECRETS['PELOTON_PASSWORD_RIDER_ONE']
    assert board.request('/credentials', {'card': 'alerts'})[1]['Location'] == '/?alerts=alerts_unchanged#alerts'
    status, _, body = board.request('/credentials', {'card': 'alerts', 'pushover_user_key': 'short'})
    alerts = body.split('id="alerts"', 1)[1].split('</section>', 1)[0]
    assert status == 400 and 'Alert keys not saved.' in alerts and 'Logins not saved' not in body
    assert 'Alert keys saved' in board.request('/?alerts=alerts_saved')[2]


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
    caplog.set_level(logging.INFO, logger='peloton-led.settings')  # setLevel clears the logger's cache
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
    assert board.request('/alert/test', {})[1]['Location'] == '/?alerts=test_off#alerts'
    monkeypatch.setenv('PUSHOVER_APP_TOKEN', 't')
    monkeypatch.setenv('PUSHOVER_USER_KEY', 'u')
    assert board.request('/alert/test', {})[1]['Location'] == '/?alerts=test_sent#alerts'
    assert len(board.sent) == 1 and 'test alert' in board.sent[0][0]
    assert board.request('/alert/test', {})[1]['Location'] == '/?alerts=test_wait#alerts'
    board.settings._last_test -= server.TEST_ALERT_EVERY_S
    board.settings.send_pushover = lambda title, message: False
    assert board.request('/alert/test', {})[1]['Location'] == '/?alerts=test_failed#alerts'
    for outcome in page.LOGIN_OUTCOMES:
        assert page.LOGIN_OUTCOMES[outcome][1].split('<')[0][:10] in unescape(board.request(f'/?logins={outcome}')[2])
    for outcome in page.ALERT_OUTCOMES:
        html = unescape(board.request(f'/?alerts={outcome}')[2])
        alerts = html.split('id="alerts"', 1)[1].split('</section>', 1)[0]
        assert page.ALERT_OUTCOMES[outcome][1].split('<')[0][:10] in alerts


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
    answers = [SimpleNamespace(returncode=0, stdout='ActiveState=active\nNextElapseUSecRealtime=@1762268400\nnoise\n'),
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
        'ActiveState': 'active', 'NextElapseUSecRealtime': '@1762268400'}
    assert runs[0] == ['systemctl', 'show', '--timestamp=unix', '--property=ActiveState',
                       '--property=NextElapseUSecRealtime', 'x.timer']
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
    assert 'Unknown (an older install)' in html and 'No run since the board started' in html and 'Renew now' in html
    assert page.logins_card(None) == '' and page.alerts_card(None) == ''
    assert 'Off: no keys' in page.alerts_card({'pushover': False}) and 'Send a test alert' not in page.alerts_card({})
    assert 'sign in with the PIN' in page.alerts_card({'pushover': True}, signed_in=False)


@pytest.mark.parametrize('value, expected', [('@1762264800', 1762264800.0), ('', None), (None, None), ('n/a', None),
                                             ('@junk', '@junk'), ('Wed 2026-11-04 09:00:00 EST', 'Wed 2026-11-04 09:00:00 EST')])
def test_systemd_times_become_epoch_seconds(value, expected):
    assert server.unix_time(value) == expected


def test_renewal_rows_for_each_state():
    html = page.renewal_status({'last_run': 1762264800.0, 'last_result': 'success', 'mode': 'none'})
    assert '<span class="pill ok">Last run worked</span>' in html and 'Off: automatic renewal' in html
    html = page.renewal_status({'last_run': 'Wed 09:00', 'last_result': None})
    assert 'Last run failed</span>' in html and '<dd>Wed 09:00 &middot; failed</dd>' in html, "an old systemd's text"
    assert re.search(r'id="logins"', page.settings_page({}, logins={'riders': [], 'seed': 'x'}))


@pytest.mark.parametrize('value, seconds', [
    ('2h 5min 3.5s', 7503.5), ('1d 30min', 88200.0), ('1w', 604800.0), ('750ms', 0.75), ('3min 200us', 180.0002),
    ('', None), (None, None), ('0', None), ('infinity', None), ('n/a', None), ('5 parsecs', None),
])
def test_systemd_timespans_become_seconds(value, seconds):
    found = server.timespan_seconds(value)
    assert found == pytest.approx(seconds) if seconds is not None else found is None


def test_a_timer_counted_from_boot_still_says_when_it_next_runs(tmp_path):
    # PelotonPi, 2026-11-05: OnBootSec/OnUnitActiveSec timers leave NextElapseUSecRealtime blank, so
    # the card said "Not scheduled" while the timer ran. Monotonic time since boot + boot's wall time.
    settings = server.Settings(str(tmp_path / 'config.json'), clock=lambda: 1_000_000.0, monotonic=lambda: 3600.0)
    assert settings.next_elapse({'NextElapseUSecRealtime': '', 'NextElapseUSecMonotonic': '1h 30min'}) == 1_001_800.0
    assert settings.next_elapse({'NextElapseUSecRealtime': '@1762268400'}) == 1762268400.0, 'a calendar timer'
    assert settings.next_elapse({'NextElapseUSecRealtime': '@0', 'NextElapseUSecMonotonic': '0'}) is None
    assert settings.next_elapse({}) is None


def test_the_card_shows_the_next_check_of_a_timer_counted_from_boot(board):
    board.units = {server.RENEW_TIMER: {'ActiveState': 'active', 'NextElapseUSecRealtime': '',
                                        'NextElapseUSecMonotonic': '2h'}}
    board.settings.clock, board.settings.monotonic = (lambda: 1762264800.0), (lambda: 3600.0)
    board.sign_in()
    card = board.request('/')[2].split('id="logins"', 1)[1].split('</section>', 1)[0]
    assert f'<dt>Next check</dt><dd>{logins.when(1762268400, ZONE)}</dd>' in card
    assert 'Not scheduled' not in card


def test_a_token_problem_says_what_it_means_and_keeps_its_capitals():
    from settings_page.logins import RiderLogin
    import dataclasses
    fields = {f.name: None for f in dataclasses.fields(RiderLogin)}
    login = RiderLogin(**{**fields, 'key': '0', 'name': 'Joel', 'token': {'ok': False, 'reason': 'JWT payload has no usable exp claim'},
                          'chain': None, 'padlock': None, 'browser_attempt': None, 'email_set': True,
                          'password_set': True})
    html = page._login_status(login, {'mode': 'browser'}, None)
    assert '<span class="k">Token</span><span>The token file can&#x27;t be used (JWT payload has no usable exp claim)</span>' in html, 'JWT, not Jwt'
    assert html.startswith('<details class="rider-card" open>'), 'no working token: it opens by itself'
    missing = dataclasses.replace(login, token={'ok': False, 'reason': 'file does not exist'})
    assert '<span>No token on this board yet</span>' in page._login_status(missing, {'mode': 'browser'}, None)


ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_the_cards_interval_and_renewal_window_are_the_units_own():
    timer = (ROOT / 'packaging' / 'systemd' / 'peloton-token-refresh.timer').read_text()
    service = (ROOT / 'packaging' / 'systemd' / 'peloton-token-refresh.service').read_text()
    assert f'OnUnitActiveSec={logins.CHECK_EVERY_S // 3600}h\n' in timer
    assert f'--renew-before-hours {logins.RENEW_BEFORE_S // 3600} ' in service


@pytest.mark.parametrize('expires, next_check, expected', [
    (100_000, 40_000, 58_000),  # due at 56_800: the first hourly check from 40_000 at or after it
    (100_000, 60_000, 60_000),  # already due: the next check
    (100_000, 56_800, 56_800),  # due exactly at a check
    (100_000, None, 56_800),    # no timer running: when it becomes due
])
def test_a_token_renews_at_the_first_check_within_twelve_hours_of_expiring(expires, next_check, expected):
    assert logins.renews_at({'ok': True, 'expires_at': expires}, next_check) == expected


def test_a_token_without_an_expiry_has_no_renewal_time():
    assert logins.renews_at({'ok': False, 'reason': 'file is empty'}, 1000) is None
    assert logins.renews_at({'ok': True}, 1000) is None


def _rider(name, expires, chain='refresh chain 3 days old'):
    import dataclasses
    from settings_page.logins import RiderLogin
    fields = {f.name: None for f in dataclasses.fields(RiderLogin)}
    return RiderLogin(**{**fields, 'key': name.lower(), 'name': name, 'chain': chain, 'email_set': False,
                         'password_set': False, 'token': {'ok': True, 'expires_at': expires, 'expired': False}})


def test_the_card_shows_the_interval_and_when_each_token_renews():
    next_check = 1762400000.0
    view = {'mode': 'no-browser', 'timer_next': next_check, 'display_running': True, 'seed': 'x',
            'riders': [_rider('Joel', next_check + 30 * 3600), _rider('Jen', next_check + 14 * 3600)]}
    html = page.logins_card(view, zone=ZONE)
    assert '<dt>Interval</dt><dd>Every hour <span class="hint">&middot; each check renews only tokens within 12 hours' in html
    assert f'<dt>Next check</dt><dd>{logins.when(next_check, ZONE)}</dd>' in html
    jen = logins.when(next_check + 2 * 3600, ZONE)  # due 2 hours after the next check, on a check
    joel = logins.when(next_check + 18 * 3600, ZONE)
    assert (f'<dt>Next renewal</dt><dd>Around {jen} <span class="hint">&middot; Jen\'s token, 12 hours before '
            'it expires</span></dd>') in html, 'the soonest rider'
    assert f'<span class="k">Renews</span><span>Around {jen} \u00b7 12 hours before it expires</span>' in html
    assert f'<span class="what">Renews around {joel}</span>' in html, 'on the closed card\'s line'


def test_with_no_check_scheduled_it_renews_at_the_first_check_after_its_due():
    view = {'mode': 'no-browser', 'timer_next': None, 'display_running': False, 'seed': 'x',
            'riders': [_rider('Joel', 1762400000.0 + 13 * 3600)]}
    html = page.logins_card(view, zone=ZONE)
    due = logins.when(1762400000.0 + 3600, ZONE)
    assert '<dt>Interval</dt><dd>Every hour while the display is on' in html
    assert f'<dt>Next renewal</dt><dd>At the first check after {due}' in html


def test_no_renewal_time_without_a_way_to_renew():
    no_refresh = {'mode': 'no-browser', 'timer_next': 1762400000.0, 'seed': 'x',
                  'riders': [_rider('Joel', 1762400000.0 + 5 * 3600, chain=None)]}
    assert 'Next renewal' not in page.logins_card(no_refresh) and 'Renews ' not in page.logins_card(no_refresh)
    browser = {**no_refresh, 'mode': 'browser'}
    assert 'Next renewal' in page.logins_card(browser), 'a browser board signs in without a refresh token'
    off = {**no_refresh, 'mode': 'none'}
    assert 'Next renewal' not in page.logins_card(off) and '<dt>Interval</dt>' not in page.logins_card(off)


def test_the_remove_keys_button_removes_both_and_says_so(board):
    board.auth_env.write_text(board.auth_env.read_text() + 'PUSHOVER_APP_TOKEN="t"\nPUSHOVER_USER_KEY="u"\n')
    board.sign_in()
    status, headers, _ = board.request('/credentials', {'card': 'alerts', 'pushover_clear': 'on'})
    assert headers['Location'] == '/?alerts=alerts_removed#alerts'
    saved = read_auth_env(board.auth_env)
    assert 'PUSHOVER_APP_TOKEN' not in saved and 'PUSHOVER_USER_KEY' not in saved
    assert saved['PELOTON_PASSWORD_RIDER_ONE'] == SECRETS['PELOTON_PASSWORD_RIDER_ONE'], 'logins untouched'
    alerts = board.request('/?alerts=alerts_removed')[2].split('id="alerts"', 1)[1].split('</section>', 1)[0]
    assert 'Pushover keys removed.' in alerts and 'Remove keys' not in alerts, 'nothing left to remove'


def test_without_a_pin_session_there_is_no_remove_button():
    html = page.alerts_card({'pushover': True}, signed_in=False)
    assert 'Send a test alert' in html and 'Remove keys' not in html
