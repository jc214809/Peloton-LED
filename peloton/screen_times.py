"""How long each rotation screen shows: the board (peloton_led.build_rotation_pages) and the settings
page both use these, so the page's figures are the board's.

A time is never 0. Turning a screen off is taking it out of display.rotation (the settings page's Show
switch), and the logo has display.show_logo; retire_zero_times turns an older config's 0s into those.
No imports from the app, so the settings service can use it without the LED driver.
"""

# The least time for one Head to head stat on 32 rows, or one of the
# journey's two steps on 32 rows (the trip, then the miles by type). A page with
# more time shares it out, so each frame stays up longer instead of the page starting over.
FRAME_SECONDS = 4.0
HIGHLIGHT_SECONDS = 5.0  # the least one name-page highlight shows (a second more than the other frames)
VERSUS_STATS = 3  # display.ui.versus_screen.STATS; a test keeps them equal
LIFETIME_MIN_SECONDS = 5.0
# The trophy rises, then the number: celebration_screen.INTRO_SECONDS + MIN_CARD_SECONDS (tested).
CELEBRATION_MIN_SECONDS = 5.8
ONE_PAGE_MIN_SECONDS = 1.0

# Each screen's time when screen_durations doesn't give one: this display setting.
FALLBACKS = {'latest_workouts': 'last_workout_duration', 'username': 'duration'}
DEFAULT_FALLBACK = 'overview_duration'
# Screens timed by another one's setting.
SHARED = {'total_workouts': 'lifetime'}
# The fallbacks' own defaults (peloton.config.DEFAULTS; a test keeps them equal).
FALLBACK_DEFAULTS = {'duration': 4, 'overview_duration': 4, 'last_workout_duration': 30}


def fallback_key(section):
    return FALLBACKS.get(SHARED.get(section, section), DEFAULT_FALLBACK)


def configured_seconds(display, section):
    """The time display gives a screen: its screen_durations entry (Total workouts uses Lifetime's),
    else the display setting it falls back on."""
    own = SHARED.get(section, section)
    durations = display.get('screen_durations')
    value = durations.get(own) if isinstance(durations, dict) else None
    if value is None:
        key = fallback_key(section)
        value = display.get(key, FALLBACK_DEFAULTS[key])
    return value


def least_seconds(section, matrix_height, frames=1):
    """The least time a screen's page can have and still show all of itself. frames: the name page's
    highlights, or the journey's steps (the settings page asks with one)."""
    if section == 'username':
        return HIGHLIGHT_SECONDS * max(1, frames)
    if section == 'journey' and frames > 1:
        return FRAME_SECONDS * frames
    if section == 'versus' and matrix_height < 64:
        return FRAME_SECONDS * VERSUS_STATS
    if section in ('lifetime', 'total_workouts'):
        return LIFETIME_MIN_SECONDS
    if section == 'milestones':
        return CELEBRATION_MIN_SECONDS
    return ONE_PAGE_MIN_SECONDS


def page_seconds(display, section, matrix_height, frames=1):
    """How long one page of a screen shows: its configured time, raised to what it needs."""
    return max(configured_seconds(display, section), least_seconds(section, matrix_height, frames))


def _is_zero(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and value == 0


def retire_zero_times(display, sections, default_rotation):
    """Older configs used 0 seconds for "don't show". Turn each 0 into the switch it meant, in place:
    a screen whose time was 0 leaves display.rotation, logo_duration 0 becomes show_logo false, and
    the 0s go (so the defaults apply if the screen is switched back on). The board shows what it did
    before. Returns what changed, for a log line; [] when nothing did."""
    if not isinstance(display, dict):
        return []
    changed = []
    if _is_zero(display.get('logo_duration')):
        display.pop('logo_duration')
        display['show_logo'] = False
        changed.append('logo_duration 0 is now show_logo false')
    durations = display.get('screen_durations')
    durations = durations if isinstance(durations, dict) else {}
    off = set()
    for section in sections:
        own = SHARED.get(section, section)
        value = durations.get(own)
        if value is None:
            value = display.get(fallback_key(section))
        if _is_zero(value):
            off.add(section)
    if _is_zero(display.get('last_workout_detail_interval')):
        off.add('latest_workouts')  # 0 s a stat gave the workout pages no time at all
        display.pop('last_workout_detail_interval')
        changed.append('last_workout_detail_interval 0 removed')
    for key in [k for k, v in durations.items() if _is_zero(v)]:
        del durations[key]
        changed.append(f'screen_durations.{key} 0 removed')
    for key in sorted(set(FALLBACKS.values()) | {DEFAULT_FALLBACK}):
        if _is_zero(display.get(key)):
            display.pop(key)
            changed.append(f'{key} 0 removed')
    rotation = display.get('rotation')
    rotation = rotation if isinstance(rotation, list) else list(default_rotation)
    hidden = [name for name in rotation if name in off]
    if hidden:
        display['rotation'] = [name for name in rotation if name not in off]
        changed.append('switched off: ' + ', '.join(hidden))
    return changed
