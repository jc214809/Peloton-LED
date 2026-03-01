"""Model registry helpers."""
from .core import GeneralWorkout, get_model_for_discipline, register_discipline
from .cycling import CyclingWorkout
from .rowing import RowingWorkout
from .strength import StrengthWorkout
from .running import RunningWorkout

__all__ = [
    "GeneralWorkout",
    "get_model_for_discipline",
    "register_discipline",
    "RunningWorkout",
    "RowingWorkout",
    "CyclingWorkout",
    "StrengthWorkout",
]
