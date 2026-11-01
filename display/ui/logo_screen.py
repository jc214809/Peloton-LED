# python file: display/ui/logo_screen.py

from typing import Optional, Any, Tuple
import logging

from PIL import Image, ImageOps

from .screen import Screen

logger = logging.getLogger(__name__)


class LogoScreen(Screen):
    """Screen that displays a static image (PNG/JPEG) full-screen on the matrix.

    The image is scaled to fit the matrix and centered on bg_color. If it can't
    be loaded, the screen draws nothing rather than crashing the manager.
    """
    def __init__(self, image_path: str, bg_color: Tuple[int, int, int] = (0, 0, 0)):
        self.image_path = image_path
        self.bg_color = bg_color
        self._pil_image = None

    def on_enter(self, matrix, state: Optional[Any] = None) -> None:
        """Load and prepare the image for the matrix when the screen becomes active."""
        try:
            img = Image.open(self.image_path).convert("RGBA")
        except Exception as exc:
            logger.warning("Could not open logo image %s: %s", self.image_path, exc)
            self._pil_image = None
            return
        target_w, target_h = matrix.width, matrix.height
        # Fit the image inside the matrix while preserving aspect ratio and center it on bg
        fitted = ImageOps.contain(img, (target_w, target_h), Image.LANCZOS)
        bg = Image.new("RGB", (target_w, target_h), self.bg_color)
        x = (target_w - fitted.width) // 2
        y = (target_h - fitted.height) // 2
        bg.paste(fitted.convert("RGB"), (x, y))
        self._pil_image = bg

    def render(self, matrix, state: Optional[Any] = None) -> bool:
        """Render the prepared image to the matrix. Returns True on success."""
        if self._pil_image is None:
            return False
        try:
            matrix.SetImage(self._pil_image)
            return True
        except Exception:
            logger.exception("Failed to render logo to matrix")
            return False
