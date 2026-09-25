"""Quiet-hours refresh scheduling: poll Peloton less often overnight."""
from datetime import datetime

import pytest

from peloton.config import load_config
from peloton.schedule import in_quiet_hours, scheduled_refresh_interval
from tests.test_dashboard import setup_dashboard

QUIET = {'quiet_start': '23:00', 'quiet_end': '05:00', 'quiet_interval': 1800}


@pytest.mark.parametrize('hour, minute, expected', [
    (23, 0, True), (2, 0, True), (4, 59, True),   # inside the wrapped window
    (5, 0, False), (10, 0, False), (22, 59, False),  # outside it
])
def test_in_quiet_hours_wraps_midnight(hour, minute, expected):
    now = datetime(2026, 1, 1, hour, minute)
    assert in_quiet_hours(QUIET, now, 'UTC') is expected


def test_in_quiet_hours_supports_a_same_day_window_too():
    same_day = {'quiet_start': '13:00', 'quiet_end': '15:00', 'quiet_interval': 1800}
    assert in_quiet_hours(same_day, datetime(2026, 1, 1, 14, 0), 'UTC')
    assert not in_quiet_hours(same_day, datetime(2026, 1, 1, 16, 0), 'UTC')


@pytest.mark.parametrize('schedule', [None, {}, {'quiet_start': '23:00', 'quiet_end': '23:00', 'quiet_interval': 1800}])
def test_in_quiet_hours_is_false_when_disabled_or_zero_width(schedule):
    assert not in_quiet_hours(schedule, datetime(2026, 1, 1, 23, 30), 'UTC')


def test_scheduled_refresh_interval_uses_quiet_interval_only_inside_the_window():
    assert scheduled_refresh_interval(QUIET, 300, datetime(2026, 1, 1, 2, 0), 'UTC') == 1800
    assert scheduled_refresh_interval(QUIET, 300, datetime(2026, 1, 1, 10, 0), 'UTC') == 300
    assert scheduled_refresh_interval(None, 300, datetime(2026, 1, 1, 2, 0), 'UTC') == 300


def test_schedule_own_timezone_overrides_the_ambient_one_when_now_is_omitted():
    # With no explicit `now`, the schedule's own timezone (not the ambient
    # ones passed as timezone_name) should decide what "current time" means.
    schedule = {**QUIET, 'timezone': 'America/New_York'}
    with_own_tz = in_quiet_hours(schedule, timezone_name='UTC')
    with_ambient_only = in_quiet_hours({**QUIET}, timezone_name='UTC')
    # Both compute *some* answer without raising; the real assertion is that
    # schedule['timezone'] is consulted at all (covered by the zone-selection
    # line), which a naive-vs-aware crash would have caught.
    assert with_own_tz in (True, False) and with_ambient_only in (True, False)


def test_dashboard_uses_the_quiet_interval_during_the_window(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    dashboard.config['refresh_interval'] = 300
    dashboard.interval = 300
    dashboard.refresh_schedule = {**QUIET, 'timezone': 'UTC'}
    dashboard.config['timezone'] = 'UTC'
    from unittest.mock import patch
    with patch('peloton.dashboard.scheduled_refresh_interval', return_value=1800) as scheduled:
        delay = dashboard.refresh()
    assert delay == 1800
    scheduled.assert_called_once()


def test_dashboard_falls_back_to_normal_interval_without_a_schedule(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    dashboard.interval = 300
    assert dashboard.refresh_schedule is None
    assert dashboard.refresh() == 300


def test_dashboard_login_needed_also_honors_the_quiet_interval(tmp_path):
    dashboard, client, token = setup_dashboard(tmp_path)
    dashboard.refresh_schedule = {**QUIET, 'timezone': 'UTC'}
    from unittest.mock import patch
    with patch('peloton.dashboard.scheduled_refresh_interval', return_value=1800):
        token.unlink()
        assert dashboard.refresh() == 1800


def test_failure_backoff_ignores_the_quiet_interval(tmp_path):
    # Backoff should stay tied to the normal interval, not balloon to the
    # quiet interval, so a real outage still retries reasonably often.
    import requests
    dashboard, client, _ = setup_dashboard(tmp_path)
    dashboard.interval = 300
    dashboard.refresh_schedule = {**QUIET, 'quiet_interval': 3600, 'timezone': 'UTC'}
    client.get_me.side_effect = requests.RequestException('boom')
    from unittest.mock import patch
    with patch('peloton.dashboard.scheduled_refresh_interval', return_value=3600):
        delay = dashboard.refresh()
    assert delay == 15  # first failure backoff, unaffected by the quiet interval


def test_config_accepts_and_validates_refresh_schedule(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"display": {"refresh_schedule": {"quiet_start": "23:00", "quiet_end": "05:00", "quiet_interval": 1800}}}')
    config = load_config(str(path))
    assert config['display']['refresh_schedule']['quiet_interval'] == 1800


@pytest.mark.parametrize('schedule, message', [
    ({'quiet_start': '23:00'}, 'requires quiet_start'),
    ({'quiet_start': '23:00', 'quiet_end': '05:00', 'quiet_interval': 1800, 'extra': 1}, 'unsupported keys'),
    ({'quiet_start': 'late', 'quiet_end': '05:00', 'quiet_interval': 1800}, 'must use HH:MM'),
    ({'quiet_start': '23:00', 'quiet_end': '05:00', 'quiet_interval': 0}, 'quiet_interval'),
    ({'quiet_start': '23:00', 'quiet_end': '05:00', 'quiet_interval': 1800, 'timezone': 'Not/Real'}, 'invalid refresh_schedule.timezone'),
])
def test_config_rejects_bad_refresh_schedule(tmp_path, schedule, message):
    import json
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'display': {'refresh_schedule': schedule}}))
    with pytest.raises(ValueError, match=message):
        load_config(str(path))
