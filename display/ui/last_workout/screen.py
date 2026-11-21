"""LastWorkoutScreen: the latest-workout page, composing the 64x64 and 64x32 layouts."""
from typing import Any, Optional

from display.display import loaded_fonts
from utils import debug
from ..screen import Screen
from .fonts import PageFonts
from .rotation import LAST_WORKOUT_DETAIL_INTERVAL_SECONDS
from .short_layout import render_short
from .tall_layout import render_tall


class LastWorkoutScreen(Screen):
    """Displays key stats from a workout summary on a 64x64 LED matrix.

    state should be the dict returned by peloton.stats.summaries.summarize_workout().

    The bottom HR/calories bar stays fixed for the whole screen. Everything
    above it goes through two phases:
      1. Intro (first detail_interval seconds): discipline/duration/title,
         plus the instructor's name underneath if there is one.
      2. Stats: the discipline title stays fixed at the top; duration/title/
         instructor clear and one stat at a time, large, cycles through the
         freed-up space below it, on the same "hold, then rise into place"
         pattern as UsernameScreen's details, instead of bundling every stat
         into small rows at once.
    """

    animated = True
    atomic_frames = True

    def __init__(self, detail_interval: float = LAST_WORKOUT_DETAIL_INTERVAL_SECONDS):
        self.elapsed = 0.0
        self.detail_interval = detail_interval

    def on_enter(self, matrix, state=None):
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += max(0, dt)

    def render(self, matrix, state: Optional[Any] = None) -> bool:
        summary = state or {}
        if not summary:
            return False

        title_font  = loaded_fonts.get("discipline")
        titles_font = loaded_fonts.get("titles")
        stat_font   = loaded_fonts.get("stats")

        if not title_font or not stat_font:
            debug.error("Fonts not loaded; call initialize_fonts() first")
            return False

        text_font = loaded_fonts.get("info") or titles_font or stat_font  # fallback if titles not loaded
        fonts = PageFonts(title_font, titles_font, text_font, stat_font)

        discipline = (summary.get("discipline") or "Workout").strip()
        layout = render_short if matrix.height < 64 else render_tall
        return layout(matrix, summary, discipline, fonts, self.elapsed, self.detail_interval)
