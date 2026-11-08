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


@pytest.fixture
def instant_clock(monkeypatch):
    """peloton_led's clock, where sleeping only moves the time on: a rotation plays at once. Screen
    times are never 0 (peloton.screen_times), so loop tests use this rather than 0-second pages."""
    import time as real_time

    import peloton_led

    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += max(0, seconds)

        def __getattr__(self, name):
            return getattr(real_time, name)

    clock = Clock()
    monkeypatch.setattr(peloton_led, 'time', clock)
    return clock
