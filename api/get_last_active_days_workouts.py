"""Utilities to find the most-recent active-day workouts for a user.

This module exposes a simple function get_last_active_days_workouts which
returns a concrete list of workout objects for the user's most recent
active date.
"""

from typing import Any, Dict, List, Optional
import logging

from peloton.api import PelotonClient

logger = logging.getLogger("get_last_active_days_workouts")


def get_last_active_days_workouts(client: PelotonClient, user_id: str, limit: int = 50, days: int = 30) -> List[Dict[str, Any]]:
    """Return all workouts that occurred on the user's most-recent active date.

    This is intentionally simple: find the date part of the first available
    timestamp on each workout and return the workouts whose date equals the
    latest date found.
    """
    try:
        recent = client.get_recent_workouts(user_id, limit=limit, days=days) or []
    except Exception as exc:  # pragma: no cover - external call
        logger.warning("Could not fetch recent workouts for last-day lookup: %s", exc)
        return []

    if not recent:
        return []

    def _date_of(w: Dict[str, Any]) -> Optional[str]:
        for k in (
            "created_at",
            "start_time",
            "start_date",
            "start_time_iso8601",
            "start_date_local",
        ):
            v = w.get(k)
            if isinstance(v, str) and v:
                # split on 'T' or space, take date portion only
                return v.split("T", 1)[0].split(" ", 1)[0]
        return None

    workouts_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for w in recent:
        d = _date_of(w)
        if not d:
            continue
        workouts_by_date.setdefault(d, []).append(w)

    if not workouts_by_date:
        return []

    last_date = max(workouts_by_date.keys())
    logger.info("Found last workout date %s with %d workouts", last_date, len(workouts_by_date[last_date]))
    return list(workouts_by_date[last_date])


class GetLastActiveDaysWorkouts:
    """Callable helper class used by the test-suite.

    Tests expect a zero-arg constructor returning a callable instance that
    behaves like the original function. Provide a thin wrapper for
    backwards-compatibility.
    """

    def __call__(self, client: PelotonClient, user_id: str, limit: int = 50, days: int = 30):
        return get_last_active_days_workouts(client, user_id, limit=limit, days=days)
