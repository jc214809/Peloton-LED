# python file: display/ui/screen.py

import logging
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

    def on_enter(self, matrix, state: Optional[Any] = None) -> None:
        """Called when this screen becomes active. Default no-op.

        Override to perform setup. Matrix is provided for convenience.
        """
        return

    def on_exit(self, matrix) -> None:
        """Called when this screen is deactivated. Default clears the matrix so
        the previous screen doesn't leave artifacts behind."""
        try:
            matrix.Clear()
        except Exception:
            logging.getLogger(__name__).exception("Failed to clear the matrix in on_exit")
