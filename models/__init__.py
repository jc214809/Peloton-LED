"""Model registry helpers."""

from .core import GeneralWorkout, get_model_for_discipline, register_discipline
from .cycling import CyclingWorkout
from .rowing import RowingWorkout
from .running import RunningWorkout
from .strength import StrengthWorkout

__all__ = [
    'GeneralWorkout',
    'get_model_for_discipline',
    'register_discipline',
    'RunningWorkout',
    'RowingWorkout',
    'CyclingWorkout',
    'StrengthWorkout',
]
