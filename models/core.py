"""Core workout model plus discipline registry."""
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Optional, Set, Tuple, Type

_REGISTRY: Dict[str, Type["GeneralWorkout"]] = {}


def register_discipline(*aliases: str):
    """Decorator to map discipline aliases to a subclass."""

    def decorator(cls: Type[GeneralWorkout]) -> Type[GeneralWorkout]:
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
@dataclass
class GeneralWorkout:
    workout_id: Optional[str]
    date_time: str
    tz: str
    discipline: str
    title: str
    instructor: str
    duration_min: Optional[int]

    distance: Optional[float] = None
    distance_unit: Optional[str] = None
    calories: Optional[float] = None
    calories_unit: Optional[str] = None
    total_output_kj: Optional[float] = None
    avg_output_w: Optional[float] = None
    hr_avg: Optional[float] = None
    hr_max: Optional[float] = None
    is_pr: bool = False

    extra: Dict[str, Any] = field(default_factory=dict)

    _common_keys: ClassVar[Tuple[str, ...]] = (
        "workout_id",
        "date_time",
        "tz",
        "discipline",
        "title",
        "instructor",
        "duration_min",
        "distance",
        "distance_unit",
        "calories",
        "calories_unit",
        "total_output_kj",
        "avg_output_w",
        "hr_avg",
        "hr_max",
        "is_pr",
    )

    @classmethod
    def _gather_common_fields(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        kw = {k: row.get(k) for k in cls._common_keys}
        extra = {k: v for k, v in row.items() if k not in cls._common_keys}
        kw["extra"] = extra
        return kw

    @classmethod
    def _specific_fields(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        return {}

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "GeneralWorkout":
        data = cls._gather_common_fields(row)
        data.update(cls._specific_fields(row))
        return cls(**data)

    @classmethod
    def perf_slugs(cls) -> Set[str]:
        return {
            "distance",
            "calories",
            "total_output",
            "avg_output",
            "hr_avg",
            "hr_max",
        }

    @classmethod
    def columns(cls) -> List[Tuple[str, str]]:
        return [
            ("date_time", "Date/Time"),
            ("discipline", "Discipline"),
            ("is_pr", "PR"),
            ("title", "Title"),
            ("instructor", "Instr."),
            ("duration_min", "Dur (m)"),
            ("distance", "Distance"),
            ("calories", "Calories"),
            ("total_output_kj", "Total (kJ)"),
            ("avg_output_w", "Avg W"),
            ("hr_avg", "HR avg"),
            ("hr_max", "HR max"),
        ]

    def format_value(self, key: str) -> str:
        if key == "distance":
            return format_decimal_with_unit(self.distance, self.distance_unit, 2)
        if key == "calories":
            return format_decimal_with_unit(self.calories, self.calories_unit, 0)
        if key == "total_output_kj":
            return _stringify(self.total_output_kj)
        if key == "avg_output_w":
            return _stringify(self.avg_output_w)
        if key in ("hr_avg", "hr_max"):
            return _stringify(getattr(self, key))
        if key == "duration_min":
            return _stringify(self.duration_min)
        if key == "is_pr":
            return "Yes" if self.is_pr else ""
        attr = getattr(self, key, None)
        if attr is not None:
            return str(attr)
        extra = self.extra.get(key)
        return "" if extra is None else str(extra)

    def to_markdown_row(self, columns: List[Tuple[str, str]]) -> List[str]:
        return [self.format_value(key) for key, _ in columns]


def format_decimal_with_unit(value: Any, unit: Optional[str], decimals: int) -> str:
    if isinstance(value, (int, float)) and unit:
        fmt = f"{{value:.{decimals}f}} {{unit}}"
        return fmt.format(value=value, unit=unit)
    if value is None:
        return ""
    return str(value)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
