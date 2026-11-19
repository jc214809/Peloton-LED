"""Text measuring, wrapping and drawing helpers shared by every part of the page."""
import re
from typing import List, Optional

from driver import graphics
from display.display import get_text_width


# The length at the front of a title: "20 min HIIT Ride", and the free workouts Peloton names by their
# exact length, "60 min 11 sec Just Walk" or "41 sec Just Walk". The page shows the length itself.
_TITLE_LENGTH = re.compile(r'^\s*(?:\d+\s*min(?:ute)?s?\b\s*)?(?:\d+\s*sec(?:ond)?s?\b\s*)?', re.IGNORECASE)


def title_without_length(title) -> str:
    """A workout's title without the length it starts with; as it is when that's all there is."""
    title = str(title or '').strip()
    return _TITLE_LENGTH.sub('', title, count=1).strip() or title


_SQUEEZE = {'.', ','}   # characters that get tight spacing on both sides


_SQUEEZE_ADV = 3        # advance used for the squeeze char itself


_SQUEEZE_PRE = 3        # advance used for the char immediately before a squeeze char


def _char_advance(font, ch: str, next_ch: str = '') -> int:
    if ch in _SQUEEZE:
        return _SQUEEZE_ADV
    if next_ch in _SQUEEZE:
        return _SQUEEZE_PRE
    return font.CharacterWidth(ord(ch))


def _draw_text(matrix, font, x: int, y: int, color, text: str) -> int:
    """Draw text with tight spacing on both sides of periods/commas. Returns final x."""
    for i, ch in enumerate(text):
        graphics.DrawText(matrix, font, x, y, color, ch)
        x += _char_advance(font, ch, text[i + 1] if i + 1 < len(text) else '')
    return x


def _text_width(font, text: str) -> int:
    return sum(_char_advance(font, ch, text[i + 1] if i + 1 < len(text) else '')
               for i, ch in enumerate(text))


def _truncate(font, text: str, max_px: int) -> str:
    while text and _text_width(font, text) > max_px:
        text = text[:-1]
    return text.rstrip()


def _wrap_two_lines(font, text: str, max_px: int) -> List[str]:
    """Split text into at most two lines that each fit within max_px."""
    words = text.split()
    if not words:
        return []
    line1 = ""
    for i, word in enumerate(words):
        test = (line1 + " " + word).strip()
        if get_text_width(font, test) <= max_px:
            line1 = test
        else:
            line2 = _truncate(font, " ".join(words[i:]), max_px)
            return [line1, line2] if line2 else [line1]
    return [line1]


def _write(matrix, font, x: int, y: int, rgb, text: str) -> int:
    graphics.DrawText(matrix, font, x, y, graphics.Color(*rgb), text)
    return get_text_width(font, text)


# The colon's dot sits mid-cell, which leaves 6 blank columns before the next word against 5 between
# other words: the word after a colon moves this many px closer (Joel, 2026-11-11).
COLON_GAP_TRIM = 3


def _words_width(font, text: str) -> int:
    """`text`'s drawn width with the gap after each colon tightened."""
    return get_text_width(font, text) - COLON_GAP_TRIM * text.count(': ')


def _draw_words(matrix, font, x: int, y: int, text: str, colour_of) -> None:
    """`text` word by word from x, each word in `colour_of(word)`, the gap after a colon tightened."""
    space = get_text_width(font, ' ')
    for word in text.split(' '):
        x += _write(matrix, font, x, y, colour_of(word), word) + space
        if word.endswith(':'):
            x -= COLON_GAP_TRIM


def _centred(matrix, font, y: int, rgb, text: str, left: int = 0, right: Optional[int] = None) -> None:
    """`text` centred between columns `left` and `right` (the panel's width by default)."""
    room = (matrix.width if right is None else right) - left
    _draw_words(matrix, font, left + max((room - _words_width(font, text)) // 2, 0), y, text, lambda _: rgb)
