"""Background refresh and atomic in-memory snapshots for the display.

`Dashboard` is the class the display loop and the app talk to: it owns the locks, the refresh thread and the
snapshot, and runs one refresh at a time. The work it orchestrates lives in sibling modules, mixed in so that
every method still shares one `self` (and so the same locks): `dashboard_fetch` (what a refresh asks Peloton
for), `dashboard_insight` (workout insight views), `dashboard_history` (the workout log and its history walks),
`dashboard_celebrations` (PRs and milestones), `dashboard_lanebreak` (a Lanebreak's score, place and lanes);
`dashboard_state` builds the snapshot's starting points.
"""

import logging
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from .api import PelotonClient, make_session
from .cache import load_snapshot, save_snapshot
from .config import renewal_failed_path
from .dashboard_celebrations import CelebrationMixin
from .dashboard_fetch import CHALLENGES_REFRESH_SECONDS, CLUB_REFRESH_SECONDS, FetchMixin
from .dashboard_history import HistoryMixin
from .dashboard_insight import InsightMixin
from .dashboard_lanebreak import LanebreakMixin
from .dashboard_state import demo_values, initial_data, prepare_cached, slim_profile
from .schedule import scheduled_refresh_interval
from .selection import is_brief, last_active_day
from .stats.records import best_times_for, merge_personal_records, parse_personal_records, previous_best_kj
from .stats.summaries import summarize_workout
from .stats.totals import extract_discipline_totals, parse_streaks
from .timestamps import workout_timestamp
from .workouts.workout_log import WorkoutLog, default_log_path

logger = logging.getLogger('peloton-led.dashboard')

# The padlock reads a file the renewal job writes; checking it every frame is waste.
RENEWAL_MARKER_CHECK_SECONDS = 30
# id never changes and the rest rarely does, so the profile is fetched at
# startup and then once a day.
PROFILE_REFRESH_SECONDS = 24 * 3600


class Dashboard(FetchMixin, InsightMixin, HistoryMixin, CelebrationMixin, LanebreakMixin):
    def __init__(self, token_path, config, demo=False, demo_login_needed=False, client_factory=None):
        self.token_path = Path(token_path)
        self.config = config
        self.interval = config.get('refresh_interval', 300)
        self.refresh_schedule = config.get('refresh_schedule')
        self._factory = client_factory or (lambda path: PelotonClient(make_session(path)))
        self._init_threads()
        self._init_refresh_state()
        self._init_paths()
        self._init_log_state()
        self._init_insight_state()
        self._init_lanebreak_state()
        self._init_page_state()
        self._data = initial_data()
        self.demo = demo
        if demo:
            self._publish(**demo_values(config, demo_login_needed))
        else:
            self._load_startup_state()

    def _init_threads(self):
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._cache_write_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None

    def _init_refresh_state(self):
        self._client = None
        self._token_stamp = None
        self._performance = OrderedDict()
        self._performance_cache_size = self.config.get('performance_cache_size', 32)
        # {workout ID: (signature, detail or None, monotonic fetch time)}: a strength class's workout detail
        # (movement tracker), fetched once per finished class; a failed fetch retries after INSIGHT_RETRY_SECONDS.
        self._details = OrderedDict()
        self._failures = 0
        self._renewal_checked_at = None
        self._renewal_failed = False

    def _init_paths(self):
        configured_cache = self.config.get('cache_path')
        self.cache_path = Path(configured_cache).expanduser() if configured_cache else self.token_path.with_name('dashboard-cache.json')
        configured_log = self.config.get('log_path')
        self.log_path = Path(configured_log).expanduser() if configured_log else default_log_path(self.cache_path)

    def _init_log_state(self):
        self._log = None
        self._log_lock = threading.Lock()
        self._history_thread = None
        self._derive_args = None
        # Log figures are computed under the log lock but published later; the
        # sequence keeps an older computation from overwriting a newer one.
        self._derived_computed = 0
        self._derived_published = 0

    def _init_insight_state(self):
        # Workout compare (display.workout_insights): the row store loads on first use.
        self._rows = None
        self._rows_lock = threading.Lock()
        self._insight_failed = {}
        # A settling workout's detail and class details, kept so each refresh in its first hour can rebuild
        # its row with the new performance graph without fetching them again; dropped after one last rebuild.
        self._insight_settling = {}
        # {workout ID: (store generation, views)}: insights are recomputed only when the row store changed.
        self._insight_views = {}
        self._rows_generation = 0

    def _init_page_state(self):
        self._profile_checked_at = None
        # When the challenges were last asked for (monotonic), and how long until the next ask.
        self._challenges_checked_at = None
        self._challenges_wait = CHALLENGES_REFRESH_SECONDS
        # Booked classes' details by class ID, fetched once each; and when a detail fetch last failed.
        self._bookings = {}
        self._booking_failed = {}
        # When the Club Peloton score was last asked for (monotonic), how long until the next ask, and the
        # newest workout then (a new one asks again at once).
        self._club_checked_at = None
        self._club_wait = CLUB_REFRESH_SECONDS
        self._club_workout = None

    def _load_startup_state(self):
        """Publish the cached snapshot and the log's lifetime figures, so the panel has data at once."""
        cached = load_snapshot(self.cache_path)
        if cached is not None:
            prepare_cached(cached, self.config)
            self._publish(**cached, status='cached', data_stale=True, cache_loaded=True)
            # Booked classes' details survive a restart (the cache validated them).
            self._bookings = {b['id']: b for b in cached.get('booked_classes') or []}
        self._log = WorkoutLog.load(self.log_path)
        # Lifetime figures come from the log, so they show at once after a restart.
        me = (cached or {}).get('me') or {}
        if self._log.user_id and self._log.user_id == me.get('id'):
            self._publish_derived(*self._compute_derived(self._derive(me)))

    def snapshot(self):
        with self._lock:
            return deepcopy(self._data)

    def booked_classes(self):
        """Just the booked classes (a copy), for the takeover check the display loop makes every second: cheaper
        than a whole snapshot. Never touches the network."""
        with self._lock:
            return deepcopy(self._data.get('booked_classes') or [])

    @property
    def login_required(self):
        with self._lock:
            return self._data['login_required']

    @property
    def renewal_failed(self):
        """The renewal job reported that only a fresh login can help. A marker
        older than the token file is ignored: the board has been re-seeded since."""
        if self.demo:
            return False
        now = time.monotonic()
        if self._renewal_checked_at is None or now - self._renewal_checked_at >= RENEWAL_MARKER_CHECK_SECONDS:
            try:
                marked = renewal_failed_path(self.token_path).stat().st_mtime_ns
            except OSError:
                failed = False
            else:
                try:
                    failed = marked >= self.token_path.stat().st_mtime_ns
                except OSError:
                    failed = True
            self._renewal_failed = failed
            self._renewal_checked_at = now
        return self._renewal_failed

    @property
    def login_indicator_required(self):
        """Draw the padlock: the token is rejected, or renewal already knows it will be.
        Only for display; the refresh loop keeps using login_required, so data
        keeps updating while the old token still works."""
        return self.login_required or self.renewal_failed

    @property
    def data_stale(self):
        with self._lock:
            return self._data['data_stale']

    @property
    def stale_indicator_required(self):
        """Only show the stale clock after three consecutive refresh failures."""
        with self._lock:
            return self._data['data_stale'] and self._data.get('consecutive_failures', 0) >= 3

    def _publish(self, **values):
        with self._lock:
            self._data.update(values)

    def _persist_snapshot(self):
        if self.demo:
            return
        with self._cache_write_lock:
            save_snapshot(self.cache_path, self.snapshot())

    def _current_interval(self):
        """The refresh interval for right now, honoring quiet hours."""
        return scheduled_refresh_interval(self.refresh_schedule, self.interval, timezone_name=self.config.get('timezone'))

    def _finish_attempt(self, started, delay, **values):
        """Publish refresh health fields together and return the next delay."""
        self._publish(
            refresh_in_progress=False,
            last_refresh_duration=max(0.0, time.monotonic() - started),
            next_refresh_at=time.time() + delay,
            **values,
        )
        return delay

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
        interval = self._current_interval()
        started = time.monotonic()
        attempted_at = time.time()
        self._publish(refresh_in_progress=True, last_attempt=attempted_at)
        stamp = self._stamp()
        if stamp is None:
            self._client = None
            self._token_stamp = None
            return self._finish_attempt(
                started, interval, login_required=True, status='login_needed', last_error='token_missing', data_stale=True
            )
        try:
            return self._refresh_with_client(stamp, started, interval)
        except (OSError, ValueError, requests.RequestException) as exc:
            return self._refresh_failed(exc, started, interval)

    def _refresh_with_client(self, stamp, started, interval):
        """The successful path of a refresh; errors propagate to `_refresh_once`."""
        if self._client is None or stamp != self._token_stamp:
            candidate = self._factory(self.token_path)
            self._client = candidate
            self._token_stamp = stamp
            self._failures = 0
            # A replaced token may be a different account: re-read the profile and its challenges.
            self._profile_checked_at = None
            self._challenges_checked_at = None
            self._club_checked_at = None
        elif self.login_required:
            # Rejected token: wait for a replacement instead of retrying it.
            return self._finish_attempt(
                started, interval, login_required=True, status='login_needed', last_error='authentication', data_stale=True
            )
        client = self._client
        me = self._profile(client)
        user_id = me.get('id')
        if not user_id:
            raise ValueError('Profile response has no user ID')
        overview = client.get_overview(user_id)
        records = self._personal_records(client, user_id, overview)
        self._refresh_challenges(client, user_id)
        self._refresh_bookings(client, user_id)
        with self._lock:
            stored_records = self._data.get('personal_records', {})
        personal_records = merge_personal_records(stored_records, parse_personal_records(records))
        tz = self.config.get('timezone') or me.get('timezone')
        with self._log_lock:
            if self._log.claim(user_id):
                self._log.save()
        workouts, total = self._fetch_recent(client, user_id, tz)
        self._refresh_club(client, user_id, workouts[0].get('id') if workouts else None)
        # A workout under a minute (a start tapped by accident) isn't a latest workout,
        # and doesn't make its day the last active one on its own.
        active_day = last_active_day([w for w in workouts if not is_brief(w)], tz)
        summaries = [self._summarize(client, workout, personal_records, tz, records) for workout in active_day]
        derived = self._merge_into_log(client, user_id, me, workouts, total, tz)
        with self._lock:
            generation = self._data['generation'] + 1
        refreshed_at = time.time()
        self._failures = 0
        delay = self._finish_attempt(
            started,
            interval,
            me=me,
            totals=extract_discipline_totals(overview),
            summaries=summaries,
            streaks=parse_streaks(overview),
            personal_records=personal_records,
            login_required=False,
            status='ready',
            last_updated=refreshed_at,
            last_error=None,
            generation=generation,
            active_day_count=len(active_day),
            data_stale=False,
            cache_loaded=False,
            consecutive_failures=0,
        )
        self._publish_derived(*derived)
        try:
            self._persist_snapshot()
        except (OSError, TypeError, ValueError) as exc:
            logger.warning('Could not persist dashboard cache (%s)', type(exc).__name__)
        return delay

    def _profile(self, client):
        """The rider's slim profile: the one in the snapshot, refetched at startup and then daily."""
        with self._lock:
            me = self._data.get('me') or {}
        if not me.get('id') or self._profile_checked_at is None or time.monotonic() - self._profile_checked_at >= PROFILE_REFRESH_SECONDS:
            me = slim_profile(client.get_me())
            self._profile_checked_at = time.monotonic()
        return me

    def _summarize(self, client, workout, personal_records, tz, records=None):
        """One latest-day workout's summary, with its performance graph, strength detail, insights and the
        Best Times it holds (a Best Time makes it a PR workout even when its output wasn't one)."""
        identity = workout.get('id')
        cached = self._cached_performance(identity)
        timestamp = workout_timestamp(workout, tz)
        settling = timestamp is None or (datetime.now(UTC) - timestamp).total_seconds() < 3600
        signature = (workout.get('total_work'), workout.get('status'), workout.get('end_time'), workout.get('updated_at'))
        if identity and (cached is None or cached[0] != signature or settling or cached[1] is None):
            perf = client.get_perf_graph(identity)
            self._cache_performance(identity, signature, perf)
        else:
            perf = cached[1] if cached else None
        detail = self._strength_detail(client, workout, signature)
        summary = summarize_workout(workout, perf, detail)
        summary['previous_best_kj'] = previous_best_kj(identity, personal_records)
        summary['best_times'] = best_times_for(identity, records, personal_records)
        if summary.get('lanebreak'):
            stats = self._lanebreak_stats(client, workout, perf, signature)
            if stats:
                summary['lanebreak_stats'] = stats
        if summary['best_times']:
            summary['is_pr'] = True
        if self.config.get('workout_insights'):
            views = self._workout_insight(client, workout, perf, settling, detail)
            if views:
                summary['insights'] = views
        return summary

    def _merge_into_log(self, client, user_id, me, workouts, total, tz):
        """Merge the fetched workouts into the log, start a history walk if one is due, and return the log's
        derived figures (sequenced) for the caller to publish."""
        self._derive_args = self._derive(me)
        with self._log_lock:
            if self._log.merge(workouts):
                self._save_log()
            walk = self._check_count(total, tz)
            derived = self._compute_derived(self._derive_args)
        if walk is not None:
            self._start_history_walk(client, user_id, rewalk=walk)
        return derived

    def _refresh_failed(self, exc, started, interval):
        """A failed refresh: ask for a new login when the token is the problem, else back off and retry."""
        response = getattr(exc, 'response', None)
        unauthorized = response is not None and response.status_code == 401
        missing = isinstance(exc, (FileNotFoundError, PermissionError)) or (
            isinstance(exc, ValueError) and str(exc) == 'Peloton token file is empty'
        )
        if unauthorized or missing:
            logger.warning('Peloton login needed; replace the token file to resume')
            return self._finish_attempt(
                started, interval, login_required=True, status='login_needed', last_error='authentication', data_stale=True
            )
        self._failures += 1
        delay = min(self.interval, 15 * 2 ** min(self._failures - 1, 6))
        if response is not None and response.status_code == 429:
            delay = self._retry_after_delay(response, delay)
        logger.warning('Refresh failed (%s); retaining previous data, retrying in %.0fs', type(exc).__name__, delay)
        return self._finish_attempt(
            started, delay, status='offline', last_error=type(exc).__name__, data_stale=True, consecutive_failures=self._failures
        )

    @staticmethod
    def _retry_after_delay(response, delay):
        """The back-off delay, raised to the 429 response's Retry-After (seconds or an HTTP date) if longer."""
        retry = response.headers.get('Retry-After', '')
        try:
            delay = max(delay, float(retry))
        except ValueError:
            try:
                delay = max(delay, (parsedate_to_datetime(retry) - datetime.now(UTC)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
        return delay

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
        if self._history_thread is not None:
            self._history_thread.join(timeout=timeout)
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
