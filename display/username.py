"""Simple renderer that writes a single username to the LED board.

This file replaces display/user_name.py and uses "username" as a single word
for consistency.
"""

from driver import graphics
from display.display import loaded_fonts, color_dict, get_text_width
from utils import debug


def render_username(matrix, username, font_key, color_key):
    """Draw the username centered on the board."""

    text = (username or "").strip() or "Peloton Member"
    font = loaded_fonts.get(font_key)
    if font is None:
        debug.error("Font %s is not loaded; call initialize_fonts() first.", font_key)
        return False

    color = color_dict.get(color_key) or color_dict.get("white")

    matrix.Clear()
    text_width = get_text_width(font, text)
    text_height = getattr(font, "height", None)
    if text_height is None:
        text_height = 8
    start_x = max((matrix.width - text_width) // 2, 0)
    start_y = max((matrix.height - text_height) // 2, 0)
    graphics.DrawText(matrix, font, start_x, start_y, color, text)

    return True
