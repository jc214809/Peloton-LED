"""The dashboard snapshot's shape and its starting points: the empty snapshot, the demo's, and a cached one.

Pure functions (no locks, no network): `Dashboard.__init__` calls them and publishes what they return.
"""
import time

from .challenges import parse_challenges
from .demo import demo_bookings, demo_club, demo_data
from .goals import weekly_progress
from .summaries import summarize_workout
from .totals import extract_discipline_totals, parse_streaks

# The only profile fields the board reads; the rest of /api/me (email,
# birthday, phone, weight, ...) is never stored.
# badge_level: the Club Peloton level (0-10), shown until the club page's first score arrives.
PROFILE_KEYS = ('id', 'username', 'timezone', 'height_unit', 'created_at', 'badge_level')


def slim_profile(me):
    return {key: me[key] for key in PROFILE_KEYS if key in me}


def with_demo_insight(summary, data, config):
    """The demo's canned insights for this workout, only when display.workout_insights is on."""
    views = (data.get('insights') or {}).get(summary.get('workout_id'))
    if views and config.get('workout_insights'):
        summary = {**summary, 'insights': views}
    return summary


def initial_data():
    """A fresh snapshot dict: nothing fetched yet."""
    return {'me': None, 'totals': {}, 'summaries': [], 'login_required': False,
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
            'time_frames': {}, 'events': {}, 'challenges': [], 'booked_classes': [], 'club': None}


def demo_values(config, demo_login_needed):
    """The fields a demo dashboard publishes at construction."""
    data = demo_data()
    zone = config.get('timezone') or data['me'].get('timezone')
    return dict(me=data['me'], totals=extract_discipline_totals(data['overview']),
                streaks=parse_streaks(data['overview']),
                distance_totals=data['distance_totals'],
                summaries=[with_demo_insight(summarize_workout(w, data['performance'][w['id']]), data, config)
                           for w in data['workouts']],
                weekly_progress=weekly_progress(data['workouts'], zone),
                challenges=parse_challenges(data['challenges']),
                booked_classes=demo_bookings(time.time()),
                club=demo_club(time.time()),
                login_required=demo_login_needed, status='ready', last_updated=time.time(),
                generation=1)


def prepare_cached(cached, config):
    """Tidy a validated cache snapshot in place before it is published."""
    if isinstance(cached.get('me'), dict):
        cached['me'] = slim_profile(cached['me'])
    for summary in cached.get('summaries') or []:
        if isinstance(summary, dict):
            # Version 2's single two-line insight is never drawn again.
            summary.pop('insight', None)
            if not config.get('workout_insights'):
                # Switched off: cached insights must not keep showing.
                summary.pop('insights', None)
    return cached
