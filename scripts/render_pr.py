#!/usr/bin/env python3
"""Render the README's PR celebration screenshot from a dashboard cache, with no API calls.

  python scripts/render_pr.py --cache cookies-joel-dashboard-cache.json

writes docs/screenshots/rotation/pr-celebration.png: the cache's newest PR workout (or --workout's), its
workout page frames and then the PR card's (the trophy rising, then each record's turn), on a 64x64 panel
(top row) and a 64x32 panel (bottom row), labelled like the README's other screenshots.
"""

import argparse
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import unittest  # noqa: E402, F401  side effect: selects the emulator graphics

from display.display import initialize_fonts  # noqa: E402
from display.ui.last_workout.rotation import LAST_WORKOUT_DETAIL_INTERVAL_SECONDS, rotating_details, stats_phase_seconds  # noqa: E402
from display.ui.last_workout.screen import LastWorkoutScreen  # noqa: E402
from display.ui.pr_celebration import PrCelebrationScreen, pr_page_seconds  # noqa: E402
from peloton.cache import load_snapshot  # noqa: E402
from scripts.render_logo import GAP, LABEL_WIDTH, SHEET_BACKGROUND, SHEET_SCALE  # noqa: E402
from scripts.render_rotation import _render_tiles  # noqa: E402


def pr_summary(snapshot, workout_id=None):
    """The summary to draw: --workout's, else the newest PR one; None when there's none."""
    summaries = [s for s in (snapshot or {}).get('summaries') or [] if isinstance(s, dict)]
    if workout_id:
        return next((s for s in summaries if s.get('workout_id') == workout_id), None)
    return next((s for s in summaries if s.get('is_pr')), None)


def panels(summary, height, detail_interval=LAST_WORKOUT_DETAIL_INTERVAL_SECONDS, scale=SHEET_SCALE):
    """The workout page's frames, then the PR card's, each drawn on a 64 x `height` panel."""
    initialize_fonts(height)
    page = detail_interval + stats_phase_seconds(rotating_details(summary, height), detail_interval)
    pages = [('last_workout', summary, page), ('pr', summary, pr_page_seconds(summary, detail_interval))]
    screens = {'last_workout': LastWorkoutScreen(detail_interval=detail_interval), 'pr': PrCelebrationScreen(detail_interval)}
    return [
        image.resize((64 * scale, height * scale), Image.NEAREST) for _, image in _render_tiles(pages, screens, detail_interval, height)
    ]


def sheet(summary):
    rows = [(f'64x{height}', panels(summary, height)) for height in (64, 32)]
    width = LABEL_WIDTH + max(len(images) for _, images in rows) * (64 * SHEET_SCALE + GAP)
    height = GAP + sum(images[0].height + GAP * 2 for _, images in rows) - GAP
    image = Image.new('RGB', (width, height), SHEET_BACKGROUND)
    draw = ImageDraw.Draw(image)
    top = GAP
    for label, images in rows:
        for index, panel in enumerate(images):
            image.paste(panel, (LABEL_WIDTH + index * (panel.width + GAP), top))
        draw.text((GAP, top + images[0].height // 2 - 6), label, fill=(200, 200, 200))
        top += images[0].height + GAP * 2
    return image


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--cache', required=True, help='Dashboard cache JSON, e.g. cookies-joel-dashboard-cache.json')
    parser.add_argument('--workout', help='Workout ID to draw (default: the newest PR workout in the cache)')
    parser.add_argument('--out', default=os.path.join(ROOT, 'docs', 'screenshots', 'rotation', 'pr-celebration.png'))
    options = parser.parse_args(argv)
    summary = pr_summary(load_snapshot(options.cache), options.workout)
    if summary is None:
        raise SystemExit(f'No PR workout in {options.cache}' + (f' with ID {options.workout}' if options.workout else ''))
    sheet(summary).save(options.out)
    print(options.out)


if __name__ == '__main__':
    main()
