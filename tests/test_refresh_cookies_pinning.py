"""Pins for refresh_cookies.main and _ensure_token: every outcome, with Peloton mocked."""

import time
from unittest.mock import patch

import pytest
import requests

from scripts import refresh_cookies
from scripts.refresh_cookies import LoginRequired, RefreshTokenRejected, _ensure_token, browser_attempt_path, refresh_token_path


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    monkeypatch.setattr(refresh_cookies, 'load_dotenv', lambda *a, **k: None)
    for name in ('PELOTON_EMAIL', 'PELOTON_PASSWORD'):
        monkeypatch.delenv(name, raising=False)


def run(monkeypatch, *argv):
    monkeypatch.setattr('sys.argv', ['refresh_cookies.py', *map(str, argv)])
    refresh_cookies.main()


def http_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(response=response)


# ---- _ensure_token ----


def test_valid_token_far_from_expiry_is_left_alone(tmp_path):
    with (
        patch.object(refresh_cookies, 'verify_token', return_value='rider'),
        patch.object(refresh_cookies, 'token_expiration', return_value=time.time() + 10 * 86400),
    ):
        assert _ensure_token(tmp_path / 'c.txt', tmp_path / 'config.json') == ('rider', False)


def test_valid_token_without_expiry_is_left_alone(tmp_path):
    with (
        patch.object(refresh_cookies, 'verify_token', return_value='rider'),
        patch.object(refresh_cookies, 'token_expiration', return_value=None),
    ):
        assert _ensure_token(tmp_path / 'c.txt', tmp_path / 'config.json') == ('rider', False)


def test_http_error_without_response_is_raised(tmp_path):
    with patch.object(refresh_cookies, 'verify_token', side_effect=requests.HTTPError()):
        with pytest.raises(requests.HTTPError):
            _ensure_token(tmp_path / 'c.txt', tmp_path / 'config.json')


@pytest.mark.parametrize('failure', [FileNotFoundError('none'), ValueError('empty'), http_error(401)])
def test_missing_empty_or_rejected_token_goes_on_to_renewal(tmp_path, failure):
    token = tmp_path / 'c.txt'
    refresh_token_path(token).write_text('{}')
    with (
        patch.object(refresh_cookies, 'verify_token', side_effect=failure),
        patch.object(refresh_cookies, 'renew_with_refresh_token', return_value='rider') as renew,
    ):
        assert _ensure_token(token, tmp_path / 'config.json') == ('rider', True)
    renew.assert_called_once_with(token)


def test_near_expiry_token_is_renewed(tmp_path):
    token = tmp_path / 'c.txt'
    refresh_token_path(token).write_text('{}')
    with (
        patch.object(refresh_cookies, 'verify_token', return_value='rider'),
        patch.object(refresh_cookies, 'token_expiration', return_value=time.time() + 60),
        patch.object(refresh_cookies, 'renew_with_refresh_token', return_value='rider2'),
    ):
        assert _ensure_token(token, tmp_path / 'config.json') == ('rider2', True)


@pytest.fixture
def rejected_setup(tmp_path):
    token = tmp_path / 'c.txt'
    refresh_token_path(token).write_text('{}')
    with (
        patch.object(refresh_cookies, 'verify_token', side_effect=http_error(401)),
        patch.object(refresh_cookies, 'renew_with_refresh_token', side_effect=RefreshTokenRejected('Rejected.')),
    ):
        yield token


def test_rejected_without_credentials_reraises(rejected_setup, tmp_path):
    with (
        patch.object(refresh_cookies, 'load_auth', return_value=('', '')) as load,
        pytest.raises(RefreshTokenRejected, match='^Rejected.$'),
    ):
        _ensure_token(rejected_setup, tmp_path / 'config.json')
    load.assert_called_once_with(tmp_path / 'config.json', interactive=False)


def test_rejected_with_given_credentials_does_not_load_config(rejected_setup, tmp_path):
    with (
        patch.object(refresh_cookies, 'load_auth') as load,
        patch.object(refresh_cookies, 'browser_login_available', return_value=False),
        pytest.raises(RefreshTokenRejected, match='^Rejected.$'),
    ):
        _ensure_token(rejected_setup, tmp_path / 'config.json', email='e', password='p')
    load.assert_not_called()


def test_rejected_without_loading_credentials_reraises(rejected_setup, tmp_path):
    with patch.object(refresh_cookies, 'load_auth') as load, pytest.raises(RefreshTokenRejected, match='^Rejected.$'):
        _ensure_token(rejected_setup, tmp_path / 'config.json', load_credentials=False)
    load.assert_not_called()


def test_rejected_with_credentials_but_no_browser_reraises(rejected_setup, tmp_path):
    with (
        patch.object(refresh_cookies, 'load_auth', return_value=('e', 'p')),
        patch.object(refresh_cookies, 'browser_login_available', return_value=False),
        pytest.raises(RefreshTokenRejected, match='^Rejected.$'),
    ):
        _ensure_token(rejected_setup, tmp_path / 'config.json')


def test_rejected_after_a_recent_browser_try_says_so(rejected_setup, tmp_path):
    with (
        patch.object(refresh_cookies, 'browser_login_available', return_value=True),
        patch.object(refresh_cookies, 'browser_fallback_due', return_value=False),
        patch.object(refresh_cookies, 'browser_login') as login,
        pytest.raises(RefreshTokenRejected) as caught,
    ):
        _ensure_token(rejected_setup, tmp_path / 'config.json', email='e', password='p')
    assert str(caught.value) == ('Rejected. A browser login was already tried in the last day; the next try is after that.')
    login.assert_not_called()
    assert not browser_attempt_path(rejected_setup).exists()


def test_rejected_falls_back_to_browser_login(rejected_setup, tmp_path, capsys):
    with (
        patch.object(refresh_cookies, 'browser_login_available', return_value=True),
        patch.object(refresh_cookies, 'browser_login', return_value='rider') as login,
    ):
        result = _ensure_token(rejected_setup, tmp_path / 'config.json', headless=False, email='e', password='p')
    assert result == ('rider', True)
    login.assert_called_once_with('e', 'p', rejected_setup, headless=False)
    assert float(browser_attempt_path(rejected_setup).read_text()) > 0
    assert 'Rejected. Trying a browser login instead.' in capsys.readouterr().err


def test_rejected_and_browser_fallback_fails(rejected_setup, tmp_path):
    with (
        patch.object(refresh_cookies, 'browser_login_available', return_value=True),
        patch.object(refresh_cookies, 'browser_login', side_effect=RuntimeError('captcha')),
        pytest.raises(RefreshTokenRejected) as caught,
    ):
        _ensure_token(rejected_setup, tmp_path / 'config.json', email='e', password='p')
    assert str(caught.value) == 'Rejected. The browser login fallback also failed: captcha'
    assert browser_attempt_path(rejected_setup).exists()


def test_other_renewal_errors_propagate(tmp_path):
    token = tmp_path / 'c.txt'
    refresh_token_path(token).write_text('{}')
    with (
        patch.object(refresh_cookies, 'verify_token', side_effect=http_error(401)),
        patch.object(refresh_cookies, 'renew_with_refresh_token', side_effect=requests.ConnectionError('off')),
    ):
        with pytest.raises(requests.ConnectionError):
            _ensure_token(token, tmp_path / 'config.json')


@pytest.fixture
def no_refresh_file(tmp_path):
    with patch.object(refresh_cookies, 'verify_token', side_effect=FileNotFoundError()):
        yield tmp_path / 'c.txt'


def test_no_refresh_file_and_no_browser_needs_seeding(no_refresh_file, tmp_path):
    with (
        patch.object(refresh_cookies, 'browser_login_available', return_value=False),
        pytest.raises(LoginRequired, match='no refresh token at .*c.refresh.json.*--seed-dir'),
    ):
        _ensure_token(no_refresh_file, tmp_path / 'config.json')


def test_no_refresh_file_and_no_credentials(no_refresh_file, tmp_path):
    with (
        patch.object(refresh_cookies, 'browser_login_available', return_value=True),
        patch.object(refresh_cookies, 'load_auth', return_value=('e', '')) as load,
        pytest.raises(LoginRequired, match='unattended Peloton credentials are not configured'),
    ):
        _ensure_token(no_refresh_file, tmp_path / 'config.json')
    load.assert_called_once_with(tmp_path / 'config.json', interactive=False)


def test_no_refresh_file_credentials_not_loaded_when_told_not_to(no_refresh_file, tmp_path):
    with (
        patch.object(refresh_cookies, 'browser_login_available', return_value=True),
        patch.object(refresh_cookies, 'load_auth') as load,
        pytest.raises(LoginRequired, match='not configured'),
    ):
        _ensure_token(no_refresh_file, tmp_path / 'config.json', load_credentials=False)
    load.assert_not_called()


def test_no_refresh_file_logs_in_with_browser(no_refresh_file, tmp_path):
    with (
        patch.object(refresh_cookies, 'browser_login_available', return_value=True),
        patch.object(refresh_cookies, 'load_auth', return_value=('e', 'p')),
        patch.object(refresh_cookies, 'browser_login', return_value='rider') as login,
    ):
        assert _ensure_token(no_refresh_file, tmp_path / 'config.json', headless=False) == ('rider', True)
    login.assert_called_once_with('e', 'p', no_refresh_file, headless=False)
    assert not browser_attempt_path(no_refresh_file).exists()


# ---- main ----


def valid_status(path):
    return {'ok': True, 'path': str(path), 'expired': False, 'expires_at': 4102444800}


def test_status_valid_token_with_refresh_token(monkeypatch, tmp_path, capsys):
    token = tmp_path / 'c.txt'
    refresh_token_path(token).write_text('{}')
    with (
        patch.object(refresh_cookies, 'token_status', return_value=valid_status(token)),
        patch.object(refresh_cookies, 'load_refresh_chain', return_value={}),
        patch.object(refresh_cookies, 'describe_chain', return_value='chain text'),
    ):
        run(monkeypatch, '--status', '--cookies', token)
    assert capsys.readouterr().out == (f'default: {token} — valid, expires 2100-01-01T00:00:00+00:00; refresh token saved (chain text)\n')


def test_status_unreadable_token_line(monkeypatch, tmp_path, capsys):
    status = {'ok': False, 'path': 'p', 'reason': 'unreadable'}
    with patch.object(refresh_cookies, 'token_status', return_value=status):
        run(monkeypatch, '--status', '--cookies', tmp_path / 'c.txt')
    assert capsys.readouterr().out == 'default: p — unreadable\n'


def test_status_all_users_lists_each_profile(monkeypatch, tmp_path, capsys):
    profiles = [('Joel', tmp_path / 'a'), ('Jen', tmp_path / 'b')]
    with (
        patch.object(refresh_cookies, 'resolve_token_paths', return_value=profiles),
        patch.object(refresh_cookies, 'token_status', side_effect=lambda p: {'ok': False, 'path': p.name, 'reason': 'x'}),
    ):
        run(monkeypatch, '--status', '--all-users')
    assert capsys.readouterr().out == 'Joel: a — x\nJen: b — x\n'


def test_ensure_single_token_reports_success(monkeypatch, tmp_path, capsys):
    with (
        patch.object(refresh_cookies, 'ensure_token', return_value=('rider', True)) as ensure,
        patch.object(refresh_cookies, 'report_outcome') as report,
        patch.object(refresh_cookies.socket, 'gethostname', return_value='board'),
    ):
        run(monkeypatch, '--ensure', '--cookies', tmp_path / 'c.txt', '--renew-before-hours', '2')
    assert capsys.readouterr().out == 'Token refreshed — logged in as: rider\n'
    assert ensure.call_args.kwargs == {'headless': True, 'renew_before_seconds': 7200.0}
    args = report.call_args.args
    assert args[0] == tmp_path / refresh_cookies.ALERT_STATE_NAME and args[1] is None and args[3] == 'board'


def test_ensure_single_token_already_valid(monkeypatch, tmp_path, capsys):
    with patch.object(refresh_cookies, 'ensure_token', return_value=('rider', False)), patch.object(refresh_cookies, 'report_outcome'):
        run(monkeypatch, '--ensure', '--cookies', tmp_path / 'c.txt')
    assert capsys.readouterr().out == 'Token already valid — logged in as: rider\n'


@pytest.mark.parametrize('extra,target', [([], 'ensure_token'), (['--all-users'], 'ensure_all_tokens')])
def test_ensure_failure_reports_and_exits(monkeypatch, tmp_path, extra, target):
    with (
        patch.object(refresh_cookies, target, side_effect=RuntimeError('boom')),
        patch.object(refresh_cookies, 'report_outcome') as report,
        patch.object(refresh_cookies.socket, 'gethostname', return_value='board'),
    ):
        with pytest.raises(SystemExit, match='^Token maintenance failed: boom$'):
            run(monkeypatch, '--ensure', *extra, '--cookies', tmp_path / 'c.txt')
    report.assert_called_once()
    assert report.call_args.args[1] == 'boom' and report.call_args.args[3] == 'board'


def test_ensure_all_users_passes_options_through(monkeypatch, tmp_path):
    with patch.object(refresh_cookies, 'ensure_all_tokens', return_value=[]) as ensure_all, patch.object(refresh_cookies, 'report_outcome'):
        run(
            monkeypatch,
            '--ensure',
            '--all-users',
            '--cookies',
            tmp_path / 'c.txt',
            '--config',
            tmp_path / 'cfg.json',
            '--renew-before-hours',
            '1',
        )
    assert ensure_all.call_args.args == (tmp_path / 'cfg.json',)
    assert ensure_all.call_args.kwargs == {'renew_before_seconds': 3600.0, 'fallback_token': tmp_path / 'c.txt'}


def test_verify_only_prints_progress_and_result(monkeypatch, tmp_path, capsys):
    with patch.object(refresh_cookies, 'verify_token', return_value='rider'):
        run(monkeypatch, '--verify-only', '--cookies', tmp_path / 'c.txt')
    out = capsys.readouterr().out
    assert out == (f'Verifying existing token in {tmp_path / "c.txt"}...\nToken is valid — logged in as: rider\n')


def test_interactive_login_prints_every_step(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv('PELOTON_EMAIL', 'e@x')
    monkeypatch.setenv('PELOTON_PASSWORD', 'p')
    with patch.object(refresh_cookies, 'browser_login', return_value='rider'):
        run(monkeypatch, '--cookies', tmp_path / 'c.txt', '--config', tmp_path / 'none.json', '--no-headless')
    assert capsys.readouterr().out == (f'Logging in...\nToken saved to {tmp_path / "c.txt"}\nToken verified — logged in as: rider\n')
