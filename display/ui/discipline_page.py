# python file: display/ui/discipline_page.py

from .screen import Screen
from typing import Optional, Dict, Any

from driver import graphics
from display.display import color_dict, get_text_width, loaded_fonts, wrap_text, draw_centered_text
from utils import debug


class DisciplinePageScreen(Screen):
    def __init__(self,
                 title_font_key: str = "park",
                 number_font_key: str = "countdown",
                 color_key: str = "red"):
        self.title_font_key = title_font_key
        self.number_font_key = number_font_key
        self.color_key = color_key

    def render(self, matrix, state: Optional[Dict[str, Any]] = None):
        """Render a discipline page.

        state can be a dict containing:
        - discipline: str
        - count: int
        - title_font_key, number_font_key, color_key (optional overrides)
        """
        title_font_key = (state or {}).get("title_font_key") or self.title_font_key
        number_font_key = (state or {}).get("number_font_key") or self.number_font_key
        color_key = (state or {}).get("color_key") or self.color_key

        title_font = loaded_fonts.get(title_font_key)
        number_font = loaded_fonts.get(number_font_key)

        if not title_font or not number_font:
            missing = title_font_key if not title_font else number_font_key
            debug.error("Font %s is not loaded; call initialize_fonts() first.", missing)
            return False

        color = color_dict.get(color_key, color_dict.get("white"))

        discipline_name = (state or {}).get("discipline") or "Discipline"
        count_val = (state or {}).get("count")
        count_text = f"{int(count_val):,}" if isinstance(count_val, (int, float)) else str(count_val or "0")

        max_name_width = max(matrix.width - 4, 4)
        title_lines = wrap_text(title_font, discipline_name, max_name_width, padding=2)
        if not title_lines:
            title_lines = [discipline_name]

        debug.info("Discipline '%s' wrapped into %d line(s): %s", discipline_name, len(title_lines), title_lines)

        top_padding = 20
        line_spacing = 2
        current_y = top_padding
        for line in title_lines:
            draw_centered_text(matrix, title_font, line, current_y, graphics.Color(242, 5, 5))
            current_y += getattr(title_font, "height", 9) + line_spacing

        remaining_top = current_y + line_spacing
        bottom_padding = max(6, line_spacing)
        remaining_height = max(matrix.height - remaining_top - bottom_padding, getattr(number_font, "height", 8))
        center_y = remaining_top + remaining_height // 2
        draw_centered_text(matrix, number_font, count_text, center_y, graphics.Color(242, 5, 5))

        return True
