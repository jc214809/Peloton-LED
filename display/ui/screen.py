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