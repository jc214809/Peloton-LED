"""The settings form's hardware cards: Panel (size, brightness, wiring) and Advanced (every other matrix setting)."""
from peloton.config import GPIO_MAPPINGS, MATRIX_DEFAULTS
from settings_page.form import (PANEL_FIELDS, PANEL_SIZES, ROTATIONS, SWITCH_KEYS, advanced_keys, number_text,
                                panel_size)
from settings_page.page.icons import icon
from settings_page.page.widgets import _attr, _field, _input, _notice, _options, _section, _switch, _unit

# Units for matrix settings that have one.
MATRIX_UNITS = {'brightness': '%', 'pwm_lsb_nanoseconds': 'ns', 'limit_refresh': 'Hz'}


def _matrix_field(key, label, hint, value):
    """A config.json "matrix" setting's row; blank, it's the app's default (MATRIX_DEFAULTS)."""
    name = f'matrix_{key}'
    default = MATRIX_DEFAULTS[key]
    blank = f'Default: {"On" if default is True else "Off" if default is False else default}' \
        if default not in (None, '') else 'Default'
    if key == 'pixel_mapper':
        choices = list(ROTATIONS) + ([(value, value)] if value and value not in dict(ROTATIONS) else [])
        control = _options(name, [('', 'Right way up')] + choices, value or '')
    elif key == 'gpio_mapping':
        # Pi boards need one (the installer stops without it), so "not set" is offered only when it isn't.
        choices = [(m, m) for m in GPIO_MAPPINGS]
        control = _options(name, ([('', 'Not set')] if value not in GPIO_MAPPINGS else []) + choices, value or '')
    elif key in SWITCH_KEYS:
        chosen = '' if value is None else ('true' if value else 'false')
        control = _options(name, [('', blank), ('true', 'On'), ('false', 'Off')], chosen)
    elif isinstance(default, str):
        control = _input(name, value or '', extra=f' class="mono" placeholder="{_attr(blank)}"')
    else:
        control = _unit(_input(name, number_text(value), 'number',
                               f' inputmode="numeric" step="1" placeholder="{_attr(blank)}"'), MATRIX_UNITS.get(key))
    return _field(name, label, control, hint)


def panel_card(matrix):
    sizes = list(PANEL_SIZES) + ([panel_size(matrix)] if panel_size(matrix) not in PANEL_SIZES else [])
    return _section('panel', 'Panel', "The LED panel's size, brightness and wiring.", (
        _field('panel_size', 'Panel size', _options('panel_size', [(s, s) for s in sizes], panel_size(matrix)),
               'Columns x rows, as on the panel\'s label.')

        + ''.join(_matrix_field(key, label, hint, matrix.get(key)) for key, label, hint in PANEL_FIELDS)
    ), 'board')


def advanced_card(config, display, matrix):
    return (
        '<details class="card" id="advanced"><summary class="card-head">'
        f'<span class="card-icon">{icon("sliders")}</span><div><h2>Advanced</h2>'
        '<p>Logging, a fallback name and panel hardware. Most boards never need these.</p></div>'
        f'<span class="chev">{icon("chevron")}</span></summary><div class="card-body">'
        + _switch('debug', 'Debug logging', config.get('debug', False), "More detail in the display's log.")
        + _field('username', 'Fallback name', _input('username', display.get('username') or '',
                                                     extra=' placeholder="Your Peloton username"'),
                 'Only shown if Peloton gives no username. Riders have their own in Goals.')
        + _notice('warn', 'The wrong panel settings can leave the board dark or flickering. Blank leaves each '
                          'one to the default.')
        + ''.join(_matrix_field(key, key.replace('_', ' ').capitalize(), '', matrix.get(key))
                  for key in advanced_keys())
        + '</div></details>')
