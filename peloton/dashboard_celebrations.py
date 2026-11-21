"""Which celebrations are due (PRs, total-workout and per-discipline milestones) and recording that one was
shown, plus the name page's fact cool-down.

`CelebrationMixin` is mixed into `Dashboard` (peloton/dashboard.py). Everything here reads and writes the
snapshot under the dashboard's `_lock`, then saves through its `_persist_snapshot`.
"""
import logging
import time

from .feeds.goals import local_date, parse_milestone_key, reached_discipline_milestones, reached_milestones
from .stats.username_facts import record_name_facts

logger = logging.getLogger('peloton-led.dashboard')

# A PR celebration keeps replaying this long after its first showing.
PR_CELEBRATION_SECONDS = 24 * 3600


class CelebrationMixin:
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
