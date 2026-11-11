"""Workout compare: the per-rider row store and the daily sync (spec section 7).

Store: `<cache stem>.workout-rows.json` beside the workout log, `{"version": 1, "rows": {id: row}}`.
Raw responses are kept in the training-data layout so a ROW_VERSION bump is a rebuild, never a
refetch: `<raw>/<rider>/<id>.workout.json` (detail), `<raw>/<rider>/<id>.json` (performance graph),
`<raw>/rides/<ride_id>.json` (class details). Standard library only apart from the API client the
caller passes in.
"""
import json
import logging
import os
from pathlib import Path

import requests

from .workout_compare import DISCIPLINES
from .workout_features import ROW_VERSION, build_row, discipline

log = logging.getLogger(__name__)

STORE_VERSION = 1
MAX_PER_RUN = 20
WINDOW_DAYS = 730
LIST_LIMIT = 20
DAY = 86400


class LoginRequired(Exception):
    """Peloton answered 401: stop the run, keep what was saved, never retry in a loop."""


def default_rows_path(cache_path):
    """cookies-joel-dashboard-cache.json -> cookies-joel-dashboard-cache.workout-rows.json"""
    cache_path = Path(cache_path)
    return cache_path.with_name(f'{cache_path.stem}.workout-rows.json')


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, ValueError) as exc:
        log.warning('%s is unreadable (%s); ignoring it', path, type(exc).__name__)
        return None


def _write_json(path, payload):
    """Write atomically (temporary file, fsync, replace), owner-only."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.new')
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, separators=(',', ':'), allow_nan=False, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class RowStore:
    """Rows keyed by workout ID. Insights are never stored: they depend on peers that change."""

    def __init__(self, path):
        self.path = Path(path)
        self.rows = {}

    @classmethod
    def load(cls, path):
        """Read the store, or start empty when it is missing, damaged or another store version."""
        store = cls(path)
        payload = _read_json(store.path)
        if payload is None:
            return store
        if not isinstance(payload, dict) or payload.get('version') != STORE_VERSION \
                or not isinstance(payload.get('rows'), dict):
            log.warning('Row store %s is another version or malformed; starting empty', store.path)
            return store
        store.rows = {k: v for k, v in payload['rows'].items() if isinstance(v, dict) and v.get('id') == k}
        return store

    def save(self):
        _write_json(self.path, {'version': STORE_VERSION, 'rows': self.rows})

    def upsert(self, row):
        """Insert or replace by workout ID: a refetch never makes a duplicate."""
        self.rows[row['id']] = row

    def is_current(self, workout_id):
        row = self.rows.get(workout_id)
        return bool(row) and row.get('v') == ROW_VERSION

    def stale_ids(self):
        return [k for k, row in self.rows.items() if row.get('v') != ROW_VERSION]


class RawFiles:
    """Saved API responses for one rider, in the training-data layout."""

    def __init__(self, root, rider):
        self.root = Path(root)
        self.folder = self.root / rider
        self.rides = self.root / 'rides'

    def detail_path(self, workout_id):
        return self.folder / f'{workout_id}.workout.json'

    def graph_path(self, workout_id):
        return self.folder / f'{workout_id}.json'

    def ride_path(self, ride_id):
        return self.rides / f'{ride_id}.json'

    def detail(self, workout_id):
        return _read_json(self.detail_path(workout_id))

    def graph(self, workout_id):
        return _read_json(self.graph_path(workout_id))

    def ride(self, ride_id):
        return _read_json(self.ride_path(ride_id)) if ride_id else None

    def has_ride(self, ride_id):
        return self.ride_path(ride_id).exists()

    def save_detail(self, workout_id, payload):
        _write_json(self.detail_path(workout_id), payload)

    def save_graph(self, workout_id, payload):
        _write_json(self.graph_path(workout_id), payload)

    def save_ride(self, ride_id, payload):
        _write_json(self.ride_path(ride_id), payload)

    def workout_ids(self):
        if not self.folder.is_dir():
            return []
        return sorted(p.name[:-len('.workout.json')] for p in self.folder.iterdir()
                      if p.name.endswith('.workout.json'))

    def build(self, workout_id):
        """The row from saved files, or None when the detail is missing, unreadable or incomplete."""
        detail = self.detail(workout_id)
        if not isinstance(detail, dict) or detail.get('status') != 'COMPLETE':
            return None
        try:
            return build_row(detail, self.graph(workout_id), self.ride((detail.get('ride') or {}).get('id')))
        except Exception:  # noqa: BLE001 - one bad file must not stop the rest
            log.exception('Workout %s: could not build a row from saved files', workout_id)
            return None


def import_raw(store, raw):
    """Build every saved workout that has no current row (first run, or a ROW_VERSION bump).

    No API calls. Returns how many rows were written.
    """
    built = 0
    for workout_id in raw.workout_ids():
        if store.is_current(workout_id):
            continue
        row = raw.build(workout_id)
        if row:
            store.upsert(row)
            built += 1
    if built:
        log.info('Built %d rows from saved files in %s', built, raw.folder)
    return built


def candidate_ids(log_workouts=None, listed=None, now=0):
    """In-scope, COMPLETE workout IDs newest first.

    `log_workouts` is the board's workout log ({id: log row}); `listed` the newest history page
    (raw API rows), used when there is no log.
    """
    found = []
    if log_workouts is not None:
        since = now - WINDOW_DAYS * DAY
        for workout_id, row in log_workouts.items():
            start = row.get('start')
            if (row.get('status') == 'COMPLETE' and row.get('discipline') in DISCIPLINES
                    and isinstance(start, (int, float)) and start >= since):
                found.append((start, workout_id))
    for workout in listed or []:
        if (workout.get('id') and workout.get('status') == 'COMPLETE'
                and discipline(workout.get('fitness_discipline')) in DISCIPLINES):
            found.append((workout.get('start_time') or 0, workout['id']))
    seen = set()
    ordered = []
    for _, workout_id in sorted(found, reverse=True):
        if workout_id not in seen:
            seen.add(workout_id)
            ordered.append(workout_id)
    return ordered


def _call(client, method, *args):
    """One API call; a 401 becomes LoginRequired, anything else propagates."""
    try:
        return getattr(client, method)(*args)
    except requests.HTTPError:
        if client.login_required:
            raise LoginRequired(f'Peloton answered 401 during {method}') from None
        raise


def fetch_row(client, raw, workout_id):
    """Fetch (or reuse) the raw responses for one workout, save them, build its row.

    Returns the row, or None when the workout must be tried again next run (missing or bad
    detail, still in progress). Raises LoginRequired on a 401.
    """
    detail = raw.detail(workout_id)
    if not isinstance(detail, dict) or detail.get('status') != 'COMPLETE':
        detail = _call(client, 'get_workout_detail', workout_id)
        if not isinstance(detail, dict) or not detail.get('id') or detail.get('start_time') is None:
            log.warning('Workout %s: no usable detail; will try again next run', workout_id)
            return None
        if detail.get('status') != 'COMPLETE':
            log.info('Workout %s is %s; will try again next run', workout_id, detail.get('status'))
            return None
        raw.save_detail(workout_id, detail)
    graph = raw.graph(workout_id)
    if graph is None:
        graph = _call(client, 'get_perf_graph', workout_id)
        if isinstance(graph, dict):
            raw.save_graph(workout_id, graph)
        else:
            log.info('Workout %s: no performance graph; building the row without it', workout_id)
            graph = None
    ride_id = (detail.get('ride') or {}).get('id')
    if ride_id and not raw.has_ride(ride_id):
        ride = _call(client, 'get_ride_details', ride_id)
        if isinstance(ride, dict):
            raw.save_ride(ride_id, ride)
    return build_row(detail, graph, raw.ride(ride_id))


def sync(client, store, raw, ids, limit=MAX_PER_RUN):
    """Fetch rows for the IDs with no current row, newest first, at most `limit` per run.

    Saves the store after every new row, so a 401 halfway keeps what came before.
    Returns the new rows' IDs. Raises LoginRequired on a 401.
    """
    missing = [workout_id for workout_id in ids if not store.is_current(workout_id)][:limit]
    added = []
    for workout_id in missing:
        try:
            row = fetch_row(client, raw, workout_id)
        except LoginRequired:
            raise
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            log.warning('Workout %s skipped (%s: %s); will try again next run', workout_id,
                        type(exc).__name__, exc)
            continue
        if row:
            store.upsert(row)
            store.save()
            added.append(workout_id)
    return added
