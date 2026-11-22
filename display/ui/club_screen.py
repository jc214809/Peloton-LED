"""The Club Peloton page: the rider's level as a gem, its name, the points, a bar across the tier and how far
to the next level.

64 rows: the gem (20 px) at the top, `GOLD III` in the tier's colour, `13,659 PTS`, the bar across the tier
(a gap where each of its levels starts), then `1,341 TO` over `CHAMPION` in that level's colour (`TOP LEVEL` for
a Legend); `2X` in gold in the bottom left corner during a double-points boost.
32 rows: a 12 px gem at the left with the level and points beside it, the bar, then `1,341 TO CHAMPION`
(`2X` at its left when both fit).
Before the first score only the gem and the level show (from /api/me).
State: peloton.feeds.club.club_page (validated again here: the cache can hold anything).
"""

from functools import lru_cache

from display.display import get_text_width, loaded_fonts
from driver import graphics
from peloton.feeds.club import KINDS, gem_kind, tier_fraction, valid_club

from .screen import Screen

WHITE = (255, 255, 255)
GREY = (145, 165, 190)
BOOST = (255, 215, 0)
BOOST_X = 2  # `2X` sits in the bottom left corner on both heights
BAR_TRACK = (35, 35, 35)
# Each gem's colour (from Peloton's own badges) and the level name's, a touch lighter where the gem is dark.
GEM_COLORS = {
    'BRONZE': (235, 115, 35),
    'SILVER': (150, 180, 215),
    'GOLD': (240, 205, 0),
    'CHAMPION': (225, 175, 245),
    'LEGEND': (210, 30, 50),
}
TEXT_COLORS = {
    'BRONZE': (240, 140, 60),
    'SILVER': (200, 215, 235),
    'GOLD': (255, 215, 0),
    'CHAMPION': (235, 190, 250),
    'LEGEND': (240, 60, 75),
}
# The gems, hand-drawn pixel art in Peloton's shapes: a hexagon (bronze, silver, gold), an octagon (Champion) and
# a cut diamond (Legend). `#` is the flat top face; every other letter is a facet, named for the way it faces,
# and lit by how much it faces the top left (FACET_SHADES). Outlines step evenly (2 across 1 down on the
# hexagon, 1 and 1 on the others), facets are flat colour and nothing is blended, so every pixel is crisp.
# Hand-editable: change a letter, then `python scripts/render_club.py` to see it.
GEM_ROWS = {
    ('HEX', 20): (
        '.........qp.........',
        '.......qqqppp.......',
        '.....qqqqqppppp.....',
        '...qqqqqqqppppppp...',
        '.wqqqqqqq##pppppppe.',
        '.wwwqqq######pppeee.',
        '.wwww##########eeee.',
        '.wwww##########eeee.',
        '.wwww##########eeee.',
        '.wwww##########eeee.',
        '.wwww##########eeee.',
        '.wwww##########eeee.',
        '.wwww##########eeee.',
        '.wwww##########eeee.',
        '.wwwzzz######mmmeee.',
        '.wzzzzzzz##mmmmmmme.',
        '...zzzzzzzmmmmmmm...',
        '.....zzzzzmmmmm.....',
        '.......zzzmmm.......',
        '.........zm.........',
    ),
    ('HEX', 12): (
        '.....qp.....',
        '...qqqppp...',
        '.qqqqqppppp.',
        'wqqqq##ppppe',
        'wwq######pee',
        'www######eee',
        'www######eee',
        'wwz######mee',
        'wzzzz##mmmme',
        '.zzzzzmmmmm.',
        '...zzzmmm...',
        '.....zm.....',
    ),
    ('OCT', 20): (
        '.....nnnnnnnnnn.....',
        '....qqnnnnnnnnpp....',
        '...qqqnnnnnnnnppp...',
        '..qqqqnnnnnnnnpppp..',
        '.qqqqqq######pppppp.',
        'wqqqqq########pppppe',
        'wwwwq##########peeee',
        'wwww############eeee',
        'wwww############eeee',
        'wwww############eeee',
        'wwww############eeee',
        'wwww############eeee',
        'wwww############eeee',
        'wwwwz##########meeee',
        'wzzzzz########mmmmme',
        '.zzzzzz######mmmmmm.',
        '..zzzzssssssssmmmm..',
        '...zzzssssssssmmm...',
        '....zzssssssssmm....',
        '.....ssssssssss.....',
    ),
    ('OCT', 12): (
        '...nnnnnn...',
        '..qnnnnnnp..',
        '.qqnnnnnnpp.',
        'wqqq####pppe',
        'wwq######pee',
        'www######eee',
        'www######eee',
        'wwz######mee',
        'wzzz####mmme',
        '.zzssssssmm.',
        '..zssssssm..',
        '...ssssss...',
    ),
    ('DIAMOND', 20): (
        '....................',
        '....................',
        '....................',
        '....qq########pp....',
        '...qqqn######nppp...',
        '..qqqqnn####nnpppp..',
        '.qqqqqnnnnnnnnppppp.',
        'qqqqqqnnnnnnnnpppppp',
        '.wwwwwwwwwmmmmmmmmm.',
        '..wwwwwwwwmmmmmmmm..',
        '...wwwwwwwmmmmmmm...',
        '....wwwwwwmmmmmm....',
        '.....wwwwwmmmmm.....',
        '......wwwwmmmm......',
        '.......wwwmmm.......',
        '........wwmm........',
        '.........wm.........',
        '....................',
        '....................',
        '....................',
    ),
    ('DIAMOND', 12): (
        '............',
        '............',
        '..qq####pp..',
        '.qqqn##nppp.',
        'qqqqnnnnpppp',
        '.wwwwwmmmmm.',
        '..wwwwmmmm..',
        '...wwwmmm...',
        '....wwmm....',
        '.....wm.....',
        '............',
        '............',
    ),
}
SHAPE_OF = {'CHAMPION': 'OCT', 'LEGEND': 'DIAMOND'}
# How bright each facet is against the gem's colour: up-left brightest, down-right darkest.
FACET_SHADES = {'#': 1.06, 'q': 1.3, 'n': 1.15, 'p': 0.9, 'w': 0.95, 'e': 0.6, 'z': 0.72, 's': 0.55, 'm': 0.45}
# Champion's corner facets catch blue light, as on Peloton's badge.
CHAMPION_CORNER = (175, 215, 240)
CORNER_FACETS = frozenset('qpzm')
# Where the 64-row page puts things: gem box, text baselines, bar rows.
GEM_64, GEM_TOP_64 = 20, 1
NAME_Y_64, POINTS_Y_64, BAR_TOP_64, TO_Y_64, NEXT_Y_64 = 33, 42, 45, 55, 63
TOP_LEVEL_Y_64 = 59  # `TOP LEVEL` alone, midway between the bar and the bottom
BAR_LEFT, BAR_RIGHT = 3, 60
# The level name's widest: a pixel clear of each edge.
LEVEL_WIDTH = 62
GEM_32, NAME_X_32, NAME_Y_32, POINTS_Y_32, BAR_TOP_32, LINE_Y_32 = 12, 17, 7, 14, 19, 30


def _shade(color, factor):
    return tuple(min(255, max(0, round(c * factor))) for c in color)


@lru_cache(maxsize=16)
def gem_pixels(kind, size):
    """Every lit pixel of a `size`-pixel gem (20 or 12) as (x, y, r, g, b) from its box's top left, from
    GEM_ROWS: each facet one flat shade of the gem's colour. An unknown kind is gold. Cached."""
    kind = kind if kind in KINDS else 'GOLD'
    rows = GEM_ROWS[(SHAPE_OF.get(kind, 'HEX'), size)]
    base = GEM_COLORS[kind]
    pixels = []
    for y, row in enumerate(rows):
        for x, facet in enumerate(row):
            if facet == '.':
                continue
            color = CHAMPION_CORNER if kind == 'CHAMPION' and facet in CORNER_FACETS else base
            pixels.append((x, y) + _shade(color, FACET_SHADES[facet]))
    return tuple(pixels)


def _text(matrix, font, x, y, color, text):
    graphics.DrawText(matrix, font, x, y, graphics.Color(*color), text)


def _centre(matrix, font, y, color, text):
    _text(matrix, font, max((matrix.width - get_text_width(font, text) + 1) // 2, 0), y, color, text)


def _first_fitting(font, width, lines):
    for line in lines:
        if line and get_text_width(font, line) <= width:
            return line
    return ''


def points_line(points, font, width):
    """`13,659 PTS`, else without the comma, else the number alone."""
    return _first_fitting(font, width, (f'{points:,} PTS', f'{points} PTS', f'{points:,}', f'{points}'))


def next_line(state, font, width):
    """`1,341 TO CHAMPION`, else without the comma, else `1,341 TO GO`; `TOP LEVEL` with no level above."""
    following, to_next = state.get('next'), state.get('to_next')
    if not following:
        return _first_fitting(font, width, ('TOP LEVEL',))
    if to_next is None:
        return ''
    return _first_fitting(font, width, (f'{to_next:,} TO {following}', f'{to_next} TO {following}', f'{to_next:,} TO GO', f'{to_next:,}'))


def fitted_level(level, fonts, width):
    """(font, text): the first font the level fits, else the last cut to fit."""
    for font in fonts:
        if get_text_width(font, level) <= width:
            return font, level
    font, text = fonts[-1], level
    while text and get_text_width(font, text) > width:
        text = text[:-1]
    return font, text


def _gem(matrix, kind, size, left, top):
    for x, y, r, g, b in gem_pixels(kind, size):
        matrix.SetPixel(left + x, top + y, r, g, b)


def _bar(matrix, state, top, color):
    """The bar across the tier: the rider's share lit in the level's colour over the track, one dark column
    where each of the tier's levels starts."""
    span = BAR_RIGHT - BAR_LEFT + 1
    filled = round(span * tier_fraction(state))
    gaps = set()
    if state['tier_max'] is not None:
        gaps = {BAR_LEFT + round(span * tier_fraction(state, mark)) for mark in state['marks']}
    for x in range(BAR_LEFT, BAR_RIGHT + 1):
        if x in gaps and BAR_LEFT < x < BAR_RIGHT:
            continue
        lit = color if x < BAR_LEFT + filled else BAR_TRACK
        for y in range(top, top + 3):
            matrix.SetPixel(x, y, *lit)


def valid_page(state):
    if not isinstance(state, dict) or state.get('kind') not in KINDS or not isinstance(state.get('level'), str):
        return False
    if not state['level'] or not isinstance(state.get('boost'), bool):
        return False
    return state.get('points') is None or valid_club(state)


class ClubScreen(Screen):
    def render(self, matrix, state=None):
        if not valid_page(state):
            return False
        if matrix.height < 64:
            return self._render_short(matrix, state)
        fonts, kind = loaded_fonts, state['kind']
        _gem(matrix, kind, GEM_64, (matrix.width - GEM_64) // 2, GEM_TOP_64)
        font, level = fitted_level(state['level'], [fonts['bold'], fonts['titles']], LEVEL_WIDTH)
        _centre(matrix, font, NAME_Y_64, TEXT_COLORS[kind], level)
        if state['points'] is None:
            _centre(matrix, fonts['stats'], 63, GREY, 'CLUB PELOTON')
            return True
        _centre(matrix, fonts['titles'], POINTS_Y_64, WHITE, points_line(state['points'], fonts['titles'], 62))
        _bar(matrix, state, BAR_TOP_64, GEM_COLORS[kind])
        following, to_next = state['next'], state['to_next']
        if following and to_next is not None:
            # Two lines: `1,341 TO`, then the next level in its own colour.
            _centre(matrix, fonts['stats'], TO_Y_64, WHITE, _first_fitting(fonts['stats'], 62, (f'{to_next:,} TO', f'{to_next} TO')))
            font, name = fitted_level(following, [fonts['stats']], 62)
            _centre(matrix, font, NEXT_Y_64, TEXT_COLORS[gem_kind(following)], name)
            bottom_left = max((matrix.width - get_text_width(font, name) + 1) // 2, 0)
        else:
            _centre(matrix, fonts['stats'], TOP_LEVEL_Y_64, WHITE, next_line(state, fonts['stats'], 62))
            bottom_left = matrix.width  # nothing on the bottom row
        # `2X` in the bottom left corner during a boost, as on 32 rows, when it clears the level's name by 2 px
        # of advance (3 blank columns: `SILVER III` and `BRONZE III` leave exactly that).
        if state['boost'] and BOOST_X + get_text_width(fonts['stats'], '2X') + 2 <= bottom_left:
            _text(matrix, fonts['stats'], BOOST_X, NEXT_Y_64, BOOST, '2X')
        return True

    def _render_short(self, matrix, state):
        small, kind = loaded_fonts['info'], state['kind']
        width = matrix.width - NAME_X_32
        if state['points'] is None:
            # Only the level: the gem and its name, in the middle of the panel.
            _gem(matrix, kind, GEM_32, 2, (matrix.height - GEM_32) // 2)
            font, level = fitted_level(state['level'], [loaded_fonts['discipline'], small], width)
            _text(matrix, font, NAME_X_32, 18, TEXT_COLORS[kind], level)
            return True
        _gem(matrix, kind, GEM_32, 1, 1)
        font, level = fitted_level(state['level'], [loaded_fonts['discipline'], small], width)
        _text(matrix, font, NAME_X_32, NAME_Y_32, TEXT_COLORS[kind], level)
        _text(matrix, small, NAME_X_32, POINTS_Y_32, WHITE, points_line(state['points'], small, width))
        _bar(matrix, state, BAR_TOP_32, GEM_COLORS[kind])
        line = next_line(state, small, 62)
        boost_width = get_text_width(small, '2X')
        if state['boost'] and boost_width + get_text_width(small, line) + 4 <= 60:
            _text(matrix, small, BOOST_X, LINE_Y_32, BOOST, '2X')
            _text(matrix, small, 62 - get_text_width(small, line), LINE_Y_32, WHITE, line)
        else:
            _centre(matrix, small, LINE_Y_32, WHITE, line)
        return True
