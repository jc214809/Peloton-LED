"""The settings page's smaller states: each save outcome, each PIN-page status, the rider pill, the zone."""

from types import SimpleNamespace

import pytest

from settings_page.page.logins_section import _rider_pill
from settings_page.page.shell import notices, pin_page
from settings_page.page.widgets import _zone


@pytest.mark.parametrize(
    'saved, kind, text',
    [
        ('restarted', 'good', 'The display is restarting with the new settings.'),
        ('not_running', 'good', "The display isn't running; it uses these settings the next time it starts."),
        ('saved', 'good', 'Restart the display for the new settings.'),
        ('failed', 'bad', "Saved, but the display didn't restart."),
    ],
)
def test_notices_say_how_the_save_went(saved, kind, text):
    html = notices(saved=saved)
    assert f'class="notice {kind}"' in html
    assert text in html


def test_notices_list_the_problems_and_nothing_else_when_not_saved():
    html = notices(problems=['display.timezone is not a zone', 'a <b> tag'])
    assert '<strong>Not saved.</strong>' in html
    assert '<li>display.timezone is not a zone</li>' in html
    assert '<li>a &lt;b&gt; tag</li>' in html
    assert notices() == ''


@pytest.mark.parametrize(
    'kwargs, kind, text',
    [
        ({'signed_out': True}, 'good', 'Signed out.'),
        ({'wrong': True}, 'bad', "That isn't the PIN on the board."),
        ({'sent': 'sent'}, 'good', 'The PIN is on its way to your phone.'),
        ({'sent': 'wait'}, 'warn', 'A PIN went out less than a minute ago'),
        ({'sent': 'used'}, 'bad', 'That PIN is out of tries.'),
        ({'sent': 'failed'}, 'bad', "Couldn't send the PIN"),
        ({'shown_s': 60}, 'good', 'for the next 1 minute.'),
        ({'shown_s': 300}, 'good', 'for the next 5 minutes.'),
    ],
)
def test_pin_page_status(kwargs, kind, text):
    html = pin_page(**kwargs)
    assert f'class="notice {kind}"' in html
    assert text in html


def test_pin_page_signed_out_wins_over_a_wrong_pin():
    html = pin_page(signed_out=True, wrong=True)
    assert 'Signed out.' in html
    assert "That isn't the PIN" not in html


@pytest.mark.parametrize(
    'token, padlock, kind, text',
    [
        ({'ok': False}, False, 'bad', 'No working token'),
        ({'ok': True, 'expired': True}, False, 'bad', 'Expired'),
        ({'ok': True}, True, 'warn', 'Needs login'),
        ({'ok': True}, False, 'ok', 'Working'),
    ],
)
def test_rider_pill(token, padlock, kind, text):
    assert _rider_pill(SimpleNamespace(token=token, padlock=padlock)) == f'<span class="pill {kind}">{text}</span>'


@pytest.mark.parametrize(
    'display',
    [
        {'timezone': 'Not/A_Zone'},
        {'timezone': '../etc'},
        {'timezone': 5},
        {},
    ],
)
def test_zone_falls_back_to_the_servers_own(display):
    assert _zone(display) is None


def test_zone_reads_the_boards_zone():
    assert _zone({'timezone': 'America/New_York'}).key == 'America/New_York'
