"""Each bad config.json produces a specific, readable error instead of a crash later."""
import json

import pytest

from peloton.config import load_config


def _load(tmp_path, config):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(config))
    return load_config(path)


@pytest.mark.parametrize('config,message', [
    ({'users': 'Joel'}, 'users must be a non-empty list'),
    ({'users': []}, 'users must be a non-empty list'),
    ({'users': ['Joel']}, r'users\[0\] must be an object'),
    ({'users': [{'name': ' '}]}, r'users\[0\] requires a name'),
    ({'users': [{'name': 'Joel', 'token_path': ''}]}, 'token_path must be a non-empty string'),
    ({'users': [{'name': 'Joel'}, {'name': 'joel'}]}, 'names and token paths must be unique'),
    ({'users': [{'name': 'A', 'token_path': 't.txt'}, {'name': 'B', 'token_path': 't.txt'}]},
     'names and token paths must be unique'),
    ({'users': [{'name': 'Joel', 'username': 5}]}, r'users\[0\].username must be a string'),
    ({'users': [{'name': 'A', 'cache_path': 'c.json'}, {'name': 'B', 'cache_path': 'c.json'}]},
     'cache and log paths must be unique'),
    ({'users': [{'name': 'A', 'log_path': 'l.json'}, {'name': 'B', 'log_path': 'l.json'}]},
     'cache and log paths must be unique'),
    ({'users': [{'name': 'A', 'cache_path': 'x.json'}, {'name': 'B', 'log_path': 'x.json'}]},
     'cache and log paths must be unique'),
    ({'users': [{'name': 'A', 'log_path': 5}]}, r'users\[0\].log_path must be a string'),
    ({'display': {'log_path': 5}}, 'display.log_path must be a string'),
    ({'users': [{'name': 'Joel', 'email_env': 'lower-case'}]}, 'must be an environment variable name'),
    ({'users': [{'name': 'Joel', 'weekly_goals': {'workouts': -1}}]}, 'weekly_goals values must be non-negative'),
    ({'display': {'weekly_goals': {'workouts': True}}}, 'weekly_goals values must be non-negative'),
    ({'display': {'font': 'comic-sans'}}, 'unsupported display.font'),
    ({'display': {'color': 'plaid'}}, 'unsupported display.color'),
    ({'display': {'timezone': 'Mars/Olympus'}}, 'invalid display.timezone'),
    ({'display': {'username': 7}}, 'display.username must be a string'),
    ({'display': {'rotation': ['username', 'username']}}, 'display.rotation must contain unique'),
    ({'display': {'rotation': ['karaoke']}}, 'display.rotation must contain unique'),
    ({'display': {'screen_durations': {'karaoke': 5}}}, 'unsupported screen name'),
    ({'display': {'screen_durations': {'username': -1}}}, 'values must be non-negative numbers'),
    ({'display': {'milestone_step': -5}}, 'milestone_step must be a non-negative integer'),
    ({'display': {'compact_workout_pages': 'yes'}}, 'compact_workout_pages must be true or false'),
    ({'display': {'brightness_schedule': {'day': 80}}}, 'brightness_schedule requires'),
    ({'display': {'brightness_schedule': {'day': 0, 'night': 20, 'day_start': '07:00', 'night_start': '21:00'}}},
     'brightness day must be from 1 to 100'),
    ({'display': {'brightness_schedule': {'day': 80, 'night': 20, 'day_start': '7am', 'night_start': '21:00'}}},
     'brightness day_start must use HH:MM'),
    ({'display': {'refresh_schedule': {'quiet_start': '23:00', 'quiet_end': '06:00', 'quiet_interval': 3600,
                                       'timezone': 5}}}, 'refresh_schedule.timezone must be a string'),
    ({'matrix': {'pixel_mapper': 3}}, 'matrix.pixel_mapper must be a string'),
])
def test_bad_config_names_the_problem(tmp_path, config, message):
    with pytest.raises(ValueError, match=message):
        _load(tmp_path, config)


def test_missing_config_points_at_the_example(tmp_path):
    with pytest.raises(ValueError, match='Copy config.json-example'):
        load_config(tmp_path / 'config.json')
    assert load_config(tmp_path / 'config.json', allow_missing=True)['display']


def test_unreadable_config(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"display": ')
    with pytest.raises(ValueError, match='Could not read config'):
        load_config(path)


@pytest.mark.parametrize('legacy', ['ride', 'park'])
def test_legacy_font_names_still_load(tmp_path, legacy):
    assert _load(tmp_path, {'display': {'font': legacy}})['display']['font'] == 'discipline'


def test_valid_brightness_and_refresh_schedules_load(tmp_path):
    config = _load(tmp_path, {'display': {
        'brightness_schedule': {'day': 80, 'night': 20, 'day_start': '07:00', 'night_start': '21:00'},
        'refresh_schedule': {'quiet_start': '23:00', 'quiet_end': '06:00', 'quiet_interval': 3600,
                             'timezone': 'America/New_York'}}})
    assert config['display']['brightness_schedule']['day'] == 80


def test_settings_the_workout_log_replaced_still_load_with_a_warning(tmp_path, caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        display = _load(tmp_path, {'display': {'history_days': 90, 'instructor_tally_max_pages': 200}})['display']
    assert 'display.history_days, display.instructor_tally_max_pages no longer do anything' in caplog.text
    assert display['history_batch_size'] == 100 and display['recent_fetch_size'] == 20
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        _load(tmp_path, {'display': {}})
    assert 'no longer do anything' not in caplog.text


def test_shipped_example_configs_load_without_retired_settings(tmp_path, caplog):
    import logging
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in ('config.json-example', 'packaging/config.pi.json'):
        # load_config reads config.json beside the given path, so load a copy.
        copy = tmp_path / name.replace('/', '-') / 'config.json'
        copy.parent.mkdir()
        copy.write_text((root / name).read_text())
        with caplog.at_level(logging.WARNING):
            display = load_config(copy)['display']
        assert 'no longer do anything' not in caplog.text, name
        assert display['history_batch_size'] == 100 and display['recent_fetch_size'] == 20, name
