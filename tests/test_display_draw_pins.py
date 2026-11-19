"""Pixel pins for the hand-drawn display code: every icon, every PR-celebration
frame and the PR star fill. Each case hashes the canvas, so a refactor of
`draw_icon`, `PrCelebrationScreen.render` or `_scanline_fill_polygon` that moves
one pixel fails here. Regenerate a hash only for an intended visual change.
"""
import hashlib

import pytest

from display.display import initialize_fonts
from display.ui.discipline_icons import DISCIPLINE_ICON_ROWS
from display.ui.lifetime_overview import draw_icon
from display.ui.pr_celebration import PrCelebrationScreen
from display.ui.pr_star import PrStarScreen
from scripts.render_demo import ImageMatrix

EXTRA_ICON_KEYS = ['dance_cardio', 'running_outdoor', 'walking_outdoor', 'hiking', 'outdoor', 'boxing',
                   'mobility', 'pilates', 'barre', 'nonsense', '']

SUMMARIES = {
    'output_gain': {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412, 'previous_best_kj': 398,
                    'duration_min': 30},
    'output_dur': {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412, 'duration_min': 30},
    'output_plain': {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412},
    'splits': {'is_pr': True, 'is_splits_pr': True, 'row_split_sec_per_500m': 128, 'duration_min': 20},
    'new_pr': {'is_pr': True},
    'wide': {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 1234567, 'previous_best_kj': 5,
             'duration_min': 45},
}
ELAPSED = [0.0, 0.3, 0.6, 1.19, 1.2, 1.25, 1.35, 1.5, 1.7, 2.0, 2.3, 3.0]
STAR_SIZES = [(64, 64), (64, 32), (32, 32), (5, 5)]


def _digest(matrix, ok=True):
    return hashlib.sha1(matrix.image.tobytes() + bytes([ok])).hexdigest()[:12]


def icon_hash(key):
    matrix = ImageMatrix(26, 24)
    draw_icon(matrix, key, 0, 0, (255, 255, 255))
    return _digest(matrix)


def pr_hash(height, name, elapsed):
    initialize_fonts(height)
    matrix = ImageMatrix(64, height)
    screen = PrCelebrationScreen()
    screen.update(elapsed)
    return _digest(matrix, screen.render(matrix, SUMMARIES[name]))


def star_hash(width, height, color, fill):
    matrix = ImageMatrix(width, height)
    return _digest(matrix, PrStarScreen(color, fill).render(matrix, None))


ICON_PINS = {
    '': '39849039f83c',
    'barre': '9375c04faccd',
    'bike_bootcamp': 'dc00b846a154',
    'boxing': 'c6f082822a65',
    'cardio': '2aec2ebf3acb',
    'cycling': '9ce0a5a3dfa8',
    'dance_cardio': '2aec2ebf3acb',
    'hiking': '1c90ee8617ba',
    'meditation': 'b713105258c5',
    'mobility': 'f9626f807fd6',
    'nonsense': '39849039f83c',
    'outdoor': '1c90ee8617ba',
    'pilates': '9375c04faccd',
    'row_bootcamp': '4c30f4cb8dfe',
    'rowing': 'de194b885c11',
    'running': '0beddfc66c86',
    'running_outdoor': '0beddfc66c86',
    'strength': '1cf5fc51decd',
    'stretching': '2a001cdb0821',
    'tread_bootcamp': '6bd3db5d026a',
    'walking': '853dc91d54c3',
    'walking_outdoor': '853dc91d54c3',
    'yoga': '4fc599adbaac',
}

PR_PINS = {
    (64, 'output_gain', 0.0): '50bba806a00c',
    (64, 'output_gain', 0.3): '08cce5ceed8d',
    (64, 'output_gain', 0.6): '82ecf926b257',
    (64, 'output_gain', 1.19): 'c80245cec691',
    (64, 'output_gain', 1.2): '8aeb537e7be7',
    (64, 'output_gain', 1.25): '6c7e2b24e03e',
    (64, 'output_gain', 1.35): 'b8cc4865b721',
    (64, 'output_gain', 1.5): '5b1c347457f8',
    (64, 'output_gain', 1.7): '25a8636a91fe',
    (64, 'output_gain', 2.0): '95589821904f',
    (64, 'output_gain', 2.3): '5b1c347457f8',
    (64, 'output_gain', 3.0): '5b1c347457f8',
    (64, 'output_dur', 0.0): '50bba806a00c',
    (64, 'output_dur', 0.3): '08cce5ceed8d',
    (64, 'output_dur', 0.6): '82ecf926b257',
    (64, 'output_dur', 1.19): 'c80245cec691',
    (64, 'output_dur', 1.2): '8aeb537e7be7',
    (64, 'output_dur', 1.25): '6c7e2b24e03e',
    (64, 'output_dur', 1.35): 'b8cc4865b721',
    (64, 'output_dur', 1.5): 'dfe394e735bf',
    (64, 'output_dur', 1.7): '916290bc49fd',
    (64, 'output_dur', 2.0): 'bcd695e76fb5',
    (64, 'output_dur', 2.3): 'dfe394e735bf',
    (64, 'output_dur', 3.0): 'dfe394e735bf',
    (64, 'output_plain', 0.0): '50bba806a00c',
    (64, 'output_plain', 0.3): '08cce5ceed8d',
    (64, 'output_plain', 0.6): '82ecf926b257',
    (64, 'output_plain', 1.19): 'c80245cec691',
    (64, 'output_plain', 1.2): '8aeb537e7be7',
    (64, 'output_plain', 1.25): '6c7e2b24e03e',
    (64, 'output_plain', 1.35): 'b8cc4865b721',
    (64, 'output_plain', 1.5): 'dbe3d64f7835',
    (64, 'output_plain', 1.7): '39bdd6c7a0e5',
    (64, 'output_plain', 2.0): '9eabcdde8f3f',
    (64, 'output_plain', 2.3): 'dbe3d64f7835',
    (64, 'output_plain', 3.0): 'dbe3d64f7835',
    (64, 'splits', 0.0): '50bba806a00c',
    (64, 'splits', 0.3): '08cce5ceed8d',
    (64, 'splits', 0.6): '82ecf926b257',
    (64, 'splits', 1.19): 'c80245cec691',
    (64, 'splits', 1.2): '8aeb537e7be7',
    (64, 'splits', 1.25): '6c7e2b24e03e',
    (64, 'splits', 1.35): 'b8cc4865b721',
    (64, 'splits', 1.5): '61393fa7b86f',
    (64, 'splits', 1.7): '93eb5330eecd',
    (64, 'splits', 2.0): '305f1d8eff06',
    (64, 'splits', 2.3): '61393fa7b86f',
    (64, 'splits', 3.0): '61393fa7b86f',
    (64, 'new_pr', 0.0): '50bba806a00c',
    (64, 'new_pr', 0.3): '08cce5ceed8d',
    (64, 'new_pr', 0.6): '82ecf926b257',
    (64, 'new_pr', 1.19): 'c80245cec691',
    (64, 'new_pr', 1.2): '8aeb537e7be7',
    (64, 'new_pr', 1.25): '6c7e2b24e03e',
    (64, 'new_pr', 1.35): 'b8cc4865b721',
    (64, 'new_pr', 1.5): 'e061c7cbb3ce',
    (64, 'new_pr', 1.7): 'ad8ca3145f61',
    (64, 'new_pr', 2.0): '793d20d3fe37',
    (64, 'new_pr', 2.3): 'e061c7cbb3ce',
    (64, 'new_pr', 3.0): 'e061c7cbb3ce',
    (64, 'wide', 0.0): '50bba806a00c',
    (64, 'wide', 0.3): '08cce5ceed8d',
    (64, 'wide', 0.6): '82ecf926b257',
    (64, 'wide', 1.19): 'c80245cec691',
    (64, 'wide', 1.2): '8aeb537e7be7',
    (64, 'wide', 1.25): '6c7e2b24e03e',
    (64, 'wide', 1.35): 'b8cc4865b721',
    (64, 'wide', 1.5): 'b093972a05bf',
    (64, 'wide', 1.7): 'c0501c765961',
    (64, 'wide', 2.0): '641c7ee7984f',
    (64, 'wide', 2.3): 'b093972a05bf',
    (64, 'wide', 3.0): 'b093972a05bf',
    (32, 'output_gain', 0.0): 'c581732b94b2',
    (32, 'output_gain', 0.3): '6399f4075c46',
    (32, 'output_gain', 0.6): '2b4ac693087b',
    (32, 'output_gain', 1.19): 'eda2c85c5d83',
    (32, 'output_gain', 1.2): '9167d2cda1ac',
    (32, 'output_gain', 1.25): '8826b3226b9a',
    (32, 'output_gain', 1.35): 'c7208905c571',
    (32, 'output_gain', 1.5): 'a674f866095c',
    (32, 'output_gain', 1.7): 'a674f866095c',
    (32, 'output_gain', 2.0): 'a674f866095c',
    (32, 'output_gain', 2.3): 'a674f866095c',
    (32, 'output_gain', 3.0): 'a674f866095c',
    (32, 'output_dur', 0.0): 'c581732b94b2',
    (32, 'output_dur', 0.3): '6399f4075c46',
    (32, 'output_dur', 0.6): '2b4ac693087b',
    (32, 'output_dur', 1.19): 'eda2c85c5d83',
    (32, 'output_dur', 1.2): '9167d2cda1ac',
    (32, 'output_dur', 1.25): '8826b3226b9a',
    (32, 'output_dur', 1.35): 'c7208905c571',
    (32, 'output_dur', 1.5): '4d35e96c45c4',
    (32, 'output_dur', 1.7): '4d35e96c45c4',
    (32, 'output_dur', 2.0): '4d35e96c45c4',
    (32, 'output_dur', 2.3): '4d35e96c45c4',
    (32, 'output_dur', 3.0): '4d35e96c45c4',
    (32, 'output_plain', 0.0): 'c581732b94b2',
    (32, 'output_plain', 0.3): '6399f4075c46',
    (32, 'output_plain', 0.6): '2b4ac693087b',
    (32, 'output_plain', 1.19): 'eda2c85c5d83',
    (32, 'output_plain', 1.2): '9167d2cda1ac',
    (32, 'output_plain', 1.25): '8826b3226b9a',
    (32, 'output_plain', 1.35): 'c7208905c571',
    (32, 'output_plain', 1.5): '3a50ceec7291',
    (32, 'output_plain', 1.7): '3a50ceec7291',
    (32, 'output_plain', 2.0): '3a50ceec7291',
    (32, 'output_plain', 2.3): '3a50ceec7291',
    (32, 'output_plain', 3.0): '3a50ceec7291',
    (32, 'splits', 0.0): 'c581732b94b2',
    (32, 'splits', 0.3): '6399f4075c46',
    (32, 'splits', 0.6): '2b4ac693087b',
    (32, 'splits', 1.19): 'eda2c85c5d83',
    (32, 'splits', 1.2): '9167d2cda1ac',
    (32, 'splits', 1.25): '8826b3226b9a',
    (32, 'splits', 1.35): 'c7208905c571',
    (32, 'splits', 1.5): 'bfddd9dabcd9',
    (32, 'splits', 1.7): 'bfddd9dabcd9',
    (32, 'splits', 2.0): 'bfddd9dabcd9',
    (32, 'splits', 2.3): 'bfddd9dabcd9',
    (32, 'splits', 3.0): 'bfddd9dabcd9',
    (32, 'new_pr', 0.0): 'c581732b94b2',
    (32, 'new_pr', 0.3): '6399f4075c46',
    (32, 'new_pr', 0.6): '2b4ac693087b',
    (32, 'new_pr', 1.19): 'eda2c85c5d83',
    (32, 'new_pr', 1.2): '9167d2cda1ac',
    (32, 'new_pr', 1.25): '8826b3226b9a',
    (32, 'new_pr', 1.35): 'c7208905c571',
    (32, 'new_pr', 1.5): 'd886b90a2346',
    (32, 'new_pr', 1.7): 'd886b90a2346',
    (32, 'new_pr', 2.0): 'd886b90a2346',
    (32, 'new_pr', 2.3): 'd886b90a2346',
    (32, 'new_pr', 3.0): 'd886b90a2346',
    (32, 'wide', 0.0): 'c581732b94b2',
    (32, 'wide', 0.3): '6399f4075c46',
    (32, 'wide', 0.6): '2b4ac693087b',
    (32, 'wide', 1.19): 'eda2c85c5d83',
    (32, 'wide', 1.2): '9167d2cda1ac',
    (32, 'wide', 1.25): '8826b3226b9a',
    (32, 'wide', 1.35): 'c7208905c571',
    (32, 'wide', 1.5): 'a98ea8eedc70',
    (32, 'wide', 1.7): 'a98ea8eedc70',
    (32, 'wide', 2.0): 'a98ea8eedc70',
    (32, 'wide', 2.3): 'a98ea8eedc70',
    (32, 'wide', 3.0): 'a98ea8eedc70',
}

STAR_PINS = {
    (64, 64, 'gold', True): 'eef484306b63',
    (64, 64, 'gold', False): '27b46f7d5443',
    (64, 64, 'nonexistent', True): 'eef484306b63',
    (64, 64, 'nonexistent', False): '27b46f7d5443',
    (64, 32, 'gold', True): 'a3bba11e5761',
    (64, 32, 'gold', False): '0d47a8ce80a8',
    (64, 32, 'nonexistent', True): 'a3bba11e5761',
    (64, 32, 'nonexistent', False): '0d47a8ce80a8',
    (32, 32, 'gold', True): 'e2b877f0043b',
    (32, 32, 'gold', False): 'acec68b9f3cf',
    (32, 32, 'nonexistent', True): 'e2b877f0043b',
    (32, 32, 'nonexistent', False): 'acec68b9f3cf',
    (5, 5, 'gold', True): '0a7325fa71e1',
    (5, 5, 'gold', False): '2abc2e276ed7',
    (5, 5, 'nonexistent', True): '0a7325fa71e1',
    (5, 5, 'nonexistent', False): '2abc2e276ed7',
}


def test_pins_cover_every_icon_the_code_knows():
    assert set(ICON_PINS) == set(DISCIPLINE_ICON_ROWS) | set(EXTRA_ICON_KEYS)


@pytest.mark.parametrize('key', sorted(ICON_PINS))
def test_icon_pixels_unchanged(key):
    assert icon_hash(key) == ICON_PINS[key]


@pytest.mark.parametrize('case', sorted(PR_PINS))
def test_pr_celebration_frame_unchanged(case):
    assert pr_hash(*case) == PR_PINS[case]


@pytest.mark.parametrize('case', sorted(STAR_PINS))
def test_pr_star_pixels_unchanged(case):
    assert star_hash(*case) == STAR_PINS[case]
