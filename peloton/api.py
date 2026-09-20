"""Peloton API helpers (session management and workout fetch)."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import logging
from .timestamps import workout_timestamp, parse_timestamp

logger = logging.getLogger("peloton-led.api")

BASE = "https://api.onepeloton.com"


def load_token(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def make_session(token_path: Path) -> requests.Session:
    token = load_token(token_path)
    if not token:
        raise ValueError("Peloton token file is empty")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "peloton-led/1.0",
        "peloton-platform": "web",
        "Authorization": f"Bearer {token}",
    })
    return session



class PelotonClient:
    def __init__(self, session: requests.Session):
        self._session = session
        self.login_required = False

    def _get(self, url: str, **kwargs) -> requests.Response:
        response = self._session.get(url, **kwargs)
        if response.status_code == 401:
            self.login_required = True
        elif response.ok:
            self.login_required = False
        return response

    def close(self) -> None:
        self._session.close()

    def get_me(self) -> Dict[str, Any]:
        resp = self._get(f"{BASE}/api/me", timeout=15)
        resp.raise_for_status()
        return self._object(resp)

    def get_workouts_page(self, user_id: str, limit: int, page: int = 0) -> Dict[str, Any]:
        params = {"joins": "ride,ride.instructor", "limit": limit, "page": page}
        resp = self._get(f"{BASE}/api/user/{user_id}/workouts", params=params, timeout=20)
        resp.raise_for_status()
        return self._object(resp)

    def get_recent_workouts(self, user_id: str, limit: int = 200, days: int = 90,
                            page_size: int = 50, max_pages: int = 10) -> List[Dict[str, Any]]:
        if min(limit, days, page_size, max_pages) <= 0:
            raise ValueError("History limits must be positive")
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent, seen, pages_seen = [], set(), set()
        self.history_truncated = False
        for page_number in range(max_pages):
            page = self.get_workouts_page(user_id, limit=page_size, page=page_number)
            rows = page.get("data") or []
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Malformed workout page")
            if not rows:
                return recent
            fingerprint = tuple(str(w.get('id') or w) for w in rows)
            if fingerprint in pages_seen:
                break
            pages_seen.add(fingerprint)
            timestamps = []
            for workout in rows:
                stamp = workout_timestamp(workout)
                if stamp is not None:
                    timestamps.append(stamp)
                identity = workout.get("id")
                if not stamp or stamp < cutoff or (identity and identity in seen):
                    continue
                if identity:
                    seen.add(identity)
                recent.append(workout)
                if len(recent) >= limit:
                    self.history_truncated = True
                    logger.warning("Workout history reached the %d-workout limit", limit)
                    return recent
            # Only stop on the date cutoff when the entire page is older.
            if timestamps and len(timestamps) == len(rows) and max(timestamps) < cutoff:
                return recent
            if page.get("show_next") is False:
                return recent
            count = page.get("page_count")
            if isinstance(count, int) and page_number + 1 >= count:
                return recent
            if len(rows) < page_size and page.get("show_next") is not True:
                return recent
        self.history_truncated = True
        logger.warning("Workout history search stopped at a repeated page or page limit")
        return recent

    def get_all_workouts(self, user_id: str, page_size: int = 50, max_pages: int = 200,
                        stop_at_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Walk the full workout history, oldest cutoff-free, for one-time or incremental pulls.

        With stop_at_id, paging stops as soon as that workout is seen again,
        so a caller who already counted everything up to a known newest
        workout only pays for the pages of workouts newer than it.
        """
        if min(page_size, max_pages) <= 0:
            raise ValueError("History limits must be positive")
        workouts, seen, pages_seen = [], set(), set()
        self.history_truncated = False
        for page_number in range(max_pages):
            page = self.get_workouts_page(user_id, limit=page_size, page=page_number)
            rows = page.get("data") or []
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Malformed workout page")
            if not rows:
                return workouts
            fingerprint = tuple(str(w.get('id') or w) for w in rows)
            if fingerprint in pages_seen:
                break
            pages_seen.add(fingerprint)
            for workout in rows:
                identity = workout.get("id")
                if identity and identity == stop_at_id:
                    return workouts
                if identity and identity in seen:
                    continue
                if identity:
                    seen.add(identity)
                workouts.append(workout)
            if page.get("show_next") is False:
                return workouts
            count = page.get("page_count")
            if isinstance(count, int) and page_number + 1 >= count:
                return workouts
            if len(rows) < page_size and page.get("show_next") is not True:
                return workouts
        self.history_truncated = True
        logger.warning("Full workout history walk stopped at the %d-page limit", max_pages)
        return workouts

    def get_perf_graph(self, workout_id: str) -> Optional[Dict[str, Any]]:
        resp = self._get(f"{BASE}/api/workout/{workout_id}/performance_graph", params={"every_n": 5}, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        try:
            return self._object(resp)
        except Exception:
            return None

    def get_overview(self, user_id: str) -> Dict[str, Any]:
        resp = self._get(f"{BASE}/api/user/{user_id}/overview", timeout=20)
        resp.raise_for_status()
        return self._object(resp)

    @staticmethod
    def _object(response):
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Expected a Peloton JSON object")
        return data


    @staticmethod
    def _normalize_ts(value: Any) -> Optional[float]:
        timestamp = parse_timestamp(value)
        return timestamp.timestamp() if timestamp else None
