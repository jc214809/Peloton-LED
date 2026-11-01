"""Rowing performance metrics."""
from .core import GeneralWorkout, register_discipline


@register_discipline("Rowing", "rowing", "caesar", "Row Bootcamp", "row_bootcamp")
class RowingWorkout(GeneralWorkout):
    @classmethod
    def perf_slugs(cls):
        return super().perf_slugs() | {"avg_speed", "avg_pace", "avg_split_pace", "avg_stroke_rate"}
