"""config.json to the settings page's form and back. No HTTP or HTML here (server.py and
page.py): apply_form takes the posted fields and returns the config to save, or what's wrong.

Only the keys the page shows change; anything else in config.json (riders' names, token and
cache paths, login variable names, the journey, keys a newer version adds) is kept as it is.
Every check is the app's own (peloton.config.validate_config), so a saved config starts the app.
"""
import copy
import re

from peloton.config import DEFAULTS, MATRIX_DEFAULTS, validate_config

# Marks a post as this page's whole form: switches post nothing when off, so a partial post
# would otherwise turn them all off.
FORM_FIELD = 'settings_form'

# Every rotation screen, in the app's default order: (name, label, hint).
SCREENS = (
    ('latest_workouts', 'Latest workouts',
     'Each recent workout, then a PR celebration when there is one. On a 64x64 board each page '
     'lasts long enough to show every stat once; 0 hides them.'),
    ('username', 'Name and highlights', 'Your name, then all-time totals, this week and top instructors.'),
    ('streaks', 'Streaks', 'Weekly and daily streaks, one per pass.'),
    ('versus', 'Head to head', 'This week, rider against rider. Needs two or more riders.'),
    ('total_workouts', 'Total workouts', 'Every workout, all time. Shown as long as each Lifetime page.'),
    ('next_milestone', 'Next milestone', 'The count up to the next milestone.'),
    ('lifetime', 'Lifetime by discipline', 'All-time totals per discipline (at least 5 seconds a page).'),
    ('journey', 'Journey', 'Miles along the journey route.'),
    ('heatmap', 'Activity heatmap', 'Minutes a day over the last 12 weeks.'),
    ('milestones', 'Milestone celebrations', 'Once, when a milestone is reached.'),
    ('goals', 'Weekly goals', "Progress toward this week's goals."),
)
SCREEN_NAMES = tuple(name for name, _, _ in SCREENS)
# Screens timed by another one's setting rather than their own.
SHARED_DURATION = {'total_workouts': 'lifetime'}

# Seconds settings in display: (key, label, hint). Blank is the app's default.
TIMING = (
    ('overview_duration', 'Each page', 'For any screen without its own time in Rotation.'),
    ('last_workout_detail_interval', 'Each workout stat', 'How long each stat shows on a workout page.'),
    ('logo_duration', 'Logo', 'At start-up and between riders (once per cycle with one rider). 0 skips it.'),
    ('refresh_interval', 'Check Peloton every',
     'How often to look for new workouts. 300 (5 minutes) is plenty; much less only adds load.'),
)

COLORS = ('white', 'gold', 'red', 'disney_blue', 'down')
WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
STREAK_REMINDER_DEFAULT = 5  # peloton.config.DEFAULTS: Saturday

PANEL_SIZES = ('64x64', '64x32')
# The Panel card's matrix settings, (key, label, hint); the rest are under Advanced. Rows and
# columns are the Panel size dropdown's.
PANEL_FIELDS = (
    ('brightness', 'Brightness', '1 to 100. A day and night schedule, when on, takes over from it.'),
    ('gpio_mapping', 'GPIO mapping',
     'How the panel is wired to the Pi. adafruit-hat-pwm needs the Pi\'s onboard audio off: after '
     'choosing it, run the installer again, which offers to turn it off.'),
    ('pixel_mapper', 'Rotation', 'Which way up the panel is mounted.'),
    ('slowdown_gpio', 'GPIO slowdown', '0 to 4: higher for a faster Pi whose panel flickers.'),
    ('pwm_lsb_nanoseconds', 'PWM timing', 'Lower is a faster refresh; raise it if colours look wrong.'),
)
SIZE_KEYS = ('rows', 'cols')
SWITCH_KEYS = ('show_refresh', 'no_hardware_pulse')
# Posted beside the Compact workout pages switch, which the page shows only on a 64x32 panel: without
# it the switch wasn't on the page, so the saved value stays (an unticked switch posts nothing).
COMPACT_SHOWN = 'compact_workout_pages_shown'
# Rotation's choices: --led-pixel-mapper values. A saved one not here is offered as it is.
ROTATIONS = (('Rotate:180', 'Upside down (Rotate:180)'), ('Rotate:90', 'A quarter turn (Rotate:90)'),
             ('Rotate:270', 'Three quarters (Rotate:270)'), ('Mirror:H', 'Mirrored left to right (Mirror:H)'),
             ('Mirror:V', 'Mirrored top to bottom (Mirror:V)'))


def advanced_keys():
    """The matrix settings under Advanced: every one not in Panel."""
    shown = {key for key, _, _ in PANEL_FIELDS} | set(SIZE_KEYS)
    return [key for key in MATRIX_DEFAULTS if key not in shown]


def section(config, key):
    """config[key] when it's an object, else {} (a broken config still shows a page)."""
    value = config.get(key)
    return value if isinstance(value, dict) else {}


def riders(config):
    """config.json's riders that have a name: [(index, rider)]."""
    users = config.get('users')
    return [(i, u) for i, u in enumerate(users if isinstance(users, list) else [])
            if isinstance(u, dict) and isinstance(u.get('name'), str)]


def rotation_rows(display):
    """[(name, on)] for the Rotation card: the rotation's screens in its order, then the others."""
    rotation = display.get('rotation')
    rotation = rotation if isinstance(rotation, list) else list(DEFAULTS['rotation'])
    chosen = [name for name in rotation if name in SCREEN_NAMES]
    return [(name, True) for name in dict.fromkeys(chosen)] + [(n, False) for n in SCREEN_NAMES if n not in chosen]


def duration_fallback(display, name):
    """What a screen's blank time is: the display setting the app falls back to."""
    key = {'latest_workouts': 'last_workout_duration', 'username': 'duration'}.get(name, 'overview_duration')
    return display.get(key, DEFAULTS[key])


def panel_size(matrix):
    """config.json's matrix size as "64x32"; the app's 64x64 where unset."""
    return f"{matrix.get('cols') or MATRIX_DEFAULTS['cols']}x{matrix.get('rows') or MATRIX_DEFAULTS['rows']}"


def number_text(value):
    """A saved number as a field shows it: "" for none, 4 not 4.0."""
    if value is None or isinstance(value, bool):
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def milestones_text(values):
    return ', '.join(str(v) for v in values) if isinstance(values, list) else ''


def _number(text):
    """A typed number as int or float; anything else stays text, for validate_config to name."""
    if re.fullmatch(r'-?\d+', text):
        return int(text)
    if re.fullmatch(r'-?(\d+\.\d*|\.\d+)', text):
        return float(text)
    return text


def _milestones(text):
    """ "100, 250 500" as [100, 250, 500], sorted and once each when they're all whole numbers."""
    values = [_number(part) for part in re.split(r'[\s,]+', text) if part]
    if all(isinstance(v, int) for v in values):
        return sorted(set(values))
    return values


def apply_form(config, form):
    """(the config to save, [problems]) from the posted form: {field: [values]}, as
    urllib.parse.parse_qs(..., keep_blank_values=True) gives it. With any problem, nothing
    should be saved."""
    if FORM_FIELD not in form:
        return config, ["That wasn't the settings form: reload the page and try again."]
    new = copy.deepcopy(config)
    problems = []

    def one(name, default=''):
        return (form.get(name) or [default])[0].strip()

    def checked(name):
        return one(name) == 'on'

    def part(owner, key):
        if not isinstance(owner.get(key), dict):
            owner[key] = {}
        return owner[key]

    def set_or_drop(owner, key, field, parse=_number):
        text = one(field)
        if text:
            owner[key] = parse(text)
        else:
            owner.pop(key, None)

    new['debug'] = checked('debug')
    display = part(new, 'display')

    # Display
    set_or_drop(display, 'username', 'username', str)
    display['font'] = one('font', display.get('font', DEFAULTS['font']))
    display['color'] = one('color', display.get('color', DEFAULTS['color']))
    if one(COMPACT_SHOWN):
        display['compact_workout_pages'] = checked('compact_workout_pages')
    reminder = one('streak_reminder_day', str(STREAK_REMINDER_DEFAULT))
    display['streak_reminder_day'] = None if reminder == 'off' else _number(reminder)

    # Rotation: the screens in page order, the ones switched on; each one's own time, blank for
    # the fallback.
    order = [name for name in form.get('rotation_order', []) if name in SCREEN_NAMES]
    display['rotation'] = [name for name in dict.fromkeys(order) if checked(f'rotation_on_{name}')]
    durations = display.get('screen_durations')
    durations = dict(durations) if isinstance(durations, dict) else {}
    for name in SCREEN_NAMES:
        if name in SHARED_DURATION or f'duration_{name}' not in form:
            continue
        set_or_drop(durations, name, f'duration_{name}')
    display['screen_durations'] = durations
    for key, _, _ in TIMING:
        set_or_drop(display, key, key)

    # Schedules
    set_or_drop(display, 'timezone', 'timezone', str)
    if checked('brightness_schedule'):
        display['brightness_schedule'] = {
            'day': _number(one('bright_day')), 'night': _number(one('bright_night')),
            'day_start': one('day_start'), 'night_start': one('night_start')}
    else:
        display['brightness_schedule'] = None
    if checked('refresh_schedule'):
        old = display.get('refresh_schedule') if isinstance(display.get('refresh_schedule'), dict) else {}
        display['refresh_schedule'] = {
            **{k: v for k, v in old.items() if k == 'timezone'},  # its own zone, set by hand, stays
            'quiet_start': one('quiet_start'), 'quiet_end': one('quiet_end'),
            'quiet_interval': _number(one('quiet_interval'))}
    else:
        display['refresh_schedule'] = None

    # Goals: everyone's, then each rider's own (blank for everyone's)
    display['weekly_goals'] = {key: _number(one(f'goal_{key}') or '0') for key in ('workouts', 'minutes')}
    display['milestones'] = _milestones(one('milestones'))
    set_or_drop(display, 'milestone_step', 'milestone_step')
    for index, user in riders(new):
        if f'rider_{index}_name' not in form:
            continue
        if one(f'rider_{index}_name') != user['name']:
            problems.append('The riders in config.json changed since this page loaded: reload it and try again.')
            break
        set_or_drop(user, 'username', f'rider_{index}_username', str)
        goals = {key: one(f'rider_{index}_{key}') for key in ('workouts', 'minutes')}
        if any(goals.values()):
            user['weekly_goals'] = {key: _number(text or '0') for key, text in goals.items()}
        else:
            user.pop('weekly_goals', None)
        set_or_drop(user, 'milestones', f'rider_{index}_milestones', _milestones)

    # Panel: size and the matrix settings. Blank is the app's default.
    matrix = part(new, 'matrix')
    if 'panel_size' in form:
        found = re.fullmatch(r'(\d+)x(\d+)', one('panel_size'))
        if found:
            matrix['cols'], matrix['rows'] = int(found.group(1)), int(found.group(2))
        else:
            problems.append(f"Panel size should be like 64x32, not {one('panel_size')!r}.")
    for key in [k for k, _, _ in PANEL_FIELDS] + advanced_keys():
        field = f'matrix_{key}'
        if field not in form:
            continue
        text = one(field)
        if text == '':
            matrix.pop(key, None)
        elif key in SWITCH_KEYS:
            matrix[key] = text == 'true'
        elif key in ('gpio_mapping', 'pixel_mapper', 'rgb_sequence'):
            matrix[key] = text
        else:
            matrix[key] = _number(text)

    if not problems:
        try:
            validate_config(copy.deepcopy(new), 'config.json')
        except ValueError as exc:
            problems.append(str(exc).removeprefix('config.json: '))
    return new, problems
