"""Background refresh and atomic in-memory snapshots for the display."""
import logging
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from .api import PelotonClient, make_session
from .cache import load_snapshot, save_snapshot
from .demo import demo_data
from .selection import last_active_day
from .summaries import summarize_workout
from .timestamps import workout_timestamp
from .totals import extract_discipline_totals
from .goals import reached_milestones, weekly_progress
from .instructors import merge_instructor_counts

logger = logging.getLogger('peloton-led.dashboard')


class Dashboard:
    def __init__(self, token_path, config, demo=False, demo_login_needed=False, client_factory=None):
        self.token_path = Path(token_path)
        self.config = config
        self.interval = config.get('refresh_interval', 300)
        self._factory = client_factory or (lambda path: PelotonClient(make_session(path)))
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._cache_write_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._client = None
        self._token_stamp = None
        self._performance = OrderedDict()
        self._performance_cache_size = config.get('performance_cache_size', 32)
        configured_cache = config.get('cache_path')
        self.cache_path = (Path(configured_cache).expanduser() if configured_cache else
                           self.token_path.with_name('dashboard-cache.json'))
        self._failures = 0
        self._data = {'me': None, 'totals': {}, 'summaries': [], 'login_required': False,
                      'status': 'loading', 'refresh_in_progress': False,
                      'last_attempt': None, 'last_updated': None,
                      'last_refresh_duration': None, 'last_error': None,
                      'next_refresh_at': None, 'generation': 0,
                      'data_stale': False, 'cache_loaded': False,
                      'consecutive_failures': 0,
                      'celebrated_pr_ids': [], 'celebrated_milestones': [],
                      'weekly_progress': {'workouts': 0, 'minutes': 0},
                      'instructor_counts': {}, 'instructor_tally_cursor': None}
        self.demo = demo
        if demo:
            data = demo_data()
            zone = config.get('timezone') or data['me'].get('timezone')
            self._publish(me=data['me'], totals=extract_discipline_totals(data['overview']),
                summaries=[summarize_workout(w, data['performance'][w['id']]) for w in data['workouts']],
                weekly_progress=weekly_progress(data['workouts'], zone),
                login_required=demo_login_needed, status='ready', last_updated=time.time(),
                generation=1)
        else:
            cached = load_snapshot(self.cache_path)
            if cached is not None:
                self._publish(**cached, status='cached', data_stale=True, cache_loaded=True)

    def snapshot(self):
        with self._lock:
            return deepcopy(self._data)

    @property
    def login_required(self):
        with self._lock:
            return self._data['login_required']

    @property
    def data_stale(self):
        with self._lock:
            return self._data['data_stale']

    @property
    def stale_indicator_required(self):
        """Only show the stale clock after three consecutive refresh failures."""
        with self._lock:
            return (self._data['data_stale'] and
                    self._data.get('consecutive_failures', 0) >= 3)

    def _publish(self, **values):
        with self._lock:
            self._data.update(values)

    def _persist_snapshot(self):
        if self.demo:
            return
        with self._cache_write_lock:
            save_snapshot(self.cache_path, self.snapshot())

    def should_celebrate_pr(self, summary):
        identity = summary.get('workout_id') if isinstance(summary, dict) else None
        if not identity or not summary.get('is_pr'):
            return False
        with self._lock:
            return identity not in self._data['celebrated_pr_ids']

    def acknowledge_pr(self, workout_id):
        """Record a displayed PR celebration immediately and durably."""
        if not workout_id:
            return
        with self._lock:
            celebrated = self._data['celebrated_pr_ids']
            if workout_id in celebrated:
                return
            self._data['celebrated_pr_ids'] = (celebrated + [workout_id])[-256:]
        try:
            self._persist_snapshot()
        except (OSError, TypeError, ValueError) as exc:
            logger.warning('Could not persist PR state (%s)', type(exc).__name__)

    def pending_milestones(self, snapshot=None):
        data = snapshot or self.snapshot()
        total = data.get('totals', {}).get('Total Workouts')
        reached = reached_milestones(total, self.config.get('milestones', []))
        celebrated = set(data.get('celebrated_milestones', []))
        return [value for value in reached if value not in celebrated]

    def acknowledge_milestone(self, milestone):
        if not isinstance(milestone, int):
            return
        with self._lock:
            celebrated = self._data['celebrated_milestones']
            if milestone in celebrated:
                return
            self._data['celebrated_milestones'] = (celebrated + [milestone])[-256:]
        try:
            self._persist_snapshot()
        except (OSError, TypeError, ValueError) as exc:
            logger.warning('Could not persist milestone state (%s)', type(exc).__name__)

    def _finish_attempt(self, started, delay, **values):
        """Publish refresh health fields together and return the next delay."""
        self._publish(refresh_in_progress=False,
                      last_refresh_duration=max(0.0, time.monotonic() - started),
                      next_refresh_at=time.time() + delay,
                      **values)
        return delay

    def _cache_performance(self, workout_id, signature, performance):
        self._performance[workout_id] = (signature, performance)
        self._performance.move_to_end(workout_id)
        while len(self._performance) > self._performance_cache_size:
            self._performance.popitem(last=False)

    def _cached_performance(self, workout_id):
        cached = self._performance.get(workout_id)
        if cached is not None:
            self._performance.move_to_end(workout_id)
        return cached

    def _stamp(self):
        try:
            stat = self.token_path.stat()
            return (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None

    def refresh(self):
        """Run one serialized refresh and return the delay until the next attempt."""
        with self._refresh_lock:
            return self._refresh_once()

    def _refresh_once(self):
        """Refresh once. Return the delay until the next request attempt."""
        if self.demo:
            return self.interval
        started = time.monotonic()
        attempted_at = time.time()
        self._publish(refresh_in_progress=True, last_attempt=attempted_at)
        stamp = self._stamp()
        if stamp is None:
            self._client = None
            self._token_stamp = None
            return self._finish_attempt(started, self.interval, login_required=True,
                                        status='login_needed', last_error='token_missing', data_stale=True)
        try:
            if self._client is None or stamp != self._token_stamp:
                candidate = self._factory(self.token_path)
                self._client = candidate
                self._token_stamp = stamp
                self._failures = 0
            elif self.login_required:
                # Rejected token: wait for a replacement instead of retrying it.
                return self._finish_attempt(started, self.interval,
                    login_required=True, status='login_needed', last_error='authentication', data_stale=True)
            client = self._client
            me = client.get_me()
            user_id = me.get('id')
            if not user_id:
                raise ValueError('Profile response has no user ID')
            overview = client.get_overview(user_id)
            workouts = client.get_recent_workouts(user_id,
                limit=self.config.get('history_limit', 200), days=self.config.get('history_days', 90),
                page_size=self.config.get('history_page_size', 50), max_pages=self.config.get('history_max_pages', 10))
            tz = self.config.get('timezone') or me.get('timezone')
            active_day = last_active_day(workouts, tz)
            summaries = []
            for workout in active_day:
                identity = workout.get('id')
                cached = self._cached_performance(identity)
                timestamp = workout_timestamp(workout, tz)
                settling = timestamp is None or (datetime.now(timezone.utc) - timestamp).total_seconds() < 3600
                signature = (workout.get('total_work'), workout.get('status'),
                             workout.get('end_time'), workout.get('updated_at'))
                if identity and (cached is None or cached[0] != signature or settling or cached[1] is None):
                    perf = client.get_perf_graph(identity)
                    self._cache_performance(identity, signature, perf)
                else:
                    perf = cached[1] if cached else None
                summaries.append(summarize_workout(workout, perf))
            with self._lock:
                generation = self._data['generation'] + 1
                prior_counts = self._data.get('instructor_counts', {})
                cursor = self._data.get('instructor_tally_cursor')
            new_workouts = client.get_all_workouts(user_id,
                page_size=self.config.get('history_page_size', 50),
                max_pages=self.config.get('instructor_tally_max_pages', 200),
                stop_at_id=cursor)
            instructor_counts = merge_instructor_counts(prior_counts, new_workouts)
            newest_id = new_workouts[0].get('id') if new_workouts else cursor
            refreshed_at = time.time()
            progress = weekly_progress(workouts, tz)
            self._failures = 0
            delay = self._finish_attempt(started, self.interval,
                me=me, totals=extract_discipline_totals(overview), summaries=summaries,
                weekly_progress=progress,
                instructor_counts=instructor_counts, instructor_tally_cursor=newest_id,
                login_required=False, status='ready', last_updated=refreshed_at,
                last_error=None, generation=generation,
                active_day_count=len(active_day),
                history_truncated=bool(getattr(client, 'history_truncated', False)),
                data_stale=False, cache_loaded=False, consecutive_failures=0)
            try:
                self._persist_snapshot()
            except (OSError, TypeError, ValueError) as exc:
                logger.warning('Could not persist dashboard cache (%s)', type(exc).__name__)
            return delay
        except (OSError, ValueError, requests.RequestException) as exc:
            response = getattr(exc, 'response', None)
            unauthorized = response is not None and response.status_code == 401
            missing = isinstance(exc, (FileNotFoundError, PermissionError)) or (
                isinstance(exc, ValueError) and str(exc) == 'Peloton token file is empty')
            if unauthorized or missing:
                logger.warning('Peloton login needed; replace the token file to resume')
                return self._finish_attempt(started, self.interval,
                    login_required=True, status='login_needed', last_error='authentication', data_stale=True)
            self._failures += 1
            delay = min(self.interval, 15 * 2 ** min(self._failures - 1, 6))
            if response is not None and response.status_code == 429:
                retry = response.headers.get('Retry-After', '')
                try:
                    delay = max(delay, float(retry))
                except ValueError:
                    try:
                        delay = max(delay, (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds())
                    except (ValueError, TypeError, OverflowError):
                        pass
            logger.warning('Refresh failed (%s); retaining previous data, retrying in %.0fs', type(exc).__name__, delay)
            return self._finish_attempt(started, delay, status='offline',
                                        last_error=type(exc).__name__, data_stale=True,
                                        consecutive_failures=self._failures)

    def start(self):
        if not self.demo and (self._thread is None or not self._thread.is_alive()):
            self._stop.clear()
            self._wake.clear()
            self._thread = threading.Thread(target=self._run, name='peloton-refresh', daemon=True)
            self._thread.start()

    def request_refresh(self):
        """Wake the worker for an immediate refresh without blocking the caller."""
        if not self.demo:
            self._wake.set()

    def _run(self):
        while not self._stop.is_set():
            stamp = self._stamp()
            delay = self.refresh()
            deadline = time.monotonic() + delay
            while not self._stop.is_set():
                remaining = max(0, deadline - time.monotonic())
                if not remaining:
                    break
                self._wake.wait(min(1, remaining))
                if self._wake.is_set():
                    self._wake.clear()
                    break
                if self._stamp() != stamp or time.monotonic() >= deadline:
                    break

    def stop(self, timeout=35):
        """Request shutdown and return whether the refresh worker stopped."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            stopped = not self._thread.is_alive()
        else:
            stopped = True
        if stopped and self._client is not None:
            close = getattr(self._client, 'close', None)
            if close:
                close()
            self._client = None
        return stopped
