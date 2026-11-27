"""Peloton API helpers (session management and workout fetch)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger('peloton-led.api')

BASE = 'https://api.onepeloton.com'
# Club Peloton's level and points: an undocumented host Peloton's web app calls (docs/PELOTON-API.md).
MEMBERS_SCORE = 'https://members-score.onepeloton.com'
# Peloton's GraphQL gateway: Lanebreak ("Odyssey") lives here (docs/PELOTON-API.md). Values go in as variables.
GRAPHQL = 'https://gql-graphql-gateway.prod.k8s.onepeloton.com/graphql'
LANEBREAK_RUN_QUERY = (
    'query LanebreakRun($id: ID!) { odysseyWorkout(id: $id) { __typename '
    '... on OdysseyWorkoutSuccessResponse { workout { score difficulty completionPercent } } } }'
)
LANEBREAK_TRACKS_QUERY = 'query LanebreakTracks { levels { ... on LevelListSuccessResponse { levels { id title duration volume } } } }'
LANEBREAK_PLACE_QUERY = (
    'query LanebreakPlace($request: LeaderboardRequestInput!) { odysseyLeaderboard(leaderboardRequest: $request) { '
    '... on OdysseyLeaderboardListSuccessResponse { leaderboard { count extraWorkoutEntry { rank workoutId } } } } }'
)
LANEBREAK_MINE_QUERY = (
    'query LanebreakMine($request: UserLeaderboardRequestInput!) { odysseyUserLeaderboard(userLeaderboardRequest: $request) { '
    '... on OdysseyLeaderboardListSuccessResponse { leaderboard { count leaderboard { workoutId } } } } }'
)
# The rider's newest runs on a track looked at when checking that a run is on it (newest first, so a new run leads).
LANEBREAK_MINE_SIZE = 50
LANEBREAK_LANES_QUERY = (
    'query LanebreakLanes { odysseyConfiguration { __typename '
    '... on OdysseyTreadConfiguration { difficultyConfigs { slug laneConfigs { index minIncline maxIncline } } } '
    '... on OdysseyBikeConfiguration { difficultyConfigs { slug laneConfigs { index minResistance maxResistance } } } } }'
)


def load_token(path: Path) -> str:
    return path.read_text(encoding='utf-8').strip()


def make_session(token_path: Path) -> requests.Session:
    token = load_token(token_path)
    if not token:
        raise ValueError('Peloton token file is empty')
    session = requests.Session()
    session.headers.update(
        {
            'User-Agent': 'peloton-led/1.0',
            'peloton-platform': 'web',
            'Authorization': f'Bearer {token}',
        }
    )
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

    def get_me(self) -> dict[str, Any]:
        resp = self._get(f'{BASE}/api/me', timeout=15)
        resp.raise_for_status()
        return self._object(resp)

    def get_workouts_page(self, user_id: str, limit: int, page: int = 0) -> dict[str, Any]:
        params = {'joins': 'ride,ride.instructor', 'limit': limit, 'page': page}
        resp = self._get(f'{BASE}/api/user/{user_id}/workouts', params=params, timeout=20)
        resp.raise_for_status()
        return self._object(resp)

    @staticmethod
    def page_rows(page: dict[str, Any]) -> list[dict[str, Any]]:
        """The workouts on one history page; raises ValueError if malformed."""
        rows = page.get('data') or []
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError('Malformed workout page')
        return rows

    @staticmethod
    def is_last_page(page: dict[str, Any], page_number: int, rows: list[dict[str, Any]], page_size: int) -> bool:
        if not rows or page.get('show_next') is False:
            return True
        count = page.get('page_count')
        if isinstance(count, int) and page_number + 1 >= count:
            return True
        return len(rows) < page_size and page.get('show_next') is not True

    def iter_workout_pages(
        self, user_id: str, page_size: int, start_page: int = 0, max_pages: int = 500
    ) -> Iterator[tuple[int, list[dict[str, Any]], dict[str, Any]]]:
        """Yield (page_number, rows, page) newest first, one page at a time.

        Callers keep only what they need from each page, so a full-history
        walk never holds every raw row at once. Stops at the oldest workout,
        or if Peloton repeats a page.
        """
        if min(page_size, max_pages) <= 0 or start_page < 0:
            raise ValueError('History limits must be positive')
        previous = None
        for page_number in range(start_page, start_page + max_pages):
            page = self.get_workouts_page(user_id, limit=page_size, page=page_number)
            rows = self.page_rows(page)
            fingerprint = tuple(str(w.get('id') or w) for w in rows)
            if rows and fingerprint == previous:
                logger.warning('Peloton repeated workout page %d; stopping the walk', page_number)
                return
            previous = fingerprint
            yield page_number, rows, page
            if self.is_last_page(page, page_number, rows, page_size):
                return
        logger.warning('Workout history walk stopped at the %d-page limit', max_pages)

    def get_perf_graph(self, workout_id: str) -> dict[str, Any] | None:
        resp = self._get(f'{BASE}/api/workout/{workout_id}/performance_graph', params={'every_n': 5}, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        try:
            return self._object(resp)
        except Exception:
            return None

    def get_ride_details(self, ride_id: str) -> dict[str, Any] | None:
        resp = self._get(f'{BASE}/api/ride/{ride_id}/details', timeout=20)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        try:
            return self._object(resp)
        except Exception:
            return None

    def get_workout_detail(self, workout_id: str) -> dict[str, Any] | None:
        resp = self._get(f'{BASE}/api/workout/{workout_id}', params={'joins': 'ride,ride.instructor'}, timeout=20)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        try:
            return self._object(resp)
        except Exception:
            return None

    def get_current_challenges(self, user_id: str) -> dict[str, Any]:
        """The running challenges the rider joined, each with their progress and tiers."""
        resp = self._get(f'{BASE}/api/user/{user_id}/challenges/current', params={'has_joined': 'true'}, timeout=20)
        resp.raise_for_status()
        return self._object(resp)

    def get_club_score(self, user_id: str) -> dict[str, Any] | None:
        """Club Peloton's level, points and tier for the rider; None when Peloton has no score (404: a free
        trial or cancelled membership). Not through `_get`: a 401 from this undocumented host must not mark
        the token as rejected when the main API just took it."""
        resp = self._session.get(f'{MEMBERS_SCORE}/v2/user/{user_id}/score', timeout=20)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._object(resp)

    def _graphql(self, query: str, variables: dict | None = None, platform: str | None = None) -> dict[str, Any]:
        """One GraphQL request. `platform` overrides the `peloton-platform` header, which picks the machine for
        Lanebreak. Not through `_get`: a 401 from the gateway must not mark the main API's token as rejected.
        Raises ValueError when the answer is GraphQL errors with no data."""
        headers = {'peloton-platform': platform} if platform else {}
        resp = self._session.post(GRAPHQL, json={'query': query, 'variables': variables or {}}, headers=headers, timeout=20)
        resp.raise_for_status()
        body = self._object(resp)
        if body.get('data') is None:
            errors = body.get('errors')
            message = errors[0].get('message') if isinstance(errors, list) and errors and isinstance(errors[0], dict) else None
            raise ValueError(f'GraphQL error: {str(message or "no data")[:120]}')
        return body

    def get_lanebreak_run(self, workout_id: str) -> dict[str, Any]:
        """A Lanebreak's score, difficulty and share of beats hit (~230 bytes)."""
        return self._graphql(LANEBREAK_RUN_QUERY, {'id': workout_id})

    def get_lanebreak_tracks(self, platform: str) -> dict[str, Any]:
        """Every Lanebreak track on one machine: ID, title, length and volume only (Tread ~28 KB, bike ~44 KB)."""
        return self._graphql(LANEBREAK_TRACKS_QUERY, platform=platform)

    def get_lanebreak_place(self, track_id: str, difficulty: str, workout_id: str, platform: str) -> dict[str, Any]:
        """A run's place among its track's runs at its difficulty (`extraWorkoutEntry`, ~300 bytes)."""
        request = {'levelId': track_id, 'difficulty': difficulty, 'from': 0, 'size': 0, 'extraWorkoutId': workout_id}
        return self._graphql(LANEBREAK_PLACE_QUERY, {'request': request}, platform)

    def get_lanebreak_mine(self, track_id: str, platform: str) -> dict[str, Any]:
        """The rider's own runs on one track, newest first (workout IDs only, ~100-600 bytes)."""
        request = {'levelId': track_id, 'from': 0, 'size': LANEBREAK_MINE_SIZE, 'sortBy': 'Date'}
        return self._graphql(LANEBREAK_MINE_QUERY, {'request': request}, platform)

    def get_lanebreak_lanes(self, platform: str) -> dict[str, Any]:
        """One machine's Lanebreak lanes: each difficulty's six incline or resistance bands (~1.5 KB)."""
        return self._graphql(LANEBREAK_LANES_QUERY, platform=platform)

    def get_reservations(self, user_id: str) -> dict[str, Any]:
        """The live and encore classes the rider booked: only their IDs (`peloton_id`), unsorted."""
        resp = self._get(f'{BASE}/api/user/{user_id}/reservations', timeout=20)
        resp.raise_for_status()
        return self._object(resp)

    def get_scheduled_class(self, peloton_id: str) -> dict[str, Any] | None:
        """One scheduled class with its start, live/encore flags, class and instructor; None when it's gone."""
        resp = self._get(f'{BASE}/api/peloton/{peloton_id}', params={'joins': 'ride,ride.instructor'}, timeout=20)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._object(resp)

    def get_personal_records(self, user_id: str) -> dict[str, Any]:
        """The rider's current records: output per discipline and class length, and Best Times on the Tread and the
        Row (6 KB; /overview carries the same list without the rowing times)."""
        resp = self._get(f'{BASE}/api/user/{user_id}/personal_records', timeout=20)
        resp.raise_for_status()
        return self._object(resp)

    def get_overview(self, user_id: str) -> dict[str, Any]:
        resp = self._get(f'{BASE}/api/user/{user_id}/overview', timeout=20)
        resp.raise_for_status()
        return self._object(resp)

    @staticmethod
    def _object(response):
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError('Expected a Peloton JSON object')
        return data
