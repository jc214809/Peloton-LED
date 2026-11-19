"""The Logins card: renewal's status and a card per rider (token health, renewal times, their own login form)."""
from html import escape

from settings_page.logins import RENEW_BEFORE_S, renews_at, when
from settings_page.page.icons import icon
from settings_page.page.widgets import _at, _attr, _notice, _pill, _secret_input, _section

# What the Logins card says after its buttons, by Settings' outcome: (kind, text).
LOGIN_OUTCOMES = {
    'logins_saved': ('good', '<strong>Logins saved</strong> to auth.env. Renewal uses them from its next run; '
                             '<em>Renew now</em> tries straight away.'),
    'logins_unchanged': ('info', 'Nothing to save: every login field was blank, so the saved ones stay.'),
    'renew_started': ('good', '<strong>Renewal started.</strong> It takes a few seconds, or a few minutes with '
                              'a browser login: reload the page to see how it went.'),
    'renew_running': ('warn', 'Renewal is already running: reload the page in a minute.'),
    'renew_failed': ('bad', "Renewal couldn't be started; the settings page's log says why."),
    'renew_unavailable': ('warn', 'Renewal can only be started on a board (it runs under systemd).'),
}


MODE_TEXT = {
    'browser': 'Automatic. Each rider\'s refresh token keeps them signed in. If Peloton rejects one, the board '
               'signs in with their saved email and password, trying at most once a day.',
    'no-browser': 'Automatic, with refresh tokens only. This board has no browser, so if a rider\'s login stops '
                  'working, re-seed it from your computer. Saved passwords aren\'t used.',
    'none': 'Off. Automatic renewal wasn\'t installed on this board (--no-auto-token). Renew now still works.',
}


def _rider_pill(login):
    """A rider's state in one pill: Working, or what needs a person."""
    if not login.token.get('ok'):
        return _pill('bad', 'No working token')
    if login.token.get('expired'):
        return _pill('bad', 'Expired')
    if login.padlock:
        return _pill('warn', 'Needs login')
    return _pill('ok', 'Working')


def _credentials_row(login, view, signed_in, problems=(), editing=False):
    """The Email & password row: whether they're saved and, with a PIN session, "Change", which opens
    this rider's write-only form in place (its own Save: other riders' logins aren't touched)."""
    saved = ('Set' if login.email_set and login.password_set
             else f'Email {"set" if login.email_set else "not set"}, password {"set" if login.password_set else "not set"}')
    if not signed_in:
        return f'<span class="k">Email &amp; password</span><span>{escape(saved)}</span>'
    top = ''
    if problems:
        items = ''.join(f'<li>{escape(p)}</li>' for p in problems)
        top = _notice('bad', f'<strong>Not saved.</strong><ul>{items}</ul>', 'alert')
    unused = ('<p class="hint">This board has no browser, so it never signs in with these: to fix a login here, '
              're-seed it from your computer.</p>' if view.get('mode') == 'no-browser' else '')
    return (f'<details class="cred" id="cred-{login.key}"{" open" if editing or problems else ""}>'
            f'<summary><span class="k">Email &amp; password</span><span>{escape(saved)} '
            f'<span class="change">&middot; {icon("edit")}Change</span></span></summary>'
            f'<form method="post" action="/credentials" class="cred-edit">'
            f'<input type="hidden" name="cred_{login.key}_name" value="{_attr(login.name)}">'
            + top + unused
            + '<p class="hint">Blank keeps what\'s saved; saved values are never shown. This page isn\'t encrypted, '
              'so only change logins on your own network.</p><div class="cred-grid">'
            + _secret_input(f'cred_{login.key}_email', 'Peloton email', 'email', login.email_set)
            + _secret_input(f'cred_{login.key}_password', 'Peloton password', 'password', login.password_set,
                            'new-password')
            + f'</div><div class="actions"><button type="submit" class="primary">{icon("lock")}Save</button>'
              '<button type="button" class="secondary js-only" hidden data-cancel>Cancel</button></div></form></details>')


def _login_status(login, view, zone, signed_in=True, problems=(), editing=False):
    """One rider's card: a header line (name, when it renews, a state pill) that opens to labelled
    rows. Closed while it works; open by itself when the rider needs a person (or their login form
    has problems)."""
    renews = _renews(login, view)
    rows = []
    token = login.token
    if not token.get('ok'):
        reason = token.get('reason') or 'unreadable'
        # refresh_cookies.py's reasons are written for its command line: say what they mean here.
        rows.append(('Token', 'No token on this board yet' if reason == 'file does not exist'
                     else f"The token file can't be used ({reason})"))
    elif token.get('expired'):
        rows.append(('Token', f'Expired {when(token["expires_at"], zone)}'))
    else:
        rows.append(('Token', f'Valid until {when(token["expires_at"], zone)}'))
    if renews is not None:
        rows.append(('Renews', f'{_renewal_time(renews, view, zone)[:1].upper()}{_renewal_time(renews, view, zone)[1:]}'
                               f' \u00b7 {RENEW_BEFORE_S // 3600} hours before it expires'))
    rows.append(('Refresh chain', login.chain[:1].upper() + login.chain[1:] if login.chain
                 else 'None: renewal needs a login'))
    if login.padlock:
        rows.append(('Renewal says', login.padlock['reason']))
    if login.browser_attempt:
        rows.append(('Last browser try', when(login.browser_attempt, zone)))
    facts = ''.join(f'<span class="k">{escape(k)}</span><span>{escape(v)}</span>' for k, v in rows)
    facts += _credentials_row(login, view, signed_in, problems, editing)
    needs_seed = not login.healthy and view.get('mode') != 'browser'
    seed = (f'<p class="hint">To log in again, run this from the Peloton-LED checkout on your computer: '
            f'<code>{escape(view["seed"])}</code></p>' if needs_seed else '')
    what = f'Renews {_renewal_time(renews, view, zone)}' if renews is not None and login.healthy else ''
    opened = not login.healthy or problems or editing
    return (f'<details class="rider-card"{" open" if opened else ""}><summary><strong>{escape(login.name)}</strong>'
            f'<span class="what">{escape(what)}</span>{_rider_pill(login)}<span class="chev">{icon("chevron")}</span>'
            f'</summary><div class="rider-body"><div class="rider-facts">{facts}</div>{seed}</div></details>')


def _renewal_pill(view):
    if view.get('renewing'):
        return _pill('now', 'Running now')
    result = view.get('last_result')
    if not view.get('last_run'):
        return _pill('', 'No run since the board started')
    if result == 'success':
        return _pill('ok', 'Last run worked')
    return _pill('bad', f'Last run failed ({result})' if result else 'Last run failed')


def _last_run_row(view, zone):
    if not view.get('last_run'):
        return None
    worked = 'worked' if view.get('last_result') == 'success' else 'failed'
    return 'Last run', escape(_at(view['last_run'], zone)) + ('' if view.get('renewing') else f' &middot; {worked}')


def _interval_row(view):
    if view.get('mode') == 'none':
        return None
    return ('Interval', 'Every hour' + (' while the display is on' if view.get('display_running') is False
                                        and not view.get('timer_next') else '')
            + ' <span class="hint">&middot; each check renews only tokens within '
              f'{RENEW_BEFORE_S // 3600} hours of expiring</span>')


def _next_check_row(view, zone):
    if view.get('timer_next'):
        return 'Next check', escape(_at(view['timer_next'], zone))
    if view.get('mode') == 'none':
        return 'Next check', 'Off: automatic renewal isn\'t installed. <em>Renew now</em> still works.'
    if view.get('display_running') is False:
        return 'Next check', ('When the display starts <span class="hint">&middot; on this manual board, '
                              'checks run hourly only while the display is on</span>')
    return 'Next check', ('Not scheduled <span class="hint">&middot; the hourly timer isn\'t running'
                          '</span>')


def _next_renewal_row(view, zone):
    upcoming = _next_renewal(view)
    if not upcoming:
        return None
    at, login = upcoming
    text = _renewal_time(at, view, zone)
    return 'Next renewal', (f'{escape(text[:1].upper() + text[1:])} <span class="hint">&middot; '
                            f'{escape(login.name)}\'s token, '
                            f'{RENEW_BEFORE_S // 3600} hours before it expires</span>')


def _failures_row(view):
    alerts = view.get('alerts') or {}
    if not alerts.get('failures'):
        return None
    count = alerts['failures']
    return 'Failures', (_pill('bad', f'{count} in a row')
                        + f'<span class="hint">{escape(alerts.get("last_message") or "no message")}</span>')


def renewal_status(view, zone=None):
    """Token renewal as labelled rows: whether it's running or how its last run went, when it next
    checks, failures in a row, and the board's mode. data-running makes the page's script follow a
    run (/renew/status answers with this block again)."""
    mode = view.get('mode')
    rows = [('Renewal', _renewal_pill(view))]
    for row in (_last_run_row(view, zone), _interval_row(view), _next_check_row(view, zone),
                _next_renewal_row(view, zone), _failures_row(view)):
        if row:
            rows.append(row)
    mode_text = MODE_TEXT.get(mode, 'Unknown (an older install): re-run the installer to record it.')
    rows.append(('Mode', f'<span class="hint">{escape(mode_text)}</span>'))
    items = ''.join(f'<dt>{label}</dt><dd>{value}</dd>' for label, value in rows)
    return (f'<dl class="facts" id="renewal" aria-live="polite"{" data-running" if view.get("renewing") else ""}>'
            f'{items}</dl>')


def _renews(login, view):
    """When renewal will renew this rider's token (logins.renews_at), or None: no timer (mode none),
    no expiry to go by, or nothing to renew with (no refresh token, on a board without a browser)."""
    mode = view.get('mode')
    if mode == 'none' or not (login.chain or mode == 'browser'):
        return None
    next_check = view.get('timer_next')
    return renews_at(login.token, next_check if isinstance(next_check, (int, float)) else None)


def _next_renewal(view):
    """(when, rider) of the soonest renewal, or None."""
    found = [(at, login) for login in view.get('riders') or () if (at := _renews(login, view)) is not None]
    return min(found, key=lambda pair: pair[0]) if found else None


def _renewal_time(at, view, zone):
    """When a renewal happens, in words (plain text): around a check's time (checks start up to 10
    minutes late, the timer's RandomizedDelaySec), or, with no check scheduled (a manual board's
    display is off), at the first check after it's due."""
    if isinstance(view.get('timer_next'), (int, float)):
        return f'around {when(at, zone)}'
    return f'at the first check after {when(at, zone)}'


def logins_card(view, signed_in=True, outcome=None, problems=(), zone=None, editing=None):
    """Logins: renewal's status, a card per rider (whose Email & password row changes their login,
    with a PIN session only: the setup hotspot alone can't), and Renew now. view: Settings.logins().
    editing: the key of the rider whose login form was just posted, which problems belong to."""
    if not view:
        return ''
    top = ''
    if outcome in LOGIN_OUTCOMES:
        kind, html = LOGIN_OUTCOMES[outcome]
        top += _notice(kind, html, 'alert' if kind == 'bad' else 'status')
    riders = view.get('riders') or []
    if problems and not any(r.key == editing for r in riders):  # not one rider's (the riders changed)
        items = ''.join(f'<li>{escape(p)}</li>' for p in problems)
        top += _notice('bad', f'<strong>Logins not saved.</strong><ul>{items}</ul>', 'alert')
    cards = ''.join(_login_status(r, view, zone, signed_in, problems if r.key == editing else (), r.key == editing)
                    for r in riders)
    actions = ('<div class="actions"><form method="post" action="/renew"><button type="submit" class="secondary">'
               f'{icon("refresh")}Renew now</button></form></div>')
    if not signed_in:
        actions += _notice('info', 'Changing logins takes the PIN, even in setup mode: '
                                   '<a href="/signin">sign in with the PIN</a>.')
    body = top + renewal_status(view, zone) + cards + actions
    return _section('logins', 'Logins', "Each rider's Peloton login, and how the board keeps it working.", body,
                    'key')
