#!/usr/bin/env python3
"""Interactively build the Pi's config.json and auth.env in one pass.

Prompts for zero or more riders. Zero riders produces a single-user config
(PELOTON_EMAIL / PELOTON_PASSWORD); one or more produces a `users` array,
each with a derived email_env/password_env and token/cache paths under
/var/lib/peloton-led/. Credentials are written straight to auth.env and
never stored in config.json.
"""
import argparse
import getpass
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from peloton.config import default_token_path, user_slug

STATE_DIR = '/var/lib/peloton-led'


def prompt_riders(input_fn=input, password_fn=getpass.getpass):
    """Collect rider name/email/password triples until an empty name is given."""
    riders = []
    print("Let's set up who's using this board.")
    while True:
        prompt = 'Rider name (leave blank to finish' + (
            ', at least one required' if not riders else '') + '): '
        name = input_fn(prompt).strip()
        if not name:
            if riders:
                break
            print('At least one rider is required for single-user mode too — '
                  "just give the account a name (e.g. your own).")
            continue
        if any(rider['name'].casefold() == name.casefold() for rider in riders):
            print(f'"{name}" was already added; use a different name.')
            continue
        email = input_fn(f'  Peloton email for {name}: ').strip()
        password = password_fn(f'  Peloton password for {name}: ')
        riders.append({'name': name, 'email': email, 'password': password})
    return riders


def build_config(riders, template):
    base = json.loads(Path(template).read_text(encoding='utf-8'))
    base['display']['cache_path'] = f'{STATE_DIR}/dashboard-cache.json'
    if len(riders) == 1:
        # A single rider still gets first-class treatment (their real name
        # everywhere) but doesn't need the users[]/email_env indirection.
        return base, {'PELOTON_EMAIL': riders[0]['email'], 'PELOTON_PASSWORD': riders[0]['password']}
    users = []
    auth_env = {}
    for rider in riders:
        suffix = re.sub(r'[^A-Z0-9]+', '_', rider['name'].upper()).strip('_') or 'USER'
        email_env = f'PELOTON_EMAIL_{suffix}'
        password_env = f'PELOTON_PASSWORD_{suffix}'
        token_name = Path(default_token_path(rider['name'])).name
        users.append({
            'name': rider['name'],
            'email_env': email_env,
            'password_env': password_env,
            'token_path': f'{STATE_DIR}/{token_name}',
            'cache_path': f'{STATE_DIR}/dashboard-cache-{user_slug(rider["name"])}.json',
        })
        auth_env[email_env] = rider['email']
        auth_env[password_env] = rider['password']
    base['users'] = users
    return base, auth_env


def write_config(config, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix='.peloton-config-', dir=destination.parent)
    temporary = Path(temp_name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(config, handle, indent=2)
            handle.write('\n')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def write_auth_env(auth_env, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix='.peloton-auth-', dir=destination.parent)
    temporary = Path(temp_name)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            for key, value in auth_env.items():
                escaped = value.replace('\\', '\\\\').replace('"', '\\"')
                handle.write(f'{key}="{escaped}"\n')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('template', type=Path, help='Base display config, e.g. packaging/config.pi.json')
    parser.add_argument('config_destination', type=Path, help='Where to write config.json')
    parser.add_argument('auth_destination', type=Path, help='Where to write auth.env')
    args = parser.parse_args()

    if not sys.stdin.isatty():
        sys.exit('setup_config.py needs an interactive terminal to prompt for riders.')

    riders = prompt_riders()
    config, auth_env = build_config(riders, args.template)
    write_config(config, args.config_destination)
    write_auth_env(auth_env, args.auth_destination)
    names = ', '.join(rider['name'] for rider in riders)
    print(f'Configured {len(riders)} rider(s): {names}')


if __name__ == '__main__':
    main()
