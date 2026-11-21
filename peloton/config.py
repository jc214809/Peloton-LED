"""Validate user configuration before initializing hardware or making requests."""
import json
import logging
import os
import re
from datetime import date
from pathlib import Path

from .feeds.booked_classes import TAKEOVER_MAX_MINUTES
from .config_rules import (Rule, int_in, is_bool, is_env_name, is_iso_date, is_nonblank_str, is_str, is_time_of_day,
                           is_timezone, non_negative_number, or_none, positive_number, run, whole_number)
from .stats.journey import DEFAULT_JOURNEY, DISTANCE_DISCIPLINES
from .screen_times import retire_zero_times
from .selection import normalize_discipline

logger = logging.getLogger('peloton-led.config')

DEFAULTS = {'font': 'stats', 'color': 'white', 'duration': 4, 'overview_duration': 4,
            'per_workout_duration': 4, 'last_workout_duration': 30, 'logo_duration': 5, 'show_logo': True,
            'last_workout_detail_interval': 4.0,
            'refresh_interval': 300, 'history_batch_size': 100, 'recent_fetch_size': 20,
            'performance_cache_size': 32,
            'rotation': ['latest_workouts', 'username', 'streaks', 'versus', 'total_workouts',
                         'next_milestone', 'lifetime', 'journey',
                         'heatmap', 'milestones', 'goals', 'challenges', 'next_class', 'club'],
            'screen_durations': {},
            'weekly_goals': {'workouts': 0, 'minutes': 0},
            'milestones': [],
            'milestone_step': 100,
            # The Next Milestone page counts down to a target this close, the total's or a discipline's
            # (25, 50, 100, then every 100), at most this many pages.
            'milestone_within': 5,
            'milestone_pages': 3,
            # A PR older than this many days isn't celebrated; None celebrates any not yet shown.
            'pr_max_age_days': None,
            # The Next class page takes over the panel this many minutes before a booked class starts
            # (0 is off, up to TAKEOVER_MAX_MINUTES); only with next_class in rotation.
            'next_class_takeover_minutes': 5,
            # Workout compare: the latest-workout page ends with one insight against similar earlier workouts.
            'workout_insights': False,
            'streak_reminder_day': 5,
            'journey': DEFAULT_JOURNEY,
            'brightness_schedule': None,
            'refresh_schedule': None}

# Panel/driver settings, one per --led-* flag (flag name minus "led-"). Flags win.
MATRIX_DEFAULTS = {'rows': 64, 'cols': 64, 'chain': 1, 'parallel': 1, 'pwm_bits': 11,
                   'brightness': 100, 'gpio_mapping': None, 'scan_mode': 1,
                   'pwm_lsb_nanoseconds': 130, 'show_refresh': False, 'slowdown_gpio': None,
                   'no_hardware_pulse': False, 'rgb_sequence': 'RGB', 'pixel_mapper': '',
                   'row_addr_type': 0, 'multiplexing': 0, 'limit_refresh': 0, 'pwm_dither_bits': 0}
GPIO_MAPPINGS = ('regular', 'adafruit-hat', 'adafruit-hat-pwm')

# Settings the workout log replaced (docs/WORKOUT-LOG-PLAN.md). Still accepted
# so older config files load, but they no longer do anything.
RETIRED_DISPLAY_KEYS = ('history_days', 'history_limit', 'history_page_size',
                        'history_max_pages', 'instructor_tally_max_pages')

ROTATION_SECTIONS = {'latest_workouts', 'username', 'streaks', 'versus', 'total_workouts',
                     'next_milestone', 'lifetime', 'journey', 'heatmap',
                     'milestones', 'goals', 'challenges', 'next_class', 'club'}
DURATION_SECTIONS = {'latest_workouts', 'username', 'streaks', 'versus', 'next_milestone',
                     'lifetime', 'journey', 'heatmap', 'milestones', 'goals', 'challenges',
                     'next_class', 'club'}


def user_slug(name):
    """Filesystem-safe slug derived from a user's display name, for default file paths."""
    slug = re.sub(r'[^a-z0-9]+', '-', name.strip().lower()).strip('-')
    return slug or 'user'


def default_token_path(name):
    return f'cookies-{user_slug(name)}.txt'


def user_token_path(user, config_dir):
    """A rider's token file: token_path, else cookies-<name>.txt, relative to the config's folder."""
    path = Path(user.get('token_path') or default_token_path(user['name'])).expanduser()
    return path if path.is_absolute() else Path(config_dir) / path


def user_cache_path(user, config_dir, token_path=None):
    """A rider's dashboard cache: cache_path (relative to the config's folder), else
    <token stem>-dashboard-cache.json beside their token. The workout log and the workout-compare
    row store are named after it."""
    if user.get('cache_path'):
        path = Path(user['cache_path']).expanduser()
        return path if path.is_absolute() else Path(config_dir) / path
    token_path = Path(token_path) if token_path else user_token_path(user, config_dir)
    return token_path.with_name(f'{token_path.stem}-dashboard-cache.json')


def renewal_failed_path(token_path):
    """cookies-joel.txt -> cookies-joel.renewal-failed: written by the token
    renewal job when only a fresh login can help, read by the display."""
    token_path = Path(token_path)
    return token_path.with_name(f'{token_path.stem}.renewal-failed')


def load_dotenv(path='.env'):
    """Populate os.environ from a local .env file, for local development only.

    Real environment variables always win; a KEY already set is left untouched.
    Silently does nothing if the file is absent, since it's optional everywhere
    except local dev (Pi installs use /etc/peloton-led/auth.env instead).
    """
    path = Path(path)
    try:
        if not path.is_file():
            return
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        # E.g. run as the service account from a directory it can't read.
        logger.warning('Ignoring %s: %s', path, exc)
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


WEEKLY_GOAL_KEYS = ('workouts', 'minutes', 'active_days')
FONTS = ('discipline', 'info', 'titles', 'stats', 'countdown')
COLORS = ('red', 'disney_blue', 'white', 'down', 'gold')
LEGACY_FONTS = ('ride', 'park')  # in the original example config; read as 'discipline'
JOURNEY_REQUIRED_KEYS = {'from', 'to', 'miles'}
BRIGHTNESS_SCHEDULE_KEYS = {'day', 'night', 'day_start', 'night_start'}
REFRESH_SCHEDULE_KEYS = {'quiet_start', 'quiet_end', 'quiet_interval'}  # and an optional 'timezone'

def _is_rotation(value):
    return (isinstance(value, list) and all(isinstance(item, str) for item in value)
            and len(value) == len(set(value)) and set(value) <= ROTATION_SECTIONS)


def _names_only_screens(value):
    return isinstance(value, dict) and set(value) <= DURATION_SECTIONS


def _all_durations_positive(value):
    return all(positive_number(seconds) for seconds in value.values())


def _names_only_goal_keys(value):
    return isinstance(value, dict) and set(value) <= set(WEEKLY_GOAL_KEYS)


def _all_goals_whole(value):
    return all(int_in(goal, 0) for goal in value.values())


def _active_days_at_most_7(value):
    return value.get('active_days', 0) <= 7


def _all_positive_ints(value):
    return isinstance(value, list) and all(int_in(item, 1) for item in value)


def _has_journey_keys(value):
    return isinstance(value, dict) and JOURNEY_REQUIRED_KEYS <= set(value)


def _is_discipline_list(value):
    return (isinstance(value, list) and bool(value)
            and all(isinstance(name, str) and normalize_discipline(name) for name in value))


def _is_brightness_schedule(value):
    return isinstance(value, dict) and set(value) == BRIGHTNESS_SCHEDULE_KEYS


def _is_refresh_schedule(value):
    return isinstance(value, dict) and REFRESH_SCHEDULE_KEYS <= set(value)


def _has_no_other_refresh_keys(value):
    return not set(value) - REFRESH_SCHEDULE_KEYS - {'timezone'}


def _is_rows(value):
    return value in (32, 64) and not isinstance(value, bool)


def _is_rgb_sequence(value):
    return isinstance(value, str) and sorted(value.upper()) == ['B', 'G', 'R']


# Row builders for the shapes the display table repeats.

def _display_duration(key):
    return Rule(key, positive_number, f'display.{key} must be a number above 0 (switch a screen off to hide it)')


def _display_positive_int(key):
    return Rule(key, whole_number(1), f'display.{key} must be a positive integer')


def _display_at_least(key, low):
    return Rule(key, whole_number(low), f'display.{key} must be a whole number of at least {low}')


def _display_string(key):
    return Rule(key, or_none(is_str), f'display.{key} must be a string')


def _matrix_whole_number(key, low, high=None):
    span = f'from {low} to {high}' if high is not None else f'at least {low}'
    return Rule(key, whole_number(low, high), f'matrix.{key} must be a whole number {span}')


# Steps that don't fit a row: cross-field rules, warnings, and values rewritten while checked.

def _normalize_milestones(path, section, prefix):
    section['milestones'] = sorted(set(section['milestones']))


def _migrate_legacy_font(path, display, prefix):
    if display['font'] in LEGACY_FONTS:
        display['font'] = 'discipline'


def _warn_retired_keys(path, display, prefix):
    retired = [key for key in RETIRED_DISPLAY_KEYS if key in display]
    if retired:
        logger.warning('%s: display.%s no longer do anything (the workout log replaced them); '
                       'they can be removed', path, ', display.'.join(retired))


def _warn_unknown_disciplines(path, journey, prefix):
    if journey.get('disciplines') is None:
        return
    known = {normalize_discipline(d) for d in DISTANCE_DISCIPLINES}
    for name in journey['disciplines']:
        if normalize_discipline(name) not in known:
            logger.warning('%s: %sjourney.disciplines: %r has no distance and adds no miles; distance comes from %s',
                           path, prefix, name, ', '.join(DISTANCE_DISCIPLINES))


def _require_user_name(path, user, prefix):
    if not is_nonblank_str(user.get('name')):
        raise ValueError(f'{path}: {prefix.rstrip(".")} requires a name string')


def _check_unique_identity(path, user, seen):
    name = user['name'].strip()
    token = user.get('token_path', '').strip() or default_token_path(name)
    if name.casefold() in seen['names'] or token in seen['tokens']:
        raise ValueError(f'{path}: user names and token paths must be unique')
    seen['names'].add(name.casefold())
    seen['tokens'].add(token)


def _check_unique_files(path, user, seen):
    for key in ('cache_path', 'log_path'):
        # Two riders sharing a cache or log would overwrite each other.
        value = user.get(key)
        if value and value in seen['files']:
            raise ValueError(f'{path}: user cache and log paths must be unique')
        if value:
            seen['files'].add(value)


def _check_brightness_schedule(path, display, prefix):
    run(_BRIGHTNESS_SCHEDULE_SHAPE, path, display, prefix)
    if display['brightness_schedule'] is not None:
        run(_BRIGHTNESS_SCHEDULE_RULES, path, display['brightness_schedule'])


def _check_refresh_schedule(path, display, prefix):
    run(_REFRESH_SCHEDULE_SHAPE, path, display, prefix)
    if display['refresh_schedule'] is not None:
        run(_REFRESH_SCHEDULE_RULES, path, display['refresh_schedule'])


def _validate_journey(path, section, prefix):
    """Route for the distance journey: from/to names, miles, disciplines. Rewrites section['journey']
    with the names trimmed and every optional key present."""
    run(_JOURNEY_SHAPE, path, section, prefix)
    journey = section['journey']
    run(_JOURNEY_RULES, path, journey, prefix)
    start = journey.get('start_date')
    section['journey'] = {**journey, 'from': journey['from'].strip(), 'to': journey['to'].strip(),
                          'disciplines': journey.get('disciplines'),
                          'start_date': None if start is None else date.fromisoformat(start.strip()).isoformat()}


# Every check validate_config makes is a row in one of these tables, in the order its error is
# reported (the first failing row wins). To validate a new config key, add one Rule row to its
# section's table: _DISPLAY_RULES for display.*, _MATRIX_RULES for matrix.*, _USER_*_RULES for each
# entry of users, and give it a default in DEFAULTS / MATRIX_DEFAULTS. Messages are word for word
# what the settings page shows and tests/test_config_validation_messages.py pins them.

_WEEKLY_GOALS_RULES = [
    Rule('weekly_goals', _names_only_goal_keys,
          '{prefix}weekly_goals must contain only workouts, minutes and active_days'),
    Rule('weekly_goals', _all_goals_whole, '{prefix}weekly_goals values must be non-negative integers'),
    Rule('weekly_goals', _active_days_at_most_7, '{prefix}weekly_goals.active_days can be at most 7'),
]

_MILESTONES_RULES = [
    Rule('milestones', _all_positive_ints, '{prefix}milestones must contain positive integers'),
    _normalize_milestones,
]

_JOURNEY_SHAPE = [Rule('journey', _has_journey_keys, '{prefix}journey needs from, to and miles')]

_JOURNEY_RULES = [
    Rule('from', is_nonblank_str, '{prefix}journey.from must be a non-empty string'),
    Rule('to', is_nonblank_str, '{prefix}journey.to must be a non-empty string'),
    Rule('miles', positive_number, '{prefix}journey.miles must be a positive number'),
    Rule('disciplines', or_none(_is_discipline_list),
          '{prefix}journey.disciplines must be a non-empty list of discipline names'),
    _warn_unknown_disciplines,
    Rule('start_date', or_none(is_iso_date), '{prefix}journey.start_date must be a YYYY-MM-DD date'),
]

_USER_IDENTITY_STEPS = [
    _require_user_name,
    Rule('token_path', or_none(is_nonblank_str), '{prefix}token_path must be a non-empty string'),
]

_USER_PATH_RULES = [
    Rule('cache_path', or_none(is_str), '{prefix}cache_path must be a string'),
    Rule('log_path', or_none(is_str), '{prefix}log_path must be a string'),
    Rule('username', or_none(is_str), '{prefix}username must be a string'),
]

_USER_ENV_RULES = [
    Rule('email_env', or_none(is_env_name), '{prefix}email_env must be an environment variable name'),
    Rule('password_env', or_none(is_env_name), '{prefix}password_env must be an environment variable name'),
]

# A key listed here is read as `matrix` merged over MATRIX_DEFAULTS, so it is always present.
_MATRIX_RULES = [
    Rule('rows', _is_rows, 'matrix.rows must be 32 or 64'),
    _matrix_whole_number('cols', 1),
    _matrix_whole_number('chain', 1),
    _matrix_whole_number('parallel', 1, 3),
    _matrix_whole_number('pwm_bits', 1, 11),
    _matrix_whole_number('brightness', 1, 100),
    _matrix_whole_number('scan_mode', 0, 1),
    _matrix_whole_number('pwm_lsb_nanoseconds', 1),
    _matrix_whole_number('row_addr_type', 0, 3),
    _matrix_whole_number('multiplexing', 0),
    _matrix_whole_number('limit_refresh', 0),
    _matrix_whole_number('pwm_dither_bits', 0),
    Rule('slowdown_gpio', or_none(whole_number(0, 4)),
          'matrix.slowdown_gpio must be a whole number from 0 to 4, or null'),
    Rule('gpio_mapping', or_none(lambda value: value in GPIO_MAPPINGS),
          f'matrix.gpio_mapping must be one of {", ".join(GPIO_MAPPINGS)}, or null'),
    Rule('show_refresh', is_bool, 'matrix.show_refresh must be true or false'),
    Rule('no_hardware_pulse', is_bool, 'matrix.no_hardware_pulse must be true or false'),
    Rule('rgb_sequence', _is_rgb_sequence, 'matrix.rgb_sequence must be an ordering of R, G and B, e.g. "RBG"'),
    Rule('pixel_mapper', is_str, 'matrix.pixel_mapper must be a string'),
]

_BRIGHTNESS_SCHEDULE_SHAPE = [
    Rule('brightness_schedule', or_none(_is_brightness_schedule),
          'display.brightness_schedule requires day, night, day_start, and night_start'),
]

# Rows for the schedule's own keys (the schedule is the section here, so no {prefix}).
_BRIGHTNESS_SCHEDULE_RULES = [
    Rule('day', whole_number(1, 100), 'brightness day must be from 1 to 100'),
    Rule('night', whole_number(1, 100), 'brightness night must be from 1 to 100'),
    Rule('day_start', is_time_of_day, 'brightness day_start must use HH:MM'),
    Rule('night_start', is_time_of_day, 'brightness night_start must use HH:MM'),
]

_REFRESH_SCHEDULE_SHAPE = [
    Rule('refresh_schedule', or_none(_is_refresh_schedule),
          'display.refresh_schedule requires quiet_start, quiet_end, and quiet_interval'),
    Rule('refresh_schedule', or_none(_has_no_other_refresh_keys),
          'display.refresh_schedule has unsupported keys'),
]

_REFRESH_SCHEDULE_RULES = [
    Rule('quiet_start', is_time_of_day, 'refresh_schedule quiet_start must use HH:MM'),
    Rule('quiet_end', is_time_of_day, 'refresh_schedule quiet_end must use HH:MM'),
    Rule('quiet_interval', whole_number(1), 'refresh_schedule.quiet_interval must be a positive integer'),
    Rule('timezone', or_none(is_str), 'refresh_schedule.timezone must be a string'),
    Rule('timezone', or_none(is_timezone), 'invalid refresh_schedule.timezone'),
]

# The display section, merged over DEFAULTS, so every key with a default is present. Warnings that
# fire between two rows stay between them so the log reads as it always did.
_DISPLAY_RULES = [
    _display_duration('duration'),
    _display_duration('overview_duration'),
    _display_duration('last_workout_duration'),
    _display_duration('logo_duration'),
    _display_duration('last_workout_detail_interval'),
    # per_workout_duration is no longer used; still accepted.
    Rule('per_workout_duration', non_negative_number, 'display.per_workout_duration must be a non-negative number'),
    Rule('show_logo', is_bool, 'display.show_logo must be true or false'),
    _display_positive_int('refresh_interval'),
    _display_positive_int('history_batch_size'),
    _display_positive_int('recent_fetch_size'),
    _display_positive_int('performance_cache_size'),
    _warn_retired_keys,
    _migrate_legacy_font,
    Rule('font', lambda value: value in FONTS, 'unsupported display.font: {value}'),
    Rule('color', lambda value: value in COLORS, 'unsupported display.color: {value}'),
    Rule('timezone', lambda value: not value or is_timezone(value), 'invalid display.timezone'),
    _display_string('username'),
    _display_string('logo_path'),
    _display_string('cache_path'),
    _display_string('log_path'),
    Rule('rotation', _is_rotation, 'display.rotation must contain unique supported screen names'),
    Rule('screen_durations', _names_only_screens, 'display.screen_durations contains an unsupported screen name'),
    Rule('screen_durations', _all_durations_positive,
          'display.screen_durations values must be numbers above 0 (switch a screen off to hide it)'),
    *_WEEKLY_GOALS_RULES,
    *_MILESTONES_RULES,
    _validate_journey,
    Rule('streak_reminder_day', or_none(whole_number(0, 6)),
          'display.streak_reminder_day must be 0 (Monday) to 6 (Sunday), or null'),
    Rule('milestone_step', whole_number(0), 'display.milestone_step must be a non-negative integer'),
    Rule('pr_max_age_days', or_none(whole_number(1)),
          'display.pr_max_age_days must be a whole number of days of at least 1, or null'),
    Rule('workout_insights', is_bool, 'display.workout_insights must be true or false'),
    _display_at_least('milestone_within', 1),
    _display_at_least('milestone_pages', 1),
    Rule('next_class_takeover_minutes', whole_number(0, TAKEOVER_MAX_MINUTES),
          'display.next_class_takeover_minutes must be a whole number of minutes '
          f'from 0 (off) to {TAKEOVER_MAX_MINUTES}'),
    _check_brightness_schedule,
    _check_refresh_schedule,
]


def _validate_user(path, user, prefix, seen):
    run(_USER_IDENTITY_STEPS, path, user, prefix)
    _check_unique_identity(path, user, seen)
    run(_USER_PATH_RULES, path, user, prefix)
    _check_unique_files(path, user, seen)
    run(_USER_ENV_RULES, path, user, prefix)
    if 'weekly_goals' in user:
        run(_WEEKLY_GOALS_RULES, path, user, prefix)
    if 'milestones' in user:
        run(_MILESTONES_RULES, path, user, prefix)
    if 'journey' in user:
        _validate_journey(path, user, prefix)


def _validate_users(path, users):
    if not isinstance(users, list) or not users:
        raise ValueError(f'{path}: users must be a non-empty list')
    seen = {'names': set(), 'tokens': set(), 'files': set()}
    for index, user in enumerate(users):
        if not isinstance(user, dict):
            raise ValueError(f'{path}: users[{index}] must be an object')
        _validate_user(path, user, f'users[{index}].', seen)


def _validate_matrix(path, matrix):
    """Optional top-level "matrix" section: LED panel and driver settings."""
    if matrix is None:
        matrix = {}
    if not isinstance(matrix, dict):
        raise ValueError(f'{path}: matrix must be a JSON object')
    unknown = set(matrix) - set(MATRIX_DEFAULTS)
    if unknown:
        raise ValueError(f'{path}: matrix has unsupported keys: {", ".join(sorted(unknown))}')
    merged = {**MATRIX_DEFAULTS, **matrix}
    run(_MATRIX_RULES, path, merged)
    merged['rgb_sequence'] = merged['rgb_sequence'].upper()
    return merged


def load_config(path='config', allow_missing=False):
    path = Path(path).with_suffix('.json')
    if not path.exists():
        if not allow_missing:
            raise ValueError(f'Config not found: {path}. Copy config.json-example to config.json.')
        config = {}
    else:
        try:
            config = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f'Could not read config {path}: {exc}') from exc
    return validate_config(config, path)


def validate_config(config, path='config.json'):
    """Check a parsed config and fill in display defaults; raises ValueError naming
    the first problem (prefixed with path). Changes config in place and returns it,
    so pass a copy to check one without changing it (the settings page does)."""
    if not isinstance(config, dict) or not isinstance(config.get('display', {}), dict):
        raise ValueError(f'{path}: config and display must be JSON objects')
    if config.get('users') is not None:
        _validate_users(path, config['users'])
    config['matrix'] = _validate_matrix(path, config.get('matrix'))
    # 0 seconds used to mean "don't show"; it's now the screen's switch (or show_logo).
    switched = retire_zero_times(config.get('display'), ROTATION_SECTIONS, DEFAULTS['rotation'])
    if switched:
        logger.warning('%s: a time of 0 now means switched off (%s); saving the settings page writes '
                       'it that way', path, '; '.join(switched))
    display = {**DEFAULTS, **config.get('display', {})}
    run(_DISPLAY_RULES, path, display, 'display.')
    config['display'] = display
    return config
