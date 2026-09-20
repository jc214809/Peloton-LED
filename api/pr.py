from peloton.records import pr_types, is_pr_workout
from peloton.selection import latest_workout


def pr_from_last_day_workouts(workouts):
    return is_pr_workout(latest_workout(workouts))
