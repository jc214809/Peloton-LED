"""Peloton API helpers (session management and workout fetch)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import requests
import logging

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

    @staticmethod
    def page_rows(page: Dict[str, Any]) -> List[Dict[str, Any]]:
        """The workouts on one history page; raises ValueError if malformed."""
        rows = page.get("data") or []
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Malformed workout page")
        return rows

    @staticmethod
    def is_last_page(page: Dict[str, Any], page_number: int, rows: List[Dict[str, Any]], page_size: int) -> bool:
        if not rows or page.get("show_next") is False:
            return True
        count = page.get("page_count")
        if isinstance(count, int) and page_number + 1 >= count:
            return True
        return len(rows) < page_size and page.get("show_next") is not True

    def iter_workout_pages(self, user_id: str, page_size: int, start_page: int = 0,
                           max_pages: int = 500) -> Iterator[Tuple[int, List[Dict[str, Any]], Dict[str, Any]]]:
        """Yield (page_number, rows, page) newest first, one page at a time.

        Callers keep only what they need from each page, so a full-history
        walk never holds every raw row at once. Stops at the oldest workout,
        or if Peloton repeats a page.
        """
        if min(page_size, max_pages) <= 0 or start_page < 0:
            raise ValueError("History limits must be positive")
        previous = None
        for page_number in range(start_page, start_page + max_pages):
            page = self.get_workouts_page(user_id, limit=page_size, page=page_number)
            rows = self.page_rows(page)
            fingerprint = tuple(str(w.get('id') or w) for w in rows)
            if rows and fingerprint == previous:
                logger.warning("Peloton repeated workout page %d; stopping the walk", page_number)
                return
            previous = fingerprint
            yield page_number, rows, page
            if self.is_last_page(page, page_number, rows, page_size):
                return
        logger.warning("Workout history walk stopped at the %d-page limit", max_pages)

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
