"""A workout's insight views for the board: the instructor milestone and the comparison with similar
earlier workouts (the workout row store), assembled as `insight_lines.board_view`s.

`InsightMixin` is mixed into `Dashboard` (peloton/dashboard.py). The row store and the insight caches are
guarded by the dashboard's `_rows_lock`, the workout log by `_log_lock`, as before.
"""
import logging
import time

import requests

from .dashboard_fetch import INSIGHT_RETRY_SECONDS
from .workouts.insight_lines import board_insights
from .feeds.instructors import class_numbers
from .workouts.workout_compare import DISCIPLINES as INSIGHT_DISCIPLINES
from .workouts.workout_features import build_row, discipline as row_discipline
from .workouts.workout_insights import insights, milestone_insight, with_milestone
from .workouts.workout_log import trim
from .workouts.workout_rows import RowStore, default_rows_path, trim_for_board

logger = logging.getLogger('peloton-led.dashboard')


class InsightMixin:
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
                store = self._loaded_rows()
                kept = self._insight_settling.get(identity)
                if not store.is_current(identity) or kept:
                    if not self._rebuild_row(client, identity, perf, settling, detail, kept):
                        return alone
                return self._insight_views_for(store, identity, milestone)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                raise
            self._insight_failed[identity] = time.monotonic()
            logger.warning('Workout insight failed (%s)', type(exc).__name__)
        except Exception as exc:  # never fail the refresh over an insight
            self._insight_failed[identity] = time.monotonic()
            logger.warning('Workout insight failed (%s)', type(exc).__name__)
        return alone

    def _loaded_rows(self):
        """The workout row store, loaded on first use. Call with the rows lock held."""
        if self._rows is None:
            self._rows = RowStore.load(default_rows_path(self.cache_path))
            # Rows older than any baseline reads are dropped, so the store stays its seeded size.
            self._rows.rows = trim_for_board(self._rows.rows, time.time())
            self._rows_generation += 1
        return self._rows

    def _row_inputs(self, client, identity, detail, kept):
        """The (workout detail, class details) a row is built from: the kept ones while settling, else fetched.
        None (remembered as failed) when the detail can't be had yet. Call with the rows lock held."""
        if kept:
            return kept
        failed_at = self._insight_failed.get(identity)
        if failed_at is not None and time.monotonic() - failed_at < INSIGHT_RETRY_SECONDS:
            return None
        detail = detail if detail is not None else client.get_workout_detail(identity)
        if not isinstance(detail, dict) or not detail.get('id') or detail.get('status') != 'COMPLETE':
            self._insight_failed[identity] = time.monotonic()
            return None
        ride_id = (detail.get('ride') or {}).get('id')
        ride = client.get_ride_details(ride_id) if ride_id else None
        return detail, ride

    def _rebuild_row(self, client, identity, perf, settling, detail, kept):
        """Build this workout's row into the store. False when its inputs couldn't be had.
        Call with the rows lock held."""
        inputs = self._row_inputs(client, identity, detail, kept)
        if inputs is None:
            return False
        detail, ride = inputs
        row = build_row(detail, perf, ride)
        self._insight_failed.pop(identity, None)
        if settling:
            self._insight_settling[identity] = (detail, ride)
        else:
            self._insight_settling.pop(identity, None)
        store = self._rows
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
        return True

    def _insight_views_for(self, store, identity, milestone):
        """The views, recomputed only when the store or the milestone moved. Call with the rows lock held."""
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
