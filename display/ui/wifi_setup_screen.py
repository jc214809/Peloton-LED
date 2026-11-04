"""The Wi-Fi setup screen, while comitup's setup hotspot is up (utils/wifi_setup.py): two pages
in turn, the open hotspot to join, then where the settings page is on it."""
import re

from display.display import color_dict, draw_centered_text, get_text_width, loaded_fonts
from driver import graphics
from utils.wifi_setup import HOTSPOT_ADDRESS
from .screen import Screen

# The settings server's port (settings_page/server.py PORT); not imported, to keep the display
# free of the server's imports.
SETTINGS_ADDRESS = f'{HOTSPOT_ADDRESS}:8080'
WAIT_BLUE = graphics.Color(80, 170, 255)
LINE_GAP = 2


def name_lines(font, name, width):
    """The hotspot name in as few lines as fit: filled word by word, breaking after hyphens
    ("peloton-" / "basement-board-" / "setup"), and a piece still too wide wherever it has to."""
    pieces = []
    for word in re.findall(r'[^-\s]*-|[^-\s]+', name):
        while get_text_width(font, word) > width:  # one piece too wide: split it by letters
            cut = max(1, next(i for i in range(len(word), 0, -1) if get_text_width(font, word[:i]) <= width))
            pieces.append(word[:cut])
            word = word[cut:]
        pieces.append(word)
    lines = ['']
    for piece in pieces:
        if lines[-1] and get_text_width(font, lines[-1] + piece) > width:
            lines.append('')
        lines[-1] += piece
    return [line for line in lines if line]


class WifiSetupScreen(Screen):
    """state: {"name": the hotspot's name, "page": 0 (join it) or 1 (the settings page's address)}."""

    def render(self, matrix, state=None):
        state = state if isinstance(state, dict) else {}
        title_font = loaded_fonts.get('titles')
        small = loaded_fonts.get('info')
        if state.get('page'):
            rows = [(title_font, color_dict['gold'], 'Settings'), (small, color_dict['white'], 'Browse to'),
                    (small, WAIT_BLUE, SETTINGS_ADDRESS)]
        else:
            name = str(state.get('name') or '')
            rows = [(title_font, color_dict['gold'], 'Wi-Fi setup'), (small, color_dict['white'], 'Join')]
            rows += [(small, WAIT_BLUE, line) for line in name_lines(small, name, matrix.width - 2)]
        if sum(font.height for font, _, _ in rows) > matrix.height:
            rows = [row for row in rows if row[2] != 'Join']  # a long name on 32 rows: the name matters more
        heights = sum(font.height for font, _, _ in rows)
        gap = max(0, min(LINE_GAP, (matrix.height - heights) // max(1, len(rows) - 1)))
        top = max(0, (matrix.height - heights - gap * (len(rows) - 1)) // 2)
        for font, color, text in rows:
            draw_centered_text(matrix, font, text, top + font.baseline, color)
            top += font.height + gap
        return True
