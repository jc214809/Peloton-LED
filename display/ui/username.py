# python file: display/ui/username.py

from .screen import Screen
from display.display import loaded_fonts, color_dict, get_text_width
from utils import debug
from driver import graphics

class UsernameScreen(Screen):
    def __init__(self, font_key="park", color_key="white"):
        self.font_key = font_key
        self.color_key = color_key

    def render(self, matrix, state=None):
        username = (state or {}).get("username") if isinstance(state, dict) else state
        text = (username or "").strip() or "Peloton Member"
        font = loaded_fonts.get(self.font_key)
        if not font:
            debug.error("Font %s is not loaded", self.font_key)
            return False
        color = color_dict.get(self.color_key, color_dict["white"])
        matrix.Clear()
        w = get_text_width(font, text)
        h = getattr(font, "height", 8)
        start_x = max((matrix.width - w) // 2, 0)
        start_y = max((matrix.height - h) // 2, 0)
        graphics.DrawText(matrix, font, start_x, start_y, color, text)
        return True
