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
from .selection import is_brief, last_active_day
from .summaries import summarize_workout
from .timestamps import workout_date, workout_timestamp
from .totals import extract_discipline_totals, parse_streaks
from .username_facts import record_name_facts
from .goals import (local_date, parse_milestone_key, reached_discipline_milestones, reached_milestones,
                    week_start, weekly_progress)
from .journey import uses_metric
from .schedule import in_quiet_hours, scheduled_refresh_interval
from .records import merge_personal_records, parse_personal_records, previous_best_kj
from .instructors import class_numbers
from .workout_log import WorkoutLog, default_log_path, trim
from .insight_lines import board_insights
from .workout_compare import DISCIPLINES as INSIGHT_DISCIPLINES
from .workout_features import build_row, discipline as row_discipline
from .workout_insights import insights, milestone_insight, with_milestone
from .workout_rows import RowStore, default_rows_path, trim_for_board

logger = logging.getLogger('peloton-led.dashboard')

# The padlock reads a file the renewal job writes; checking it every frame is waste.
RENEWAL_MARKER_CHECK_SECONDS = 30
# The only profile fields the board reads; the rest of /api/me (email,
# birthday, phone, weight, ...) is never stored.
PROFILE_KEYS = ('id', 'username', 'timezone', 'height_unit', 'created_at')
# id never changes and the rest rarely does, so the profile is fetched at
# startup and then once a day.
PROFILE_REFRESH_SECONDS = 24 * 3600
# Each refresh reads the newest page; more only to finish the latest day, cover
# this week while the log is still filling, or close a gap after downtime.
# A PR celebration keeps replaying this long after its first showing.
PR_CELEBRATION_SECONDS = 24 * 3600
MAX_RECENT_PAGES = 10
# History walks: pause between batches, and a safety limit on batches.
HISTORY_BATCH_PAUSE_SECONDS = 1.0
MAX_HISTORY_BATCHES = 500
# The log's workout count must disagree with Peloton's this many refreshes in
# a row (riding out a lag right after a workout) before a full re-walk, which
# runs at most once a day and, with a refresh_schedule, in quiet hours.
MISMATCH_LIMIT = 3
REWALK_INTERVAL_SECONDS = 24 * 3600
# A workout whose detail could not be had (404, not COMPLETE yet) is not asked for again this long.
INSIGHT_RETRY_SECONDS = 3600


def slim_profile(me):
    return {key: me[key] for key in PROFILE_KEYS if key in me}


def with_demo_insight(summary, data, config):
    """The demo's canned insights for this workout, only when display.workout_insights is on."""
    views = (data.get('insights') or {}).get(summary.get('workout_id'))
    if views and config.get('workout_insights'):
        summary = {**summary, 'insights': views}
    return summary


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
        # {workout ID: (signature, detail or None, monotonic fetch time)}: a strength class's workout detail
        # (movement tracker), fetched once per finished class; a failed fetch retries after INSIGHT_RETRY_SECONDS.
        self._details = OrderedDict()
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
                      'celebrated_pr_ids': [], 'pr_shown_at': {}, 'celebrated_milestones': [],
                      'milestone_shown_at': {}, 'name_facts_passes': 0, 'name_facts_shown': {},
                      'celebrated_discipline_milestones': [], 'discipline_milestone_shown_at': {},
                      'weekly_progress': {'workouts': 0, 'minutes': 0},
                      'instructor_counts': {}, 'instructor_names': {}, 'streaks': {},
                      'distance_totals': {}, 'personal_records': {},
                      'streak_week_workouts': None, 'activity_days': {},
                      'time_frames': {}, 'events': {}}
        self.demo = demo
        if demo:
            data = demo_data()
            zone = config.get('timezone') or data['me'].get('timezone')
            self._publish(me=data['me'], totals=extract_discipline_totals(data['overview']),
                streaks=parse_streaks(data['overview']),
                distance_totals=data['distance_totals'],
                summaries=[with_demo_insight(summarize_workout(w, data['performance'][w['id']]), data, config)
                           for w in data['workouts']],
                weekly_progress=weekly_progress(data['workouts'], zone),
                login_required=demo_login_needed, status='ready', last_updated=time.time(),
                generation=1)
        else:
            cached = load_snapshot(self.cache_path)
            if cached is not None:
                if isinstance(cached.get('me'), dict):
                    cached['me'] = slim_profile(cached['me'])
                for summary in cached.get('summaries') or []:
                    if isinstance(summary, dict):
                        # Version 2's single two-line insight is never drawn again.
                        summary.pop('insight', None)
                        if not config.get('workout_insights'):
                            # Switched off: cached insights must not keep showing.
                            summary.pop('insights', None)
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

    def should_celebrate_pr(self, summary, now=None):
        """A PR workout's celebration is due for 24 hours after its first showing (so a rider who
        wasn't watching that one cycle still sees it; milestones use the board's day instead). With
        `pr_max_age_days` set, a workout older than that is never celebrated."""
        identity = summary.get('workout_id') if isinstance(summary, dict) else None
        if not identity or not summary.get('is_pr'):
            return False
        now = time.time() if now is None else now
        max_age = self.config.get('pr_max_age_days')
        workout_at = summary.get('workout_at')
        if (max_age and isinstance(workout_at, (int, float)) and not isinstance(workout_at, bool)
                and now - workout_at > max_age * 86400):
            return False
        with self._lock:
            if identity in self._data['celebrated_pr_ids']:
                return False
            shown = (self._data.get('pr_shown_at') or {}).get(identity)
        return shown is None or now - shown < PR_CELEBRATION_SECONDS

    def acknowledge_pr(self, workout_id, now=None):
        """Record a displayed PR celebration immediately and durably. The first showing starts its
        24 hours; a later acknowledgement after that retires it (and any other expired one) for good."""
        if not workout_id:
            return
        now = time.time() if now is None else now
        self._acknowledge(workout_id, [], 'celebrated_pr_ids', 'pr_shown_at', str, now, rolling=True)

    def acknowledge_name_facts(self, keys):
        """Record that a name page showed these facts (their `key`s): one more page, and the cool-down
        of each starts. Saved at once, so a restart keeps it."""
        with self._lock:
            self._data['name_facts_passes'], self._data['name_facts_shown'] = record_name_facts(
                self._data.get('name_facts_passes') or 0, self._data.get('name_facts_shown') or {}, keys)
        try:
            self._persist_snapshot()
        except (OSError, TypeError, ValueError) as exc:
            logger.warning('Could not persist name page state (%s)', type(exc).__name__)

    def _celebration_zone(self, data):
        return self.config.get('timezone') or (data.get('me') or {}).get('timezone')

    def pending_milestones(self, snapshot=None, now=None):
        """Reached milestones still to celebrate: never shown, or first shown
        earlier today (the board's day), so a rider who wasn't watching that
        one cycle still sees it. Oldest first."""
        data = snapshot or self.snapshot()
        total = data.get('totals', {}).get('Total Workouts')
        reached = reached_milestones(total, self.config.get('milestones', []),
                                     self.config.get('milestone_step', 0))
        return self._still_to_celebrate(data, reached, data.get('celebrated_milestones', []),
                                        data.get('milestone_shown_at'), now)

    def pending_discipline_milestones(self, snapshot=None, now=None):
        """Per-discipline milestones ('strength:500') still to celebrate, as pending_milestones."""
        data = snapshot or self.snapshot()
        reached = reached_discipline_milestones(data.get('totals', {}))
        return self._still_to_celebrate(data, reached, data.get('celebrated_discipline_milestones', []),
                                        data.get('discipline_milestone_shown_at'), now)

    def _still_to_celebrate(self, data, reached, celebrated, shown, now):
        celebrated, shown = set(celebrated or []), shown or {}
        now = time.time() if now is None else now
        zone = self._celebration_zone(data)
        today = local_date(now, zone)
        return [value for value in reached if value not in celebrated
                and local_date(shown.get(str(value), now), zone) == today]

    def acknowledge_milestone(self, milestone, now=None):
        """Record that milestone's celebration was shown: a total-workouts milestone (an int) or a
        per-discipline one ('strength:500').

        The first showing starts its day; after midnight it's done for good. Lower milestones still
        pending (of the same discipline) are done too: only the newest one is celebrated (e.g.
        100/250/500 all reached when first set up).
        """
        now = time.time() if now is None else now
        if isinstance(milestone, int) and not isinstance(milestone, bool):
            lower = [value for value in self.pending_milestones(now=now) if value < milestone]
            self._acknowledge(milestone, lower, 'celebrated_milestones', 'milestone_shown_at', int, now)
            return
        parsed = parse_milestone_key(milestone)
        if parsed is None:
            return
        lower = [key for key in self.pending_discipline_milestones(now=now)
                 if (other := parse_milestone_key(key)) and other[0] == parsed[0] and other[1] < parsed[1]]
        self._acknowledge(milestone, lower, 'celebrated_discipline_milestones',
                          'discipline_milestone_shown_at', str, now)

    def _acknowledge(self, milestone, lower, celebrated_key, shown_key, parse, now, rolling=False):
        with self._lock:
            today = local_date(now, self._celebration_zone(self._data))
            celebrated = list(self._data.get(celebrated_key) or [])
            shown = dict(self._data.get(shown_key) or {})
            expired = [parse(key) for key, at in shown.items()
                       if (now - at >= PR_CELEBRATION_SECONDS if rolling
                           else local_date(at, self._celebration_zone(self._data)) != today)]
            done = [value for value in lower + expired if value not in celebrated]
            for value in expired:
                del shown[str(value)]
            started = (str(milestone) not in shown and milestone not in celebrated
                       and milestone not in done)
            if started:
                shown[str(milestone)] = now
            if not done and not started:
                return
            self._data[celebrated_key] = (celebrated + done)[-256:]
            self._data[shown_key] = shown
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

    def _strength_detail(self, client, workout, signature):
        """A finished strength class's workout detail (for the movement tracker's reps and weights), or None.

        Fetched once per class and kept while its signature holds; the workout insights reuse it rather
        than fetching it again. A failed or bad fetch retries after INSIGHT_RETRY_SECONDS. Only a 401 escapes."""
        identity = workout.get('id')
        if (not identity or workout.get('status') != 'COMPLETE'
                or str(workout.get('fitness_discipline') or '').lower() != 'strength'):
            return None
        cached = self._details.get(identity)
        if cached and cached[0] == signature and (
                cached[1] is not None or time.monotonic() - cached[2] < INSIGHT_RETRY_SECONDS):
            self._details.move_to_end(identity)
            return cached[1]
        try:
            detail = client.get_workout_detail(identity)
            if not isinstance(detail, dict) or detail.get('id') != identity or detail.get('status') != 'COMPLETE':
                detail = None
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                raise
            logger.warning('Workout detail failed (%s)', type(exc).__name__)
            detail = None
        except (requests.RequestException, ValueError) as exc:
            logger.warning('Workout detail failed (%s)', type(exc).__name__)
            detail = None
        self._details[identity] = (signature, detail, time.monotonic())
        self._details.move_to_end(identity)
        while len(self._details) > self._performance_cache_size:
            self._details.popitem(last=False)
        return detail

    def _stamp(self):
        try:
            stat = self.token_path.stat()
            return (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None

    def _milestone(self, workout):
        """The instructor-milestone message for this workout, or None: counted from the workout log, so only
        once the log has the whole history (a partial log would call the 3rd class the 1st)."""
        try:
            identity, row, names = trim(workout)
            with self._log_lock:
                if identity is None or not self._log.complete:
                    return None
                return milestone_insight(class_numbers(self._log.workouts, identity, row,
                                                       {**self._log.instructors, **names}))
        except Exception as exc:  # never fail the refresh over an insight
            logger.warning('Instructor milestone failed (%s)', type(exc).__name__)
            return None

    def _workout_insight(self, client, workout, perf, settling, detail=None):
        """The board's views (insight_lines.board_view) comparing this workout with similar earlier ones, or None.

        From the first refresh that sees the workout COMPLETE: the workout and class details are fetched
        once and the row built (a strength class's workout detail comes in as `detail`, already fetched
        for the page's tracker stats). While the workout is still settling (its first hour, when the performance
        graph is refetched each refresh), each refresh rebuilds the row from the kept details and the new
        graph, and logs when the row changed; the first refresh after the hour rebuilds it one last time.
        The views are recomputed only when the row store changed (a new or rebuilt row, or a reload):
        peers are earlier workouts, so nothing else moves them. Only a 401 escapes."""
        identity = workout.get('id')
        if not identity or workout.get('status') != 'COMPLETE':
            return None
        # The milestone needs the workout log, not the row store, so every discipline can have one and a
        # failed row build still shows it.
        milestone = self._milestone(workout)
        alone = board_insights(with_milestone([], milestone)) or None
        if row_discipline(workout.get('fitness_discipline')) not in INSIGHT_DISCIPLINES:
            return alone
        try:
            with self._rows_lock:
                if self._rows is None:
                    self._rows = RowStore.load(default_rows_path(self.cache_path))
                    # Rows older than any baseline reads are dropped, so the store stays its seeded size.
                    self._rows.rows = trim_for_board(self._rows.rows, time.time())
                    self._rows_generation += 1
                store = self._rows
                kept = self._insight_settling.get(identity)
                if not store.is_current(identity) or kept:
                    if kept:
                        detail, ride = kept
                    else:
                        failed_at = self._insight_failed.get(identity)
                        if failed_at is not None and time.monotonic() - failed_at < INSIGHT_RETRY_SECONDS:
                            return alone
                        detail = detail if detail is not None else client.get_workout_detail(identity)
                        if not isinstance(detail, dict) or not detail.get('id') or detail.get('status') != 'COMPLETE':
                            self._insight_failed[identity] = time.monotonic()
                            return alone
                        ride_id = (detail.get('ride') or {}).get('id')
                        ride = client.get_ride_details(ride_id) if ride_id else None
                    row = build_row(detail, perf, ride)
                    self._insight_failed.pop(identity, None)
                    if settling:
                        self._insight_settling[identity] = (detail, ride)
                    else:
                        self._insight_settling.pop(identity, None)
                    # A rebuild that comes out the same writes nothing: the store is 1-2 MB, and a Pi Zero
                    # would otherwise rewrite it every refresh of the settling hour.
                    if store.rows.get(identity) != row:
                        if kept:
                            logger.info('Workout %s changed while settling', identity[:8])
                        store.upsert(row)
                        self._rows_generation += 1
                        try:
                            store.save()
                        except OSError as exc:
                            logger.warning('Could not save the workout rows (%s)', type(exc).__name__)
                # The views also move with the milestone (the log may finish its history after the first refresh).
                key = (self._rows_generation, milestone)
                cached = self._insight_views.get(identity)
                if cached and cached[0] == key:
                    return cached[1]
                views = board_insights(with_milestone(insights(store.rows[identity], store.current_rows()),
                                                      milestone)) or None
                if cached and cached[1] != views:
                    logger.info('Workout %s insights changed', identity[:8])
                self._insight_views[identity] = (key, views)
                return views
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                raise
            self._insight_failed[identity] = time.monotonic()
            logger.warning('Workout insight failed (%s)', type(exc).__name__)
        except Exception as exc:  # never fail the refresh over an insight
            self._insight_failed[identity] = time.monotonic()
            logger.warning('Workout insight failed (%s)', type(exc).__name__)
        return alone

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
            # A workout under a minute (a start tapped by accident) isn't a latest workout,
            # and doesn't make its day the last active one on its own.
            active_day = last_active_day([w for w in workouts if not is_brief(w)], tz)
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
                detail = self._strength_detail(client, workout, signature)
                summary = summarize_workout(workout, perf, detail)
                summary['previous_best_kj'] = previous_best_kj(identity, personal_records)
                if self.config.get('workout_insights'):
                    views = self._workout_insight(client, workout, perf, settling, detail)
                    if views:
                        summary['insights'] = views
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
                'tzname': self.config.get('timezone') or me.get('timezone'),
                'member_since': me.get('created_at')}

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
