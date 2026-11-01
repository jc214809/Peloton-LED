"""Discipline registry: which performance-graph metrics each discipline reports."""
from typing import Dict, Optional, Set, Type

_REGISTRY: Dict[str, Type["GeneralWorkout"]] = {}


def register_discipline(*aliases: str):
    """Decorator to map discipline aliases to a subclass."""

    def decorator(cls: "Type[GeneralWorkout]") -> "Type[GeneralWorkout]":
        for alias in aliases:
            _REGISTRY[alias.strip().lower()] = cls
        return cls

    return decorator


def get_model_for_discipline(discipline: Optional[str]) -> Type["GeneralWorkout"]:
    """Return the registered model for a discipline (case-insensitive)."""
    if discipline is None:
        return GeneralWorkout
    return _REGISTRY.get(discipline.strip().lower(), GeneralWorkout)


@register_discipline("general")
class GeneralWorkout:
    @classmethod
    def perf_slugs(cls) -> Set[str]:
        """Summary slugs read from the workout's performance graph."""
        return {"distance", "calories", "total_output", "avg_output", "hr_avg", "hr_max"}
