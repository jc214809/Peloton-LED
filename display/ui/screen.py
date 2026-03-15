# python file: display/ui/screen.py

from abc import ABC, abstractmethod
from typing import Any, Optional

class Screen(ABC):
    """Abstract screen interface for all renderers."""

    @abstractmethod
    def render(self, matrix, state: Optional[Any] = None) -> bool:
        """Draw current view to matrix. `state` can be any context (user/workout)."""
        pass

    def update(self, dt: float) -> None:
        """Optional animation update called on tick; dt is seconds since last call."""
        return

    def handle_event(self, event: Any) -> Optional[str]:
        """Optional input handler; can return a navigation command or None."""
        return None

    def on_enter(self, matrix, state: Optional[Any] = None) -> None:
        """Called when this screen becomes active. Default no-op.

        Override to perform setup. Matrix is provided for convenience.
        """
        return

    def on_exit(self, matrix) -> None:
        """Called when this screen is deactivated. Default clears the matrix.

        Override to perform teardown. Default behavior clears the matrix to
        ensure the previous screen doesn't leave artifacts on the display.
        """
        import logging
        logger = logging.getLogger(__name__)

        # Quick sanity log so you know this ran
        logger.debug("on_exit called for screen %s, matrix=%r", getattr(self, "__class__", None), matrix)

        try:
            # Prefer canonical Clear if present
            if hasattr(matrix, "Clear"):
                matrix.Clear()
            # fallback lowercase
            elif hasattr(matrix, "clear"):
                matrix.clear()
            # some APIs use fill(0) or fill((0,0,0))
            elif hasattr(matrix, "fill"):
                try:
                    matrix.fill(0)
                except TypeError:
                    matrix.fill((0, 0, 0))
            # some drivers use a canvas object (example: canvas.Clear())
            elif hasattr(matrix, "ClearScreen"):
                matrix.ClearScreen()

            # Force a refresh/update if available
            if hasattr(matrix, "Show"):
                try:
                    matrix.Show()
                except Exception:
                    # Show might not be needed; ignore failures here (they'll be logged below)
                    pass
            elif hasattr(matrix, "show"):
                try:
                    matrix.show()
                except Exception:
                    pass
            elif hasattr(matrix, "SwapOnVSync"):
                try:
                    matrix.SwapOnVSync()
                except Exception:
                    pass

        except Exception:
            logger.exception("Failed to clear/update matrix in on_exit")
            # In development you might want to re-raise so you notice the problem:
            # raise
