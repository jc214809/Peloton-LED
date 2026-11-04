"""comitup's Wi-Fi setup hotspot: reading its state, the setup screen, and holding it while it's up."""
import pytest

import utils.wifi_setup as wifi_setup
from utils.wifi_setup import hotspot_name


@pytest.mark.parametrize('content,expected', [
    ('HOTSPOT PelotonPi-setup\n', 'PelotonPi-setup'),
    ('CONNECTED PelotonPi-setup\n', None),
    ('CONNECTING PelotonPi-setup\n', None),
    ('HOTSPOT\n', None),
    ('', None),
])
def test_hotspot_name_only_while_the_hotspot_is_up(tmp_path, content, expected):
    path = tmp_path / 'comitup-state'
    path.write_text(content)
    assert hotspot_name(str(path)) == expected


def test_no_comitup_is_never_in_setup(tmp_path):
    assert hotspot_name(str(tmp_path / 'missing')) is None


def test_an_unreadable_state_is_logged_once(tmp_path, caplog, monkeypatch):
    monkeypatch.setattr(wifi_setup, '_last_problem', None)
    for _ in range(3):
        assert hotspot_name(str(tmp_path)) is None  # a folder
    assert caplog.text.count("Can't read") == 1
    good = tmp_path / 'state'
    good.write_text('HOTSPOT x\n')
    hotspot_name(str(good))
    assert wifi_setup._last_problem is None


class Matrix:
    def __init__(self, height):
        self.width, self.height, self.pixels = 64, height, {}

    def SetPixel(self, x, y, r, g, b):
        self.pixels[(x, y)] = (r, g, b)


@pytest.fixture(params=[32, 64])
def fonts(request):
    from display.display import initialize_fonts
    initialize_fonts(request.param)
    return request.param


def drawn_text(monkeypatch, height, state):
    """The lines the screen draws, and the rows they sit on."""
    import display.ui.wifi_setup_screen as screen
    lines = []
    monkeypatch.setattr(screen, 'draw_centered_text',
                        lambda matrix, font, text, y, color: lines.append((text, y, font.height)))
    assert screen.WifiSetupScreen().render(Matrix(height), state) is True
    return lines


@pytest.mark.parametrize('name', ['PelotonPi-setup', 'peloton-basement-board-setup',
                                  'abcdefghijklmnopqrstuvwxyz-setup'])
def test_the_setup_screen_fits_the_hotspot_name_on_both_boards(monkeypatch, fonts, name):
    lines = drawn_text(monkeypatch, fonts, {'name': name, 'page': 0})
    assert lines[0][0] == 'Wi-Fi setup'
    assert ''.join(text for text, _, _ in lines if text not in ('Wi-Fi setup', 'Join')) == name
    assert all(y - height + 1 >= 0 and y < fonts + 2 for _, y, height in lines)  # on the panel
    if fonts == 64:
        assert lines[1][0] == 'Join'


def test_the_second_page_says_where_the_settings_page_is(monkeypatch, fonts):
    lines = [text for text, _, _ in drawn_text(monkeypatch, fonts, {'page': 1})]
    assert lines == ['Settings', 'Browse to', '10.41.0.1:8080']


def test_the_settings_address_matches_the_servers_port():
    from display.ui.wifi_setup_screen import SETTINGS_ADDRESS
    from settings_page.server import PORT
    assert SETTINGS_ADDRESS == f'{wifi_setup.HOTSPOT_ADDRESS}:{PORT}'


def test_name_lines_split_a_piece_too_wide_by_letters(fonts):
    from display.display import get_text_width, loaded_fonts
    from display.ui.wifi_setup_screen import name_lines
    font = loaded_fonts['info']
    lines = name_lines(font, 'x' * 40, 62)
    assert ''.join(lines) == 'x' * 40 and all(get_text_width(font, line) <= 62 for line in lines)
    assert name_lines(font, 'a-b', 62) == ['a-b']


def test_the_display_holds_the_setup_screen_until_the_hotspot_goes(monkeypatch):
    import peloton_led
    names = iter(['Pi-setup', 'Pi-setup', 'Pi-setup', None])
    monkeypatch.setattr(peloton_led, 'hotspot_name', lambda: next(names))
    shown = []
    monkeypatch.setattr(peloton_led, 'show_and_wait',
                        lambda manager, name, state, duration, dashboard=None: shown.append((name, state, duration)))
    assert peloton_led.show_wifi_setup_while_needed(object()) is True
    assert shown == [('wifi_setup', {'name': 'Pi-setup', 'page': 0}, 5),
                     ('wifi_setup', {'name': 'Pi-setup', 'page': 1}, 5),
                     ('wifi_setup', {'name': 'Pi-setup', 'page': 0}, 5)]


def test_no_hotspot_shows_nothing(monkeypatch):
    import peloton_led
    monkeypatch.setattr(peloton_led, 'hotspot_name', lambda: None)
    monkeypatch.setattr(peloton_led, 'show_and_wait', lambda *a, **k: pytest.fail('shown'))
    assert peloton_led.show_wifi_setup_while_needed(object()) is False


def test_each_rotation_cycle_checks_for_the_hotspot_first(monkeypatch):
    import peloton_led
    order = []
    monkeypatch.setattr(peloton_led, 'show_wifi_setup_while_needed', lambda manager: order.append('wifi'))
    monkeypatch.setattr(peloton_led, 'weekly_rivals', lambda profiles: [])
    monkeypatch.setattr(peloton_led, 'run_display_loop', lambda *a, **k: order.append('rotation'))
    peloton_led.run_multi_user_loop(object(), [{'dashboard': object()}], {}, {}, cycles=2)
    assert order == ['wifi', 'rotation', 'wifi', 'rotation']
