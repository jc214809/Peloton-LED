"""Rowing-specific workout model definitions."""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .core import GeneralWorkout, format_decimal_with_unit, register_discipline


def _format_split_sec(sec: Optional[float]) -> str:
    if not isinstance(sec, (int, float)) or sec <= 0:
        return ""
    total_seconds = int(round(sec))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d} s/500m"


@register_discipline("Rowing", "rowing", "caesar")
@dataclass
class RowingWorkout(GeneralWorkout):
    avg_speed: Optional[float] = None
    avg_speed_unit: Optional[str] = None
    avg_pace: Optional[float] = None
    avg_pace_unit: Optional[str] = None
    row_split_sec_per_500m: Optional[float] = None
    avg_stroke_rate: Optional[float] = None
    avg_stroke_rate_unit: Optional[str] = None

    @classmethod
    def columns(cls) -> List[Tuple[str, str]]:
        return super().columns() + [
            ("avg_speed", "Avg Speed"),
            ("avg_pace", "Avg Pace"),
            ("row_split_sec_per_500m", "Avg Split"),
            ("avg_stroke_rate", "Avg Stroke Rate"),
        ]

    @classmethod
    def _specific_fields(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "avg_speed": row.get("avg_speed"),
            "avg_speed_unit": row.get("avg_speed_unit"),
            "avg_pace": row.get("avg_pace"),
            "avg_pace_unit": row.get("avg_pace_unit"),
            "row_split_sec_per_500m": row.get("row_split_sec_per_500m"),
            "avg_stroke_rate": row.get("avg_stroke_rate"),
            "avg_stroke_rate_unit": row.get("avg_stroke_rate_unit"),
        }

    def format_value(self, key: str) -> str:
        if key == "avg_speed":
            return format_decimal_with_unit(self.avg_speed, self.avg_speed_unit, 1)
        if key == "avg_pace":
            return format_decimal_with_unit(self.avg_pace, self.avg_pace_unit, 2)
        if key == "row_split_sec_per_500m":
            return _format_split_sec(self.row_split_sec_per_500m)
        if key == "avg_stroke_rate":
            return format_decimal_with_unit(self.avg_stroke_rate, self.avg_stroke_rate_unit, 0)
        return super().format_value(key)
