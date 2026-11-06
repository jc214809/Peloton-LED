import pytest


@pytest.fixture(autouse=True)
def no_history_batch_pause(monkeypatch):
    """History walks pause a second between batches on a board; not in tests."""
    monkeypatch.setattr('peloton.dashboard.HISTORY_BATCH_PAUSE_SECONDS', 0)


@pytest.fixture(autouse=True)
def heartbeat_in_tmp(tmp_path, monkeypatch):
    """The display beats after each screen (utils/heartbeat.py): never into a real board's /run."""
    import utils.heartbeat as heartbeat
    monkeypatch.setattr(heartbeat, 'HEARTBEAT_FILE', str(tmp_path / 'peloton-led' / 'health'))
    heartbeat._last_problem = None
