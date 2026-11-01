import stat
import time
from unittest.mock import MagicMock, patch
import pytest
import requests
from scripts.refresh_cookies import (_dump_failure_diagnostics, browser_login, ensure_all_tokens,
                                     ensure_token, resolve_token_paths, save_verified_token,
                                     token_expiration, token_status)


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


def test_browser_login_uses_a_realistic_desktop_context(tmp_path):
    # A bare new_context() (no viewport/locale/timezone) is an easy bot-
    # detection signal; guard against silently regressing back to that.
    import playwright.sync_api

    page = MagicMock()
    page.url = 'https://www.onepeloton.com/login'
    page.goto.side_effect = playwright.sync_api.TimeoutError('stop after context creation')
    browser = MagicMock()
    browser.new_context.return_value.new_page.return_value = page
    playwright_cm = MagicMock()
    playwright_cm.__enter__.return_value.chromium.launch.return_value = browser

    with patch('playwright.sync_api.sync_playwright', return_value=playwright_cm):
        with pytest.raises(RuntimeError):
            browser_login('rider@example.com', 'secret', tmp_path / 'token')

    context_kwargs = browser.new_context.call_args.kwargs
    assert context_kwargs['viewport'] == {'width': 1920, 'height': 1080}
    assert context_kwargs['locale'] == 'en-US'
    assert context_kwargs['timezone_id']


def test_browser_login_waits_for_the_form_not_network_idle(tmp_path):
    # The members app keeps the network busy; on a Pi Zero 2 W "networkidle"
    # never arrived within 30 s, so login failed before the form was tried.
    import playwright.sync_api
    from scripts.refresh_cookies import FORM_TIMEOUT_MS, TOKEN_TIMEOUT_MS

    page = MagicMock()
    page.url = 'https://members.onepeloton.com/login/'
    page.wait_for_function.side_effect = playwright.sync_api.TimeoutError('no token')
    browser = MagicMock()
    browser.new_context.return_value.new_page.return_value = page
    playwright_cm = MagicMock()
    playwright_cm.__enter__.return_value.chromium.launch.return_value = browser

    with patch('playwright.sync_api.sync_playwright', return_value=playwright_cm):
        with pytest.raises(RuntimeError, match='No access token found after login'):
            browser_login('rider@example.com', 'secret', tmp_path / 'token')
    assert page.goto.call_args.kwargs == {'wait_until': 'domcontentloaded', 'timeout': FORM_TIMEOUT_MS}
    assert FORM_TIMEOUT_MS >= 120_000 and TOKEN_TIMEOUT_MS >= 180_000
    for call in page.locator.return_value.fill.call_args_list + page.locator.return_value.click.call_args_list:
        assert call.kwargs['timeout'] == FORM_TIMEOUT_MS
    assert page.wait_for_function.call_args.kwargs['timeout'] == TOKEN_TIMEOUT_MS


def test_dump_failure_diagnostics_writes_screenshot_and_html(tmp_path):
    token_path = tmp_path / 'cookies-joel.txt'
    page = MagicMock()
    page.content.return_value = '<html>stuck here</html>'
    message = _dump_failure_diagnostics(page, token_path)
    screenshot = tmp_path / 'cookies-joel-login-failure.png'
    html = tmp_path / 'cookies-joel-login-failure.html'
    assert html.read_text() == '<html>stuck here</html>'
    assert page.screenshot.call_args.kwargs['path'] == str(screenshot)
    assert str(screenshot) in message
    assert str(html) in message


def test_dump_failure_diagnostics_never_raises_on_its_own_failure(tmp_path):
    page = MagicMock()
    page.screenshot.side_effect = RuntimeError('browser already closed')
    assert _dump_failure_diagnostics(page, tmp_path / 'token') == ''


def test_browser_login_wraps_timeout_reaching_login_form(tmp_path):
    import playwright.sync_api

    page = MagicMock()
    page.url = 'https://www.onepeloton.com/login'
    page.goto.side_effect = playwright.sync_api.TimeoutError('Timeout 30000ms exceeded')
    browser = MagicMock()
    browser.new_context.return_value.new_page.return_value = page
    playwright_cm = MagicMock()
    playwright_cm.__enter__.return_value.chromium.launch.return_value = browser

    with patch('playwright.sync_api.sync_playwright', return_value=playwright_cm):
        with pytest.raises(RuntimeError, match='Could not reach or fill in the login form'):
            browser_login('rider@example.com', 'secret', tmp_path / 'token')
    browser.close.assert_called_once()


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


def _jwt_with_exp(exp) -> str:
    import base64
    import json
    encoded = base64.urlsafe_b64encode(json.dumps({'exp': exp}).encode()).decode().rstrip('=')
    return f'header.{encoded}.signature'


def test_token_status_reports_missing_file(tmp_path):
    status = token_status(tmp_path / 'missing-token')
    assert status == {'path': str(tmp_path / 'missing-token'), 'ok': False, 'reason': 'file does not exist'}


def test_token_status_reports_unreadable_file(tmp_path):
    token = tmp_path / 'token'
    token.write_text('irrelevant')
    token.chmod(0o000)
    try:
        status = token_status(token)
    finally:
        token.chmod(0o600)
    assert status['ok'] is False
    assert 'cannot read file' in status['reason']


def test_token_status_reports_empty_file(tmp_path):
    token = tmp_path / 'token'
    token.write_text('   ')
    assert token_status(token) == {'path': str(token), 'ok': False, 'reason': 'file is empty'}


def test_token_status_reports_non_jwt_shape(tmp_path):
    token = tmp_path / 'token'
    token.write_text('not-a-jwt-at-all')
    status = token_status(token)
    assert status['ok'] is False
    assert 'not a 3-part JWT' in status['reason']
    assert '1 dot-separated' in status['reason']


def test_token_status_reports_payload_with_no_exp_claim(tmp_path):
    import base64
    import json
    token = tmp_path / 'token'
    encoded = base64.urlsafe_b64encode(json.dumps({'sub': 'rider'}).encode()).decode().rstrip('=')
    token.write_text(f'header.{encoded}.signature')
    status = token_status(token)
    assert status == {'path': str(token), 'ok': False, 'reason': 'JWT payload has no usable exp claim'}


def test_token_status_reports_expired_token(tmp_path):
    token = tmp_path / 'token'
    token.write_text(_jwt_with_exp(time.time() - 3600))
    status = token_status(token)
    assert status['ok'] is True
    assert status['expired'] is True


def test_token_status_reports_valid_token(tmp_path):
    token = tmp_path / 'token'
    expiry = time.time() + 3600
    token.write_text(_jwt_with_exp(expiry))
    status = token_status(token)
    assert status == {'path': str(token), 'ok': True, 'expires_at': expiry, 'expired': False}


def test_resolve_token_paths_without_users_returns_fallback(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text('{}')
    fallback = tmp_path / 'cookies.txt'
    assert resolve_token_paths(config, fallback) == [('default', fallback)]


def test_resolve_token_paths_missing_config_returns_fallback(tmp_path):
    fallback = tmp_path / 'cookies.txt'
    assert resolve_token_paths(tmp_path / 'missing.json', fallback) == [('default', fallback)]


def test_resolve_token_paths_derives_each_users_token_file(tmp_path):
    import json
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'users': [{'name': 'Joel'}, {'name': 'Jen', 'token_path': 'jen.token'}]}))
    resolved = resolve_token_paths(config, tmp_path / 'cookies.txt')
    assert resolved == [('Joel', tmp_path / 'cookies-joel.txt'), ('Jen', tmp_path / 'jen.token')]


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


def test_all_user_renewal_failure_message_is_not_just_the_exception_type(tmp_path):
    import json
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'users': [{'name': 'Joel', 'token_path': 'joel.token'}]}))
    with patch('scripts.refresh_cookies.ensure_token',
               side_effect=RuntimeError('No access token found after login; browser reached '
                                        'www.onepeloton.com/login. The existing token was not changed.')):
        with pytest.raises(RuntimeError, match='browser reached www.onepeloton.com/login'):
            ensure_all_tokens(config)


# --- Refresh-token renewal (no browser) ---------------------------------------

import json as _json
from scripts.refresh_cookies import (AUTH0_CLIENT_ID, AUTH0_TOKEN_URL, RefreshTokenRejected,
                                     browser_login_available, load_refresh_token,
                                     refresh_token_path, renew_with_refresh_token,
                                     save_refresh_token, seed_tokens)


def _token_response(status, body):
    response = requests.Response()
    response.status_code = status
    response._content = body if isinstance(body, bytes) else _json.dumps(body).encode()
    response.url = AUTH0_TOKEN_URL
    return response


def _seeded(tmp_path, refresh='refresh-old', client_id='client-synthetic'):
    token = tmp_path / 'cookies-joel.txt'
    token.write_text('access-old')
    save_refresh_token(refresh_token_path(token), refresh, client_id)
    return token


def test_refresh_token_path_sits_beside_the_access_token(tmp_path):
    assert refresh_token_path(tmp_path / 'cookies-joel.txt') == tmp_path / 'cookies-joel.refresh.json'
    assert refresh_token_path(tmp_path / 'cookies.txt') == tmp_path / 'cookies.refresh.json'


def test_save_refresh_token_is_private_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / 'cookies.refresh.json'
    save_refresh_token(path, 'refresh-synthetic', 'client-synthetic')
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load_refresh_token(path) == ('refresh-synthetic', 'client-synthetic')
    assert list(tmp_path.iterdir()) == [path]


def test_load_refresh_token_defaults_client_id(tmp_path):
    path = tmp_path / 'cookies.refresh.json'
    path.write_text(_json.dumps({'refresh_token': 'refresh-synthetic'}))
    assert load_refresh_token(path) == ('refresh-synthetic', AUTH0_CLIENT_ID)


@pytest.mark.parametrize('content', ['not json', '[]', '{"refresh_token": ""}', '{"client_id": "x"}'])
def test_load_refresh_token_rejects_unusable_files(tmp_path, content):
    path = tmp_path / 'cookies.refresh.json'
    path.write_text(content)
    with pytest.raises(RuntimeError, match='refresh'):
        load_refresh_token(path)


def test_renew_persists_rotated_refresh_token_before_verifying_access_token(tmp_path):
    token = _seeded(tmp_path)
    refresh_file = refresh_token_path(token)

    def verify(path):
        # The old refresh token is already spent; the new one must be on disk
        # before anything else can fail.
        assert load_refresh_token(refresh_file) == ('refresh-new', 'client-synthetic')
        assert path.read_text() == 'access-new'
        return 'demo'

    with patch('scripts.refresh_cookies.requests.post', return_value=_token_response(
            200, {'access_token': 'access-new', 'refresh_token': 'refresh-new', 'expires_in': 172800})) as post, \
         patch('scripts.refresh_cookies.verify_token', side_effect=verify):
        assert renew_with_refresh_token(token) == 'demo'
    assert post.call_args.args == (AUTH0_TOKEN_URL,)
    assert post.call_args.kwargs['json'] == {'grant_type': 'refresh_token',
                                             'client_id': 'client-synthetic',
                                             'refresh_token': 'refresh-old'}
    assert post.call_args.kwargs['timeout'] > 0
    assert token.read_text() == 'access-new'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['cookies-joel.refresh.json', 'cookies-joel.txt']


def test_renew_without_rotation_keeps_the_existing_refresh_token(tmp_path):
    token = _seeded(tmp_path)
    with patch('scripts.refresh_cookies.requests.post',
               return_value=_token_response(200, {'access_token': 'access-new'})), \
         patch('scripts.refresh_cookies.verify_token', return_value='demo'):
        renew_with_refresh_token(token)
    assert load_refresh_token(refresh_token_path(token))[0] == 'refresh-old'


@pytest.mark.parametrize('status', [400, 401, 403])
def test_renew_invalid_grant_raises_rejected_and_changes_nothing(tmp_path, status):
    token = _seeded(tmp_path)
    before = refresh_token_path(token).read_text()
    with patch('scripts.refresh_cookies.requests.post', return_value=_token_response(
            status, {'error': 'invalid_grant', 'error_description': 'Unknown or invalid refresh token.'})):
        with pytest.raises(RefreshTokenRejected, match='seed-dir'):
            renew_with_refresh_token(token)
    assert token.read_text() == 'access-old'
    assert refresh_token_path(token).read_text() == before


def test_renew_other_client_error_is_not_reported_as_rejected(tmp_path):
    token = _seeded(tmp_path)
    with patch('scripts.refresh_cookies.requests.post',
               return_value=_token_response(429, {'error': 'too_many_requests'})):
        with pytest.raises(RuntimeError, match='HTTP 429 \\(too_many_requests\\)') as raised:
            renew_with_refresh_token(token)
    assert not isinstance(raised.value, RefreshTokenRejected)
    assert token.read_text() == 'access-old'


@pytest.mark.parametrize('failure', [requests.ConnectionError('offline'), requests.Timeout('slow')])
def test_renew_network_failure_changes_nothing(tmp_path, failure):
    token = _seeded(tmp_path)
    before = refresh_token_path(token).read_text()
    with patch('scripts.refresh_cookies.requests.post', side_effect=failure):
        with pytest.raises(type(failure)):
            renew_with_refresh_token(token)
    assert token.read_text() == 'access-old'
    assert refresh_token_path(token).read_text() == before


def test_renew_server_error_changes_nothing(tmp_path):
    token = _seeded(tmp_path)
    with patch('scripts.refresh_cookies.requests.post', return_value=_token_response(503, b'<html>down</html>')):
        with pytest.raises(requests.HTTPError):
            renew_with_refresh_token(token)
    assert token.read_text() == 'access-old'


@pytest.mark.parametrize('body', [b'<html>not json</html>', b'[]', b'"text"'])
def test_renew_bad_json_changes_nothing(tmp_path, body):
    token = _seeded(tmp_path)
    with patch('scripts.refresh_cookies.requests.post', return_value=_token_response(200, body)):
        with pytest.raises(RuntimeError, match='non-JSON'):
            renew_with_refresh_token(token)
    assert token.read_text() == 'access-old'
    assert load_refresh_token(refresh_token_path(token))[0] == 'refresh-old'


def test_renew_missing_access_token_still_saves_the_rotated_refresh_token(tmp_path):
    token = _seeded(tmp_path)
    with patch('scripts.refresh_cookies.requests.post',
               return_value=_token_response(200, {'refresh_token': 'refresh-new'})):
        with pytest.raises(RuntimeError, match='no access_token'):
            renew_with_refresh_token(token)
    assert token.read_text() == 'access-old'
    assert load_refresh_token(refresh_token_path(token))[0] == 'refresh-new'


def test_renew_with_missing_refresh_file_raises_without_network(tmp_path):
    token = tmp_path / 'cookies.txt'
    with patch('scripts.refresh_cookies.requests.post') as post:
        with pytest.raises(RuntimeError, match='Cannot read refresh token file'):
            renew_with_refresh_token(token)
    post.assert_not_called()


def _rejected_401():
    response = requests.Response()
    response.status_code = 401
    return requests.HTTPError(response=response)


def test_ensure_uses_refresh_token_instead_of_browser(tmp_path):
    token = _seeded(tmp_path)
    with patch('scripts.refresh_cookies.verify_token', side_effect=_rejected_401()), \
         patch('scripts.refresh_cookies.renew_with_refresh_token', return_value='demo') as renew, \
         patch('scripts.refresh_cookies.browser_login') as login:
        assert ensure_token(token, tmp_path / 'config.json') == ('demo', True)
    renew.assert_called_once_with(token)
    login.assert_not_called()


def test_ensure_renews_near_expiry_with_refresh_token(tmp_path):
    token = _seeded(tmp_path)
    with patch('scripts.refresh_cookies.verify_token', return_value='demo'), \
         patch('scripts.refresh_cookies.token_expiration', return_value=time.time() + 11 * 3600), \
         patch('scripts.refresh_cookies.renew_with_refresh_token', return_value='demo') as renew, \
         patch('scripts.refresh_cookies.browser_login') as login:
        assert ensure_token(token, tmp_path / 'config.json') == ('demo', True)
    renew.assert_called_once_with(token)
    login.assert_not_called()


def test_ensure_never_falls_back_to_browser_after_invalid_grant(tmp_path, monkeypatch):
    # A slow board would just fail a Chromium login every hour; keep the old
    # token and tell the user to re-seed instead.
    token = _seeded(tmp_path)
    monkeypatch.setenv('PELOTON_EMAIL', 'rider@example.com')
    monkeypatch.setenv('PELOTON_PASSWORD', 'secret')
    with patch('scripts.refresh_cookies.verify_token', side_effect=_rejected_401()), \
         patch('scripts.refresh_cookies.renew_with_refresh_token',
               side_effect=RefreshTokenRejected('invalid_grant; seed-dir')), \
         patch('scripts.refresh_cookies.browser_login') as login:
        with pytest.raises(RefreshTokenRejected):
            ensure_token(token, tmp_path / 'config.json')
    login.assert_not_called()
    assert token.read_text() == 'access-old'


def test_ensure_without_refresh_token_or_browser_asks_for_a_seed(tmp_path, monkeypatch):
    token = tmp_path / 'cookies.txt'
    token.write_text('rejected')
    monkeypatch.setenv('PELOTON_EMAIL', 'rider@example.com')
    monkeypatch.setenv('PELOTON_PASSWORD', 'secret')
    with patch('scripts.refresh_cookies.verify_token', side_effect=_rejected_401()), \
         patch('scripts.refresh_cookies.browser_login_available', return_value=False), \
         patch('scripts.refresh_cookies.browser_login') as login:
        with pytest.raises(RuntimeError, match='no refresh token .* --seed-dir'):
            ensure_token(token, tmp_path / 'config.json')
    login.assert_not_called()


def test_browser_login_unavailable_when_configured_chromium_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv('PELOTON_CHROMIUM_EXECUTABLE', str(tmp_path / 'no-chromium'))
    assert browser_login_available() is False
    monkeypatch.delenv('PELOTON_CHROMIUM_EXECUTABLE')
    with patch('scripts.refresh_cookies.importlib.util.find_spec', return_value=None):
        assert browser_login_available() is False


def _logged_in_playwright(credentials):
    page = MagicMock()
    page.url = 'https://members.onepeloton.com/home'
    page.wait_for_function.return_value.json_value.return_value = credentials
    browser = MagicMock()
    browser.new_context.return_value.new_page.return_value = page
    playwright_cm = MagicMock()
    playwright_cm.__enter__.return_value.chromium.launch.return_value = browser
    return playwright_cm


def test_browser_login_saves_the_refresh_token_beside_the_access_token(tmp_path):
    token = tmp_path / 'cookies-joel.txt'
    playwright_cm = _logged_in_playwright({'access_token': 'access-new', 'refresh_token': 'refresh-new',
                                           'client_id': 'client-synthetic'})
    with patch('playwright.sync_api.sync_playwright', return_value=playwright_cm), \
         patch('scripts.refresh_cookies.verify_token', return_value='demo'):
        assert browser_login('rider@example.com', 'secret', token) == 'demo'
    assert token.read_text() == 'access-new'
    assert load_refresh_token(refresh_token_path(token)) == ('refresh-new', 'client-synthetic')
    assert stat.S_IMODE(refresh_token_path(token).stat().st_mode) == 0o600


def test_browser_login_without_refresh_token_still_saves_access_token(tmp_path, capsys):
    token = tmp_path / 'cookies.txt'
    playwright_cm = _logged_in_playwright({'access_token': 'access-new', 'refresh_token': None,
                                           'client_id': None})
    with patch('playwright.sync_api.sync_playwright', return_value=playwright_cm), \
         patch('scripts.refresh_cookies.verify_token', return_value='demo'):
        browser_login('rider@example.com', 'secret', token)
    assert token.read_text() == 'access-new'
    assert not refresh_token_path(token).exists()
    assert 'no refresh token' in capsys.readouterr().err


def test_seed_tokens_writes_one_pair_per_rider_under_board_file_names(tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    config.write_text(_json.dumps({'users': [
        {'name': 'Joel', 'token_path': '/var/lib/peloton-led/cookies-joel.txt'},
        {'name': 'Jen'},
    ]}))
    for name in ('JOEL', 'JEN'):
        monkeypatch.setenv(f'PELOTON_EMAIL_{name}', f'{name.lower()}@example.com')
        monkeypatch.setenv(f'PELOTON_PASSWORD_{name}', 'secret')

    def fake_login(email, password, token_path, headless=True):
        token_path.write_text('access')
        save_refresh_token(refresh_token_path(token_path), 'refresh', 'client')
        return email

    seed_dir = tmp_path / 'seed'
    with patch('scripts.refresh_cookies.browser_login', side_effect=fake_login) as login:
        seeded = seed_tokens(seed_dir, config)
    assert seeded == [('Joel', seed_dir / 'cookies-joel.txt'), ('Jen', seed_dir / 'cookies-jen.txt')]
    assert [call.args[0] for call in login.call_args_list] == ['joel@example.com', 'jen@example.com']
    assert stat.S_IMODE(seed_dir.stat().st_mode) == 0o700


def test_seed_tokens_fails_when_login_gives_no_refresh_token(tmp_path, monkeypatch):
    monkeypatch.setenv('PELOTON_EMAIL', 'rider@example.com')
    monkeypatch.setenv('PELOTON_PASSWORD', 'secret')
    with patch('scripts.refresh_cookies.browser_login', return_value='demo'):
        with pytest.raises(RuntimeError, match='no refresh token'):
            seed_tokens(tmp_path / 'seed', tmp_path / 'missing.json')


def test_seed_dir_install_hint_can_be_suppressed_for_seed_board(tmp_path, monkeypatch, capsys):
    import sys as _sys
    from scripts import refresh_cookies
    seeded = [('Joel', tmp_path / 'cookies-joel.txt')]
    for hint, expected in ((['--no-install-hint'], False), ([], True)):
        monkeypatch.setattr(_sys, 'argv', ['refresh_cookies.py', '--seed-dir', str(tmp_path), *hint])
        with patch('scripts.refresh_cookies.seed_tokens', return_value=seeded):
            refresh_cookies.main()
        assert ('sudo install' in capsys.readouterr().out) is expected


# Refresh-chain age: learn how long Auth0 keeps a login's chain alive.
from datetime import datetime as _datetime, timedelta as _timedelta, timezone as _timezone
from scripts.refresh_cookies import describe_chain, load_refresh_chain


def test_new_refresh_token_starts_a_chain(tmp_path):
    token = _seeded(tmp_path)
    chain = load_refresh_chain(refresh_token_path(token))
    assert chain['chain_start_exact'] is True
    assert chain['renewals'] == 0
    started = _datetime.fromisoformat(chain['chain_started_at'])
    assert abs((_datetime.now(_timezone.utc) - started).total_seconds()) < 60


def test_rotation_carries_the_chain_start_and_counts_renewals(tmp_path):
    token = tmp_path / 'cookies-joel.txt'
    token.write_text('access-old')
    started = '2026-10-01T00:00:00+00:00'
    save_refresh_token(refresh_token_path(token), 'refresh-old', 'client-synthetic',
                       {'chain_started_at': started, 'chain_start_exact': True, 'renewals': 4})
    with patch('scripts.refresh_cookies.requests.post', return_value=_token_response(
            200, {'access_token': 'access-new', 'refresh_token': 'refresh-new'})), \
         patch('scripts.refresh_cookies.verify_token', return_value='demo'):
        renew_with_refresh_token(token)
    chain = load_refresh_chain(refresh_token_path(token))
    assert chain == {'chain_started_at': started, 'chain_start_exact': True, 'renewals': 5}
    assert load_refresh_token(refresh_token_path(token))[0] == 'refresh-new'


def test_untracked_file_falls_back_to_its_save_time_as_a_lower_bound(tmp_path):
    path = tmp_path / 'cookies.refresh.json'
    path.write_text(_json.dumps({'refresh_token': 'r', 'saved_at': '2026-10-30T00:00:00+00:00'}))
    chain = load_refresh_chain(path)
    assert chain == {'chain_started_at': '2026-10-30T00:00:00+00:00',
                     'chain_start_exact': False, 'renewals': None}
    now = _datetime(2026, 11, 1, tzinfo=_timezone.utc)
    assert describe_chain(chain, now) == 'refresh chain at least 2.0 days old'
    assert describe_chain({**chain, 'renewals': 1}, now) == 'refresh chain at least 2.0 days old, 1+ renewals'


@pytest.mark.parametrize('content', ['not json', '[]', '{"chain_started_at": "yesterday", "renewals": -1}',
                                     '{"chain_started_at": 5, "renewals": true}'])
def test_unreadable_chain_metadata_is_unknown_not_an_error(tmp_path, content):
    path = tmp_path / 'cookies.refresh.json'
    path.write_text(content)
    chain = load_refresh_chain(path)
    assert chain['chain_started_at'] is None and chain['renewals'] is None
    assert describe_chain(chain) == 'refresh chain age unknown'


def test_missing_refresh_file_chain_is_unknown(tmp_path):
    assert describe_chain(load_refresh_chain(tmp_path / 'absent.refresh.json')) == 'refresh chain age unknown'


def test_describe_chain_exact(tmp_path):
    chain = {'chain_started_at': '2026-10-01T00:00:00+00:00', 'chain_start_exact': True, 'renewals': 1}
    assert describe_chain(chain, _datetime(2026, 10, 4, 12, tzinfo=_timezone.utc)) == \
        'refresh chain 3.5 days old, 1 renewal'


def test_invalid_grant_message_reports_the_chain_age(tmp_path):
    token = tmp_path / 'cookies.txt'
    token.write_text('access-old')
    save_refresh_token(refresh_token_path(token), 'r', 'c',
                       {'chain_started_at': '2026-10-01T00:00:00+00:00', 'chain_start_exact': True,
                        'renewals': 30})
    with patch('scripts.refresh_cookies.requests.post',
               return_value=_token_response(403, {'error': 'invalid_grant'})):
        with pytest.raises(RefreshTokenRejected, match=r'refresh chain [\d.]+ days old, 30 renewals'):
            renew_with_refresh_token(token)


def test_untracked_file_gains_a_chain_on_first_renewal(tmp_path):
    token = tmp_path / 'cookies.txt'
    token.write_text('access-old')
    refresh_token_path(token).write_text(_json.dumps(
        {'refresh_token': 'r', 'client_id': 'c', 'saved_at': '2026-10-30T00:00:00+00:00'}))
    with patch('scripts.refresh_cookies.requests.post', return_value=_token_response(
            200, {'access_token': 'a', 'refresh_token': 'r2'})), \
         patch('scripts.refresh_cookies.verify_token', return_value='demo'):
        renew_with_refresh_token(token)
    assert load_refresh_chain(refresh_token_path(token)) == {
        'chain_started_at': '2026-10-30T00:00:00+00:00', 'chain_start_exact': False, 'renewals': 1}


def test_status_reports_the_chain(tmp_path, capsys, monkeypatch):
    from scripts import refresh_cookies
    token = tmp_path / 'cookies.txt'
    token.write_text(_jwt_with_exp(time.time() + 3600))
    save_refresh_token(refresh_token_path(token), 'r', 'c')
    monkeypatch.setattr('sys.argv', ['refresh_cookies.py', '--status', '--cookies', str(token)])
    refresh_cookies.main()
    assert 'refresh token saved (refresh chain 0.0 days old, 0 renewals)' in capsys.readouterr().out
