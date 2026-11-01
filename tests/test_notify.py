import json
from unittest.mock import patch

import pytest
import requests

from peloton import notify
from peloton.notify import plan_alert, report_outcome, send_pushover

HOUR = 60 * 60
DAY = 24 * HOUR


@pytest.fixture
def pushover_env(monkeypatch):
    monkeypatch.setenv('PUSHOVER_APP_TOKEN', 'app-synthetic')
    monkeypatch.setenv('PUSHOVER_USER_KEY', 'user-synthetic')


def _response(status, body):
    response = requests.Response()
    response.status_code = status
    response._content = body if isinstance(body, bytes) else json.dumps(body).encode()
    return response


# plan_alert: the rate-limiting rules.

def test_single_failure_waits_for_a_second_run():
    alert, state = plan_alert({}, 'offline', 0)
    assert alert is None
    assert state == {'failures': 1, 'last_message': 'offline', 'last_alert_at': None}
    alert, state = plan_alert(state, 'offline', HOUR)
    assert alert == ('Peloton token renewal failed', 'offline')
    assert state['failures'] == 2


def test_invalid_grant_alerts_at_once():
    alert, _ = plan_alert({}, 'cookies.refresh.json (invalid_grant); seed again', 0)
    assert alert is not None


def test_ongoing_failure_repeats_once_a_day_even_when_the_wording_changes():
    state = {'failures': 2, 'last_message': 'object at 0x1', 'last_alert_at': 0}
    assert plan_alert(state, 'object at 0x2', 23 * HOUR)[0] is None
    assert plan_alert(state, 'object at 0x3', DAY)[0] is not None


def test_success_after_an_alert_sends_one_recovery_and_clears_state():
    alert, state = plan_alert({'failures': 3, 'last_alert_at': 0}, None, HOUR)
    assert alert == ('Peloton token renewal recovered', 'Token renewal is working again.')
    assert state == {}


def test_success_after_an_unalerted_blip_is_silent():
    assert plan_alert({'failures': 1, 'last_alert_at': None}, None, HOUR) == (None, {})
    assert plan_alert({}, None, HOUR) == (None, {})


@pytest.mark.parametrize('state', [{'failures': 'x', 'last_alert_at': 'yesterday'},
                                   {'failures': True, 'last_alert_at': True}])
def test_garbage_state_is_treated_as_fresh(state):
    alert, new_state = plan_alert(state, 'offline', 0)
    assert alert is None and new_state['failures'] == 1


# send_pushover: never raises, reports acceptance.

def test_send_without_configuration_skips_the_network(monkeypatch):
    monkeypatch.delenv('PUSHOVER_APP_TOKEN', raising=False)
    monkeypatch.delenv('PUSHOVER_USER_KEY', raising=False)
    with patch('peloton.notify.requests.post') as post:
        assert send_pushover('t', 'm') is False
    post.assert_not_called()


def test_send_posts_the_message(pushover_env):
    with patch('peloton.notify.requests.post', return_value=_response(200, {'status': 1})) as post:
        assert send_pushover('title', 'message') is True
    assert post.call_args.args == (notify.PUSHOVER_URL,)
    assert post.call_args.kwargs['data'] == {'token': 'app-synthetic', 'user': 'user-synthetic',
                                             'title': 'title', 'message': 'message'}
    assert post.call_args.kwargs['timeout'] > 0


def test_send_truncates_to_pushover_limits(pushover_env):
    with patch('peloton.notify.requests.post', return_value=_response(200, {'status': 1})) as post:
        send_pushover('t' * 300, 'm' * 2000)
    assert len(post.call_args.kwargs['data']['title']) == 250
    assert len(post.call_args.kwargs['data']['message']) == 1024


@pytest.mark.parametrize('outcome', [
    requests.ConnectionError('offline'), requests.Timeout('slow'),
    _response(200, b'<html>not json</html>'), _response(200, {'status': 0}),
    _response(200, []), _response(400, {'status': 0, 'errors': ['user key is invalid']}),
    _response(500, b''),
])
def test_send_failures_return_false(pushover_env, outcome):
    kwargs = {'side_effect': outcome} if isinstance(outcome, Exception) else {'return_value': outcome}
    with patch('peloton.notify.requests.post', **kwargs):
        assert send_pushover('t', 'm') is False


# report_outcome: state file round trips.

def test_report_outcome_alerts_once_then_recovers(tmp_path, pushover_env):
    state = tmp_path / 'token-alert-state.json'
    with patch('peloton.notify.requests.post', return_value=_response(200, {'status': 1})) as post:
        report_outcome(state, 'offline', 0, 'pelotonpi')
        report_outcome(state, 'offline', HOUR, 'pelotonpi')
        report_outcome(state, 'offline', 2 * HOUR, 'pelotonpi')
        assert post.call_count == 1
        assert post.call_args.kwargs['data']['message'] == 'pelotonpi: offline'
        report_outcome(state, None, 3 * HOUR, 'pelotonpi')
    assert post.call_count == 2
    assert post.call_args.kwargs['data']['title'] == 'Peloton token renewal recovered'
    assert not state.exists()


def test_report_outcome_retries_an_alert_pushover_did_not_accept(tmp_path, pushover_env):
    state = tmp_path / 'token-alert-state.json'
    with patch('peloton.notify.requests.post', side_effect=requests.ConnectionError('down')):
        report_outcome(state, 'x invalid_grant', 0)
    assert json.loads(state.read_text())['last_alert_at'] is None
    with patch('peloton.notify.requests.post', return_value=_response(200, {'status': 1})) as post:
        report_outcome(state, 'x invalid_grant', HOUR)
    post.assert_called_once()


def test_report_outcome_retries_an_unsent_recovery(tmp_path, pushover_env):
    state = tmp_path / 'token-alert-state.json'
    state.write_text(json.dumps({'failures': 2, 'last_alert_at': 0}))
    with patch('peloton.notify.requests.post', return_value=_response(500, b'')):
        report_outcome(state, None, HOUR)
    assert state.exists()
    with patch('peloton.notify.requests.post', return_value=_response(200, {'status': 1})):
        report_outcome(state, None, 2 * HOUR)
    assert not state.exists()


def test_report_outcome_ignores_a_corrupt_state_file(tmp_path, pushover_env):
    state = tmp_path / 'token-alert-state.json'
    state.write_text('not json')
    with patch('peloton.notify.requests.post') as post:
        report_outcome(state, 'offline', 0)
    post.assert_not_called()
    assert json.loads(state.read_text())['failures'] == 1


def test_report_outcome_never_raises(tmp_path, pushover_env):
    # The state directory is missing, so the write fails; the job must not.
    report_outcome(tmp_path / 'missing' / 'state.json', 'offline', 0)


def test_ensure_reports_failure_and_success_to_the_alert_state(tmp_path, monkeypatch):
    from scripts import refresh_cookies
    token = tmp_path / 'cookies.txt'
    monkeypatch.setattr('sys.argv', ['refresh_cookies.py', '--ensure', '--cookies', str(token),
                                     '--config', str(tmp_path / 'config.json')])
    with patch('scripts.refresh_cookies.ensure_token', side_effect=RuntimeError('boom')), \
         patch('scripts.refresh_cookies.report_outcome') as report:
        with pytest.raises(SystemExit):
            refresh_cookies.main()
    assert report.call_args.args[0] == tmp_path / 'token-alert-state.json'
    assert report.call_args.args[1] == 'boom'
    with patch('scripts.refresh_cookies.ensure_token', return_value=('demo', False)), \
         patch('scripts.refresh_cookies.report_outcome') as report:
        refresh_cookies.main()
    assert report.call_args.args[1] is None
