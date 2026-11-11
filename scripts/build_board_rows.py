"""Build a board's trimmed workout-row store from this computer's rows and saved responses.

    python scripts/build_board_rows.py --config config.local.json --board-config config.json --list
    python scripts/build_board_rows.py --rider joel --config config.local.json --out /tmp/rows.json

--list prints one `<rider>\t<file name on the board>` line per rider in the config. The name comes
from the board's config (`--board-config`, default config.json, the Pi's): its cache file name with
`.workout-rows.json`, which is where the board's Dashboard looks. The Mac's own cache names differ
(cookies-joel-dashboard-cache.json against the board's dashboard-cache-joel.json).
--out rebuilds any row missing or stale from training-data/ first (no API calls), keeps in-scope
rows from the last 760 days, and writes the store (0600).
Used by scripts/push_workout_rows.sh.
"""
import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from peloton.config import load_config, user_slug  # noqa: E402
from peloton.workout_rows import RawFiles, RowStore, board_store, import_raw  # noqa: E402
from workout_insights import rider_paths  # noqa: E402

log = logging.getLogger('build-board-rows')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--rider')
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--raw-dir', default=str(ROOT / 'training-data'))
    parser.add_argument('--out')
    parser.add_argument('--board-config', default='config.json',
                        help="the board's config (for --list): its cache paths name the board's files")
    parser.add_argument('--list', action='store_true', help='print each rider and its board file name')
    parser.add_argument('--now', type=float, default=None, help='epoch seconds (tests)')
    options = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s', stream=sys.stderr)
    try:
        config = load_config(options.config)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if options.list:
        users = config.get('users') or []
        if not users:
            raise SystemExit(f'No riders (users) in {options.config}')
        try:
            board_config = load_config(options.board_config)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        for user in users:
            # rider_paths exits when the board's config has no rider of that name.
            name, _, rows_path, _ = rider_paths(board_config, options.board_config, user['name'])
            print(f'{user_slug(name)}\t{rows_path.name}')
        return 0

    if not options.rider or not options.out:
        parser.error('--rider and --out are required (or use --list)')
    name, _, rows_path, _ = rider_paths(config, options.config, options.rider)
    store = RowStore.load(rows_path)
    raw = RawFiles(options.raw_dir, user_slug(name))
    if import_raw(store, raw):
        store.save()
    now = options.now if options.now is not None else time.time()
    board = board_store(store, now, options.out)
    board.save()
    log.info('%s: %d of %d rows -> %s', name, len(board.rows), len(store.rows), options.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
