"""The settings form's plain cards: General, Timing, Goals, Milestones and Schedules."""

from html import escape
from zoneinfo import available_timezones

from peloton.config import DEFAULTS
from peloton.feeds.booked_classes import TAKEOVER_END_AFTER_START, TAKEOVER_MAX_MINUTES
from settings_page.form import COLORS, STREAK_REMINDER_DEFAULT, TIMING, TIMING_LEAST, WEEKDAYS, milestones_text, riders, section
from settings_page.page.widgets import _attr, _field, _hint, _input, _mini, _number, _options, _section, _switch, _unit

# The text colours, by config value: "disney_blue" and "down" (another red) are kept for old configs.
COLOUR_NAMES = {'white': 'White', 'gold': 'Gold', 'red': 'Red', 'disney_blue': 'Blue', 'down': 'Red (darker)'}


def _colour_choices(chosen):
    """The text colours to offer: white, gold, red and blue, plus a config's own if it's another."""
    shown = ('white', 'gold', 'red', 'disney_blue')
    return [(c, COLOUR_NAMES[c]) for c in COLORS if c in shown or c == chosen]


def general_card(merged):
    """merged: the config's display over DEFAULTS."""
    return _section(
        'general',
        'General',
        "How the board's pages look.",
        (
            _field(
                'color',
                'Text colour',
                _options('color', _colour_choices(merged['color']), merged['color']),
                'For your name and the per-discipline pages.',
            )
        ),
        'type',
    )


def _timing_field(display, merged, key, label, hint):
    least = TIMING_LEAST.get(key, 0)
    value = display.get(key)
    if least and isinstance(value, (int, float)) and not isinstance(value, bool):
        value = max(value, least)  # shown, and saved, as the board plays it
    field = _field(key, label, _number(key, value, DEFAULTS[key], unit='s', least=least), hint)
    if key == 'logo_duration':
        field = _switch('show_logo', 'Show the logo', merged['show_logo'], 'The Peloton LED logo at start-up and between riders.') + field
    return field


def timing_card(display, merged):
    """display: the config's display; merged: it over DEFAULTS."""
    return _section(
        'timing',
        'Timing',
        'How long pages last, and how often the board checks Peloton.',
        ''.join(_timing_field(display, merged, key, label, hint) for key, label, hint in TIMING)
        + _field(
            'next_class_takeover_minutes',
            'Class takeover',
            _number(
                'next_class_takeover_minutes',
                display.get('next_class_takeover_minutes'),
                DEFAULTS['next_class_takeover_minutes'],
                f' step="1" max="{TAKEOVER_MAX_MINUTES}" inputmode="numeric"',
                'min',
            ),
            'The Next booked class page takes over the whole panel this many minutes before a booked '
            "class starts (either rider's), until "
            f'{TAKEOVER_END_AFTER_START // 60} minutes after. 0 for never. Only with that screen on.',
        ),
        'clock',
    )


def goals_card(config, display):
    shared_goals = section(display, 'weekly_goals')
    reminder = display.get('streak_reminder_day', STREAK_REMINDER_DEFAULT)
    rider_list = riders(config)
    return _section(
        'goals',
        'Goals',
        'Weekly goals and the streak reminder.',
        (
            '<h3>Everyone</h3>'
            + _field(
                'goal_workouts',
                'Workouts a week',
                _number('goal_workouts', shared_goals.get('workouts'), 0, ' step="1" inputmode="numeric"', 'workouts'),
                '0 or blank for no workouts goal.',
            )
            + _field(
                'goal_minutes',
                'Minutes a week',
                _number('goal_minutes', shared_goals.get('minutes'), 0, ' step="1" inputmode="numeric"', 'min'),
                '0 or blank for no minutes goal.',
            )
            + _field(
                'goal_active_days',
                'Active days a week',
                _number('goal_active_days', shared_goals.get('active_days'), 0, ' step="1" max="7" inputmode="numeric"', 'days'),
                'Days with at least one workout, Monday to Sunday (two on one day count once). 0 or blank for no active-days goal.',
            )
            + _field(
                'streak_reminder_day',
                'Streak reminder from',
                _options(
                    'streak_reminder_day',
                    [('off', 'Never')] + [(str(i), d) for i, d in enumerate(WEEKDAYS)],
                    'off' if reminder is None else str(reminder),
                ),
                'From this day, a week with no workout yet shows "keep your streak" instead of the streak.',
            )
            + (
                (
                    '<h3>Each rider</h3><p class="hint">Blank uses Everyone\'s. Setting any weekly goal gives the '
                    'rider their own set (the others blank are no goal).</p>'
                    + ''.join(_rider(i, rider, display) for i, rider in rider_list)
                )
                if rider_list
                else ''
            )
        ),
        'target',
    )


def milestones_card(config, display):
    rider_list = riders(config)
    shared_list = milestones_text(display.get('milestones'))
    count = ' step="1" inputmode="numeric"'
    return _section(
        'milestone-settings',
        'Milestones',
        'The trophy when a total is reached, and the countdown to the next one.',
        (
            '<h3>Total workouts</h3>'
            + _field(
                'milestones',
                'Celebrate at',
                _input('milestones', shared_list, extra=' placeholder="100, 250, 500"'),
                'Lifetime workout counts, separated by commas. Blank for none.',
            )
            + _field(
                'milestone_step',
                'Then every',
                _number('milestone_step', display.get('milestone_step'), DEFAULTS['milestone_step'], count, 'workouts'),
                'Past the list, every this many workouts (100: 2,100, 2,200…). 0 for none.',
            )
            + '<h3>Each discipline</h3>'
            + _hint('25, 50, 100, then every 100 classes, picked automatically: 500th Strength, 600th Ride. Nothing to set.')
            + _hint(
                'A round number set by "Then every" or a discipline only gets the trophy if it was '
                "reached in the last 10 of those workouts, so old ones aren't celebrated."
            )
            + '<h3>Countdown</h3>'
            + _field(
                'milestone_within',
                'Show it from',
                _number('milestone_within', display.get('milestone_within'), DEFAULTS['milestone_within'], count, 'to go'),
                'The Next milestone page appears when the total or a discipline is this many workouts or fewer from its next one.',
            )
            + _field(
                'milestone_pages',
                'Up to',
                _number('milestone_pages', display.get('milestone_pages'), DEFAULTS['milestone_pages'], count, 'pages'),
                'When more are that close, the closest ones.',
            )
            + (
                (
                    '<h3>Each rider</h3><p class="hint">Their own total workouts to celebrate. Blank uses the '
                    'list above.</p>'
                    + ''.join(
                        _field(
                            f'rider_{i}_milestones',
                            rider['name'],
                            _input(
                                f'rider_{i}_milestones',
                                milestones_text(rider.get('milestones')),
                                extra=f' placeholder="{_attr(shared_list or "None")}"',
                            ),
                        )
                        for i, rider in rider_list
                    )
                )
                if rider_list
                else ''
            )
        ),
        'trophy',
    )


def schedules_card(display):
    bright = display.get('brightness_schedule') if isinstance(display.get('brightness_schedule'), dict) else None
    quiet = display.get('refresh_schedule') if isinstance(display.get('refresh_schedule'), dict) else None
    b, q = bright or {}, quiet or {}
    level = ' min="1" max="100" step="1" inputmode="numeric"'
    zones = ''.join(f'<option value="{_attr(z)}">' for z in sorted(available_timezones()))
    return _section(
        'schedules',
        'Schedules',
        'Dimming at night and checking Peloton less while you sleep.',
        (
            _field(
                'timezone',
                'Time zone',
                _input(
                    'timezone',
                    display.get('timezone') or '',
                    extra=' list="zones" autocomplete="off" placeholder="Your Peloton profile\'s"',
                )
                + f'<datalist id="zones">{zones}</datalist>',
                "For the schedules, the week's start and today's date. Like America/New_York.",
            )
            + _schedule_switch(
                'brightness_schedule',
                'Day and night brightness',
                bright,
                'Dim the panel at night.',
                '<div class="schedule">'
                + _mini('bright_day', 'Day brightness', _unit(_input('bright_day', b.get('day', 80), 'number', level), '%'))
                + _mini('day_start', 'Day starts', _input('day_start', b.get('day_start', '07:00'), 'time'))
                + _mini('bright_night', 'Night brightness', _unit(_input('bright_night', b.get('night', 15), 'number', level), '%'))
                + _mini('night_start', 'Night starts', _input('night_start', b.get('night_start', '22:00'), 'time'))
                + '</div>',
            )
            + _schedule_switch(
                'refresh_schedule',
                'Quiet hours',
                quiet,
                'Check Peloton less often overnight.',
                '<div class="schedule three">'
                + _mini('quiet_start', 'From', _input('quiet_start', q.get('quiet_start', '23:00'), 'time'))
                + _mini('quiet_end', 'Until', _input('quiet_end', q.get('quiet_end', '05:00'), 'time'))
                + _mini(
                    'quiet_interval',
                    'Check every',
                    _unit(_input('quiet_interval', q.get('quiet_interval', 3600), 'number', ' step="1" inputmode="numeric"'), 's'),
                )
                + '</div>',
            )
        ),
        'sun',
    )


def _rider(index, rider, display):
    goals = section(rider, 'weekly_goals')
    shared = section(display, 'weekly_goals')
    name = rider['name']
    fields = (
        _mini(
            f'rider_{index}_username',
            'Name on the board',
            _input(f'rider_{index}_username', rider.get('username') or '', extra=' placeholder="Their Peloton username"'),
        )
        + _mini(
            f'rider_{index}_workouts',
            'Workouts a week',
            _number(
                f'rider_{index}_workouts', goals.get('workouts'), shared.get('workouts', 0), ' step="1" inputmode="numeric"', 'workouts'
            ),
        )
        + _mini(
            f'rider_{index}_minutes',
            'Minutes a week',
            _number(f'rider_{index}_minutes', goals.get('minutes'), shared.get('minutes', 0), ' step="1" inputmode="numeric"', 'min'),
        )
        + _mini(
            f'rider_{index}_active_days',
            'Active days a week',
            _number(
                f'rider_{index}_active_days',
                goals.get('active_days'),
                shared.get('active_days', 0),
                ' step="1" max="7" inputmode="numeric"',
                'days',
            ),
        )
    )
    return (
        f'<div class="rider"><h3>{escape(name)}</h3>'
        f'<input type="hidden" name="rider_{index}_name" value="{_attr(name)}">'
        f'<div class="rider-grid">{fields}</div></div>'
    )


def _schedule_switch(sid, label, schedule, hint, fields):
    return (
        _switch(sid, label, schedule is not None, hint)
        + f'<div class="schedule-wrap" id="{sid}-fields">'
        + (
            ''
            if schedule
            else '<p class="hint schedule-note">Not set up yet: these are suggested starting values, saved only if you turn this on.</p>'
        )
        + fields
        + '</div>'
    )
