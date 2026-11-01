"""Running, walking and hiking performance metrics."""
from .core import GeneralWorkout, register_discipline


@register_discipline(
    "Running",
    "running",
    "running_outdoor",
    "Outdoor Run",
    "Tread Bootcamp", "Walking", "walking_outdoor", "Outdoor Walk",
    "Hiking", "hiking",
)
class RunningWorkout(GeneralWorkout):
    @classmethod
    def perf_slugs(cls):
        return super().perf_slugs() | {
            "avg_speed", "max_speed", "avg_pace", "avg_incline", "max_incline", "elevation"}
