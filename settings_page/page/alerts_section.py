"""The Pushover alerts card: whether the keys are set, a test alert, and the write-only keys."""
from html import escape

from settings_page.page.icons import icon
from settings_page.page.widgets import _notice, _pill, _post, _secret_input, _section

# What the Pushover alerts card says after its buttons: (kind, text).
ALERT_OUTCOMES = {
    'alerts_saved': ('good', '<strong>Alert keys saved</strong> to auth.env.'),
    'alerts_unchanged': ('info', 'Nothing to save: both key fields were blank, so the saved ones stay.'),
    'alerts_removed': ('good', '<strong>Pushover keys removed.</strong> No more alerts or PIN by phone until you '
                               'add them again.'),
    'test_sent': ('good', 'Test alert sent: check your phone.'),
    'test_wait': ('warn', 'A test alert went out less than a minute ago.'),
    'test_failed': ('bad', "Pushover didn't take the test alert: check the keys (the log says why)."),
    'test_off': ('warn', 'Set both Pushover keys below first.'),
}


def alerts_card(view, signed_in=True, outcome=None, problems=()):
    """Pushover alerts: whether the keys are set, a test alert, and the write-only keys (a PIN
    session, as for logins). view: Settings.logins() (its "pushover")."""
    if not view:
        return ''
    keys_set = bool(view.get('pushover'))
    top = ''
    if problems:
        items = ''.join(f'<li>{escape(p)}</li>' for p in problems)
        top += _notice('bad', f'<strong>Alert keys not saved.</strong><ul>{items}</ul>', 'alert')
    if outcome in ALERT_OUTCOMES:
        kind, html = ALERT_OUTCOMES[outcome]
        top += _notice(kind, html, 'alert' if kind == 'bad' else 'status')
    status = ('<dl class="facts"><dt>Alerts</dt><dd>'
              + (_pill('ok', 'On') if keys_set else _pill('', 'Off: no keys'))
              + '</dd><dt>Sent for</dt><dd><span class="hint">Token renewal problems, a rolled-back update, and '
                'the sign-in PIN when you ask for it</span></dd></dl>')
    remove = (_post('/credentials', 'Remove keys', 'x', 'Removing\u2026',
                    fields='<input type="hidden" name="card" value="alerts">'
                           '<input type="hidden" name="pushover_clear" value="on">',
                    confirm='Remove the Pushover keys? The board stops sending alerts, and the PIN can\'t go to '
                            'your phone, until you add them again.')
              if signed_in else '')  # removing takes the PIN, like changing them
    test = ('<div class="actions"><form method="post" action="/alert/test"><button type="submit" class="secondary">'
            f'{icon("phone")}Send a test alert</button></form>{remove}</div>' if keys_set else '')
    if signed_in:
        keys = ('<form method="post" action="/credentials" id="alert-keys"><input type="hidden" name="card" '
                'value="alerts"><h3>Keys</h3><p class="hint">From pushover.net: your user key, and an app\'s '
                'token. Saved to auth.env and never shown again: blank keeps what\'s saved.</p><div class="cred-grid">'
                + _secret_input('pushover_app_token', 'App token', 'password', keys_set)
                + _secret_input('pushover_user_key', 'User key', 'password', keys_set)
                + '</div>'
                + f'<div class="actions"><button type="submit" class="primary">{icon("lock")}Save alert keys'
                  '</button></div></form>')
    else:
        keys = _notice('info', 'Changing the keys takes the PIN, even in setup mode: '
                               '<a href="/signin">sign in with the PIN</a>.')
    return _section('alerts', 'Pushover alerts', 'Messages to your phone when the board needs you.',
                    top + status + test + keys, 'bell')
