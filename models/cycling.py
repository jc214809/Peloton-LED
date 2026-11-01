"""Cycling-specific performance metrics."""
from .core import GeneralWorkout, register_discipline


@register_discipline("Cycling", "cycling", "bike_bootcamp", "Bike Bootcamp")
class CyclingWorkout(GeneralWorkout):
    @classmethod
    def perf_slugs(cls):
        return super().perf_slugs() | {"avg_speed", "max_speed", "avg_cadence", "avg_resistance"}
