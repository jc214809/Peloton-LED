# python file: display/ui/pr_star.py

from .screen import Screen
from typing import List, Tuple

from driver import graphics
from display.display import color_dict
from utils import debug


class PrStarScreen(Screen):
    def __init__(self, color_key: str = "gold", fill: bool = True):
        self.color_key = color_key
        self.fill = fill

    def _unit_star_points(self, outer_radius: float = 0.5, inner_radius: float = 0.2, cx: float = 0.5, cy: float = 0.5) -> List[Tuple[float, float]]:
        import math

        points: List[Tuple[float, float]] = []
        num_points = 5
        angle_offset = -math.pi / 2
        for i in range(num_points * 2):
            angle = angle_offset + i * math.pi / num_points
            r = outer_radius if i % 2 == 0 else inner_radius
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            points.append((x, y))
        return points

    def _scale_points_to_matrix(self, points: List[Tuple[float, float]], width: int, height: int) -> List[Tuple[float, float]]:
        scaled: List[Tuple[float, float]] = []
        for x, y in points:
            px = x * (width - 1)
            py = y * (height - 1)
            px = max(0.0, min(width - 1, px))
            py = max(0.0, min(height - 1, py))
            scaled.append((px, py))
        return scaled

    def _round_points(self, points: List[Tuple[float, float]]) -> List[Tuple[int, int]]:
        return [(int(round(x)), int(round(y))) for x, y in points]

    def _scanline_fill_polygon(self, matrix, poly: List[Tuple[float, float]], color) -> None:
        height = matrix.height
        if not poly:
            return

        edges = []
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            if y1 == y2:
                continue
            if y1 < y2:
                y_min, y_max = y1, y2
                x_at_ymin = x1
                slope = (x2 - x1) / (y2 - y1)
            else:
                y_min, y_max = y2, y1
                x_at_ymin = x2
                slope = (x1 - x2) / (y1 - y2)
            edges.append((y_min, y_max, x_at_ymin, slope))

        if not edges:
            return

        for y in range(0, height):
            xs = []
            for y_min, y_max, x_at_ymin, slope in edges:
                if y_min <= y < y_max:
                    x = x_at_ymin + slope * (y - y_min)
                    xs.append(x)
            if not xs:
                continue
            xs.sort()
            for i in range(0, len(xs), 2):
                try:
                    x_start = int(round(xs[i]))
                    x_end = int(round(xs[i + 1]))
                except IndexError:
                    break
                x_start = max(0, min(matrix.width - 1, x_start))
                x_end = max(0, min(matrix.width - 1, x_end))
                try:
                    graphics.DrawLine(matrix, x_start, y, x_end, y, color)
                except Exception:
                    for x in range(x_start, x_end + 1):
                        try:
                            graphics.DrawPixel(matrix, x, y, color)
                        except Exception:
                            pass

    def render(self, matrix, state=None):
        color = color_dict.get(self.color_key) or color_dict.get("gold")

        w, h = matrix.width, matrix.height
        min_dim = min(w, h)
        pad_px = max(1.0, min_dim * 0.06)
        pad_unit = pad_px / max(min_dim - 1, 1)
        outer = max(0.0, 0.5 - pad_unit)
        inner = outer * 0.381966

        try:
            unit = self._unit_star_points(outer_radius=outer, inner_radius=inner, cx=0.5, cy=0.5)
            poly = self._scale_points_to_matrix(unit, w, h)
            if self.fill:
                self._scanline_fill_polygon(matrix, poly, color)
            else:
                poly_int = self._round_points(poly)
                n = len(poly_int)
                for i in range(n):
                    x1, y1 = poly_int[i]
                    x2, y2 = poly_int[(i + 1) % n]
                    try:
                        graphics.DrawLine(matrix, x1, y1, x2, y2, color)
                    except Exception:
                        dx = x2 - x1
                        dy = y2 - y1
                        steps = max(abs(dx), abs(dy), 1)
                        for s in range(steps + 1):
                            fx = int(round(x1 + dx * (s / steps)))
                            fy = int(round(y1 + dy * (s / steps)))
                            try:
                                graphics.DrawPixel(matrix, fx, fy, color)
                            except Exception:
                                pass
            return True
        except Exception as exc:
            debug.error("Failed to render PR star: %s", exc)
            return False
