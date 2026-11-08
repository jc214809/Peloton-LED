"""The settings page's form and config.json: what the page posts becomes the config to save."""
import copy
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from peloton.config import DEFAULTS, MATRIX_DEFAULTS, ROTATION_SECTIONS, load_config
from settings_page import page
from settings_page.form import (FORM_FIELD, SCREEN_NAMES, advanced_keys, apply_form, duration_fallback,
                                number_text, panel_size, rotation_rows)

ROOT = Path(__file__).resolve().parents[1]

TWO_RIDERS = {
    'debug': False,
    'matrix': {'rows': 32, 'cols': 64, 'gpio_mapping': 'adafruit-hat-pwm', 'brightness': 70},
    'users': [
        {'name': 'Joel', 'email_env': 'PELOTON_EMAIL_RIDER_ONE', 'password_env': 'PELOTON_PASSWORD_RIDER_ONE',
         'weekly_goals': {'workouts': 5, 'minutes': 0}, 'milestones': [100, 250]},
        {'name': 'Jen', 'token_path': 'cookies-jen.txt'},
    ],
    'display': {'timezone': 'America/New_York', 'rotation': ['username', 'latest_workouts', 'goals'],
                'screen_durations': {'latest_workouts': 15, 'username': 9}, 'weekly_goals': {'workouts': 3},
                'journey': {'from': 'A', 'to': 'B', 'miles': 10}, 'cache_path': 'keep.json'},
    'future_key': {'kept': True},
}


class FormReader(HTMLParser):
    """What a browser posts for the page's settings form, as parse_qs gives it."""

    def __init__(self):
        super().__init__()
        self.fields, self.in_form, self.select, self.first_option = {}, False, None, None

    def add(self, name, value):
        self.fields.setdefault(name, []).append(value)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form' and a.get('id') == 'settings':
            self.in_form = True
        if not self.in_form:
            return
        if tag == 'input' and a.get('name'):
            if a.get('type') == 'checkbox':
                if 'checked' in a:
                    self.add(a['name'], 'on')
            else:
                self.add(a['name'], a.get('value', ''))
        elif tag == 'select':
            self.select, self.first_option = a['name'], None
        elif tag == 'option' and self.select:
            if self.first_option is None:
                self.first_option = a.get('value', '')
            if 'selected' in a:
                self.add(self.select, a.get('value', ''))
                self.select = None

    def handle_endtag(self, tag):
        if tag == 'select' and self.select:  # nothing selected: the browser posts the first option
            self.add(self.select, self.first_option)
            self.select = None
        if tag == 'form':
            self.in_form = False


def posted(config, **changes):
    """The form the page shows for config, as posted, with changes: {field: value or [values], or None to
    leave it out (an unticked switch)}."""
    reader = FormReader()
    reader.feed(page.settings_page(config))
    fields = reader.fields
    for name, value in changes.items():
        if value is None:
            fields.pop(name, None)
        else:
            fields[name] = value if isinstance(value, list) else [str(value)]
    return fields


def test_every_rotation_screen_is_on_the_page():
    assert set(SCREEN_NAMES) == ROTATION_SECTIONS
    assert tuple(SCREEN_NAMES) == tuple(DEFAULTS['rotation'])


@pytest.mark.parametrize('config', [
    TWO_RIDERS,
    json.loads((ROOT / 'config.json-example').read_text()),
    json.loads((ROOT / 'packaging' / 'config.pi.json').read_text()),
    json.loads((ROOT / 'config.dual-users-example.json').read_text()),
    {},
])
def test_saving_the_page_unchanged_keeps_a_config_that_loads_the_same(tmp_path, config):
    new, problems = apply_form(config, posted(config))
    assert problems == []
    before, after = tmp_path / 'before.json', tmp_path / 'after.json'
    before.write_text(json.dumps(config))
    after.write_text(json.dumps(new))

    def same(loaded):
        """The page spells some settings out: debug false, and a 0 weekly goal (none at all)."""
        loaded.setdefault('debug', False)
        for owner in [loaded['display']] + (loaded.get('users') or []):
            if 'weekly_goals' in owner:
                owner['weekly_goals'] = {k: v for k, v in owner['weekly_goals'].items() if v}
        return loaded
    assert same(load_config(after)) == same(load_config(before))


def test_keys_the_page_does_not_show_are_kept():
    new, problems = apply_form(TWO_RIDERS, posted(TWO_RIDERS))
    assert problems == []
    assert new['future_key'] == {'kept': True}
    assert new['display']['journey'] == TWO_RIDERS['display']['journey']
    assert new['display']['cache_path'] == 'keep.json'
    assert new['users'][0]['email_env'] == 'PELOTON_EMAIL_RIDER_ONE'
    assert new['users'][1]['token_path'] == 'cookies-jen.txt'
    assert TWO_RIDERS['users'][0]['milestones'] == [100, 250]  # the original isn't touched


def test_rotation_follows_page_order_and_switches():
    order = ['goals', 'username', 'streaks', 'latest_workouts'] + [n for n in SCREEN_NAMES
                                                                    if n not in ('goals', 'username', 'streaks',
                                                                                 'latest_workouts')]
    form = posted(TWO_RIDERS, rotation_order=order, rotation_on_streaks='on', rotation_on_latest_workouts=None)
    new, problems = apply_form(TWO_RIDERS, form)
    assert problems == []
    assert new['display']['rotation'] == ['goals', 'username', 'streaks']


def test_rotation_rows_list_the_rotation_first_then_the_rest_off():
    rows = rotation_rows({'rotation': ['goals', 'username', 'bogus']})
    assert rows[:2] == [('goals', True), ('username', True)]
    assert {name for name, on in rows[2:] if on} == set()
    assert [name for name, _ in rows].count('goals') == 1 and len(rows) == len(SCREEN_NAMES)
    assert [name for name, on in rotation_rows({}) if on] == list(DEFAULTS['rotation'])


def test_screen_times_blank_falls_back_and_numbers_are_kept():
    form = posted(TWO_RIDERS, duration_username='', duration_goals='6.5', duration_heatmap='0')
    new, problems = apply_form(TWO_RIDERS, form)
    assert problems == []
    assert new['display']['screen_durations'] == {'latest_workouts': 15, 'goals': 6.5, 'heatmap': 0}
    assert 'duration_total_workouts' not in form  # timed by Lifetime


def test_duration_fallbacks_name_the_setting_the_app_uses():
    display = {**DEFAULTS, 'duration': 7, 'last_workout_duration': 30, 'overview_duration': 4}
    assert duration_fallback(display, 'username') == 7
    assert duration_fallback(display, 'latest_workouts') == 30
    assert duration_fallback(display, 'goals') == 4


@pytest.mark.parametrize('field,value,message', [
    ('duration_goals', '-1', 'screen_durations values must be non-negative'),
    ('duration_goals', 'soon', 'screen_durations values must be non-negative'),
    ('refresh_interval', '0', 'display.refresh_interval must be a positive integer'),
    ('refresh_interval', '60.5', 'display.refresh_interval must be a positive integer'),
    ('timezone', 'Mars/Olympus', 'invalid display.timezone'),
    ('goal_workouts', '-2', 'weekly_goals values must be non-negative'),
    ('milestones', '100, ten', 'milestones must contain positive integers'),
    ('rider_0_milestones', '0', 'milestones must contain positive integers'),
    ('matrix_brightness', '101', 'matrix.brightness must be a whole number from 1 to 100'),
    ('matrix_slowdown_gpio', '9', 'matrix.slowdown_gpio must be a whole number from 0 to 4'),
    ('matrix_rgb_sequence', 'RGX', 'matrix.rgb_sequence must be an ordering'),
    ('panel_size', '64x48', 'matrix.rows must be 32 or 64'),
    ('panel_size', 'big', 'Panel size should be like 64x32'),
    ('font', 'comic-sans', 'unsupported display.font'),
    ('streak_reminder_day', '9', 'streak_reminder_day must be 0 (Monday) to 6'),
])
def test_bad_values_are_named_and_nothing_is_saved(field, value, message):
    _, problems = apply_form(TWO_RIDERS, posted(TWO_RIDERS, **{field: value}))
    assert len(problems) == 1 and message in problems[0]
    assert not problems[0].startswith('config.json')


def test_brightness_schedule_on_off_and_bad_times():
    on = posted(TWO_RIDERS, brightness_schedule='on', bright_day='90', bright_night='10',
                day_start='06:30', night_start='21:00')
    new, problems = apply_form(TWO_RIDERS, on)
    assert problems == []
    assert new['display']['brightness_schedule'] == {'day': 90, 'night': 10, 'day_start': '06:30',
                                                      'night_start': '21:00'}
    new, _ = apply_form(new, posted(new, brightness_schedule=None))
    assert new['display']['brightness_schedule'] is None
    _, problems = apply_form(TWO_RIDERS, posted(TWO_RIDERS, brightness_schedule='on', day_start=''))
    assert problems and 'brightness day_start must use HH:MM' in problems[0]


def test_quiet_hours_keep_their_own_time_zone():
    config = copy.deepcopy(TWO_RIDERS)
    config['display']['refresh_schedule'] = {'quiet_start': '23:00', 'quiet_end': '05:00',
                                             'quiet_interval': 1800, 'timezone': 'Europe/London'}
    new, problems = apply_form(config, posted(config, quiet_interval='3600'))
    assert problems == []
    assert new['display']['refresh_schedule'] == {'timezone': 'Europe/London', 'quiet_start': '23:00',
                                                  'quiet_end': '05:00', 'quiet_interval': 3600}
    new, _ = apply_form(new, posted(new, refresh_schedule=None))
    assert new['display']['refresh_schedule'] is None
    _, problems = apply_form(config, posted(config, quiet_interval='0'))
    assert problems and 'quiet_interval must be a positive integer' in problems[0]


def test_shared_goals_blank_is_no_goal_and_milestones_are_sorted_once_each():
    new, problems = apply_form(TWO_RIDERS, posted(TWO_RIDERS, goal_workouts='', goal_minutes='150',
                                                  milestones='500, 100 250,100', milestone_step=''))
    assert problems == []
    assert new['display']['weekly_goals'] == {'workouts': 0, 'minutes': 150}
    assert new['display']['milestones'] == [100, 250, 500]
    assert 'milestone_step' not in new['display']


def test_milestone_countdown_settings_save_blank_to_default_and_reject_bad_values():
    new, problems = apply_form(TWO_RIDERS, posted(TWO_RIDERS, milestone_within='8',
                                                  milestone_pages='',
                                                  discipline_milestone_celebrate_within='0'))
    assert problems == []
    assert new['display']['milestone_within'] == 8
    assert new['display']['discipline_milestone_celebrate_within'] == 0  # 0 is "never", not blank
    assert 'milestone_pages' not in new['display']
    for field, value in (('milestone_within', '0'), ('milestone_pages', '0'),
                         ('discipline_milestone_celebrate_within', '2.5')):
        _, problems = apply_form(TWO_RIDERS, posted(TWO_RIDERS, **{field: value}))
        assert problems and field in problems[0]


def test_each_rider_has_own_goals_or_everyones():
    form = posted(TWO_RIDERS, rider_0_workouts='', rider_0_minutes='', rider_0_milestones='',
                  rider_1_workouts='4', rider_1_milestones='50 100', rider_1_username='JenRides')
    new, problems = apply_form(TWO_RIDERS, form)
    assert problems == []
    joel, jen = new['users']
    assert 'weekly_goals' not in joel and 'milestones' not in joel
    assert jen['weekly_goals'] == {'workouts': 4, 'minutes': 0}
    assert jen['milestones'] == [50, 100]
    assert jen['username'] == 'JenRides'
    new, _ = apply_form(new, posted(new, rider_1_username=''))
    assert 'username' not in new['users'][1]


def test_a_rider_list_changed_since_the_page_loaded_saves_nothing():
    form = posted(TWO_RIDERS)
    renamed = copy.deepcopy(TWO_RIDERS)
    renamed['users'][0]['name'] = 'Joe'
    _, problems = apply_form(renamed, form)
    assert problems == ['The riders in config.json changed since this page loaded: reload it and try again.']


def test_panel_size_and_matrix_blanks():
    form = posted(TWO_RIDERS, panel_size='64x64', matrix_brightness='', matrix_pixel_mapper='Rotate:180',
                  matrix_show_refresh='true', matrix_pwm_bits='9', matrix_rgb_sequence='rbg')
    new, problems = apply_form(TWO_RIDERS, form)
    assert problems == []
    matrix = new['matrix']
    assert (matrix['rows'], matrix['cols']) == (64, 64)
    assert 'brightness' not in matrix
    assert matrix['pixel_mapper'] == 'Rotate:180'
    assert matrix['show_refresh'] is True and matrix['pwm_bits'] == 9 and matrix['rgb_sequence'] == 'rbg'
    new, _ = apply_form(new, posted(new, matrix_show_refresh='false', matrix_pixel_mapper=''))
    assert new['matrix']['show_refresh'] is False and 'pixel_mapper' not in new['matrix']


def test_a_board_with_a_gpio_mapping_is_not_offered_none():
    html = page.settings_page(TWO_RIDERS)
    select = html.split('id="matrix_gpio_mapping"', 1)[1].split('</select>', 1)[0]
    assert '>Not set<' not in select and 'value="adafruit-hat-pwm" selected' in select
    unset = page.settings_page({})
    assert '>Not set<' in unset.split('id="matrix_gpio_mapping"', 1)[1].split('</select>', 1)[0]


def test_display_options_and_switches():
    form = posted(TWO_RIDERS, debug='on', compact_workout_pages='on', streak_reminder_day='off',
                  username='Rider', font='info', color='gold')
    new, problems = apply_form(TWO_RIDERS, form)
    assert problems == []
    assert new['debug'] is True
    d = new['display']
    assert d['compact_workout_pages'] is True and d['streak_reminder_day'] is None
    assert (d['username'], d['font'], d['color']) == ('Rider', 'info', 'gold')
    new, _ = apply_form(new, posted(new, debug=None, streak_reminder_day='0'))
    assert new['debug'] is False and new['display']['streak_reminder_day'] == 0


def test_a_post_that_is_not_the_whole_form_changes_nothing():
    form = posted(TWO_RIDERS)
    del form[FORM_FIELD]
    new, problems = apply_form(TWO_RIDERS, form)
    assert new is TWO_RIDERS and problems


def test_a_broken_config_still_gives_a_page_and_saves_whole():
    broken = {'display': 'nope', 'matrix': [], 'users': 'x'}
    form = posted(broken)
    new, problems = apply_form(broken, form)
    assert problems == ["users must be a non-empty list"]
    del broken['users']
    new, problems = apply_form(broken, posted(broken))
    assert problems == [] and isinstance(new['display'], dict) and isinstance(new['matrix'], dict)


def test_helpers():
    assert panel_size({}) == '64x64' and panel_size({'rows': 32}) == '64x32'
    assert number_text(4.0) == '4' and number_text(None) == '' and number_text(True) == '' and number_text(2.5) == '2.5'
    assert set(advanced_keys()) | {'rows', 'cols', 'brightness', 'gpio_mapping', 'pixel_mapper', 'slowdown_gpio',
                                   'pwm_lsb_nanoseconds'} == set(MATRIX_DEFAULTS)


def test_rotation_rows_have_a_grip_and_arrow_for_the_script():
    html = page.settings_page(TWO_RIDERS)
    rows = html.split('<li class="screen-row')[1:]
    assert len(rows) == len(SCREEN_NAMES)
    for row in rows:
        # Hidden until the script runs: without it, rows keep their order and the switches still work.
        assert 'class="grip js-only" hidden aria-label="Drag to reorder' in row
        assert 'class="move js-only" hidden' in row
    assert "screens.append(row)" in page.SCRIPT  # switched off: to the bottom
    assert "addEventListener('pointerdown'" in page.SCRIPT  # mouse and touch dragging


def test_total_workouts_time_says_it_matches_lifetime():
    html = page.settings_page(TWO_RIDERS)
    row = next(r for r in html.split('<li class="screen-row')[1:] if 'value="total_workouts"' in r)
    assert '>Same as Lifetime</span>' in row
    assert 'title="Shown as long as each Lifetime by discipline page"' in row
    assert 'duration_total_workouts' not in row


def test_number_fields_show_their_units():
    import re
    config = {**TWO_RIDERS, 'display': {**TWO_RIDERS['display'], 'brightness_schedule': None}}
    html = page.settings_page(config)
    units = dict(re.findall(r'<span class="unit"[^>]*><input [^>]*id="([^"]+)"[^>]*>'
                            r'<span class="unit-text" aria-hidden="true">([^<]+)</span>', html))
    expected = {'duration_goals': 's', 'overview_duration': 's', 'refresh_interval': 's', 'logo_duration': 's',
                'last_workout_detail_interval': 's', 'quiet_interval': 's', 'goal_minutes': 'min',
                'goal_workouts': 'workouts', 'milestone_step': 'workouts', 'rider_0_minutes': 'min',
                'rider_1_workouts': 'workouts', 'bright_day': '%', 'bright_night': '%', 'matrix_brightness': '%',
                'matrix_pwm_lsb_nanoseconds': 'ns', 'matrix_limit_refresh': 'Hz'}
    assert {name: units.get(name) for name in expected} == expected
    assert 'duration_total_workouts' not in units  # timed by Lifetime, no field
    assert 'matrix_chain' not in units and 'matrix_slowdown_gpio' not in units  # counts, not units
    assert 'style="--u: 8"' in html  # "workouts" gets room for its 8 letters
    assert '(seconds)' not in html and '(ns)' not in html


def _card(html, sid):
    return html.split(f'id="{sid}"', 1)[1].split('</section>', 1)[0]


def test_name_and_text_is_gone_and_its_settings_live_where_they_belong():
    html = page.settings_page(TWO_RIDERS)
    assert 'Name and text' not in html and 'href="#display"' not in html
    assert 'name="font"' not in html, 'the name screen fits its own font: the setting did nothing'
    assert 'name="streak_reminder_day"' in _card(html, 'goals')
    general = _card(html, 'general')
    assert 'Text colour' in general and 'name="compact_workout_pages"' in general
    assert 'Text colour' not in _card(html, 'panel')
    assert html.index('href="#general"') < html.index('href="#rotation"'), 'first of the settings'
    assert html.index('id="general"') < html.index('id="rotation"')
    advanced = html.split('id="advanced"', 1)[1].split('</details>', 1)[0]
    assert 'Fallback name' in advanced and 'name="username"' in advanced


def test_the_text_colours_are_four_plus_an_old_configs_own():
    colours = re.findall(r'<option value="(\w+)"', page.settings_page(TWO_RIDERS).split('id="color"', 1)[1].split('</select>', 1)[0])
    assert colours == ['white', 'gold', 'red', 'disney_blue']
    old = {**TWO_RIDERS, 'display': {**TWO_RIDERS['display'], 'color': 'down'}}
    select = page.settings_page(old).split('id="color"', 1)[1].split('</select>', 1)[0]
    assert '<option value="down" selected>Red (darker)</option>' in select


def test_compact_pages_show_only_on_64x32_and_a_64x64_save_keeps_them():
    big = {**TWO_RIDERS, 'matrix': {**TWO_RIDERS['matrix'], 'rows': 64},
           'display': {**TWO_RIDERS['display'], 'compact_workout_pages': True}}
    assert 'compact_workout_pages' not in page.settings_page(big)
    new, problems = apply_form(big, posted(big))
    assert not problems and new['display']['compact_workout_pages'] is True, 'not on the page: kept'
    small = {**big, 'matrix': TWO_RIDERS['matrix']}
    new, _ = apply_form(small, posted(small, compact_workout_pages=None))
    assert new['display']['compact_workout_pages'] is False, 'on the page and unticked: off'


def test_the_font_a_config_has_is_kept_though_the_page_no_longer_shows_it():
    config = {**TWO_RIDERS, 'display': {**TWO_RIDERS['display'], 'font': 'titles'}}
    new, _ = apply_form(config, posted(config))
    assert new['display']['font'] == 'titles'


def test_rotation_has_column_headings_with_tooltips():
    html = page.settings_page(TWO_RIDERS)
    rotation = _card(html, 'rotation')
    head = rotation.split('id="screens-head">', 1)[1].split('</div>', 1)[0]
    assert [h for h in re.findall(r'<span class="(?:grip-col|seconds-col|)">([^<]*)', head)] == ['', '#', 'Screen', 'Seconds', 'Show', '']
    for tid, label in (('tip-rotation-order', 'Order'), ('tip-rotation-seconds', 'Seconds'), ('tip-rotation-show', 'Show')):
        assert f'aria-label="About {label}" aria-describedby="{tid}"' in head
        assert f'role="tooltip" id="{tid}">' in head
    assert '0 skips the screen' in head and 'Seconds per page' not in rotation, 'the old note is in the tooltips now'
    assert rotation.index('id="screens-head"') < rotation.index('id="screens"')
    assert "getElementById('screens-head').classList.add('js')" in html, 'lines up with the grip column'
