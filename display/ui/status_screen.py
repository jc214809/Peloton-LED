from display.display import color_dict, draw_centered_text, loaded_fonts

from .screen import Screen


class StatusScreen(Screen):
    def render(self, matrix, state=None):
        text = {
            'loading': 'Loading',
            'login_needed': 'Login needed',
            'offline': 'Offline',
            'cached': 'Cached data',
            'empty': 'No workouts',
        }.get(state, 'Peloton')
        draw_centered_text(matrix, loaded_fonts.get('info'), text, matrix.height // 2, color_dict['white'])
        return True
