import json
import stat
from pathlib import Path

from peloton.config import load_config
from scripts.setup_config import build_config, prompt_riders, write_auth_env, write_config

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'packaging' / 'config.pi.json'


def test_zero_riders_prompts_again_instead_of_accepting_empty_setup():
    answers = iter(['', 'Joel', 'joel@example.com', 'joelpw', ''])
    riders = prompt_riders(input_fn=lambda _: next(answers), password_fn=lambda _: next(answers))
    assert riders == [{'name': 'Joel', 'email': 'joel@example.com', 'password': 'joelpw'}]


def test_prompt_riders_collects_until_blank_name():
    answers = iter(['Joel', 'joel@example.com', 'joelpw', 'Jen', 'jen@example.com', 'jenpw', ''])
    riders = prompt_riders(input_fn=lambda _: next(answers), password_fn=lambda _: next(answers))
    assert [r['name'] for r in riders] == ['Joel', 'Jen']


def test_prompt_riders_rejects_duplicate_names():
    answers = iter(['Joel', 'a@example.com', 'pw', 'joel', 'Jen', 'jen@example.com', 'jenpw', ''])
    riders = prompt_riders(input_fn=lambda _: next(answers), password_fn=lambda _: next(answers))
    assert [r['name'] for r in riders] == ['Joel', 'Jen']


def test_single_rider_uses_plain_email_password_vars_and_no_users_array():
    config, auth_env = build_config(
        [{'name': 'Joel', 'email': 'joel@example.com', 'password': 'secret'}], TEMPLATE)
    assert 'users' not in config
    assert auth_env == {'PELOTON_EMAIL': 'joel@example.com', 'PELOTON_PASSWORD': 'secret'}
    assert config['display']['cache_path'] == '/var/lib/peloton-led/dashboard-cache.json'


def test_multiple_riders_get_isolated_state_paths_and_env_vars():
    riders = [{'name': 'Joel', 'email': 'joel@example.com', 'password': 'pw1'},
              {'name': 'Jen', 'email': 'jen@example.com', 'password': 'pw2'}]
    config, auth_env = build_config(riders, TEMPLATE)
    users = config['users']
    assert users[0]['token_path'] == '/var/lib/peloton-led/cookies-joel.txt'
    assert users[0]['cache_path'] == '/var/lib/peloton-led/dashboard-cache-joel.json'
    assert users[1]['token_path'] == '/var/lib/peloton-led/cookies-jen.txt'
    assert auth_env == {
        'PELOTON_EMAIL_JOEL': 'joel@example.com', 'PELOTON_PASSWORD_JOEL': 'pw1',
        'PELOTON_EMAIL_JEN': 'jen@example.com', 'PELOTON_PASSWORD_JEN': 'pw2',
    }


def test_built_configs_pass_real_validation(tmp_path):
    single, _ = build_config([{'name': 'Joel', 'email': 'a@example.com', 'password': 'pw'}], TEMPLATE)
    dual, _ = build_config([
        {'name': 'Joel', 'email': 'a@example.com', 'password': 'pw'},
        {'name': 'Jen', 'email': 'b@example.com', 'password': 'pw2'},
    ], TEMPLATE)
    single_path = tmp_path / 'single.json'
    dual_path = tmp_path / 'dual.json'
    single_path.write_text(json.dumps(single))
    dual_path.write_text(json.dumps(dual))
    assert 'users' not in load_config(single_path)
    assert [u['name'] for u in load_config(dual_path)['users']] == ['Joel', 'Jen']


def test_write_config_is_atomic_and_readable(tmp_path):
    destination = tmp_path / 'nested' / 'config.json'
    write_config({'debug': False}, destination)
    assert json.loads(destination.read_text()) == {'debug': False}


def test_write_auth_env_is_owner_only_and_escapes_special_characters(tmp_path):
    destination = tmp_path / 'auth.env'
    write_auth_env({'PELOTON_PASSWORD': 'has"quote\\slash'}, destination)
    content = destination.read_text()
    assert content == 'PELOTON_PASSWORD="has\\"quote\\\\slash"\n'
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
