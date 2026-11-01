"""LogoScreen: the display.logo_path override for the startup logo."""
from pathlib import Path
from unittest.mock import Mock

from PIL import Image

from display.ui.logo_screen import LogoScreen

ROOT = Path(__file__).resolve().parents[1]


def _matrix(height):
    matrix = Mock(width=64, height=height)
    return matrix


def test_logo_is_fitted_and_centered_on_the_background(tmp_path):
    wide = tmp_path / 'wide.png'
    Image.new('RGB', (128, 32), (200, 0, 0)).save(wide)
    screen = LogoScreen(str(wide), bg_color=(0, 0, 50))
    matrix = _matrix(64)
    screen.on_enter(matrix)
    assert screen.render(matrix) is True
    image = matrix.SetImage.call_args.args[0]
    assert image.size == (64, 64)
    assert image.getpixel((32, 2)) == (0, 0, 50)      # letterbox
    assert image.getpixel((32, 32))[0] > 150           # logo


def test_bundled_logo_fills_a_32_row_board():
    screen = LogoScreen(str(ROOT / 'prepared_logos' / 'peloton_64x32_auto.png'))
    matrix = _matrix(32)
    screen.on_enter(matrix)
    assert screen.render(matrix) is True
    assert matrix.SetImage.call_args.args[0].size == (64, 32)


def test_missing_logo_draws_nothing(tmp_path, caplog):
    screen = LogoScreen(str(tmp_path / 'missing.png'))
    matrix = _matrix(64)
    screen.on_enter(matrix)
    assert screen.render(matrix) is False
    matrix.SetImage.assert_not_called()
    assert 'Could not open logo image' in caplog.text


def test_driver_failure_is_logged_not_raised(tmp_path, caplog):
    logo = tmp_path / 'logo.png'
    Image.new('RGB', (64, 64), (255, 255, 255)).save(logo)
    screen = LogoScreen(str(logo))
    matrix = _matrix(64)
    matrix.SetImage.side_effect = RuntimeError('driver gone')
    screen.on_enter(matrix)
    assert screen.render(matrix) is False
    assert 'Failed to render logo' in caplog.text
