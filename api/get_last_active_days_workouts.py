"""Get completed workouts from the most recent local active day."""
import logging
from peloton.selection import last_active_day

logger = logging.getLogger('peloton-led.workouts')


def get_last_active_days_workouts(client, user_id, limit=50, days=30, tzname=None):
    try:
        recent = client.get_recent_workouts(user_id, limit=limit, days=days) or []
    except Exception as exc:
        logger.warning('Could not fetch recent workouts: %s', type(exc).__name__)
        return []
    return last_active_day(recent, tzname)


class GetLastActiveDaysWorkouts:
    def __call__(self, client, user_id, limit=50, days=30, tzname=None):
        return get_last_active_days_workouts(client, user_id, limit, days, tzname)
