import pytest


@pytest.fixture(autouse=True)
def no_history_batch_pause(monkeypatch):
    """History walks pause a second between batches on a board; not in tests."""
    monkeypatch.setattr('peloton.dashboard.HISTORY_BATCH_PAUSE_SECONDS', 0)
