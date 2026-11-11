"""Workout compare row store and daily sync (spec section 7), plus scripts/workout_insights.py."""
import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest
import requests

from peloton import workout_rows
from peloton.workout_features import ROW_VERSION
from peloton.workout_rows import (LoginRequired, RawFiles, RowStore, candidate_ids, default_rows_path,
                                  fetch_row, import_raw, sync)

START = 1_700_000_000
NOW = START + 10 * 86400


def detail(wid='w1', start=START, **over):
    base = {'id': wid, 'start_time': start, 'end_time': start + 1200, 'status': 'COMPLETE',
            'fitness_discipline': 'cycling', 'workout_type': 'class', 'timezone': 'UTC',
            'ride': {'id': f'ride-{wid}', 'duration': 1200}}
    base.update(over)
    return base


GRAPH = {'seconds_since_pedaling_start': [0, 5, 10, 15], 'duration': 20,
         'metrics': [{'slug': 'output', 'values': [10, 20, 30, 40]}]}
RIDE = {'ride': {'id': 'x', 'title': 'T'}}


def http_error(status=500):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f'{status}', response=response)


class FakeClient:
    """Records calls; `details` maps id -> payload (or an exception to raise)."""

    def __init__(self, details=None, graphs=None, rides=None):
        self.details = details or {}
        self.graphs = graphs if graphs is not None else {}
        self.rides = rides if rides is not None else {}
        self.calls = []
        self.login_required = False
        self.closed = False
        self.page = {'data': []}
        self.listed = []

    def _get(self, source, key, name):
        self.calls.append((name, key))
        value = source.get(key)
        if isinstance(value, Exception):
            if isinstance(value, requests.HTTPError) and value.response.status_code == 401:
                self.login_required = True
            raise value
        return value

    def get_workout_detail(self, wid):
        return self._get(self.details, wid, 'detail')

    def get_perf_graph(self, wid):
        return self._get(self.graphs, wid, 'graph')

    def get_ride_details(self, rid):
        return self._get(self.rides, rid, 'ride')

    def get_me(self):
        self.calls.append(('me', None))
        return {'id': 'user1'}

    def get_workouts_page(self, user_id, limit=20, page=0):
        self.calls.append(('page', user_id))
        return self.page

    def page_rows(self, page):
        return self.listed

    def close(self):
        self.closed = True

    def names(self, name):
        return [k for n, k in self.calls if n == name]


def make_client(*wids, **kw):
    return FakeClient(details={w: detail(w, START + i) for i, w in enumerate(wids)},
                      graphs={w: GRAPH for w in wids}, rides={f'ride-{w}': RIDE for w in wids}, **kw)


@pytest.fixture
def raw(tmp_path):
    return RawFiles(tmp_path / 'raw', 'joel')


# --- RowStore ---------------------------------------------------------------------------------

def test_default_rows_path():
    assert default_rows_path('/x/cookies-joel-dashboard-cache.json') == \
        Path('/x/cookies-joel-dashboard-cache.workout-rows.json')


def test_load_missing_is_empty(tmp_path):
    assert RowStore.load(tmp_path / 'none.json').rows == {}


def test_load_unreadable_json_is_empty_with_warning(tmp_path, caplog):
    path = tmp_path / 'rows.json'
    path.write_text('{not json')
    assert RowStore.load(path).rows == {}
    assert 'unreadable' in caplog.text


@pytest.mark.parametrize('payload', [{'version': 2, 'rows': {}}, {'version': 1, 'rows': []},
                                     {'version': 1}, [1, 2]])
def test_load_other_version_or_malformed_is_empty(tmp_path, payload, caplog):
    path = tmp_path / 'rows.json'
    path.write_text(json.dumps(payload))
    assert RowStore.load(path).rows == {}
    assert 'another version or malformed' in caplog.text


def test_load_drops_entries_whose_key_differs_from_id(tmp_path):
    path = tmp_path / 'rows.json'
    path.write_text(json.dumps({'version': 1, 'rows': {
        'a': {'id': 'a', 'v': 1}, 'b': {'id': 'other'}, 'c': 'junk', 'd': {'v': 1}}}))
    assert list(RowStore.load(path).rows) == ['a']


def test_save_load_roundtrip_and_mode(tmp_path):
    store = RowStore(tmp_path / 'sub' / 'rows.json')
    store.upsert({'id': 'a', 'v': ROW_VERSION})
    store.save()
    assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600
    assert RowStore.load(store.path).rows == {'a': {'id': 'a', 'v': ROW_VERSION}}
    assert [p.name for p in store.path.parent.iterdir()] == ['rows.json']


def test_upsert_replaces_by_id():
    store = RowStore('unused')
    store.upsert({'id': 'a', 'n': 1})
    store.upsert({'id': 'a', 'n': 2})
    assert store.rows == {'a': {'id': 'a', 'n': 2}}


def test_is_current_and_stale_ids():
    store = RowStore('unused')
    store.upsert({'id': 'new', 'v': ROW_VERSION})
    store.upsert({'id': 'old', 'v': 0})
    assert store.is_current('new') and not store.is_current('old') and not store.is_current('nope')
    assert store.stale_ids() == ['old']


def test_save_failure_in_dump_keeps_old_file_and_removes_temp(tmp_path, monkeypatch):
    store = RowStore(tmp_path / 'rows.json')
    store.upsert({'id': 'a', 'v': 1})
    store.save()
    before = store.path.read_bytes()
    store.upsert({'id': 'b', 'v': 1})

    def boom(*a, **k):
        raise OSError('disk full')
    monkeypatch.setattr(workout_rows.json, 'dump', boom)
    with pytest.raises(OSError):
        store.save()
    assert store.path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ['rows.json']


def test_save_failure_in_replace_keeps_old_file_and_removes_temp(tmp_path, monkeypatch):
    store = RowStore(tmp_path / 'rows.json')
    store.upsert({'id': 'a', 'v': 1})
    store.save()
    before = store.path.read_bytes()
    store.upsert({'id': 'b', 'v': 1})
    seen = []
    real_replace = os.replace

    def boom(src, dst):
        seen.append(Path(src).name)
        raise OSError('nope')
    monkeypatch.setattr(workout_rows.os, 'replace', boom)
    with pytest.raises(OSError):
        store.save()
    monkeypatch.setattr(workout_rows.os, 'replace', real_replace)
    assert seen == ['.rows.json.new']
    assert store.path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ['rows.json']


def test_save_rejects_nan_without_touching_file(tmp_path):
    store = RowStore(tmp_path / 'rows.json')
    store.upsert({'id': 'a', 'x': 1})
    store.save()
    before = store.path.read_bytes()
    store.upsert({'id': 'b', 'x': float('nan')})
    with pytest.raises(ValueError):
        store.save()
    assert store.path.read_bytes() == before


# --- RawFiles ---------------------------------------------------------------------------------

def test_raw_paths_use_training_data_layout(raw, tmp_path):
    base = tmp_path / 'raw'
    assert raw.detail_path('w') == base / 'joel' / 'w.workout.json'
    assert raw.graph_path('w') == base / 'joel' / 'w.json'
    assert raw.ride_path('r') == base / 'rides' / 'r.json'


def test_raw_save_and_read_back(raw):
    raw.save_detail('w', detail('w'))
    raw.save_graph('w', GRAPH)
    raw.save_ride('r', RIDE)
    assert raw.detail('w')['id'] == 'w'
    assert raw.graph('w') == GRAPH
    assert raw.ride('r') == RIDE and raw.has_ride('r') and not raw.has_ride('zz')
    assert raw.ride(None) is None


def test_workout_ids_empty_folder_and_sorted(raw):
    assert raw.workout_ids() == []
    raw.save_detail('b', detail('b'))
    raw.save_detail('a', detail('a'))
    raw.save_graph('a', GRAPH)  # graph files are not workout ids
    assert raw.workout_ids() == ['a', 'b']


def test_build_returns_row(raw):
    raw.save_detail('w1', detail('w1'))
    raw.save_graph('w1', GRAPH)
    row = raw.build('w1')
    assert row['id'] == 'w1' and row['v'] == ROW_VERSION and row['has_graph'] is True


def test_build_none_when_missing_unreadable_or_incomplete(raw):
    assert raw.build('missing') is None
    raw.folder.mkdir(parents=True)
    raw.detail_path('bad').write_text('{oops')
    assert raw.build('bad') is None
    raw.detail_path('list').write_text('[]')
    assert raw.build('list') is None
    raw.save_detail('prog', detail('prog', status='IN_PROGRESS'))
    assert raw.build('prog') is None


def test_build_logs_and_returns_none_when_build_row_raises(raw, monkeypatch, caplog):
    raw.save_detail('w1', detail('w1'))

    def boom(*a):
        raise RuntimeError('bad')
    monkeypatch.setattr(workout_rows, 'build_row', boom)
    assert raw.build('w1') is None
    assert 'could not build a row' in caplog.text


# --- import_raw -------------------------------------------------------------------------------

def test_import_raw_builds_stale_rows_with_no_client_calls(raw, tmp_path):
    for wid in ('a', 'b'):
        raw.save_detail(wid, detail(wid))
    store = RowStore(tmp_path / 'rows.json')
    store.upsert({'id': 'a', 'v': 0})
    store.upsert({'id': 'b', 'v': 0})
    assert import_raw(store, raw) == 2
    assert store.stale_ids() == [] and store.rows['a']['disc'] == 'cycling'


def test_import_raw_skips_current_and_unbuildable(raw, tmp_path):
    raw.save_detail('a', detail('a'))
    raw.save_detail('b', detail('b', status='IN_PROGRESS'))
    store = RowStore(tmp_path / 'rows.json')
    store.upsert({'id': 'a', 'v': ROW_VERSION, 'marker': 1})
    assert import_raw(store, raw) == 0
    assert store.rows['a']['marker'] == 1 and 'b' not in store.rows


# --- candidate_ids ----------------------------------------------------------------------------

def log_row(start, disc='cycling', status='COMPLETE'):
    return {'start': start, 'discipline': disc, 'status': status}


def test_candidates_from_log_filtered_and_newest_first():
    log_rows = {'old': log_row(NOW - 800 * 86400), 'a': log_row(NOW - 5), 'b': log_row(NOW - 1),
                'yoga': log_row(NOW - 1, 'yoga'), 'prog': log_row(NOW - 1, status='IN_PROGRESS'),
                'nostart': {'status': 'COMPLETE', 'discipline': 'cycling', 'start': None},
                'strstart': log_row('x')}
    assert candidate_ids(log_workouts=log_rows, now=NOW) == ['b', 'a']


def test_candidates_from_listed_rows_with_alias():
    listed = [{'id': 'r1', 'status': 'COMPLETE', 'fitness_discipline': 'caesar', 'start_time': 5},
              {'id': 'y', 'status': 'COMPLETE', 'fitness_discipline': 'yoga', 'start_time': 9},
              {'id': 'p', 'status': 'IN_PROGRESS', 'fitness_discipline': 'cycling', 'start_time': 9},
              {'status': 'COMPLETE', 'fitness_discipline': 'cycling'},
              {'id': 'c', 'status': 'COMPLETE', 'fitness_discipline': 'cycling'}]
    assert candidate_ids(listed=listed, now=NOW) == ['r1', 'c']


def test_candidates_merge_and_dedupe():
    log_rows = {'a': log_row(NOW - 10), 'b': log_row(NOW - 20)}
    listed = [{'id': 'a', 'status': 'COMPLETE', 'fitness_discipline': 'cycling', 'start_time': NOW - 10},
              {'id': 'c', 'status': 'COMPLETE', 'fitness_discipline': 'rowing', 'start_time': NOW - 5}]
    assert candidate_ids(log_workouts=log_rows, listed=listed, now=NOW) == ['c', 'a', 'b']


def test_candidates_nothing():
    assert candidate_ids() == []


# --- fetch_row / sync -------------------------------------------------------------------------

def test_fetch_row_saves_raw_before_building(raw, monkeypatch):
    client = make_client('w1')
    order = []
    real = workout_rows.build_row

    def spy(*a):
        order.append((raw.detail_path('w1').exists(), raw.graph_path('w1').exists(),
                      raw.ride_path('ride-w1').exists()))
        return real(*a)
    monkeypatch.setattr(workout_rows, 'build_row', spy)
    row = fetch_row(client, raw, 'w1')
    assert order == [(True, True, True)]
    assert row['id'] == 'w1' and row['has_graph'] is True
    assert [n for n, _ in client.calls] == ['detail', 'graph', 'ride']


def test_fetch_row_reuses_saved_raw_with_no_calls(raw):
    raw.save_detail('w1', detail('w1'))
    raw.save_graph('w1', GRAPH)
    raw.save_ride('ride-w1', RIDE)
    client = FakeClient()
    assert fetch_row(client, raw, 'w1')['id'] == 'w1'
    assert client.calls == []


def test_fetch_row_does_not_refetch_existing_ride(raw):
    raw.save_ride('ride-w1', RIDE)
    client = make_client('w1')
    fetch_row(client, raw, 'w1')
    assert client.names('ride') == []


def test_fetch_row_ride_not_dict_not_saved(raw):
    client = make_client('w1')
    client.rides = {'ride-w1': None}
    assert fetch_row(client, raw, 'w1')['id'] == 'w1'
    assert not raw.has_ride('ride-w1')


def test_fetch_row_detail_without_ride_makes_no_ride_call(raw):
    client = make_client('w1')
    client.details['w1']['ride'] = None
    assert fetch_row(client, raw, 'w1') is not None
    assert client.names('ride') == []


def test_fetch_row_in_progress_skipped_and_not_saved(raw):
    client = FakeClient(details={'w1': detail('w1', status='IN_PROGRESS')})
    assert fetch_row(client, raw, 'w1') is None
    assert not raw.detail_path('w1').exists()
    client.details['w1'] = detail('w1')  # finished by the next run
    client.graphs['w1'] = GRAPH
    assert fetch_row(client, raw, 'w1')['id'] == 'w1'


def test_fetch_row_refetches_when_saved_detail_is_not_complete(raw):
    raw.save_detail('w1', detail('w1', status='IN_PROGRESS'))
    client = make_client('w1')
    assert fetch_row(client, raw, 'w1') is not None
    assert client.names('detail') == ['w1']


@pytest.mark.parametrize('payload', [None, [], {}, {'id': 'w1'}, {'start_time': 5}])
def test_fetch_row_unusable_detail_returns_none(raw, payload):
    assert fetch_row(FakeClient(details={'w1': payload}), raw, 'w1') is None
    assert not raw.detail_path('w1').exists()


def test_fetch_row_graph_none_builds_without_graph(raw):
    client = make_client('w1')
    client.graphs = {'w1': None}
    row = fetch_row(client, raw, 'w1')
    assert row['has_graph'] is False
    assert not raw.graph_path('w1').exists()


def test_fetch_row_401_raises_login_required(raw):
    client = make_client('w1')
    client.details['w1'] = http_error(401)
    with pytest.raises(LoginRequired):
        fetch_row(client, raw, 'w1')


def test_fetch_row_non_401_http_error_propagates(raw):
    client = make_client('w1')
    client.details['w1'] = http_error(500)
    with pytest.raises(requests.HTTPError):
        fetch_row(client, raw, 'w1')


def test_sync_returns_added_and_saves(raw, tmp_path):
    client = make_client('a', 'b')
    store = RowStore(tmp_path / 'rows.json')
    assert sync(client, store, raw, ['b', 'a']) == ['b', 'a']
    assert set(RowStore.load(store.path).rows) == {'a', 'b'}


def test_sync_skips_current_ids(raw, tmp_path):
    client = make_client('a', 'b')
    store = RowStore(tmp_path / 'rows.json')
    store.upsert({'id': 'a', 'v': ROW_VERSION})
    assert sync(client, store, raw, ['a', 'b']) == ['b']
    assert client.names('detail') == ['b']


def test_sync_refetch_replaces_stale_row_without_duplicate(raw, tmp_path):
    client = make_client('a')
    store = RowStore(tmp_path / 'rows.json')
    store.upsert({'id': 'a', 'v': 0, 'old': True})
    assert sync(client, store, raw, ['a']) == ['a']
    assert list(store.rows) == ['a'] and 'old' not in store.rows['a']


def test_sync_in_progress_picked_up_next_run(raw, tmp_path):
    client = FakeClient(details={'a': detail('a', status='IN_PROGRESS')})
    store = RowStore(tmp_path / 'rows.json')
    assert sync(client, store, raw, ['a']) == []
    assert not store.path.exists() and not raw.detail_path('a').exists()
    client.details['a'] = detail('a')
    client.graphs['a'] = GRAPH
    assert sync(client, store, raw, ['a']) == ['a']


def test_sync_bad_detail_skips_and_continues(raw, tmp_path):
    client = make_client('good')
    client.details['bad'] = None
    store = RowStore(tmp_path / 'rows.json')
    assert sync(client, store, raw, ['bad', 'good']) == ['good']


@pytest.mark.parametrize('exc', [http_error(500), ValueError('bad json'), KeyError('k'), TypeError('t'),
                                 requests.ConnectionError('down')])
def test_sync_recoverable_error_skips_that_workout(raw, tmp_path, exc, caplog):
    client = make_client('good')
    client.details['bad'] = exc
    store = RowStore(tmp_path / 'rows.json')
    assert sync(client, store, raw, ['bad', 'good']) == ['good']
    assert 'skipped' in caplog.text


def test_sync_401_raises_and_keeps_earlier_rows(raw, tmp_path):
    client = make_client('a', 'c')
    client.details['b'] = http_error(401)
    store = RowStore(tmp_path / 'rows.json')
    with pytest.raises(LoginRequired):
        sync(client, store, raw, ['a', 'b', 'c'])
    assert list(RowStore.load(store.path).rows) == ['a']
    assert client.names('detail') == ['a', 'b']


def test_sync_stops_at_limit_newest_first(raw, tmp_path):
    ids = [f'w{i:02d}' for i in range(25)]
    client = make_client(*ids)
    store = RowStore(tmp_path / 'rows.json')
    added = sync(client, store, raw, ids)
    assert added == ids[:20] and client.names('detail') == ids[:20]
    assert workout_rows.MAX_PER_RUN == 20
    assert sync(make_client(*ids), RowStore(tmp_path / 'r2.json'), raw, ids, limit=3) == ids[:3]


# --- scripts/workout_insights.py --------------------------------------------------------------

@pytest.fixture
def script():
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'workout_insights.py'
    spec = importlib.util.spec_from_file_location('workout_insights_script', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def config(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'users': [
        {'name': 'Joel', 'token_path': 'tok.txt', 'cache_path': 'joel-cache.json'}]}))
    return path


def run(script, config, tmp_path, *extra):
    return script.main(['--rider', 'joel', '--config', str(config), '--raw-dir', str(tmp_path / 'raw'),
                        *extra])


def seed_raw(tmp_path, *wids):
    files = RawFiles(tmp_path / 'raw', 'joel')
    for i, wid in enumerate(wids):
        files.save_detail(wid, detail(wid, START + i * 3600))
        files.save_graph(wid, GRAPH)
    return files


def no_client(script, monkeypatch):
    def boom(*a, **k):
        raise AssertionError('client constructed')
    monkeypatch.setattr(script, 'PelotonClient', boom)
    monkeypatch.setattr(script, 'make_session', boom)


def test_script_dry_run_prints_latest_and_writes_nothing(script, config, tmp_path, monkeypatch, capsys):
    no_client(script, monkeypatch)
    seed_raw(tmp_path, 'aaaaaaaa1', 'bbbbbbbb2')
    assert run(script, config, tmp_path, '--dry-run') == 0
    out = capsys.readouterr().out
    assert 'bbbbbbbb' in out and 'aaaaaaaa' not in out
    assert not list(tmp_path.glob('*.workout-rows.json'))


def test_script_dry_run_nothing_stored(script, config, tmp_path, monkeypatch, capsys):
    no_client(script, monkeypatch)
    assert run(script, config, tmp_path, '--dry-run') == 0
    assert 'No in-scope workouts stored for Joel' in capsys.readouterr().out


def test_script_run_stores_and_prints_new_workout(script, config, tmp_path, monkeypatch, capsys):
    client = make_client('cccccccc3')
    client.listed = [{'id': 'cccccccc3', 'status': 'COMPLETE', 'fitness_discipline': 'cycling',
                      'start_time': START}]
    monkeypatch.setattr(script, 'PelotonClient', lambda session: client)
    monkeypatch.setattr(script, 'make_session', lambda token: 'session')
    assert run(script, config, tmp_path) == 0
    assert 'cccccccc' in capsys.readouterr().out
    assert client.closed and client.names('me') == [None]
    assert list(RowStore.load(tmp_path / 'joel-cache.workout-rows.json').rows) == ['cccccccc3']
    assert (tmp_path / 'raw' / 'joel' / 'cccccccc3.workout.json').exists()


def test_script_uses_workout_log_user_id_and_ids(script, config, tmp_path, monkeypatch, capsys):
    import time
    from peloton.workout_log import WorkoutLog, default_log_path
    log_path = default_log_path(tmp_path / 'joel-cache.json')
    wl = WorkoutLog(log_path)
    wl.user_id = 'u9'
    wl.workouts = {'dddddddd4': {'start': int(time.time()) - 60, 'discipline': 'cycling',
                                 'status': 'COMPLETE'}}
    wl.save()
    client = make_client('dddddddd4')
    monkeypatch.setattr(script, 'PelotonClient', lambda session: client)
    monkeypatch.setattr(script, 'make_session', lambda token: 'session')
    assert run(script, config, tmp_path) == 0
    assert client.names('me') == [] and client.names('page') == ['u9']
    assert client.names('detail') == ['dddddddd4']


def test_script_login_required_returns_2_and_keeps_rows(script, config, tmp_path, monkeypatch, capsys):
    client = make_client('eeeeeeee5')
    client.listed = [
        {'id': 'eeeeeeee5', 'status': 'COMPLETE', 'fitness_discipline': 'cycling', 'start_time': START + 9},
        {'id': 'ffffffff6', 'status': 'COMPLETE', 'fitness_discipline': 'cycling', 'start_time': START + 1}]
    client.details['ffffffff6'] = http_error(401)
    monkeypatch.setattr(script, 'PelotonClient', lambda session: client)
    monkeypatch.setattr(script, 'make_session', lambda token: 'session')
    assert run(script, config, tmp_path) == 2
    assert client.closed
    assert list(RowStore.load(tmp_path / 'joel-cache.workout-rows.json').rows) == ['eeeeeeee5']


def test_script_workout_prefix_picks_stored_row(script, config, tmp_path, monkeypatch, capsys):
    no_client(script, monkeypatch)
    seed_raw(tmp_path, 'aaaaaaaa1', 'bbbbbbbb2')
    assert run(script, config, tmp_path, '--dry-run', '--workout', 'aaaa') == 0
    out = capsys.readouterr().out
    assert 'aaaaaaaa' in out and 'bbbbbbbb' not in out


def test_script_unknown_workout_exits(script, config, tmp_path, monkeypatch):
    no_client(script, monkeypatch)
    seed_raw(tmp_path, 'aaaaaaaa1')
    with pytest.raises(SystemExit, match='No stored workout'):
        run(script, config, tmp_path, '--dry-run', '--workout', 'zzz')


def test_script_unknown_rider_exits(script, config, tmp_path):
    with pytest.raises(SystemExit, match='No rider named'):
        script.main(['--rider', 'nobody', '--config', str(config), '--dry-run'])


def test_script_missing_config_exits(script, tmp_path):
    with pytest.raises(SystemExit, match='Config not found'):
        script.main(['--rider', 'joel', '--config', str(tmp_path / 'nope.json'), '--dry-run'])


def test_script_rider_paths_defaults_and_overrides(script, tmp_path):
    config = {'users': [{'name': 'Jen Q', 'token_path': 'cookies-jen.txt'},
                        {'name': 'Al', 'token_path': '/abs/tok.txt', 'cache_path': '/abs/c.json',
                         'log_path': 'lg.json'}]}
    cfg = tmp_path / 'config.json'
    name, token, rows, log_path = script.rider_paths(config, cfg, 'jen-q')
    assert name == 'Jen Q' and token == tmp_path / 'cookies-jen.txt'
    assert rows == tmp_path / 'cookies-jen-dashboard-cache.workout-rows.json'
    assert log_path.parent == tmp_path
    name, token, rows, log_path = script.rider_paths(config, cfg, 'al')
    assert rows == Path('/abs/c.workout-rows.json') and log_path == tmp_path / 'lg.json'


def test_script_import_raw_rebuild_saved_on_real_run(script, config, tmp_path, monkeypatch):
    seed_raw(tmp_path, 'aaaaaaaa1')
    client = FakeClient()
    monkeypatch.setattr(script, 'PelotonClient', lambda session: client)
    monkeypatch.setattr(script, 'make_session', lambda token: 'session')
    assert run(script, config, tmp_path) == 0
    assert 'aaaaaaaa1' in RowStore.load(tmp_path / 'joel-cache.workout-rows.json').rows
    assert client.names('detail') == []
