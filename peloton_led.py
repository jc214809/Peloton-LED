#!/usr/bin/env python3
"""Peloton LED dashboard: network-free screen rotation over background snapshots."""
import logging
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from peloton.config import load_config, default_token_path, load_dotenv
from peloton.dashboard import Dashboard
from peloton.instructors import top_instructors
from peloton.totals import extract_discipline_totals, lifetime_overview_pages, total_workout_count  # Kept available for callers.
from utils.utils import args, led_matrix_options
from utils.username import resolve_display_username
from display.ui.last_workout_screen import LAST_WORKOUT_DETAIL_INTERVAL_SECONDS, rotating_details
from display.ui.pr_celebration import BURST_SECONDS as PR_BURST_SECONDS, SETTLE_SECONDS as PR_SETTLE_SECONDS

logger = logging.getLogger('peloton-led')
ROOT = Path(__file__).resolve().parent
DEFAULT_ROTATION = ('latest_workouts', 'username', 'total_workouts', 'lifetime',
                    'milestones', 'goals')


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


def build_rotation_pages(snapshot, dashboard, display, username, matrix_height):
    """Build one rotation from configured named sections."""
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
                    stat_count = len(rotating_details(summary, matrix_height))
                    page_duration = detail_interval * (1 + stat_count)
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
                            'lines': [f'{total:,}']})
        weekly_workouts = progress.get('workouts', 0)
        weekly_minutes = progress.get('minutes', 0)
        details.append({'label': 'THIS WEEK',
                        'value': f'{weekly_workouts} WORKOUTS / {weekly_minutes} MIN',
                        'lines': [f'{weekly_workouts} WORKOUTS', f'{weekly_minutes} MINUTES']})
        if favorite:
            details.append({'label': 'TOP DISCIPLINE',
                            'value': f'{favorite[0]} / {favorite[1]:,}',
                            'lines': [favorite[0].upper(), f'{favorite[1]:,} WORKOUTS']})
        instructor_ranks = top_instructors(snapshot.get('instructor_counts', {}), limit=3)
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
    overview_pages = lifetime_overview_pages(snapshot['totals'],
                                             page_size=4 if matrix_height >= 64 else 2)
    discipline_duration = _duration(display, 'lifetime', display['overview_duration'])
    if discipline_duration > 0:
        discipline_duration = max(discipline_duration, 5.0)
    total = total_workout_count(snapshot['totals'])
    if 'total_workouts' in groups and total is not None:
        groups['total_workouts'].append(('discipline', {
            'discipline': 'Total Workouts', 'count': total,
            'color_key': display['color']}, discipline_duration))
    if 'lifetime' in groups:
        for index, items in enumerate(overview_pages):
            groups['lifetime'].append(('lifetime', {
                'items': items, 'page': index + 1, 'pages': len(overview_pages)},
                discipline_duration))

    goal_duration = _duration(display, 'goals', display['overview_duration'])
    if 'goals' in groups:
        progress = snapshot.get('weekly_progress', {})
        for key, target in display.get('weekly_goals', {}).items():
            if target > 0:
                groups['goals'].append(('goal', {
                    'title': 'Weekly Goal', 'current': progress.get(key, 0),
                    'target': target, 'unit': key}, goal_duration))
    if 'milestones' in groups and display.get('milestones'):
        for milestone in dashboard.pending_milestones(snapshot):
            groups['milestones'].append(('goal', {
                'title': 'Milestone', 'current': milestone, 'target': milestone,
                'unit': 'Total Workouts', 'milestone': True},
                _duration(display, 'milestones', display['overview_duration'])))
    return [page for section in rotation for page in groups[section]]


def show_and_wait(manager, name, state, duration, dashboard=None):
    manager.show(name, state)
    manager.tick(state)
    deadline = time.monotonic() + duration
    previous = dashboard.login_required if dashboard else None
    while time.monotonic() < deadline:
        time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        if dashboard and dashboard.login_required != previous:
            # Repaint when authentication changes, even during a long screen.
            previous = dashboard.login_required
            manager.matrix.Clear()
            manager.tick(state)
        elif getattr(getattr(manager, 'current', None), 'animated', False) is True:
            manager.tick(state)


def run_display_loop(manager, dashboard, display, username_override=None, cycles=0):
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
        pages = build_rotation_pages(snapshot, dashboard, display, username, matrix_height)
        for name, state, duration in pages:
            show_and_wait(manager, name, state, duration, dashboard)
            if name == 'pr':
                dashboard.acknowledge_pr(state.get('workout_id'))
            elif name == 'goal' and state.get('milestone'):
                dashboard.acknowledge_milestone(state['target'])
        completed += 1
        if not any(page[2] for page in pages):
            time.sleep(0.05)  # Avoid a busy loop when all durations are zero.


def run_multi_user_loop(manager, profiles, display, active, cycles=0):
    """Show one complete rotation per user, in configured order."""
    completed = 0
    while not cycles or completed < cycles:
        for profile in profiles:
            active['dashboard'] = profile['dashboard']
            run_display_loop(manager, profile['dashboard'], display,
                             profile.get('username'), cycles=1)
        completed += 1


def configured_profiles(config, options):
    """Build dashboard/profile records with isolated token and cache paths."""
    display = config['display']
    users = config.get('users')
    if not users:
        return [{'name': 'default', 'username': options.username,
                 'dashboard': Dashboard(options.cookies, display, demo=options.demo,
                     demo_login_needed=options.demo_login_needed)}]
    config_dir = Path(options.config).with_suffix('.json').expanduser().resolve().parent
    profiles = []
    for user in users:
        token_path = Path(user.get('token_path') or default_token_path(user['name'])).expanduser()
        if not token_path.is_absolute():
            token_path = config_dir / token_path
        user_display = dict(display)
        if 'weekly_goals' in user:
            user_display['weekly_goals'] = user['weekly_goals']
        if 'milestones' in user:
            user_display['milestones'] = user['milestones']
        if user.get('cache_path'):
            cache_path = Path(user['cache_path']).expanduser()
            if not cache_path.is_absolute():
                cache_path = config_dir / cache_path
            user_display['cache_path'] = str(cache_path)
        else:
            user_display['cache_path'] = str(token_path.with_name(
                f'{token_path.stem}-dashboard-cache.json'))
        profiles.append({'name': user['name'], 'username': user.get('username'),
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
    from display.ui.status_screen import StatusScreen
    from display.ui.goal_screen import GoalScreen

    matrix = RGBMatrix(options=led_matrix_options(options))
    try:
        matrix.Clear()
    except Exception as exc:
        raise SystemExit(f'Could not initialize the matrix: {exc}') from exc
    initialize_fonts(matrix.height)
    profiles = configured_profiles(config, options)
    active = {'dashboard': profiles[0]['dashboard']}
    manager = ScreenManager(matrix,
        login_required=lambda: active['dashboard'].login_required,
        stale_data=lambda: active['dashboard'].stale_indicator_required)
    manager.register('username', UsernameScreen(font_key=display['font'], color_key=display['color']))
    manager.register('discipline', DisciplinePageScreen())
    manager.register('lifetime', LifetimeOverviewScreen())
    manager.register('last_workout', LastWorkoutScreen(
        detail_interval=display.get('last_workout_detail_interval', LAST_WORKOUT_DETAIL_INTERVAL_SECONDS)))
    manager.register('pr', PrCelebrationScreen())
    manager.register('status', StatusScreen())
    manager.register('goal', GoalScreen())
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
