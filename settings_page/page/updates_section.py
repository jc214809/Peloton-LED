"""The Updates card: what's installed, a channel to check, what a check found, Update now and Roll back."""

import re
from html import escape

from self_update.github import FAILED, PASSED, REPO, RUNNING
from self_update.state import ROLLBACK_FAILED, UNFINISHED
from self_update.update import BETA, BETA_BRANCH, CURRENT, RELEASES, WAITING, WOULD_UPDATE, beta_number, name_of, release_of
from settings_page.logins import when
from settings_page.page.icons import icon
from settings_page.page.widgets import _attr, _field, _notice, _options, _post, _section
from settings_page.updates import BUSY, START_FAILED, STARTED, STEPS


def _sentence(text):
    """text as a sentence: a capital (unless it starts with a commit's sha) and a full stop."""
    text = str(text or '').strip()
    if not re.match(r'[0-9a-f]{7,40}\b', text):
        text = text[:1].upper() + text[1:]
    return escape(text + ('' if text.endswith('.') else '.'))


def _short(sha):
    return escape(str(sha)[:7]) if sha else '?'


# What's in an update: at most this many of its pull requests, then "and N more".
CHANGES_SHOWN = 12


def _pr_link(number):
    return f'<a href="https://github.com/{REPO}/pull/{int(number)}" target="_blank" rel="noopener">#{int(number)}</a>'


def _beta_name(version, sha):
    """A Beta by its number when it's exactly one (v0.1.5-beta: "Beta 0.1.5"), else by its commit."""
    number = beta_number(version)
    return f'Beta {escape(number)}' if number else f'Beta <span class="mono">{_short(sha)}</span>'


def _installed_name(view):
    """What's installed, as the card names it: a Beta by its number or commit, else its version."""
    if view.get('installed_channel') == BETA:
        return _beta_name(view['version'], view['sha'])
    return escape(str(view['version']))


def _found_name(found):
    """What a check found (or an update is installing), as the card names it: develop-beta's tip by
    its number or commit, a release by its version, else its ref and commit."""
    if found.get('ref') == BETA_BRANCH:
        return _beta_name(found.get('version'), found.get('sha'))
    if found.get('version'):
        return escape(str(found['version']))
    return f'{escape(str(found.get("ref")))} {_short(found.get("sha"))}'


def _changes(view, found):
    """What an update brings (updates.Updates.details): from what to what, its pull requests (linked
    to GitHub) with their release notes under their titles, and whether pip runs. '' if the check
    couldn't say. Pull requests whose notes say None go in one "Behind the scenes" line."""
    changes = found.get('changes')
    if changes is None:
        return ''
    head = f'<strong>{_installed_name(view)} → {_found_name(found)}</strong>'
    shown, hidden = [], []
    for number, title, *rest in changes:
        notes = rest[0] if rest else None
        if notes == [] and number:
            hidden.append(number)
        else:
            shown.append((number, title, notes))
    items = ''
    for number, title, notes in shown[:CHANGES_SHOWN]:
        tag = _pr_link(number) if number else '<span class="mono">•</span>'
        notes = ''.join(f'<li>{escape(str(note))}</li>' for note in notes or ())
        notes = f'<ul class="notes">{notes}</ul>' if notes else ''
        items += f'<li>{tag}<span>{escape(str(title))}{notes}</span></li>'
    more = len(shown) - CHANGES_SHOWN
    if more > 0:
        items += f'<li><span class="mono"></span><span class="hint">and {more} more</span></li>'
    if hidden:
        items += (
            f'<li><span class="mono"></span><span class="hint">Behind the scenes, nothing you\'d notice: '
            f'{", ".join(_pr_link(number) for number in hidden)}</span></li>'
        )
    packages = (
        '<p class="hint">Its Python packages change too, so it takes longer: up to hours on a Pi Zero.</p>' if found.get('packages') else ''
    )
    return f'<div class="changes"><p>{head}</p>' + (f'<ul aria-label="What\'s in it">{items}</ul>' if items else '') + f'{packages}</div>'


def _started_notice(started, running):
    """How starting an update or rollback went."""
    if started == STARTED and not running:
        return _notice('info', '<strong>Started.</strong> It may be finished already: reload the page to see.')
    if started == BUSY:
        return _notice('warn', "An update or rollback is already running: this one didn't start.")
    if started == START_FAILED:
        return _notice('bad', "<strong>Couldn't start it.</strong> The settings page's log says why.", 'alert')
    return ''


def _progress_notice(view, running):
    """An update running now, or one that stopped midway, or a failed rollback."""
    if running:
        to = view.get('to') or {}
        target = f' · Updating to {_found_name(to)}' if to.get('ref') else ''
        return _notice(
            'info',
            f'<strong id="update-phase">{escape(view["status"] or "")}</strong>'
            f'<span id="update-running"></span>{target}'
            + _steps(view.get('step'))
            + '<p>The board restarts as it updates, and so does this page: it comes back by '
            "itself in a few minutes (sign in again if it asks). Don't change settings until "
            "it's done: a rollback puts config.json back as it was before.</p>" + _changes(view, to),
        )
    if view['phase'] in UNFINISHED:
        return _notice(
            'warn',
            f'<strong>An update stopped midway</strong> (at {escape(view["phase"])}). Roll it back '
            'below, or restart the board: it rolls back at boot.',
            'alert',
        )
    if view['phase'] == ROLLBACK_FAILED:
        return _notice(
            'bad',
            '<strong>The last rollback failed.</strong> Try Roll back again, or over SSH: <code>sudo peloton-rollback</code>.',
            'alert',
        )
    return ''


def _outcome_notice(view, running, zone):
    """How the last update, rollback or boot recovery went (not while one is running)."""
    outcome = view.get('outcome')
    if not outcome or running:
        return ''
    name = {'update': 'update', 'rollback': 'rollback', 'recover': 'rollback at boot'}.get(outcome.get('command'), 'update')
    return _notice(
        'good' if outcome.get('ok') else 'bad',
        f'<strong>Last {name}</strong> ({escape(when(outcome.get("at"), zone))}): {_sentence(outcome.get("message"))}',
        'status' if outcome.get('ok') else 'alert',
    )


def _installed_block(view):
    where = f'on {escape(view["branch"])}' if view['branch'] else 'as installed by an update'
    if view.get('installed_channel') == BETA:
        release = release_of(view['version'])
        newer = f', newer than release {escape(release)}' if release != '0.0.0' else ''  # 0.0.0: none yet
        return f'<p><strong>{_installed_name(view)}</strong></p><p class="hint">A Beta (test) version {where}{newer}</p>'
    return (
        f'<p><strong>{escape(str(view["version"]))}</strong> <span class="mono">{_short(view["sha"])}</span></p><p class="hint">{where}</p>'
    )


def _check_form(view, running):
    return (
        '<form method="post" action="/update/check" data-busy="Checking…" class="add-row">'
        + _options('channel', [(RELEASES, 'Releases'), (BETA, 'Beta')], view['channel'])
        + f'<button type="submit" class="secondary"{" disabled" if running else ""}>{icon("refresh")}'
        '<span>Check</span></button></form>'
    )


def _rollback_field(view, running):
    """The Roll back row, when there is an update to undo ('' if not)."""
    old = view.get('from')
    if not (old and view['phase'] not in ('idle', 'rolled_back')):
        return ''
    # The exact commit (and branch) from before the update, whatever channel is picked above.
    # A point taken before rollback points had a channel: on develop-beta, it was a Beta.
    back_to = name_of({**old, 'channel': BETA} if old.get('branch') == BETA_BRANCH else old) + (
        f' on {old["branch"]}' if old.get('branch') else ''
    )
    return _field(
        'update_rollback',
        'Roll back',
        _post(
            '/update/rollback',
            'Roll back',
            'undo',
            'Rolling back…',
            confirm='Roll back the last update? This also puts back config.json as it was before it, undoing settings saved since.',
            disabled=running,
        ),
        f'Back to {back_to}, as before the last update. This also puts back config.json as it was then, undoing settings saved since.',
    )


def updates_card(view, started=None, zone=None):
    """The Updates card, from updates.Updates.view(): what's installed, how the last update went, a
    channel to check, and Update now (after a check found one) and Roll back. started: how starting
    an update or rollback went, one of updates.STARTS."""
    if not view:
        return ''
    running = view['running']
    top = _started_notice(started, running) + _progress_notice(view, running) + _outcome_notice(view, running, zone)
    body = (
        top
        + _field('update_installed', 'Installed', _installed_block(view))
        + _field(
            'channel',
            'Check for a newer version',
            _check_form(view, running) + ('' if running else check_result(view, zone)),
            'Releases: the newest release. Beta: the newest test version whose checks passed. '
            "Never a downgrade: from Beta, Releases waits for a release newer than what's installed.",
        )
    )
    body += _rollback_field(view, running)
    return _section('updates', 'Updates', "This board's version, and newer ones from GitHub.", body, 'refresh')


def _steps(step):
    """An update's STEPS, step (an index) the one it's on; hidden for a rollback (step None)."""
    items = ''
    for i, text in enumerate(STEPS):
        if step is not None and i < step:
            items += f'<li class="done">{escape(text)}</li>'
        elif i == step:
            items += f'<li class="now" aria-current="step">{escape(text)}</li>'
        else:
            items += f'<li>{escape(text)}</li>'
    return f'<ol class="steps" id="update-steps" aria-label="Steps"{" hidden" if step is None else ""}>{items}</ol>'


def _run_name(name):
    """A CI run's name in words: "pytest (3.11)" is "Tests on Python 3.11"."""
    found = re.fullmatch(r'(?:py)?test \((\d+\.\d+)\)', name)
    return f'Tests on Python {found.group(1)}' if found else name


def _waiting(runs, checked):
    """A newer Beta held back by its CI (runs: [name, RUNNING/PASSED/FAILED] each), as a notice
    with one row per run, in the update steps' style."""
    states = [state for _, state in runs]
    if FAILED in states:
        headline, after = "A newer Beta didn't pass its tests", "It won't be installed; the next Beta that passes can be."
    elif runs:
        headline = 'A newer Beta is being tested'
        after = f'It can be installed once {"both pass" if len(runs) == 2 else "they all pass" if len(runs) > 2 else "it passes"}.'
    else:
        headline, after = "A newer Beta hasn't been tested yet", 'It can be installed once its tests pass.'
    rows = ''
    for name, state in sorted(runs):
        css = {RUNNING: ' class="now"', PASSED: ' class="done"', FAILED: ' class="failed"'}.get(state, '')
        rows += f'<li{css}>{escape(_run_name(name))}: {escape(state)}</li>'
    steps = f'<ol class="steps" aria-label="Tests">{rows}</ol>' if rows else '<br>'
    return _notice('info', f'<strong>{headline}.</strong>{checked}{steps}<span class="when">{after}</span>')


def check_result(view, zone=None):
    """What the last check found (updates.Updates.view()'s "check"), under the Check button: an
    update with Update now, the newest already, or why it can't; while the page's own check runs,
    a placeholder its script replaces. '' when there's nothing to say."""
    check = view.get('check')
    if not check:
        if not view.get('auto_check'):
            return ''
        name = 'Beta' if view['channel'] == BETA else 'Releases'
        return (
            f'<div id="update-check" data-auto="{_attr(view["channel"])}">'
            + _notice('info', f'Checking {name} for a newer version…')
            + '</div>'
        )
    name = 'Beta' if check['channel'] == BETA else 'Releases'
    checked = f' <span class="when">· checked {escape(when(check["at"], zone))}</span>'
    if check['result'] == WOULD_UPDATE:
        found = (
            _notice('new', f'<strong>Update available on {name}: {_found_name(check)}</strong>{checked}' + _changes(view, check))
            + '<div class="below">'
            + _post(
                '/update/start',
                'Update now',
                'refresh',
                'Starting…',
                'primary',
                f'<input type="hidden" name="channel" value="{_attr(check["channel"])}">',
            )
            + '</div><p class="hint">A few minutes, longer if its Python packages change. If the new '
            "version doesn't work within 5 minutes, the board rolls back by itself.</p>"
        )
    elif check['result'] == CURRENT:
        found = _notice(
            'good',
            f'<strong>Up to date:</strong> this is the newest on {name}.{checked}'
            f'<br><span class="when">{_sentence(check["message"])}</span>',
        )
    elif check['result'] == WAITING and isinstance(check.get('runs'), list):
        found = _waiting(check['runs'], checked)
    elif check['result'] == WAITING:
        found = _notice(
            'info',
            f"<strong>Up to date for now:</strong> a newer {name} version isn't ready yet."
            f'{checked}<br><span class="when">{_sentence(check["message"])}</span>',
        )
    else:
        found = _notice('warn', f"<strong>Can't update right now:</strong> {_sentence(check['message'])}{checked}")
    return f'<div id="update-check">{found}</div>'
