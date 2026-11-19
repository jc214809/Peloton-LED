"""Pins the settings page's HTML, byte for byte, so the page can be split into modules without changing it.

Each case renders a public page function and compares it with a stored copy in
tests/fixtures/settings_page_html/. To rewrite the copies after a change to the page that is meant:
UPDATE_HTML_FIXTURES=1 python -m pytest tests/test_settings_page_html.py

Three things are kept out of the per-case copies so they stay small and the same on every machine: the
stylesheet and the script (compared once, as style.css and script.js), and the time zone list (the machine's
tzdata decides it). A state case (notices, cards) stores only the top of the page, before the settings
form; the settings form is pinned by the config cases, and the Workout insights card by its own cases.
"""
import copy
import json
import os
import re
import time
from pathlib import Path

import pytest

from settings_page import page
from settings_page.logins import RiderLogin

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'settings_page_html'
WRITE = bool(os.environ.get('UPDATE_HTML_FIXTURES'))
NOW = 1_700_000_000  # Tue Nov 14 2023, 22:13 UTC

STYLE_BLOCK = re.compile(r'<style>(.*?)</style>', re.S)
SCRIPT_BLOCK = re.compile(r'<script>(.*?)</script>', re.S)
ZONES_BLOCK = re.compile(r'<datalist id="zones">.*?</datalist>', re.S)


@pytest.fixture(autouse=True)
def utc(monkeypatch):
    """Times on the page come out in the board's zone, or the machine's when the config has none."""
    monkeypatch.setenv('TZ', 'UTC')
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def normalised(html):
    """html with the stylesheet, the script and the zone list swapped for markers."""
    html = STYLE_BLOCK.sub('<style>[STYLE]</style>', html)
    html = SCRIPT_BLOCK.sub('<script>[SCRIPT]</script>', html)
    return ZONES_BLOCK.sub('<datalist id="zones">[ZONES]</datalist>', html)


def compare(name, text):
    path = FIXTURES / name
    if WRITE:
        path.write_text(text, encoding='utf-8')
    assert path.exists(), f'{name} has no stored copy: UPDATE_HTML_FIXTURES=1 writes it'
    assert text == path.read_text(encoding='utf-8'), f'{name} changed'


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


FULL = {
    'debug': True,
    'matrix': {'rows': 32, 'cols': 64, 'chain': 2, 'parallel': 1, 'pwm_bits': 9, 'brightness': 70,
               'gpio_mapping': 'adafruit-hat-pwm', 'scan_mode': 0, 'pwm_lsb_nanoseconds': 200, 'show_refresh': True,
               'slowdown_gpio': 2, 'no_hardware_pulse': False, 'rgb_sequence': 'RBG', 'pixel_mapper': 'Mirror:H',
               'row_addr_type': 2, 'multiplexing': 3, 'limit_refresh': 120, 'pwm_dither_bits': 1},
    'users': [
        {'name': 'Joel', 'email_env': 'PELOTON_EMAIL_RIDER_ONE', 'password_env': 'PELOTON_PASSWORD_RIDER_ONE',
         'weekly_goals': {'workouts': 5, 'minutes': 120, 'active_days': 4}, 'milestones': [100, 250, 500],
         'journey': {'from': 'A', 'to': 'B', 'miles': 10}},
        {'name': 'Jen "J" <Smith>', 'token_path': 'cookies-jen.txt', 'weekly_goals': {'workouts': 3}},
    ],
    'display': {
        'username': 'Fallback & Name', 'font': 'stats', 'color': 'down', 'duration': 6, 'overview_duration': 7,
        'last_workout_detail_interval': 3, 'workout_insights': True, 'logo_duration': 8, 'show_logo': False,
        'timezone': 'America/New_York', 'refresh_interval': 240, 'history_batch_size': 50,
        'rotation': ['username', 'latest_workouts', 'versus', 'lifetime', 'journey', 'goals', 'challenges',
                     'next_class', 'club', 'milestones', 'next_milestone'],
        'screen_durations': {'username': 9, 'lifetime': 5.5, 'milestones': 2, 'goals': 0.5, 'club': 1},
        'weekly_goals': {'workouts': 4, 'minutes': 90, 'active_days': 5}, 'milestones': [1000, 2000],
        'milestone_step': 50, 'milestone_within': 8, 'milestone_pages': 2, 'streak_reminder_day': 4,
        'next_class_takeover_minutes': 10,
        'brightness_schedule': {'day': 90, 'night': 10, 'day_start': '06:30', 'night_start': '21:15'},
        'refresh_schedule': {'quiet_start': '22:00', 'quiet_end': '06:00', 'quiet_interval': 1800},
    },
    'future_key': {'kept': True},
}

CONFIGS = {
    'example': lambda: load('config.json-example'),
    'dual-users': lambda: load('config.dual-users-example.json'),
    'pi': lambda: load('packaging/config.pi.json'),
    'full': lambda: copy.deepcopy(FULL),
    'empty': lambda: {},
    'broken-sections': lambda: {'display': 'nope', 'matrix': [1], 'users': 'x'},
}


@pytest.mark.parametrize('name', CONFIGS)
def test_the_form_for_each_config(name):
    compare(f'config-{name}.html', normalised(page.settings_page(CONFIGS[name]())))


def test_the_stylesheet_and_script_are_unchanged():
    html = page.settings_page({})
    compare('style.css', STYLE_BLOCK.search(html).group(1))
    compare('script.js', SCRIPT_BLOCK.search(html).group(1))
    assert STYLE_BLOCK.search(page.pin_page()).group(1) == STYLE_BLOCK.search(html).group(1)


def test_the_time_zone_list_is_sorted_zone_names():
    options = re.findall(r'<option value="([^"]+)">', ZONES_BLOCK.search(page.settings_page({})).group(0))
    assert options == sorted(options) and 'America/New_York' in options


# --- state cases: the top of the page (everything before the settings form)

def top_of(html):
    return normalised(html[html.index('<header'):html.index('<form method="post" action="/save"')])


def rider(key='default', name='Joel', token=None, chain='refresh token, 29 days left', **changes):
    """A RiderLogin; changes: padlock, browser_attempt, email_set, password_set."""
    token = {'ok': True, 'expires_at': NOW + 5 * 86400, 'expired': False} if token is None else token
    fields = {'padlock': None, 'browser_attempt': None, 'email_set': True, 'password_set': True, **changes}
    return RiderLogin(key=key, name=name, token_path=Path(f'/etc/peloton-led/cookies-{key}.txt'),
                      email_env='PELOTON_EMAIL', password_env='PELOTON_PASSWORD', token=token, chain=chain,
                      **fields)


VALID = {'ok': True, 'expires_at': NOW + 5 * 86400, 'expired': False}
EXPIRING = {'ok': True, 'expires_at': NOW + 3 * 3600, 'expired': False}
EXPIRED = {'ok': True, 'expires_at': NOW - 86400, 'expired': True}
MISSING_FILE = {'ok': False, 'reason': 'file does not exist'}
BROKEN = {'ok': False, 'reason': 'not valid JSON'}


def logins_view(**changes):
    view = {'riders': [rider('0', 'Joel', VALID), rider('1', 'Jen', EXPIRING, chain=None, email_set=False,
                                                        password_set=False)],
            'mode': 'browser', 'renewing': False, 'last_result': 'success', 'last_run': NOW - 1800,
            'timer_next': NOW + 1800, 'display_running': True, 'alerts': {}, 'pushover': True,
            'seed': 'scripts/seed_board.sh pi@PelotonPi.local'}
    return {**view, **changes}


LOGINS = {
    'healthy': logins_view(),
    'tokens-missing-expired': logins_view(riders=[rider('0', 'Joel', MISSING_FILE, chain=None),
                                                  rider('1', 'Jen', EXPIRED), rider('2', 'Sam', BROKEN)]),
    'padlock-browser-try': logins_view(riders=[rider('default', 'Joel', VALID, padlock={'reason': 'bad password',
                                                                                         'at': NOW - 60},
                                                     browser_attempt=NOW - 7200)]),
    'no-browser-mode': logins_view(mode='no-browser', riders=[rider('0', 'Joel', EXPIRED, chain=None)]),
    'timer-off-mode-none': logins_view(mode='none', timer_next=None),
    'manual-board-display-off': logins_view(timer_next=None, display_running=False),
    'timer-not-running': logins_view(timer_next=None),
    'renewing': logins_view(renewing=True, last_result=None),
    'never-run': logins_view(last_run=None, last_result=None),
    'last-run-failed': logins_view(last_result='exit-code', alerts={'failures': 3, 'last_message': 'Auth0 said no'}),
    'failures-no-message': logins_view(last_result=None, alerts={'failures': 1}),
    'systemd-text-times': logins_view(last_run='Tue 2023-11-14 22:00', timer_next='Tue 2023-11-14 23:00'),
    'odd-mode': logins_view(mode='weird'),
    'no-pushover': logins_view(pushover=False),
    'no-riders': logins_view(riders=[]),
}


@pytest.mark.parametrize('name', LOGINS)
def test_the_logins_and_alerts_cards(name):
    config = {'display': {'timezone': 'America/New_York'}}
    compare(f'logins-{name}.html', top_of(page.settings_page(config, logins=LOGINS[name])))


LOGIN_CASES = {
    'signed-out': dict(signed_in=False),
    'saved': dict(login_outcome='logins_saved'),
    'unchanged': dict(login_outcome='logins_unchanged'),
    'renew-started': dict(login_outcome='renew_started'),
    'renew-running': dict(login_outcome='renew_running'),
    'renew-failed': dict(login_outcome='renew_failed'),
    'renew-unavailable': dict(login_outcome='renew_unavailable'),
    'unknown-outcome': dict(login_outcome='nope'),
    'problems-for-a-rider': dict(login_problems=['Email: not an email', 'Password: too <long>'], editing_rider='1'),
    'problems-for-nobody': dict(login_problems=['Something changed'], editing_rider='9'),
    'editing-without-problems': dict(editing_rider='0'),
    'alerts-saved': dict(alert_outcome='alerts_saved'),
    'alerts-unchanged': dict(alert_outcome='alerts_unchanged'),
    'alerts-removed': dict(alert_outcome='alerts_removed'),
    'test-sent': dict(alert_outcome='test_sent'),
    'test-wait': dict(alert_outcome='test_wait'),
    'test-failed': dict(alert_outcome='test_failed'),
    'test-off': dict(alert_outcome='test_off'),
    'alert-problems': dict(alert_problems=['Both keys are needed']),
    'alert-problems-signed-out': dict(alert_problems=['Both keys are needed'], signed_in=False),
}


@pytest.mark.parametrize('name', LOGIN_CASES)
def test_the_logins_and_alerts_outcomes(name):
    html = page.settings_page({'display': {'timezone': 'UTC'}}, logins=LOGINS['healthy'], **LOGIN_CASES[name])
    compare(f'login-outcome-{name}.html', top_of(html))


PAGE_CASES = {
    'plain': dict(),
    'board-name': dict(board='PelotonPi'),
    'hotspot': dict(hotspot='Peloton-LED <setup>', board='PelotonPi'),
    'note': dict(note='config.json is not valid JSON: line 3'),
    'problems': dict(problems=['display.duration must be a number', 'Rotation needs a <screen>']),
    'saved-restarted': dict(saved='restarted'),
    'saved-not-running': dict(saved='not_running'),
    'saved-only': dict(saved='saved'),
    'saved-failed': dict(saved='failed'),
    'saved-unknown': dict(saved='bogus'),
    'problems-and-hotspot-and-note': dict(problems=['One'], hotspot='Setup', note='Could not read', saved='failed'),
    'display-stopped': dict(display_running=False, board='PelotonPi'),
    'display-running': dict(display_running=True),
    'power-restart': dict(power_outcome='restart-display'),
    'power-stop': dict(power_outcome='stop-display'),
    'power-start': dict(power_outcome='start-display'),
    'power-failed-restart': dict(power_outcome='failed-restart-display'),
    'power-failed-stop': dict(power_outcome='failed-stop-display'),
    'power-failed-start': dict(power_outcome='failed-start-display'),
    'power-failed-reboot': dict(power_outcome='failed-reboot'),
    'power-failed-poweroff': dict(power_outcome='failed-poweroff'),
    'power-unavailable': dict(power_outcome='unavailable'),
    'power-unknown': dict(power_outcome='nope'),
}


@pytest.mark.parametrize('name', PAGE_CASES)
def test_the_notices_and_top_bar(name):
    compare(f'page-{name}.html', top_of(page.settings_page({}, **PAGE_CASES[name])))


UPDATES = {'version': '2.1.0', 'sha': 'a' * 40, 'branch': 'develop-beta', 'running': False, 'phase': 'idle',
           'status': None, 'step': None, 'from': None, 'outcome': None, 'check': None, 'channel': 'releases',
           'auto_check': False}
FOUND = {'channel': 'beta', 'result': 'would_update', 'message': 'would update to develop-beta (bbbbbbb)',
         'ok': True, 'at': NOW - 120, 'ref': 'develop-beta', 'sha': 'b' * 40}
CHANGES = [(12, 'Settings page: a Power menu', ['Restart or stop the display from the page', 'Reboot the Pi']),
           (13, 'Fix <the> thing', []), (14, 'Tidy', None), (None, 'A commit with no pull request'),
           (15, 'Another', ['Notes & more'])]
MANY = [(100 + i, f'Change {i}', ['Visible']) for i in range(15)] + [(200, 'Quiet', [])]
RUNNING = {**UPDATES, 'running': True, 'phase': 'switched', 'status': 'Installing the new version', 'step': 2,
           'to': {'ref': 'develop-beta', 'sha': 'b' * 40, 'version': '2.2.0-beta', 'changes': CHANGES,
                  'packages': True}}
OUTCOME = {'command': 'update', 'ok': True, 'at': NOW - 3600, 'message': 'updated to 2.1.0'}


def update_case(**changes):
    return {**UPDATES, **changes}


UPDATE_CASES = {
    'up-to-date': {'view': UPDATES},
    'no-branch': {'view': update_case(branch=None)},
    'beta-installed': {'view': update_case(installed_channel='beta', version='0.1.37-beta', channel='beta')},
    'beta-installed-no-release': {'view': update_case(installed_channel='beta', version='0.0.5-beta')},
    'beta-installed-odd-version': {'view': update_case(installed_channel='beta', version='develop')},
    'would-update-beta': {'view': update_case(channel='beta', check=FOUND)},
    'would-update-changes': {'view': update_case(channel='beta', check={**FOUND, 'changes': CHANGES,
                                                                        'packages': True})},
    'would-update-many-changes': {'view': update_case(check={**FOUND, 'changes': MANY, 'channel': 'releases',
                                                             'ref': 'v2.2.0', 'version': '2.2.0'})},
    'would-update-ref-and-sha': {'view': update_case(check={**FOUND, 'ref': 'v9', 'channel': 'releases'})},
    'would-update-from-beta': {'view': update_case(installed_channel='beta', version='0.1.5-beta',
                                                   check={**FOUND, 'changes': CHANGES})},
    'current': {'view': update_case(check={**FOUND, 'result': 'current', 'message': 'no release newer than 2.1.0'})},
    'waiting-plain': {'view': update_case(check={**FOUND, 'result': 'waiting', 'message': "3333333's CI is running"})},
    'waiting-runs': {'view': update_case(check={**FOUND, 'result': 'waiting', 'message': 'x',
                                                'runs': [['pytest (3.13)', 'passed'], ['pytest (3.11)', 'running']]})},
    'waiting-failed': {'view': update_case(check={**FOUND, 'result': 'waiting', 'message': 'x',
                                                  'runs': [['test (3.11)', 'passed'], ['lint', 'failed']]})},
    'waiting-no-runs': {'view': update_case(check={**FOUND, 'result': 'waiting', 'message': 'x', 'runs': []})},
    'waiting-three-runs': {'view': update_case(check={**FOUND, 'result': 'waiting', 'message': 'x',
                                                      'runs': [['a', 'running'], ['b', 'running'], ['c', 'passed']]})},
    'blocked': {'view': update_case(check={**FOUND, 'result': 'blocked', 'ok': False,
                                           'message': 'the checkout has changes: M a'})},
    'auto-check': {'view': update_case(auto_check=True)},
    'auto-check-beta': {'view': update_case(auto_check=True, channel='beta')},
    'running': {'view': RUNNING},
    'running-rollback': {'view': update_case(running=True, phase='ready', status='Rolling back', step=None)},
    'running-no-target': {'view': update_case(running=True, phase='ready', status=None, step=0, to=None)},
    'started-while-idle': {'view': UPDATES, 'started': 'started'},
    'started-while-running': {'view': RUNNING, 'started': 'started'},
    'busy': {'view': UPDATES, 'started': 'busy'},
    'start-failed': {'view': UPDATES, 'started': 'start_failed'},
    'unfinished': {'view': update_case(phase='switched')},
    'rollback-failed': {'view': update_case(phase='rollback_failed')},
    'outcome-ok': {'view': update_case(outcome=OUTCOME)},
    'outcome-failed': {'view': update_case(outcome={**OUTCOME, 'ok': False, 'message': 'tests failed, rolled back'})},
    'outcome-rollback': {'view': update_case(outcome={**OUTCOME, 'command': 'rollback'})},
    'outcome-recover': {'view': update_case(outcome={**OUTCOME, 'command': 'recover'})},
    'outcome-hidden-while-running': {'view': {**RUNNING, 'outcome': OUTCOME}},
    'can-roll-back': {'view': update_case(phase='installed', **{'from': {'sha': 'c' * 40, 'version': '2.0.0',
                                                                         'branch': 'main'}})},
    'can-roll-back-beta': {'view': update_case(phase='checking', **{'from': {'sha': 'c' * 40, 'version': '0.1.2-beta',
                                                                             'branch': 'develop-beta'}})},
    'can-roll-back-while-running': {'view': {**RUNNING, 'from': {'sha': 'c' * 40, 'version': '2.0.0'}}},
    'rolled-back-no-button': {'view': update_case(phase='rolled_back', **{'from': {'sha': 'c' * 40}})},
}


@pytest.mark.parametrize('name', UPDATE_CASES)
def test_the_updates_card(name):
    case = UPDATE_CASES[name]
    config = {'display': {'timezone': 'America/New_York'}}
    html = page.settings_page(config, updates=case['view'], started=case.get('started'))
    compare(f'updates-{name}.html', top_of(html))
    if 'started' not in case:
        zone = page._zone(config['display'])
        compare(f'updates-check-{name}.html', page.check_result(case['view'], zone))


def test_the_pages_after_a_check_and_a_renewal_poll():
    zone = page._zone({'timezone': 'America/New_York'})
    compare('renewal-status.html', page.renewal_status(LOGINS['healthy'], zone))
    compare('renewal-status-running.html', page.renewal_status(LOGINS['renewing'], zone))
    assert page._zone({}) is None and page._zone({'timezone': 'Not/AZone'}) is None


HISTORY = {
    'ready-and-incomplete': [
        {'name': 'Joel', 'state': 'ready', 'workouts': 1234, 'updated': NOW - 600,
         'incomplete': [{'date': '2023-11-02', 'title': 'Cool <ride>', 'missing': ['performance graph']},
                        {'date': 'bogus', 'title': None, 'missing': ['class details', 'movement list']},
                        {'date': None, 'title': 'No date', 'missing': ['performance graph']}]},
        {'name': 'Jen', 'state': 'ready', 'workouts': 1, 'updated': None, 'incomplete': []}],
    'waiting': [{'name': 'Joel', 'state': 'missing'}, {'name': 'Jen', 'state': 'old'},
                {'name': 'Sam', 'state': 'unreadable'}, {'name': 'Pat', 'state': 'surprise'}],
    'one-waiting': [{'name': 'Joel', 'state': 'missing'}],
    'empty': [],
}


def insights_of(html):
    start = html.index('<section class="card" id="insights"')
    return normalised(html[start:html.index('<section class="card" id="timing"')])


@pytest.mark.parametrize('name', HISTORY)
@pytest.mark.parametrize('on', [True, False])
def test_the_workout_insights_card(name, on):
    config = {'display': {'workout_insights': on, 'timezone': 'America/New_York'}}
    html = page.settings_page(config, history=HISTORY[name])
    compare(f'insights-{name}-{"on" if on else "off"}.html', insights_of(html))


def test_the_insights_card_without_history():
    compare('insights-no-history.html', insights_of(page.settings_page({'display': {'workout_insights': True}})))


@pytest.mark.parametrize('name, args', [
    ('plain', {}), ('board', dict(board='PelotonPi')), ('shown', dict(shown_s=120)), ('shown-long', dict(shown_s=600)),
    ('shown-short', dict(shown_s=20)), ('wrong', dict(wrong=True)), ('phone', dict(phone=True)),
    ('sent', dict(sent='sent', phone=True)), ('wait', dict(sent='wait', phone=True)),
    ('used', dict(sent='used', phone=True)), ('failed', dict(sent='failed', phone=True)),
    ('signed-out', dict(signed_out=True)), ('display-stopped', dict(display_running=False)),
    ('display-stopped-phone', dict(display_running=False, phone=True)),
    ('everything', dict(shown_s=90, board='PelotonPi', phone=True, wrong=True, display_running=False)),
])
def test_the_sign_in_page(name, args):
    compare(f'pin-{name}.html', normalised(page.pin_page(**args)))


def test_the_message_page():
    compare('message.html', normalised(page.message_page('Not <found>', "There's nothing at this address.")))
