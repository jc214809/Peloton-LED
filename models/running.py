"""Running-specific workout model definitions."""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .core import GeneralWorkout, format_decimal_with_unit, register_discipline


def _format_split_sec(sec: Optional[float]) -> str:
    if not isinstance(sec, (int, float)) or sec <= 0:
        return ""
    total_seconds = int(round(sec))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d} s/500m"


@register_discipline(
    "Running",
    "running",
    "running_outdoor",
    "Outdoor Run",
    "Tread Bootcamp",
)
@dataclass
class RunningWorkout(GeneralWorkout):
    avg_speed: Optional[float] = None
    avg_speed_unit: Optional[str] = None
    max_speed: Optional[float] = None
    max_speed_unit: Optional[str] = None
    avg_pace: Optional[float] = None
    avg_pace_unit: Optional[str] = None
    avg_incline: Optional[float] = None
    avg_incline_unit: Optional[str] = None
    max_incline: Optional[float] = None
    max_incline_unit: Optional[str] = None
    elevation: Optional[float] = None
    elevation_unit: Optional[str] = None

    @classmethod
    def columns(cls) -> List[Tuple[str, str]]:
        return super().columns() + [
            ("avg_speed", "Avg Speed"),
            ("max_speed", "Max Speed"),
            ("avg_pace", "Avg Pace"),
            ("avg_incline", "Avg Incline"),
            ("max_incline", "Max Incline"),
            ("elevation", "Elev"),
        ]

    @classmethod
    def perf_slugs(cls):
        return super().perf_slugs() | {
            "avg_speed",
            "max_speed",
            "avg_pace",
            "avg_incline",
            "max_incline",
            "elevation",
        }

    @classmethod
    def _specific_fields(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "avg_speed": row.get("avg_speed"),
            "avg_speed_unit": row.get("avg_speed_unit"),
            "max_speed": row.get("max_speed"),
            "max_speed_unit": row.get("max_speed_unit"),
            "avg_pace": row.get("avg_pace"),
            "avg_pace_unit": row.get("avg_pace_unit"),
            "avg_incline": row.get("avg_incline"),
            "avg_incline_unit": row.get("avg_incline_unit"),
            "max_incline": row.get("max_incline"),
            "max_incline_unit": row.get("max_incline_unit"),
            "elevation": row.get("elevation"),
            "elevation_unit": row.get("elevation_unit"),
        }

    def format_value(self, key: str) -> str:
        if key == "avg_speed":
            return format_decimal_with_unit(self.avg_speed, self.avg_speed_unit, 1)
        if key == "max_speed":
            return format_decimal_with_unit(self.max_speed, self.max_speed_unit, 1)
        if key == "avg_pace":
            return format_decimal_with_unit(self.avg_pace, self.avg_pace_unit, 2)
        if key == "avg_incline":
            return format_decimal_with_unit(self.avg_incline, self.avg_incline_unit, 1)
        if key == "max_incline":
            return format_decimal_with_unit(self.max_incline, self.max_incline_unit, 1)
        if key == "elevation":
            return format_decimal_with_unit(self.elevation, self.elevation_unit, 0)
        return super().format_value(key)
