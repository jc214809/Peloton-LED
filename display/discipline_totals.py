"""Render discipline totals (name + workout count) on the LED board."""

from typing import Optional

from driver import graphics
from display.display import color_dict, get_text_width, loaded_fonts, wrap_text
from utils import debug


def _draw_centered_text(matrix, font, text, y, color):
    if font is None:
        return

    width = get_text_width(font, text)
    x = max((matrix.width - width) // 2, 0)
    graphics.DrawText(matrix, font, x, y, color, text)


def render_discipline_page(matrix, discipline_name: str, count: Optional[int],
    title_font_key: str = "park",
    number_font_key: str = "countdown",
    color_key: str = "red",
):
    """Display the discipline name and workout count on the board."""

    title_font = loaded_fonts.get(title_font_key)
    number_font = loaded_fonts.get(number_font_key)

    if not title_font or not number_font:
        missing = title_font_key if not title_font else number_font_key
        debug.error("Font %s is not loaded; call initialize_fonts() first.", missing)
        return False

    color = color_dict.get(color_key, color_dict.get("white"))

    matrix.Clear()

    discipline_text = (discipline_name or "").strip() or "Discipline"
    count_text = f"{int(count):,}" if isinstance(count, (int, float)) else str(count or "0")

    max_name_width = max(matrix.width - 4, 4)
    title_lines = wrap_text(title_font, discipline_text, max_name_width, padding=2)
    if not title_lines:
        title_lines = [discipline_text]

    debug.info("Discipline '%s' wrapped into %d line(s): %s", discipline_text, len(title_lines), title_lines)

    top_padding = 20
    line_spacing = 2
    current_y = top_padding
    for line in title_lines:
        _draw_centered_text(matrix, title_font, line, current_y, graphics.Color(242, 5, 5))
        current_y += getattr(title_font, "height", 9) + line_spacing

    remaining_top = current_y + line_spacing
    bottom_padding = max(6, line_spacing)
    remaining_height = max(matrix.height - remaining_top - bottom_padding, getattr(number_font, "height", 8))
    center_y = remaining_top + remaining_height // 2
    _draw_centered_text(matrix, number_font, count_text, center_y, graphics.Color(242, 5, 5))

    return True
