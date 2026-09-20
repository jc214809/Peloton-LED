from unittest.mock import Mock
import json
import stat
import requests
from peloton.dashboard import Dashboard
from peloton.demo import demo_data


def setup_dashboard(tmp_path):
    token = tmp_path / 'token'
    token.write_text('synthetic-token')
    data = demo_data()
    client = Mock(history_truncated=False)
    client.get_me.return_value = data['me']
    client.get_overview.return_value = data['overview']
    client.get_recent_workouts.return_value = [data['workouts'][0]]
    client.get_perf_graph.return_value = data['performance']['demo-cycling']
    client.get_all_workouts.return_value = []
    dashboard = Dashboard(token, {}, client_factory=lambda _: client)
    return dashboard, client, token


def test_refresh_updates_history_but_caches_old_performance(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    assert dashboard.refresh() == 300
    before = dashboard.snapshot()
    assert before['summaries'][0]['workout_id'] == 'demo-cycling'
    dashboard.refresh()
    assert client.get_recent_workouts.call_count == 2
    assert client.get_perf_graph.call_count == 1
    client.get_recent_workouts.return_value = [dict(client.get_recent_workouts.return_value[0], id='new')]
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['workout_id'] == 'new'
    assert client.get_perf_graph.call_count == 2
    client.get_recent_workouts.return_value = [client.get_recent_workouts.return_value[0] | {'id': 'demo-cycling'}]
    dashboard.refresh()
    assert client.get_perf_graph.call_count == 2


def test_instructor_tally_accumulates_incrementally_across_refreshes(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    client.get_all_workouts.return_value = [
        {'id': 'w2', 'status': 'COMPLETE', 'ride': {'instructor': {'name': 'Cody Rigsby'}}},
        {'id': 'w1', 'status': 'COMPLETE', 'ride': {'instructor': {'name': 'Cody Rigsby'}}},
    ]
    dashboard.refresh()
    assert dashboard.snapshot()['instructor_counts'] == {'Cody Rigsby': 2}
    assert dashboard.snapshot()['instructor_tally_cursor'] == 'w2'
    # get_all_workouts is called with the cursor from the previous refresh,
    # so only genuinely new workouts need to be walked.
    client.get_all_workouts.return_value = [
        {'id': 'w3', 'status': 'COMPLETE', 'ride': {'instructor': {'name': 'Robin Arzon'}}},
    ]
    dashboard.refresh()
    assert client.get_all_workouts.call_args.kwargs['stop_at_id'] == 'w2'
    assert dashboard.snapshot()['instructor_counts'] == {'Cody Rigsby': 2, 'Robin Arzon': 1}
    assert dashboard.snapshot()['instructor_tally_cursor'] == 'w3'


def test_instructor_tally_cursor_persists_when_no_new_workouts(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    client.get_all_workouts.return_value = [
        {'id': 'w1', 'status': 'COMPLETE', 'ride': {'instructor': {'name': 'Cody Rigsby'}}},
    ]
    dashboard.refresh()
    client.get_all_workouts.return_value = []
    dashboard.refresh()
    assert dashboard.snapshot()['instructor_tally_cursor'] == 'w1'
    assert dashboard.snapshot()['instructor_counts'] == {'Cody Rigsby': 1}


def test_offline_retains_snapshot_and_does_not_set_login(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    dashboard.refresh()
    previous = dashboard.snapshot()
    client.get_overview.side_effect = requests.ConnectionError('offline')
    assert dashboard.refresh() == 15
    assert dashboard.snapshot()['summaries'] == previous['summaries']
    assert dashboard.snapshot()['last_updated'] == previous['last_updated']
    assert dashboard.snapshot()['status'] == 'offline'
    assert dashboard.snapshot()['data_stale']
    assert not dashboard.login_required


def test_stale_indicator_waits_for_three_consecutive_failures(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    dashboard.refresh()
    client.get_overview.side_effect = requests.ConnectionError('offline')
    dashboard.refresh()
    assert dashboard.snapshot()['consecutive_failures'] == 1
    assert not dashboard.stale_indicator_required
    dashboard.refresh()
    assert dashboard.snapshot()['consecutive_failures'] == 2
    assert not dashboard.stale_indicator_required
    dashboard.refresh()
    assert dashboard.snapshot()['consecutive_failures'] == 3
    assert dashboard.stale_indicator_required
    client.get_overview.side_effect = None
    dashboard.refresh()
    assert dashboard.snapshot()['consecutive_failures'] == 0
    assert not dashboard.stale_indicator_required


def test_successful_snapshot_survives_offline_restart(tmp_path):
    dashboard, client, token = setup_dashboard(tmp_path)
    dashboard.refresh()
    cache_path = tmp_path / 'dashboard-cache.json'
    assert cache_path.exists()
    assert stat.S_IMODE(cache_path.stat().st_mode) == 0o600

    offline = Mock(history_truncated=False)
    offline.get_me.side_effect = requests.ConnectionError('offline')
    restarted = Dashboard(token, {}, client_factory=lambda _: offline)
    loaded = restarted.snapshot()
    assert loaded['status'] == 'cached'
    assert loaded['cache_loaded'] is True
    assert loaded['data_stale'] is True
    assert loaded['summaries'] == dashboard.snapshot()['summaries']

    restarted.refresh()
    recovered = restarted.snapshot()
    assert recovered['status'] == 'offline'
    assert recovered['summaries'] == loaded['summaries']
    assert recovered['last_updated'] == loaded['last_updated']


def test_instructor_tally_survives_restart(tmp_path):
    dashboard, client, token = setup_dashboard(tmp_path)
    client.get_all_workouts.return_value = [
        {'id': 'w1', 'status': 'COMPLETE', 'ride': {'instructor': {'name': 'Cody Rigsby'}}},
    ]
    dashboard.refresh()
    offline = Mock(history_truncated=False)
    offline.get_me.side_effect = requests.ConnectionError('offline')
    restarted = Dashboard(token, {}, client_factory=lambda _: offline)
    loaded = restarted.snapshot()
    assert loaded['instructor_counts'] == {'Cody Rigsby': 1}
    assert loaded['instructor_tally_cursor'] == 'w1'


def test_corrupt_or_wrong_version_cache_is_ignored(tmp_path):
    token = tmp_path / 'token'
    token.write_text('synthetic-token')
    cache_path = tmp_path / 'dashboard-cache.json'
    for contents in ('not json', json.dumps({'version': 999, 'snapshot': {}}),
                     json.dumps({'version': 1, 'snapshot': {'summaries': {}, 'totals': {}}})):
        cache_path.write_text(contents)
        dashboard = Dashboard(token, {})
        snapshot = dashboard.snapshot()
        assert snapshot['status'] == 'loading'
        assert snapshot['summaries'] == []
        assert snapshot['cache_loaded'] is False


def test_pr_acknowledgement_survives_restart(tmp_path):
    dashboard, _, token = setup_dashboard(tmp_path)
    dashboard.refresh()
    summary = dashboard.snapshot()['summaries'][0]
    assert summary['is_pr']
    assert dashboard.should_celebrate_pr(summary)
    dashboard.acknowledge_pr(summary['workout_id'])
    assert not dashboard.should_celebrate_pr(summary)

    restarted = Dashboard(token, {})
    restored = restarted.snapshot()['summaries'][0]
    assert not restarted.should_celebrate_pr(restored)


def test_milestone_acknowledgement_survives_restart(tmp_path):
    dashboard, _, token = setup_dashboard(tmp_path)
    dashboard.config['milestones'] = [100, 1000]
    dashboard.refresh()
    assert dashboard.pending_milestones() == [100, 1000]
    dashboard.acknowledge_milestone(100)
    assert dashboard.pending_milestones() == [1000]
    restarted = Dashboard(token, {'milestones': [100, 1000]})
    assert restarted.pending_milestones() == [1000]


def test_rejected_token_pauses_until_file_replaced(tmp_path):
    dashboard, client, token = setup_dashboard(tmp_path)
    response = requests.Response()
    response.status_code = 401
    client.get_me.side_effect = requests.HTTPError(response=response)
    dashboard.refresh()
    assert dashboard.login_required
    dashboard.refresh()
    assert client.get_me.call_count == 1
    token.write_text('replacement-synthetic-token')
    client.get_me.side_effect = None
    dashboard.refresh()
    assert not dashboard.login_required
    assert dashboard.snapshot()['status'] == 'ready'


def test_missing_token_and_demo_make_no_requests(tmp_path):
    factory = Mock()
    dashboard = Dashboard(tmp_path / 'missing', {}, client_factory=factory)
    dashboard.refresh()
    assert dashboard.login_required
    factory.assert_not_called()
    demo = Dashboard(tmp_path / 'missing', {}, demo=True, client_factory=factory)
    demo.refresh()
    assert len(demo.snapshot()['summaries']) == 5
    assert not demo.login_required
    factory.assert_not_called()


def test_rate_limit_honors_retry_after(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    response = requests.Response()
    response.status_code = 429
    response.headers['Retry-After'] = '600'
    client.get_me.side_effect = requests.HTTPError(response=response)
    assert dashboard.refresh() == 600
    assert not dashboard.login_required


def test_snapshot_cannot_mutate_live_data(tmp_path):
    dashboard, _, _ = setup_dashboard(tmp_path)
    dashboard.refresh()
    snapshot = dashboard.snapshot()
    snapshot['summaries'].clear()
    assert dashboard.snapshot()['summaries']


def test_refresh_health_is_published_atomically(tmp_path):
    dashboard, _, _ = setup_dashboard(tmp_path)
    dashboard.refresh()
    snapshot = dashboard.snapshot()
    assert snapshot['status'] == 'ready'
    assert snapshot['refresh_in_progress'] is False
    assert snapshot['last_attempt'] is not None
    assert snapshot['last_updated'] is not None
    assert snapshot['last_refresh_duration'] >= 0
    assert snapshot['next_refresh_at'] >= snapshot['last_updated']
    assert snapshot['last_error'] is None
    assert snapshot['generation'] == 1
    assert snapshot['data_stale'] is False


def test_lru_performance_cache_is_bounded(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    dashboard._performance_cache_size = 2
    original = client.get_recent_workouts.return_value[0]
    for identity in ('one', 'two', 'three'):
        client.get_recent_workouts.return_value = [dict(original, id=identity)]
        dashboard.refresh()
    assert list(dashboard._performance) == ['two', 'three']


def test_refresh_summarizes_every_workout_on_latest_active_day(tmp_path):
    from datetime import datetime, timedelta, timezone

    dashboard, client, _ = setup_dashboard(tmp_path)
    latest_day = datetime.now(timezone.utc) - timedelta(days=7)
    older_day = latest_day - timedelta(days=1)
    client.get_recent_workouts.return_value = [
        {'id': 'older', 'status': 'COMPLETE', 'start_time': older_day.timestamp(),
         'fitness_discipline': 'strength'},
        {'id': 'morning', 'status': 'COMPLETE', 'start_time': latest_day.replace(hour=9).timestamp(),
         'fitness_discipline': 'yoga'},
        {'id': 'evening', 'status': 'COMPLETE', 'start_time': latest_day.replace(hour=18).timestamp(),
         'fitness_discipline': 'rowing'},
        {'id': 'active', 'status': 'IN_PROGRESS', 'start_time': latest_day.replace(hour=20).timestamp(),
         'fitness_discipline': 'cycling'},
    ]
    client.get_perf_graph.return_value = {'duration': 1200}
    dashboard.refresh()
    snapshot = dashboard.snapshot()
    assert [summary['workout_id'] for summary in snapshot['summaries']] == ['evening', 'morning']
    assert snapshot['active_day_count'] == 2
    assert {call.args[0] for call in client.get_perf_graph.call_args_list} == {'evening', 'morning'}


def test_same_rejected_token_finishes_attempt_state(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    response = requests.Response()
    response.status_code = 401
    client.get_me.side_effect = requests.HTTPError(response=response)
    dashboard.refresh()
    dashboard.refresh()
    snapshot = dashboard.snapshot()
    assert snapshot['refresh_in_progress'] is False
    assert snapshot['status'] == 'login_needed'
    assert snapshot['last_error'] == 'authentication'


def test_background_refresh_does_not_block_snapshot_or_shutdown(tmp_path):
    import threading
    dashboard, client, _ = setup_dashboard(tmp_path)
    entered, release = threading.Event(), threading.Event()
    data = demo_data()
    def slow_profile():
        entered.set()
        assert release.wait(3)
        return data['me']
    client.get_me.side_effect = slow_profile
    dashboard.start()
    try:
        assert entered.wait(2)
        assert dashboard.snapshot()['status'] == 'loading'
        assert dashboard.snapshot()['summaries'] == []
    finally:
        release.set()
        dashboard.stop()
    assert not dashboard._thread.is_alive()


def test_worker_refreshes_automatically_without_screen_calls(tmp_path):
    import threading
    dashboard, client, _ = setup_dashboard(tmp_path)
    dashboard.interval = 0.02
    refreshed = threading.Event()
    calls = 0
    def overview(_):
        nonlocal calls
        calls += 1
        if calls == 2:
            refreshed.set()
        return demo_data()['overview']
    client.get_overview.side_effect = overview
    dashboard.start()
    try:
        assert refreshed.wait(2)
    finally:
        dashboard.stop()
    assert client.get_recent_workouts.call_count >= 2


def test_request_refresh_wakes_sleeping_worker(tmp_path):
    import threading
    dashboard, client, _ = setup_dashboard(tmp_path)
    dashboard.interval = 3600
    refreshed = threading.Event()
    calls = 0
    def overview(_):
        nonlocal calls
        calls += 1
        if calls == 2:
            refreshed.set()
        return demo_data()['overview']
    client.get_overview.side_effect = overview
    dashboard.start()
    try:
        deadline = threading.Event()
        for _ in range(100):
            if client.get_overview.call_count:
                break
            deadline.wait(0.01)
        dashboard.request_refresh()
        assert refreshed.wait(2)
    finally:
        assert dashboard.stop(timeout=2)


def test_stop_reports_blocked_worker_then_completes(tmp_path):
    import threading
    dashboard, client, _ = setup_dashboard(tmp_path)
    entered, release = threading.Event(), threading.Event()
    client.get_me.side_effect = lambda: (entered.set(), release.wait(2), demo_data()['me'])[-1]
    dashboard.start()
    assert entered.wait(1)
    assert dashboard.stop(timeout=0.01) is False
    release.set()
    assert dashboard.stop(timeout=2) is True
    client.close.assert_called_once()


def test_screen_rotation_continues_during_slow_refresh(tmp_path):
    import threading
    from peloton_led import run_display_loop

    dashboard, client, _ = setup_dashboard(tmp_path)
    dashboard.refresh()
    entered, release = threading.Event(), threading.Event()
    client.get_me.side_effect = lambda: (entered.set(), release.wait(2), demo_data()['me'])[-1]
    dashboard.start()
    assert entered.wait(1)
    manager = Mock()
    display = {'duration': 0, 'overview_duration': 0, 'last_workout_duration': 0,
               'color': 'white'}
    try:
        run_display_loop(manager, dashboard, display, cycles=1)
        assert manager.show.call_count > 1
        assert manager.tick.call_count == manager.show.call_count
    finally:
        release.set()
        assert dashboard.stop(timeout=2)
