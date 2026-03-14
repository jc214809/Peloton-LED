# python file: display/ui/pr_star.py

from .screen import Screen
from display.pr_display import render_pr_star
from utils import debug


class PrStarScreen(Screen):
    def __init__(self, color_key: str = "gold", fill: bool = True):
        self.color_key = color_key
        self.fill = fill

    def render(self, matrix, state=None):
        try:
            return render_pr_star(matrix, color_key=self.color_key, fill=self.fill)
        except Exception as exc:
            debug.error("PrStarScreen failed to render: %s", exc)
            return False
