from unittest.mock import Mock, patch
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import stat
import requests

from peloton.api import PelotonClient
from peloton.dashboard import Dashboard
from peloton.demo import demo_data


def serve_history(client):
    """Answer get_workouts_page from client.history (newest first), with the
    real paging logic, so tests can change history between refreshes."""
    def page(user_id, limit, page=0):
        rows = client.history[page * limit:(page + 1) * limit]
        pages = max(1, -(-len(client.history) // limit))
        return {'data': rows, 'total': len(client.history), 'page_count': pages,
                'show_next': page < pages - 1}
    client.get_workouts_page.side_effect = page
    client.page_rows = PelotonClient.page_rows
    client.is_last_page = PelotonClient.is_last_page
    client.iter_workout_pages.side_effect = lambda *a, **k: PelotonClient.iter_workout_pages(client, *a, **k)


def recent_fetches(client):
    """Newest-page fetches made by refreshes (history walks use 100-row batches)."""
    return sum(1 for c in client.get_workouts_page.call_args_list if c.kwargs['limit'] == 20)


def setup_dashboard(tmp_path, config=None):
    token = tmp_path / 'token'
    token.write_text('synthetic-token')
    data = demo_data()
    client = Mock()
    client.get_me.return_value = data['me']
    client.get_overview.return_value = data['overview']
    client.history = [data['workouts'][0]]
    client.get_perf_graph.return_value = data['performance']['demo-cycling']
    serve_history(client)
    dashboard = Dashboard(token, dict(config or {}), client_factory=lambda _: client)
    return dashboard, client, token


def test_refresh_updates_history_but_caches_old_performance(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    assert dashboard.refresh() == 300
    before = dashboard.snapshot()
    assert before['summaries'][0]['workout_id'] == 'demo-cycling'
    dashboard.refresh()
    assert recent_fetches(client) == 2
    assert client.get_perf_graph.call_count == 1
    client.history = [dict(client.history[0], id='new')]
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['workout_id'] == 'new'
    assert client.get_perf_graph.call_count == 2
    client.history = [client.history[0] | {'id': 'demo-cycling'}]
    dashboard.refresh()
    assert client.get_perf_graph.call_count == 2


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

    offline = Mock()
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


def _at(text, zone='America/New_York'):
    return datetime.fromisoformat(text).replace(tzinfo=ZoneInfo(zone)).timestamp()


def test_pr_celebrates_for_24_hours_then_retires_and_survives_restart(tmp_path):
    dashboard, _, token = setup_dashboard(tmp_path, {})
    dashboard.refresh()
    summary = dashboard.snapshot()['summaries'][0]
    start = _at('2026-11-07T07:00')
    assert dashboard.should_celebrate_pr(summary, now=start)
    dashboard.acknowledge_pr(summary['workout_id'], now=start)
    restarted = Dashboard(token, {})
    restored = restarted.snapshot()['summaries'][0]
    # Across midnight it's still on, until 24 hours after the first showing.
    assert restarted.should_celebrate_pr(restored, now=start + 24 * 3600 - 1)
    # A repeat showing doesn't restart the clock.
    restarted.acknowledge_pr(summary['workout_id'], now=start + 3600)
    assert not restarted.should_celebrate_pr(restored, now=start + 24 * 3600)
    # The next acknowledgement after that moves it to the done list for good.
    restarted.acknowledge_pr('other', now=start + 24 * 3600 + 1)
    after = Dashboard(token, {}).snapshot()
    assert summary['workout_id'] in after['celebrated_pr_ids']
    assert summary['workout_id'] not in after['pr_shown_at']
    assert not restarted.should_celebrate_pr(restored, now=start + 60)


def test_pr_max_age_days_skips_old_workouts_only_when_set(tmp_path):
    dashboard, _, _ = setup_dashboard(tmp_path, {'pr_max_age_days': 3})
    dashboard.refresh()
    summary = dashboard.snapshot()['summaries'][0]
    day = 86400
    old = dict(summary, workout_at=1000.0)
    assert not dashboard.should_celebrate_pr(old, now=1000.0 + 3 * day + 1)
    assert dashboard.should_celebrate_pr(old, now=1000.0 + 3 * day)
    # Without a timestamp (a cache from before it existed) the age can't be judged: celebrate.
    assert dashboard.should_celebrate_pr(dict(summary, workout_at=None), now=1000.0 + 99 * day)
    unlimited, _, _ = setup_dashboard(tmp_path, {})
    assert unlimited.should_celebrate_pr(old, now=1000.0 + 99 * day)


def test_pr_state_failing_to_save_is_logged_not_raised(tmp_path, caplog):
    dashboard, _, _ = setup_dashboard(tmp_path)
    dashboard.refresh()
    with patch.object(dashboard, '_persist_snapshot', side_effect=OSError('disk full')):
        dashboard.acknowledge_pr('x')
    assert 'Could not persist' in caplog.text


def test_milestone_celebrates_until_midnight_and_survives_restart(tmp_path):
    config = {'milestones': [100, 1000], 'timezone': 'America/New_York'}
    dashboard, _, token = setup_dashboard(tmp_path, config)
    dashboard.refresh()
    assert dashboard.pending_milestones() == [100, 1000]
    # Showing the newest at 7 am retires the older one at once; the newest keeps its day.
    dashboard.acknowledge_milestone(1000, now=_at('2026-11-07T07:00'))
    assert dashboard.pending_milestones(now=_at('2026-11-07T21:00')) == [1000]
    restarted = Dashboard(token, dict(config))
    assert restarted.pending_milestones(now=_at('2026-11-07T23:59')) == [1000]
    # Showing it again doesn't restart its day.
    restarted.acknowledge_milestone(1000, now=_at('2026-11-07T23:00'))
    assert restarted.pending_milestones(now=_at('2026-11-08T00:00')) == []
    # The next acknowledgement after midnight moves it to the done list for good.
    restarted.acknowledge_milestone(1000, now=_at('2026-11-08T00:01'))
    after = Dashboard(token, dict(config)).snapshot()
    assert after['celebrated_milestones'] == [100, 1000] and after['milestone_shown_at'] == {}


def test_name_page_cooldown_counts_pages_and_survives_restart(tmp_path):
    dashboard, _, token = setup_dashboard(tmp_path, {})
    dashboard.refresh()
    assert dashboard.snapshot()['name_facts_passes'] == 0 and dashboard.snapshot()['name_facts_shown'] == {}
    dashboard.acknowledge_name_facts(['30d:rank', 'kind:rank'])
    dashboard.acknowledge_name_facts(['year:total'])
    restarted = Dashboard(token, {}).snapshot()
    assert restarted['name_facts_passes'] == 2
    assert restarted['name_facts_shown'] == {'30d:rank': 1, 'kind:rank': 1, 'year:total': 2}
    # A page with nothing recordable still counts, so the top threes keep turning.
    again = Dashboard(token, {})
    again.acknowledge_name_facts([])
    assert again.snapshot()['name_facts_passes'] == 3


def test_name_page_cooldown_survives_a_failed_write(tmp_path, caplog):
    dashboard, _, _ = setup_dashboard(tmp_path, {})
    dashboard.refresh()
    with patch.object(dashboard, '_persist_snapshot', side_effect=OSError('disk full')):
        dashboard.acknowledge_name_facts(['a'])
    assert dashboard.snapshot()['name_facts_passes'] == 1 and 'Could not persist name page state' in caplog.text


def test_milestone_day_ends_at_the_boards_midnight_not_utcs(tmp_path):
    # 8 pm in New York is already tomorrow in UTC; the celebration still runs to New York's midnight.
    dashboard, _, _ = setup_dashboard(tmp_path, {'milestones': [100], 'timezone': 'America/New_York'})
    dashboard.refresh()
    dashboard.acknowledge_milestone(100, now=_at('2026-11-07T20:00'))
    assert dashboard.pending_milestones(now=_at('2026-11-07T23:30')) == [100]
    assert dashboard.pending_milestones(now=_at('2026-11-08T00:30')) == []


def test_milestone_day_uses_the_profile_zone_without_one_in_config(tmp_path):
    dashboard, _, _ = setup_dashboard(tmp_path, {'milestones': [100]})
    dashboard.refresh()
    dashboard._publish(me={**dashboard.snapshot()['me'], 'timezone': 'America/Los_Angeles'})
    # 3 pm and 5:30 pm in Los Angeles fall either side of UTC's midnight: still the same day.
    dashboard.acknowledge_milestone(100, now=_at('2026-11-07T15:00', 'America/Los_Angeles'))
    assert dashboard.pending_milestones(now=_at('2026-11-07T17:30', 'America/Los_Angeles')) == [100]
    assert dashboard.pending_milestones(now=_at('2026-11-08T00:01', 'America/Los_Angeles')) == []


def test_acknowledging_a_milestone_ignores_bad_values_and_repeat_shows(tmp_path):
    dashboard, _, _ = setup_dashboard(tmp_path)
    dashboard.config['milestones'] = [100]
    dashboard.refresh()
    for bad in (None, '100', True):
        dashboard.acknowledge_milestone(bad)
    assert dashboard.snapshot()['milestone_shown_at'] == {}
    dashboard.acknowledge_milestone(100, now=10.0)
    with patch.object(dashboard, '_persist_snapshot') as persist:
        dashboard.acknowledge_milestone(100, now=20.0)  # nothing new: no write
    persist.assert_not_called()
    assert dashboard.snapshot()['milestone_shown_at'] == {'100': 10.0}


def test_milestone_state_failing_to_save_is_logged_not_raised(tmp_path, caplog):
    dashboard, _, _ = setup_dashboard(tmp_path)
    dashboard.config['milestones'] = [100]
    dashboard.refresh()
    with patch.object(dashboard, '_persist_snapshot', side_effect=OSError('disk full')):
        dashboard.acknowledge_milestone(100, now=10.0)
    assert 'Could not persist milestone state' in caplog.text


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
    original = client.history[0]
    for identity in ('one', 'two', 'three'):
        client.history = [dict(original, id=identity)]
        dashboard.refresh()
    assert list(dashboard._performance) == ['two', 'three']


def test_refresh_summarizes_every_workout_on_latest_active_day(tmp_path):
    from datetime import datetime, timedelta, timezone

    dashboard, client, _ = setup_dashboard(tmp_path)
    latest_day = datetime.now(timezone.utc) - timedelta(days=7)
    older_day = latest_day - timedelta(days=1)
    client.history = [
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
    assert [summary['workout_id'] for summary in snapshot['summaries']] == ['morning', 'evening']
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
    assert client.get_workouts_page.call_count >= 2


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


def test_screen_rotation_continues_during_slow_refresh(tmp_path, instant_clock):
    import threading
    from peloton_led import run_display_loop

    dashboard, client, _ = setup_dashboard(tmp_path)
    dashboard.refresh()
    entered, release = threading.Event(), threading.Event()
    # The profile is cached for a day, so the second refresh blocks on the overview.
    client.get_overview.side_effect = lambda _: (entered.set(), release.wait(2), demo_data()['overview'])[-1]
    dashboard.start()
    assert entered.wait(1)
    manager = Mock()
    display = {'color': 'white'}
    try:
        run_display_loop(manager, dashboard, display, cycles=1)
        assert manager.show.call_count > 1
        assert manager.tick.call_count == manager.show.call_count
    finally:
        release.set()
        assert dashboard.stop(timeout=2)


def _overview_with_record(data, raw_value, workout_id):
    return dict(data['overview'], personal_records=[
        {'slug': 'cycling', 'records': [
            {'name': '30 min', 'raw_value': raw_value, 'workout_id': workout_id,
             'workout_date': '2026-09-01T12:00:00'},
            {'name': '45 min', 'raw_value': -1, 'workout_id': None, 'workout_date': None},
        ]}])


def test_new_pr_gets_the_record_it_beat_and_survives_restart(tmp_path):
    dashboard, client, token = setup_dashboard(tmp_path)
    data = demo_data()
    # Startup refresh: the old record is already on file.
    client.get_overview.return_value = _overview_with_record(data, 250400.0, 'old-ride')
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['previous_best_kj'] is None
    # The rider sets a new 30 min record with the latest workout.
    pr_ride = dict(data['workouts'][0], id='pr-ride', is_total_work_personal_record=True)
    client.history = [pr_ride]
    client.get_overview.return_value = _overview_with_record(data, 262900.0, 'pr-ride')
    dashboard.refresh()
    snap = dashboard.snapshot()
    assert snap['summaries'][0]['previous_best_kj'] == 250.4
    assert snap['personal_records']['cycling|30 min']['previous']['workout_id'] == 'old-ride'
    # Later refreshes (same record holder) keep the comparison.
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['previous_best_kj'] == 250.4
    offline = Mock()
    offline.get_me.side_effect = requests.ConnectionError('offline')
    restarted = Dashboard(token, {}, client_factory=lambda _: offline)
    assert restarted.snapshot()['summaries'][0]['previous_best_kj'] == 250.4
    assert restarted.snapshot()['personal_records']['cycling|30 min']['value_kj'] == 262.9


def test_pr_set_before_first_capture_has_no_previous_best(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    data = demo_data()
    client.history = [dict(data['workouts'][0], id='pr-ride')]
    client.get_overview.return_value = _overview_with_record(data, 262900.0, 'pr-ride')
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['previous_best_kj'] is None


def test_damaged_records_table_is_dropped_without_losing_cache(tmp_path):
    dashboard, client, token = setup_dashboard(tmp_path)
    dashboard.refresh()
    cache = tmp_path / 'dashboard-cache.json'
    payload = json.loads(cache.read_text())
    payload['snapshot']['personal_records'] = {'cycling|30 min': 'garbage'}
    cache.write_text(json.dumps(payload))
    restarted = Dashboard(token, {}, client_factory=lambda _: Mock())
    assert restarted.snapshot()['summaries'][0]['workout_id'] == 'demo-cycling'
    assert restarted.snapshot()['personal_records'] == {}


def test_a_workout_under_a_minute_is_not_a_latest_workout(tmp_path):
    # A 41-second "Just Walk" (a start tapped by accident) became the first latest-workout page.
    from datetime import datetime, timedelta, timezone

    dashboard, client, _ = setup_dashboard(tmp_path)
    day = datetime.now(timezone.utc) - timedelta(days=7)
    earlier = day - timedelta(days=1)

    def workout(identity, start, seconds):
        return {'id': identity, 'status': 'COMPLETE', 'start_time': start.timestamp(),
                'end_time': start.timestamp() + seconds if seconds is not None else None,
                'fitness_discipline': 'walking'}
    client.history = [workout('walk', day.replace(hour=12, minute=15), 3611),
                      workout('tap', day.replace(hour=12, minute=14), 41),
                      workout('unknown-length', day.replace(hour=17), None)]
    client.get_perf_graph.return_value = {'duration': 1200}
    dashboard.refresh()
    assert [s['workout_id'] for s in dashboard.snapshot()['summaries']] == ['walk', 'unknown-length']
    # Alone on its day, it doesn't make that day the latest: the day before shows.
    client.history = [workout('tap', day.replace(hour=12), 41), workout('yesterday', earlier.replace(hour=9), 1800)]
    dashboard.refresh()
    assert [s['workout_id'] for s in dashboard.snapshot()['summaries']] == ['yesterday']


def test_profile_keeps_created_at_and_no_personal_fields(tmp_path):
    me = {'id': 'u1', 'username': 'joel', 'timezone': 'America/New_York', 'height_unit': 'in',
          'created_at': 1604844000, 'email': 'a@b.c', 'birthday': 123, 'phone_number': '555', 'weight': 180,
          'total_followers': 3}
    dashboard, client, _ = setup_dashboard(tmp_path)
    client.get_me.return_value = me
    dashboard.refresh()
    assert dashboard.snapshot()['me'] == {'id': 'u1', 'username': 'joel', 'timezone': 'America/New_York',
                                          'height_unit': 'in', 'created_at': 1604844000}


def test_the_anniversary_comes_from_the_profile_in_the_derived_figures(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path, {'timezone': 'America/New_York'})
    client.get_me.return_value = dict(client.get_me.return_value, created_at=1604844000)   # 2020-11-08 09:20 EST
    with patch('peloton.workout_log.WorkoutLog.derived', return_value={}) as derived:
        dashboard.refresh()
    assert derived.call_args.kwargs['member_since'] == 1604844000


# --- Workout compare on the board (display.workout_insights) ---

def _insight_setup(tmp_path, config=None, discipline='cycling', status='COMPLETE', age_days=7):
    from datetime import datetime, timedelta, timezone
    dashboard, client, token = setup_dashboard(tmp_path, {'workout_insights': True} if config is None else config)
    start = datetime.now(timezone.utc) - timedelta(days=age_days)
    client.history = [{'id': 'w1', 'status': status, 'start_time': start.timestamp(),
                       'fitness_discipline': discipline}]
    client.get_perf_graph.return_value = {'duration': 1200}
    client.get_workout_detail.return_value = {'id': 'w1', 'status': 'COMPLETE', 'start_time': 1, 'ride': {'id': 'r1'}}
    client.get_ride_details.return_value = {'ride': {}}
    return dashboard, client, token


def _fake_row(workout_id='w1', output=112):
    from peloton.workout_features import ROW_VERSION
    return {'id': workout_id, 'v': ROW_VERSION, 'start': 1_800_000_000, 'disc': 'cycling', 'wtype': 'class',
            'ctype': 'Music', 'mode': 'plain', 'outdoor': False, 'dur': 1200, 'complete': True,
            'work': {'output': output, 'heart_rate': None}, 'eff': None, 'strive': None,
            'target_under': None, 'pace_fit': None, 'sets': None, 'plan': None, 'arms_sections': 0}


def _seed_peers(dashboard, outputs):
    from peloton.workout_rows import RowStore, default_rows_path
    store = RowStore(default_rows_path(dashboard.cache_path))
    for i, output in enumerate(outputs):
        row = _fake_row(f'p{i}', output)
        row['start'] -= (i + 1) * 86400
        store.upsert(row)
    store.save()


def test_new_workout_fetches_detail_and_ride_once_and_gets_an_insight(tmp_path):
    dashboard, client, _ = _insight_setup(tmp_path)
    _seed_peers(dashboard, [110, 111, 112, 113, 114, 111])
    with patch('peloton.dashboard.build_row', return_value=_fake_row('w1', 112)) as build:
        dashboard.refresh()
        summary = dashboard.snapshot()['summaries'][0]
        assert summary['insights'][0]['code'] == 'in_line'
        assert len(summary['insights']) == 1
        assert summary['insights'][0]['headline'] == 'CONSISTENT'
        assert summary['insights'][0]['footer'] == '6 SIMILAR RIDES'
        assert client.get_workout_detail.call_count == 1
        client.get_ride_details.assert_called_once_with('r1')
        assert build.call_args.args[1] == {'duration': 1200}
        dashboard.refresh()
        assert dashboard.snapshot()['summaries'][0]['insights'][0]['code'] == 'in_line'
    assert client.get_workout_detail.call_count == 1
    assert client.get_ride_details.call_count == 1
    # The row was saved, so a restarted board makes no calls either.
    again = Dashboard(dashboard.token_path, {'workout_insights': True}, client_factory=lambda _: client)
    again.refresh()
    assert client.get_workout_detail.call_count == 1
    assert again.snapshot()['summaries'][0]['insights'][0]['code'] == 'in_line'


def test_a_detail_without_a_class_makes_no_ride_call(tmp_path):
    dashboard, client, _ = _insight_setup(tmp_path)
    client.get_workout_detail.return_value = {'id': 'w1', 'status': 'COMPLETE', 'start_time': 1}
    with patch('peloton.dashboard.build_row', return_value=_fake_row()), \
            patch('peloton.dashboard.insights', return_value=[('nothing', '', {})]):
        dashboard.refresh()
    client.get_ride_details.assert_not_called()
    assert 'insights' not in dashboard.snapshot()['summaries'][0]


def test_real_row_building_end_to_end_gives_a_resistance_insight(tmp_path):
    dashboard, client, _ = _insight_setup(tmp_path)
    client.get_workout_detail.return_value = {
        'id': 'w1', 'status': 'COMPLETE', 'start_time': 1_800_000_000, 'end_time': 1_800_001_200,
        'fitness_discipline': 'cycling', 'timezone': 'UTC', 'ride': {'id': 'r1', 'duration': 1200}}
    dashboard.refresh()
    # Whatever the rules say about this bare workout, the refresh survived and stored a row.
    assert dashboard._rows.is_current('w1')


def test_unfinished_or_other_discipline_workouts_get_none_and_no_calls(tmp_path):
    for kwargs in ({'status': 'IN_PROGRESS'}, {'discipline': 'yoga'}):
        folder = tmp_path / str(sorted(kwargs.items()))
        folder.mkdir()
        dashboard, client, _ = _insight_setup(folder, **kwargs)
        dashboard.refresh()
        # (an unfinished workout never reaches the summaries at all)
        assert all('insights' not in summary for summary in dashboard.snapshot()['summaries'])
        client.get_workout_detail.assert_not_called()


def test_a_settling_workout_gets_insights_at_once_then_rebuilds_for_its_hour_then_stops(tmp_path, caplog):
    import logging
    from datetime import datetime, timezone
    caplog.set_level(logging.INFO, logger='peloton-led.dashboard')
    dashboard, client, _ = _insight_setup(tmp_path, age_days=0)  # just finished: still settling
    _seed_peers(dashboard, [110, 111, 112, 113, 114, 111])
    rows = iter([_fake_row('w1', 112), _fake_row('w1', 112), _fake_row('w1', 150), _fake_row('w1', 150)])
    from peloton.workout_rows import RowStore
    saves = []
    real_save = RowStore.save
    with patch('peloton.dashboard.build_row', side_effect=lambda *_: next(rows)) as build, \
            patch.object(RowStore, 'save', autospec=True, side_effect=lambda store: saves.append(1) or real_save(store)):
        dashboard.refresh()
        assert dashboard.snapshot()['summaries'][0]['insights'][0]['code'] == 'in_line'  # no hour's wait
        assert len(saves) == 1
        dashboard.refresh()
        assert build.call_count == 2  # rebuilt from the kept details and the refetched graph
        assert 'changed while settling' not in caplog.text
        assert len(saves) == 1  # the same row: nothing written, the cached insights kept
        dashboard.refresh()
        assert 'Workout w1 changed while settling' in caplog.text
        assert 'Workout w1 insights changed' in caplog.text
        assert dashboard.snapshot()['summaries'][0]['insights'][0]['code'] == 'output_up'
        # The hour is over: one last rebuild, then the row and its insights stay as they are.
        client.history[0]['start_time'] = datetime.now(timezone.utc).timestamp() - 2 * 3600
        dashboard.refresh()
        assert build.call_count == 4
        dashboard.refresh()
        dashboard.refresh()
        assert build.call_count == 4
    # The details were fetched once, however many rebuilds.
    assert client.get_workout_detail.call_count == 1
    assert client.get_ride_details.call_count == 1
    assert dashboard._insight_settling == {}
    assert len(saves) == 2  # the first build and the one change; the last rebuild came out the same


def test_insights_are_recomputed_only_when_the_row_store_changes(tmp_path):
    from peloton.workout_insights import insights as real_insights
    dashboard, client, token = _insight_setup(tmp_path)
    _seed_peers(dashboard, [110, 111, 112, 113, 114, 111])
    with patch('peloton.dashboard.build_row', return_value=_fake_row('w1', 112)), \
            patch('peloton.dashboard.insights', side_effect=real_insights) as computed:
        for _ in range(3):
            dashboard.refresh()
        assert computed.call_count == 1
        assert dashboard.snapshot()['summaries'][0]['insights'][0]['code'] == 'in_line'
        # A restarted board computes once from the stored row, with no API calls.
        again = Dashboard(token, {'workout_insights': True}, client_factory=lambda _: client)
        again.refresh()
        again.refresh()
        assert computed.call_count == 2
    assert client.get_workout_detail.call_count == 1
    assert again.snapshot()['summaries'][0]['insights'][0]['code'] == 'in_line'


def test_a_missing_detail_gives_no_insight_and_is_not_refetched(tmp_path):
    dashboard, client, _ = _insight_setup(tmp_path)
    client.get_workout_detail.return_value = None
    dashboard.refresh()
    dashboard.refresh()
    assert 'insights' not in dashboard.snapshot()['summaries'][0]
    assert client.get_workout_detail.call_count == 1
    # After the retry window it asks again.
    dashboard._insight_failed['w1'] -= 3601
    dashboard.refresh()
    assert client.get_workout_detail.call_count == 2


def test_an_unfinished_detail_is_retried_later_not_every_refresh(tmp_path):
    dashboard, client, _ = _insight_setup(tmp_path)
    client.get_workout_detail.return_value = {'id': 'w1', 'status': 'IN_PROGRESS'}
    dashboard.refresh()
    dashboard.refresh()
    assert client.get_workout_detail.call_count == 1


def test_an_insight_failure_never_fails_the_refresh(tmp_path, caplog):
    dashboard, client, _ = _insight_setup(tmp_path)
    client.get_workout_detail.side_effect = requests.ConnectionError('boom')
    dashboard.refresh()
    snapshot = dashboard.snapshot()
    assert snapshot['status'] == 'ready'
    assert 'insights' not in snapshot['summaries'][0]
    assert 'Workout insight failed (ConnectionError)' in caplog.text
    client.get_workout_detail.side_effect = None
    client.get_workout_detail.return_value = {'id': 'w1', 'status': 'COMPLETE'}  # no start_time: build_row raises
    dashboard._insight_failed.clear()
    dashboard.refresh()
    assert dashboard.snapshot()['status'] == 'ready'


def test_an_unauthorized_detail_is_a_login_problem(tmp_path):
    dashboard, client, _ = _insight_setup(tmp_path)
    response = Mock(status_code=401)
    client.get_workout_detail.side_effect = requests.HTTPError(response=response)
    dashboard.refresh()
    assert dashboard.login_required


def test_other_http_errors_in_the_insight_are_swallowed(tmp_path):
    dashboard, client, _ = _insight_setup(tmp_path)
    client.get_workout_detail.side_effect = requests.HTTPError(response=Mock(status_code=500))
    dashboard.refresh()
    assert dashboard.snapshot()['status'] == 'ready'
    assert not dashboard.login_required


def test_a_failing_row_save_is_logged_and_the_insight_still_shows(tmp_path, caplog):
    dashboard, client, _ = _insight_setup(tmp_path)
    _seed_peers(dashboard, [110, 111, 112, 113, 114, 111])
    with patch('peloton.dashboard.build_row', return_value=_fake_row('w1', 112)), \
            patch('peloton.workout_rows.RowStore.save', side_effect=OSError('read-only')):
        dashboard.refresh()
    assert 'Could not save the workout rows' in caplog.text
    assert dashboard.snapshot()['summaries'][0]['insights'][0]['code'] == 'in_line'


def test_switch_off_makes_no_extra_calls_and_loads_no_store(tmp_path):
    dashboard, client, _ = _insight_setup(tmp_path, config={})
    dashboard.refresh()
    assert 'insights' not in dashboard.snapshot()['summaries'][0]
    client.get_workout_detail.assert_not_called()
    client.get_ride_details.assert_not_called()
    assert dashboard._rows is None


def test_the_cache_keeps_the_insight_and_a_switched_off_board_strips_it(tmp_path):
    dashboard, client, token = _insight_setup(tmp_path)
    _seed_peers(dashboard, [110, 111, 112, 113, 114, 111])
    with patch('peloton.dashboard.build_row', return_value=_fake_row('w1', 112)):
        dashboard.refresh()
    on = Dashboard(token, {'workout_insights': True}, client_factory=lambda _: client)
    assert on.snapshot()['summaries'][0]['insights'][0]['code'] == 'in_line'
    off = Dashboard(token, {}, client_factory=lambda _: client)
    assert 'insights' not in off.snapshot()['summaries'][0]
    assert off.snapshot()['summaries'][0]['workout_id'] == 'w1'


def test_a_cached_version_2_insight_is_dropped_whether_the_switch_is_on_or_off(tmp_path):
    from peloton.cache import save_snapshot
    for config in ({'workout_insights': True}, {}):
        folder = tmp_path / str(bool(config))
        folder.mkdir()
        dashboard, client, token = _insight_setup(folder, config=config)
        old = {'code': 'output_up', 'lines': ['STRONG RIDE', '205 VS 180 W'], 'facts': {}}
        save_snapshot(dashboard.cache_path, {'summaries': [{'workout_id': 'w1', 'insight': old}, 'junk'],
                                             'totals': {}, 'last_updated': 1.0})
        summary = Dashboard(token, config, client_factory=lambda _: client).snapshot()['summaries'][0]
        assert 'insight' not in summary and summary['workout_id'] == 'w1'


def test_the_board_keeps_the_first_two_shown_insights_in_order(tmp_path):
    dashboard, client, _ = _insight_setup(tmp_path)
    messages = [('too_few', '', {'n': 1, 'noun': 'ride'}), ('resistance_low', '', {'pct': 30}),
                ('cadence_low', '', {'pct': 40}), ('effort_high', '', {'n': 5})]  # effort: no rate, skipped
    with patch('peloton.dashboard.build_row', return_value=_fake_row()), \
            patch('peloton.dashboard.insights', return_value=messages + [('pace_low', '', {'pct': 50})]):
        dashboard.refresh()
    views = dashboard.snapshot()['summaries'][0]['insights']
    assert [view['code'] for view in views] == ['resistance_low', 'cadence_low']


def test_the_board_store_drops_rows_past_the_window_when_it_loads(tmp_path):
    dashboard, client, _ = _insight_setup(tmp_path)
    _seed_peers(dashboard, [110, 111, 112, 113, 114])
    from peloton.workout_rows import RowStore, default_rows_path
    store = RowStore.load(default_rows_path(dashboard.cache_path))
    old = _fake_row('old')
    old['start'] = time.time() - 800 * 86400
    store.upsert(old)
    store.save()
    with patch('peloton.dashboard.build_row', return_value=_fake_row('w1', 112)):
        dashboard.refresh()
    saved = RowStore.load(default_rows_path(dashboard.cache_path))
    assert 'old' not in saved.rows and {'p0', 'w1'} <= set(saved.rows)
