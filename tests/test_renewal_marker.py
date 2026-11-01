"""The renewal job's 'needs a fresh login' marker and the padlock it drives."""
import os
import time
from unittest.mock import Mock, patch

import pytest
import requests

from peloton.config import renewal_failed_path
from peloton.dashboard import Dashboard, RENEWAL_MARKER_CHECK_SECONDS
from scripts.refresh_cookies import LoginRequired, RefreshTokenRejected, ensure_token


def _dashboard(tmp_path, **kwargs):
    token = tmp_path / 'cookies-joel.txt'
    token.write_text('token')
    return Dashboard(token, {'cache_path': str(tmp_path / 'cache.json')},
                     client_factory=lambda path: Mock(), **kwargs), token


def _age(path, seconds):
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


def test_marker_path_sits_beside_the_token(tmp_path):
    assert renewal_failed_path(tmp_path / 'cookies-joel.txt') == tmp_path / 'cookies-joel.renewal-failed'


def test_no_marker_no_padlock(tmp_path):
    dashboard, _ = _dashboard(tmp_path)
    assert dashboard.renewal_failed is False
    assert dashboard.login_indicator_required is False


def test_marker_newer_than_token_shows_padlock_without_stopping_refreshes(tmp_path):
    dashboard, token = _dashboard(tmp_path)
    _age(token, 3600)
    renewal_failed_path(token).write_text('{}')
    assert dashboard.login_indicator_required is True
    # Data keeps refreshing with the still-valid token.
    assert dashboard.login_required is False


def test_marker_older_than_a_reseeded_token_is_ignored(tmp_path):
    dashboard, token = _dashboard(tmp_path)
    renewal_failed_path(token).write_text('{}')
    _age(renewal_failed_path(token), 3600)
    assert dashboard.renewal_failed is False


def test_marker_with_missing_token_shows_padlock(tmp_path):
    dashboard, token = _dashboard(tmp_path)
    renewal_failed_path(token).write_text('{}')
    token.unlink()
    assert dashboard.renewal_failed is True


def test_marker_is_checked_at_most_every_30_seconds(tmp_path):
    dashboard, token = _dashboard(tmp_path)
    _age(token, 3600)
    with patch('peloton.dashboard.time.monotonic', return_value=1000.0):
        assert dashboard.renewal_failed is False
        renewal_failed_path(token).write_text('{}')
        assert dashboard.renewal_failed is False
    with patch('peloton.dashboard.time.monotonic', return_value=1000.0 + RENEWAL_MARKER_CHECK_SECONDS):
        assert dashboard.renewal_failed is True


def test_demo_never_reads_the_marker(tmp_path):
    token = tmp_path / 'cookies.txt'
    renewal_failed_path(token).write_text('{}')
    dashboard = Dashboard(token, {}, demo=True)
    assert dashboard.renewal_failed is False


def test_rejected_token_still_shows_padlock(tmp_path):
    dashboard, _ = _dashboard(tmp_path)
    dashboard._publish(login_required=True)
    assert dashboard.login_indicator_required is True


# The renewal job's side.

@pytest.mark.parametrize('failure', [RefreshTokenRejected('invalid_grant'), LoginRequired('seed it')])
def test_login_required_failures_write_the_marker(tmp_path, failure):
    token = tmp_path / 'cookies.txt'
    with patch('scripts.refresh_cookies._ensure_token', side_effect=failure):
        with pytest.raises(LoginRequired):
            ensure_token(token, tmp_path / 'config.json')
    assert str(failure) in renewal_failed_path(token).read_text()


@pytest.mark.parametrize('failure', [requests.ConnectionError('offline'), RuntimeError('HTTP 503')])
def test_transient_failures_leave_the_marker_alone(tmp_path, failure):
    token = tmp_path / 'cookies.txt'
    with patch('scripts.refresh_cookies._ensure_token', side_effect=failure):
        with pytest.raises(type(failure)):
            ensure_token(token, tmp_path / 'config.json')
    assert not renewal_failed_path(token).exists()
    renewal_failed_path(token).write_text('earlier')
    with patch('scripts.refresh_cookies._ensure_token', side_effect=failure):
        with pytest.raises(type(failure)):
            ensure_token(token, tmp_path / 'config.json')
    assert renewal_failed_path(token).read_text() == 'earlier'


def test_success_removes_the_marker(tmp_path):
    token = tmp_path / 'cookies.txt'
    renewal_failed_path(token).write_text('earlier')
    with patch('scripts.refresh_cookies._ensure_token', return_value=('demo', True)):
        assert ensure_token(token, tmp_path / 'config.json') == ('demo', True)
    assert not renewal_failed_path(token).exists()


def test_unwritable_marker_does_not_hide_the_real_error(tmp_path):
    token = tmp_path / 'missing-dir' / 'cookies.txt'
    with patch('scripts.refresh_cookies._ensure_token', side_effect=RefreshTokenRejected('invalid_grant')):
        with pytest.raises(RefreshTokenRejected, match='invalid_grant'):
            ensure_token(token, tmp_path / 'config.json')


def test_missing_refresh_and_browser_is_login_required(tmp_path):
    token = tmp_path / 'cookies.txt'
    token.write_text('rejected')
    response = requests.Response()
    response.status_code = 401
    with patch('scripts.refresh_cookies.verify_token', side_effect=requests.HTTPError(response=response)), \
         patch('scripts.refresh_cookies.browser_login_available', return_value=False):
        with pytest.raises(LoginRequired):
            ensure_token(token, tmp_path / 'config.json')
    assert renewal_failed_path(token).exists()


def test_show_and_wait_repaints_when_the_marker_appears():
    from peloton_led import show_and_wait
    dashboard = Mock()
    states = iter([False, True, True, True, True, True, True, True, True, True])
    type(dashboard).login_indicator_required = property(lambda self: next(states, True))
    manager = Mock()
    with patch('peloton_led.time.sleep'):
        show_and_wait(manager, 'username', {}, 0.5, dashboard)
    manager.matrix.Clear.assert_called()
