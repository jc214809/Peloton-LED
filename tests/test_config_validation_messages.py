"""Pins what validate_config says, word for word and in order, for every check it makes.

validate_config raises ValueError naming the first problem, prefixed with the path, so each case here is
one config and the exact text of that error. Cases with two faults pin which one is reported first.
Written before validate_config was made table-driven and kept unchanged through it: any rewording is a
change the settings page and these tests must see.
"""
import copy
import json
import logging
import math
from pathlib import Path

import pytest

from peloton.config import validate_config

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / 'fixtures' / 'config_validation'
PATH = 'config.json'
GOOD_JOURNEY = {'from': 'A', 'to': 'B', 'miles': 10}
BRIGHTNESS = {'day': 80, 'night': 20, 'day_start': '07:00', 'night_start': '21:00'}
REFRESH = {'quiet_start': '23:00', 'quiet_end': '06:00', 'quiet_interval': 3600}
GOALS_KEYS = 'must contain only workouts, minutes and active_days'
DURATION_TEXT = 'must be a number above 0 (switch a screen off to hide it)'
ROTATION_TEXT = 'display.rotation must contain unique supported screen names'
TAKEOVER_TEXT = 'display.next_class_takeover_minutes must be a whole number of minutes from 0 (off) to 10'
BRIGHTNESS_KEYS = 'display.brightness_schedule requires day, night, day_start, and night_start'
REFRESH_KEYS = 'display.refresh_schedule requires quiet_start, quiet_end, and quiet_interval'
REMINDER_TEXT = 'display.streak_reminder_day must be 0 (Monday) to 6 (Sunday), or null'
PR_AGE_TEXT = 'display.pr_max_age_days must be a whole number of days of at least 1, or null'
DISCIPLINES_TEXT = 'display.journey.disciplines must be a non-empty list of discipline names'
RGB_TEXT = 'matrix.rgb_sequence must be an ordering of R, G and B, e.g. "RBG"'
GPIO_TEXT = 'matrix.gpio_mapping must be one of regular, adafruit-hat, adafruit-hat-pwm, or null'


def display(**keys):
    return {'display': keys}


def rider(**keys):
    return {'users': [{'name': 'Joel', **keys}]}


def message_of(config):
    with pytest.raises(ValueError) as caught:
        validate_config(copy.deepcopy(config), PATH)
    return str(caught.value)


def case(config, message, id):
    return pytest.param(config, f'{PATH}: {message}', id=id)


# Every case: (config, the error's full text). Grouped in the order validate_config checks them.
STRUCTURE = [
    case([], 'config and display must be JSON objects', 'config-not-an-object'),
    case({'display': 5}, 'config and display must be JSON objects', 'display-not-an-object'),
    case({'display': None}, 'config and display must be JSON objects', 'display-null'),
]

USERS = [
    case({'users': 'Joel'}, 'users must be a non-empty list', 'users-not-a-list'),
    case({'users': []}, 'users must be a non-empty list', 'users-empty'),
    case({'users': ['Joel']}, 'users[0] must be an object', 'user-not-an-object'),
    case({'users': [{'name': 'A'}, 7]}, 'users[1] must be an object', 'second-user-not-an-object'),
    case({'users': [{}]}, 'users[0] requires a name string', 'user-without-name'),
    case({'users': [{'name': 5}]}, 'users[0] requires a name string', 'user-name-not-a-string'),
    case({'users': [{'name': ' '}]}, 'users[0] requires a name string', 'user-name-blank'),
    case({'users': [{'name': 'Joel', 'token_path': ''}]},
         'users[0].token_path must be a non-empty string', 'token-path-empty'),
    case({'users': [{'name': 'Joel', 'token_path': 5}]},
         'users[0].token_path must be a non-empty string', 'token-path-not-a-string'),
    case({'users': [{'name': 'A'}, {'name': 'B', 'token_path': ' '}]},
         'users[1].token_path must be a non-empty string', 'second-token-path-blank'),
    case({'users': [{'name': 'Joel'}, {'name': 'joel'}]},
         'user names and token paths must be unique', 'duplicate-name'),
    case({'users': [{'name': 'Joel'}, {'name': ' JOEL '}]},
         'user names and token paths must be unique', 'duplicate-name-spaces-and-case'),
    case({'users': [{'name': 'A', 'token_path': 't.txt'}, {'name': 'B', 'token_path': 't.txt'}]},
         'user names and token paths must be unique', 'duplicate-token-path'),
    case({'users': [{'name': 'Jen'}, {'name': 'B', 'token_path': 'cookies-jen.txt'}]},
         'user names and token paths must be unique', 'token-path-matches-default-of-earlier-rider'),
    case({'users': [{'name': 'A', 'username': 5}]}, 'users[0].username must be a string', 'user-username'),
    case({'users': [{'name': 'A', 'cache_path': 5}]}, 'users[0].cache_path must be a string', 'user-cache-path'),
    case({'users': [{'name': 'A', 'log_path': 5}]}, 'users[0].log_path must be a string', 'user-log-path'),
    case({'users': [{'name': 'A', 'cache_path': 'c.json'}, {'name': 'B', 'cache_path': 'c.json'}]},
         'user cache and log paths must be unique', 'duplicate-cache-path'),
    case({'users': [{'name': 'A', 'log_path': 'l.json'}, {'name': 'B', 'log_path': 'l.json'}]},
         'user cache and log paths must be unique', 'duplicate-log-path'),
    case({'users': [{'name': 'A', 'cache_path': 'x.json'}, {'name': 'B', 'log_path': 'x.json'}]},
         'user cache and log paths must be unique', 'cache-path-matches-log-path'),
    case({'users': [{'name': 'A', 'cache_path': 'x.json', 'log_path': 'x.json'}]},
         'user cache and log paths must be unique', 'one-rider-cache-equals-log'),
    case({'users': [{'name': 'A', 'email_env': 'lower-case'}]},
         'users[0].email_env must be an environment variable name', 'email-env-bad-name'),
    case({'users': [{'name': 'A', 'email_env': 5}]},
         'users[0].email_env must be an environment variable name', 'email-env-not-a-string'),
    case({'users': [{'name': 'A', 'password_env': '1ABC'}]},
         'users[0].password_env must be an environment variable name', 'password-env-starts-with-digit'),
    case({'users': [{'name': 'A', 'password_env': ''}]},
         'users[0].password_env must be an environment variable name', 'password-env-empty'),
    case({'users': [{'name': 'A'}, {'name': 'B', 'password_env': 'a'}]},
         'users[1].password_env must be an environment variable name', 'second-rider-password-env'),
    case({'users': [{'name': 'A', 'weekly_goals': 5}]},
         f'users[0].weekly_goals {GOALS_KEYS}', 'user-goals-not-a-dict'),
    case({'users': [{'name': 'A', 'weekly_goals': {'workouts': -1}}]},
         'users[0].weekly_goals values must be non-negative integers', 'user-goals-negative'),
    case({'users': [{'name': 'A', 'milestones': 5}]},
         'users[0].milestones must contain positive integers', 'user-milestones-not-a-list'),
    case({'users': [{'name': 'A', 'journey': 5}]},
         'users[0].journey needs from, to and miles', 'user-journey-not-a-dict'),
    # Faults in one rider are reported in check order, riders in list order.
    case({'users': [{'name': 'A', 'token_path': '', 'username': 5}]},
         'users[0].token_path must be a non-empty string', 'order-token-path-before-username'),
    case({'users': [{'name': 'A', 'username': 5, 'log_path': 5, 'cache_path': 5}]},
         'users[0].cache_path must be a string', 'order-cache-path-before-log-path-and-username'),
    case({'users': [{'name': 'A', 'username': 5, 'log_path': 5}]},
         'users[0].log_path must be a string', 'order-log-path-before-username'),
    case({'users': [{'name': 'A', 'log_path': 5, 'email_env': 'x'}]},
         'users[0].log_path must be a string', 'order-log-path-before-email-env'),
    case({'users': [{'name': 'A', 'email_env': 'x', 'weekly_goals': 5, 'milestones': 5, 'journey': 5}]},
         'users[0].email_env must be an environment variable name', 'order-email-env-before-goals'),
    case({'users': [{'name': 'A', 'weekly_goals': 5, 'milestones': 5, 'journey': 5}]},
         f'users[0].weekly_goals {GOALS_KEYS}', 'order-goals-before-milestones'),
    case({'users': [{'name': 'A', 'milestones': 5, 'journey': 5}]},
         'users[0].milestones must contain positive integers', 'order-milestones-before-journey'),
    case({'users': [{'name': 'A'}, {'name': 'a', 'cache_path': 5}]},
         'user names and token paths must be unique', 'order-duplicate-before-cache-path-type'),
    case({'users': [{'name': 'A', 'cache_path': 'c.json'}, {'name': 'B', 'cache_path': 'c.json', 'email_env': 'x'}]},
         'user cache and log paths must be unique', 'order-duplicate-cache-before-email-env'),
    case({'users': [{'name': 'A', 'username': 5}, {'name': 'a'}]},
         'users[0].username must be a string', 'order-first-rider-before-duplicate'),
    case({'users': [{'name': 'A'}, {'name': 'a', 'username': 5}]},
         'user names and token paths must be unique', 'order-duplicate-before-second-riders-fields'),
    case({'users': [{'name': 'A', 'username': 5}], 'matrix': 5},
         'users[0].username must be a string', 'order-users-before-matrix'),
]

WEEKLY_GOALS = [
    case(display(weekly_goals=None), f'display.weekly_goals {GOALS_KEYS}', 'goals-null'),
    case(display(weekly_goals=[]), f'display.weekly_goals {GOALS_KEYS}', 'goals-list'),
    case(display(weekly_goals={'steps': 1}), f'display.weekly_goals {GOALS_KEYS}', 'goals-unknown-key'),
    case(display(weekly_goals={'workouts': -1}), 'display.weekly_goals values must be non-negative integers',
         'goals-negative'),
    case(display(weekly_goals={'workouts': True}), 'display.weekly_goals values must be non-negative integers',
         'goals-bool'),
    case(display(weekly_goals={'minutes': 1.5}), 'display.weekly_goals values must be non-negative integers',
         'goals-float'),
    case(display(weekly_goals={'minutes': '30'}), 'display.weekly_goals values must be non-negative integers',
         'goals-string'),
    case(display(weekly_goals={'active_days': 8}), 'display.weekly_goals.active_days can be at most 7',
         'goals-active-days-over-7'),
    case(rider(weekly_goals={'active_days': 8}), 'users[0].weekly_goals.active_days can be at most 7',
         'user-goals-active-days-over-7'),
    case(display(weekly_goals={'active_days': -1}), 'display.weekly_goals values must be non-negative integers',
         'goals-active-days-negative'),
]

MILESTONES = [
    case(display(milestones=None), 'display.milestones must contain positive integers', 'milestones-null'),
    case(display(milestones='100'), 'display.milestones must contain positive integers', 'milestones-string'),
    case(display(milestones=[100, True]), 'display.milestones must contain positive integers', 'milestones-bool'),
    case(display(milestones=[0]), 'display.milestones must contain positive integers', 'milestones-zero'),
    case(display(milestones=[-5]), 'display.milestones must contain positive integers', 'milestones-negative'),
    case(display(milestones=[100.0]), 'display.milestones must contain positive integers', 'milestones-float'),
    case(display(milestones=['5']), 'display.milestones must contain positive integers', 'milestones-text-item'),
]

JOURNEY = [
    case(display(journey=None), 'display.journey needs from, to and miles', 'journey-null'),
    case(display(journey='Columbus'), 'display.journey needs from, to and miles', 'journey-string'),
    case(display(journey={'from': 'A', 'to': 'B'}), 'display.journey needs from, to and miles', 'journey-no-miles'),
    case(display(journey={'to': 'B', 'miles': 1}), 'display.journey needs from, to and miles', 'journey-no-from'),
    case(display(journey={**GOOD_JOURNEY, 'from': ''}), 'display.journey.from must be a non-empty string',
         'journey-from-empty'),
    case(display(journey={**GOOD_JOURNEY, 'from': 5}), 'display.journey.from must be a non-empty string',
         'journey-from-not-a-string'),
    case(display(journey={**GOOD_JOURNEY, 'to': '  '}), 'display.journey.to must be a non-empty string',
         'journey-to-blank'),
    case(display(journey={**GOOD_JOURNEY, 'from': '', 'to': ''}), 'display.journey.from must be a non-empty string',
         'journey-from-checked-before-to'),
    case(display(journey={**GOOD_JOURNEY, 'miles': True}), 'display.journey.miles must be a positive number',
         'journey-miles-bool'),
    case(display(journey={**GOOD_JOURNEY, 'miles': '880'}), 'display.journey.miles must be a positive number',
         'journey-miles-string'),
    case(display(journey={**GOOD_JOURNEY, 'miles': 0}), 'display.journey.miles must be a positive number',
         'journey-miles-zero'),
    case(display(journey={**GOOD_JOURNEY, 'miles': -3.5}), 'display.journey.miles must be a positive number',
         'journey-miles-negative'),
    case(display(journey={**GOOD_JOURNEY, 'miles': math.nan}), 'display.journey.miles must be a positive number',
         'journey-miles-nan'),
    case(display(journey={**GOOD_JOURNEY, 'miles': math.inf}), 'display.journey.miles must be a positive number',
         'journey-miles-infinite'),
    case(display(journey={**GOOD_JOURNEY, 'disciplines': []}), DISCIPLINES_TEXT, 'journey-disciplines-empty'),
    case(display(journey={**GOOD_JOURNEY, 'disciplines': 'cycling'}), DISCIPLINES_TEXT,
         'journey-disciplines-string'),
    case(display(journey={**GOOD_JOURNEY, 'disciplines': [5]}), DISCIPLINES_TEXT, 'journey-disciplines-not-text'),
    case(display(journey={**GOOD_JOURNEY, 'disciplines': ['Cycling', '']}), DISCIPLINES_TEXT,
         'journey-disciplines-blank-name'),
    case(display(journey={**GOOD_JOURNEY, 'start_date': 'someday'}),
         'display.journey.start_date must be a YYYY-MM-DD date', 'journey-start-date-text'),
    case(display(journey={**GOOD_JOURNEY, 'start_date': 5}),
         'display.journey.start_date must be a YYYY-MM-DD date', 'journey-start-date-not-text'),
    case(display(journey={**GOOD_JOURNEY, 'start_date': '2026-13-01'}),
         'display.journey.start_date must be a YYYY-MM-DD date', 'journey-start-date-bad-month'),
    case(rider(journey={**GOOD_JOURNEY, 'miles': 0}), 'users[0].journey.miles must be a positive number',
         'user-journey-miles'),
    # Check order inside the journey.
    case(display(journey={**GOOD_JOURNEY, 'from': '', 'miles': 0}), 'display.journey.from must be a non-empty string',
         'order-journey-from-before-miles'),
    case(display(journey={**GOOD_JOURNEY, 'miles': 0, 'disciplines': []}),
         'display.journey.miles must be a positive number', 'order-journey-miles-before-disciplines'),
    case(display(journey={**GOOD_JOURNEY, 'disciplines': [], 'start_date': 'x'}), DISCIPLINES_TEXT,
         'order-journey-disciplines-before-start-date'),
]

MATRIX = [
    case({'matrix': 5}, 'matrix must be a JSON object', 'matrix-not-an-object'),
    case({'matrix': []}, 'matrix must be a JSON object', 'matrix-list'),
    case({'matrix': {'zebra': 1}}, 'matrix has unsupported keys: zebra', 'matrix-one-unknown-key'),
    case({'matrix': {'zebra': 1, 'apple': 2}}, 'matrix has unsupported keys: apple, zebra',
         'matrix-unknown-keys-sorted'),
    case({'matrix': {'rows': 48}}, 'matrix.rows must be 32 or 64', 'matrix-rows-48'),
    case({'matrix': {'rows': True}}, 'matrix.rows must be 32 or 64', 'matrix-rows-bool'),
    case({'matrix': {'rows': '64'}}, 'matrix.rows must be 32 or 64', 'matrix-rows-text'),
    case({'matrix': {'cols': 0}}, 'matrix.cols must be a whole number at least 1', 'matrix-cols-zero'),
    case({'matrix': {'cols': 64.0}}, 'matrix.cols must be a whole number at least 1', 'matrix-cols-float'),
    case({'matrix': {'cols': True}}, 'matrix.cols must be a whole number at least 1', 'matrix-cols-bool'),
    case({'matrix': {'chain': 0}}, 'matrix.chain must be a whole number at least 1', 'matrix-chain'),
    case({'matrix': {'parallel': 4}}, 'matrix.parallel must be a whole number from 1 to 3', 'matrix-parallel-high'),
    case({'matrix': {'parallel': 0}}, 'matrix.parallel must be a whole number from 1 to 3', 'matrix-parallel-low'),
    case({'matrix': {'pwm_bits': 12}}, 'matrix.pwm_bits must be a whole number from 1 to 11', 'matrix-pwm-bits'),
    case({'matrix': {'brightness': 101}}, 'matrix.brightness must be a whole number from 1 to 100',
         'matrix-brightness-high'),
    case({'matrix': {'brightness': 0}}, 'matrix.brightness must be a whole number from 1 to 100',
         'matrix-brightness-low'),
    case({'matrix': {'scan_mode': 2}}, 'matrix.scan_mode must be a whole number from 0 to 1', 'matrix-scan-mode'),
    case({'matrix': {'pwm_lsb_nanoseconds': 0}}, 'matrix.pwm_lsb_nanoseconds must be a whole number at least 1',
         'matrix-pwm-lsb'),
    case({'matrix': {'row_addr_type': 4}}, 'matrix.row_addr_type must be a whole number from 0 to 3',
         'matrix-row-addr-type'),
    case({'matrix': {'multiplexing': -1}}, 'matrix.multiplexing must be a whole number at least 0',
         'matrix-multiplexing'),
    case({'matrix': {'limit_refresh': -1}}, 'matrix.limit_refresh must be a whole number at least 0',
         'matrix-limit-refresh'),
    case({'matrix': {'pwm_dither_bits': 'a'}}, 'matrix.pwm_dither_bits must be a whole number at least 0',
         'matrix-pwm-dither-bits'),
    case({'matrix': {'slowdown_gpio': 5}}, 'matrix.slowdown_gpio must be a whole number from 0 to 4, or null',
         'matrix-slowdown-gpio-high'),
    case({'matrix': {'slowdown_gpio': 'x'}}, 'matrix.slowdown_gpio must be a whole number from 0 to 4, or null',
         'matrix-slowdown-gpio-text'),
    case({'matrix': {'gpio_mapping': 'bogus'}}, GPIO_TEXT, 'matrix-gpio-mapping'),
    case({'matrix': {'show_refresh': 1}}, 'matrix.show_refresh must be true or false', 'matrix-show-refresh'),
    case({'matrix': {'no_hardware_pulse': 'no'}}, 'matrix.no_hardware_pulse must be true or false',
         'matrix-no-hardware-pulse'),
    case({'matrix': {'rgb_sequence': 5}}, RGB_TEXT, 'matrix-rgb-sequence-not-text'),
    case({'matrix': {'rgb_sequence': 'RRG'}}, RGB_TEXT, 'matrix-rgb-sequence-repeats'),
    case({'matrix': {'rgb_sequence': 'RG'}}, RGB_TEXT, 'matrix-rgb-sequence-short'),
    case({'matrix': {'pixel_mapper': 3}}, 'matrix.pixel_mapper must be a string', 'matrix-pixel-mapper'),
    # Check order inside the matrix.
    case({'matrix': {'zebra': 1, 'rows': 48}}, 'matrix has unsupported keys: zebra',
         'order-matrix-unknown-before-rows'),
    case({'matrix': {'rows': 48, 'cols': 0}}, 'matrix.rows must be 32 or 64', 'order-matrix-rows-before-cols'),
    case({'matrix': {'cols': 0, 'chain': 0}}, 'matrix.cols must be a whole number at least 1',
         'order-matrix-cols-before-chain'),
    case({'matrix': {'chain': 0, 'parallel': 9}}, 'matrix.chain must be a whole number at least 1',
         'order-matrix-chain-before-parallel'),
    case({'matrix': {'pwm_dither_bits': -1, 'slowdown_gpio': 9}},
         'matrix.pwm_dither_bits must be a whole number at least 0', 'order-matrix-ranges-before-slowdown'),
    case({'matrix': {'slowdown_gpio': 9, 'gpio_mapping': 'x'}},
         'matrix.slowdown_gpio must be a whole number from 0 to 4, or null', 'order-matrix-slowdown-before-mapping'),
    case({'matrix': {'gpio_mapping': 'x', 'show_refresh': 1}}, GPIO_TEXT, 'order-matrix-mapping-before-flags'),
    case({'matrix': {'show_refresh': 1, 'no_hardware_pulse': 1}}, 'matrix.show_refresh must be true or false',
         'order-matrix-show-refresh-before-pulse'),
    case({'matrix': {'no_hardware_pulse': 1, 'rgb_sequence': 5}}, 'matrix.no_hardware_pulse must be true or false',
         'order-matrix-flags-before-rgb'),
    case({'matrix': {'rgb_sequence': 5, 'pixel_mapper': 3}}, RGB_TEXT, 'order-matrix-rgb-before-mapper'),
    case({'matrix': 5, 'display': {'font': 'x'}}, 'matrix must be a JSON object', 'order-matrix-before-display'),
]

DURATIONS = [
    case(display(**{key: bad}), f'display.{key} {DURATION_TEXT}', f'{key}-{label}')
    for key in ('duration', 'overview_duration', 'last_workout_duration', 'logo_duration',
                'last_workout_detail_interval')
    for label, bad in (('negative', -1), ('bool', True), ('text', '4'), ('nan', math.nan))
    # 0 is not an error here: retire_zero_times turns it into a switch before the check.
]

DISPLAY_SCALARS = [
    case(display(per_workout_duration=-1), 'display.per_workout_duration must be a non-negative number',
         'per-workout-duration-negative'),
    case(display(per_workout_duration='x'), 'display.per_workout_duration must be a non-negative number',
         'per-workout-duration-text'),
    case(display(per_workout_duration=math.inf), 'display.per_workout_duration must be a non-negative number',
         'per-workout-duration-infinite'),
    case(display(show_logo='yes'), 'display.show_logo must be true or false', 'show-logo'),
    case(display(show_logo=1), 'display.show_logo must be true or false', 'show-logo-int'),
    *[case(display(**{key: bad}), f'display.{key} must be a positive integer', f'{key}-{label}')
      for key in ('refresh_interval', 'history_batch_size', 'recent_fetch_size', 'performance_cache_size')
      for label, bad in (('zero', 0), ('bool', True), ('float', 1.5), ('text', '5'))],
    case(display(font='comic-sans'), 'unsupported display.font: comic-sans', 'font-unknown'),
    case(display(font=5), 'unsupported display.font: 5', 'font-not-text'),
    case(display(color='plaid'), 'unsupported display.color: plaid', 'color-unknown'),
    case(display(color=None), 'unsupported display.color: None', 'color-null'),
    case(display(timezone='Mars/Olympus'), 'invalid display.timezone', 'timezone-unknown'),
    case(display(timezone=5), 'invalid display.timezone', 'timezone-not-text'),
    case(display(timezone='../etc'), 'invalid display.timezone', 'timezone-path-like'),
    *[case(display(**{key: 7}), f'display.{key} must be a string', f'display-{key}-not-text')
      for key in ('username', 'logo_path', 'cache_path', 'log_path')],
    case(display(rotation='username'), ROTATION_TEXT, 'rotation-string'),
    case(display(rotation=None), ROTATION_TEXT, 'rotation-null'),
    case(display(rotation=['username', 5]), ROTATION_TEXT, 'rotation-non-text-item'),
    case(display(rotation=['username', 'username']), ROTATION_TEXT, 'rotation-duplicate'),
    case(display(rotation=['karaoke']), ROTATION_TEXT, 'rotation-unknown-screen'),
    case(display(screen_durations=None), 'display.screen_durations contains an unsupported screen name',
         'screen-durations-null'),
    case(display(screen_durations=[]), 'display.screen_durations contains an unsupported screen name',
         'screen-durations-list'),
    case(display(screen_durations={'karaoke': 5}), 'display.screen_durations contains an unsupported screen name',
         'screen-durations-unknown-screen'),
    case(display(screen_durations={'total_workouts': 5}),
         'display.screen_durations contains an unsupported screen name', 'screen-durations-total-workouts'),
    *[case(display(screen_durations={'username': bad}),
           'display.screen_durations values must be numbers above 0 (switch a screen off to hide it)',
           f'screen-durations-{label}')
      for label, bad in (('negative', -1), ('bool', True), ('text', '5'), ('nan', math.nan))],
    case(display(streak_reminder_day=7), REMINDER_TEXT, 'streak-reminder-day-high'),
    case(display(streak_reminder_day=-1), REMINDER_TEXT, 'streak-reminder-day-low'),
    case(display(streak_reminder_day=True), REMINDER_TEXT, 'streak-reminder-day-bool'),
    case(display(streak_reminder_day='mon'), REMINDER_TEXT, 'streak-reminder-day-text'),
    case(display(milestone_step=-5), 'display.milestone_step must be a non-negative integer',
         'milestone-step-negative'),
    case(display(milestone_step=True), 'display.milestone_step must be a non-negative integer',
         'milestone-step-bool'),
    case(display(milestone_step=None), 'display.milestone_step must be a non-negative integer',
         'milestone-step-null'),
    case(display(pr_max_age_days=0), PR_AGE_TEXT, 'pr-max-age-zero'),
    case(display(pr_max_age_days=True), PR_AGE_TEXT, 'pr-max-age-bool'),
    case(display(pr_max_age_days=2.5), PR_AGE_TEXT, 'pr-max-age-float'),
    case(display(workout_insights='yes'), 'display.workout_insights must be true or false', 'workout-insights'),
    case(display(workout_insights=None), 'display.workout_insights must be true or false', 'workout-insights-null'),
    *[case(display(**{key: bad}), f'display.{key} must be a whole number of at least 1', f'{key}-{label}')
      for key in ('milestone_within', 'milestone_pages')
      for label, bad in (('zero', 0), ('bool', True), ('float', 2.5), ('null', None))],
    case(display(next_class_takeover_minutes=-1), TAKEOVER_TEXT, 'takeover-negative'),
    case(display(next_class_takeover_minutes=11), TAKEOVER_TEXT, 'takeover-too-long'),
    case(display(next_class_takeover_minutes=True), TAKEOVER_TEXT, 'takeover-bool'),
    case(display(next_class_takeover_minutes=None), TAKEOVER_TEXT, 'takeover-null'),
]

BRIGHTNESS_SCHEDULE = [
    case(display(brightness_schedule=5), BRIGHTNESS_KEYS, 'brightness-not-a-dict'),
    case(display(brightness_schedule={'day': 80}), BRIGHTNESS_KEYS, 'brightness-missing-keys'),
    case(display(brightness_schedule={**BRIGHTNESS, 'extra': 1}), BRIGHTNESS_KEYS, 'brightness-extra-key'),
    case(display(brightness_schedule={**BRIGHTNESS, 'day': 0}), 'brightness day must be from 1 to 100',
         'brightness-day-low'),
    case(display(brightness_schedule={**BRIGHTNESS, 'day': True}), 'brightness day must be from 1 to 100',
         'brightness-day-bool'),
    case(display(brightness_schedule={**BRIGHTNESS, 'day': 50.5}), 'brightness day must be from 1 to 100',
         'brightness-day-float'),
    case(display(brightness_schedule={**BRIGHTNESS, 'night': 101}), 'brightness night must be from 1 to 100',
         'brightness-night-high'),
    case(display(brightness_schedule={**BRIGHTNESS, 'day': 0, 'night': 0}), 'brightness day must be from 1 to 100',
         'brightness-day-before-night'),
    case(display(brightness_schedule={**BRIGHTNESS, 'day_start': '7am'}), 'brightness day_start must use HH:MM',
         'brightness-day-start-text'),
    case(display(brightness_schedule={**BRIGHTNESS, 'day_start': None}), 'brightness day_start must use HH:MM',
         'brightness-day-start-null'),
    case(display(brightness_schedule={**BRIGHTNESS, 'night_start': '25:00'}),
         'brightness night_start must use HH:MM', 'brightness-night-start-bad-hour'),
    case(display(brightness_schedule={**BRIGHTNESS, 'night': 0, 'day_start': 'x'}),
         'brightness night must be from 1 to 100', 'brightness-numbers-before-times'),
]

REFRESH_SCHEDULE = [
    case(display(refresh_schedule=5), REFRESH_KEYS, 'refresh-not-a-dict'),
    case(display(refresh_schedule={'quiet_start': '23:00'}), REFRESH_KEYS, 'refresh-missing-keys'),
    case(display(refresh_schedule={**REFRESH, 'color': 'red'}),
         'display.refresh_schedule has unsupported keys', 'refresh-unsupported-key'),
    case(display(refresh_schedule={**REFRESH, 'quiet_start': '11pm'}), 'refresh_schedule quiet_start must use HH:MM',
         'refresh-quiet-start-text'),
    case(display(refresh_schedule={**REFRESH, 'quiet_end': None}), 'refresh_schedule quiet_end must use HH:MM',
         'refresh-quiet-end-null'),
    case(display(refresh_schedule={**REFRESH, 'quiet_start': 'x', 'quiet_end': 'y'}),
         'refresh_schedule quiet_start must use HH:MM', 'refresh-start-before-end'),
    case(display(refresh_schedule={**REFRESH, 'quiet_interval': 0}),
         'refresh_schedule.quiet_interval must be a positive integer', 'refresh-interval-zero'),
    case(display(refresh_schedule={**REFRESH, 'quiet_interval': True}),
         'refresh_schedule.quiet_interval must be a positive integer', 'refresh-interval-bool'),
    case(display(refresh_schedule={**REFRESH, 'quiet_interval': 60.5}),
         'refresh_schedule.quiet_interval must be a positive integer', 'refresh-interval-float'),
    case(display(refresh_schedule={**REFRESH, 'timezone': 5}), 'refresh_schedule.timezone must be a string',
         'refresh-timezone-not-text'),
    case(display(refresh_schedule={**REFRESH, 'timezone': 'Mars/Olympus'}), 'invalid refresh_schedule.timezone',
         'refresh-timezone-unknown'),
    case(display(refresh_schedule={**REFRESH, 'timezone': '../etc'}), 'invalid refresh_schedule.timezone',
         'refresh-timezone-path-like'),
    case(display(refresh_schedule={**REFRESH, 'timezone': ''}), 'invalid refresh_schedule.timezone',
         'refresh-timezone-empty'),
    case(display(refresh_schedule={**REFRESH, 'color': 'red', 'quiet_start': 'x'}),
         'display.refresh_schedule has unsupported keys', 'refresh-unsupported-before-times'),
    case(display(refresh_schedule={**REFRESH, 'quiet_end': 'y', 'quiet_interval': 0}),
         'refresh_schedule quiet_end must use HH:MM', 'refresh-times-before-interval'),
    case(display(refresh_schedule={**REFRESH, 'quiet_interval': 0, 'timezone': 5}),
         'refresh_schedule.quiet_interval must be a positive integer', 'refresh-interval-before-timezone'),
]

# Several faults at once: the first check in validate_config's order wins.
ORDER = [
    case({'users': [{'name': ' '}], 'display': {'font': 'x'}}, 'users[0] requires a name string',
         'order-users-before-display'),
    case({'matrix': {'rows': 48}, 'display': {'duration': -1}}, 'matrix.rows must be 32 or 64',
         'order-matrix-before-durations'),
    case(display(duration=-1, overview_duration=-1), f'display.duration {DURATION_TEXT}',
         'order-duration-before-overview'),
    case(display(overview_duration=-1, last_workout_duration=-1), f'display.overview_duration {DURATION_TEXT}',
         'order-overview-before-last-workout'),
    case(display(last_workout_detail_interval=-1, per_workout_duration=-1),
         f'display.last_workout_detail_interval {DURATION_TEXT}', 'order-durations-before-per-workout'),
    case(display(per_workout_duration=-1, show_logo='x'),
         'display.per_workout_duration must be a non-negative number', 'order-per-workout-before-show-logo'),
    case(display(show_logo='x', refresh_interval=0), 'display.show_logo must be true or false',
         'order-show-logo-before-integers'),
    case(display(refresh_interval=0, history_batch_size=0), 'display.refresh_interval must be a positive integer',
         'order-integers-in-order'),
    case(display(performance_cache_size=0, font='x'), 'display.performance_cache_size must be a positive integer',
         'order-integers-before-font'),
    case(display(font='x', color='x'), 'unsupported display.font: x', 'order-font-before-color'),
    case(display(color='x', timezone='x'), 'unsupported display.color: x', 'order-color-before-timezone'),
    case(display(timezone='x', username=5), 'invalid display.timezone', 'order-timezone-before-strings'),
    case(display(username=5, logo_path=5), 'display.username must be a string', 'order-strings-in-order'),
    case(display(log_path=5, rotation=['x']), 'display.log_path must be a string', 'order-strings-before-rotation'),
    case(display(rotation=['x'], screen_durations={'x': 1}), ROTATION_TEXT, 'order-rotation-before-durations'),
    case(display(screen_durations={'x': 1}, weekly_goals=None),
         'display.screen_durations contains an unsupported screen name', 'order-durations-before-goals'),
    case(display(weekly_goals=None, milestones=None), f'display.weekly_goals {GOALS_KEYS}',
         'order-goals-before-milestones-display'),
    case(display(milestones=None, journey=None), 'display.milestones must contain positive integers',
         'order-milestones-before-journey-display'),
    case(display(journey=None, streak_reminder_day=9), 'display.journey needs from, to and miles',
         'order-journey-before-reminder'),
    case(display(streak_reminder_day=9, milestone_step=-1), REMINDER_TEXT, 'order-reminder-before-step'),
    case(display(milestone_step=-1, pr_max_age_days=0), 'display.milestone_step must be a non-negative integer',
         'order-step-before-pr-age'),
    case(display(pr_max_age_days=0, workout_insights=1), PR_AGE_TEXT, 'order-pr-age-before-insights'),
    case(display(workout_insights=1, milestone_within=0), 'display.workout_insights must be true or false',
         'order-insights-before-within'),
    case(display(milestone_within=0, milestone_pages=0), 'display.milestone_within must be a whole number of at least 1',
         'order-within-before-pages'),
    case(display(milestone_pages=0, next_class_takeover_minutes=-1),
         'display.milestone_pages must be a whole number of at least 1', 'order-pages-before-takeover'),
    case(display(next_class_takeover_minutes=-1, brightness_schedule=5), TAKEOVER_TEXT,
         'order-takeover-before-brightness'),
    case(display(brightness_schedule=5, refresh_schedule=5), BRIGHTNESS_KEYS, 'order-brightness-before-refresh'),
]

INVALID = (STRUCTURE + USERS + WEEKLY_GOALS + MILESTONES + JOURNEY + MATRIX + DURATIONS + DISPLAY_SCALARS
           + BRIGHTNESS_SCHEDULE + REFRESH_SCHEDULE + ORDER)


@pytest.mark.parametrize('config,message', INVALID)
def test_invalid_config_gives_exactly_this_message(config, message):
    assert message_of(config) == message


def test_the_message_starts_with_the_path_it_was_given():
    with pytest.raises(ValueError) as caught:
        validate_config({'matrix': 5}, '/etc/peloton-led/config.json')
    assert str(caught.value) == '/etc/peloton-led/config.json: matrix must be a JSON object'


def test_a_null_token_path_crashes_instead_of_naming_the_problem():
    # Pinned as-is (reported in the code health notes, not fixed): null passes the "is not None" guard,
    # then the default-path lookup calls .strip() on None.
    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'strip'"):
        validate_config({'users': [{'name': 'Joel', 'token_path': None}]}, PATH)


# Valid configs: no error, and the returned config is exactly what the display and settings page read.

def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def roundtrip(value):
    return json.loads(json.dumps(value))


@pytest.mark.parametrize('example,fixture', [
    ('config.json-example', 'config.json-example.checked.json'),
    ('config.dual-users-example.json', 'config.dual-users-example.checked.json'),
    ('packaging/config.pi.json', 'config.pi.checked.json'),
])
def test_shipped_configs_validate_to_the_same_result(example, fixture):
    config = json.loads((ROOT / example).read_text(encoding='utf-8'))
    assert roundtrip(validate_config(config, PATH)) == load_fixture(fixture)


FULL_CONFIG = {
    'debug': True,
    'users': [
        {'name': 'Joel', 'token_path': 'cookies-joel.txt', 'cache_path': 'joel-cache.json',
         'log_path': 'joel-log.json', 'username': 'JoelC',
         'email_env': 'PELOTON_EMAIL_ONE', 'password_env': 'PELOTON_PASSWORD_ONE',
         'weekly_goals': {'workouts': 5, 'minutes': 120, 'active_days': 7},
         'milestones': [500, 100, 250, 100],
         'journey': {'from': ' Columbus ', 'to': ' Disney World ', 'miles': 880.5,
                     'disciplines': ['Cycling', 'Run'], 'start_date': ' 2026-01-05 '}},
        {'name': 'Jen', 'token_path': 'cookies-jen.txt', 'cache_path': 'jen-cache.json', 'log_path': 'jen-log.json'},
    ],
    'matrix': {'rows': 32, 'cols': 64, 'chain': 2, 'parallel': 3, 'pwm_bits': 8, 'brightness': 60,
               'gpio_mapping': 'adafruit-hat-pwm', 'scan_mode': 0, 'pwm_lsb_nanoseconds': 200,
               'show_refresh': True, 'slowdown_gpio': 2, 'no_hardware_pulse': True, 'rgb_sequence': 'rbg',
               'pixel_mapper': 'U-mapper', 'row_addr_type': 2, 'multiplexing': 1, 'limit_refresh': 120,
               'pwm_dither_bits': 1},
    'display': {
        'username': 'Peloton Member', 'logo_path': 'logo.png', 'cache_path': 'cache.json', 'log_path': 'log.json',
        'font': 'ride', 'color': 'gold', 'timezone': 'America/New_York',
        'duration': 5.5, 'overview_duration': 3, 'last_workout_duration': 20, 'logo_duration': 2.5,
        'last_workout_detail_interval': 3, 'per_workout_duration': 0, 'show_logo': False,
        'refresh_interval': 120, 'history_batch_size': 50, 'recent_fetch_size': 10, 'performance_cache_size': 8,
        'rotation': ['goals', 'username', 'next_class'],
        'screen_durations': {'username': 9, 'goals': 4.5},
        'weekly_goals': {'workouts': 4, 'minutes': 90, 'active_days': 3},
        'milestones': [300, 100, 100],
        'journey': {'from': 'A', 'to': 'B', 'miles': 12, 'disciplines': ['Walking'], 'start_date': '2026-02-01'},
        'streak_reminder_day': 6, 'milestone_step': 0, 'milestone_within': 2, 'milestone_pages': 1,
        'pr_max_age_days': 30, 'next_class_takeover_minutes': 10, 'workout_insights': True,
        'brightness_schedule': BRIGHTNESS,
        'refresh_schedule': {**REFRESH, 'timezone': 'America/Chicago'},
        'history_days': 90,
    },
}


def test_a_config_with_every_optional_section_filled_validates_to_this_result():
    checked = validate_config(copy.deepcopy(FULL_CONFIG), PATH)
    assert roundtrip(checked) == load_fixture('full.checked.json')
    # What the checks normalize, spelled out: names trimmed, milestones sorted and de-duplicated, the legacy
    # font and a lower-case RGB order rewritten, the date written back as ISO.
    assert checked['users'][0]['milestones'] == [100, 250, 500]
    assert checked['users'][0]['journey']['from'] == 'Columbus'
    assert checked['users'][0]['journey']['start_date'] == '2026-01-05'
    assert checked['display']['milestones'] == [100, 300]
    assert checked['display']['font'] == 'discipline'
    assert checked['matrix']['rgb_sequence'] == 'RBG'


def test_checking_an_already_checked_config_changes_nothing():
    once = validate_config(copy.deepcopy(FULL_CONFIG), PATH)
    assert validate_config(copy.deepcopy(once), PATH) == once


@pytest.mark.parametrize('config', [{}, {'display': {}}, {'matrix': None}, {'users': [{'name': 'A'}]}])
def test_empty_sections_take_the_defaults(config):
    checked = validate_config(copy.deepcopy(config), PATH)
    assert checked['matrix']['rows'] == 64 and checked['display']['rotation'][0] == 'latest_workouts'
    assert checked['display']['journey'] == {'from': 'Columbus', 'to': 'Disney World', 'miles': 880,
                                             'disciplines': None, 'start_date': None}


@pytest.mark.parametrize('journey,expected', [
    ({'from': 'A', 'to': 'B', 'miles': 3}, {'from': 'A', 'to': 'B', 'miles': 3, 'disciplines': None,
                                          'start_date': None}),
    ({'from': ' A ', 'to': ' B ', 'miles': 2.5, 'start_date': ' 2026-03-04 ', 'extra': 'kept'},
     {'from': 'A', 'to': 'B', 'miles': 2.5, 'disciplines': None, 'start_date': '2026-03-04', 'extra': 'kept'}),
])
def test_journey_is_normalized(journey, expected):
    assert validate_config(display(journey=journey), PATH)['display']['journey'] == expected


def test_a_discipline_with_no_distance_warns_but_is_accepted(caplog):
    journey = {**GOOD_JOURNEY, 'disciplines': ['Cycling', 'Yoga', 'Strength']}
    with caplog.at_level(logging.WARNING, logger='peloton-led.config'):
        checked = validate_config(display(journey=journey), PATH)
    assert checked['display']['journey']['disciplines'] == ['Cycling', 'Yoga', 'Strength']
    distance = ('Cycling, Bike Bootcamp, Running, Outdoor Run, Tread Bootcamp, Walking, Outdoor Walk, '
                'Rowing, Row Bootcamp')
    tail = f'has no distance and adds no miles; distance comes from {distance}'
    assert [record.getMessage() for record in caplog.records] == [
        f"config.json: display.journey.disciplines: 'Yoga' {tail}",
        f"config.json: display.journey.disciplines: 'Strength' {tail}",
    ]


def test_milestones_come_back_sorted_and_unique_for_a_rider_and_the_display():
    config = {'users': [{'name': 'A', 'milestones': [9, 3, 9]}], 'display': {'milestones': [5, 1, 5]}}
    checked = validate_config(config, PATH)
    assert checked['users'][0]['milestones'] == [3, 9] and checked['display']['milestones'] == [1, 5]


def test_the_matrix_keeps_its_defaults_and_overrides():
    checked = validate_config({'matrix': {'rows': 32, 'brightness': 40}}, PATH)['matrix']
    assert checked['rows'] == 32 and checked['brightness'] == 40 and checked['cols'] == 64
    assert checked['gpio_mapping'] is None and checked['rgb_sequence'] == 'RGB'


def test_zero_times_become_switches_with_a_warning(caplog):
    config = display(logo_duration=0, last_workout_detail_interval=0,
                     rotation=['username', 'goals'], screen_durations={'goals': 0, 'username': 6})
    with caplog.at_level(logging.WARNING, logger='peloton-led.config'):
        checked = validate_config(config, PATH)['display']
    assert checked['show_logo'] is False and checked['logo_duration'] == 5
    assert checked['rotation'] == ['username'] and checked['screen_durations'] == {'username': 6}
    assert [record.getMessage() for record in caplog.records] == [
        'config.json: a time of 0 now means switched off (logo_duration 0 is now show_logo false; '
        'last_workout_detail_interval 0 removed; screen_durations.goals 0 removed; switched off: goals); '
        'saving the settings page writes it that way']


def test_retired_settings_warn_with_their_names(caplog):
    with caplog.at_level(logging.WARNING, logger='peloton-led.config'):
        validate_config(display(history_limit=5, history_days=9), PATH)
    assert [record.getMessage() for record in caplog.records] == [
        'config.json: display.history_days, display.history_limit no longer do anything '
        '(the workout log replaced them); they can be removed']


@pytest.mark.parametrize('tz', ['America/New_York', 'UTC', '', None])
def test_valid_and_empty_timezones_pass(tz):
    assert validate_config(display(timezone=tz), PATH)['display']['timezone'] == tz


@pytest.mark.parametrize('key,value', [
    ('streak_reminder_day', None), ('pr_max_age_days', None), ('next_class_takeover_minutes', 0),
    ('next_class_takeover_minutes', 10), ('milestone_step', 0), ('per_workout_duration', 0),
    ('streak_reminder_day', 0), ('streak_reminder_day', 6), ('pr_max_age_days', 1),
])
def test_boundary_values_that_are_allowed(key, value):
    assert validate_config(display(**{key: value}), PATH)['display'][key] == value


@pytest.mark.parametrize('key,value', [
    ('cols', 1), ('chain', 1), ('parallel', 3), ('pwm_bits', 11), ('brightness', 1), ('brightness', 100),
    ('scan_mode', 0), ('scan_mode', 1), ('row_addr_type', 3), ('multiplexing', 0), ('slowdown_gpio', 0),
    ('slowdown_gpio', 4), ('slowdown_gpio', None), ('gpio_mapping', 'regular'), ('gpio_mapping', 'adafruit-hat'),
    ('rows', 32), ('show_refresh', True), ('no_hardware_pulse', False), ('pixel_mapper', ''),
])
def test_matrix_boundary_values_that_are_allowed(key, value):
    assert validate_config({'matrix': {key: value}}, PATH)['matrix'][key] == value


def test_a_refresh_schedule_without_a_timezone_is_valid():
    checked = validate_config(display(refresh_schedule=dict(REFRESH)), PATH)['display']['refresh_schedule']
    assert checked == REFRESH
