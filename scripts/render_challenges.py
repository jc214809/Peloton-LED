#!/usr/bin/env python3
"""Render the README's challenges screenshot from the board's own drawing code, so it never drifts from it.

  python scripts/render_challenges.py

writes docs/screenshots/rotation/challenges.png: the challenges page for each case in PAGES, on a 64x64 panel
(top row) and a 64x32 panel (bottom row), labelled like the README's other screenshots. The page is drawn settled
(after its intro). `write_gifs(folder)` (from Python) writes challenge-intro-64.gif and -32.gif: the intro of the
first page in PAGES, 6x larger.
"""

import argparse
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from display.display import initialize_fonts  # noqa: E402
from display.ui.challenge_screen import INTRO_SECONDS, ChallengeScreen  # noqa: E402
from peloton.feeds.challenges import short_title  # noqa: E402
from scripts.render_demo import ImageMatrix  # noqa: E402
from scripts.render_logo import GAP, LABEL_WIDTH, SHEET_BACKGROUND, SHEET_SCALE  # noqa: E402


def _page(title, value, shown, unit, tier, following, to_next):
    return {
        'title': short_title(title),
        'end_time': None,
        'value': float(value),
        'shown': shown,
        'unit': unit,
        'tier': {'title': tier[0], 'value': float(tier[1])},
        'next': {'title': following[0], 'value': float(following[1])},
        'to_next': to_next,
    }


# Real titles and figures from 2026-11-14, titles shortened by short_title as on the board: a numbered tier,
# named tiers from bronze to gold, and the widest bottom line.
PAGES = [
    _page('The Annual 2026', 5503, '5,503', 'MIN', ('5K', 5000), ('6K', 6000), '497'),
    _page('The Countdown to Turkey Burn Challenge', 2, '2', 'CLASSES', ('UNEARNED', 0), ('GOLD', 18), '16'),
    _page('November 2026 Cycling Challenge', 43.5, '43.5', 'MILES', ('UNEARNED', 0), ('BRONZE', 50), '6.5'),
    _page('November 2026 Activity Challenge', 14, '14', 'DAYS', ('BRONZE', 10), ('SILVER', 15), '1'),
    _page('November 2026 Rep Goal Challenge', 1640, '1,640', 'REPS', ('BRONZE', 1500), ('SILVER', 3000), '1,360'),
]


def panels(height, scale=SHEET_SCALE):
    """Each page in PAGES drawn on a 64 x `height` panel, each pixel `scale` wide."""
    initialize_fonts(height)
    images = []
    for state in PAGES:
        matrix = ImageMatrix(64, height)
        screen = ChallengeScreen()
        screen.update(INTRO_SECONDS)  # the settled page, not the intro
        if not screen.render(matrix, state):
            raise RuntimeError(f'challenge page drew nothing for {state}')
        images.append(matrix.image.resize((64 * scale, height * scale), Image.NEAREST))
    return images


def sheet():
    rows = [(f'64x{height}', panels(height)) for height in (64, 32)]
    width = LABEL_WIDTH + len(PAGES) * (64 * SHEET_SCALE + GAP)
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


def intro_frames(height, state, scale=6):
    """The intro of one page as images, one per 20 fps frame, then a short hold on the settled page."""
    initialize_fonts(height)
    frames = []
    for index in range(round((INTRO_SECONDS + 1.0) / ChallengeScreen.frame_seconds) + 1):
        screen = ChallengeScreen()
        screen.update(index * ChallengeScreen.frame_seconds)
        matrix = ImageMatrix(64, height)
        screen.render(matrix, state)
        frames.append(matrix.image.resize((64 * scale, height * scale), Image.NEAREST))
    return frames


def write_gifs(folder, state=None):
    for height in (64, 32):
        frames = intro_frames(height, state or PAGES[0])
        path = os.path.join(folder, f'challenge-intro-{height}.gif')
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(ChallengeScreen.frame_seconds * 1000), loop=0)
        print(f'Wrote {path}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', default=os.path.join(ROOT, 'docs', 'screenshots', 'rotation', 'challenges.png'))
    options = parser.parse_args(argv)
    sheet().save(options.out)
    print(f'Wrote {options.out}')


if __name__ == '__main__':
    main()
