"""The dashboard cache file's exact bytes are pinned, so a refactor of peloton/dashboard*.py
cannot change what a board writes or what an older board's file reads back as."""
import json
from pathlib import Path

from peloton.cache import PERSISTED_KEYS, load_snapshot
from peloton.challenges import parse_challenges
from peloton.dashboard import Dashboard
from peloton.demo import demo_bookings, demo_club, demo_data
from tests.test_dashboard import setup_dashboard

EXPECTED = Path(__file__).parent / 'fixtures' / 'dashboard_cache_expected.json'
FIXED_NOW = 1_700_000_000.0


def populated_dashboard(tmp_path):
    """A dashboard after a real refresh, then every other persisted field filled with fixed values."""
    dashboard, _client, _token = setup_dashboard(tmp_path, {'cache_path': str(tmp_path / 'cache.json')})
    dashboard.refresh()
    dashboard._publish(
        last_updated=FIXED_NOW, generation=7,
        celebrated_pr_ids=['pr-1'], pr_shown_at={'pr-1': FIXED_NOW - 60},
        celebrated_milestones=[100, 250], milestone_shown_at={'250': FIXED_NOW - 90},
        celebrated_discipline_milestones=['strength:100'],
        discipline_milestone_shown_at={'strength:100': FIXED_NOW - 120},
        name_facts_passes=3, name_facts_shown={'fact-a': 2},
        weekly_progress={'workouts': 4, 'minutes': 180},
        challenges=parse_challenges(demo_data()['challenges']),
        booked_classes=demo_bookings(FIXED_NOW), club=demo_club(FIXED_NOW))
    dashboard._persist_snapshot()
    return dashboard


def _expected():
    return EXPECTED.read_text(encoding='utf-8').rstrip('\n')


def test_cache_file_is_byte_for_byte_the_stored_copy(tmp_path):
    dashboard = populated_dashboard(tmp_path)
    written = dashboard.cache_path.read_text(encoding='utf-8')
    assert set(json.loads(written)['snapshot']) == set(PERSISTED_KEYS)
    assert written == _expected()


def test_stored_cache_loads_and_is_written_back_unchanged(tmp_path):
    """Old file in, new code out: a board restarting on this code reads the file and rewrites it identically."""
    cache = tmp_path / 'cache.json'
    cache.write_text(_expected(), encoding='utf-8')
    token = tmp_path / 'token'
    token.write_text('synthetic-token')
    assert load_snapshot(cache) is not None
    dashboard = Dashboard(token, {'cache_path': str(cache)})
    assert dashboard.snapshot()['status'] == 'cached'
    dashboard._persist_snapshot()
    assert cache.read_text(encoding='utf-8') == _expected()
