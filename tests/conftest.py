import pytest


@pytest.fixture(scope='session', autouse=True)
def parse_each_font_once():
    """bdfparser reads a BDF in pure Python (~0.5 s a font) and every render re-runs initialize_fonts, which
    was most of the suite's run time. Parsed fonts are read-only, so share one per path."""
    from RGBMatrixEmulator.graphics import font as emulator_font
    parsed = {}
    real_load = emulator_font.Font.LoadFont

    def load_font(self, path):
        if path not in parsed:
            real_load(self, path)
            parsed[path] = (self.bdf_font, self.headers, self.props, self.default_character)
        self.bdf_font, self.headers, self.props, self.default_character = parsed[path]

    emulator_font.Font.LoadFont = load_font
    yield
    emulator_font.Font.LoadFont = real_load


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
