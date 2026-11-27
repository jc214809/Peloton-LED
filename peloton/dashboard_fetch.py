"""What a refresh asks Peloton for besides the overview: personal records, recent workouts, per-workout detail,
and the optional pages' data (challenges, booked classes, Club Peloton).

`FetchMixin` is mixed into `Dashboard` (peloton/dashboard.py): these methods share its state (the caches
and the "last asked" clocks) and publish through its `_publish`, so they stay methods rather than functions.
"""

import logging
import time

import requests

from .config import DEFAULTS
from .feeds.booked_classes import reservation_ids, slim_class
from .feeds.challenges import parse_challenges
from .feeds.club import NOT_A_MEMBER, parse_score
from .feeds.goals import week_start
from .selection import last_active_day
from .timestamps import workout_date, workout_timestamp

logger = logging.getLogger('peloton-led.dashboard')

# Each refresh reads the newest page; more only to finish the latest day, cover
# this week while the log is still filling, or close a gap after downtime.
MAX_RECENT_PAGES = 10
# A workout whose detail could not be had (404, not COMPLETE yet) is not asked for again this long.
INSIGHT_RETRY_SECONDS = 3600
# Workouts whose detail can carry Peloton's movement tracker: strength classes and Tread Bootcamps (`circuit`; the
# Vision Tread counts the floor blocks' reps, first seen 2026-11-23). No bike or row bootcamp in either rider's
# history has ever been tracked, so they aren't asked.
TRACKED_DISCIPLINES = frozenset({'strength', 'circuit'})
# Challenge progress moves a class at a time, so hourly is plenty: 24 calls a day per rider. A failed
# fetch keeps the last list and tries again sooner.
CHALLENGES_REFRESH_SECONDS = 3600
CHALLENGES_RETRY_SECONDS = 900
# A booked class whose details could not be had is not asked for again this long (the reservations list
# itself is asked for every refresh: about 140-420 bytes, 288 calls a day at the default 300 s).
BOOKING_RETRY_SECONDS = 3600
# Club Peloton points move when a workout lands (2 a workout day) or weekly (streaks, high fives), so the score
# is asked for when a new workout shows up and every 6 hours: about 4-10 calls a day per rider. A failed fetch
# keeps the last figures and tries again sooner.
CLUB_REFRESH_SECONDS = 6 * 3600
CLUB_RETRY_SECONDS = 900


class FetchMixin:
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
        """A finished strength class's or Tread Bootcamp's workout detail (for the movement tracker's reps and
        weights), or None.

        Fetched once per class and kept while its signature holds; the workout insights reuse it rather
        than fetching it again. A failed or bad fetch retries after INSIGHT_RETRY_SECONDS. Only a 401 escapes."""
        identity = workout.get('id')
        if (
            not identity
            or workout.get('status') != 'COMPLETE'
            or str(workout.get('fitness_discipline') or '').lower() not in TRACKED_DISCIPLINES
        ):
            return None
        cached = self._details.get(identity)
        if cached and cached[0] == signature and (cached[1] is not None or time.monotonic() - cached[2] < INSIGHT_RETRY_SECONDS):
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

    def _shows_challenges(self):
        rotation = self.config.get('rotation', DEFAULTS['rotation'])
        return isinstance(rotation, list) and 'challenges' in rotation

    def _personal_records(self, client, user_id, overview):
        """The rider's records from /personal_records, which has the rowing Best Times /overview leaves out; on a
        failure, the overview's own list instead, so a refresh never fails over it. A 401 still ends the refresh."""
        try:
            records = client.get_personal_records(user_id)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                raise
            logger.warning("Personal records fetch failed (%s); using the overview's", type(exc).__name__)
            return overview
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Personal records fetch failed (%s); using the overview's", type(exc).__name__)
            return overview
        if not isinstance(records, dict) or not isinstance(records.get('personal_records'), list):
            logger.warning("Personal records response had no list; using the overview's")
            return overview
        return records

    def _refresh_challenges(self, client, user_id):
        """Fetch the joined challenges when due (hourly; sooner after a failure) and publish them. Only when the
        challenges page is in the rotation. A failure keeps the last list; only a 401 escapes."""
        if not self._shows_challenges():
            return
        now = time.monotonic()
        if self._challenges_checked_at is not None and now - self._challenges_checked_at < self._challenges_wait:
            return
        self._challenges_checked_at = now
        try:
            challenges = parse_challenges(client.get_current_challenges(user_id))
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                raise
            logger.warning('Challenges fetch failed (%s); keeping the last list', type(exc).__name__)
            self._challenges_wait = CHALLENGES_RETRY_SECONDS
            return
        except (requests.RequestException, ValueError) as exc:
            logger.warning('Challenges fetch failed (%s); keeping the last list', type(exc).__name__)
            self._challenges_wait = CHALLENGES_RETRY_SECONDS
            return
        self._challenges_wait = CHALLENGES_REFRESH_SECONDS
        self._publish(challenges=challenges)

    def _shows_next_class(self):
        rotation = self.config.get('rotation', DEFAULTS['rotation'])
        return isinstance(rotation, list) and 'next_class' in rotation

    def _scheduled_class(self, client, identity):
        """One booked class's details, slimmed, or None (logged) when they can't be had. Only a 401 escapes."""
        try:
            booking = slim_class(client.get_scheduled_class(identity), identity)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                raise
            booking, reason = None, type(exc).__name__
        except (requests.RequestException, ValueError) as exc:
            booking, reason = None, type(exc).__name__
        else:
            reason = 'not a class the page can show'
        if booking is None:
            logger.warning('Booked class %s: no details (%s); asking again in an hour', identity, reason)
        return booking

    def _refresh_bookings(self, client, user_id):
        """Every refresh while the next-class page is in the rotation: the booked classes' IDs (one small call),
        then each new one's details once, kept by ID while it stays booked. A failure keeps the last list and
        never fails the refresh; only a 401 escapes."""
        if not self._shows_next_class():
            return
        try:
            ids = reservation_ids(client.get_reservations(user_id))
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                raise
            logger.warning('Reservations fetch failed (%s); keeping the last list', type(exc).__name__)
            return
        except (requests.RequestException, ValueError) as exc:
            logger.warning('Reservations fetch failed (%s); keeping the last list', type(exc).__name__)
            return
        now = time.monotonic()
        bookings = []
        for identity in ids:
            booking = self._bookings.get(identity)
            failed_at = self._booking_failed.get(identity)
            if booking is None and (failed_at is None or now - failed_at >= BOOKING_RETRY_SECONDS):
                booking = self._scheduled_class(client, identity)
                if booking is None:
                    self._booking_failed[identity] = now
            if booking is not None:
                bookings.append(booking)
        self._bookings = {b['id']: b for b in bookings}
        self._booking_failed = {k: at for k, at in self._booking_failed.items() if k in ids}
        self._publish(booked_classes=sorted(bookings, key=lambda b: b['start']))

    def _shows_club(self):
        rotation = self.config.get('rotation', DEFAULTS['rotation'])
        return isinstance(rotation, list) and 'club' in rotation

    def _refresh_club(self, client, user_id, newest_workout):
        """Fetch the Club Peloton score when due (a new workout, else every 6 hours; sooner after a failure) and
        publish it. Only while the club page is in the rotation. The host is undocumented, so any failure,
        a 401 included, keeps the last figures and never fails the refresh; a 404 means the rider has no score."""
        if not self._shows_club():
            return
        now = time.monotonic()
        new_workout = newest_workout is not None and newest_workout != self._club_workout
        if self._club_checked_at is not None and not new_workout and now - self._club_checked_at < self._club_wait:
            return
        self._club_checked_at = now
        self._club_workout = newest_workout
        try:
            payload = client.get_club_score(user_id)
            club = NOT_A_MEMBER if payload is None else parse_score(payload, time.time())
        except (requests.RequestException, ValueError) as exc:
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            logger.warning(
                'Club Peloton score fetch failed (%s%s); keeping the last figures', type(exc).__name__, f' {status}' if status else ''
            )
            self._club_wait = CLUB_RETRY_SECONDS
            return
        self._club_wait = CLUB_REFRESH_SECONDS
        self._publish(club=club)

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
            gap = complete and bool(self._log.workouts) and not any(self._log.knows(w.get('id')) for w in rows)
        if gap:
            return True
        stamp = workout_timestamp(oldest, tz)
        return not complete and stamp is not None and stamp >= monday
