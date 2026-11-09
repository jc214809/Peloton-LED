"""scripts/list_facts.py: every name-page fact for a workout log, offline."""
from datetime import datetime, timezone

import pytest

from peloton.cache import save_snapshot
from peloton.workout_log import WorkoutLog
from scripts import list_facts
from scripts.list_facts import demo_log, snapshot_for

NOW = datetime(2026, 11, 8, 17, 0, tzinfo=timezone.utc)


def _saved_demo_log(tmp_path, complete=True):
    log = demo_log(NOW)
    log.path = tmp_path / 'dashboard-cache-rider.workouts.json'
    log.backfill['complete'] = complete
    log.save()
    return log.path


def test_the_demo_log_is_deterministic_and_has_classes_that_repeat():
    first, second = demo_log(NOW), demo_log(NOW)
    assert first.workouts == second.workouts and len(first.workouts) > 500
    rides = [row['ride_id'] for row in first.workouts.values()]
    assert len(set(rides)) < len(rides)


def test_snapshot_counts_discipline_totals_from_the_log_without_a_cache():
    snapshot = snapshot_for(demo_log(NOW), 'America/New_York', NOW, assume_complete=True)
    totals = snapshot['totals']
    assert totals['Total Workouts'] == sum(count for label, count in totals.items() if label != 'Total Workouts')
    assert 'Bike Bootcamp' in totals and set(snapshot['time_frames']) >= {'30d', 'year', 'all'}


def test_snapshot_takes_the_totals_from_a_cache_when_given(tmp_path):
    cache = tmp_path / 'cache.json'
    save_snapshot(cache, {'me': {}, 'totals': {'Total Workouts': 2123, 'Cycling': 641}, 'summaries': [], 'last_updated': 1773496800})
    snapshot = snapshot_for(demo_log(NOW), None, NOW, cache, assume_complete=True)
    assert snapshot['totals'] == {'Total Workouts': 2123, 'Cycling': 641}


def test_an_unreadable_cache_stops_the_script(tmp_path):
    with pytest.raises(SystemExit, match='dashboard cache'):
        snapshot_for(demo_log(NOW), None, NOW, tmp_path / 'missing.json', assume_complete=True)


def test_demo_prints_the_frames_the_facts_and_the_first_passes(capsys):
    assert list_facts.main(['--demo', '--tz', 'America/New_York', '--passes', '3']) == 0
    out = capsys.readouterr().out
    assert 'TOP DISCIPLINE' in out and 'LAST 30 DAYS' in out and '== year' in out
    assert 'pass 0: TOTAL WORKOUTS | THIS WEEK | TOP DISCIPLINE | TOP INSTRUCTOR' in out
    assert 'pass 2:' in out and 'pass 3:' not in out


def test_a_log_file_works_when_its_backfill_is_complete(tmp_path, capsys):
    path = _saved_demo_log(tmp_path)
    assert list_facts.main(['--log', str(path), '--passes', '1']) == 0
    assert '== 30d' in capsys.readouterr().out


def test_an_unfinished_log_has_no_frames_until_assumed_complete(tmp_path, capsys):
    path = _saved_demo_log(tmp_path, complete=False)
    list_facts.main(['--log', str(path), '--passes', '1'])
    assert 'backfill is not complete' in capsys.readouterr().out
    list_facts.main(['--log', str(path), '--passes', '1', '--assume-complete'])
    assert '== 30d' in capsys.readouterr().out


def test_a_missing_or_empty_log_stops_the_script(tmp_path):
    with pytest.raises(SystemExit, match='No workout log'):
        list_facts.main(['--log', str(tmp_path / 'nope.json')])
    empty = tmp_path / 'empty.workouts.json'
    WorkoutLog(empty).save()
    with pytest.raises(SystemExit, match='empty'):
        list_facts.main(['--log', str(empty)])


def test_one_source_is_required():
    with pytest.raises(SystemExit):
        list_facts.main([])
