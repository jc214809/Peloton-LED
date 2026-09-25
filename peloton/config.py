"""Validate user configuration before initializing hardware or making requests."""
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .journey import DEFAULT_JOURNEY
from .selection import normalize_discipline

DEFAULTS = {'font': 'stats', 'color': 'white', 'duration': 4, 'overview_duration': 4,
            'per_workout_duration': 4, 'last_workout_duration': 30, 'logo_duration': 3,
            'last_workout_detail_interval': 4.0,
            'refresh_interval': 300, 'history_days': 90, 'history_limit': 200,
            'history_page_size': 50, 'history_max_pages': 10,
            'instructor_tally_max_pages': 200,
            'performance_cache_size': 32,
            'rotation': ['latest_workouts', 'username', 'streaks', 'versus', 'total_workouts',
                         'next_milestone', 'lifetime', 'journey',
                         'milestones', 'goals'],
            'screen_durations': {},
            'weekly_goals': {'workouts': 0, 'minutes': 0},
            'milestones': [],
            'milestone_step': 100,
            'journey': DEFAULT_JOURNEY,
            'brightness_schedule': None,
            'compact_workout_pages': False}

ROTATION_SECTIONS = {'latest_workouts', 'username', 'streaks', 'versus', 'total_workouts',
                     'next_milestone', 'lifetime', 'journey', 'milestones', 'goals'}
DURATION_SECTIONS = {'latest_workouts', 'username', 'streaks', 'versus', 'next_milestone',
                     'lifetime', 'journey', 'milestones', 'goals'}


def user_slug(name):
    """Filesystem-safe slug derived from a user's display name, for default file paths."""
    slug = re.sub(r'[^a-z0-9]+', '-', name.strip().lower()).strip('-')
    return slug or 'user'


def default_token_path(name):
    return f'cookies-{user_slug(name)}.txt'


def load_dotenv(path='.env'):
    """Populate os.environ from a local .env file, for local development only.

    Real environment variables always win; a KEY already set is left untouched.
    Silently does nothing if the file is absent, since it's optional everywhere
    except local dev (Pi installs use /etc/peloton-led/auth.env instead).
    """
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _validate_weekly_goals(path, goals, prefix):
    if not isinstance(goals, dict) or not set(goals) <= {'workouts', 'minutes'}:
        raise ValueError(f'{path}: {prefix}weekly_goals must contain workouts and/or minutes')
    for value in goals.values():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f'{path}: {prefix}weekly_goals values must be non-negative integers')


def _validate_milestones(path, milestones, prefix):
    if (not isinstance(milestones, list) or any(isinstance(value, bool) or
            not isinstance(value, int) or value <= 0 for value in milestones)):
        raise ValueError(f'{path}: {prefix}milestones must contain positive integers')
    return sorted(set(milestones))


def _validate_journey(path, journey, prefix):
    """Route for the distance journey: from/to names, miles, disciplines."""
    where = f'{path}: {prefix}journey'
    if not isinstance(journey, dict) or not {'from', 'to', 'miles', 'disciplines'} <= set(journey):
        raise ValueError(f'{where} needs from, to, miles and disciplines')
    for key in ('from', 'to'):
        if not isinstance(journey[key], str) or not journey[key].strip():
            raise ValueError(f'{where}.{key} must be a non-empty string')
    miles = journey['miles']
    if isinstance(miles, bool) or not isinstance(miles, (int, float)) or not math.isfinite(miles) or miles <= 0:
        raise ValueError(f'{where}.miles must be a positive number')
    disciplines = journey['disciplines']
    if (not isinstance(disciplines, list) or not disciplines
            or not all(isinstance(d, str) and normalize_discipline(d) for d in disciplines)):
        raise ValueError(f'{where}.disciplines must be a non-empty list of discipline names')
    return {**journey, 'from': journey['from'].strip(), 'to': journey['to'].strip()}


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
    if not isinstance(config, dict) or not isinstance(config.get('display', {}), dict):
        raise ValueError(f'{path}: config and display must be JSON objects')
    users = config.get('users')
    if users is not None:
        if not isinstance(users, list) or not users:
            raise ValueError(f'{path}: users must be a non-empty list')
        seen_names = set()
        seen_tokens = set()
        seen_caches = set()
        for index, user in enumerate(users):
            if not isinstance(user, dict):
                raise ValueError(f'{path}: users[{index}] must be an object')
            if not isinstance(user.get('name'), str) or not user['name'].strip():
                raise ValueError(f'{path}: users[{index}] requires a name string')
            if user.get('token_path') is not None and (
                    not isinstance(user['token_path'], str) or not user['token_path'].strip()):
                raise ValueError(f'{path}: users[{index}].token_path must be a non-empty string')
            name = user['name'].strip()
            token = user.get('token_path', '').strip() or default_token_path(name)
            if name.casefold() in seen_names or token in seen_tokens:
                raise ValueError(f'{path}: user names and token paths must be unique')
            seen_names.add(name.casefold())
            seen_tokens.add(token)
            for key in ('cache_path', 'username'):
                if user.get(key) is not None and not isinstance(user[key], str):
                    raise ValueError(f'{path}: users[{index}].{key} must be a string')
            cache = user.get('cache_path')
            if cache and cache in seen_caches:
                raise ValueError(f'{path}: user cache paths must be unique')
            if cache:
                seen_caches.add(cache)
            for key in ('email_env', 'password_env'):
                value = user.get(key)
                if value is not None and (not isinstance(value, str) or
                        re.fullmatch(r'[A-Z_][A-Z0-9_]*', value) is None):
                    raise ValueError(f'{path}: users[{index}].{key} must be an environment variable name')
            if 'weekly_goals' in user:
                _validate_weekly_goals(path, user['weekly_goals'], f'users[{index}].')
            if 'milestones' in user:
                user['milestones'] = _validate_milestones(path, user['milestones'], f'users[{index}].')
            if 'journey' in user:
                user['journey'] = _validate_journey(path, user['journey'], f'users[{index}].')
    display = {**DEFAULTS, **config.get('display', {})}
    for key in ('duration', 'overview_duration', 'per_workout_duration', 'last_workout_duration', 'logo_duration',
                'last_workout_detail_interval'):
        value = display[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f'{path}: display.{key} must be a non-negative number')
    for key in ('refresh_interval', 'history_days', 'history_limit', 'history_page_size',
                'history_max_pages', 'instructor_tally_max_pages', 'performance_cache_size'):
        value = display[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f'{path}: display.{key} must be a positive integer')
    if display['font'] not in ('discipline', 'info', 'titles', 'stats', 'countdown'):
        # Legacy names appeared in the original example config.
        if display['font'] in ('ride', 'park'):
            display['font'] = 'discipline'
        else:
            raise ValueError(f'{path}: unsupported display.font: {display["font"]}')
    if display['color'] not in ('red', 'disney_blue', 'white', 'down', 'gold'):
        raise ValueError(f'{path}: unsupported display.color: {display["color"]}')
    tz = display.get('timezone')
    if tz:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
            raise ValueError(f'{path}: invalid display.timezone') from exc
    for key in ('username', 'logo_path', 'cache_path'):
        if display.get(key) is not None and not isinstance(display[key], str):
            raise ValueError(f'{path}: display.{key} must be a string')
    rotation = display.get('rotation')
    if (not isinstance(rotation, list) or not all(isinstance(item, str) for item in rotation)
            or len(rotation) != len(set(rotation)) or not set(rotation) <= ROTATION_SECTIONS):
        raise ValueError(f'{path}: display.rotation must contain unique supported screen names')
    durations = display.get('screen_durations')
    if not isinstance(durations, dict) or not set(durations) <= DURATION_SECTIONS:
        raise ValueError(f'{path}: display.screen_durations contains an unsupported screen name')
    for value in durations.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f'{path}: display.screen_durations values must be non-negative numbers')
    _validate_weekly_goals(path, display.get('weekly_goals'), 'display.')
    display['milestones'] = _validate_milestones(path, display.get('milestones'), 'display.')
    display['journey'] = _validate_journey(path, display.get('journey'), 'display.')
    step = display.get('milestone_step')
    if isinstance(step, bool) or not isinstance(step, int) or step < 0:
        raise ValueError(f'{path}: display.milestone_step must be a non-negative integer')
    if not isinstance(display.get('compact_workout_pages'), bool):
        raise ValueError(f'{path}: display.compact_workout_pages must be true or false')
    schedule = display.get('brightness_schedule')
    if schedule is not None:
        required = {'day', 'night', 'day_start', 'night_start'}
        if not isinstance(schedule, dict) or set(schedule) != required:
            raise ValueError(f'{path}: display.brightness_schedule requires day, night, day_start, and night_start')
        for key in ('day', 'night'):
            if isinstance(schedule[key], bool) or not isinstance(schedule[key], int) or not 1 <= schedule[key] <= 100:
                raise ValueError(f'{path}: brightness {key} must be from 1 to 100')
        for key in ('day_start', 'night_start'):
            try:
                datetime.strptime(schedule[key], '%H:%M')
            except (TypeError, ValueError) as exc:
                raise ValueError(f'{path}: brightness {key} must use HH:MM') from exc
    config['display'] = display
    return config
