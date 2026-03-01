"""Cycling-specific workout model definitions."""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .core import GeneralWorkout, format_decimal_with_unit, register_discipline


@register_discipline("Cycling", "cycling", "bike_bootcamp")
@dataclass
class CyclingWorkout(GeneralWorkout):
    avg_speed: Optional[float] = None
    avg_speed_unit: Optional[str] = None
    max_speed: Optional[float] = None
    max_speed_unit: Optional[str] = None
    avg_cadence: Optional[float] = None
    avg_cadence_unit: Optional[str] = None
    avg_resistance: Optional[float] = None
    avg_resistance_unit: Optional[str] = None

    @classmethod
    def columns(cls) -> List[Tuple[str, str]]:
        return super().columns() + [
            ("avg_speed", "Avg Speed"),
            ("max_speed", "Max Speed"),
            ("avg_cadence", "Avg Cadence"),
            ("avg_resistance", "Avg Res"),
        ]

    @classmethod
    def _specific_fields(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "avg_speed": row.get("avg_speed"),
            "avg_speed_unit": row.get("avg_speed_unit"),
            "max_speed": row.get("max_speed"),
            "max_speed_unit": row.get("max_speed_unit"),
            "avg_cadence": row.get("avg_cadence"),
            "avg_cadence_unit": row.get("avg_cadence_unit"),
            "avg_resistance": row.get("avg_resistance"),
            "avg_resistance_unit": row.get("avg_resistance_unit"),
        }

    def format_value(self, key: str) -> str:
        if key in ("avg_speed", "max_speed"):
            value = getattr(self, key)
            unit = getattr(self, f"{key}_unit")
            return format_decimal_with_unit(value, unit, 1)
        if key == "avg_cadence":
            return format_decimal_with_unit(self.avg_cadence, self.avg_cadence_unit, 0)
        if key == "avg_resistance":
            return format_decimal_with_unit(self.avg_resistance, self.avg_resistance_unit, 0)
        return super().format_value(key)
