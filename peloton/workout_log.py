"""Per-rider log of every workout, as slim rows keyed by workout ID.

The log is a local copy of history Peloton already keeps: losing or damaging
it only costs a re-download. Lifetime figures (instructor counts, journey
miles, this week's progress) are recomputed from it, so a counting fix never
needs new API calls. See docs/WORKOUT-LOG-PLAN.md.
"""
import json
import logging
import os
from pathlib import Path

from .goals import weekly_progress
from .instructors import merge_instructor_counts
from .journey import merge_distance_totals
from .selection import discipline_of
from .timestamps import workout_timestamp

logger = logging.getLogger('peloton-led.workout-log')

LOG_VERSION = 1
HR_ZONES = 5


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _text(value):
    return value if isinstance(value, str) and value else None


def length_seconds(workout):
    """The workout length "this week" minutes have always used."""
    ride = workout.get('ride') if isinstance(workout.get('ride'), dict) else {}
    value = workout.get('duration') or workout.get('length') or ride.get('duration') or 0
    return value if _number(value) is not None else 0


def trim(workout):
    """One history row as a slim log row, plus any instructor name it carries.

    Returns (workout_id, row, {instructor_id: name}); workout_id is None for
    rows that can't be logged (no ID).
    """
    identity = _text(workout.get('id')) if isinstance(workout, dict) else None
    if identity is None:
        return None, None, {}
    ride = workout.get('ride') if isinstance(workout.get('ride'), dict) else {}
    instructor = ride.get('instructor') if isinstance(ride.get('instructor'), dict) else {}
    stamp = workout_timestamp(workout)
    instructor_id = _text(instructor.get('id'))
    group = None
    names = {}
    if instructor_id and instructor.get('is_instructor_group'):
        members = instructor.get('individual_instructor_ids')
        group = sorted({m for m in members if _text(m)}) if isinstance(members, list) else []
    elif instructor_id:
        name = (instructor.get('name') or instructor.get('display_name') or '')
        if isinstance(name, str) and name.strip():
            names[instructor_id] = name.strip()
    zones = (workout.get('effort_zones') or {}) if isinstance(workout.get('effort_zones'), dict) else {}
    durations = zones.get('heart_rate_zone_durations') if isinstance(zones.get('heart_rate_zone_durations'), dict) else {}
    hr_zone_s = [_number(durations.get(f'heart_rate_z{zone}_duration')) for zone in range(1, HR_ZONES + 1)]
    row = {
        'start': int(stamp.timestamp()) if stamp else None,
        'end': _number(workout.get('end_time')),
        'tz': _text(workout.get('timezone')),
        'status': _text(workout.get('status')),
        'discipline': discipline_of({**workout, 'ride': ride}) or None,
        'ride_id': _text(ride.get('id')),
        'title': _text(ride.get('title')) or _text(workout.get('title')) or _text(workout.get('name')),
        'class_length_s': length_seconds(workout),
        'total_work_j': _number(workout.get('total_work')),
        'distance': _number(workout.get('distance')),
        'calories': _number(workout.get('calories')),
        'instructor_id': instructor_id,
        'group_ids': group,
        'pr_output': workout.get('is_total_work_personal_record') is True,
        'pr_splits': workout.get('is_splits_personal_record') is True,
        'effort_points': _number(zones.get('total_effort_points')),
        'hr_zone_s': hr_zone_s if any(v is not None for v in hr_zone_s) else None,
        'counts_for_streaks': workout.get('is_3p_fit_feed_workout_excluded_from_streaks') is not True,
    }
    return identity, row, names


def as_workout(identity, row, instructors):
    """A log row in the shape of a Peloton history row, so the existing
    tally, journey and weekly functions read it exactly as they read the API."""
    instructor = {'id': row.get('instructor_id')}
    if row.get('group_ids') is not None:
        instructor.update(is_instructor_group=True, individual_instructor_ids=row['group_ids'])
    elif row.get('instructor_id') in instructors:
        instructor['name'] = instructors[row['instructor_id']]
    return {'id': identity, 'start_time': row.get('start'), 'timezone': row.get('tz'),
            'status': row.get('status'), 'fitness_discipline': row.get('discipline'),
            'distance': row.get('distance'), 'total_work': row.get('total_work_j'),
            'duration': row.get('class_length_s'),
            'ride': {'instructor': instructor}}


def _valid_row(row):
    return (isinstance(row, dict) and (row.get('start') is None or _number(row['start']) is not None)
            and (row.get('status') is None or isinstance(row['status'], str)))


class WorkoutLog:
    def __init__(self, path):
        self.path = Path(path)
        self.user_id = None
        self.workouts = {}
        self.instructors = {}
        self.backfill = {'complete': False, 'next_page': 0, 'finished_at': None}
        self.check = {'mismatches': 0, 'last_rewalk': None}
        self._walk_seen = None
        self.revision = 0

    @classmethod
    def load(cls, path):
        """Read the log, or start an empty one if it's missing, damaged or from another version."""
        log = cls(path)
        try:
            payload = json.loads(log.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return log
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            logger.warning('Workout log %s is unreadable (%s); rebuilding it', log.path, type(exc).__name__)
            return log
        if not isinstance(payload, dict) or payload.get('version') != LOG_VERSION:
            logger.warning('Workout log %s has an unknown format; rebuilding it', log.path)
            return log
        workouts, instructors = payload.get('workouts'), payload.get('instructors')
        backfill, check = payload.get('backfill'), payload.get('check')
        if (not isinstance(workouts, dict) or not all(_valid_row(r) for r in workouts.values())
                or not isinstance(instructors, dict)
                or not all(isinstance(v, str) for v in instructors.values())
                or not isinstance(backfill, dict) or not isinstance(check, dict)
                or not (payload.get('user_id') is None or isinstance(payload.get('user_id'), str))):
            logger.warning('Workout log %s is damaged; rebuilding it', log.path)
            return log
        log.user_id = payload.get('user_id')
        log.workouts, log.instructors = workouts, instructors
        log.backfill = {'complete': backfill.get('complete') is True,
                        'next_page': backfill.get('next_page') if isinstance(backfill.get('next_page'), int) else 0,
                        'finished_at': _number(backfill.get('finished_at'))}
        mismatches = check.get('mismatches')
        log.check = {'mismatches': mismatches if isinstance(mismatches, int) and not isinstance(mismatches, bool) else 0,
                     'last_rewalk': _number(check.get('last_rewalk'))}
        return log

    def save(self):
        """Atomically write the log, owner-only, like the dashboard cache."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f'.{self.path.name}.tmp')
        payload = {'version': LOG_VERSION, 'user_id': self.user_id, 'backfill': self.backfill,
                   'check': self.check, 'instructors': self.instructors, 'workouts': self.workouts}
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, separators=(',', ':'), allow_nan=False, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @property
    def complete(self):
        return self.backfill['complete']

    def claim(self, user_id):
        """Tie the log to a Peloton account; a different account starts over.
        Returns True when the log was reset."""
        if self.user_id == user_id:
            return False
        if self.user_id is not None:
            logger.warning('Workout log %s belongs to another Peloton account; starting a new one', self.path)
        reset = self.user_id is not None or bool(self.workouts)
        self.__init__(self.path)
        self.user_id = user_id
        return reset

    def merge(self, workouts):
        """Add or overwrite rows by workout ID. Returns the IDs that changed."""
        changed = []
        for workout in workouts:
            identity, row, names = trim(workout)
            if identity is None:
                continue
            if self._walk_seen is not None:
                self._walk_seen.add(identity)
            for instructor_id, name in names.items():
                if self.instructors.get(instructor_id) != name:
                    self.instructors[instructor_id] = name
                    changed.append(identity)
            if self.workouts.get(identity) != row:
                self.workouts[identity] = row
                changed.append(identity)
        if changed:
            self.revision += 1
        return list(dict.fromkeys(changed))

    def knows(self, workout_id):
        return workout_id in self.workouts

    def begin_walk(self):
        """Start remembering every ID seen, so a full walk can drop deleted workouts."""
        self._walk_seen = set()

    def end_walk(self, remove_unseen):
        """Finish a walk. With remove_unseen, rows Peloton no longer returned
        (and no refresh merged meanwhile) are deleted. Returns how many."""
        seen, self._walk_seen = self._walk_seen, None
        if not remove_unseen or seen is None:
            return 0
        gone = [identity for identity in self.workouts if identity not in seen]
        for identity in gone:
            del self.workouts[identity]
        if gone:
            self.revision += 1
        return len(gone)

    def as_workouts(self):
        """Every row as a history-shaped workout, newest first."""
        rows = sorted(self.workouts.items(), key=lambda item: (item[1].get('start') or 0, item[0]),
                      reverse=True)
        return [as_workout(identity, row, self.instructors) for identity, row in rows]

    def derived(self, journey=None, metric=False, tzname=None, now=None):
        """Figures the screens read, computed from the whole log.

        Instructor counts and journey miles stay empty until the backfill has
        the full history, so a partial log never shows a too-small total.
        """
        workouts = self.as_workouts()
        result = {'weekly_progress': weekly_progress(workouts, tzname, now=now)}
        if self.complete:
            counts, names = merge_instructor_counts({}, {}, workouts)
            since = (journey or {}).get('start_date')
            result.update(instructor_counts=counts, instructor_names=names,
                          distance_totals=merge_distance_totals({}, workouts, metric, since=since, tzname=tzname))
        else:
            result.update(instructor_counts={}, instructor_names={}, distance_totals={})
        return result


def default_log_path(cache_path):
    """dashboard-cache-joel.json -> dashboard-cache-joel.workouts.json"""
    cache_path = Path(cache_path)
    return cache_path.with_name(f'{cache_path.stem}.workouts.json')
