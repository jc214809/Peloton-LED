import json
from types import SimpleNamespace

from api.get_last_active_days_workouts import GetLastActiveDaysWorkouts


def load_fixture(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class FakeClient:
    def __init__(self, recent_workouts):
        self._recent = recent_workouts

    def get_recent_workouts(self, user_id, limit=50, days=30):
        # ignore params for testing convenience
        return self._recent


def test_get_last_active_days_workouts_returns_latest_date_entries(tmp_path):
    fixtures = load_fixture("tests/fixtures/recent_workouts.json")
    client = FakeClient(fixtures)

    getter = GetLastActiveDaysWorkouts()
    result = getter(client, "user-123")

    # The fixture contains three entries on 2026-03-14 (ids 1,2,4) and one on 2026-03-13 (id 3)
    assert isinstance(result, list)
    ids = {w.get("id") for w in result}
    assert ids == {"1", "2", "4"}


def test_get_last_active_days_workouts_handles_empty_list():
    client = FakeClient([])
    getter = GetLastActiveDaysWorkouts()
    result = getter(client, "user-123")
    assert result == []
