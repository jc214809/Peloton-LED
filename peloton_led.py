#!/usr/bin/env python3
"""Peloton LED dashboard: network-free screen rotation over background snapshots."""
import logging
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from peloton.booked_classes import SHOWN_AFTER_START, takeover_booking
from peloton.config import DEFAULTS, load_config, load_dotenv, user_cache_path, user_token_path
from peloton.dashboard import Dashboard
from peloton.totals import extract_discipline_totals, lifetime_overview_pages, total_workout_count  # noqa: F401  re-export kept for callers
from utils import heartbeat
from utils.utils import args, ensure_privileges_dropped, led_matrix_options
from utils.username import resolve_display_username
from utils.wifi_setup import hotspot_name
from display.rotation_pages import DEFAULT_ROTATION, build_rotation_pages
from display.ui.last_workout.rotation import LAST_WORKOUT_DETAIL_INTERVAL_SECONDS
from display.ui.settings_pin import shown_pin

logger = logging.getLogger('peloton-led')
ROOT = Path(__file__).resolve().parent
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


# How often a long page checks for a next-class takeover (a page cut short is fine), and the pages that finish
# first: a celebration is somebody's moment (Joel, 2026-11-15).
TAKEOVER_CHECK_SECONDS = 1.0
UNINTERRUPTED_PAGES = frozenset({'celebration', 'pr'})


def show_and_wait(manager, name, state, duration, dashboard=None, interrupt=None):
    """Show a page for `duration` seconds. `interrupt`, when given, is asked every TAKEOVER_CHECK_SECONDS and
    cuts the page short when it returns true; returns whether it did."""
    manager.show(name, state)
    manager.tick(state)
    deadline = time.monotonic() + duration
    next_check = time.monotonic() + TAKEOVER_CHECK_SECONDS
    previous = _overlays(dashboard)
    step = _tick_seconds(manager)
    cut = False
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
        if interrupt is not None and time.monotonic() >= next_check:
            next_check = time.monotonic() + TAKEOVER_CHECK_SECONDS
            if interrupt():
                cut = True
                break
    heartbeat.beat()  # for the updater's health check (self_update)
    return cut


class NextClassTakeover:
    """From `display.next_class_takeover_minutes` before a booked class starts until TAKEOVER_END_AFTER_START
    after, the next-class page holds the panel, whoever's rotation is showing.

    Reads each rider's bookings from their dashboard's snapshot (no network). A rider counts only with
    `next_class` in their rotation (bookings aren't fetched otherwise) and the setting above 0. The sooner start
    wins; a tie goes to the first configured rider."""

    def __init__(self, profiles, display, active=None):
        self.profiles, self.display, self.active = profiles, display, active

    def _display(self, profile):
        return profile.get('display', self.display)

    def due(self, now=None):
        """(rider's index, booking) taking over now, or None."""
        now = time.time() if now is None else now
        best = None
        for index, profile in enumerate(self.profiles):
            display = self._display(profile)
            minutes = display.get('next_class_takeover_minutes', DEFAULTS['next_class_takeover_minutes'])
            if 'next_class' not in display.get('rotation', DEFAULT_ROTATION):
                continue
            booking = takeover_booking(profile['dashboard'].booked_classes(), now, minutes)
            if booking is not None and (best is None or booking['start'] < best[1]['start']):
                best = (index, booking)
        return best

    def pending(self):
        return self.due() is not None

    def _state(self, index, booking, now):
        profile = self.profiles[index]
        zone = self._display(profile).get('timezone')
        if not zone:
            zone = (profile['dashboard'].snapshot().get('me') or {}).get('timezone')
        return {'booking': booking, 'now': now, 'timezone': zone}

    def _label(self, index):
        profile = self.profiles[index]
        return profile.get('name') or profile.get('username') or f'rider {index + 1}'

    def hold(self, manager):
        """Hold the next-class page while a takeover is due, re-rendered with the time now so the countdown is
        live. Shown once per takeover (the tag's pulse starts there and isn't reset again), checked every
        TAKEOVER_CHECK_SECONDS: a booking that's gone ends it, a sooner one replaces it. Returns whether it
        held. The padlock follows the rider whose class it is."""
        found = self.due()
        if found is None:
            return False
        restore = self.active['dashboard'] if self.active is not None else None
        shown = step = state = previous = next_check = None
        try:
            while found is not None:
                index, booking = found
                key = (index, booking['id'], booking['start'])
                if key != shown:
                    if shown is not None:
                        self._ended(shown)
                    shown = key
                    logger.info('Next-class takeover: %s, class at %s.', self._label(index), booking['start'])
                    if self.active is not None:
                        self.active['dashboard'] = self.profiles[index]['dashboard']
                    state = self._state(index, booking, time.time())
                    manager.show('next_class', state)
                    manager.tick(state)
                    step = _tick_seconds(manager)
                    previous = _overlays(self.profiles[index]['dashboard'])
                    next_check = time.monotonic() + TAKEOVER_CHECK_SECONDS
                time.sleep(step)
                state = {**state, 'booking': booking, 'now': time.time()}
                current = _overlays(self.profiles[index]['dashboard'])
                checking = time.monotonic() >= next_check
                if current != previous:
                    previous = current
                    manager.matrix.Clear()
                    manager.tick(state)
                elif checking or getattr(getattr(manager, 'current', None), 'animated', False) is True:
                    manager.tick(state)  # a still page redraws once a check; the pulse every frame
                if checking:
                    next_check = time.monotonic() + TAKEOVER_CHECK_SECONDS
                    heartbeat.beat()
                    found = self.due()
        finally:
            self._ended(shown)
            if restore is not None:
                self.active['dashboard'] = restore
        heartbeat.beat()
        return True

    def _ended(self, key):
        logger.info('Next-class takeover ended for %s (class at %s).', self._label(key[0]), key[2])


def _rotation_pages(manager, dashboard, display, username_override, rivals, pass_index):
    """This pass's pages, built from the dashboard's snapshot (no network)."""
    snapshot = dashboard.snapshot()
    username = resolve_display_username(username_override, snapshot['me'], display)
    matrix_height = getattr(getattr(manager, 'matrix', None), 'height', 64)
    if not isinstance(matrix_height, (int, float)):
        matrix_height = 64
    profile = snapshot.get('me') or {}
    apply_scheduled_brightness(manager.matrix, display,
                               timezone_name=profile.get('timezone'))
    return build_rotation_pages(snapshot, dashboard, display, username, matrix_height,
                                rivals=rivals, pass_index=pass_index)


def _acknowledge_page(dashboard, name, state):
    """Tell the dashboard a page that celebrates something has been shown."""
    if name == 'pr':
        dashboard.acknowledge_pr(state.get('workout_id'))
    elif name == 'username':
        dashboard.acknowledge_name_facts(state['fact_keys'])
    elif name == 'celebration' and state.get('milestone'):
        dashboard.acknowledge_milestone(state['milestone'])


def _play_page(manager, dashboard, takeover, page):
    """Show one rotation page; returns whether the rotation moves on (False: a takeover cut it short, so it
    plays again from its start once the takeover ends)."""
    name, state, duration = page
    if takeover is not None and takeover.hold(manager) and name == 'next_class':
        return True
    if name == 'next_class':
        now = time.time()
        if state['booking']['start'] + SHOWN_AFTER_START <= now:
            return True  # it has been going long enough since this rotation was built
        state = {**state, 'now': now}
    extra = {}
    if takeover is not None and name not in UNINTERRUPTED_PAGES:
        extra['interrupt'] = takeover.pending
    if show_and_wait(manager, name, state, duration, dashboard, **extra) is True:
        return False  # cut short by a takeover: held at the top, then this page again
    _acknowledge_page(dashboard, name, state)
    return True


def run_display_loop(manager, dashboard, display, username_override=None, cycles=0, rivals=None,  # noqa: PLR0913
                     first_pass=0, takeover=None):
    """Play `cycles` rotations (0 forever). `takeover`, a NextClassTakeover, is checked before every page and
    every TAKEOVER_CHECK_SECONDS during one (not a celebration or PR page, which finish first). A page it cut
    short plays again from its start once the takeover ends, except the next-class page, which the takeover
    just showed (its time is refreshed when it plays, so it never counts down from a stale `now`)."""
    completed = 0
    while not cycles or completed < cycles:
        pages = _rotation_pages(manager, dashboard, display, username_override, rivals, first_pass + completed)
        position = 0
        while position < len(pages):
            if _play_page(manager, dashboard, takeover, pages[position]):
                position += 1
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
    logo_duration = display.get('logo_duration', 0) if display.get('show_logo', True) else 0
    takeover = NextClassTakeover(profiles, display, active)
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
                             rivals=rivals if index == 0 else None, first_pass=completed,
                             takeover=takeover)
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
        user_display['cache_path'] = str(user_cache_path(user, config_dir, token_path))
        if user.get('log_path'):
            log_path = Path(user['log_path']).expanduser()
            if not log_path.is_absolute():
                log_path = config_dir / log_path
            user_display['log_path'] = str(log_path)
        profiles.append({'name': user['name'], 'username': user.get('username'), 'display': user_display,
                         'dashboard': Dashboard(token_path, user_display,
                             demo=options.demo, demo_login_needed=options.demo_login_needed)})
    return profiles


def _load_checked_config(options):
    """The config, checked (a bad one exits with its message), with the command-line overrides applied and
    the log level set."""
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
    return config


def _import_display():
    """The driver and screen classes, imported only once the configuration has been checked."""
    from driver import RGBMatrix
    from display.display import initialize_fonts
    from display.ui.manager import ScreenManager
    from display.ui.username import UsernameScreen
    from display.ui.discipline_page import DisciplinePageScreen
    from display.ui.lifetime_overview import LifetimeOverviewScreen
    from display.ui.logo_screen import LogoScreen
    from display.ui.logo_mask_screen import LogoMaskScreen
    from display.ui.last_workout.screen import LastWorkoutScreen
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
    from display.ui.challenge_screen import ChallengeScreen
    from display.ui.next_class_screen import NextClassScreen
    from display.ui.club_screen import ClubScreen
    return SimpleNamespace(
        RGBMatrix=RGBMatrix,
        initialize_fonts=initialize_fonts,
        ScreenManager=ScreenManager,
        UsernameScreen=UsernameScreen,
        DisciplinePageScreen=DisciplinePageScreen,
        LifetimeOverviewScreen=LifetimeOverviewScreen,
        LogoScreen=LogoScreen,
        LogoMaskScreen=LogoMaskScreen,
        LastWorkoutScreen=LastWorkoutScreen,
        PrCelebrationScreen=PrCelebrationScreen,
        CelebrationScreen=CelebrationScreen,
        StatusScreen=StatusScreen,
        GoalScreen=GoalScreen,
        StreakScreen=StreakScreen,
        VersusScreen=VersusScreen,
        CountdownScreen=CountdownScreen,
        JourneyScreen=JourneyScreen,
        HeatmapScreen=HeatmapScreen,
        StreakRiskScreen=StreakRiskScreen,
        WifiSetupScreen=WifiSetupScreen,
        ChallengeScreen=ChallengeScreen,
        NextClassScreen=NextClassScreen,
        ClubScreen=ClubScreen)


def _build_matrix(options, config, ui):
    """The matrix, then the drop from root (right after RGBMatrix(...), nothing in between), then a clear."""
    matrix = ui.RGBMatrix(options=led_matrix_options(options, config['matrix']))
    ensure_privileges_dropped()
    try:
        matrix.Clear()
    except Exception as exc:
        raise SystemExit(f'Could not initialize the matrix: {exc}') from exc
    return matrix


def _build_manager(matrix, display, active, ui):
    """The ScreenManager with every rotation screen registered (the logo is registered in main)."""
    manager = ui.ScreenManager(matrix,
        login_required=lambda: active['dashboard'].login_indicator_required,
        stale_data=lambda: active['dashboard'].stale_indicator_required)
    manager.register('username', ui.UsernameScreen(font_key=display['font'], color_key=display['color']))
    manager.register('discipline', ui.DisciplinePageScreen())
    manager.register('lifetime', ui.LifetimeOverviewScreen())
    manager.register('last_workout', ui.LastWorkoutScreen(
        detail_interval=display.get('last_workout_detail_interval', LAST_WORKOUT_DETAIL_INTERVAL_SECONDS)))
    manager.register('pr', ui.PrCelebrationScreen(
        detail_interval=display.get('last_workout_detail_interval', LAST_WORKOUT_DETAIL_INTERVAL_SECONDS)))
    manager.register('celebration', ui.CelebrationScreen())
    manager.register('status', ui.StatusScreen())
    manager.register('goal', ui.GoalScreen())
    manager.register('streak', ui.StreakScreen())
    manager.register('versus', ui.VersusScreen())
    manager.register('countdown', ui.CountdownScreen())
    manager.register('journey', ui.JourneyScreen())
    manager.register('heatmap', ui.HeatmapScreen())
    manager.register('streak_risk', ui.StreakRiskScreen())
    manager.register('wifi_setup', ui.WifiSetupScreen())
    manager.register('challenge', ui.ChallengeScreen())
    manager.register('next_class', ui.NextClassScreen())
    manager.register('club', ui.ClubScreen())
    return manager


def _wait_for_first_refresh(manager, profiles, active):
    """A finite real-data smoke run waits (up to 60 s) for each rider's initial request."""
    deadline = time.monotonic() + 60
    for profile in profiles:
        active['dashboard'] = profile['dashboard']
        while (profile['dashboard'].snapshot()['status'] == 'loading'
               and time.monotonic() < deadline):
            show_and_wait(manager, 'status', 'loading', 0.2, profile['dashboard'])


def main():
    load_dotenv()
    options = args()
    config = _load_checked_config(options)
    display = config['display']
    ui = _import_display()
    matrix = _build_matrix(options, config, ui)
    ui.initialize_fonts(matrix.height)
    profiles = configured_profiles(config, options)
    active = {'dashboard': profiles[0]['dashboard']}
    manager = _build_manager(matrix, display, active, ui)
    configured_logo = display.get('logo_path')
    logo = Path(configured_logo) if configured_logo else None
    for profile in profiles:
        profile['dashboard'].start()
    try:
        # The built-in pixel mask needs no image decoding; display.logo_path
        # still overrides it with an image file when one is configured.
        if logo is not None and logo.exists():
            manager.register('logo', ui.LogoScreen(str(logo)))
        else:
            manager.register('logo', ui.LogoMaskScreen())
        if display['show_logo']:
            show_and_wait(manager, 'logo', None, display['logo_duration'], active['dashboard'])
        if options.cycles and not options.demo:
            _wait_for_first_refresh(manager, profiles, active)
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
