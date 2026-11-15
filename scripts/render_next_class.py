#!/usr/bin/env python3
"""Render the README's next-class screenshot from the board's own drawing code, so it never drifts from it.

  python scripts/render_next_class.py

writes docs/screenshots/rotation/next_class.png: the next-class page for each case in PAGES, on a 64x64 panel
(top row) and a 64x32 panel (bottom row), labelled like the README's other screenshots (the tag at full brightness). `--gifs FOLDER` (or `write_gifs(folder)`)
writes next-class-pulse-64.gif and -32.gif instead: one cycle of the tag's pulse for a LIVE class 5 minutes out.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from display.display import initialize_fonts  # noqa: E402
from display.ui.next_class_screen import PULSE_FRAME_SECONDS, PULSE_PERIOD, NextClassScreen  # noqa: E402
from scripts.render_demo import ImageMatrix  # noqa: E402
from scripts.render_logo import GAP, LABEL_WIDTH, SHEET_BACKGROUND, SHEET_SCALE  # noqa: E402

# Sunday 2026-11-15, 12:00 PM in New York: the moment every page counts from.
NOW = 1794762000
ZONE = 'America/New_York'


def _page(discipline, minutes, instructor, tag, starts_in):
    return {'id': discipline, 'start': float(NOW + starts_in), 'tag': tag, 'discipline': discipline,
            'minutes': minutes, 'instructor': instructor}


# A live ride tomorrow, an encore bootcamp within the hour (a shared first name), and a class starting now.
PAGES = [
    _page('cycling', 20, 'Ben Alldis', 'LIVE', 22 * 3600),
    _page('tread_bootcamp', 45, 'Jess Sims', 'ENCORE', 45 * 60),
    _page('strength', 30, 'Charlotte Weidenbach', 'LIVE', -60),
]


def panels(height, scale=SHEET_SCALE):
    """Each page in PAGES drawn on a 64 x `height` panel, each pixel `scale` wide."""
    initialize_fonts(height)
    images = []
    for booking in PAGES:
        matrix = ImageMatrix(64, height)
        if not NextClassScreen().render(matrix, {'booking': booking, 'now': NOW, 'timezone': ZONE}):
            raise RuntimeError(f'next-class page drew nothing for {booking}')
        images.append(matrix.image.resize((64 * scale, height * scale), Image.NEAREST))
    return images


def pulse_frames(height, scale=8, starts_in=300):
    """One pulse cycle of a LIVE class `starts_in` seconds out, a frame every PULSE_FRAME_SECONDS."""
    initialize_fonts(height)
    state = {'booking': _page('cycling', 20, 'Ben Alldis', 'LIVE', starts_in), 'now': NOW, 'timezone': ZONE}
    screen = NextClassScreen()
    screen.on_enter(None, state)
    frames = []
    for _ in range(round(PULSE_PERIOD / PULSE_FRAME_SECONDS)):
        matrix = ImageMatrix(64, height)
        screen.render(matrix, state)
        frames.append(matrix.image.resize((64 * scale, height * scale), Image.NEAREST))
        screen.update(PULSE_FRAME_SECONDS)
    return frames


def write_gifs(folder):
    for height in (64, 32):
        frames = pulse_frames(height)
        path = os.path.join(folder, f'next-class-pulse-{height}.gif')
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=round(PULSE_FRAME_SECONDS * 1000),
                       loop=0)
        print(f'Wrote {path}')


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', default=os.path.join(ROOT, 'docs', 'screenshots', 'rotation', 'next_class.png'))
    parser.add_argument('--gifs', metavar='FOLDER', help='write the pulse GIFs to FOLDER instead of the sheet')
    options = parser.parse_args(argv)
    if options.gifs:
        write_gifs(options.gifs)
        return
    sheet().save(options.out)
    print(f'Wrote {options.out}')


if __name__ == '__main__':
    main()
