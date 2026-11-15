"""The Club Peloton page: the rider's level as a gem, its name, the points, a bar across the tier and how far
to the next level.

64 rows: the gem (20 px) at the top, `GOLD III` in the tier's colour, `13,659 PTS`, the bar across the tier
(a gap where each of its levels starts), then `1,341 TO` over `CHAMPION` in that level's colour (`TOP LEVEL` for
a Legend); `2X` in gold in the bottom left corner during a double-points boost.
32 rows: a 13 px gem at the left with the level and points beside it, the bar, then `1,341 TO CHAMPION`
(`2X` at its left when both fit).
Before the first score only the gem and the level show (from /api/me).
State: peloton.club.club_page (validated again here: the cache can hold anything).
"""
import math
from functools import lru_cache

from driver import graphics

from display.display import get_text_width, loaded_fonts
from peloton.club import KINDS, gem_kind, tier_fraction, valid_club
from .screen import Screen

WHITE = (255, 255, 255)
GREY = (145, 165, 190)
BOOST = (255, 215, 0)
BOOST_X = 2  # `2X` sits in the bottom left corner on both heights
BAR_TRACK = (35, 35, 35)
# Each gem's colour (from Peloton's own badges) and the level name's, a touch lighter where the gem is dark.
GEM_COLORS = {'BRONZE': (235, 115, 35), 'SILVER': (150, 180, 215), 'GOLD': (240, 205, 0),
              'CHAMPION': (225, 175, 245), 'LEGEND': (210, 30, 50)}
TEXT_COLORS = {'BRONZE': (240, 140, 60), 'SILVER': (200, 215, 235), 'GOLD': (255, 215, 0),
               'CHAMPION': (235, 190, 250), 'LEGEND': (240, 60, 75)}
# Champion's gem shimmers: its facets take turns in these.
CHAMPION_FACETS = ((240, 190, 245), (180, 220, 245), (205, 170, 245), (245, 215, 235))
# The gems' outlines in a 2 x 2 box centred on 0: a hexagon (bronze, silver, gold), an octagon (champion) and
# a cut diamond (legend), as Peloton draws them; and the point the facets meet at.
SHAPES = {
    'HEX': ([(0.9 * math.cos(math.radians(a)), math.sin(math.radians(a))) for a in (-90, -30, 30, 90, 150, 210)],
            (0.0, 0.0)),
    'OCT': ([(-0.55, -1), (0.55, -1), (1, -0.55), (1, 0.55), (0.55, 1), (-0.55, 1), (-1, 0.55), (-1, -0.55)],
            (0.0, 0.0)),
    'DIAMOND': ([(-0.55, -0.75), (0.55, -0.75), (1, -0.25), (0, 1), (-1, -0.25)], (0.0, -0.25)),
}
SHAPE_OF = {'CHAMPION': 'OCT', 'LEGEND': 'DIAMOND'}
TABLE = 0.5  # the flat top face, as a share of the gem
LIGHT = (-0.6, -0.8)  # light from the top left
SUBSAMPLES = 4
# Where the 64-row page puts things: gem box, text baselines, bar rows.
GEM_64, GEM_TOP_64 = 20, 1
NAME_Y_64, POINTS_Y_64, BAR_TOP_64, TO_Y_64, NEXT_Y_64 = 33, 42, 45, 55, 63
TOP_LEVEL_Y_64 = 59  # `TOP LEVEL` alone, midway between the bar and the bottom
BAR_LEFT, BAR_RIGHT = 3, 60
# The level name's widest: a pixel clear of each edge.
LEVEL_WIDTH = 62
GEM_32, NAME_X_32, NAME_Y_32, POINTS_Y_32, BAR_TOP_32, LINE_Y_32 = 13, 17, 7, 14, 19, 30


def _inside(point, polygon):
    """Inside a convex polygon whose points run clockwise (y down)."""
    x, y = point
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1]):
        if (bx - ax) * (y - ay) - (by - ay) * (x - ax) < 0:
            return False
    return True


def _facet(point, polygon, centre):
    """Which edge's facet a point is in: the wedge from the centre between that edge's two corners."""
    angle = math.atan2(point[1] - centre[1], point[0] - centre[0])
    corners = [math.atan2(y - centre[1], x - centre[0]) for x, y in polygon]
    for i, start in enumerate(corners[:-1]):
        if (angle - start) % math.tau <= (corners[i + 1] - start) % math.tau:
            return i
    return len(corners) - 1  # the wedge from the last corner round to the first


def _shade(color, factor):
    return tuple(min(255, max(0, round(c * factor))) for c in color)


@lru_cache(maxsize=16)
def gem_pixels(kind, size):
    """Every lit pixel of a `size`-pixel gem as (x, y, r, g, b) from its box's top left: the flat top face in
    the gem's colour, each edge's facet lit by how much it faces the top left, the edges smoothed (4 x 4
    samples a pixel). Cached: the page draws the same gem often."""
    kind = kind if kind in KINDS else 'GOLD'
    polygon, centre = SHAPES[SHAPE_OF.get(kind, 'HEX')]
    table = [(centre[0] + (x - centre[0]) * TABLE, centre[1] + (y - centre[1]) * TABLE) for x, y in polygon]
    base = GEM_COLORS[kind]
    colors = []
    for i, ((ax, ay), (bx, by)) in enumerate(zip(polygon, polygon[1:] + polygon[:1])):
        length = math.hypot(bx - ax, by - ay) or 1
        normal = ((by - ay) / length, -(bx - ax) / length)  # outward, for clockwise points with y down
        facing = normal[0] * LIGHT[0] + normal[1] * LIGHT[1]
        color = CHAMPION_FACETS[i % len(CHAMPION_FACETS)] if kind == 'CHAMPION' else base
        colors.append(_shade(color, 0.8 + 0.45 * facing))
    top = _shade(base, 1.05)
    pixels = []
    total = SUBSAMPLES * SUBSAMPLES
    for y in range(size):
        for x in range(size):
            mix = [0, 0, 0]
            for i in range(SUBSAMPLES):
                for j in range(SUBSAMPLES):
                    point = (((x + (i + 0.5) / SUBSAMPLES) / size) * 2 - 1,
                             ((y + (j + 0.5) / SUBSAMPLES) / size) * 2 - 1)
                    if not _inside(point, polygon):
                        continue
                    color = top if _inside(point, table) else colors[_facet(point, polygon, centre)]
                    for k in range(3):
                        mix[k] += color[k]
            if any(mix):
                pixels.append((x, y) + tuple(round(m / total) for m in mix))
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
    return _first_fitting(font, width, (f'{to_next:,} TO {following}', f'{to_next} TO {following}',
                                        f'{to_next:,} TO GO', f'{to_next:,}'))


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
            _centre(matrix, fonts['stats'], TO_Y_64, WHITE,
                    _first_fitting(fonts['stats'], 62, (f'{to_next:,} TO', f'{to_next} TO')))
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
