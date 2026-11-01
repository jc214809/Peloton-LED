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
from .config import renewal_failed_path
from .demo import demo_data
from .selection import last_active_day
from .summaries import summarize_workout
from .timestamps import workout_date, workout_timestamp
from .totals import extract_discipline_totals, parse_streaks
from .goals import reached_milestones, week_start, weekly_progress
from .journey import uses_metric
from .schedule import in_quiet_hours, scheduled_refresh_interval
from .records import merge_personal_records, parse_personal_records, previous_best_kj
from .workout_log import WorkoutLog, default_log_path

logger = logging.getLogger('peloton-led.dashboard')

# The padlock reads a file the renewal job writes; checking it every frame is waste.
RENEWAL_MARKER_CHECK_SECONDS = 30
# The only profile fields the board reads; the rest of /api/me (email,
# birthday, phone, weight, ...) is never stored.
PROFILE_KEYS = ('id', 'username', 'timezone', 'height_unit')
# id never changes and the rest rarely does, so the profile is fetched at
# startup and then once a day.
PROFILE_REFRESH_SECONDS = 24 * 3600
# Each refresh reads the newest page; more only to finish the latest day, cover
# this week while the log is still filling, or close a gap after downtime.
MAX_RECENT_PAGES = 10
# History walks: pause between batches, and a safety limit on batches.
HISTORY_BATCH_PAUSE_SECONDS = 1.0
MAX_HISTORY_BATCHES = 500
# The log's workout count must disagree with Peloton's this many refreshes in
# a row (riding out a lag right after a workout) before a full re-walk, which
# runs at most once a day and, with a refresh_schedule, in quiet hours.
MISMATCH_LIMIT = 3
REWALK_INTERVAL_SECONDS = 24 * 3600


def slim_profile(me):
    return {key: me[key] for key in PROFILE_KEYS if key in me}


class Dashboard:
    def __init__(self, token_path, config, demo=False, demo_login_needed=False, client_factory=None):
        self.token_path = Path(token_path)
        self.config = config
        self.interval = config.get('refresh_interval', 300)
        self.refresh_schedule = config.get('refresh_schedule')
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
        self._renewal_checked_at = None
        self._renewal_failed = False
        configured_log = config.get('log_path')
        self.log_path = (Path(configured_log).expanduser() if configured_log else
                         default_log_path(self.cache_path))
        self._log = None
        self._log_lock = threading.Lock()
        self._history_thread = None
        self._profile_checked_at = None
        self._derive_args = None
        # Log figures are computed under the log lock but published later; the
        # sequence keeps an older computation from overwriting a newer one.
        self._derived_computed = 0
        self._derived_published = 0
        self._data = {'me': None, 'totals': {}, 'summaries': [], 'login_required': False,
                      'status': 'loading', 'refresh_in_progress': False,
                      'last_attempt': None, 'last_updated': None,
                      'last_refresh_duration': None, 'last_error': None,
                      'next_refresh_at': None, 'generation': 0,
                      'data_stale': False, 'cache_loaded': False,
                      'consecutive_failures': 0,
                      'celebrated_pr_ids': [], 'celebrated_milestones': [],
                      'weekly_progress': {'workouts': 0, 'minutes': 0},
                      'instructor_counts': {}, 'instructor_names': {}, 'streaks': {},
                      'distance_totals': {}, 'personal_records': {},
                      'streak_week_workouts': None, 'activity_days': {}}
        self.demo = demo
        if demo:
            data = demo_data()
            zone = config.get('timezone') or data['me'].get('timezone')
            self._publish(me=data['me'], totals=extract_discipline_totals(data['overview']),
                streaks=parse_streaks(data['overview']),
                distance_totals=data['distance_totals'],
                summaries=[summarize_workout(w, data['performance'][w['id']]) for w in data['workouts']],
                weekly_progress=weekly_progress(data['workouts'], zone),
                login_required=demo_login_needed, status='ready', last_updated=time.time(),
                generation=1)
        else:
            cached = load_snapshot(self.cache_path)
            if cached is not None:
                if isinstance(cached.get('me'), dict):
                    cached['me'] = slim_profile(cached['me'])
                self._publish(**cached, status='cached', data_stale=True, cache_loaded=True)
            self._log = WorkoutLog.load(self.log_path)
            # Lifetime figures come from the log, so they show at once after a restart.
            me = (cached or {}).get('me') or {}
            if self._log.user_id and self._log.user_id == me.get('id'):
                self._publish_derived(*self._compute_derived(self._derive(me)))

    def snapshot(self):
        with self._lock:
            return deepcopy(self._data)

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
        reached = reached_milestones(total, self.config.get('milestones', []),
                                     self.config.get('milestone_step', 0))
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

    def _current_interval(self):
        """The refresh interval for right now, honoring quiet hours."""
        return scheduled_refresh_interval(self.refresh_schedule, self.interval,
                                          timezone_name=self.config.get('timezone'))

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
        interval = self._current_interval()
        started = time.monotonic()
        attempted_at = time.time()
        self._publish(refresh_in_progress=True, last_attempt=attempted_at)
        stamp = self._stamp()
        if stamp is None:
            self._client = None
            self._token_stamp = None
            return self._finish_attempt(started, interval, login_required=True,
                                        status='login_needed', last_error='token_missing', data_stale=True)
        try:
            if self._client is None or stamp != self._token_stamp:
                candidate = self._factory(self.token_path)
                self._client = candidate
                self._token_stamp = stamp
                self._failures = 0
                # A replaced token may be a different account: re-read the profile.
                self._profile_checked_at = None
            elif self.login_required:
                # Rejected token: wait for a replacement instead of retrying it.
                return self._finish_attempt(started, interval,
                    login_required=True, status='login_needed', last_error='authentication', data_stale=True)
            client = self._client
            with self._lock:
                me = self._data.get('me') or {}
            if (not me.get('id') or self._profile_checked_at is None
                    or time.monotonic() - self._profile_checked_at >= PROFILE_REFRESH_SECONDS):
                me = slim_profile(client.get_me())
                self._profile_checked_at = time.monotonic()
            user_id = me.get('id')
            if not user_id:
                raise ValueError('Profile response has no user ID')
            overview = client.get_overview(user_id)
            with self._lock:
                stored_records = self._data.get('personal_records', {})
            personal_records = merge_personal_records(stored_records, parse_personal_records(overview))
            tz = self.config.get('timezone') or me.get('timezone')
            with self._log_lock:
                if self._log.claim(user_id):
                    self._log.save()
            workouts, total = self._fetch_recent(client, user_id, tz)
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
                summary = summarize_workout(workout, perf)
                summary['previous_best_kj'] = previous_best_kj(identity, personal_records)
                summaries.append(summary)
            self._derive_args = self._derive(me)
            with self._log_lock:
                if self._log.merge(workouts):
                    self._save_log()
                walk = self._check_count(total, tz)
                derived = self._compute_derived(self._derive_args)
            if walk is not None:
                self._start_history_walk(client, user_id, rewalk=walk)
            with self._lock:
                generation = self._data['generation'] + 1
            refreshed_at = time.time()
            self._failures = 0
            delay = self._finish_attempt(started, interval,
                me=me, totals=extract_discipline_totals(overview), summaries=summaries,
                streaks=parse_streaks(overview),
                personal_records=personal_records,
                login_required=False, status='ready', last_updated=refreshed_at,
                last_error=None, generation=generation,
                active_day_count=len(active_day),
                data_stale=False, cache_loaded=False, consecutive_failures=0)
            self._publish_derived(*derived)
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
                return self._finish_attempt(started, interval,
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

    def _derive(self, me):
        return {'journey': self.config.get('journey'), 'metric': uses_metric(me),
                'tzname': self.config.get('timezone') or me.get('timezone')}

    def _compute_derived(self, args):
        """Log figures plus their sequence number. Call with the log lock held
        (or before the refresh thread starts)."""
        self._derived_computed += 1
        return self._log.derived(**args), self._derived_computed

    def _publish_derived(self, derived, sequence):
        with self._lock:
            if sequence > self._derived_published:
                self._data.update(derived)
                self._derived_published = sequence

    def _save_log(self):
        try:
            self._log.save()
        except (OSError, TypeError, ValueError) as exc:
            logger.warning('Could not save the workout log (%s)', type(exc).__name__)

    def _fetch_recent(self, client, user_id, tz):
        """The newest workouts, raw, plus Peloton's total workout count.

        One page normally. More only while the latest active day continues
        past it, while a still-filling log needs the rest of this week, or
        when none of the page is in the log yet (the board was off a while).
        """
        size = self.config.get('recent_fetch_size', 20)
        monday, _ = week_start(tz)
        workouts, total = [], None
        for page_number, rows, page in client.iter_workout_pages(user_id, size, max_pages=MAX_RECENT_PAGES):
            if page_number == 0:
                count = page.get('total')
                total = count if isinstance(count, int) and not isinstance(count, bool) else None
            workouts.extend(rows)
            if not self._needs_more(workouts, rows, tz, monday):
                break
        return workouts, total

    def _needs_more(self, workouts, rows, tz, monday):
        if not rows:
            return False
        oldest = rows[-1]
        active = last_active_day(workouts, tz)
        if not active or workout_date(oldest, tz) == workout_date(active[0], tz):
            return True
        with self._log_lock:
            complete = self._log.complete
            gap = complete and bool(self._log.workouts) and not any(
                self._log.knows(w.get('id')) for w in rows)
        if gap:
            return True
        stamp = workout_timestamp(oldest, tz)
        return not complete and stamp is not None and stamp >= monday

    def _check_count(self, total, tz):
        """Compare the log with Peloton's workout count. Returns None, or
        whether a history walk should start (False: backfill, True: re-walk).
        Call with the log lock held."""
        log = self._log
        if self._history_running():
            return None
        if not log.complete:
            return False
        if total is None:
            return None
        count = len(log.workouts)
        if count == total:
            if log.check['mismatches']:
                log.check['mismatches'] = 0
                self._save_log()
            return None
        log.check['mismatches'] += 1
        self._save_log()
        logger.warning('Workout log has %d workouts but Peloton reports %d (%d refresh(es) in a row)',
                       count, total, log.check['mismatches'])
        last = log.check['last_rewalk']
        due = (log.check['mismatches'] >= MISMATCH_LIMIT
               and (last is None or time.time() - last >= REWALK_INTERVAL_SECONDS)
               and (not self.refresh_schedule or in_quiet_hours(self.refresh_schedule, timezone_name=tz)))
        return True if due else None

    def _history_running(self):
        return self._history_thread is not None and self._history_thread.is_alive()

    def _start_history_walk(self, client, user_id, rewalk):
        if self._history_running() or self._stop.is_set():
            return
        self._history_thread = threading.Thread(target=self._walk_history, args=(client, user_id, rewalk),
                                                name='peloton-history', daemon=True)
        self._history_thread.start()

    def wait_for_history(self, timeout=None):
        """Wait for a running history download or re-walk. True once none is running."""
        thread = self._history_thread
        if thread is not None:
            thread.join(timeout)
        return not self._history_running()

    def _walk_history(self, client, user_id, rewalk):
        """Download the full history in batches into the log (backfill), or
        walk it again to repair it (re-walk). Saves after every batch, so an
        interrupted backfill resumes where it stopped."""
        batch = self.config.get('history_batch_size', 100)
        with self._log_lock:
            if rewalk:
                self._log.check['last_rewalk'] = time.time()
            start = 0 if rewalk else self._log.backfill['next_page']
            full = start == 0
            if full:
                self._log.begin_walk()
        kind = 're-walk' if rewalk else 'download'
        logger.info('Workout history %s started for %s (batches of %d, from batch %d)',
                    kind, self.log_path.name, batch, start)
        started = time.monotonic()
        finished = False
        try:
            last = None
            for page_number, rows, page in client.iter_workout_pages(
                    user_id, batch, start_page=start, max_pages=MAX_HISTORY_BATCHES):
                with self._log_lock:
                    if self._log.user_id != user_id:
                        return
                    self._log.merge(rows)
                    if not rewalk:
                        self._log.backfill['next_page'] = page_number + 1
                    self._save_log()
                last = page
                if not self._log_pause():
                    return
            with self._log_lock:
                removed = self._log.end_walk(remove_unseen=full)
                self._log.backfill = {'complete': True, 'next_page': 0, 'finished_at': time.time()}
                self._log.check['mismatches'] = 0
                self._save_log()
                count = len(self._log.workouts)
                derived = self._compute_derived(self._derive_args) if self._derive_args else None
            finished = True
            total = last.get('total') if last else None
            logger.info('Workout history %s finished: %d workouts in the log, Peloton reports %s, '
                        '%d removed, %.0fs', kind, count, total, removed, time.monotonic() - started)
            if derived:
                self._publish_derived(*derived)
        except (OSError, ValueError, requests.RequestException) as exc:
            logger.warning('Workout history %s paused (%s); it resumes on a later refresh',
                           kind, type(exc).__name__)
        finally:
            if not finished:
                with self._log_lock:
                    self._log.end_walk(remove_unseen=False)

    def _log_pause(self):
        """Pause between batches. False if the dashboard is stopping."""
        return not self._stop.wait(HISTORY_BATCH_PAUSE_SECONDS)

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
