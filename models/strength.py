"""Strength and other no-machine classes: only the general metrics."""
from .core import GeneralWorkout, register_discipline


@register_discipline(
    "Strength", "strength", "Cardio", "cardio", "bootcamp",
    "Yoga", "yoga", "Meditation", "meditation", "Stretching", "stretching",
    "Pilates", "pilates", "Barre", "barre", "Boxing", "boxing",
    "Dance Cardio", "dance_cardio", "Mobility", "mobility",
)
class StrengthWorkout(GeneralWorkout):
    pass
