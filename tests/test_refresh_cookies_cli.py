"""refresh_cookies.py's command line and remaining helpers, with Peloton mocked."""
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts import refresh_cookies
from scripts.refresh_cookies import (ensure_all_tokens, ensure_token, load_auth, seed_tokens,
                                     token_status, verify_token)


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    # main() reads a local .env; keep the developer's real credentials out of tests.
    monkeypatch.setattr(refresh_cookies, 'load_dotenv', lambda *a, **k: None)
    for name in ('PELOTON_EMAIL', 'PELOTON_PASSWORD'):
        monkeypatch.delenv(name, raising=False)


def run(monkeypatch, *argv):
    monkeypatch.setattr('sys.argv', ['refresh_cookies.py', *map(str, argv)])
    refresh_cookies.main()


@pytest.mark.parametrize('argv', [
    ['--seed-dir', 'x', '--ensure'], ['--ensure', '--verify-only'], ['--status', '--ensure'],
    ['--all-users'], ['--ensure', '--renew-before-hours', '-1'], ['--ensure', '--renew-before-hours', 'nan'],
])
def test_conflicting_flags_are_usage_errors(monkeypatch, argv, capsys):
    with pytest.raises(SystemExit) as exit_info:
        run(monkeypatch, *argv)
    assert exit_info.value.code == 2
    assert 'error:' in capsys.readouterr().err


def test_verify_only(monkeypatch, tmp_path, capsys):
    with patch.object(refresh_cookies, 'verify_token', return_value='rider'):
        run(monkeypatch, '--verify-only', '--cookies', tmp_path / 'c.txt')
    assert 'logged in as: rider' in capsys.readouterr().out
    with patch.object(refresh_cookies, 'verify_token', side_effect=RuntimeError('401')):
        with pytest.raises(SystemExit, match='Token verification failed: 401'):
            run(monkeypatch, '--verify-only', '--cookies', tmp_path / 'c.txt')


def test_seed_dir_prints_install_steps(monkeypatch, tmp_path, capsys):
    seeded = [('Joel', tmp_path / 'seed' / 'cookies-joel.txt')]
    with patch.object(refresh_cookies, 'seed_tokens', return_value=seeded) as seed:
        run(monkeypatch, '--seed-dir', tmp_path / 'seed', '--no-headless')
    assert seed.call_args.kwargs == {'headless': False}
    out = capsys.readouterr().out
    assert 'cookies-joel.txt cookies-joel.refresh.json' in out
    assert 'ONE board only' in out


def test_seed_dir_without_hint_and_failure(monkeypatch, tmp_path, capsys):
    with patch.object(refresh_cookies, 'seed_tokens', return_value=[]):
        run(monkeypatch, '--seed-dir', tmp_path, '--no-install-hint')
    assert capsys.readouterr().out == ''
    with patch.object(refresh_cookies, 'seed_tokens', side_effect=RuntimeError('no refresh token')):
        with pytest.raises(SystemExit, match='Seeding failed: no refresh token'):
            run(monkeypatch, '--seed-dir', tmp_path)


def test_ensure_all_users_prints_each_profile(monkeypatch, tmp_path, capsys):
    results = [('Joel', 'joel', True), ('Jen', 'jen', False)]
    with patch.object(refresh_cookies, 'ensure_all_tokens', return_value=results), \
         patch.object(refresh_cookies, 'report_outcome') as report:
        run(monkeypatch, '--ensure', '--all-users', '--cookies', tmp_path / 'cookies.txt')
    out = capsys.readouterr().out
    assert 'Joel: token refreshed' in out and 'Jen: token already valid' in out
    assert report.call_args.args[1] is None


def test_status_all_users_reports_problems(monkeypatch, tmp_path, capsys):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'users': [{'name': 'Joel'}]}))
    run(monkeypatch, '--status', '--all-users', '--config', config)
    assert 'Joel: ' in capsys.readouterr().out


def test_status_expired_without_refresh_token(monkeypatch, tmp_path, capsys):
    import base64
    payload = base64.urlsafe_b64encode(json.dumps({'exp': 1}).encode()).decode().rstrip('=')
    token = tmp_path / 'cookies.txt'
    token.write_text(f'h.{payload}.s')
    run(monkeypatch, '--status', '--cookies', token)
    out = capsys.readouterr().out
    assert 'EXPIRED' in out and 'no refresh token' in out


def test_interactive_login(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv('PELOTON_EMAIL', 'rider@example.com')
    monkeypatch.setenv('PELOTON_PASSWORD', 'secret')
    with patch.object(refresh_cookies, 'browser_login', return_value='rider') as login:
        run(monkeypatch, '--cookies', tmp_path / 'c.txt', '--config', tmp_path / 'none.json')
    assert login.call_args.kwargs == {'headless': True}
    assert 'logged in as: rider' in capsys.readouterr().out
    with patch.object(refresh_cookies, 'browser_login', side_effect=RuntimeError('captcha')):
        with pytest.raises(SystemExit, match='captcha'):
            run(monkeypatch, '--cookies', tmp_path / 'c.txt', '--config', tmp_path / 'none.json')


def test_interactive_login_needs_email_and_password(monkeypatch, tmp_path):
    monkeypatch.setattr('builtins.input', lambda prompt: '')
    with pytest.raises(SystemExit, match='no email'):
        run(monkeypatch, '--config', tmp_path / 'none.json')
    monkeypatch.setattr('builtins.input', lambda prompt: 'rider@example.com')
    monkeypatch.setattr(refresh_cookies.getpass, 'getpass', lambda prompt: '')
    with pytest.raises(SystemExit, match='no password'):
        run(monkeypatch, '--config', tmp_path / 'none.json')


def test_load_auth_prefers_env_then_config_then_prompts(monkeypatch, tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'auth': {'email': 'cfg@example.com', 'password': 'cfg'}}))
    assert load_auth(config) == ('cfg@example.com', 'cfg')
    monkeypatch.setenv('PELOTON_EMAIL', 'env@example.com')
    assert load_auth(config)[0] == 'env@example.com'
    monkeypatch.setattr('builtins.input', lambda prompt: ' typed@example.com ')
    monkeypatch.setattr(refresh_cookies.getpass, 'getpass', lambda prompt: 'typed')
    monkeypatch.delenv('PELOTON_EMAIL')
    assert load_auth(tmp_path / 'missing.json') == ('typed@example.com', 'typed')
    assert load_auth(tmp_path / 'missing.json', interactive=False) == ('', '')


@pytest.mark.parametrize('body,expected', [
    ({'username': 'rider', 'email': 'e'}, 'rider'), ({'email': 'e@x'}, 'e@x'),
    ({'id': 'u1'}, 'u1'), ({}, 'unknown'),
])
def test_verify_token_names_the_account(tmp_path, body, expected):
    token = tmp_path / 'cookies.txt'
    token.write_text('t')
    session = MagicMock()
    session.get.return_value.json.return_value = body
    with patch.object(refresh_cookies, 'make_session', return_value=session):
        assert verify_token(token) == expected
    session.close.assert_called_once()


def test_verify_token_closes_the_session_on_failure(tmp_path):
    session = MagicMock()
    session.get.side_effect = requests.ConnectionError('offline')
    with patch.object(refresh_cookies, 'make_session', return_value=session):
        with pytest.raises(requests.ConnectionError):
            verify_token(tmp_path / 'cookies.txt')
    session.close.assert_called_once()


def test_ensure_server_error_is_not_treated_as_login(tmp_path):
    response = requests.Response()
    response.status_code = 503
    with patch.object(refresh_cookies, 'verify_token', side_effect=requests.HTTPError(response=response)), \
         patch.object(refresh_cookies, 'renew_with_refresh_token') as renew:
        with pytest.raises(requests.HTTPError):
            ensure_token(tmp_path / 'cookies.txt', tmp_path / 'config.json')
    renew.assert_not_called()


def test_ensure_all_tokens_without_users_uses_the_fallback(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text('{}')
    with patch.object(refresh_cookies, 'ensure_token', return_value=('rider', False)) as ensure:
        assert ensure_all_tokens(config, fallback_token=tmp_path / 'c.txt') == [('default', 'rider', False)]
    assert ensure.call_args.args[0] == tmp_path / 'c.txt'


def test_token_status_reports_an_undecodable_payload(tmp_path):
    token = tmp_path / 'cookies.txt'
    token.write_text('h.!!!!.s')
    assert 'did not decode' in token_status(token)['reason']


def test_seed_needs_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr('builtins.input', lambda prompt: '')
    monkeypatch.setattr(refresh_cookies.getpass, 'getpass', lambda prompt: '')
    with patch.object(refresh_cookies, 'browser_login') as login:
        with pytest.raises(RuntimeError, match='No credentials for default'):
            seed_tokens(tmp_path / 'seed', tmp_path / 'missing.json')
    login.assert_not_called()
