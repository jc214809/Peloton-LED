"""Workout compare, daily run (Mac, version 1): fetch new workouts, store their rows, print insights.

    python scripts/workout_insights.py --rider joel --config config.local.json --dry-run
    python scripts/workout_insights.py --rider joel --config config.local.json
    python scripts/workout_insights.py --rider jen --config config.local.json --workout 823e0327
    python scripts/workout_insights.py --rider joel --config config.local.json --dry-run --last 10

Rows live in `<cache stem>.workout-rows.json` beside the rider's workout log. Raw responses are
saved under --raw-dir (default training-data/) before a row is built, so a ROW_VERSION bump is a
rebuild from those files with no API calls. A run: rebuild any row missing or stale from saved
files; list the newest workouts (1 call; the rider's workout log adds the last 730 days for
catch-up); fetch up to --limit missing ones newest first (2-3 calls each); print the insights of
each new workout, or of the latest one when nothing is new. Under each workout, a `board:` line per
insight the LED board would show for it (peloton/insight_lines.py: headline | sentence), or that it shows none.

--dry-run makes no API calls and writes nothing. A 401 stops the run (exit 2) and keeps every row
already saved. Uses the Mac's own token from the config, never a board's.
"""
import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from peloton.api import PelotonClient, make_session  # noqa: E402
from peloton.insight_lines import board_insights  # noqa: E402
from peloton.config import load_config, user_slug, user_token_path  # noqa: E402
from peloton.workout_compare import DISCIPLINES  # noqa: E402
from peloton.workout_insights import insights  # noqa: E402
from peloton.workout_log import WorkoutLog, default_log_path  # noqa: E402
from peloton.workout_rows import (MAX_PER_RUN, LoginRequired, RawFiles, RowStore,  # noqa: E402
                                  candidate_ids, default_rows_path, import_raw, sync)

log = logging.getLogger('workout-insights')
EXIT_LOGIN = 2


def args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--rider', required=True, help="the rider's name in the config's users")
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--raw-dir', default=str(ROOT / 'training-data'),
                        help='saved API responses (training-data layout)')
    parser.add_argument('--dry-run', action='store_true', help='no API calls, no writes')
    parser.add_argument('--limit', type=int, default=MAX_PER_RUN, help='most workouts fetched per run')
    parser.add_argument('--workout', help='print this workout (ID or ID prefix) instead')
    parser.add_argument('--last', type=int, help='print the newest N in-scope workouts instead')
    parser.add_argument('--verbose', action='store_true')
    return parser.parse_args(argv)


def rider_paths(config, config_path, rider):
    """(name, token path, rows path, log path) for the rider named in the config's users."""
    config_dir = Path(config_path).with_suffix('.json').expanduser().resolve().parent
    for user in config.get('users') or []:
        if user_slug(user.get('name') or '') == user_slug(rider):
            token = user_token_path(user, config_dir)
            if user.get('cache_path'):
                cache = Path(user['cache_path']).expanduser()
                cache = cache if cache.is_absolute() else config_dir / cache
            else:
                cache = token.with_name(f'{token.stem}-dashboard-cache.json')
            if user.get('log_path'):
                log_path = Path(user['log_path']).expanduser()
                log_path = log_path if log_path.is_absolute() else config_dir / log_path
            else:
                log_path = default_log_path(cache)
            return user['name'], token, default_rows_path(cache), log_path
    raise SystemExit(f'No rider named {rider!r} in {config_path}')


def describe(row, rows):
    lines = [f"{row['date']} {row.get('title') or row['disc']} ({row['id'][:8]})"]
    messages = insights(row, rows)
    lines += [f'  [{code}] {text}' for code, text, _ in messages]
    views = board_insights(messages)
    lines += [f"  board: {view['headline']} | {view['sentence']}" for view in views] or ['  board: (no slide)']
    return '\n'.join(lines)


def latest(rows):
    usable = [r for r in rows if r['disc'] in DISCIPLINES and r['complete']]
    return max(usable, key=lambda r: r['start']) if usable else None


def fetch_new(client, store, raw, log_path, limit):
    """IDs to fetch: the newest history page, plus the workout log's last 730 days when present."""
    workout_log = WorkoutLog.load(log_path) if log_path.exists() else None
    user_id = workout_log.user_id if workout_log and workout_log.user_id else None
    if not user_id:
        user_id = client.get_me()['id']
    page = client.get_workouts_page(user_id, limit=20, page=0)
    ids = candidate_ids(log_workouts=workout_log.workouts if workout_log else None,
                        listed=client.page_rows(page), now=time.time())
    return sync(client, store, raw, ids, limit=limit)


def main(argv=None):
    options = args(argv)
    logging.basicConfig(level=logging.DEBUG if options.verbose else logging.INFO,
                        format='%(levelname)s %(name)s: %(message)s', stream=sys.stderr)
    try:
        config = load_config(options.config)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    name, token, rows_path, log_path = rider_paths(config, options.config, options.rider)
    store = RowStore.load(rows_path)
    raw = RawFiles(options.raw_dir, user_slug(name))
    if import_raw(store, raw) and not options.dry_run:
        store.save()

    added = []
    status = 0
    if options.dry_run:
        log.info('Dry run: no API calls, nothing written')
    else:
        client = PelotonClient(make_session(token))
        try:
            added = fetch_new(client, store, raw, log_path, options.limit)
        except LoginRequired as exc:
            log.error('%s: the token for %s needs renewing; rows saved so far are kept', exc, name)
            status = EXIT_LOGIN
        finally:
            client.close()
        log.info('%d new workout(s) stored in %s', len(added), rows_path)

    rows = list(store.rows.values())
    if options.workout:
        chosen = [r for r in rows if r['id'].startswith(options.workout)]
        if not chosen:
            raise SystemExit(f'No stored workout {options.workout!r}')
    elif options.last:
        usable = [r for r in rows if r['disc'] in DISCIPLINES]
        chosen = sorted(usable, key=lambda r: r['start'])[-options.last:]
    elif added:
        chosen = sorted((store.rows[i] for i in added), key=lambda r: r['start'])
    else:
        chosen = [r for r in [latest(rows)] if r]
    if not chosen:
        print(f'No in-scope workouts stored for {name}.')
    for row in chosen:
        print(describe(row, rows))
    return status


if __name__ == '__main__':
    sys.exit(main())
