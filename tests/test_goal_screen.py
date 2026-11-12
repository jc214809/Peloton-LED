"""The weekly-goal page: big value, readable labels, 1 px margin on the longest goals."""
import pytest

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.goal_screen import MAX_VALUE_WIDTH, GoalScreen, value_font
from scripts.render_demo import ImageMatrix

CASES = [('workouts', 0, 5), ('workouts', 12, 7), ('minutes', 30, 300), ('minutes', 135, 300),
         ('minutes', 300, 300), ('minutes', 1200, 1500)]


def render(height, unit, current, target):
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    assert GoalScreen().render(matrix, {'title': 'Weekly Goal', 'current': current, 'target': target, 'unit': unit})
    return matrix.image


def text_pixels(image):
    """Lit pixels above the progress bar (the bar is drawn in its own rows)."""
    bar_top = image.height - 7
    return [(x, y) for y in range(bar_top - 1) for x in range(image.width) if image.getpixel((x, y)) != (0, 0, 0)]


@pytest.mark.parametrize('unit,current,target', CASES)
def test_64_row_goal_text_keeps_a_pixel_margin_on_each_side(unit, current, target):
    xs = [x for x, _ in text_pixels(render(64, unit, current, target))]
    assert min(xs) >= 1 and max(xs) <= 62


def test_64_row_goal_has_title_value_and_unit_bands_clear_of_the_bar():
    rows = sorted({y for _, y in text_pixels(render(64, 'minutes', 135, 300))})
    bands = [[rows[0]]]
    for y in rows[1:]:
        (bands[-1].append(y) if y - bands[-1][-1] == 1 else bands.append([y]))
    assert len(bands) == 3
    assert len(bands[1]) >= 10 and len(bands[0]) >= 6 and len(bands[2]) >= 6
    assert bands[-1][-1] < 57


def test_value_font_steps_down_only_when_too_wide():
    initialize_fonts(64)
    assert value_font('135/300') is loaded_fonts['goal_value']
    assert value_font('1200/1000') is loaded_fonts['title_bold']  # 9 characters: 7x13B is 63 wide
    assert value_font('100/150') is loaded_fonts['goal_value']
    assert get_text_width(loaded_fonts['goal_value'], '135/300') <= MAX_VALUE_WIDTH
