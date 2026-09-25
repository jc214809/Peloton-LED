"""Render one full display rotation to a PNG contact sheet, with no API calls.

    python scripts/render_rotation.py --height 32 --cache cookies-joel-dashboard-cache.json
    python scripts/render_rotation.py --height 64 --demo --out /tmp/demo-64.png

Pages come from the app's own build_rotation_pages, so the sheet shows what the
panel would actually cycle through. Animated pages get one frame per phase
(intro, each stat, each username detail, PR burst and card).
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Importing unittest selects the emulator graphics without initializing a matrix.
import unittest  # noqa: F401,E402

from PIL import Image, ImageDraw  # noqa: E402

SCALE = 4
ALL_SECTIONS = ['latest_workouts', 'username', 'total_workouts', 'lifetime', 'milestones', 'goals']


class PreviewDashboard:
    """Stands in for Dashboard: every PR and reached milestone is still pending."""

    def __init__(self, milestones):
        self.milestones = milestones

    def should_celebrate_pr(self, summary):
        return bool(summary.get('is_pr'))

    def pending_milestones(self, snapshot):
        total = snapshot.get('totals', {}).get('Total Workouts') or 0
        return [m for m in self.milestones if total >= m][-1:]


def load_snapshot_for(options):
    if options.demo:
        from peloton.demo import demo_data
        from peloton.summaries import summarize_workout
        from peloton.totals import extract_discipline_totals
        data = demo_data()
        return {'me': data['me'], 'totals': extract_discipline_totals(data['overview']),
                'summaries': [summarize_workout(w, data['performance'][w['id']])
                              for w in data['workouts']],
                'weekly_progress': {'workouts': 3, 'minutes': 95},
                'instructor_counts': {}, 'status': 'ready'}
    from peloton.cache import load_snapshot
    snapshot = load_snapshot(options.cache)
    if snapshot is None:
        raise SystemExit(f'Could not read a dashboard cache from {options.cache}')
    snapshot.setdefault('status', 'ready')
    return snapshot


def frame_times(name, state, duration, detail_interval):
    """Seconds into the page at which to capture a frame."""
    if name == 'last_workout':
        count = max(1, round(duration / detail_interval))
        return [0.6 + i * detail_interval for i in range(count)]
    if name == 'username':
        from display.ui.username import DETAIL_INTERVAL_SECONDS
        return [0.6 + i * DETAIL_INTERVAL_SECONDS for i in range(max(1, len(state.get('details', []))))]
    if name == 'pr':
        from display.ui.pr_celebration import BURST_SECONDS, SETTLE_SECONDS
        return [0.5, BURST_SECONDS + SETTLE_SECONDS + 0.5]
    return [0.5]


def render(options):
    from display.display import initialize_fonts
    from display.ui.discipline_page import DisciplinePageScreen
    from display.ui.goal_screen import GoalScreen
    from display.ui.last_workout_screen import LastWorkoutScreen, LAST_WORKOUT_DETAIL_INTERVAL_SECONDS
    from display.ui.lifetime_overview import LifetimeOverviewScreen
    from display.ui.logo_mask_screen import LogoMaskScreen
    from display.ui.pr_celebration import PrCelebrationScreen
    from display.ui.status_screen import StatusScreen
    from display.ui.username import UsernameScreen
    from display.ui.login_indicator import draw_login_indicator
    from display.ui.stale_indicator import draw_stale_indicator
    from peloton.config import DEFAULTS
    from peloton_led import build_rotation_pages
    from scripts.render_demo import ImageMatrix

    display = {**DEFAULTS, 'rotation': ALL_SECTIONS, 'color': 'white',
               'milestones': [100, 250, 500, 1000, 2000], 'weekly_goals': {'workouts': 5, 'minutes': 150}}
    detail_interval = display['last_workout_detail_interval']
    initialize_fonts(options.height)
    screens = {'username': UsernameScreen(font_key=display['font'], color_key=display['color']),
               'discipline': DisciplinePageScreen(), 'lifetime': LifetimeOverviewScreen(),
               'last_workout': LastWorkoutScreen(detail_interval=detail_interval),
               'pr': PrCelebrationScreen(), 'status': StatusScreen(), 'goal': GoalScreen(),
               'logo': LogoMaskScreen()}
    snapshot = load_snapshot_for(options)
    username = options.username or (snapshot.get('me') or {}).get('username') or 'Rider'
    pages = [('logo', None, 1.0)]
    pages += build_rotation_pages(snapshot, PreviewDashboard(display['milestones']),
                                  display, username, options.height)
    if options.overlays and snapshot['summaries']:
        pages.append(('last_workout', {**snapshot['summaries'][0], 'login_required': True,
                                       'data_stale': True}, detail_interval))

    tiles = []
    for name, state, duration in pages:
        for t in frame_times(name, state or {}, duration, detail_interval or LAST_WORKOUT_DETAIL_INTERVAL_SECONDS):
            matrix = ImageMatrix(height=options.height)
            screen = screens[name]
            screen.on_enter(matrix, state)
            screen.update(t)
            screen.render(matrix, state)
            if isinstance(state, dict) and state.get('login_required'):
                draw_login_indicator(matrix)
            if isinstance(state, dict) and state.get('data_stale'):
                draw_stale_indicator(matrix)
            label = name
            if isinstance(state, dict):
                label += f": {state.get('discipline') or state.get('username') or state.get('title') or ''}"
            tiles.append((f'{label} @{t:.1f}s'[:40], matrix.image))

    tile_w, tile_h = 64 * SCALE + 12, options.height * SCALE + 28
    columns = options.columns
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new('RGB', (tile_w * columns, tile_h * rows), '#202020')
    draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(tiles):
        x, y = (index % columns) * tile_w, (index // columns) * tile_h
        sheet.paste(image.resize((64 * SCALE, options.height * SCALE), Image.Resampling.NEAREST), (x + 6, y + 22))
        draw.text((x + 6, y + 6), label, fill='white')
    sheet.save(options.out)
    print(f'{len(tiles)} frames from {len(pages)} pages -> {options.out}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--cache', help='Dashboard cache JSON, e.g. cookies-joel-dashboard-cache.json')
    source.add_argument('--demo', action='store_true', help='Use built-in demo data')
    parser.add_argument('--height', type=int, choices=(32, 64), default=32)
    parser.add_argument('--username', help='Name to show on the username page')
    parser.add_argument('--columns', type=int, default=5)
    parser.add_argument('--no-overlays', dest='overlays', action='store_false',
                        help='Skip the extra frame showing the login and stale-data icons')
    parser.add_argument('--out', default='/tmp/peloton-rotation.png')
    render(parser.parse_args(argv))


if __name__ == '__main__':
    main()
