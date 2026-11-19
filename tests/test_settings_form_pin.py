"""Pins apply_form: full and partial posted forms applied to example configs, comparing the config it returns
and the problems it names against values captured before it was split into one function per form section
(docs/CODE-HEALTH-PLAN.md, 2e).

Regenerate the fixture only for a deliberate change to what a form does: PIN_REGEN=1 python -m pytest
tests/test_settings_form_pin.py
"""
import copy
import json
import os
from pathlib import Path

from peloton.config import MATRIX_DEFAULTS, WEEKLY_GOAL_KEYS
from settings_page.form import FORM_FIELD, PANEL_FIELDS, SCREEN_NAMES, TIMING, advanced_keys, apply_form

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / 'fixtures' / 'settings_form_pin.json'

RIDERS = {
    'debug': True,
    'matrix': {'rows': 32, 'cols': 64, 'gpio_mapping': 'adafruit-hat-pwm', 'brightness': 70, 'show_refresh': True},
    'users': [
        {'name': 'Joel', 'email_env': 'E1', 'password_env': 'P1', 'username': 'joel',
         'weekly_goals': {'workouts': 5, 'minutes': 0}, 'milestones': [100, 250]},
        {'name': 'Jen', 'token_path': 'cookies-jen.txt'},
        {'email': 'nameless@example.com'},
    ],
    'display': {'timezone': 'America/New_York', 'rotation': ['username', 'latest_workouts', 'goals'],
                'screen_durations': {'latest_workouts': 15, 'username': 9, 'lifetime': 8},
                'weekly_goals': {'workouts': 3}, 'journey': {'from': 'A', 'to': 'B', 'miles': 10},
                'cache_path': 'keep.json', 'compact_workout_pages': True, 'last_workout_duration': 20,
                'discipline_milestone_celebrate_within': 3, 'brightness_schedule': {
                    'day': 80, 'night': 10, 'day_start': '07:00', 'night_start': '21:00'},
                'refresh_schedule': {'timezone': 'America/Chicago', 'quiet_start': '23:00', 'quiet_end': '06:00',
                                     'quiet_interval': 900}, 'next_class_takeover_minutes': 10},
    'future_key': {'kept': True},
}
LEGACY_ZEROS = {'display': {'rotation': ['username', 'goals', 'club'], 'logo_duration': 0,
                            'screen_durations': {'goals': 0, 'club': 4}}}
CONFIGS = {
    'riders': RIDERS,
    'example': json.loads((ROOT / 'config.json-example').read_text()),
    'dual': json.loads((ROOT / 'config.dual-users-example.json').read_text()),
    'emulator': json.loads((ROOT / 'emulator_config.json').read_text()),
    'empty': {},
    'broken-sections': {'display': 'oops', 'matrix': [1], 'users': 'none', 'debug': 'yes'},
    'legacy-zeros': LEGACY_ZEROS,
}


def _matrix_fields():
    """The Panel card's and Advanced's fields, each with a plain valid value."""
    panel = {'brightness': ['55'], 'gpio_mapping': ['regular'], 'pixel_mapper': ['Rotate:180'],
             'slowdown_gpio': ['2'], 'pwm_lsb_nanoseconds': ['200']}
    other = {'show_refresh': ['true'], 'no_hardware_pulse': ['false'], 'rgb_sequence': ['RBG']}
    fields = {f'matrix_{key}': panel[key] for key, _, _ in PANEL_FIELDS}
    fields.update({f'matrix_{key}': other.get(key, [str(MATRIX_DEFAULTS[key] or 0)]) for key in advanced_keys()})
    return fields


def full_form(**changes):
    """Every field the page posts, with plain valid values; changes: {field: value or [values], None to omit}."""
    form = {FORM_FIELD: ['1'], 'debug': ['on'], 'username': ['Joel C'], 'font': ['stats'], 'color': ['gold'],
            'streak_reminder_day': ['4'], 'rotation_order': list(reversed(SCREEN_NAMES)),
            'show_logo': ['on'], 'workout_insights': ['on'], 'timezone': ['America/Denver'],
            'brightness_schedule': ['on'], 'bright_day': ['90'], 'bright_night': ['15'], 'day_start': ['06:30'],
            'night_start': ['20:45'], 'refresh_schedule': ['on'], 'quiet_start': ['22:00'], 'quiet_end': ['05:30'],
            'quiet_interval': ['1200'], 'milestones': ['100, 250 500 500'], 'milestone_step': ['50'],
            'milestone_within': ['8'], 'milestone_pages': ['2'], 'next_class_takeover_minutes': ['7'],
            'panel_size': ['64x64']}
    for name in SCREEN_NAMES:
        if name != 'club':
            form[f'rotation_on_{name}'] = ['on']
        form[f'duration_{name}'] = [str(6 + len(name) % 5)]
    for key, _, _ in TIMING:
        form[key] = ['12']
    for key in WEEKLY_GOAL_KEYS:
        form[f'goal_{key}'] = ['3']
    for index in range(3):
        form.update({f'rider_{index}_name': [(RIDERS['users'][index] or {}).get('name', '')],
                     f'rider_{index}_username': [f'rider{index}'], f'rider_{index}_milestones': ['10, 20']})
        for key in WEEKLY_GOAL_KEYS:
            form[f'rider_{index}_{key}'] = ['2']
    form.update(_matrix_fields())
    for name, value in changes.items():
        if value is None:
            form.pop(name, None)
        else:
            form[name] = value if isinstance(value, list) else [value]
    return form


def blank_form(**changes):
    """Only the form marker plus changes: what a partial post, or one with every switch off, looks like."""
    form = {FORM_FIELD: ['1']}
    form.update({name: value if isinstance(value, list) else [value] for name, value in changes.items()})
    return form


def _forms():
    forms = {
        'full': full_form(),
        'blank': blank_form(),
        'not-the-form': {'debug': ['on']},
        'switches-off': full_form(debug=None, show_logo=None, workout_insights=None, brightness_schedule=None,
                                  refresh_schedule=None, **{f'rotation_on_{n}': None for n in SCREEN_NAMES}),
        'blank-values': full_form(**{k: '' for k in (
            'username', 'timezone', 'milestone_step', 'milestone_within', 'milestone_pages', 'milestones',
            'next_class_takeover_minutes', 'overview_duration', 'refresh_interval', 'logo_duration',
            'last_workout_detail_interval', 'rider_0_username', 'rider_0_milestones',
            'matrix_brightness', 'matrix_gpio_mapping', 'matrix_show_refresh', 'matrix_rows')},
            **{f'duration_{n}': '' for n in SCREEN_NAMES},
            **{f'goal_{k}': '' for k in WEEKLY_GOAL_KEYS},
            **{f'rider_0_{k}': '' for k in WEEKLY_GOAL_KEYS}),
        'reminder-off': full_form(streak_reminder_day='off'),
        'reminder-missing': full_form(streak_reminder_day=None, font=None, color=None),
        'reminder-bad': full_form(streak_reminder_day='soon'),
        'rotation-junk': full_form(rotation_order=['club', 'bogus', 'club', 'goals', 'username'],
                                   rotation_on_bogus='on'),
        'rotation-order-missing': full_form(rotation_order=None),
        'screen-durations-absent': full_form(**{f'duration_{n}': None for n in SCREEN_NAMES}),
        'duration-junk': full_form(duration_username='fast', duration_goals='-3', duration_heatmap='4.5'),
        'duration-too-short': full_form(duration_milestones='2', duration_lifetime='1', duration_journey='0.5',
                                        duration_versus='0', duration_streaks='0'),
        'timing-too-short': full_form(overview_duration='0', logo_duration='0', last_workout_detail_interval='0.5',
                                      refresh_interval='0'),
        'timing-one-second': full_form(logo_duration='1', overview_duration='1.5'),
        'brightness-schedule-junk': full_form(bright_day='bright', day_start='7am'),
        'refresh-schedule-junk': full_form(quiet_interval='often', quiet_start=''),
        'goals-junk': full_form(goal_workouts='many', goal_active_days='9'),
        'goals-negative': full_form(goal_minutes='-5'),
        'milestones-floats': full_form(milestones='1.5, 100'),
        'milestones-words': full_form(milestones='one hundred'),
        'milestones-sorted': full_form(milestones='500 100 250 100'),
        'milestone-step-junk': full_form(milestone_step='lots'),
        'takeover-zero': full_form(next_class_takeover_minutes='0'),
        'rider-mismatch': full_form(rider_0_name='Someone Else'),
        'rider-second-mismatch': full_form(rider_1_name='Jon'),
        'rider-no-goals': full_form(rider_0_workouts='', rider_0_minutes='', rider_0_active_days=''),
        'rider-some-goals': full_form(rider_0_workouts='4', rider_0_minutes='', rider_0_active_days=''),
        'rider-goals-junk': full_form(rider_0_workouts='x'),
        'riders-absent': full_form(**{f'rider_{i}_name': None for i in range(3)}),
        'rider-index-beyond': full_form(rider_5_name='Ghost', rider_5_username='ghost'),
        'panel-bad': full_form(panel_size='wide'),
        'panel-32': full_form(panel_size='64x32'),
        'panel-absent': full_form(panel_size=None),
        'panel-junk-numbers': full_form(matrix_brightness='bright', matrix_slowdown_gpio='9', matrix_pwm_bits='99'),
        'panel-switches': full_form(matrix_show_refresh='true', matrix_no_hardware_pulse='true'),
        'panel-strings': full_form(matrix_gpio_mapping='adafruit-hat', matrix_pixel_mapper='Mirror:H',
                                   matrix_rgb_sequence='GRB'),
        'panel-bad-mapping': full_form(matrix_gpio_mapping='custom'),
        'matrix-fields-absent': full_form(**{f'matrix_{k}': None for k in
                                             [k for k, _, _ in PANEL_FIELDS] + advanced_keys()}),
        'username-spaces': full_form(username='  Joel  ', timezone='  UTC  '),
        'timezone-bad': full_form(timezone='Mars/Base'),
        'partial-display': blank_form(username='Only Name', color='red'),
        'partial-rotation': blank_form(rotation_order=['goals', 'username'], rotation_on_goals='on',
                                       rotation_on_username='on'),
        'partial-durations': blank_form(duration_goals='7', duration_total_workouts='9', duration_latest_workouts='3'),
        'partial-panel': blank_form(panel_size='64x32', matrix_brightness='40'),
        'partial-riders': blank_form(rider_0_name='Joel', rider_0_username='j', rider_1_name='Jen'),
        'partial-schedules': blank_form(brightness_schedule='on', bright_day='80', bright_night='20',
                                        day_start='08:00', night_start='22:00', refresh_schedule='on',
                                        quiet_start='23:00', quiet_end='06:00', quiet_interval='600'),
        'partial-timing': blank_form(overview_duration='8', logo_duration='3'),
        'partial-goals': blank_form(goal_workouts='4', milestones='100 200'),
    }
    return forms


def _cases():
    return {f'{config}/{form}': (config, form) for config in CONFIGS for form in _forms()}


def _apply(config_name, form_name):
    config = copy.deepcopy(CONFIGS[config_name])
    before = copy.deepcopy(config)
    result, problems = apply_form(config, _forms()[form_name])
    assert config == before  # never edits the config it is given, unless it returns it as is
    return {'config': json.loads(json.dumps(result, default=repr)), 'problems': problems}


def test_apply_form_matches_the_pinned_output():
    got = {name: _apply(*pair) for name, pair in _cases().items()}
    if os.environ.get('PIN_REGEN'):
        FIXTURE.write_text(json.dumps(got, sort_keys=True, separators=(',', ':')) + '\n')
    expected = json.loads(FIXTURE.read_text())
    assert sorted(got) == sorted(expected)
    for name in got:
        assert got[name] == expected[name], name


def test_the_pinned_forms_reach_every_kind_of_outcome():
    outcomes = [_apply(*pair) for pair in _cases().values()]
    problems = ' '.join(p for outcome in outcomes for p in outcome['problems'])
    assert any(not o['problems'] for o in outcomes)
    for fragment in ("That wasn't the settings form", 'changed since this page loaded', 'Panel size should be',
                     'needs at least', 'To hide the logo, switch it off', 'To hide it, switch it off'):
        assert fragment in problems
