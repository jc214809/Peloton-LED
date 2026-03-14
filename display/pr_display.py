"""PR display renderer.

Draws a yellow star that scales to the current matrix size. Intended to be
shown when the most recent workout (today or yesterday) was a PR.

Usage: from display.pr_display import render_pr_star
Call render_pr_star(matrix) to display a filled gold star.
"""
from typing import List, Tuple

from driver import graphics
from display.display import color_dict
from utils import debug


def _unit_star_points(outer_radius: float = 0.5, inner_radius: float = 0.2, cx: float = 0.5, cy: float = 0.5) -> List[Tuple[float, float]]:
    """Return 10-point star points in unit coordinates (0..1).

    Uses a 5-point star (10 vertices alternating outer/inner).
    """
    import math

    points: List[Tuple[float, float]] = []
    # 5 points => 10 vertices (outer + inner alternating)
    num_points = 5
    angle_offset = -math.pi / 2  # start at the top
    for i in range(num_points * 2):
        angle = angle_offset + i * math.pi / num_points
        r = outer_radius if i % 2 == 0 else inner_radius
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        points.append((x, y))
    return points


def _scale_points_to_matrix(points: List[Tuple[float, float]], width: int, height: int) -> List[Tuple[float, float]]:
    """Scale unit (0..1) points to matrix coordinates (floats).

    Coordinates are clamped into the matrix bounds.
    """
    scaled: List[Tuple[float, float]] = []
    for x, y in points:
        px = x * (width - 1)
        py = y * (height - 1)
        px = max(0.0, min(width - 1, px))
        py = max(0.0, min(height - 1, py))
        scaled.append((px, py))
    return scaled


def _round_points(points: List[Tuple[float, float]]) -> List[Tuple[int, int]]:
    return [(int(round(x)), int(round(y))) for x, y in points]


def _scanline_fill_polygon(matrix, poly: List[Tuple[float, float]], color) -> None:
    """Simple scanline polygon fill using horizontal DrawLine calls."""
    height = matrix.height
    if not poly:
        return

    # Build edges
    edges = []
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if y1 == y2:
            continue
        # store as (y_min, y_max, x_at_ymin, slope_dx_dy)
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

    # For each scanline, collect intersections and draw spans
    for y in range(0, height):
        xs = []
        for y_min, y_max, x_at_ymin, slope in edges:
            # Using [y_min, y_max) convention to avoid double counting shared vertices
            if y_min <= y < y_max:
                x = x_at_ymin + slope * (y - y_min)
                xs.append(x)
        if not xs:
            continue
        xs.sort()
        # Pair up and draw horizontal lines
        for i in range(0, len(xs), 2):
            try:
                x_start = int(round(xs[i]))
                x_end = int(round(xs[i + 1]))
            except IndexError:
                break
            # clamp
            x_start = max(0, min(matrix.width - 1, x_start))
            x_end = max(0, min(matrix.width - 1, x_end))
            # DrawLine(x1, y, x2, y, color)
            try:
                graphics.DrawLine(matrix, x_start, y, x_end, y, color)
            except Exception:
                # Fallback to per-pixel draw if DrawLine isn't available
                for x in range(x_start, x_end + 1):
                    try:
                        graphics.DrawPixel(matrix, x, y, color)
                    except Exception:
                        pass


def render_pr_star(matrix, color_key: str = "gold", fill: bool = True) -> bool:
    """Render a PR star to the provided matrix.

    The star is defined in unit coordinates and scaled to the matrix size so
    it fills the available area appropriately for 32/64-high boards.

    Returns True on successful render, False otherwise.
    """
    color = color_dict.get(color_key) or color_dict.get("gold")

    matrix.Clear()

    # Determine radii to better fill wide vs tall matrices. Outer radius is
    # chosen so the star fills most of the smaller dimension.
    w, h = matrix.width, matrix.height
    min_dim = min(w, h)
    # Keep a small margin so points don't clip on tiny matrices.
    pad_px = max(1.0, min_dim * 0.06)
    pad_unit = pad_px / max(min_dim - 1, 1)
    outer = max(0.0, 0.5 - pad_unit)
    # Golden ratio inner/outer keeps proportions consistent.
    inner = outer * 0.381966

    try:
        unit = _unit_star_points(outer_radius=outer, inner_radius=inner, cx=0.5, cy=0.5)
        poly = _scale_points_to_matrix(unit, w, h)
        if fill:
            _scanline_fill_polygon(matrix, poly, color)
        else:
            # draw outline
            poly_int = _round_points(poly)
            n = len(poly_int)
            for i in range(n):
                x1, y1 = poly_int[i]
                x2, y2 = poly_int[(i + 1) % n]
                try:
                    graphics.DrawLine(matrix, x1, y1, x2, y2, color)
                except Exception:
                    # fallback to drawing pixels along the segment
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
    except Exception as exc:  # pragma: no cover - drawing errors depend on hardware
        debug.error("Failed to render PR star: %s", exc)
        return False
