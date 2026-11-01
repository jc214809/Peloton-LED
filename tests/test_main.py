"""peloton_led.main(): startup, shutdown and failure paths, on an in-memory matrix."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import peloton_led
from peloton.dashboard import Dashboard
from scripts.render_demo import ImageMatrix

ROOT = Path(__file__).resolve().parents[1]
FAST = {'duration': 0, 'overview_duration': 0, 'last_workout_duration': 0,
        'per_workout_duration': 0, 'logo_duration': 0}


class FakeMatrix(ImageMatrix):
    """Stands in for RGBMatrix so no emulator server starts."""
    instances = []

    def __init__(self, options=None):
        super().__init__(width=64, height=options.rows if options else 64)
        self.cleared = 0
        FakeMatrix.instances.append(self)

    def Clear(self):
        self.cleared = getattr(self, 'cleared', 0) + 1
        super().Clear()


@pytest.fixture
def fake_matrix(monkeypatch):
    FakeMatrix.instances = []
    monkeypatch.setattr(sys.modules['driver'], 'RGBMatrix', FakeMatrix)
    monkeypatch.setattr(peloton_led, 'load_dotenv', lambda *a, **k: None)
    return FakeMatrix


def _config(tmp_path, display=None, **extra):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'display': {**FAST, **(display or {})}, **extra}))
    return path


def _main(monkeypatch, *argv):
    monkeypatch.setattr(sys, 'argv', ['peloton_led.py', '--emulated', *map(str, argv)])
    peloton_led.main()


@pytest.mark.parametrize('rows', [32, 64])
def test_demo_runs_one_rotation_and_cleans_up(monkeypatch, tmp_path, fake_matrix, rows):
    config = _config(tmp_path, {'logo_duration': 0.01})
    _main(monkeypatch, '--demo', '--cycles', '1', '--config', config, '--led-rows', rows,
          '--display-duration', '0', '--refresh-interval', '60')
    matrix = fake_matrix.instances[-1]
    assert matrix.height == rows
    assert matrix.cleared >= 2  # at startup and at shutdown


def test_invalid_config_exits_with_its_message(monkeypatch, tmp_path, fake_matrix):
    bad = tmp_path / 'config.json'
    bad.write_text('{broken')
    with pytest.raises(SystemExit):
        _main(monkeypatch, '--config', bad)
    assert fake_matrix.instances == []


def test_matrix_that_cannot_clear_is_a_startup_error(monkeypatch, tmp_path, fake_matrix):
    def broken(self):
        if hasattr(self, 'image'):  # after construction, like a driver that loses the GPIO
            raise RuntimeError('no GPIO access')
        ImageMatrix.Clear(self)
    monkeypatch.setattr(FakeMatrix, 'Clear', broken)
    with pytest.raises(SystemExit, match='Could not initialize the matrix: no GPIO access'):
        _main(monkeypatch, '--demo', '--cycles', '1', '--config', _config(tmp_path))


def test_configured_logo_image_is_used(monkeypatch, tmp_path, fake_matrix):
    logo = ROOT / 'prepared_logos' / 'peloton_64x64_auto.png'
    assert logo.exists()
    with patch('display.ui.logo_screen.LogoScreen.__init__', return_value=None) as screen, \
         patch.object(peloton_led, 'run_multi_user_loop'):
        _main(monkeypatch, '--demo', '--config', _config(tmp_path, {'logo_path': str(logo)}))
    assert screen.call_args.args == (str(logo),)


def test_ctrl_c_stops_every_dashboard(monkeypatch, tmp_path, fake_matrix, caplog):
    with patch.object(peloton_led, 'run_multi_user_loop', side_effect=KeyboardInterrupt), \
         patch.object(Dashboard, 'stop', return_value=False) as stop, \
         caplog.at_level('INFO', logger='peloton-led'):
        _main(monkeypatch, '--demo', '--config', _config(tmp_path))
    stop.assert_called()
    assert 'Stopping Peloton display' in caplog.text
    assert 'did not stop before its request timeout' in caplog.text


def test_finite_real_run_waits_for_the_first_refresh(monkeypatch, tmp_path, fake_matrix):
    # No token file: the first refresh finishes at once with login_needed.
    config = _config(tmp_path, users=[{'name': 'Joel'}, {'name': 'Jen'}])
    with patch.object(peloton_led, 'run_multi_user_loop') as loop:
        _main(monkeypatch, '--cycles', '1', '--config', config)
    profiles = loop.call_args.args[1]
    assert [p['name'] for p in profiles] == ['Joel', 'Jen']
    assert all(p['dashboard'].snapshot()['status'] != 'loading' for p in profiles)


def test_configured_profiles_apply_per_rider_settings(tmp_path):
    from types import SimpleNamespace
    options = SimpleNamespace(config=str(tmp_path / 'config.json'), demo=True,
                              demo_login_needed=False, cookies='cookies.txt', username=None)
    display = {'refresh_interval': 300}
    users = [
        {'name': 'Joel', 'username': 'JC', 'weekly_goals': {'workouts': 4}, 'milestones': [500],
         'journey': {'miles': 1000}, 'cache_path': 'caches/joel.json'},
        {'name': 'Jen', 'token_path': '/var/lib/peloton-led/jen.txt', 'cache_path': '/tmp/jen.json'},
        {'name': 'Kid'},
    ]
    joel, jen, kid = peloton_led.configured_profiles({'display': display, 'users': users}, options)
    assert joel['username'] == 'JC'
    assert joel['dashboard'].config['weekly_goals'] == {'workouts': 4}
    assert joel['dashboard'].config['milestones'] == [500]
    assert joel['dashboard'].config['journey'] == {'miles': 1000}
    assert joel['dashboard'].cache_path == tmp_path / 'caches' / 'joel.json'
    assert joel['dashboard'].token_path == tmp_path / 'cookies-joel.txt'
    assert jen['dashboard'].token_path == Path('/var/lib/peloton-led/jen.txt')
    assert jen['dashboard'].cache_path == Path('/tmp/jen.json')
    assert kid['dashboard'].cache_path == tmp_path / 'cookies-kid-dashboard-cache.json'
    assert 'weekly_goals' not in display  # the shared display config is untouched
