"""The settings page's PIN, over whatever's on the board while it's up.

The settings server (settings_page/pins.py) writes "<PIN> <expiry, epoch seconds>" to PIN_FILE
when someone asks for one, and removes it once it's used. Asked every frame, so the file is read
at most every CHECK_EVERY_S. Drawn as big white digits in a gold-edged black box, centred, the
same size on 64x64 and 64x32 boards so it reads from across the room: its own 3x5 digits at
SCALE, so it needs no font.
"""
import logging
import time

from settings_page.pins import PIN_FILE

logger = logging.getLogger('peloton-led.settings-pin')

CHECK_EVERY_S = 1.0
DIGITS = {
    '0': ['###', '#.#', '#.#', '#.#', '###'],
    '1': ['.#.', '##.', '.#.', '.#.', '###'],
    '2': ['###', '..#', '###', '#..', '###'],
    '3': ['###', '..#', '.##', '..#', '###'],
    '4': ['#.#', '#.#', '###', '..#', '..#'],
    '5': ['###', '#..', '###', '..#', '###'],
    '6': ['###', '#..', '###', '#.#', '###'],
    '7': ['###', '..#', '.#.', '.#.', '.#.'],
    '8': ['###', '#.#', '###', '#.#', '###'],
    '9': ['###', '#.#', '###', '..#', '###'],
}
SCALE = 2
GAP = 1  # between digits, before scaling
PAD = 2  # black between the digits and the gold edge
WHITE, GOLD, BLACK = (255, 255, 255), (255, 190, 0), (0, 0, 0)

_cache = {'at': None, 'pin': None, 'expires': 0.0}
_last_problem = None


def shown_pin(path=None, clock=time.time, monotonic=time.monotonic):
    """The PIN to show now, or None."""
    now = monotonic()
    if _cache['at'] is None or now - _cache['at'] >= CHECK_EVERY_S:
        _cache.update(at=now, **_read(path or PIN_FILE))
    return _cache['pin'] if _cache['pin'] and clock() < _cache['expires'] else None


def _read(path):
    global _last_problem
    try:
        with open(path, encoding='utf-8') as f:
            pin, expires = f.read().split()
        found = {'pin': pin if pin.isdigit() else None, 'expires': float(expires)}
    except FileNotFoundError:
        found = {'pin': None, 'expires': 0.0}
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        problem = f"Can't read the settings PIN from {path}: {exc}"
        if problem != _last_problem:  # asked every frame: say it once
            logger.warning(problem)
        _last_problem = problem
        return {'pin': None, 'expires': 0.0}
    _last_problem = None
    return found


def draw_pin(canvas, pin):
    digits = [DIGITS[d] for d in pin if d in DIGITS]
    if not digits:
        return
    text_w = (len(digits) * (3 + GAP) - GAP) * SCALE
    text_h = 5 * SCALE
    w, h = text_w + 2 * (PAD + 1), text_h + 2 * (PAD + 1)
    x0, y0 = (canvas.width - w) // 2, (canvas.height - h) // 2
    for y in range(h):
        for x in range(w):
            edge = x in (0, w - 1) or y in (0, h - 1)
            canvas.SetPixel(x0 + x, y0 + y, *(GOLD if edge else BLACK))
    left, top = x0 + PAD + 1, y0 + PAD + 1
    for i, art in enumerate(digits):
        for row, line in enumerate(art):
            for col, key in enumerate(line):
                if key != '#':
                    continue
                for dy in range(SCALE):
                    for dx in range(SCALE):
                        canvas.SetPixel(left + (i * (3 + GAP) + col) * SCALE + dx, top + row * SCALE + dy, *WHITE)


def draw_if_pin_shown(canvas):
    pin = shown_pin()
    if pin:
        draw_pin(canvas, pin)
