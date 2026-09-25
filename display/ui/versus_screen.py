"""Two riders side by side for the current week: workouts, minutes, output."""
from driver import graphics

from display.display import get_text_width, loaded_fonts
from .last_workout_screen import _TROPHY_W, _draw_trophy
from .screen import Screen

DETAIL_INTERVAL_SECONDS = 4.0
STATS = (('workouts', 'WORKOUTS'), ('minutes', 'MINUTES'), ('output_kj', 'OUTPUT KJ'))
RIDER_COLORS = (graphics.Color(0, 150, 255), graphics.Color(255, 80, 150))
_GREY = graphics.Color(145, 165, 190)
_GOLD = graphics.Color(255, 215, 0)
_WHITE = graphics.Color(255, 255, 255)


def weekly_leader(riders):
    """Index of the rider ahead this week (workouts, then minutes, then
    output), or None on a full tie."""
    keys = [tuple(r.get(k) or 0 for k, _ in STATS) for r in riders[:2]]
    if keys[0] == keys[1]:
        return None
    return 0 if keys[0] > keys[1] else 1


def _fit(font, text, width):
    while text and get_text_width(font, text) > width:
        text = text[:-1]
    return text


class VersusScreen(Screen):
    """state: {'riders': [{'name', 'workouts', 'minutes', 'output_kj'}, ...]}.

    Only the first two riders are compared. 64 rows show all three stats at
    once; 32 rows show one stat at a time, rotating.
    """

    animated = True
    atomic_frames = True

    def __init__(self):
        self.elapsed = 0.0

    def on_enter(self, matrix, state=None):
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += max(0, dt)

    def _values(self, matrix, fonts, riders, key, y):
        """Left rider's value centered in the left half, right in the right;
        the larger one in gold. Uses the first font both values fit in."""
        a, b = (r.get(key) or 0 for r in riders)
        half = matrix.width // 2
        texts = [f'{a:,}', f'{b:,}']
        fonts = [f for f in fonts if f is not None]
        font = next((f for f in fonts if all(get_text_width(f, t) <= half - 2 for t in texts)), fonts[-1])
        for i, value in enumerate((a, b)):
            text = texts[i]
            color = _GOLD if value > (b if i == 0 else a) else _WHITE
            x = i * half + max((half - get_text_width(font, text)) // 2, 1)
            graphics.DrawText(matrix, font, x, y, color, text)

    def render(self, matrix, state=None):
        riders = (state or {}).get('riders') if isinstance(state, dict) else None
        if not isinstance(riders, list) or len(riders) < 2:
            return False
        riders = riders[:2]
        small = loaded_fonts.get('stats') or loaded_fonts.get('info')
        name_font = loaded_fonts.get('titles') or small
        value_font = loaded_fonts.get('titles') or small
        big = loaded_fonts.get('big') or value_font
        if small is None or name_font is None:
            return False
        w, half = matrix.width, matrix.width // 2
        leader = weekly_leader(riders)
        short = matrix.height < 64

        # Names across the top, each in its rider color; trophy by the leader.
        name_y = 6 if short else 16
        room = half - 2 - (_TROPHY_W + 1)
        for i, rider in enumerate(riders):
            name = _fit(name_font, str(rider.get('name') or f'RIDER {i + 1}').upper(), room)
            name_w = get_text_width(name_font, name)
            x = i * half + max((half - name_w - (_TROPHY_W + 1 if leader == i else 0)) // 2, 1)
            graphics.DrawText(matrix, name_font, x, name_y, RIDER_COLORS[i], name)
            if leader == i:
                _draw_trophy(matrix, x + name_w + 1, name_y - 7)

        if short:
            key, label = STATS[int(self.elapsed / DETAIL_INTERVAL_SECONDS) % len(STATS)]
            graphics.DrawText(matrix, small, max((w - get_text_width(small, label)) // 2, 1), 15, _GREY, label)
            # Big digits when they fit; smaller fonts keep 4-5 digit values apart.
            self._values(matrix, (big, loaded_fonts.get('countdown'), small), riders, key, 29)
            return True

        title = 'THIS WEEK'
        graphics.DrawText(matrix, small, (w - get_text_width(small, title)) // 2, 6, _GREY, title)
        # 15-row pitch: 5-row label, 2 blank, 6-row value, 2 blank.
        for row, (key, label) in enumerate(STATS):
            label_y = 24 + row * 15
            graphics.DrawText(matrix, small, (w - get_text_width(small, label)) // 2, label_y, _GREY, label)
            self._values(matrix, (value_font, small), riders, key, label_y + 8)
        return True
