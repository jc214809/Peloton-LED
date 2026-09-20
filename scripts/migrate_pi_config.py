#!/usr/bin/env python3
"""Create a production Pi config while keeping credentials out of it."""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from peloton.config import default_token_path


def migrate_config(source: Path, template: Path, destination: Path) -> None:
    base = json.loads(template.read_text(encoding='utf-8'))
    if source.exists():
        existing = json.loads(source.read_text(encoding='utf-8'))
        if not isinstance(existing, dict) or not isinstance(existing.get('display', {}), dict):
            raise ValueError('Existing config and display must be JSON objects')
        base['debug'] = existing.get('debug', base.get('debug', False))
        base['display'].update(existing.get('display', {}))
        if existing.get('users'):
            base['users'] = existing['users']
    base.pop('auth', None)
    base['display']['cache_path'] = '/var/lib/peloton-led/dashboard-cache.json'
    for index, user in enumerate(base.get('users', []), start=1):
        token_name = Path(user.get('token_path') or default_token_path(user['name'])).name
        cache_name = Path(user.get('cache_path') or f'dashboard-cache-user-{index}.json').name
        user['token_path'] = f'/var/lib/peloton-led/{token_name}'
        user['cache_path'] = f'/var/lib/peloton-led/{cache_name}'
        user.pop('email', None)
        user.pop('password', None)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix='.peloton-config-', dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(base, handle, indent=2)
            handle.write('\n')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('template', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    migrate_config(args.source, args.template, args.destination)


if __name__ == '__main__':
    main()
