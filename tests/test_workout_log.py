"""The per-workout log: trimming, storage, parity with the old tallies, and the
dashboard flows built on it (backfill, refresh merge, count check, re-walk)."""
import json
import logging
import stat
import time
from unittest.mock import Mock, patch

import pytest
import requests

from peloton.goals import weekly_progress
from peloton.instructors import merge_instructor_counts
from peloton.journey import merge_distance_totals
from peloton.workout_log import LOG_VERSION, WorkoutLog, default_log_path, trim
import peloton.dashboard as dashboard_module
from tests.test_dashboard import recent_fetches, setup_dashboard

NOW = time.time()
DAY = 86400


def _w(identity, age_days=0.0, status='COMPLETE', discipline='cycling', distance=None, instructor=('cody', 'Cody Rigsby'),
       total_work=None, duration=1200, **extra):
    ride = {'fitness_discipline': discipline, 'duration': duration, 'title': f'{duration // 60} min ride',
            'id': f'class-{identity}'}
    if instructor is not None:
        identity_, name = instructor
        ride['instructor'] = {'id': identity_, 'name': name}
    return {'id': identity, 'status': status, 'start_time': int(NOW - age_days * DAY), 'end_time': None,
            'timezone': 'America/New_York', 'fitness_discipline': discipline, 'distance': distance,
            'total_work': total_work, 'ride': ride, **extra}


# trim / as_workout

def test_trim_keeps_the_planned_fields_and_drops_the_bulk():
    raw = _w('w1', distance=5.4, total_work=139000, calories=333.1, is_total_work_personal_record=True,
             effort_zones={'total_effort_points': 14.2, 'heart_rate_zone_durations': {
                 'heart_rate_z1_duration': 60, 'heart_rate_z2_duration': 120, 'heart_rate_z3_duration': 300,
                 'heart_rate_z4_duration': 0, 'heart_rate_z5_duration': 0}},
             is_3p_fit_feed_workout_excluded_from_streaks=True)
    raw['ride']['instructor'].update(bio='x' * 4000, image_url='https://example.com/a.png')
    identity, row, names = trim(raw)
    assert identity == 'w1' and names == {'cody': 'Cody Rigsby'}
    assert row['discipline'] == 'cycling' and row['distance'] == 5.4 and row['total_work_j'] == 139000
    assert row['class_length_s'] == 1200 and row['calories'] == 333.1 and row['ride_id'] == 'class-w1'
    assert row['pr_output'] is True and row['pr_splits'] is False
    assert row['effort_points'] == 14.2 and row['hr_zone_s'] == [60, 120, 300, 0, 0]
    assert row['counts_for_streaks'] is False and row['instructor_id'] == 'cody' and row['group_ids'] is None
    assert len(json.dumps(row)) < 450  # versus ~8 KB per raw row


def test_trim_placeholders_groups_and_bad_values():
    _, placeholder, names = trim(_w('walk', instructor=(None, 'JUST WALK')))
    assert placeholder['instructor_id'] is None and names == {}
    group = _w('pair')
    group['ride']['instructor'] = {'id': 'pair', 'name': 'Jess & Selena', 'is_instructor_group': True,
                                   'individual_instructor_ids': ['selena', 'jess', 'jess', 7, '']}
    _, row, names = trim(group)
    assert row['group_ids'] == ['jess', 'selena'] and names == {}
    group['ride']['instructor']['individual_instructor_ids'] = 'nope'
    assert trim(group)[1]['group_ids'] == []
    odd = {'id': 'odd', 'status': 5, 'distance': True, 'total_work': 'lots', 'ride': 'not a dict',
           'effort_zones': [], 'name': 'Strength Workout'}
    _, row, _ = trim(odd)
    assert row['status'] is None and row['distance'] is None and row['total_work_j'] is None
    assert row['start'] is None and row['title'] == 'Strength Workout' and row['hr_zone_s'] is None
    assert trim({'status': 'COMPLETE'}) == (None, None, {})
    assert trim('not a workout') == (None, None, {})


def test_as_workout_round_trips_through_the_existing_readers():
    history = [_w('a', 0.1, discipline='caesar', distance=2000, instructor=('alex', 'Alex Karwoski')),
               _w('b', 1, distance=10.5, total_work=200000, duration=1800),
               _w('c', 2, status='IN_PROGRESS', distance=3),
               _w('d', 400, discipline='running', distance=3.1, instructor=(None, 'JUST RUN')),
               _w('e', 3, discipline='strength', duration=600, instructor=('jess', 'Jess Sims'))]
    log = WorkoutLog('unused')
    log.merge(history)
    log.backfill['complete'] = True
    rebuilt = log.as_workouts()
    assert [w['id'] for w in rebuilt] == ['a', 'b', 'c', 'e', 'd']
    for metric in (False, True):
        for since in (None, '2025-01-01'):
            assert (merge_distance_totals({}, rebuilt, metric, since=since, tzname='America/New_York')
                    == merge_distance_totals({}, history, metric, since=since, tzname='America/New_York'))
    assert merge_instructor_counts({}, {}, rebuilt) == merge_instructor_counts({}, {}, history)
    assert weekly_progress(rebuilt, 'America/New_York') == weekly_progress(history, 'America/New_York')


def test_derived_figures_match_the_old_tallies_and_wait_for_a_complete_log():
    history = [_w('a', 0.2, distance=4.0), _w('b', 1, instructor=('jess', 'Jess Sims'))]
    log = WorkoutLog('unused')
    log.merge(history)
    partial = log.derived(journey={'start_date': None}, tzname='America/New_York')
    assert partial['instructor_counts'] == {} and partial['distance_totals'] == {}
    assert partial['weekly_progress'] == weekly_progress(history, 'America/New_York')
    log.backfill['complete'] = True
    full = log.derived(journey={'start_date': None}, tzname='America/New_York')
    assert full['instructor_counts'] == {'cody': 1, 'jess': 1}
    assert full['instructor_names'] == {'cody': 'Cody Rigsby', 'jess': 'Jess Sims'}
    assert full['distance_totals'] == {'cycling': 4.0}


# merge by ID

def test_merge_overwrites_by_id_so_finishing_and_edits_count_once():
    log = WorkoutLog('unused')
    assert log.merge([_w('w1', status='IN_PROGRESS', distance=1.0)]) == ['w1']
    assert log.merge([_w('w1', distance=5.0)]) == ['w1']          # finished
    assert log.merge([_w('w1', distance=5.2)]) == ['w1']          # Peloton corrected it later
    revision = log.revision
    assert log.merge([_w('w1', distance=5.2)]) == []              # same page again: no change
    assert log.revision == revision
    log.backfill['complete'] = True
    assert log.derived()['distance_totals'] == {'cycling': 5.2}
    assert len(log.workouts) == 1


def test_instructor_rename_updates_the_directory():
    log = WorkoutLog('unused')
    log.merge([_w('w1', instructor=('robin', 'Robin Arzon'))])
    assert log.merge([_w('w1', instructor=('robin', 'Robin Arzón'))]) == ['w1']
    assert log.instructors == {'robin': 'Robin Arzón'}


def test_walk_removes_only_rows_neither_the_walk_nor_a_refresh_saw():
    log = WorkoutLog('unused')
    log.merge([_w('kept'), _w('deleted'), _w('new')])
    log.begin_walk()
    log.merge([_w('kept')])            # the walk's pages
    log.merge([_w('during')])          # a refresh merges a brand-new workout mid-walk
    assert log.end_walk(remove_unseen=True) == 2
    assert set(log.workouts) == {'kept', 'during'}
    log.begin_walk()
    assert log.end_walk(remove_unseen=False) == 0 and len(log.workouts) == 2
    assert log.end_walk(remove_unseen=True) == 0  # no walk running


# storage

def test_save_and_load_round_trip_privately(tmp_path):
    path = tmp_path / 'state' / 'cache.workouts.json'
    log = WorkoutLog(path)
    log.claim('user-1')
    log.merge([_w('w1', distance=2.5), _w('w2', instructor=('jess', 'Jess Sims'))])
    log.backfill.update(complete=True, next_page=0, finished_at=NOW)
    log.check['mismatches'] = 2
    log.save()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(path.parent.glob('.*.tmp'))
    loaded = WorkoutLog.load(path)
    assert loaded.user_id == 'user-1' and loaded.complete and loaded.check['mismatches'] == 2
    assert loaded.workouts == log.workouts and loaded.instructors == log.instructors


@pytest.mark.parametrize('contents', [
    'not json', json.dumps([1]), json.dumps({'version': 99}),
    json.dumps({'version': LOG_VERSION, 'workouts': [], 'instructors': {}, 'backfill': {}, 'check': {}}),
    json.dumps({'version': LOG_VERSION, 'workouts': {'w': {'start': 'soon'}}, 'instructors': {},
                'backfill': {}, 'check': {}}),
    json.dumps({'version': LOG_VERSION, 'workouts': {}, 'instructors': {'x': 5}, 'backfill': {}, 'check': {}}),
    json.dumps({'version': LOG_VERSION, 'workouts': {}, 'instructors': {}, 'backfill': {}, 'check': {},
                'user_id': 7}),
])
def test_damaged_or_unknown_logs_start_over(tmp_path, contents, caplog):
    path = tmp_path / 'log.json'
    path.write_text(contents)
    with caplog.at_level(logging.WARNING):
        log = WorkoutLog.load(path)
    assert log.workouts == {} and log.user_id is None and not log.complete
    assert 'rebuilding' in caplog.text


def test_missing_log_and_odd_progress_fields_load_safely(tmp_path):
    assert WorkoutLog.load(tmp_path / 'missing.json').workouts == {}
    path = tmp_path / 'log.json'
    path.write_text(json.dumps({'version': LOG_VERSION, 'user_id': 'u', 'workouts': {}, 'instructors': {},
                                'backfill': {'complete': 'yes', 'next_page': 'x'},
                                'check': {'mismatches': True, 'last_rewalk': 'never'}}))
    log = WorkoutLog.load(path)
    assert not log.complete and log.backfill['next_page'] == 0
    assert log.check == {'mismatches': 0, 'last_rewalk': None}


def test_claim_ties_the_log_to_one_account(caplog):
    log = WorkoutLog('unused')
    assert log.claim('joel') is False and log.user_id == 'joel'
    log.merge([_w('w1')])
    assert log.claim('joel') is False and log.workouts
    with caplog.at_level(logging.WARNING):
        assert log.claim('jen') is True
    assert log.user_id == 'jen' and log.workouts == {} and 'another Peloton account' in caplog.text


def test_default_log_path_sits_beside_the_cache(tmp_path):
    assert default_log_path(tmp_path / 'dashboard-cache-joel.json') == tmp_path / 'dashboard-cache-joel.workouts.json'


def test_save_failure_leaves_no_temporary_file(tmp_path):
    log = WorkoutLog(tmp_path / 'log.json')
    log.merge([_w('w1')])
    with patch('peloton.workout_log.json.dump', side_effect=ValueError('boom')):
        with pytest.raises(ValueError):
            log.save()
    assert list(tmp_path.iterdir()) == []


# dashboard: backfill and refresh

def _dashboard(tmp_path, history, **config):
    dashboard, client, token = setup_dashboard(tmp_path, config)
    client.history = list(history)
    return dashboard, client, token


def _refresh(dashboard):
    delay = dashboard.refresh()
    assert dashboard.wait_for_history(5)
    return delay


def _history(count, start_age=0.0, step=0.5, **kwargs):
    return [_w(f'w{index:04d}', start_age + index * step, **kwargs) for index in range(count)]


def test_first_refresh_shows_at_once_then_backfills_in_batches(tmp_path, caplog):
    history = _history(250, distance=1.0)
    dashboard, client, _ = _dashboard(tmp_path, history)
    gate = Mock(wraps=dashboard_module.Dashboard._log_pause)
    with caplog.at_level(logging.INFO):
        with patch.object(dashboard_module.Dashboard, '_log_pause', lambda self: gate(self)):
            _refresh(dashboard)
    batches = [c.kwargs for c in client.get_workouts_page.call_args_list if c.kwargs['limit'] == 100]
    assert [b['page'] for b in batches] == [0, 1, 2]
    assert gate.call_count == 3
    snap = dashboard.snapshot()
    assert snap['status'] == 'ready'
    assert snap['instructor_counts'] == {'cody': 250}
    assert snap['distance_totals'] == {'cycling': 250.0}
    log = WorkoutLog.load(dashboard.log_path)
    assert log.complete and len(log.workouts) == 250 and log.user_id == 'demo'
    assert 'finished: 250 workouts in the log, Peloton reports 250, 0 removed' in caplog.text


def test_history_figures_stay_hidden_until_the_backfill_finishes(tmp_path):
    dashboard, client, _ = _dashboard(tmp_path, _history(30, distance=1.0))
    with patch.object(dashboard_module.Dashboard, '_start_history_walk'):
        dashboard.refresh()
    snap = dashboard.snapshot()
    assert snap['status'] == 'ready' and snap['summaries']
    assert snap['instructor_counts'] == {} and snap['distance_totals'] == {}


def test_backfill_resumes_after_a_failure_mid_download(tmp_path, caplog):
    history = _history(250)
    dashboard, client, _ = _dashboard(tmp_path, history)
    serve = client.get_workouts_page.side_effect
    def flaky(user_id, limit, page=0):
        if limit == 100 and page == 1 and not flaky.failed:
            flaky.failed = True
            raise requests.ConnectionError('wifi dropped')
        return serve(user_id, limit, page)
    flaky.failed = False
    client.get_workouts_page.side_effect = flaky
    with caplog.at_level(logging.WARNING):
        _refresh(dashboard)
    assert 'download paused (ConnectionError)' in caplog.text
    log = WorkoutLog.load(dashboard.log_path)
    assert not log.complete and log.backfill['next_page'] == 1 and len(log.workouts) == 100
    client.get_workouts_page.reset_mock()
    _refresh(dashboard)
    assert [c.kwargs['page'] for c in client.get_workouts_page.call_args_list if c.kwargs['limit'] == 100] == [1, 2]
    log = WorkoutLog.load(dashboard.log_path)
    assert log.complete and len(log.workouts) == 250
    assert dashboard.snapshot()['instructor_counts'] == {'cody': 250}


def test_steady_refresh_is_one_small_page(tmp_path):
    dashboard, client, _ = _dashboard(tmp_path, _history(250))
    _refresh(dashboard)
    client.reset_mock()
    _refresh(dashboard)
    assert client.get_me.call_count == 0          # profile cached for a day
    assert client.get_overview.call_count == 1
    assert [c.kwargs for c in client.get_workouts_page.call_args_list] == [{'limit': 20, 'page': 0}]


def test_in_progress_workout_counts_once_it_finishes(tmp_path):
    # Regression (#27): a cursor used to step past running workouts for good.
    history = _history(30, start_age=1, distance=2.0)
    dashboard, client, _ = _dashboard(tmp_path, [_w('live', 0.01, status='IN_PROGRESS', distance=0.5)] + history)
    _refresh(dashboard)
    assert dashboard.snapshot()['distance_totals'] == {'cycling': 60.0}
    client.history[0] = _w('live', 0.01, distance=6.0)
    _refresh(dashboard)
    assert dashboard.snapshot()['distance_totals'] == {'cycling': 66.0}
    assert dashboard.snapshot()['instructor_counts'] == {'cody': 31}


def test_deleting_the_newest_workout_never_double_counts(tmp_path):
    # Regression: with a cursor, deleting the cursor workout re-added the whole history.
    history = _history(150, distance=1.0)
    dashboard, client, _ = _dashboard(tmp_path, history)
    _refresh(dashboard)
    del client.history[0]
    for _ in range(5):
        _refresh(dashboard)
    snap = dashboard.snapshot()
    assert snap['distance_totals']['cycling'] <= 150.0
    assert snap['instructor_counts'] == {'cody': 150} or snap['instructor_counts'] == {'cody': 149}


def test_lasting_count_mismatch_rewalks_once_and_drops_deleted_workouts(tmp_path, caplog):
    history = _history(150, distance=1.0)
    dashboard, client, _ = _dashboard(tmp_path, history)
    _refresh(dashboard)
    del client.history[60]                       # deleted in Peloton, deep in history
    walks = []
    original = dashboard_module.Dashboard._walk_history
    def track(self, client_, user_id, rewalk):
        walks.append(rewalk)
        return original(self, client_, user_id, rewalk)
    with patch.object(dashboard_module.Dashboard, '_walk_history', track), caplog.at_level(logging.WARNING):
        _refresh(dashboard)
        _refresh(dashboard)
        assert walks == []                       # a brief lag is ridden out
        _refresh(dashboard)
        assert walks == [True]
        assert dashboard.snapshot()['instructor_counts'] == {'cody': 149}
        log = WorkoutLog.load(dashboard.log_path)
        assert len(log.workouts) == 149 and log.check['mismatches'] == 0 and log.check['last_rewalk']
        del client.history[10]
        for _ in range(4):
            _refresh(dashboard)
        assert walks == [True]                   # at most one re-walk a day
    assert 'has 149 workouts but Peloton reports 148 (3 refresh(es) in a row)' in caplog.text


def test_count_matches_reset_the_mismatch_streak(tmp_path):
    history = _history(30)
    dashboard, client, _ = _dashboard(tmp_path, history)
    _refresh(dashboard)
    client.history.append(_w('old-import', 400))   # appears at the very end of history
    _refresh(dashboard)
    assert WorkoutLog.load(dashboard.log_path).check['mismatches'] == 1
    client.history.pop()
    _refresh(dashboard)
    assert WorkoutLog.load(dashboard.log_path).check['mismatches'] == 0


def test_rewalk_waits_for_quiet_hours_when_a_schedule_is_set(tmp_path):
    schedule = {'quiet_start': '23:00', 'quiet_end': '05:30', 'quiet_interval': 1800}
    dashboard, client, _ = _dashboard(tmp_path, _history(30), refresh_schedule=schedule)
    _refresh(dashboard)
    client.history.pop()
    with patch.object(dashboard_module, 'in_quiet_hours', return_value=False), \
         patch.object(dashboard_module.Dashboard, '_start_history_walk') as start:
        for _ in range(4):
            dashboard.refresh()
        start.assert_not_called()
    with patch.object(dashboard_module, 'in_quiet_hours', return_value=True):
        _refresh(dashboard)
    assert len(WorkoutLog.load(dashboard.log_path).workouts) == 29


def test_downtime_gap_is_closed_on_the_next_refresh(tmp_path):
    history = _history(100, start_age=10)
    dashboard, client, _ = _dashboard(tmp_path, history)
    _refresh(dashboard)
    # The board was off while 45 new workouts happened.
    client.history = _history(45, step=0.2, instructor=('jess', 'Jess Sims')) + history
    client.history = [dict(w, id=f'new{i}') if i < 45 else w for i, w in enumerate(client.history)]
    client.get_workouts_page.reset_mock()
    _refresh(dashboard)
    assert [c.kwargs['page'] for c in client.get_workouts_page.call_args_list] == [0, 1, 2]
    assert dashboard.snapshot()['instructor_counts'] == {'cody': 100, 'jess': 45}


def test_latest_day_longer_than_one_page_is_shown_whole(tmp_path):
    busy_day = [_w(f'today{i}', 0.001 * (i + 1), instructor=('jess', 'Jess Sims')) for i in range(25)]
    dashboard, client, _ = _dashboard(tmp_path, busy_day + _history(10, start_age=3))
    client.get_perf_graph.return_value = None
    _refresh(dashboard)
    assert dashboard.snapshot()['active_day_count'] == 25


def test_this_week_is_complete_before_the_backfill_finishes(tmp_path):
    from peloton.goals import week_start
    monday, now = week_start('America/New_York')
    hours = max(1.0, (now - monday).total_seconds() / 3600 - 1)
    week = [_w(f'wk{i}', (hours * (i + 1) / 31) / 24, duration=600, instructor=('jess', 'Jess Sims'))
            for i in range(30)]
    dashboard, client, _ = _dashboard(tmp_path, week + _history(10, start_age=8))
    dashboard.config['timezone'] = 'America/New_York'
    with patch.object(dashboard_module.Dashboard, '_start_history_walk'):
        dashboard.refresh()
    assert dashboard.snapshot()['weekly_progress']['workouts'] == 30
    assert recent_fetches(client) == 2


def test_journey_start_date_change_needs_no_downloads(tmp_path):
    history = [_w('recent', 1, distance=3.0), _w('old', 500, distance=7.0)]
    dashboard, client, _ = _dashboard(tmp_path, history)
    _refresh(dashboard)
    assert dashboard.snapshot()['distance_totals'] == {'cycling': 10.0}
    client.reset_mock()
    dashboard.config['journey'] = {'from': 'A', 'to': 'B', 'miles': 100, 'disciplines': None,
                                   'start_date': '2026-01-01' if time.gmtime(NOW - 500 * DAY).tm_year < 2026
                                   else time.strftime('%Y-%m-%d', time.gmtime(NOW - 100 * DAY))}
    _refresh(dashboard)
    assert dashboard.snapshot()['distance_totals'] == {'cycling': 3.0}
    assert [c.kwargs['limit'] for c in client.get_workouts_page.call_args_list] == [20]


def test_placeholder_instructors_never_rank(tmp_path):
    # Regression (#28): "JUST WALK" was Jen's #2 instructor.
    history = [_w(f'walk{i}', i, discipline='walking', instructor=(None, 'JUST WALK')) for i in range(5)]
    history += [_w('class', 6, instructor=('cody', 'Cody Rigsby'))]
    dashboard, _, _ = _dashboard(tmp_path, history)
    _refresh(dashboard)
    assert dashboard.snapshot()['instructor_counts'] == {'cody': 1}


# dashboard: profile, ownership, restart

def test_profile_is_slim_and_fetched_daily(tmp_path, monkeypatch):
    dashboard, client, _ = _dashboard(tmp_path, _history(5))
    client.get_me.return_value = {'id': 'demo-user', 'username': 'Rider', 'timezone': 'America/New_York',
                                  'height_unit': 'imperial', 'email': 'rider@example.com',
                                  'birthday': 0, 'phone_number': '555', 'weight': 180}
    clock = [1000.0]
    monkeypatch.setattr(dashboard_module.time, 'monotonic', lambda: clock[0])
    _refresh(dashboard)
    assert dashboard.snapshot()['me'] == {'id': 'demo-user', 'username': 'Rider',
                                          'timezone': 'America/New_York', 'height_unit': 'imperial'}
    cache = json.loads(dashboard.cache_path.read_text())
    assert 'email' not in json.dumps(cache) and 'phone_number' not in json.dumps(cache)
    clock[0] += 23 * 3600
    _refresh(dashboard)
    assert client.get_me.call_count == 1
    clock[0] += 3600
    _refresh(dashboard)
    assert client.get_me.call_count == 2


def test_old_cache_profile_is_slimmed_on_load_and_old_tally_keys_dropped(tmp_path):
    dashboard, client, token = _dashboard(tmp_path, _history(5))
    _refresh(dashboard)
    payload = json.loads(dashboard.cache_path.read_text())
    payload['snapshot']['me'] = {'id': 'demo', 'email': 'rider@example.com', 'username': 'Rider'}
    payload['snapshot'].update(instructor_counts={'JUST WALK': 9}, instructor_tally_cursor='w', tally_version=3)
    dashboard.cache_path.write_text(json.dumps(payload))
    restarted = dashboard_module.Dashboard(token, {}, client_factory=lambda _: client)
    snap = restarted.snapshot()
    assert snap['me'] == {'id': 'demo', 'username': 'Rider'}
    assert snap['instructor_counts'] == {'cody': 5}          # from the log, not the old cache
    assert 'tally_version' not in snap and 'instructor_tally_cursor' not in snap


def test_restart_shows_lifetime_figures_from_the_log_before_any_refresh(tmp_path):
    dashboard, client, token = _dashboard(tmp_path, _history(40, distance=1.5))
    _refresh(dashboard)
    offline = Mock()
    offline.get_me.side_effect = requests.ConnectionError('offline')
    restarted = dashboard_module.Dashboard(token, {}, client_factory=lambda _: offline)
    snap = restarted.snapshot()
    assert snap['status'] == 'cached'
    assert snap['instructor_counts'] == {'cody': 40} and snap['distance_totals'] == {'cycling': 60.0}


def test_a_log_for_another_account_is_replaced(tmp_path, caplog):
    dashboard, client, token = _dashboard(tmp_path, _history(5))
    _refresh(dashboard)
    token.write_text('someone-else')               # a different rider's token
    client.get_me.return_value = {'id': 'other-user', 'username': 'Other'}
    client.history = _history(3, instructor=('jess', 'Jess Sims'))
    with caplog.at_level(logging.WARNING):
        _refresh(dashboard)
    assert 'another Peloton account' in caplog.text
    log = WorkoutLog.load(dashboard.log_path)
    assert log.user_id == 'other-user' and len(log.workouts) == 3
    assert dashboard.snapshot()['instructor_counts'] == {'jess': 3}


def test_log_path_can_be_configured(tmp_path):
    dashboard, _, _ = _dashboard(tmp_path, _history(3), log_path=str(tmp_path / 'logs' / 'joel.json'))
    _refresh(dashboard)
    assert (tmp_path / 'logs' / 'joel.json').exists()


def test_unwritable_log_is_logged_and_the_board_keeps_going(tmp_path, caplog):
    dashboard, _, _ = _dashboard(tmp_path, _history(3))
    with patch.object(WorkoutLog, 'save', side_effect=OSError('read-only')), caplog.at_level(logging.WARNING):
        _refresh(dashboard)
    assert 'Could not save the workout log (OSError)' in caplog.text
    assert dashboard.snapshot()['status'] == 'ready'


def test_stop_also_stops_a_running_backfill(tmp_path, monkeypatch):
    import threading
    dashboard, client, _ = _dashboard(tmp_path, _history(500))
    paused = threading.Event()
    def slow_pause(self):
        paused.set()
        return not self._stop.wait(5)
    monkeypatch.setattr(dashboard_module.Dashboard, '_log_pause', slow_pause)
    dashboard.refresh()
    assert paused.wait(2)
    assert dashboard.stop(timeout=2)
    assert not dashboard._history_running()
    log = WorkoutLog.load(dashboard.log_path)
    assert not log.complete and log.backfill['next_page'] == 1


def test_walk_for_a_replaced_account_stops(tmp_path):
    dashboard, client, _ = _dashboard(tmp_path, _history(250))
    dashboard._log.claim('demo')
    dashboard._log.user_id = 'someone-else'
    dashboard._walk_history(client, 'demo', rewalk=False)
    assert dashboard._log.workouts == {}


def test_group_classes_and_unloggable_rows_through_the_log():
    group = _w('pair', instructor=None)
    group['ride']['instructor'] = {'id': 'pair', 'is_instructor_group': True,
                                   'individual_instructor_ids': ['jess', 'selena']}
    history = [group, _w('solo', 1, instructor=('jess', 'Jess Sims')), {'status': 'COMPLETE'}]
    log = WorkoutLog('unused')
    assert log.merge(history) == ['pair', 'solo']
    log.backfill['complete'] = True
    derived = log.derived()
    assert derived['instructor_counts'] == {'jess': 2, 'selena': 1}
    assert derived['instructor_names'] == {'jess': 'Jess Sims'}


def test_empty_history_and_missing_total_are_handled(tmp_path):
    dashboard, client, _ = _dashboard(tmp_path, [])
    _refresh(dashboard)
    snap = dashboard.snapshot()
    assert snap['status'] == 'ready' and snap['summaries'] == [] and snap['instructor_counts'] == {}
    assert WorkoutLog.load(dashboard.log_path).complete
    serve = client.get_workouts_page.side_effect
    client.history = _history(3)
    client.get_workouts_page.side_effect = lambda *a, **k: {k2: v for k2, v in serve(*a, **k).items() if k2 != 'total'}
    for _ in range(4):
        _refresh(dashboard)
    assert WorkoutLog.load(dashboard.log_path).check['mismatches'] == 0  # no total: no check


def test_refresh_during_a_walk_skips_the_count_check(tmp_path, monkeypatch):
    import threading
    dashboard, client, _ = _dashboard(tmp_path, _history(300))
    paused, release = threading.Event(), threading.Event()
    def held_pause(self):
        paused.set()
        return release.wait(5)
    monkeypatch.setattr(dashboard_module.Dashboard, '_log_pause', held_pause)
    assert dashboard.wait_for_history(0)          # nothing running yet
    dashboard.refresh()
    assert paused.wait(2)
    with patch.object(dashboard_module.Dashboard, '_start_history_walk') as start:
        dashboard.refresh()                         # walk still running
        start.assert_not_called()
    release.set()
    assert dashboard.wait_for_history(5)
    assert dashboard.snapshot()['instructor_counts'] == {'cody': 300}


def test_older_log_figures_never_overwrite_newer_ones(tmp_path):
    # A refresh computes figures, the history download finishes and publishes
    # the complete ones, then the refresh publishes: the older set must lose.
    dashboard, _, _ = _dashboard(tmp_path, _history(5))
    _refresh(dashboard)
    stale = dashboard._compute_derived(dashboard._derive_args)
    fresh = ({**stale[0], 'instructor_counts': {'cody': 99}}, stale[1] + 1)
    dashboard._derived_computed = fresh[1]
    dashboard._publish_derived(*fresh)
    dashboard._publish_derived({**stale[0], 'instructor_counts': {}}, stale[1])
    assert dashboard.snapshot()['instructor_counts'] == {'cody': 99}
