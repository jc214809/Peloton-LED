"""Strength-specific workout model definitions."""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .core import GeneralWorkout, register_discipline


@register_discipline("Strength", "strength", "cardio", "bootcamp")
@dataclass
class StrengthWorkout(GeneralWorkout):
    @classmethod
    def columns(cls) -> List[Tuple[str, str]]:
        return super().columns()

    @classmethod
    def _specific_fields(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        # Strength uses only general metrics for now
        return {}

    @classmethod
    def perf_slugs(cls):
        return super().perf_slugs()
