"""The settings page, assembled: the notices, the cards outside the form, the settings form, and the table of contents."""

import copy
from html import escape

from peloton.config import DEFAULTS, ROTATION_SECTIONS
from peloton.screen_times import retire_zero_times
from settings_page.form import FORM_FIELD, section
from settings_page.page.alerts_section import alerts_card
from settings_page.page.form_sections import general_card, goals_card, milestones_card, schedules_card, timing_card
from settings_page.page.hardware_sections import advanced_card, panel_card
from settings_page.page.icons import icon
from settings_page.page.insights_section import insights_card
from settings_page.page.logins_section import logins_card
from settings_page.page.rotation_section import rotation_card
from settings_page.page.script import SCRIPT
from settings_page.page.shell import POWER_OUTCOMES, _topbar, document, notices
from settings_page.page.updates_section import updates_card
from settings_page.page.widgets import _notice, _zone

SECTIONS = (  # id, nav title, icon
    ('updates', 'Updates', 'refresh'),
    ('logins', 'Logins', 'key'),
    ('alerts', 'Pushover alerts', 'bell'),
    ('general', 'General', 'type'),
    ('rotation', 'Rotation', 'list'),
    ('insights', 'Workout insights', 'bulb'),
    ('timing', 'Timing', 'clock'),
    ('goals', 'Goals', 'target'),
    ('milestone-settings', 'Milestones', 'trophy'),
    ('schedules', 'Schedules', 'sun'),
    ('panel', 'Panel', 'board'),
    ('advanced', 'Advanced', 'sliders'),
)


def _top_notices(problems, saved, hotspot, note, power_outcome):
    """Everything said above the cards: a Power menu outcome, a save's outcome, setup mode, a config problem."""
    power_notice = ''
    if power_outcome in POWER_OUTCOMES:
        kind, html = POWER_OUTCOMES[power_outcome]
        power_notice = _notice(kind, html, 'alert' if kind == 'bad' else 'status')
    return (
        power_notice
        + notices(problems, saved)
        + (
            _notice(
                'warn',
                f'<strong>Setup mode.</strong> Anyone who joins <strong>{escape(hotspot)}</strong> '
                'can open this page while the board is in Wi-Fi setup.',
            )
            if hotspot
            else ''
        )
        + (_notice('warn', escape(note)) if note else '')
    )


def _table_of_contents(updates, logins):
    return ''.join(
        f'<a href="#{sid}">{icon(glyph)}{escape(title)}</a>'
        for sid, title, glyph in SECTIONS
        if (sid != 'updates' or updates) and (sid not in ('logins', 'alerts') or logins)
    )


def settings_page(  # noqa: PLR0913
    config,
    hotspot=None,
    problems=(),
    saved=None,
    board=None,
    note=None,
    logins=None,
    signed_in=True,
    login_outcome=None,
    login_problems=(),
    updates=None,
    started=None,
    alert_outcome=None,
    alert_problems=(),
    editing_rider=None,
    history=None,
    power_outcome=None,
    display_running=None,
):
    """The settings form, filled from config. hotspot: the Wi-Fi setup hotspot's name when this
    browser is on it (no PIN needed). note: why config.json couldn't be read, if it couldn't.
    logins: Settings.logins() for the Logins card (None leaves it off); signed_in: a PIN session,
    which changing logins needs. updates: updates.Updates.view() for the Updates card (None leaves
    it off); started: how starting an update or rollback went, one of updates.STARTS. alert_outcome
    and alert_problems: the Pushover alerts card's (ALERT_OUTCOMES). editing_rider: the key of the
    rider whose login form login_problems came from (their card and form start open). history:
    settings_page.history.rider_histories() for the Workout insights card (None leaves the list off).
    power_outcome: how the Power menu's last action went, one of POWER_OUTCOMES. display_running: whether
    the display is running (False: the menu offers Start; None, unknown: Stop). The menu sits with Sign
    out: not on the setup hotspot, where nobody has a PIN session."""
    # An older config's 0 seconds meant "off": show it as the switch it meant, as the board reads it.
    display = copy.deepcopy(section(config, 'display'))
    retire_zero_times(display, ROTATION_SECTIONS, DEFAULTS['rotation'])
    matrix = section(config, 'matrix')
    merged = {**DEFAULTS, **display}  # what the app uses where config.json says nothing

    top = _top_notices(problems, saved, hotspot, note, power_outcome)
    toc = _table_of_contents(updates, logins)
    mode = ('warn', 'Setup mode') if hotspot else ('good', 'Signed in')
    body = (
        _topbar(board, mode, sign_out=not hotspot, power=not hotspot, display_running=display_running)
        # (on the hotspot there's no PIN session to end, and /power takes one)
        + f'<div class="shell"><nav class="toc" aria-label="Sections">{toc}</nav><main>'
        + '<div class="page-head"><h1>Settings</h1><p>Changes are checked, saved to the board\'s config.json, '
        "and the display restarts to use them. Logins go to the board's auth.env and are never shown.</p></div>"
        + top
        + f'<div class="stack" style="margin-bottom:20px">{updates_card(updates, started, _zone(display))}'
        f'{logins_card(logins, signed_in, login_outcome, login_problems, _zone(display), editing_rider)}'
        f'{alerts_card(logins, signed_in, alert_outcome, alert_problems)}</div>'
        + f'<form method="post" action="/save" id="settings"><input type="hidden" name="{FORM_FIELD}" value="1">'
        f'<div class="stack">{general_card(merged)}{rotation_card(display, merged, matrix)}'
        f'{insights_card(merged, history, _zone(display))}{timing_card(display, merged)}'
        f'{goals_card(config, display)}{milestones_card(config, display)}{schedules_card(display)}'
        f'{panel_card(matrix)}{advanced_card(config, display, matrix)}</div>'
        + '<div class="savebar"><div class="savebar-in"><div class="status" id="save-status"><span class="dot"></span>'
        '<span>Everything here is saved to config.json</span></div>'
        f'<button type="submit" class="primary" id="save">{icon("check")}<span>Save and restart</span></button>'
        '</div></div></form></main></div>'
    )
    return document('Board settings', body, SCRIPT)
