"""The settings page's view of workout-compare history on the board (settings_page/history.py)."""
import json
import os
from pathlib import Path

import pytest

from peloton.config import user_cache_path
from peloton.workout_features import ROW_VERSION
from peloton.workout_rows import BOARD_DAYS, DAY, current_board_rows
from settings_page import history
from settings_page.history import (MISSING, NO_CLASS, NO_GRAPH, NO_MOVEMENTS, OLD, READY, RECENT_DAYS, UNREADABLE,
                                   missing_data, rider_histories, rows_paths)
from tests.test_settings_form import TWO_RIDERS

NOW = 1_800_000_000


def row(identity, days_ago=10, disc='cycling', version=ROW_VERSION, **fields):
    return {'id': identity, 'v': version, 'disc': disc, 'start': NOW - days_ago * DAY, 'has_graph': True,
            'wtype': 'class', 'ctype': 'Power Zone', **fields}


def write_store(path, rows):
    path.write_text(json.dumps({'version': 1, 'rows': {r['id']: r for r in rows} if isinstance(rows, list)
                                else rows}))


@pytest.fixture(autouse=True)
def fresh_counts():
    history._counted.clear()
    yield
    history._counted.clear()


def test_rows_paths_follow_the_display_for_each_rider(tmp_path):
    config = {**TWO_RIDERS, 'users': [{'name': 'Joel'}, {'name': 'Jen', 'token_path': 'tokens/cookies-jen.txt'},
                                      {'name': 'Kid', 'cache_path': '/var/lib/peloton-led/dashboard-cache-kid.json'},
                                      {'name': 'Guest', 'cache_path': 'guest.json'}, 'junk', {'no': 'name'}]}
    assert rows_paths(config, tmp_path, 'unused') == [
        ('Joel', tmp_path / 'cookies-joel-dashboard-cache.workout-rows.json'),
        ('Jen', tmp_path / 'tokens' / 'cookies-jen-dashboard-cache.workout-rows.json'),
        ('Kid', Path('/var/lib/peloton-led/dashboard-cache-kid.workout-rows.json')),
        ('Guest', tmp_path / 'guest.workout-rows.json')]


def test_a_single_rider_board_uses_the_display_cache_or_the_token_folder(tmp_path):
    token = tmp_path / 'tokens' / 'cookies.txt'
    assert rows_paths({}, tmp_path, token) == [('This board', tmp_path / 'tokens' / 'dashboard-cache.workout-rows.json')]
    assert rows_paths({'display': {'username': 'Joel', 'cache_path': 'cache.json'}}, tmp_path, token) == [
        ('Joel', tmp_path / 'cache.workout-rows.json')]
    assert rows_paths({'display': {'username': '', 'cache_path': '/var/lib/x/c.json'}}, tmp_path, token) == [
        ('This board', Path('/var/lib/x/c.workout-rows.json'))]
    assert rows_paths({'users': 'junk', 'display': 'junk'}, tmp_path, token)[0][0] == 'This board'


def test_user_cache_path_matches_the_display(tmp_path):
    assert user_cache_path({'name': 'Joel'}, tmp_path) == tmp_path / 'cookies-joel-dashboard-cache.json'
    assert user_cache_path({'name': 'Joel'}, tmp_path, tmp_path / 'a' / 'tok.txt') == tmp_path / 'a' / 'tok-dashboard-cache.json'
    assert user_cache_path({'name': 'Joel', 'cache_path': '~/c.json'}, tmp_path) == Path('~/c.json').expanduser()


def test_current_board_rows_counts_as_the_board_does():
    rows = {r['id']: r for r in [row('a'), row('b', disc='yoga'), row('c', days_ago=BOARD_DAYS + 1),
                                 row('d', version=ROW_VERSION - 1), row('e', disc='strength')]}
    rows['f'] = 'junk'
    assert sorted(r['id'] for r in current_board_rows(rows, NOW)) == ['a', 'e']


def test_each_riders_history_state(tmp_path):
    write_store(tmp_path / 'cookies-joel-dashboard-cache.workout-rows.json',
                [row('a'), row('b'), row('c', disc='meditation')])
    joel, jen = rider_histories(TWO_RIDERS, tmp_path, 'unused', NOW)
    assert joel['name'] == 'Joel' and joel['state'] == READY and joel['workouts'] == 2
    assert joel['updated'] == pytest.approx(os.path.getmtime(tmp_path / 'cookies-joel-dashboard-cache.workout-rows.json'))
    assert jen == {'name': 'Jen', 'state': MISSING, 'workouts': 0, 'updated': None, 'incomplete': []}
    jen_path = tmp_path / 'cookies-jen-dashboard-cache.workout-rows.json'
    for content, state in ((json.dumps({'version': 1, 'rows': {'x': row('x', version=ROW_VERSION - 1)}}), OLD),
                           (json.dumps({'version': 1, 'rows': {}}), MISSING),
                           ('{not json', UNREADABLE), (json.dumps({'rows': []}), UNREADABLE),
                           (json.dumps(['rows']), UNREADABLE)):
        jen_path.write_text(content)
        os.utime(jen_path, ns=(os.stat(jen_path).st_mtime_ns + 1_000_000,) * 2)  # a new stamp each time
        assert rider_histories(TWO_RIDERS, tmp_path, 'unused', NOW)[1]['state'] == state, content


def test_a_path_that_cannot_be_checked_is_unreadable(tmp_path):
    (tmp_path / 'blocker').write_text('a file, not a folder')
    config = {'users': [{'name': 'Joel', 'cache_path': 'blocker/cache.json'}]}
    assert rider_histories(config, tmp_path, 'unused', NOW)[0]['state'] == UNREADABLE


def test_the_count_is_read_once_until_the_file_changes(tmp_path, monkeypatch):
    path = tmp_path / 'cookies-joel-dashboard-cache.workout-rows.json'
    write_store(path, [row('a')])
    reads = []
    real = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda self, *a, **k: reads.append(self) or real(self, *a, **k))
    assert rider_histories(TWO_RIDERS, tmp_path, 'unused', NOW)[0]['workouts'] == 1
    assert rider_histories(TWO_RIDERS, tmp_path, 'unused', NOW)[0]['workouts'] == 1
    assert reads == [path]
    write_store(path, [row('a'), row('b')])  # the board added a workout
    assert rider_histories(TWO_RIDERS, tmp_path, 'unused', NOW)[0]['workouts'] == 2
    assert reads == [path, path]


def test_what_a_row_can_be_missing():
    assert missing_data(row('a')) == []
    assert missing_data(row('a', has_graph=False)) == [NO_GRAPH]
    assert missing_data(row('a', has_graph=False, ctype=None)) == [NO_GRAPH, NO_CLASS]
    assert missing_data(row('a', disc='strength', asks=None)) == [NO_MOVEMENTS]
    assert missing_data(row('a', disc='strength', ctype=None)) == [NO_CLASS]  # no class: no movements either
    assert missing_data(row('a', disc='strength', asks={'work_min': 20})) == []
    # A freestyle workout never had a class; heart rate and the tracker are the rider's, not a gap.
    assert missing_data(row('a', wtype='freestyle', ctype=None)) == []
    assert missing_data(row('a', disc='strength', wtype='freestyle', ctype=None, hr_avg=None, tracker=None)) == []
    assert missing_data({'id': 'a'}) == [NO_GRAPH]  # an old or odd row without the flag


def test_only_recent_workouts_missing_data_are_listed(tmp_path):
    path = tmp_path / 'cookies-joel-dashboard-cache.workout-rows.json'
    write_store(path, [row('whole', days_ago=1),
                       row('new', days_ago=2, has_graph=False, title='30 min Full Body Strength',
                           date='2027-01-13', disc='strength', asks={'work_min': 20}),
                       row('newer', days_ago=1, ctype=None),
                       row('old', days_ago=RECENT_DAYS + 1, has_graph=False),   # Peloton sent less back then
                       row('yoga', days_ago=1, disc='yoga', has_graph=False),   # not compared on the board
                       row('stale', days_ago=1, has_graph=False, version=ROW_VERSION - 1)])
    joel = rider_histories(TWO_RIDERS, tmp_path, 'unused', NOW)[0]
    assert joel['workouts'] == 4
    assert [(w['id'], w['missing']) for w in joel['incomplete']] == [('newer', [NO_CLASS]), ('new', [NO_GRAPH])]
    assert joel['incomplete'][1] == {'id': 'new', 'start': NOW - 2 * DAY, 'date': '2027-01-13', 'disc': 'strength',
                                     'title': '30 min Full Body Strength', 'missing': [NO_GRAPH]}
    # Kept until the file changes, but a workout still ages out of the window.
    later = rider_histories(TWO_RIDERS, tmp_path, 'unused', NOW + (RECENT_DAYS - 2) * DAY + 1)[0]
    assert [w['id'] for w in later['incomplete']] == ['newer']
