"""The settings page's PIN: the gate's rules, and how the panel shows it."""
import os

import pytest

import display.ui.settings_pin as settings_pin
from settings_page import pins
from settings_page.pins import MAX_SESSIONS, PIN_SHOWN_S, SEND_EVERY_S, SESSION_S, TRIES_PER_PIN, PinGate


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def gate(tmp_path):
    return PinGate(str(tmp_path / 'pin'), clock=Clock())


def pin_on_board(gate):
    pin, expires = open(gate.pin_file).read().split()
    return pin, float(expires)


def test_showing_a_pin_writes_it_for_the_display_to_read(gate):
    assert gate.show_pin() == PIN_SHOWN_S
    pin, expires = pin_on_board(gate)
    assert len(pin) == 4 and pin.isdigit() and expires == gate.clock() + PIN_SHOWN_S
    assert oct(os.stat(gate.pin_file).st_mode & 0o777) == '0o640'
    gate.clock.now += 30
    assert gate.show_pin() == PIN_SHOWN_S - 30 and pin_on_board(gate)[0] == pin  # the same one, until it runs out
    gate.clock.now += PIN_SHOWN_S
    gate.show_pin()
    assert pin_on_board(gate)[1] == gate.clock() + PIN_SHOWN_S


def test_the_right_pin_gives_a_session_once(gate):
    gate.show_pin()
    pin, _ = pin_on_board(gate)
    token = gate.try_pin(f' {pin} ')
    assert token and gate.signed_in(token) and not os.path.exists(gate.pin_file)
    assert gate.try_pin(pin) is None  # used
    gate.clock.now += SESSION_S
    assert not gate.signed_in(token)
    assert not gate.signed_in(None) and not gate.signed_in('made-up')


def test_wrong_guesses_use_the_pin_up_until_it_runs_out(gate):
    gate.show_pin()
    pin, _ = pin_on_board(gate)
    wrong = '0000' if pin != '0000' else '1111'
    for _ in range(TRIES_PER_PIN):
        assert gate.try_pin(wrong) is None
    assert not os.path.exists(gate.pin_file)
    assert gate.try_pin(pin) is None
    gate.show_pin()  # no new one until this one's time is up
    assert not os.path.exists(gate.pin_file)
    gate.clock.now += PIN_SHOWN_S
    gate.show_pin()
    assert os.path.exists(gate.pin_file)


def test_no_pin_up_signs_no_one_in(gate):
    assert gate.try_pin('1234') is None
    gate.show_pin()
    pin, _ = pin_on_board(gate)
    gate.clock.now += PIN_SHOWN_S
    assert gate.try_pin(pin) is None


def test_sessions_are_capped_oldest_first_and_sign_out_ends_one(gate):
    tokens = []
    for _ in range(MAX_SESSIONS + 1):
        gate.show_pin()
        tokens.append(gate.try_pin(pin_on_board(gate)[0]))
        gate.clock.now += 1
    assert not gate.signed_in(tokens[0]) and all(gate.signed_in(t) for t in tokens[1:])
    gate.sign_out(tokens[1])
    gate.sign_out('not-a-session')
    assert not gate.signed_in(tokens[1])


def test_sending_is_rate_limited_and_never_while_used_up(gate):
    sent = []
    assert gate.send_pin(lambda pin, left: sent.append((pin, left)) or True) == 'sent'
    assert sent == [(pin_on_board(gate)[0], PIN_SHOWN_S)]
    assert gate.send_pin(lambda pin, left: True) == 'wait'
    gate.clock.now += SEND_EVERY_S
    assert gate.send_pin(lambda pin, left: False) == 'failed'
    gate.clock.now += SEND_EVERY_S

    def boom(pin, left):
        raise RuntimeError('network down')
    assert gate.send_pin(boom) == 'failed'
    for _ in range(TRIES_PER_PIN):
        gate.try_pin('wrong')
    gate.clock.now += SEND_EVERY_S
    assert gate.send_pin(lambda pin, left: True) == 'used'


def test_pin_file_problems_are_logged_not_raised(tmp_path, caplog):
    gate = PinGate(str(tmp_path / 'missing-folder' / 'pin'))
    assert gate.show_pin() > 0
    assert "can't put the PIN on the board" in caplog.text
    folder = tmp_path / 'a-folder'
    folder.mkdir()
    (folder / 'x').write_text('')
    gate = PinGate(str(folder))
    gate._remove()  # a non-empty folder can't be removed
    assert "can't take the PIN off the board" in caplog.text


def test_pin_file_location_can_be_set_for_development(monkeypatch):
    import importlib
    monkeypatch.setenv('PELOTON_SETTINGS_PIN_FILE', '/tmp/dev-pin')
    try:
        assert importlib.reload(pins).PIN_FILE == '/tmp/dev-pin'
    finally:
        monkeypatch.delenv('PELOTON_SETTINGS_PIN_FILE')
        importlib.reload(pins)
    assert pins.PIN_FILE == '/run/peloton-led-settings/pin'


# --- On the panel

@pytest.fixture
def fresh_cache(monkeypatch):
    monkeypatch.setattr(settings_pin, '_cache', {'at': None, 'pin': None, 'expires': 0.0})
    monkeypatch.setattr(settings_pin, '_last_problem', None)


def test_the_display_shows_a_pin_until_it_runs_out_and_rereads_at_most_each_second(tmp_path, fresh_cache):
    path = tmp_path / 'pin'
    path.write_text('4827 2000\n')
    tick = [0.0]
    assert settings_pin.shown_pin(str(path), clock=lambda: 1000, monotonic=lambda: tick[0]) == '4827'
    path.unlink()
    tick[0] = 0.5
    assert settings_pin.shown_pin(str(path), clock=lambda: 1000, monotonic=lambda: tick[0]) == '4827'  # cached
    assert settings_pin.shown_pin(str(path), clock=lambda: 2000, monotonic=lambda: tick[0]) is None  # expired
    tick[0] = 1.5
    assert settings_pin.shown_pin(str(path), clock=lambda: 1000, monotonic=lambda: tick[0]) is None  # gone


@pytest.mark.parametrize('content', ['garbage', '12ab 2000', '1234 soon'])
def test_a_bad_pin_file_shows_nothing_and_is_logged_once(tmp_path, fresh_cache, caplog, content):
    path = tmp_path / 'pin'
    path.write_text(content)
    for tick in (0, 2):
        assert settings_pin.shown_pin(str(path), clock=lambda: 1000, monotonic=lambda: tick) is None
    if content != '12ab 2000':
        assert caplog.text.count("Can't read the settings PIN") == 1


class Canvas:
    def __init__(self, width=64, height=32):
        self.width, self.height, self.pixels = width, height, {}

    def SetPixel(self, x, y, r, g, b):
        self.pixels[(x, y)] = (r, g, b)


@pytest.mark.parametrize('height', [32, 64])
def test_the_pin_is_a_centred_box_on_both_boards(height):
    canvas = Canvas(64, height)
    settings_pin.draw_pin(canvas, '4827')
    xs = [x for x, _ in canvas.pixels]
    ys = [y for _, y in canvas.pixels]
    assert (min(xs), max(xs)) == (14, 49) and max(ys) - min(ys) == 15
    assert min(ys) == (height - 16) // 2
    assert canvas.pixels[(14, min(ys))] == settings_pin.GOLD
    assert settings_pin.WHITE in canvas.pixels.values()
    empty = Canvas()
    settings_pin.draw_pin(empty, 'abc')
    assert empty.pixels == {}


def test_the_manager_draws_the_pin_over_any_screen(monkeypatch):
    from display.ui.manager import ScreenManager
    from display.ui.screen import Screen

    class Blank(Screen):
        def render(self, matrix, state=None):
            return True

    class Matrix(Canvas):
        def Clear(self):
            self.pixels = {}

    monkeypatch.setattr('display.ui.settings_pin.shown_pin', lambda: '1234')
    matrix = Matrix()
    manager = ScreenManager(matrix)
    manager.register('blank', Blank())
    manager.show('blank')
    manager.tick({})
    assert settings_pin.GOLD in matrix.pixels.values()


def test_show_and_wait_repaints_when_a_pin_appears(monkeypatch):
    import peloton_led
    pins_seen = iter([None] + ['5555'] * 100)
    monkeypatch.setattr(peloton_led, 'shown_pin', lambda: next(pins_seen))

    class Manager:
        def __init__(self):
            self.ticks, self.clears = 0, 0
            self.matrix = self
            self.current = None

        def show(self, name, state):
            pass

        def tick(self, state):
            self.ticks += 1

        def Clear(self):
            self.clears += 1

    manager = Manager()
    peloton_led.show_and_wait(manager, 'username', {}, 0.3)
    assert manager.clears == 1 and manager.ticks == 2
