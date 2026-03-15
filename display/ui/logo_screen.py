# python file: display/ui/logo_screen.py

from typing import Optional, Any, Tuple
from .screen import Screen
import logging

logger = logging.getLogger(__name__)

class LogoScreen(Screen):
    """Screen that displays a static image (PNG/JPEG) full-screen on the matrix.

    The screen attempts to load the image with Pillow and scale it to the
    matrix resolution. If Pillow isn't available or the image can't be loaded,
    the screen becomes a no-op but will not crash the manager.
    """
    def __init__(self, image_path: str, bg_color: Tuple[int, int, int] = (0, 0, 0)):
        self.image_path = image_path
        self.bg_color = bg_color
        self._pil_image = None

    def _matrix_size(self, matrix) -> Optional[Tuple[int, int]]:
        # Try common attributes first
        w = getattr(matrix, "width", None)
        h = getattr(matrix, "height", None)
        if w and h:
            return (w, h)
        # rpi-rgb-led-matrix exposes options with rows/cols/chain_length/parallel
        opts = getattr(matrix, "options", None)
        if opts is not None:
            try:
                cols = getattr(opts, "cols", None) or getattr(opts, "cols", None)
                rows = getattr(opts, "rows", None)
                chain = getattr(opts, "chain_length", 1)
                parallel = getattr(opts, "parallel", 1)
                if cols and rows:
                    return (int(cols) * int(chain), int(rows) * int(parallel))
            except Exception:
                pass
        # last resort: try options on matrix directly
        cols = getattr(matrix, "cols", None)
        rows = getattr(matrix, "rows", None)
        chain = getattr(matrix, "chain_length", 1)
        parallel = getattr(matrix, "parallel", 1)
        if cols and rows:
            return (int(cols) * int(chain), int(rows) * int(parallel))
        return None

    def on_enter(self, matrix, state: Optional[Any] = None) -> None:
        """Load and prepare the image for the matrix when the screen becomes active."""
        try:
            from PIL import Image, ImageOps
        except Exception:
            logger.warning("Pillow not available; LogoScreen will be inert")
            self._pil_image = None
            return

        try:
            img = Image.open(self.image_path).convert("RGBA")
        except Exception as exc:
            logger.warning("Could not open logo image %s: %s", self.image_path, exc)
            self._pil_image = None
            return

        size = self._matrix_size(matrix)
        if size is None:
            # If we can't determine the matrix size, keep the original image
            logger.debug("Could not determine matrix size; storing original image")
            self._pil_image = img.convert("RGB")
            return

        target_w, target_h = size
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
            # Prefer SetImage for rpi-rgb-led-matrix
            if hasattr(matrix, "SetImage"):
                matrix.SetImage(self._pil_image)
            elif hasattr(matrix, "SetBitmap"):
                # some drivers might provide alternative names
                matrix.SetBitmap(self._pil_image)
            elif hasattr(matrix, "SetImagePIL"):
                matrix.SetImagePIL(self._pil_image)
            else:
                # Try common draw/update methods
                if hasattr(matrix, "image"):
                    # a hypothetical canvas attribute
                    try:
                        matrix.image.paste(self._pil_image)
                    except Exception:
                        pass
                # As a last resort try setting attributes used by the matrix viewers
                # Many bindings accept a PIL Image directly via SetImage, so failing
                # that we simply return False.
                return False
            return True
        except Exception:
            logger.exception("Failed to render logo to matrix")
            return False
