from .screen import Screen
from display.display import loaded_fonts, color_dict, draw_centered_text


class StatusScreen(Screen):
    def render(self, matrix, state=None):
        text = {'loading': 'Loading', 'login_needed': 'Login needed',
                'offline': 'Offline', 'cached': 'Cached data',
                'empty': 'No workouts'}.get(state, 'Peloton')
        draw_centered_text(matrix, loaded_fonts.get('info'), text, matrix.height // 2,
                           color_dict['white'])
        return True
