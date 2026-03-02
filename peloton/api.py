"""Peloton API helpers (session management and workout fetch)."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

BASE = "https://api.onepeloton.com"


def load_cookie_dict(path: Path) -> Dict[str, str]:
    txt = path.read_text(encoding="utf-8").strip()
    parts = [p.strip() for p in txt.split(";") if p.strip()]
    cookies: Dict[str, str] = {}
    for part in parts:
        if "=" in part:
            key, val = part.split("=", 1)
            cookies[key] = val
    return cookies


def make_session(cookie_path: Path) -> requests.Session:
    cookies = load_cookie_dict(cookie_path)
    session = requests.Session()
    session.headers.update({"User-Agent": "peloton-led/1.0", "peloton-platform": "web"})
    session.cookies.update(cookies)
    return session


class PelotonClient:
    def __init__(self, session: requests.Session):
        self._session = session

    def get_me(self) -> Dict[str, Any]:
        resp = self._session.get(f"{BASE}/api/me", timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_workouts_page(self, user_id: str, limit: int, page: int = 0) -> Dict[str, Any]:
        params = {"joins": "ride,ride.instructor", "limit": limit, "page": page}
        resp = self._session.get(f"{BASE}/api/user/{user_id}/workouts", params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def get_recent_workouts(self, user_id: str, limit: int, days: int) -> List[Dict[str, Any]]:
        page = self.get_workouts_page(user_id, limit=limit, page=0)
        thr_ts = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        recent: List[Dict[str, Any]] = []
        for workout in page.get("data", []):
            ts = self._normalize_ts(workout.get("start_time"))
            if ts is None:
                continue
            if ts >= thr_ts:
                recent.append(workout)
        return recent

    def get_perf_graph(self, workout_id: str) -> Optional[Dict[str, Any]]:
        resp = self._session.get(f"{BASE}/api/workout/{workout_id}/performance_graph", params={"every_n": 5}, timeout=30)
        if not resp.ok:
            return None
        try:
            return resp.json()
        except Exception:
            return None

    @staticmethod
    def _normalize_ts(value: Any) -> Optional[float]:
        if value is None:
            return None
        timestamp = float(value)
        if timestamp > 1e12:
            timestamp /= 1000.0
        return timestamp
