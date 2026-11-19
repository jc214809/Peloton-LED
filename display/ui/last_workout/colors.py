"""The page's colours: discipline, heart-rate zone and insight palettes."""
from driver import graphics
from ..logo_art import ZONE_COLORS


_WHITE = graphics.Color(255, 255, 255)


_GOLD  = graphics.Color(255, 215,   0)


_RED   = graphics.Color(220,  20,  20)


_BLUE  = graphics.Color(  0, 120, 255)


_DISCIPLINE_COLORS = {
    "cycling":       graphics.Color(220, 50,  20),
    "bike bootcamp": graphics.Color(220, 50,  20),
    "tread bootcamp": graphics.Color(20, 200, 80),
    "row bootcamp":  graphics.Color(0, 140, 255),
    "running":       graphics.Color(20,  200, 80),
    "walking":       graphics.Color(20,  180, 60),
    "outdoor run":   graphics.Color(20,  200, 80),
    "outdoor walk":  graphics.Color(20,  180, 60),
    "strength":      graphics.Color(255, 140,  0),
    "bootcamp":      graphics.Color(255, 140,  0),
    "rowing":        graphics.Color(0,   140, 255),
    "yoga":          graphics.Color(160,   0, 220),
    "meditation":    graphics.Color(120,   0, 180),
    "stretching":    graphics.Color(0,   200, 180),
    "cardio":        graphics.Color(255,  80,   0),
    "pilates":       graphics.Color(200, 100, 200),
    "barre":         graphics.Color(220,  80, 160),
    "boxing":        graphics.Color(255,  80,  0),
    "dance cardio":  graphics.Color(255,  80, 120),
    "mobility":      graphics.Color(0,  200, 180),
}


def _disc_color(discipline: str) -> graphics.Color:
    return _DISCIPLINE_COLORS.get(discipline.strip().lower(), _WHITE)


def _disc_rgb(discipline: str):
    colour = _disc_color(discipline)
    return colour.red, colour.green, colour.blue


# Heart-rate zone colors, zone 1 first; also used to color graph columns.
HR_ZONE_COLORS = list(ZONE_COLORS)


_LABEL_GREY = (145, 165, 190)


_PEAK_WHITE = (255, 255, 255)


_INSIGHT_GOLD = (255, 200, 0)


# Insight sentences and reasons: full white is glaring on the panel next to the coloured figures.
_INSIGHT_TEXT = (200, 205, 215)


_INSIGHT_DIM = (70, 80, 95)


# The 'usual' bar: navy, so today's bar is the one that stands out (the number and label stay grey).
_USUAL_BAR = (20, 50, 140)
