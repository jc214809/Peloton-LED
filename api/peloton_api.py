#!/usr/bin/env python3
"""Wrapper for Peloton API calls with safe error handling."""

import logging
from typing import Any, Dict, Optional, List

from peloton.api import PelotonClient

from api.get_last_active_days_workouts import get_last_active_days_workouts

logger = logging.getLogger("peloton-led.peloton_api")


class PelotonAPI:
    """Convenience wrapper around PelotonClient that handles common
    network-related exceptions and provides safe defaults.

    The class accepts an optional PelotonClient (None when cookies/session
    are missing) so callers don't need to guard for client presence.
    """

    def __init__(self, client: Optional[PelotonClient]):
        self.client = client

    def get_overview(self, user_id: Optional[str]) -> Dict[str, Any]:
        """Return the overview for a user or an empty dict on error.

        If the underlying client is missing or the user_id is falsy, an
        empty dict is returned and a debug message is emitted.
        """
        if not self.client or not user_id:
            logger.debug("Peloton client or user id missing; skipping overview fetch")
            return {}
        try:
            return self.client.get_overview(user_id) or {}
        except Exception as exc:  # pragma: no cover - external call
            logger.warning("Could not fetch overview: %s", exc)
            return {}

    def get_last_active_days_workouts(self, user_id: Optional[str], limit: int = 50, days: int = 30) -> List[Dict[str, Any]]:
        """Return recent workouts from the last `days` days for a user or an empty list on error.

        If the underlying client is missing or the user_id is falsy, an
        empty list is returned and a debug message is emitted.
        """
        if not self.client or not user_id:
            logger.debug("Peloton client or user id missing; skipping recent workouts fetch")
            return []
        try:
            return get_last_active_days_workouts(self.client, user_id, limit=limit, days=days) or []
        except Exception as exc:  # pragma: no cover - external call
            logger.warning("Could not fetch recent workouts for PR check: %s", exc)
            return []

    def get_workout_discipline_label(self, workout: Dict[str, Any]) -> str:
        """Return a human-friendly discipline label for a workout.

        This prefers the project's peloton.summaries.summarize_workout helper
        when available (imported lazily) and falls back to commonly-used
        fields found in workout/ride payloads. Always returns a non-empty
        string (defaults to "Workout").
        """
        if not isinstance(workout, dict):
            return "Workout"

        # Try the summarizer first (import lazily to avoid circular imports).
        try:
            from peloton.summaries import summarize_workout
        except Exception:
            summarize_workout = None

        if summarize_workout:
            try:
                summary = summarize_workout(workout, None)
                if isinstance(summary, dict):
                    disc = summary.get("discipline")
                    if disc:
                        return str(disc).strip()
            except Exception as exc:  # pragma: no cover - external call
                logger.debug("summarize_workout failed: %s", exc)

        # Fallback extraction from common fields present in Peloton payloads.
        ride = workout.get("ride") or {}
        disc_label = (
            (ride.get("fitness_discipline_display_name") or workout.get("fitness_discipline_display_name"))
            or (ride.get("fitness_discipline") or workout.get("fitness_discipline"))
            or workout.get("discipline")
            or ride.get("title")
        )
        if isinstance(disc_label, dict):
            disc_label = disc_label.get("name") or disc_label.get("display_name") or ""

        return (disc_label or "Workout").strip()
