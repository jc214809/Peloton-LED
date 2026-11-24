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

EXTRA_ICON_KEYS = [
    'dance_cardio',
    'running_outdoor',
    'walking_outdoor',
    'hiking',
    'outdoor',
    'boxing',
    'mobility',
    'pilates',
    'barre',
    'nonsense',
    '',
]

SUMMARIES = {
    'output_gain': {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412, 'previous_best_kj': 398, 'duration_min': 30},
    'output_dur': {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412, 'duration_min': 30},
    'output_plain': {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412},
    'splits': {'is_pr': True, 'is_splits_pr': True, 'row_split_sec_per_500m': 128, 'duration_min': 20},
    'new_pr': {'is_pr': True},
    'wide': {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 1234567, 'previous_best_kj': 5, 'duration_min': 45},
    # Joel's first Vision Tread run (2026-11-22): output, 1K and 1 mile, one turn each.
    'tread_run': {
        'is_pr': True,
        'is_output_pr': True,
        'total_output_kj': 180.3,
        'previous_best_kj': 170,
        'duration_min': 20,
        'discipline': 'Running',
        'best_times': [{'label': '1K', 'seconds': 633.0}, {'label': '1 MILE', 'seconds': 1005.0}],
    },
    'largest': {'is_pr': True, 'discipline': 'Tread Bootcamp', 'best_times': [{'label': 'MARATHON', 'seconds': 17999}]},
}
# The trophy rising (0 to 0.6 s), the text's arrival (0.8 s), both halves of the first turn, later turns, past the end.
ELAPSED = [0.0, 0.3, 0.59, 0.6, 0.79, 0.8, 1.5, 4.0, 6.85, 9.0, 13.0, 30.0]
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
    'cardio': '345282501e2a',
    'cycling': '9ce0a5a3dfa8',
    'dance_cardio': '345282501e2a',
    'hiking': '1c90ee8617ba',
    'meditation': 'b713105258c5',
    'mobility': 'f9626f807fd6',
    'nonsense': '39849039f83c',
    'outdoor': '1c90ee8617ba',
    'pilates': '9375c04faccd',
    'row_bootcamp': '4c30f4cb8dfe',
    'rowing': 'de194b885c11',
    'running': 'c31bf6d1d607',
    'running_outdoor': 'c31bf6d1d607',
    'strength': '33d8765bc605',
    'stretching': '2a001cdb0821',
    'tread_bootcamp': '9372d046270d',
    'walking': '02fbd90b2f98',
    'walking_outdoor': '02fbd90b2f98',
    'yoga': '4fc599adbaac',
}

PR_PINS = {
    (64, 'output_gain', 0.0): 'e66becb09e33',
    (64, 'output_gain', 0.3): 'a17e5968a6eb',
    (64, 'output_gain', 0.59): 'eec64e0cc257',
    (64, 'output_gain', 0.6): '6b5e21eb299a',
    (64, 'output_gain', 0.79): '6cf10b88eb05',
    (64, 'output_gain', 0.8): 'd48bde56b6c1',
    (64, 'output_gain', 1.5): '5a4f9e289bf1',
    (64, 'output_gain', 4.0): 'ede598a86848',
    (64, 'output_gain', 6.85): '1f4e65f9659d',
    (64, 'output_gain', 9.0): '92a9de63fb60',
    (64, 'output_gain', 13.0): '4ccd0b912dd6',
    (64, 'output_gain', 30.0): 'ad4e67eef673',
    (64, 'output_dur', 0.0): 'e66becb09e33',
    (64, 'output_dur', 0.3): 'a17e5968a6eb',
    (64, 'output_dur', 0.59): 'eec64e0cc257',
    (64, 'output_dur', 0.6): '6b5e21eb299a',
    (64, 'output_dur', 0.79): '6cf10b88eb05',
    (64, 'output_dur', 0.8): 'b02377a85640',
    (64, 'output_dur', 1.5): '5deadbd99d28',
    (64, 'output_dur', 4.0): 'ede598a86848',
    (64, 'output_dur', 6.85): '1f4e65f9659d',
    (64, 'output_dur', 9.0): '92a9de63fb60',
    (64, 'output_dur', 13.0): '4ccd0b912dd6',
    (64, 'output_dur', 30.0): 'ad4e67eef673',
    (64, 'output_plain', 0.0): 'e66becb09e33',
    (64, 'output_plain', 0.3): 'a17e5968a6eb',
    (64, 'output_plain', 0.59): 'eec64e0cc257',
    (64, 'output_plain', 0.6): '6b5e21eb299a',
    (64, 'output_plain', 0.79): '6cf10b88eb05',
    (64, 'output_plain', 0.8): '1cc43230dff1',
    (64, 'output_plain', 1.5): '628e561eccbb',
    (64, 'output_plain', 4.0): '9babc484a57f',
    (64, 'output_plain', 6.85): 'c364de612230',
    (64, 'output_plain', 9.0): '1423d9a117b1',
    (64, 'output_plain', 13.0): '62781d141c4f',
    (64, 'output_plain', 30.0): 'd3ee18330984',
    (64, 'splits', 0.0): 'e66becb09e33',
    (64, 'splits', 0.3): 'a17e5968a6eb',
    (64, 'splits', 0.59): 'eec64e0cc257',
    (64, 'splits', 0.6): '6b5e21eb299a',
    (64, 'splits', 0.79): '6cf10b88eb05',
    (64, 'splits', 0.8): '08846490f0c8',
    (64, 'splits', 1.5): 'c1764ded3992',
    (64, 'splits', 4.0): 'a91398e7aa5c',
    (64, 'splits', 6.85): '1b11645a726e',
    (64, 'splits', 9.0): '661faa33fc8d',
    (64, 'splits', 13.0): 'af3b306f8a1a',
    (64, 'splits', 30.0): '3a67e4a62b10',
    (64, 'new_pr', 0.0): 'e66becb09e33',
    (64, 'new_pr', 0.3): 'a17e5968a6eb',
    (64, 'new_pr', 0.59): 'eec64e0cc257',
    (64, 'new_pr', 0.6): '6b5e21eb299a',
    (64, 'new_pr', 0.79): '6cf10b88eb05',
    (64, 'new_pr', 0.8): 'bf218f0c851e',
    (64, 'new_pr', 1.5): 'd15e4d2adc96',
    (64, 'new_pr', 4.0): 'bfc03d89846a',
    (64, 'new_pr', 6.85): 'b06b00291fa4',
    (64, 'new_pr', 9.0): '7824196ac8a0',
    (64, 'new_pr', 13.0): 'b10a9ffb1e8e',
    (64, 'new_pr', 30.0): 'b4dcfc7ca23c',
    (64, 'wide', 0.0): 'e66becb09e33',
    (64, 'wide', 0.3): 'a17e5968a6eb',
    (64, 'wide', 0.59): 'eec64e0cc257',
    (64, 'wide', 0.6): '6b5e21eb299a',
    (64, 'wide', 0.79): '6cf10b88eb05',
    (64, 'wide', 0.8): 'f204f3ab00c9',
    (64, 'wide', 1.5): '4ce0986fda11',
    (64, 'wide', 4.0): '57d226613845',
    (64, 'wide', 6.85): '4a438211abb0',
    (64, 'wide', 9.0): '69d210c755f6',
    (64, 'wide', 13.0): 'c5539dd880bc',
    (64, 'wide', 30.0): '9e4562e061d5',
    (64, 'tread_run', 0.0): 'e66becb09e33',
    (64, 'tread_run', 0.3): 'a17e5968a6eb',
    (64, 'tread_run', 0.59): 'eec64e0cc257',
    (64, 'tread_run', 0.6): '6b5e21eb299a',
    (64, 'tread_run', 0.79): '6cf10b88eb05',
    (64, 'tread_run', 0.8): '97be2e1058ef',
    (64, 'tread_run', 1.5): '60e85726030b',
    (64, 'tread_run', 4.0): '797cfbc083f1',
    (64, 'tread_run', 6.85): 'da9507a3f70b',
    (64, 'tread_run', 9.0): '7e487bf55166',
    (64, 'tread_run', 13.0): '70b12c6b6ec6',
    (64, 'tread_run', 30.0): '811cc9e46b65',
    (64, 'largest', 0.0): 'e66becb09e33',
    (64, 'largest', 0.3): 'a17e5968a6eb',
    (64, 'largest', 0.59): 'eec64e0cc257',
    (64, 'largest', 0.6): '6b5e21eb299a',
    (64, 'largest', 0.79): '6cf10b88eb05',
    (64, 'largest', 0.8): 'cc0bda244d3a',
    (64, 'largest', 1.5): '0bb8fef8f8ce',
    (64, 'largest', 4.0): '6e13426aba21',
    (64, 'largest', 6.85): '4bd36dc15feb',
    (64, 'largest', 9.0): 'b387327915ba',
    (64, 'largest', 13.0): 'f38ef8bd3693',
    (64, 'largest', 30.0): 'ef2495bf131d',
    (32, 'output_gain', 0.0): 'b67bfe4a18b6',
    (32, 'output_gain', 0.3): '28c0dee31a0c',
    (32, 'output_gain', 0.59): 'dff7e9452c8c',
    (32, 'output_gain', 0.6): '7cf8fe958dc3',
    (32, 'output_gain', 0.79): '0dcc9c148594',
    (32, 'output_gain', 0.8): '2697c28f41bc',
    (32, 'output_gain', 1.5): '9cbfb27af027',
    (32, 'output_gain', 4.0): '1ce606b53a35',
    (32, 'output_gain', 6.85): '7e0675c3b2b1',
    (32, 'output_gain', 9.0): '1f4edcae0fa2',
    (32, 'output_gain', 13.0): '4792828a0b01',
    (32, 'output_gain', 30.0): 'de01df315c28',
    (32, 'output_dur', 0.0): 'b67bfe4a18b6',
    (32, 'output_dur', 0.3): '28c0dee31a0c',
    (32, 'output_dur', 0.59): 'dff7e9452c8c',
    (32, 'output_dur', 0.6): '7cf8fe958dc3',
    (32, 'output_dur', 0.79): '0dcc9c148594',
    (32, 'output_dur', 0.8): 'f8832075566b',
    (32, 'output_dur', 1.5): 'ff1b76783846',
    (32, 'output_dur', 4.0): '1ce606b53a35',
    (32, 'output_dur', 6.85): '7e0675c3b2b1',
    (32, 'output_dur', 9.0): '1f4edcae0fa2',
    (32, 'output_dur', 13.0): '4792828a0b01',
    (32, 'output_dur', 30.0): 'de01df315c28',
    (32, 'output_plain', 0.0): 'b67bfe4a18b6',
    (32, 'output_plain', 0.3): '28c0dee31a0c',
    (32, 'output_plain', 0.59): 'dff7e9452c8c',
    (32, 'output_plain', 0.6): '7cf8fe958dc3',
    (32, 'output_plain', 0.79): '0dcc9c148594',
    (32, 'output_plain', 0.8): 'c771ef5d8fb4',
    (32, 'output_plain', 1.5): '46b858c9a104',
    (32, 'output_plain', 4.0): '27c2104803cf',
    (32, 'output_plain', 6.85): '22624781d3c6',
    (32, 'output_plain', 9.0): '2e9cb5037b50',
    (32, 'output_plain', 13.0): '8772ce790f11',
    (32, 'output_plain', 30.0): 'a9b350f5ce3f',
    (32, 'splits', 0.0): 'b67bfe4a18b6',
    (32, 'splits', 0.3): '28c0dee31a0c',
    (32, 'splits', 0.59): 'dff7e9452c8c',
    (32, 'splits', 0.6): '7cf8fe958dc3',
    (32, 'splits', 0.79): '0dcc9c148594',
    (32, 'splits', 0.8): '1933cee7d8de',
    (32, 'splits', 1.5): 'f161bfb9070c',
    (32, 'splits', 4.0): 'd432abd3dd4c',
    (32, 'splits', 6.85): '76cf7cc22262',
    (32, 'splits', 9.0): '7e7b1ac2f165',
    (32, 'splits', 13.0): 'e7061e65e860',
    (32, 'splits', 30.0): '1b8a931fec1a',
    (32, 'new_pr', 0.0): 'b67bfe4a18b6',
    (32, 'new_pr', 0.3): '28c0dee31a0c',
    (32, 'new_pr', 0.59): 'dff7e9452c8c',
    (32, 'new_pr', 0.6): '7cf8fe958dc3',
    (32, 'new_pr', 0.79): '0dcc9c148594',
    (32, 'new_pr', 0.8): 'e437f2e723ea',
    (32, 'new_pr', 1.5): 'ac0c15cd3122',
    (32, 'new_pr', 4.0): 'd623a8606a51',
    (32, 'new_pr', 6.85): '80c42dc6ac01',
    (32, 'new_pr', 9.0): '0da6eac12f08',
    (32, 'new_pr', 13.0): 'cb270877beee',
    (32, 'new_pr', 30.0): '4c445c424c2a',
    (32, 'wide', 0.0): 'b67bfe4a18b6',
    (32, 'wide', 0.3): '28c0dee31a0c',
    (32, 'wide', 0.59): 'dff7e9452c8c',
    (32, 'wide', 0.6): '7cf8fe958dc3',
    (32, 'wide', 0.79): '0dcc9c148594',
    (32, 'wide', 0.8): '0eae05343d5f',
    (32, 'wide', 1.5): 'f09ca129f854',
    (32, 'wide', 4.0): '9e0fa297ceb2',
    (32, 'wide', 6.85): '207f8882a57f',
    (32, 'wide', 9.0): 'be09366c1e30',
    (32, 'wide', 13.0): 'b03160e2e13f',
    (32, 'wide', 30.0): '6d7517731cd0',
    (32, 'tread_run', 0.0): 'b67bfe4a18b6',
    (32, 'tread_run', 0.3): '28c0dee31a0c',
    (32, 'tread_run', 0.59): 'dff7e9452c8c',
    (32, 'tread_run', 0.6): '7cf8fe958dc3',
    (32, 'tread_run', 0.79): '0dcc9c148594',
    (32, 'tread_run', 0.8): 'fd4e7c068c43',
    (32, 'tread_run', 1.5): 'b8ba0239c52c',
    (32, 'tread_run', 4.0): 'eb97f8cf3528',
    (32, 'tread_run', 6.85): '9bd2004c3e5f',
    (32, 'tread_run', 9.0): '73b8c28bf22c',
    (32, 'tread_run', 13.0): '959ee62963f4',
    (32, 'tread_run', 30.0): 'adf1244be7be',
    (32, 'largest', 0.0): 'b67bfe4a18b6',
    (32, 'largest', 0.3): '28c0dee31a0c',
    (32, 'largest', 0.59): 'dff7e9452c8c',
    (32, 'largest', 0.6): '7cf8fe958dc3',
    (32, 'largest', 0.79): '0dcc9c148594',
    (32, 'largest', 0.8): '23c4486d96d5',
    (32, 'largest', 1.5): 'bf0283e91e1e',
    (32, 'largest', 4.0): 'f2e51881c135',
    (32, 'largest', 6.85): '8a3c3cd7129e',
    (32, 'largest', 9.0): '087818e60e06',
    (32, 'largest', 13.0): 'd99bc6cdada5',
    (32, 'largest', 30.0): '2def93cab48e',
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


# The fallbacks below never run in the rotation, so they're checked directly.


def test_pr_card_too_wide_value_drops_to_the_headline_font(monkeypatch):
    initialize_fonts(64)
    import display.ui.pr_celebration as pr

    drawn = []
    monkeypatch.setattr(PrCelebrationScreen, '_centred', staticmethod(lambda matrix, font, y, color, text: drawn.append((y, font))))
    monkeypatch.setattr(pr, 'get_text_width', lambda font, text: 999 if text.endswith('KJ') else 10)
    screen = PrCelebrationScreen()
    screen.update(3.0)
    screen.render(ImageMatrix(64, 64), {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412})
    fonts = dict(drawn)
    assert fonts[pr._TALL_VALUE] is fonts[pr._TALL_HEAD]  # the value is drawn in the headline's font


class _Canvas:
    width = height = 8


class _Graphics:
    """driver.graphics stand-in: records pixels, and can fail lines or pixels like a bare canvas."""

    def __init__(self, line_fails=False, pixel_fails_at=()):
        self.line_fails, self.pixel_fails_at = line_fails, set(pixel_fails_at)
        self.lines, self.pixels = [], []

    def DrawLine(self, matrix, x0, y0, x1, y1, color):
        if self.line_fails:
            raise RuntimeError('no DrawLine')
        self.lines.append((x0, y0, x1, y1))

    def DrawPixel(self, matrix, x, y, color):
        if (x, y) in self.pixel_fails_at:
            raise RuntimeError('no pixel')
        self.pixels.append((x, y))


SQUARE = [(1, 1), (5, 1), (5, 5), (1, 5)]  # two horizontal edges, which add no crossings


def _fill(monkeypatch, poly, fake):
    import display.ui.pr_star as pr_star

    monkeypatch.setattr(pr_star, 'graphics', fake)
    PrStarScreen()._scanline_fill_polygon(_Canvas(), poly, 'gold')
    return fake


def test_star_fill_draws_one_span_per_row(monkeypatch):
    fake = _fill(monkeypatch, SQUARE, _Graphics())
    assert fake.lines == [(1, y, 5, y) for y in range(1, 5)]


def test_star_fill_falls_back_to_pixels_and_skips_ones_that_fail(monkeypatch):
    fake = _fill(monkeypatch, SQUARE, _Graphics(line_fails=True, pixel_fails_at={(3, 2)}))
    assert fake.pixels == [(x, y) for y in range(1, 5) for x in range(1, 6) if (x, y) != (3, 2)]


@pytest.mark.parametrize('poly', [[], [(0, 2), (6, 2), (3, 2)]])
def test_star_fill_draws_nothing_without_a_shape(monkeypatch, poly):
    fake = _fill(monkeypatch, poly, _Graphics())
    assert fake.lines == [] and fake.pixels == []


def test_star_fill_stops_a_row_on_an_unpaired_crossing(monkeypatch):
    monkeypatch.setattr(PrStarScreen, '_crossings', staticmethod(lambda edges, y: [1.0, 4.0, 6.0]))
    fake = _fill(monkeypatch, SQUARE, _Graphics())
    assert fake.lines == [(1, y, 4, y) for y in range(8)]
