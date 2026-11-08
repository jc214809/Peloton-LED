#!/usr/bin/env python3
"""Peloton LED dashboard: network-free screen rotation over background snapshots."""
import logging
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from peloton.activity import daily_streak_start
from peloton.config import load_config, load_dotenv, user_token_path
from peloton.dashboard import Dashboard
from peloton.goals import (MAX_UPCOMING, UPCOMING_WITHIN, parse_milestone_key, upcoming_milestones, week_day,
                           week_start)
from peloton.journey import journey_progress
from peloton.selection import normalize_discipline
from peloton.instructors import top_instructors
from peloton.totals import extract_discipline_totals, lifetime_overview_pages, total_workout_count  # Kept available for callers.
from utils import heartbeat
from utils.utils import args, ensure_privileges_dropped, led_matrix_options
from utils.username import resolve_display_username
from utils.wifi_setup import hotspot_name
from display.ui.last_workout_screen import (LAST_WORKOUT_DETAIL_INTERVAL_SECONDS, rotating_details,
                                           stats_phase_seconds)
from display.ui.settings_pin import shown_pin
from display.ui.pr_celebration import BURST_SECONDS as PR_BURST_SECONDS, SETTLE_SECONDS as PR_SETTLE_SECONDS
from display.ui.celebration_screen import INTRO_SECONDS, MIN_CARD_SECONDS, discipline_noun, milestone_noun
from display.ui.streak_screen import streak_views

logger = logging.getLogger('peloton-led')
ROOT = Path(__file__).resolve().parent
DEFAULT_ROTATION = ('latest_workouts', 'username', 'streaks', 'versus', 'total_workouts',
                    'next_milestone', 'lifetime', 'journey', 'heatmap',
                    'milestones', 'goals')
# Seconds per Wi-Fi setup page; the hotspot is rechecked between pages.
WIFI_SETUP_PAGE_SECONDS = 5


def scheduled_brightness(display, now=None, timezone_name=None):
    """Return scheduled brightness, or None when scheduling is disabled."""
    schedule = display.get('brightness_schedule')
    if not schedule:
        return None
    zone_name = display.get('timezone') or timezone_name
    zone = ZoneInfo(zone_name) if zone_name else None
    current = now or datetime.now(zone)
    minute = current.hour * 60 + current.minute
    day_hour, day_minute = map(int, schedule['day_start'].split(':'))
    night_hour, night_minute = map(int, schedule['night_start'].split(':'))
    day_start = day_hour * 60 + day_minute
    night_start = night_hour * 60 + night_minute
    if day_start <= night_start:
        daytime = day_start <= minute < night_start
    else:
        daytime = minute >= day_start or minute < night_start
    return schedule['day' if daytime else 'night']


def apply_scheduled_brightness(matrix, display, now=None, timezone_name=None):
    brightness = scheduled_brightness(display, now, timezone_name)
    if brightness is not None and getattr(matrix, 'brightness', None) != brightness:
        matrix.brightness = brightness


def _duration(display, section, fallback):
    return display.get('screen_durations', {}).get(section, fallback)


def build_rotation_pages(snapshot, dashboard, display, username, matrix_height, rivals=None,
                         pass_index=0):
    """Build one rotation from configured named sections.

    rivals: every configured rider's weekly progress, passed for only one
    rider per multi-user cycle so the head-to-head page shows once.
    pass_index: which rotation pass this is; the streak page shows the
    weekly streak on even passes and the daily one on odd passes.
    """
    rotation = display.get('rotation', DEFAULT_ROTATION)
    groups = {name: [] for name in rotation}
    workout_duration = _duration(display, 'latest_workouts', display['last_workout_duration'])
    detail_interval = display.get('last_workout_detail_interval', LAST_WORKOUT_DETAIL_INTERVAL_SECONDS)
    if 'latest_workouts' in groups:
        if snapshot['summaries']:
            for summary in snapshot['summaries']:
                states = [summary]
                compact = matrix_height < 64 and display.get('compact_workout_pages')
                if compact:
                    states = [{**summary, 'compact_page': page} for page in (0, 1)]
                # On the full-board layout the screen intros, then cycles one
                # stat at a time; size the page to exactly one pass so every
                # stat shows once — no cut-offs and no wrap-around repeats.
                if workout_duration > 0 and not compact:
                    page_duration = detail_interval + stats_phase_seconds(
                        rotating_details(summary, matrix_height), detail_interval)
                else:
                    page_duration = workout_duration
                for state in states:
                    groups['latest_workouts'].append(('last_workout', state, page_duration))
                if dashboard.should_celebrate_pr(summary):
                    # Burst + settle animation, then the card holds one interval.
                    pr_duration = _duration(display, 'milestones', display['overview_duration'])
                    if pr_duration > 0:
                        pr_duration = PR_BURST_SECONDS + PR_SETTLE_SECONDS + detail_interval
                    groups['latest_workouts'].append(('pr', summary, pr_duration))
        else:
            status = snapshot['status'] if snapshot['status'] != 'ready' else 'empty'
            groups['latest_workouts'].append(
                ('status', status, min(workout_duration, 2)))
    if 'username' in groups:
        totals = snapshot.get('totals', {})
        total = total_workout_count(totals)
        progress = snapshot.get('weekly_progress', {})
        disciplines = [(label, count) for label, count in totals.items()
                       if label != 'Total Workouts' and isinstance(count, int)]
        favorite = max(disciplines, key=lambda item: item[1], default=None)
        details = []
        if total is not None:
            details.append({'label': 'TOTAL WORKOUTS', 'value': f'{total:,}',
                            'lines': [f'{total:,}'], 'font_key': 'big', 'color_key': 'gold'})
        weekly_workouts = progress.get('workouts', 0)
        weekly_minutes = progress.get('minutes', 0)
        details.append({'label': 'THIS WEEK',
                        'value': f'{weekly_workouts} WORKOUTS / {weekly_minutes} MIN',
                        'lines': [f'{weekly_workouts} WORKOUTS', f'{weekly_minutes} MINUTES']})
        if favorite:
            details.append({'label': 'TOP DISCIPLINE',
                            'value': f'{favorite[0]} / {favorite[1]:,}',
                            'lines': [favorite[0].upper(), f'{favorite[1]:,} WORKOUTS']})
        instructor_ranks = top_instructors(snapshot.get('instructor_counts', {}),
                                           snapshot.get('instructor_names', {}), limit=3)
        rank_labels = ('TOP INSTRUCTOR', '2ND INSTRUCTOR', '3RD INSTRUCTOR')
        for rank_label, (name, count) in zip(rank_labels, instructor_ranks):
            details.append({'label': rank_label, 'value': f'{name} / {count:,}',
                            'lines': [name.upper(), f'{count:,} CLASSES']})
        username_duration = _duration(display, 'username', display['duration'])
        if username_duration > 0 and details:
            from display.ui.username import DETAIL_INTERVAL_SECONDS
            username_duration = max(
                username_duration, len(details) * DETAIL_INTERVAL_SECONDS)
        groups['username'].append(('username', {'username': username, 'details': details},
                                   username_duration))

    # 64 rows fit a 2x2 grid of icon tiles per page; 32 rows fit one row of two.
    zone = display.get('timezone') or (snapshot.get('me') or {}).get('timezone')
    if 'streaks' in groups and streak_views(snapshot.get('streaks')):
        streaks = snapshot['streaks']
        streak_duration = _duration(display, 'streaks', display['overview_duration'])
        weekday = week_day(zone)
        reminder_day = display.get('streak_reminder_day', 5)
        if (reminder_day is not None and weekday >= reminder_day
                and snapshot.get('streak_week_workouts') == 0 and streaks.get('current_weekly', 0) > 0):
            # Late in the week with nothing that counts yet: one workout keeps the streak.
            groups['streaks'].append(('streak_risk', {
                'current': streaks['current_weekly'], 'days_left': 7 - weekday},
                streak_duration))
        else:
            state = dict(streaks)
            if streaks.get('current_daily', 0) > 0:
                today = week_start(zone)[1].date()
                state.update(today=today.isoformat(), daily_start=daily_streak_start(
                    streaks['current_daily'], today, snapshot.get('activity_days'),
                    streaks.get('start_date_of_current_daily'), zone).isoformat())
            # One streak per pass: weekly, then daily on the next pass.
            views = streak_views(state)
            state['view'] = views[pass_index % len(views)][0]
            groups['streaks'].append(('streak', state, streak_duration))

    if 'versus' in groups and rivals and len(rivals) >= 2:
        from display.ui.versus_screen import DETAIL_INTERVAL_SECONDS, STATS
        versus_duration = _duration(display, 'versus', display['overview_duration'])
        if versus_duration > 0 and matrix_height < 64:
            # 32 rows show one stat at a time; give each its full turn.
            versus_duration = max(versus_duration, len(STATS) * DETAIL_INTERVAL_SECONDS)
        groups['versus'].append(('versus', {'riders': rivals, 'weekday': week_day(zone)},
                                 versus_duration))

    overview_pages = lifetime_overview_pages(snapshot['totals'],
                                             page_size=4 if matrix_height >= 64 else 2)
    discipline_duration = _duration(display, 'lifetime', display['overview_duration'])
    if discipline_duration > 0:
        discipline_duration = max(discipline_duration, 5.0)
    total = total_workout_count(snapshot['totals'])
    if 'total_workouts' in groups and total is not None:
        groups['total_workouts'].append(('discipline', {
            'discipline': 'Total Workouts', 'count': total,
            'color_key': display['color'], 'number_font_key': 'big',
            'number_color_key': 'gold'}, discipline_duration))
    if 'next_milestone' in groups:
        # Usually empty: only the total or a discipline a few workouts from its next target.
        for upcoming in upcoming_milestones(
                total, display.get('milestones', []), display.get('milestone_step', 0), snapshot.get('totals'),
                within=display.get('milestone_within', UPCOMING_WITHIN),
                limit=display.get('milestone_pages', MAX_UPCOMING)):
            # 2,200TH WORKOUT on 64 rows; TO 2,200 / WORKOUTS on 32.
            title = upcoming['label'] if upcoming['discipline'] or matrix_height < 64 else 'Workout'
            groups['next_milestone'].append(('countdown', {
                'total': upcoming['count'], 'target': upcoming['target'],
                'previous': upcoming['previous'], 'title': title, 'discipline': upcoming['discipline']},
                _duration(display, 'next_milestone', display['overview_duration'])))
    if 'lifetime' in groups:
        for index, items in enumerate(overview_pages):
            groups['lifetime'].append(('lifetime', {
                'items': items, 'page': index + 1, 'pages': len(overview_pages)},
                discipline_duration))

    if 'journey' in groups:
        progress = journey_progress(snapshot.get('distance_totals'), display.get('journey'))
        # Skip until the distance tally has something (e.g. before the backfill).
        if progress and progress['miles'] > 0:
            groups['journey'].append(('journey', progress,
                                      _duration(display, 'journey', display['overview_duration'])))

    if 'heatmap' in groups and snapshot.get('activity_days'):
        from peloton.activity import HEATMAP_WEEKS
        today = week_start(zone)[1].date().isoformat()
        groups['heatmap'].append(('heatmap', {'days': snapshot['activity_days'], 'today': today,
                                              'weeks': HEATMAP_WEEKS},
                                  _duration(display, 'heatmap', display['overview_duration'])))

    goal_duration = _duration(display, 'goals', display['overview_duration'])
    if 'goals' in groups:
        progress = snapshot.get('weekly_progress', {})
        for key, target in display.get('weekly_goals', {}).items():
            if target > 0:
                groups['goals'].append(('goal', {
                    'title': 'Weekly Goal', 'current': progress.get(key, 0),
                    'target': target, 'unit': key}, goal_duration))
    # A celebration leads the rotation (after the logo), wherever 'milestones' sits in it. One per
    # rotation: the newest total-workouts milestone (acknowledging it retires any older ones), and any
    # discipline's taking turns with it pass by pass, so each shows during its day.
    celebrations = []
    if 'milestones' in groups:
        candidates = []
        if display.get('milestones') or display.get('milestone_step'):
            pending = dashboard.pending_milestones(snapshot)
            if pending:
                candidates.append({'number': pending[-1], 'noun': milestone_noun(None),
                                   'subtitle': username, 'milestone': pending[-1]})
        labels = {normalize_discipline(label): label for label in snapshot.get('totals', {})}
        for key in dashboard.pending_discipline_milestones(snapshot):
            discipline, target = parse_milestone_key(key)
            candidates.append({'number': target, 'noun': discipline_noun(discipline, labels.get(discipline)),
                               'subtitle': username, 'milestone': key})
        if candidates:
            celebration_duration = _duration(display, 'milestones', display['overview_duration'])
            if celebration_duration > 0:
                celebration_duration = max(celebration_duration, INTRO_SECONDS + MIN_CARD_SECONDS)
            celebrations.append(('celebration', candidates[pass_index % len(candidates)],
                                 celebration_duration))
    return celebrations + [page for section in rotation for page in groups[section]]


def _overlays(dashboard):
    """What's drawn over every screen: the login padlock and the settings page's PIN."""
    return (dashboard.login_indicator_required if dashboard else None, shown_pin())


# Seconds between ticks; an animated screen may ask for less with `frame_seconds`.
TICK_SECONDS = 0.2


def _tick_seconds(manager):
    wanted = getattr(getattr(manager, 'current', None), 'frame_seconds', None)
    if isinstance(wanted, (int, float)) and not isinstance(wanted, bool) and wanted > 0:
        return min(wanted, TICK_SECONDS)
    return TICK_SECONDS


def show_and_wait(manager, name, state, duration, dashboard=None):
    manager.show(name, state)
    manager.tick(state)
    deadline = time.monotonic() + duration
    previous = _overlays(dashboard)
    step = _tick_seconds(manager)
    while time.monotonic() < deadline:
        time.sleep(min(step, max(0, deadline - time.monotonic())))
        current = _overlays(dashboard)
        if current != previous:
            # Repaint when authentication or the settings PIN changes, even during a long screen.
            previous = current
            manager.matrix.Clear()
            manager.tick(state)
        elif getattr(getattr(manager, 'current', None), 'animated', False) is True:
            manager.tick(state)
    heartbeat.beat()  # for the updater's health check (self_update)


def run_display_loop(manager, dashboard, display, username_override=None, cycles=0, rivals=None,
                     first_pass=0):
    completed = 0
    while not cycles or completed < cycles:
        snapshot = dashboard.snapshot()
        username = resolve_display_username(username_override, snapshot['me'], display)
        matrix_height = getattr(getattr(manager, 'matrix', None), 'height', 64)
        if not isinstance(matrix_height, (int, float)):
            matrix_height = 64
        profile = snapshot.get('me') or {}
        apply_scheduled_brightness(manager.matrix, display,
                                   timezone_name=profile.get('timezone'))
        pages = build_rotation_pages(snapshot, dashboard, display, username, matrix_height,
                                     rivals=rivals, pass_index=first_pass + completed)
        for name, state, duration in pages:
            show_and_wait(manager, name, state, duration, dashboard)
            if name == 'pr':
                dashboard.acknowledge_pr(state.get('workout_id'))
            elif name == 'celebration' and state.get('milestone'):
                dashboard.acknowledge_milestone(state['milestone'])
        completed += 1
        if not any(page[2] for page in pages):
            time.sleep(0.05)  # Avoid a busy loop when all durations are zero.


def show_wifi_setup_while_needed(manager):
    """While comitup's Wi-Fi setup hotspot is up (no known Wi-Fi in range), show how to join it
    and where the settings page is, until the board is on a network. Returns whether it showed."""
    name = hotspot_name()
    if not name:
        return False
    logger.info('No known Wi-Fi: showing the setup screen for the %s hotspot.', name)
    page = 0
    while name:
        show_and_wait(manager, 'wifi_setup', {'name': name, 'page': page}, WIFI_SETUP_PAGE_SECONDS)
        page = 1 - page
        name = hotspot_name()
    logger.info('Wi-Fi setup hotspot down; carrying on.')
    return True


def run_multi_user_loop(manager, profiles, display, active, cycles=0):
    """Show one complete rotation per user, in configured order, with the logo between them
    (and between cycles). The first rotation goes without, since main() has just shown it."""
    completed = 0
    logo_duration = display.get('logo_duration', 0)
    while not cycles or completed < cycles:
        show_wifi_setup_while_needed(manager)
        rivals = weekly_rivals(profiles)
        for index, profile in enumerate(profiles):
            active['dashboard'] = profile['dashboard']
            if logo_duration > 0 and (completed or index):
                show_and_wait(manager, 'logo', None, logo_duration, profile['dashboard'])
            # The head-to-head page covers everyone, so show it once per cycle. Each rider's
            # rotation uses their own display settings (weekly goals, milestones, journey).
            run_display_loop(manager, profile['dashboard'], profile.get('display', display),
                             profile.get('username'), cycles=1,
                             rivals=rivals if index == 0 else None, first_pass=completed)
        completed += 1


def weekly_rivals(profiles):
    """Each rider's name and this week's progress, for the versus page."""
    rivals = []
    for profile in profiles:
        progress = profile['dashboard'].snapshot().get('weekly_progress') or {}
        rivals.append({'name': profile.get('name') or profile.get('username') or 'Rider',
                       'workouts': progress.get('workouts', 0), 'minutes': progress.get('minutes', 0),
                       'output_kj': progress.get('output_kj', 0)})
    return rivals


def configured_profiles(config, options):
    """Build dashboard/profile records with isolated token and cache paths."""
    display = config['display']
    users = config.get('users')
    if not users:
        return [{'name': 'default', 'username': options.username, 'display': display,
                 'dashboard': Dashboard(options.cookies, display, demo=options.demo,
                     demo_login_needed=options.demo_login_needed)}]
    config_dir = Path(options.config).with_suffix('.json').expanduser().resolve().parent
    profiles = []
    for user in users:
        token_path = user_token_path(user, config_dir)
        user_display = dict(display)
        if 'weekly_goals' in user:
            user_display['weekly_goals'] = user['weekly_goals']
        if 'milestones' in user:
            user_display['milestones'] = user['milestones']
        if 'journey' in user:
            user_display['journey'] = user['journey']
        if user.get('cache_path'):
            cache_path = Path(user['cache_path']).expanduser()
            if not cache_path.is_absolute():
                cache_path = config_dir / cache_path
            user_display['cache_path'] = str(cache_path)
        else:
            user_display['cache_path'] = str(token_path.with_name(
                f'{token_path.stem}-dashboard-cache.json'))
        if user.get('log_path'):
            log_path = Path(user['log_path']).expanduser()
            if not log_path.is_absolute():
                log_path = config_dir / log_path
            user_display['log_path'] = str(log_path)
        profiles.append({'name': user['name'], 'username': user.get('username'), 'display': user_display,
                         'dashboard': Dashboard(token_path, user_display,
                             demo=options.demo, demo_login_needed=options.demo_login_needed)})
    return profiles


def main():
    load_dotenv()
    options = args()
    try:
        config = load_config(options.config, allow_missing=options.demo)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    display = config['display']
    if options.display_duration is not None:
        display['duration'] = options.display_duration
    if options.refresh_interval is not None:
        display['refresh_interval'] = options.refresh_interval
    logger.setLevel(logging.DEBUG if config.get('debug') else logging.INFO)

    # Delay driver imports until configuration has been checked.
    from driver import RGBMatrix
    from display.display import initialize_fonts
    from display.ui.manager import ScreenManager
    from display.ui.username import UsernameScreen
    from display.ui.discipline_page import DisciplinePageScreen
    from display.ui.lifetime_overview import LifetimeOverviewScreen
    from display.ui.logo_screen import LogoScreen
    from display.ui.logo_mask_screen import LogoMaskScreen
    from display.ui.last_workout_screen import LastWorkoutScreen
    from display.ui.pr_celebration import PrCelebrationScreen
    from display.ui.celebration_screen import CelebrationScreen
    from display.ui.status_screen import StatusScreen
    from display.ui.goal_screen import GoalScreen
    from display.ui.streak_screen import StreakScreen
    from display.ui.versus_screen import VersusScreen
    from display.ui.countdown_screen import CountdownScreen
    from display.ui.journey_screen import JourneyScreen
    from display.ui.heatmap_screen import HeatmapScreen
    from display.ui.streak_risk_screen import StreakRiskScreen
    from display.ui.wifi_setup_screen import WifiSetupScreen

    matrix = RGBMatrix(options=led_matrix_options(options, config['matrix']))
    ensure_privileges_dropped()
    try:
        matrix.Clear()
    except Exception as exc:
        raise SystemExit(f'Could not initialize the matrix: {exc}') from exc
    initialize_fonts(matrix.height)
    profiles = configured_profiles(config, options)
    active = {'dashboard': profiles[0]['dashboard']}
    manager = ScreenManager(matrix,
        login_required=lambda: active['dashboard'].login_indicator_required,
        stale_data=lambda: active['dashboard'].stale_indicator_required)
    manager.register('username', UsernameScreen(font_key=display['font'], color_key=display['color']))
    manager.register('discipline', DisciplinePageScreen())
    manager.register('lifetime', LifetimeOverviewScreen())
    manager.register('last_workout', LastWorkoutScreen(
        detail_interval=display.get('last_workout_detail_interval', LAST_WORKOUT_DETAIL_INTERVAL_SECONDS)))
    manager.register('pr', PrCelebrationScreen())
    manager.register('celebration', CelebrationScreen())
    manager.register('status', StatusScreen())
    manager.register('goal', GoalScreen())
    manager.register('streak', StreakScreen())
    manager.register('versus', VersusScreen())
    manager.register('countdown', CountdownScreen())
    manager.register('journey', JourneyScreen())
    manager.register('heatmap', HeatmapScreen())
    manager.register('streak_risk', StreakRiskScreen())
    manager.register('wifi_setup', WifiSetupScreen())
    configured_logo = display.get('logo_path')
    logo = Path(configured_logo) if configured_logo else None
    for profile in profiles:
        profile['dashboard'].start()
    try:
        # The built-in pixel mask needs no image decoding; display.logo_path
        # still overrides it with an image file when one is configured.
        if logo is not None and logo.exists():
            manager.register('logo', LogoScreen(str(logo)))
        else:
            manager.register('logo', LogoMaskScreen())
        if display['logo_duration'] > 0:
            show_and_wait(manager, 'logo', None, display['logo_duration'], active['dashboard'])
        if options.cycles and not options.demo:
            # A finite real-data smoke run should wait for the initial request.
            deadline = time.monotonic() + 60
            for profile in profiles:
                active['dashboard'] = profile['dashboard']
                while (profile['dashboard'].snapshot()['status'] == 'loading'
                       and time.monotonic() < deadline):
                    show_and_wait(manager, 'status', 'loading', 0.2, profile['dashboard'])
        run_multi_user_loop(manager, profiles, display, active, options.cycles)
    except KeyboardInterrupt:
        logger.info('Stopping Peloton display')
    finally:
        for profile in profiles:
            if not profile['dashboard'].stop():
                logger.warning('Refresh worker for %s did not stop before its request timeout',
                               profile['name'])
        matrix.Clear()


if __name__ == '__main__':
    main()
