import stat
import time
from unittest.mock import patch
import pytest
import requests
from scripts.refresh_cookies import (ensure_all_tokens, ensure_token, save_verified_token,
                                     token_expiration)


def test_failed_verification_preserves_old_token(tmp_path):
    token = tmp_path / 'token'
    token.write_text('old-synthetic')
    with patch('scripts.refresh_cookies.verify_token', side_effect=ValueError('invalid')):
        with pytest.raises(ValueError):
            save_verified_token('new-synthetic', token)
    assert token.read_text() == 'old-synthetic'
    assert list(tmp_path.iterdir()) == [token]


def test_successful_save_is_private_and_verified_before_replacement(tmp_path):
    token = tmp_path / 'token'
    token.write_text('old-synthetic')
    def verify(path):
        assert token.read_text() == 'old-synthetic'
        assert path.read_text() == 'new-synthetic'
        return 'demo'
    with patch('scripts.refresh_cookies.verify_token', side_effect=verify):
        assert save_verified_token('new-synthetic', token) == 'demo'
    assert token.read_text() == 'new-synthetic'
    assert stat.S_IMODE(token.stat().st_mode) == 0o600
    assert list(tmp_path.iterdir()) == [token]


def test_ensure_does_not_open_browser_for_valid_token(tmp_path):
    token = tmp_path / 'token'
    token.write_text('valid')
    with patch('scripts.refresh_cookies.verify_token', return_value='demo'), \
         patch('scripts.refresh_cookies.browser_login') as login:
        assert ensure_token(token, tmp_path / 'config.json') == ('demo', False)
    login.assert_not_called()


def test_ensure_renews_valid_token_with_less_than_12_hours_left(tmp_path, monkeypatch):
    token = tmp_path / 'token'
    token.write_text('valid-jwt-placeholder')
    config = tmp_path / 'config.json'
    config.write_text('{}')
    monkeypatch.setenv('PELOTON_EMAIL', 'rider@example.com')
    monkeypatch.setenv('PELOTON_PASSWORD', 'secret')
    with patch('scripts.refresh_cookies.verify_token', return_value='demo'), \
         patch('scripts.refresh_cookies.token_expiration', return_value=time.time() + 11 * 3600), \
         patch('scripts.refresh_cookies.browser_login', return_value='demo') as login:
        assert ensure_token(token, config) == ('demo', True)
    login.assert_called_once_with('rider@example.com', 'secret', token, headless=True)


def test_ensure_keeps_valid_token_with_more_than_12_hours_left(tmp_path):
    token = tmp_path / 'token'
    token.write_text('valid-jwt-placeholder')
    with patch('scripts.refresh_cookies.verify_token', return_value='demo'), \
         patch('scripts.refresh_cookies.token_expiration', return_value=time.time() + 13 * 3600), \
         patch('scripts.refresh_cookies.browser_login') as login:
        assert ensure_token(token, tmp_path / 'config.json') == ('demo', False)
    login.assert_not_called()


def test_token_expiration_reads_jwt_payload(tmp_path):
    import base64
    import json
    token = tmp_path / 'token'
    encoded = base64.urlsafe_b64encode(json.dumps({'exp': 1_800_000_000}).encode()).decode().rstrip('=')
    token.write_text(f'header.{encoded}.signature')
    assert token_expiration(token) == 1_800_000_000


@pytest.mark.parametrize('failure', [requests.ConnectionError('offline'),
                                     requests.Timeout('slow')])
def test_ensure_does_not_open_browser_for_network_failure(tmp_path, failure):
    token = tmp_path / 'token'
    token.write_text('existing')
    with patch('scripts.refresh_cookies.verify_token', side_effect=failure), \
         patch('scripts.refresh_cookies.browser_login') as login:
        with pytest.raises(type(failure)):
            ensure_token(token, tmp_path / 'config.json')
    login.assert_not_called()


def test_ensure_refreshes_after_401(tmp_path, monkeypatch):
    token = tmp_path / 'token'
    token.write_text('rejected')
    config = tmp_path / 'config.json'
    config.write_text('{}')
    monkeypatch.setenv('PELOTON_EMAIL', 'rider@example.com')
    monkeypatch.setenv('PELOTON_PASSWORD', 'secret')
    response = requests.Response()
    response.status_code = 401
    rejected = requests.HTTPError(response=response)
    with patch('scripts.refresh_cookies.verify_token', side_effect=rejected), \
         patch('scripts.refresh_cookies.browser_login', return_value='demo') as login:
        assert ensure_token(token, config) == ('demo', True)
    login.assert_called_once_with('rider@example.com', 'secret', token, headless=True)


def test_ensure_logs_in_when_token_file_does_not_exist_yet(tmp_path, monkeypatch):
    token = tmp_path / 'token'  # never created
    config = tmp_path / 'config.json'
    config.write_text('{}')
    monkeypatch.setenv('PELOTON_EMAIL', 'rider@example.com')
    monkeypatch.setenv('PELOTON_PASSWORD', 'secret')
    with patch('scripts.refresh_cookies.browser_login', return_value='demo') as login:
        assert ensure_token(token, config) == ('demo', True)
    login.assert_called_once_with('rider@example.com', 'secret', token, headless=True)


def test_ensure_rejected_token_requires_unattended_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv('PELOTON_EMAIL', raising=False)
    monkeypatch.delenv('PELOTON_PASSWORD', raising=False)
    token = tmp_path / 'token'
    token.write_text('rejected')
    response = requests.Response()
    response.status_code = 401
    with patch('scripts.refresh_cookies.verify_token',
               side_effect=requests.HTTPError(response=response)):
        with pytest.raises(RuntimeError, match='credentials'):
            ensure_token(token, tmp_path / 'missing.json')


def test_ensure_all_tokens_uses_isolated_paths_and_credentials(tmp_path, monkeypatch):
    import json
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'users': [
        {'name': 'Rider One', 'token_path': 'one.token'},
        {'name': 'Rider Two', 'token_path': 'two.token',
         'email_env': 'SECOND_EMAIL', 'password_env': 'SECOND_PASSWORD'},
    ]}))
    monkeypatch.setenv('PELOTON_EMAIL_RIDER_ONE', 'one@example.com')
    monkeypatch.setenv('PELOTON_PASSWORD_RIDER_ONE', 'one-secret')
    monkeypatch.setenv('SECOND_EMAIL', 'two@example.com')
    monkeypatch.setenv('SECOND_PASSWORD', 'two-secret')
    with patch('scripts.refresh_cookies.ensure_token', side_effect=[
            ('one-user', False), ('two-user', True)]) as ensure:
        results = ensure_all_tokens(config)
    assert results == [('Rider One', 'one-user', False), ('Rider Two', 'two-user', True)]
    assert ensure.call_args_list[0].args[:2] == (tmp_path / 'one.token', config)
    assert ensure.call_args_list[0].kwargs['email'] == 'one@example.com'
    assert ensure.call_args_list[1].args[:2] == (tmp_path / 'two.token', config)
    assert ensure.call_args_list[1].kwargs['password'] == 'two-secret'


def test_ensure_all_tokens_derives_token_path_from_name_when_omitted(tmp_path, monkeypatch):
    import json
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'users': [{'name': 'Joel'}, {'name': 'Jen'}]}))
    monkeypatch.setenv('PELOTON_EMAIL_JOEL', 'joel@example.com')
    monkeypatch.setenv('PELOTON_PASSWORD_JOEL', 'joel-secret')
    monkeypatch.setenv('PELOTON_EMAIL_JEN', 'jen@example.com')
    monkeypatch.setenv('PELOTON_PASSWORD_JEN', 'jen-secret')
    with patch('scripts.refresh_cookies.ensure_token', side_effect=[
            ('joel-user', False), ('jen-user', False)]) as ensure:
        ensure_all_tokens(config)
    assert ensure.call_args_list[0].args[0] == tmp_path / 'cookies-joel.txt'
    assert ensure.call_args_list[1].args[0] == tmp_path / 'cookies-jen.txt'


def test_all_user_renewal_attempts_later_profiles_after_one_failure(tmp_path):
    import json
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'users': [
        {'name': 'One', 'token_path': 'one.token'},
        {'name': 'Two', 'token_path': 'two.token'},
    ]}))
    with patch('scripts.refresh_cookies.ensure_token',
               side_effect=[RuntimeError('first failed'), ('two-user', False)]) as ensure:
        with pytest.raises(RuntimeError, match='One'):
            ensure_all_tokens(config)
    assert ensure.call_count == 2
