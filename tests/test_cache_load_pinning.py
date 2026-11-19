"""Pins what load_snapshot accepts, rejects and repairs: the cache holds anything."""
import json

import pytest

from peloton.cache import CACHE_VERSION, load_snapshot
from peloton.club import NOT_A_MEMBER


def base():
    return {'summaries': [], 'totals': {}, 'me': None, 'last_updated': 100}


def write(tmp_path, snapshot, version=CACHE_VERSION):
    path = tmp_path / 'cache.json'
    path.write_text(json.dumps({'version': version, 'snapshot': snapshot}), encoding='utf-8')
    return path


def test_unreadable_files_load_as_none(tmp_path):
    assert load_snapshot(tmp_path / 'missing.json') is None
    bad = tmp_path / 'bad.json'
    bad.write_text('{nope', encoding='utf-8')
    assert load_snapshot(bad) is None
    binary = tmp_path / 'binary.json'
    binary.write_bytes(b'\xff\xfe\x00')
    assert load_snapshot(binary) is None


@pytest.mark.parametrize('payload', [[], 'text', {'snapshot': {}}, {'version': 2, 'snapshot': {}},
                                     {'version': 1, 'snapshot': []}, {'version': 1}])
def test_wrong_envelope_is_rejected(tmp_path, payload):
    path = tmp_path / 'cache.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    assert load_snapshot(path) is None


@pytest.mark.parametrize('change', [
    {'summaries': {}}, {'summaries': None}, {'totals': []}, {'totals': None},
    {'me': 'rider'}, {'me': []},
    {'celebrated_pr_ids': 'x'}, {'celebrated_pr_ids': [1]},
    {'celebrated_milestones': 'x'}, {'celebrated_milestones': ['1']},
    {'weekly_progress': []},
    {'last_updated': None}, {'last_updated': True}, {'last_updated': '1'},
])
def test_damaged_required_fields_reject_the_whole_cache(tmp_path, change):
    assert load_snapshot(write(tmp_path, {**base(), **change})) is None


def test_missing_required_fields_reject_the_whole_cache(tmp_path):
    for key in ('summaries', 'totals', 'last_updated'):
        snapshot = base()
        del snapshot[key]
        assert load_snapshot(write(tmp_path, snapshot)) is None


def test_valid_snapshot_keeps_only_persisted_keys(tmp_path):
    snapshot = {**base(), 'me': {'id': 'u'}, 'celebrated_pr_ids': ['a'], 'celebrated_milestones': [100],
                'weekly_progress': {'x': 1}, 'last_updated': 1.5, 'stray': 'dropped'}
    assert load_snapshot(write(tmp_path, snapshot)) == {k: v for k, v in snapshot.items() if k != 'stray'}


GOOD = {
    'personal_records': {'cycling': {'workout_id': 'w'}},
    'streaks': {'current': 3},
    'milestone_shown_at': {'100': 5, '200': 6.5},
    'pr_shown_at': {'w1': 5},
    'celebrated_discipline_milestones': ['strength:500'],
    'discipline_milestone_shown_at': {'strength:500': 5},
    'challenges': [],
    'booked_classes': [],
    'club': NOT_A_MEMBER,
}


@pytest.mark.parametrize('key', sorted(GOOD))
def test_good_values_are_kept(tmp_path, key):
    assert load_snapshot(write(tmp_path, {**base(), key: GOOD[key]}))[key] == GOOD[key]


BAD = {
    'personal_records': ['x', {'cycling': 'w'}, {'cycling': {'workout_id': 1}}],
    'streaks': ['x', {'current': 'x'}, {'current': True}, {'current': 1.5}],
    'milestone_shown_at': ['x', {'abc': 5}, {'100': 'x'}, {'100': True}],
    'pr_shown_at': ['x', {'w': 'x'}, {'w': True}, ],
    'celebrated_discipline_milestones': ['x', ['bogus'], [5], ['strength:x']],
    'discipline_milestone_shown_at': ['x', {'bogus': 5}, {'strength:500': 'x'}, {'strength:500': True}],
    'challenges': ['x', ['junk'], [{}]],
    'booked_classes': ['x', ['junk'], 5],
    'club': ['x', {}, 5],
}


@pytest.mark.parametrize('key,value', [(k, v) for k, values in sorted(BAD.items()) for v in values])
def test_damaged_optional_entries_are_dropped_not_the_cache(tmp_path, key, value):
    restored = load_snapshot(write(tmp_path, {**base(), key: value}))
    assert restored is not None
    assert key not in restored
    assert restored['summaries'] == [] and restored['totals'] == {}


def test_null_optional_entries_stay_null(tmp_path):
    snapshot = {**base(), 'personal_records': None, 'streaks': None, 'milestone_shown_at': None,
                'pr_shown_at': None, 'celebrated_discipline_milestones': None,
                'discipline_milestone_shown_at': None, 'challenges': None, 'club': None}
    restored = load_snapshot(write(tmp_path, snapshot))
    for key in snapshot:
        assert key in restored


@pytest.mark.parametrize('passes,shown', [(2, {'fact': 3}), (0, {})])
def test_name_facts_cool_down_is_kept_when_sound(tmp_path, passes, shown):
    restored = load_snapshot(write(tmp_path, {**base(), 'name_facts_passes': passes,
                                              'name_facts_shown': shown}))
    assert restored['name_facts_passes'] == passes and restored['name_facts_shown'] == shown


@pytest.mark.parametrize('damage', [
    {'name_facts_passes': True, 'name_facts_shown': {}},
    {'name_facts_passes': 'x', 'name_facts_shown': {}},
    {'name_facts_passes': -1, 'name_facts_shown': {}},
    {'name_facts_passes': 1, 'name_facts_shown': []},
    {'name_facts_passes': 1, 'name_facts_shown': {'f': True}},
    {'name_facts_passes': 1, 'name_facts_shown': {'f': 'x'}},
    {'name_facts_passes': 1},
    {'name_facts_shown': {}},
])
def test_damaged_name_facts_cool_down_drops_both_halves(tmp_path, damage):
    restored = load_snapshot(write(tmp_path, {**base(), **damage}))
    assert restored is not None
    assert 'name_facts_passes' not in restored and 'name_facts_shown' not in restored
