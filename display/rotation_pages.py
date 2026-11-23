"""The rotation's page list: one builder per screen, each turning the dashboard's snapshot and the rider's
display settings into that screen's pages. Network-free: it only reads the snapshot it is given.

A page is (screen name, state, seconds). peloton_led.build_rotation_pages is this module's entry point.
Every page time comes from peloton.screen_times, as the settings page shows it. A screen that is off isn't
in `display.rotation` (old configs' 0s are switched off by load_config).
"""

import time
from typing import Any, NamedTuple

from display.ui.celebration_screen import discipline_noun, milestone_noun
from display.ui.last_workout.rotation import LAST_WORKOUT_DETAIL_INTERVAL_SECONDS, rotating_details, stats_phase_seconds
from display.ui.pr_celebration import pr_page_seconds
from display.ui.streak_screen import streak_views
from peloton.feeds.booked_classes import next_booking
from peloton.feeds.challenges import shown_challenges
from peloton.feeds.club import club_page
from peloton.feeds.goals import MAX_UPCOMING, UPCOMING_WITHIN, parse_milestone_key, upcoming_milestones, week_day, week_start
from peloton.screen_times import page_seconds
from peloton.selection import normalize_discipline
from peloton.stats.journey import journey_progress
from peloton.stats.totals import lifetime_overview_pages, total_workout_count
from peloton.stats.username_facts import shown_keys, username_details
from peloton.workouts.activity import daily_streak_start

DEFAULT_ROTATION = (
    'latest_workouts',
    'username',
    'streaks',
    'versus',
    'total_workouts',
    'next_milestone',
    'lifetime',
    'journey',
    'heatmap',
    'milestones',
    'goals',
    'challenges',
    'next_class',
    'club',
)
# The "loading" / "no workouts yet" page that stands in for Latest workouts.
STATUS_SECONDS = 2


class RotationInputs(NamedTuple):
    """What every builder reads: the arguments of build_rotation_pages, and the display timezone."""

    snapshot: dict
    dashboard: Any
    display: dict
    username: str
    matrix_height: int
    rivals: Any
    pass_index: int
    zone: Any

    def seconds(self, section, frames=1):
        """How long one page of `section` shows on this panel."""
        return page_seconds(self.display, section, self.matrix_height, frames)


def _latest_workout_pages(inputs):
    """Latest workouts: a page per workout of the latest day, each followed by its PR celebration when due;
    the loading / no-workouts status page when there are none."""
    snapshot, display = inputs.snapshot, inputs.display
    pages = []
    detail_interval = display.get('last_workout_detail_interval', LAST_WORKOUT_DETAIL_INTERVAL_SECONDS)
    if not snapshot['summaries']:
        status = snapshot['status'] if snapshot['status'] != 'ready' else 'empty'
        return [('status', status, STATUS_SECONDS)]
    for summary in snapshot['summaries']:
        # The screen intros, then cycles one stat at a time; size the page to exactly
        # one pass so every stat shows once: no cut-offs and no wrap-around repeats.
        page_duration = detail_interval + stats_phase_seconds(rotating_details(summary, inputs.matrix_height), detail_interval)
        pages.append(('last_workout', summary, page_duration))
        if inputs.dashboard.should_celebrate_pr(summary):
            # The trophy's entrance, then a turn per record broken: one interval plus a little more each.
            pages.append(('pr', summary, pr_page_seconds(summary, detail_interval)))
    return pages


def _username_pages(inputs):
    """Name and highlights: the name page with its facts."""
    details = username_details(inputs.snapshot, inputs.pass_index)
    # The page's time is shared by its highlights (at least 4 s each), so more time means each
    # stays up longer rather than the list starting over.
    duration = inputs.seconds('username', frames=len(details))
    state = {'username': inputs.username, 'details': details, 'fact_keys': shown_keys(details)}
    if details:
        state['detail_seconds'] = duration / len(details)
    return [('username', state, duration)]


def _streak_risk_page(inputs, streaks, duration):
    """The late-in-the-week reminder page when a weekly streak has nothing that counts yet, else None."""
    weekday = week_day(inputs.zone)
    reminder_day = inputs.display.get('streak_reminder_day', 5)
    if (
        reminder_day is not None
        and weekday >= reminder_day
        and inputs.snapshot.get('streak_week_workouts') == 0
        and streaks.get('current_weekly', 0) > 0
    ):
        # Late in the week with nothing that counts yet: one workout keeps the streak.
        return ('streak_risk', {'current': streaks['current_weekly'], 'days_left': 7 - weekday}, duration)
    return None


def _streak_pages(inputs):
    """Streaks: the weekly streak reminder, or one streak a pass (weekly, then daily)."""
    snapshot = inputs.snapshot
    if not streak_views(snapshot.get('streaks')):
        return []
    streaks = snapshot['streaks']
    duration = inputs.seconds('streaks')
    risk = _streak_risk_page(inputs, streaks, duration)
    if risk:
        return [risk]
    state = dict(streaks)
    if streaks.get('current_daily', 0) > 0:
        today = week_start(inputs.zone)[1].date()
        state.update(
            today=today.isoformat(),
            daily_start=daily_streak_start(
                streaks['current_daily'], today, snapshot.get('activity_days'), streaks.get('start_date_of_current_daily'), inputs.zone
            ).isoformat(),
        )
    # One streak per pass: weekly, then daily on the next pass.
    views = streak_views(state)
    state['view'] = views[inputs.pass_index % len(views)][0]
    return [('streak', state, duration)]


def _versus_pages(inputs):
    """Head to head: one page when two or more riders are compared."""
    if not inputs.rivals or len(inputs.rivals) < 2:
        return []
    from display.ui.versus_screen import STATS

    duration = inputs.seconds('versus')
    state = {'riders': inputs.rivals, 'weekday': week_day(inputs.zone)}
    if inputs.matrix_height < 64:
        # 32 rows show one stat at a time: the page's time shared by the stats, each shown once.
        state['stat_seconds'] = duration / len(STATS)
    return [('versus', state, duration)]


def _total_workouts_pages(inputs):
    """Total workouts: the all-time count on a Lifetime-length page."""
    total = total_workout_count(inputs.snapshot['totals'])
    if total is None:
        return []
    return [
        (
            'discipline',
            {
                'discipline': 'Total Workouts',
                'count': total,
                'color_key': inputs.display['color'],
                'number_font_key': 'big',
                'number_color_key': 'gold',
            },
            inputs.seconds('lifetime'),
        )
    ]


def _next_milestone_pages(inputs):
    """Next milestone: a countdown page for the total or a discipline a few workouts from its next target
    (usually none)."""
    snapshot, display, height = inputs.snapshot, inputs.display, inputs.matrix_height
    pages = []
    for upcoming in upcoming_milestones(
        total_workout_count(snapshot['totals']),
        display.get('milestones', []),
        display.get('milestone_step', 0),
        snapshot.get('totals'),
        within=display.get('milestone_within', UPCOMING_WITHIN),
        limit=display.get('milestone_pages', MAX_UPCOMING),
    ):
        # 2,200TH WORKOUT on 64 rows; TO 2,200 / WORKOUTS on 32.
        title = upcoming['label'] if upcoming['discipline'] or height < 64 else 'Workout'
        pages.append(
            (
                'countdown',
                {
                    'total': upcoming['count'],
                    'target': upcoming['target'],
                    'previous': upcoming['previous'],
                    'title': title,
                    'discipline': upcoming['discipline'],
                },
                inputs.seconds('next_milestone'),
            )
        )
    return pages


def _lifetime_pages(inputs):
    """Lifetime by discipline: the all-time totals, a few disciplines per page (4 on 64 rows, 2 on 32)."""
    overview_pages = lifetime_overview_pages(inputs.snapshot['totals'], page_size=4 if inputs.matrix_height >= 64 else 2)
    duration = inputs.seconds('lifetime')
    return [
        ('lifetime', {'items': items, 'page': index + 1, 'pages': len(overview_pages)}, duration)
        for index, items in enumerate(overview_pages)
    ]


def _journey_pages(inputs):
    """Journey: miles along the route, once the distance tally has something (e.g. after the backfill)."""
    progress = journey_progress(inputs.snapshot.get('distance_totals'), inputs.display.get('journey'))
    if not (progress and progress['miles'] > 0):
        return []
    from display.ui.journey_screen import journey_steps

    # 32 rows show the trip, then the miles by type: the page's time shared, each once.
    steps = journey_steps(progress, inputs.matrix_height)
    duration = inputs.seconds('journey', steps)
    if steps > 1:
        progress['step_seconds'] = duration / steps
    return [('journey', progress, duration)]


def _heatmap_pages(inputs):
    """Activity heatmap: the last 12 weeks, when there are activity days."""
    if not inputs.snapshot.get('activity_days'):
        return []
    from peloton.workouts.activity import HEATMAP_WEEKS

    today = week_start(inputs.zone)[1].date().isoformat()
    return [('heatmap', {'days': inputs.snapshot['activity_days'], 'today': today, 'weeks': HEATMAP_WEEKS}, inputs.seconds('heatmap'))]


def _goal_pages(inputs):
    """Weekly goals: a page per goal with a target above 0."""
    duration = inputs.seconds('goals')
    progress = inputs.snapshot.get('weekly_progress', {})
    return [
        ('goal', {'title': 'Weekly Goal', 'current': progress.get(key, 0), 'target': target, 'unit': key.replace('_', ' ')}, duration)
        for key, target in inputs.display.get('weekly_goals', {}).items()
        if target > 0
    ]


def _challenge_pages(inputs):
    """Challenges: a page per running challenge with progress, toward its next tier or at the top one earned (the cache is
    validated)."""
    duration = inputs.seconds('challenges')
    return [('challenge', challenge, duration) for challenge in shown_challenges(inputs.snapshot.get('challenges'), time.time())]


def _next_class_pages(inputs):
    """Next booked class: the soonest live or encore class, until it has been going a few minutes (the cache
    is validated)."""
    now = time.time()
    booking = next_booking(inputs.snapshot.get('booked_classes'), now)
    if booking is None:
        return []
    return [('next_class', {'booking': booking, 'now': now, 'timezone': inputs.zone}, inputs.seconds('next_class'))]


def _club_pages(inputs):
    """Club Peloton: the score's level and points, else the level from the profile (the cache is validated)."""
    club = club_page(inputs.snapshot.get('club'), inputs.snapshot.get('me'), time.time())
    return [] if club is None else [('club', club, inputs.seconds('club'))]


def _celebration_pages(inputs):
    """Milestone celebrations: one page per rotation, the newest total-workouts milestone (acknowledging it
    retires any older ones) and any discipline's taking turns pass by pass, so each shows during its day."""
    snapshot, dashboard, display = inputs.snapshot, inputs.dashboard, inputs.display
    candidates = []
    if display.get('milestones') or display.get('milestone_step'):
        pending = dashboard.pending_milestones(snapshot)
        if pending:
            candidates.append({'number': pending[-1], 'noun': milestone_noun(None), 'subtitle': inputs.username, 'milestone': pending[-1]})
    labels = {normalize_discipline(label): label for label in snapshot.get('totals', {})}
    for key in dashboard.pending_discipline_milestones(snapshot):
        discipline, target = parse_milestone_key(key)
        candidates.append(
            {'number': target, 'noun': discipline_noun(discipline, labels.get(discipline)), 'subtitle': inputs.username, 'milestone': key}
        )
    if not candidates:
        return []
    return [('celebration', candidates[inputs.pass_index % len(candidates)], inputs.seconds('milestones'))]


# Each rotation screen's builder, in the order they run (the order matters only to what they read from the
# dashboard and the clock). 'milestones' is not here: its celebration leads the rotation, wherever it sits.
PAGE_BUILDERS = (
    ('latest_workouts', _latest_workout_pages),
    ('username', _username_pages),
    ('streaks', _streak_pages),
    ('versus', _versus_pages),
    ('total_workouts', _total_workouts_pages),
    ('next_milestone', _next_milestone_pages),
    ('lifetime', _lifetime_pages),
    ('journey', _journey_pages),
    ('heatmap', _heatmap_pages),
    ('goals', _goal_pages),
    ('challenges', _challenge_pages),
    ('next_class', _next_class_pages),
    ('club', _club_pages),
)


def build_rotation_pages(snapshot, dashboard, display, username, matrix_height, rivals=None, pass_index=0):
    """Build one rotation from configured named sections.

    rivals: every configured rider's weekly progress, passed for only one
    rider per multi-user cycle so the head-to-head page shows once.
    pass_index: which rotation pass this is; the streak page shows the
    weekly streak on even passes and the daily one on odd passes, and the
    name page picks its varied highlights by it (peloton.stats.username_facts).
    """
    rotation = display.get('rotation', DEFAULT_ROTATION)
    zone = display.get('timezone') or (snapshot.get('me') or {}).get('timezone')
    inputs = RotationInputs(snapshot, dashboard, display, username, matrix_height, rivals, pass_index, zone)
    groups = {name: [] for name in rotation}
    for name, builder in PAGE_BUILDERS:
        if name in groups:
            groups[name] = builder(inputs)
    # A celebration leads the rotation (after the logo), wherever 'milestones' sits in it.
    celebrations = _celebration_pages(inputs) if 'milestones' in groups else []
    return celebrations + [page for section in rotation for page in groups[section]]
