from typing import Dict, Iterable, Optional


def is_pr_workout(workout: Dict) -> bool:
    """Return True if the given workout appears to be a personal record.

    Checks common fields returned by the Peloton API: explicit PR flags and
    achievement templates with the 'output_pr' slug.
    """
    if not workout:
        return False
    if bool(workout.get("is_total_work_personal_record")):
        return True
    if bool(workout.get("is_splits_personal_record")):
        return True
    for template in (workout.get("achievement_templates") or []):
        if (template.get("slug") or "").strip().lower() == "output_pr":
            return True
    return False


def latest_workout(workouts: Iterable[Dict]) -> Optional[Dict]:
    """Return the most recent workout from an iterable based on common timestamp
    fields. Returns None if no suitable timestamp is found.
    """
    def _ts_key(w: Dict) -> str:
        for k in (
            "created_at",
            "start_time",
            "start_date",
            "start_time_iso8601",
            "start_date_local",
        ):
            v = w.get(k)
            if isinstance(v, str) and v:
                return v
        return ""

    try:
        return max(workouts, key=_ts_key)
    except Exception:
        return None


def pr_from_last_day_workouts(workouts: Iterable[Dict]) -> bool:
    """Return True if the latest workout in the provided iterable appears to
    be a personal record.
    """
    latest = latest_workout(workouts)
    if not latest:
        return False
    return is_pr_workout(latest)
