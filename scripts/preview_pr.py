"""Preview the PR celebration screen using your most recent real Peloton PR.

    python scripts/preview_pr.py --user Joel              # play it in the emulator
    python scripts/preview_pr.py --user Jen --png pr.png  # save a frame strip instead

Pages back through workout history (newest first) until it finds a PR, so it
costs 1 profile call + 1 call per 50 workouts searched + 1 performance call.
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logger = logging.getLogger('peloton-led.preview-pr')


def parse_options(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--user', help='Rider name from config users (default: first)')
    parser.add_argument('--token', help='Token file path, overriding the configured one')
    parser.add_argument('--max-pages', type=int, default=20, help='History pages of 50 to search')
    parser.add_argument('--png', help='Save preview frames to this PNG instead of opening the emulator')
    parser.add_argument('--replay', type=float, default=6.0, help='Seconds before the animation restarts')
    parser.add_argument('--previous-best', type=float, metavar='KJ',
                        help='Old record to show the gain against (preview only; the app learns this itself)')
    return parser.parse_args(argv)


def token_path_for(config, config_path, user_name=None):
    from peloton.config import default_token_path
    users = config.get('users') or []
    if not users:
        return ROOT / 'cookies.txt', 'default'
    user = users[0]
    if user_name:
        matches = [u for u in users if u['name'].strip().casefold() == user_name.strip().casefold()]
        if not matches:
            raise SystemExit(f"No user named {user_name!r}; configured: {', '.join(u['name'] for u in users)}")
        user = matches[0]
    path = Path(user.get('token_path') or default_token_path(user['name'])).expanduser()
    if not path.is_absolute():
        path = Path(config_path).expanduser().resolve().parent / path
    return path, user['name']


def find_latest_pr(client, user_id, max_pages, page_size=50):
    """Newest completed PR workout and the number of history pages read."""
    from peloton.records import is_pr_workout
    from peloton.selection import is_completed
    for page_number in range(max_pages):
        page = client.get_workouts_page(user_id, limit=page_size, page=page_number)
        rows = page.get('data') or []
        if not isinstance(rows, list):
            raise ValueError('Malformed workout page')
        for workout in rows:
            if isinstance(workout, dict) and is_completed(workout) and is_pr_workout(workout):
                return workout, page_number + 1
        if not rows or page.get('show_next') is False:
            return None, page_number + 1
    return None, max_pages


def save_frames(summary, destination):
    import unittest  # noqa: F401  (selects emulator graphics without a matrix)
    from PIL import Image
    from display.display import initialize_fonts
    from display.ui.pr_celebration import PrCelebrationScreen
    from scripts.render_demo import ImageMatrix
    initialize_fonts(64)
    tiles = []
    for elapsed in (0.2, 0.8, 1.35, 2.5):
        matrix = ImageMatrix(height=64)
        screen = PrCelebrationScreen()
        screen.on_enter(matrix, summary)
        screen.update(elapsed)
        screen.render(matrix, summary)
        tiles.append(matrix.image.resize((256, 256), Image.NEAREST))
    sheet = Image.new('RGB', (len(tiles) * 264 - 8, 256), (40, 40, 40))
    for index, tile in enumerate(tiles):
        sheet.paste(tile, (index * 264, 0))
    sheet.save(destination)


def play_in_emulator(summary, replay):
    # The driver picks emulator vs hardware from the app's own CLI flags.
    sys.argv = [sys.argv[0], '--emulated', '--led-rows', '64', '--led-cols', '64']
    from driver import RGBMatrix
    from utils.utils import args, led_matrix_options
    from display.display import initialize_fonts
    from display.ui.manager import ScreenManager
    from display.ui.pr_celebration import PrCelebrationScreen
    matrix = RGBMatrix(options=led_matrix_options(args()))
    initialize_fonts(matrix.height)
    manager = ScreenManager(matrix)
    manager.register('pr', PrCelebrationScreen())
    logger.info('Playing in the emulator; Ctrl+C to stop')
    try:
        while True:
            manager.show('pr', summary)
            deadline = time.monotonic() + replay
            while time.monotonic() < deadline:
                manager.tick(summary)
                time.sleep(1 / 30)
    except KeyboardInterrupt:
        pass


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    options = parse_options(argv)
    from peloton.api import PelotonClient, make_session
    from peloton.config import load_config, load_dotenv
    from peloton.summaries import summarize_workout
    load_dotenv(ROOT / '.env')
    try:
        config = load_config(options.config)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if options.token:
        token_path, name = Path(options.token), options.user or 'rider'
    else:
        token_path, name = token_path_for(config, options.config, options.user)
    if not token_path.exists():
        raise SystemExit(f'Token file not found: {token_path} (run scripts/refresh_cookies.py)')

    client = PelotonClient(make_session(token_path))
    try:
        me = client.get_me()
        user_id = me.get('id')
        if not user_id:
            raise SystemExit('Peloton profile response had no user ID')
        workout, pages = find_latest_pr(client, user_id, options.max_pages)
        if workout is None:
            raise SystemExit(f'No PR found for {name} in the last {pages * 50} workouts '
                             f'(try a larger --max-pages)')
        summary = summarize_workout(workout, client.get_perf_graph(workout['id']))
    except Exception as exc:
        response = getattr(exc, 'response', None)
        if response is not None and response.status_code == 401:
            raise SystemExit(f'Peloton rejected the token in {token_path}; refresh it and retry') from exc
        raise
    finally:
        client.close()

    if options.previous_best is not None:
        summary['previous_best_kj'] = options.previous_best
    logger.info('%s: latest PR after %d history page(s), %d API calls total', name, pages, pages + 2)
    logger.info(json.dumps({k: summary.get(k) for k in (
        'date_time', 'discipline', 'title', 'instructor', 'duration_min', 'total_output_kj',
        'total_work_kj', 'previous_best_kj', 'row_split_sec_per_500m', 'is_output_pr',
        'is_splits_pr')}, indent=2))
    if options.png:
        save_frames(summary, options.png)
        logger.info('Saved frames to %s', options.png)
    else:
        play_in_emulator(summary, options.replay)


if __name__ == '__main__':
    main()
