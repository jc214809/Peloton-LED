"""Small HTML builders the page's cards share: escaping, labelled fields, switches, notices, pills, buttons."""

from html import escape

from settings_page.form import number_text
from settings_page.logins import when
from settings_page.page.icons import icon


def _attr(value):
    return escape(str(value), quote=True)


def _hint(text):
    return f'<p class="hint">{escape(text)}</p>' if text else ''


def _field(name, label, control, hint='', inline=False):
    """A labelled row: label and hint on the left, the control on the right (stacked on a phone)."""
    return (
        f'<div class="field{" inline" if inline else ""}"><div class="field-label"><div class="label-row">'
        f'<label for="{name}">{escape(label)}</label></div>{_hint(hint)}</div>'
        f'<div class="field-control">{control}</div></div>'
    )


def _input(name, value='', kind='text', extra=''):
    return f'<input type="{kind}" id="{name}" name="{name}" value="{_attr(value)}"{extra}>'


def _unit(control, unit):
    """A field with its unit ("s", "%") inside its right edge; the label still says what it is."""
    if not unit:
        return control
    return f'<span class="unit" style="--u: {len(unit)}">{control}<span class="unit-text" aria-hidden="true">{escape(unit)}</span></span>'


def _number(name, value, placeholder='', extra='', unit=None, least=0):
    """A number field: decimals allowed (step any) unless extra says otherwise; least is its min."""
    return _unit(
        _input(
            name,
            number_text(value),
            'number',
            f' inputmode="decimal" step="any" min="{number_text(least)}" placeholder="{_attr(number_text(placeholder))}"{extra}',
        ),
        unit,
    )


def _options(name, options, chosen, extra=''):
    """options: (value, text) pairs."""
    opts = ''.join(f'<option value="{_attr(v)}"{" selected" if v == chosen else ""}>{escape(t)}</option>' for v, t in options)
    return f'<select id="{name}" name="{name}"{extra}>{opts}</select>'


def _switch_input(name, on, extra=''):
    return f'<input type="checkbox" class="switch" role="switch" id="{name}" name="{name}"{" checked" if on else ""}{extra}>'


def _switch(name, label, on, hint=''):
    return _field(name, label, _switch_input(name, on), hint, inline=True)


def _section(sid, title, description, body, glyph):
    return (
        f'<section class="card" id="{sid}" aria-labelledby="{sid}-title"><div class="card-head">'
        f'<span class="card-icon">{icon(glyph)}</span><div><h2 id="{sid}-title">{escape(title)}</h2>'
        f'<p>{escape(description)}</p></div></div><div class="card-body">{body}</div></section>'
    )


def _mini(name, label, control):
    return f'<div><label class="mini" for="{name}">{escape(label)}</label>{control}</div>'


def _tip(tid, label, text):
    """A column heading's ⓘ: its text shows on hover, keyboard focus or a tap (which focuses it), and
    screen readers get it as the button's description."""
    return (
        f'<span class="tip-wrap"><button type="button" class="tip" aria-label="About {_attr(label)}" '
        f'aria-describedby="{tid}">{icon("info")}</button>'
        f'<span class="tip-text" role="tooltip" id="{tid}">{escape(text)}</span></span>'
    )


def _notice(kind, html, role='status'):
    glyph = {'good': 'check', 'bad': 'alert', 'warn': 'info', 'info': 'info', 'new': 'refresh'}[kind]
    return f'<div class="notice {kind}" role="{role}">{icon(glyph)}<div>{html}</div></div>'


def _pill(kind, text):
    return f'<span class="pill {kind}">{escape(text)}</span>'


def _post(action, label, glyph, busy, kind='secondary', fields='', confirm=None, disabled=False):  # noqa: PLR0913
    """A one-button form of the Updates card. busy: the button's text while it works."""
    extra = f' data-confirm="{_attr(confirm)}"' if confirm else ''
    return (
        f'<form method="post" action="{action}" data-busy="{_attr(busy)}"{extra}>{fields}'
        f'<button type="submit" class="{kind}"{" disabled" if disabled else ""}>{icon(glyph)}'
        f'<span>{escape(label)}</span></button></form>'
    )


def _secret_input(name, label, kind, is_set, autocomplete='off'):
    """A write-only field: it never holds the saved value, only says whether there is one."""
    placeholder = 'Saved: type to replace' if is_set else 'Not set'
    return _mini(name, label, _input(name, '', kind, f' autocomplete="{autocomplete}" spellcheck="false" placeholder="{placeholder}"'))


def _at(value, zone):
    """A time from Settings.logins() (epoch seconds) in the page's style, or systemd's own text."""
    return when(value, zone) if isinstance(value, (int, float)) else str(value)


def _zone(display):
    """The board's zone for times on the page, or the server's own."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(display['timezone']) if isinstance(display.get('timezone'), str) else None
    except (ValueError, KeyError, OSError):
        return None
