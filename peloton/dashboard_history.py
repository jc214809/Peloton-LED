"""The workout log's side of a refresh: lifetime figures derived from it, the count check against Peloton's
total, and the background history download / re-walk.

`HistoryMixin` is mixed into `Dashboard` (peloton/dashboard.py). The log is guarded by the dashboard's
`_log_lock`; the derived-figure sequence numbers by `_lock` (in `_publish_derived`); both locks stay as
they were when this code lived in dashboard.py.
"""
import logging
import threading
import time

import requests

from .journey import uses_metric
from .schedule import in_quiet_hours

logger = logging.getLogger('peloton-led.dashboard')

# History walks: pause between batches, and a safety limit on batches.
HISTORY_BATCH_PAUSE_SECONDS = 1.0
MAX_HISTORY_BATCHES = 500
# The log's workout count must disagree with Peloton's this many refreshes in
# a row (riding out a lag right after a workout) before a full re-walk, which
# runs at most once a day and, with a refresh_schedule, in quiet hours.
MISMATCH_LIMIT = 3
REWALK_INTERVAL_SECONDS = 24 * 3600


class HistoryMixin:
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
