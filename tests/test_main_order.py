"""peloton_led.main(): the startup order is load-bearing (the service starts as root and drops privileges right
after RGBMatrix(...)), so these pin it, plus the config overrides and the logo choice."""

import logging
import sys
from unittest.mock import patch

import pytest

import peloton_led
from peloton.dashboard import Dashboard
from scripts.render_demo import ImageMatrix
from tests.test_main import FakeMatrix, _config, _main


@pytest.fixture
def fake_matrix(monkeypatch):
    FakeMatrix.instances = []
    monkeypatch.setattr(sys.modules['driver'], 'RGBMatrix', FakeMatrix)
    monkeypatch.setattr(peloton_led, 'load_dotenv', lambda *a, **k: None)
    return FakeMatrix


def test_startup_order_drops_privileges_right_after_the_matrix_is_built(monkeypatch, tmp_path, fake_matrix):
    from display.ui.manager import ScreenManager

    events = []

    def record(name, real=None):
        def wrapper(*a, **k):
            events.append(name)
            return real(*a, **k) if real else None

        return wrapper

    def build_matrix(self, options=None):
        events.append('matrix')
        ImageMatrix.__init__(self, width=64, height=64)
        self.built = True

    def clear(self):
        if getattr(self, 'built', False):  # the constructor clears too; only main()'s calls matter here
            events.append('clear')

    real_load, real_profiles = peloton_led.load_config, peloton_led.configured_profiles
    monkeypatch.setattr(peloton_led, 'load_config', record('config', real_load))
    monkeypatch.setattr(peloton_led, 'ensure_privileges_dropped', record('drop'))
    monkeypatch.setattr(peloton_led, 'configured_profiles', record('profiles', real_profiles))
    monkeypatch.setattr(peloton_led, 'show_and_wait', record('show'))
    monkeypatch.setattr(peloton_led, 'run_multi_user_loop', record('loop'))
    monkeypatch.setattr(sys.modules['display.display'], 'initialize_fonts', record('fonts'))
    monkeypatch.setattr(FakeMatrix, '__init__', build_matrix)
    monkeypatch.setattr(FakeMatrix, 'Clear', clear)
    monkeypatch.setattr(Dashboard, 'start', record('start'))
    monkeypatch.setattr(Dashboard, 'stop', lambda self: events.append('stop') or True)
    registered = []
    real_register = ScreenManager.register

    def register(self, name, screen):
        registered.append(name)
        real_register(self, name, screen)

    monkeypatch.setattr(ScreenManager, 'register', register)
    _main(monkeypatch, '--demo', '--config', _config(tmp_path, {'show_logo': True, 'logo_duration': 3}))
    assert events == [
        'config',
        'matrix',
        'drop',
        'clear',
        'fonts',
        'profiles',
        'clear',
        'start',
        'show',
        'loop',
        'stop',
        'clear',
    ]  # the 3rd 'clear' is ScreenManager's
    assert registered == [
        'username',
        'discipline',
        'lifetime',
        'last_workout',
        'pr',
        'celebration',
        'status',
        'goal',
        'streak',
        'versus',
        'countdown',
        'journey',
        'heatmap',
        'streak_risk',
        'wifi_setup',
        'challenge',
        'next_class',
        'club',
        'logo',
    ]


def test_command_line_overrides_and_debug_flag_reach_the_display_config(monkeypatch, tmp_path, fake_matrix):
    with patch.object(peloton_led, 'run_multi_user_loop') as loop:
        _main(monkeypatch, '--demo', '--config', _config(tmp_path, debug=True), '--display-duration', '7', '--refresh-interval', '99')
    display = loop.call_args.args[2]
    assert display['duration'] == 7 and display['refresh_interval'] == 99
    assert logging.getLogger('peloton-led').level == logging.DEBUG
    with patch.object(peloton_led, 'run_multi_user_loop'):
        _main(monkeypatch, '--demo', '--config', _config(tmp_path))
    assert logging.getLogger('peloton-led').level == logging.INFO


def test_startup_logo_shows_for_its_duration_and_falls_back_to_the_pixel_mask(monkeypatch, tmp_path, fake_matrix):
    from display.ui.logo_mask_screen import LogoMaskScreen

    seen = []

    def show(manager, name, state, duration, dashboard=None, **kwargs):
        seen.append((name, state, duration, type(manager.screens.get('logo'))))

    monkeypatch.setattr(peloton_led, 'show_and_wait', show)
    config = _config(tmp_path, {'show_logo': True, 'logo_duration': 3, 'logo_path': str(tmp_path / 'missing.png')})
    with patch.object(peloton_led, 'run_multi_user_loop'):
        _main(monkeypatch, '--demo', '--config', config)
    assert seen == [('logo', None, 3, LogoMaskScreen)]


def test_display_loop_naps_between_rotations_when_every_page_has_no_time(monkeypatch):
    from types import SimpleNamespace

    naps = []
    monkeypatch.setattr(peloton_led.time, 'sleep', naps.append)
    monkeypatch.setattr(peloton_led, 'build_rotation_pages', lambda *a, **k: [('status', 'loading', 0)])
    monkeypatch.setattr(peloton_led, 'show_and_wait', lambda *a, **k: False)
    dashboard = SimpleNamespace(snapshot=lambda: {'me': {}})
    manager = SimpleNamespace(matrix=SimpleNamespace(height=64, brightness=1))
    peloton_led.run_display_loop(manager, dashboard, {}, 'Rider', cycles=2)
    assert naps == [0.05, 0.05]
