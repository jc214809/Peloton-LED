"""The page's frame (document, top bar, Power menu, save notices) and the plain pages: sign-in and errors."""

from html import escape

from settings_page import logo
from settings_page.page.icons import icon
from settings_page.page.script import FORM_SCRIPT
from settings_page.page.style import STYLE
from settings_page.page.widgets import _attr, _notice, _post

# What a save says, by Settings.restart_app's outcome.
SAVED = ('restarted', 'not_running', 'saved', 'failed')
# What the top bar's Power menu says after an action (server.POWER_ACTIONS; failures are "failed-<action>"): (kind, text).
POWER_OUTCOMES = {
    'restart-display': ('good', '<strong>Display restarted.</strong>'),
    'stop-display': ('good', '<strong>Display stopped.</strong> It stays dark until you start it again.'),
    'start-display': ('good', '<strong>Display started.</strong>'),
    'failed-restart-display': ('bad', "<strong>Couldn't restart the display.</strong> The settings page's log says why."),
    'failed-stop-display': ('bad', "<strong>Couldn't stop the display.</strong> The settings page's log says why."),
    'failed-start-display': ('bad', "<strong>Couldn't start the display.</strong> The settings page's log says why."),
    'failed-reboot': ('bad', "<strong>Couldn't reboot the Pi.</strong> The settings page's log says why."),
    'failed-poweroff': ('bad', "<strong>Couldn't shut down the Pi.</strong> The settings page's log says why."),
    'unavailable': ('warn', 'The Power menu only works on a board (it uses systemd).'),
}
SENT = ('sent', 'wait', 'used', 'failed')  # pins.PinGate.send_pin's outcomes
TOUCH_ICON = '/apple-touch-icon.png'  # server.py serves logo.touch_icon_png() here, without a PIN


def document(title, body, script=''):
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta name="robots" content="noindex"><title>{escape(title)}</title>'
        f'<link rel="icon" type="image/svg+xml" href="{_attr(logo.favicon_href())}">'
        f'<link rel="apple-touch-icon" href="{TOUCH_ICON}"><style>{STYLE}</style></head>'
        f'<body>{body}{f"<script>{script}</script>" if script else ""}</body></html>'
    )


def power_menu(display_running=None):
    """The top bar's Power menu: a <details> dropdown (no JavaScript needed) of one-button POST forms to
    /power, each asking first (the same data-confirm the Updates card's buttons use). display_running:
    False offers Start display instead of Stop; None (no telling) offers Stop."""

    def item(action, label, glyph, busy, confirm, kind=''):
        return _post('/power', label, glyph, busy, kind, f'<input type="hidden" name="action" value="{action}">', confirm)

    stop = (
        item('start-display', 'Start display', 'refresh', 'Starting…', 'Start the display?')
        if display_running is False
        else item('stop-display', 'Stop display', 'stop', 'Stopping…', 'Stop the display? The board stays dark until you start it again.')
    )
    return (
        '<details class="power"><summary aria-label="Power menu">' + icon('power') + 'Power ' + icon('chevron') + '</summary>'
        '<div class="power-menu"><div class="power-head">Display</div>'
        + item(
            'restart-display', 'Restart display', 'refresh', 'Restarting…', 'Restart the display? The board goes dark for a few seconds.'
        )
        + stop
        + '<hr><div class="power-head">Raspberry Pi</div>'
        + item('reboot', 'Reboot the Pi', 'refresh', 'Rebooting…', 'Reboot the Pi? The board and this page come back in about a minute.')
        + item(
            'poweroff',
            'Shut down the Pi',
            'power',
            'Shutting down…',
            'Shut down the Pi? It stays off until you unplug it and plug it back in, and this page goes away too.',
            'danger',
        )
        + '</div></details>'
    )


def _topbar(board=None, mode=None, sign_out=False, power=False, display_running=None):
    """mode: ("warn" or "good", text) for the badge on the right. sign_out: a Sign out button after it.
    power: a Power menu before Sign out (display_running as power_menu's)."""
    chips = f'<span class="chip board">{icon("board")}{escape(board)}</span>' if board else ''
    if mode:
        kind, text = mode
        chips += f'<span class="chip status {kind}">{icon("wifi" if kind == "warn" else "lock")}{escape(text)}</span>'
    if power:
        chips += power_menu(display_running)
    if sign_out:
        chips += '<form method="post" action="/signout"><button type="submit" class="ghost">Sign out</button></form>'
    return (
        f'<header class="topbar"><div class="topbar-in"><div class="brand"><span class="mark">{logo.svg()}</span>'
        f'<div><div class="brand-name">Peloton LED</div><div class="brand-sub">Board settings</div>'
        f'</div></div><div class="top-meta">{chips}</div></div></header>'
    )


def message_page(title, text):
    """A plain page for errors (not found, not allowed)."""
    body = (
        f'{_topbar()}<div class="center"><div class="card auth"><div class="auth-icon">{icon("info")}</div>'
        f'<h1>{escape(title)}</h1><p>{escape(text)}</p><a class="btn secondary" href="/">Go to settings</a></div></div>'
    )
    return document(title, body)


def notices(problems=(), saved=None):
    """saved: None (nothing saved), or one of SAVED."""
    html = ''
    if problems:
        items = ''.join(f'<li>{escape(p)}</li>' for p in problems)
        html += _notice('bad', f'<strong>Not saved.</strong> Fix these and save again:<ul>{items}</ul>', 'alert')
    if saved == 'restarted':
        html += _notice('good', '<strong>Saved.</strong> The display is restarting with the new settings.')
    elif saved == 'not_running':
        html += _notice('good', "<strong>Saved.</strong> The display isn't running; it uses these settings the next time it starts.")
    elif saved == 'saved':
        html += _notice('good', '<strong>Saved.</strong> Restart the display for the new settings.')
    elif saved == 'failed':
        html += _notice(
            'bad',
            "<strong>Saved, but the display didn't restart.</strong> Run "
            '<code>sudo systemctl restart peloton-led</code> on the board, or unplug it and '
            'plug it back in.',
            'alert',
        )
    return html


def pin_page(shown_s=None, wrong=False, board=None, phone=False, sent=None, signed_out=False, display_running=True):
    """The sign-in page. shown_s: a PIN is on the board for this long. phone: offer to send it by
    Pushover; sent: how that went, one of SENT. signed_out: just signed out. display_running:
    False when the display isn't running, so a PIN can't show on the panel."""
    status = ''
    if signed_out:
        status = _notice('good', 'Signed out. This browser needs a new PIN to change settings.')
    elif wrong:
        status = _notice('bad', "That isn't the PIN on the board. Try again, or ask for a new one.", 'alert')
    elif sent == 'sent':
        status = _notice('good', "The PIN is on its way to your phone. It's on the board too.")
    elif sent == 'wait':
        status = _notice('warn', 'A PIN went out less than a minute ago: check your phone, or try again in a minute.')
    elif sent == 'used':
        status = _notice('bad', 'That PIN is out of tries. Ask for a new one in a couple of minutes.', 'alert')
    elif sent == 'failed':
        status = _notice('bad', "Couldn't send the PIN (the board's log says why).", 'alert')
    elif shown_s:
        status = _notice('good', f'The PIN is on the board for the next {max(1, round(shown_s / 60))} minute{"s" if shown_s > 90 else ""}.')
    if not display_running:
        status += _notice(
            'warn',
            "The display isn't running, so the PIN can't show on the panel. "
            + ('Send it to your phone instead, or start' if phone else 'Start')
            + ' it with <code>sudo systemctl start peloton-led</code>.',
        )
    body = (
        _topbar(board) + f'<div class="center"><div class="card auth"><div class="auth-icon">{icon("lock")}</div>'
        "<h1>Sign in to this board</h1><p>To change this board's settings, type in the PIN it shows.</p>"
        + status
        + '<div class="step"><span class="step-n">1</span><div class="step-body"><strong>Show a PIN</strong>'
        f'<p>It appears on the LED board for two minutes{" and can go to your phone" if phone else ""}.</p>'
        f'<div class="buttons"><form method="post" action="/pin/show"><button type="submit" class="secondary">'
        f'{icon("board")}Show a PIN on the board</button></form>'
        + (
            f'<form method="post" action="/pin/send"><button type="submit" class="secondary">{icon("phone")}'
            'Send the PIN to my phone</button></form>'
            if phone
            else ''
        )
        + '</div></div></div>'
        + '<div class="step"><span class="step-n">2</span><div class="step-body"><label for="pin"><strong>Type it in'
        '</strong></label><p>You stay signed in on this browser for an hour.</p>'
        '<form method="post" action="/pin"><input type="text" id="pin" name="pin" class="pin" inputmode="numeric" '
        'autocomplete="one-time-code" pattern="[0-9]*" maxlength="8" required autofocus aria-label="PIN">'
        '<button type="submit" class="primary block">Sign in</button></form></div></div>' + '</div></div>'
    )
    return document('Sign in · Board settings', body, FORM_SCRIPT)
