"""Render synthetic screens to a PNG contact sheet, with no server or API calls."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Importing unittest selects the emulator graphics without initializing a matrix.
import unittest
from PIL import Image, ImageDraw
from display.display import initialize_fonts
from display.ui.last_workout_screen import LastWorkoutScreen
from display.ui.discipline_page import DisciplinePageScreen
from display.ui.lifetime_overview import LifetimeOverviewScreen
from display.ui.username import UsernameScreen
from display.ui.pr_celebration import BURST_SECONDS, SETTLE_SECONDS, PrCelebrationScreen
from display.ui.manager import ScreenManager
from peloton.demo import demo_data
from peloton.summaries import summarize_workout
from peloton.totals import extract_discipline_totals, lifetime_overview_pages


class ImageMatrix:
    def __init__(self, width=64, height=64):
        self.width, self.height = width, height
        self.Clear()

    def Clear(self):
        self.image = Image.new('RGB', (self.width, self.height))

    def SetPixel(self, x, y, r, g, b):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.image.putpixel((int(x), int(y)), (int(r), int(g), int(b)))


def render_contact_sheet(destination):
    data = demo_data()
    panels = []
    for height in (64, 32):
        initialize_fonts(height)
        matrix = ImageMatrix(height=height)
        samples = [(w['ride']['fitness_discipline'], LastWorkoutScreen(),
                    summarize_workout(w, data['performance'][w['id']])) for w in data['workouts']]
        samples += [('Login needed', LastWorkoutScreen(), samples[0][2]),
                    ('Username', UsernameScreen('info'), 'Demo Rider'),
                    ('PR', PrCelebrationScreen(), next(s for _, _, s in samples if s.get('is_pr')))]
        if height == 64:
            lifetime = lifetime_overview_pages(extract_discipline_totals(data['overview']))
            samples += [(f'Lifetime {index + 1}', LifetimeOverviewScreen(),
                         {'items': items, 'page': index + 1, 'pages': len(lifetime)})
                        for index, items in enumerate(lifetime)]
        else:
            samples += [('Totals', DisciplinePageScreen(), {'discipline': 'Bike Bootcamp', 'count': 1234})]
        for label, screen, state in samples:
            manager = ScreenManager(matrix, initial=screen, login_required=lambda: label == 'Login needed')
            if label == 'PR':
                screen.update(BURST_SECONDS + SETTLE_SECONDS + 0.5)  # show the card, not the burst
            manager.tick(state)
            tile = Image.new('RGB', (272, 294), '#202020')
            tile.paste(matrix.image.resize((256, height * 4), Image.Resampling.NEAREST), (8, 26))
            ImageDraw.Draw(tile).text((8, 7), f'{height} rows: {label}', fill='white')
            panels.append(tile)
    sheet = Image.new('RGB', (272 * 6, 294 * 3), '#202020')
    for i, panel in enumerate(panels):
        sheet.paste(panel, ((i % 6) * 272, (i // 6) * 294))
    sheet.save(destination)


if __name__ == '__main__':
    render_contact_sheet(sys.argv[1] if len(sys.argv) > 1 else '/tmp/peloton-demo.png')
