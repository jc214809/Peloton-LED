"""Screen times (peloton/screen_times.py): never 0, shared out across a page's frames, and the settings
page's figures are the board's."""
import copy
import json
import logging
import re

import pytest

from peloton import screen_times
from peloton.config import DEFAULTS, ROTATION_SECTIONS, load_config
from peloton.dashboard import Dashboard
from peloton.screen_times import page_seconds, retire_zero_times
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix
from settings_page import page
from settings_page.form import apply_form

from test_settings_form import posted

RIVALS = [{'name': 'Joel', 'workouts': 5, 'minutes': 245, 'output_kj': 1234},
          {'name': 'Jen', 'workouts': 4, 'minutes': 190, 'output_kj': 612}]


def _retire(display):
    display = copy.deepcopy(display)
    return display, retire_zero_times(display, ROTATION_SECTIONS, DEFAULTS['rotation'])


def test_the_shared_numbers_match_the_screens_and_config_they_stand_for():
    from display.ui import username, versus_screen
    from display.ui.celebration_screen import INTRO_SECONDS, MIN_CARD_SECONDS
    assert screen_times.VERSUS_STATS == len(versus_screen.STATS)
    assert screen_times.FRAME_SECONDS == username.DETAIL_INTERVAL_SECONDS == versus_screen.DETAIL_INTERVAL_SECONDS
    assert screen_times.CELEBRATION_MIN_SECONDS == pytest.approx(INTRO_SECONDS + MIN_CARD_SECONDS)
    assert all(DEFAULTS[key] == value for key, value in screen_times.FALLBACK_DEFAULTS.items())


def test_the_journeys_two_steps_need_4_seconds_each():
    assert screen_times.least_seconds('journey', 32, 2) == 8
    assert screen_times.least_seconds('journey', 32) == screen_times.least_seconds('journey', 64) == 1
    display = {**DEFAULTS, 'screen_durations': {'journey': 3}}
    assert page.shows_for('journey', display, 32) == (
        '3 s. With miles of more than one type, the trip then the miles by type, 4 s each (8 s in all).')
    assert page.shows_for('journey', display, 64) == '3 s.'


def test_an_old_zero_is_the_switch_it_meant():
    display, changed = _retire({'rotation': ['username', 'goals', 'lifetime', 'total_workouts', 'versus'],
                                'screen_durations': {'goals': 0, 'versus': 12}, 'logo_duration': 0})
    assert display == {'rotation': ['username', 'lifetime', 'total_workouts', 'versus'],
                       'screen_durations': {'versus': 12}, 'show_logo': False}
    assert changed and any('goals' in line for line in changed)


def test_a_zero_fallback_switches_off_only_the_screens_that_use_it():
    display, _ = _retire({'overview_duration': 0, 'duration': 0, 'screen_durations': {'versus': 9, 'lifetime': 6}})
    # No rotation in the file: the default one, less what 0 hid. Lifetime and versus have their own.
    assert display['rotation'] == ['latest_workouts', 'versus', 'total_workouts', 'lifetime']
    assert 'overview_duration' not in display and 'duration' not in display
    display, _ = _retire({'rotation': ['latest_workouts', 'username'], 'last_workout_detail_interval': 0})
    assert display == {'rotation': ['username']}


def test_a_config_without_zeros_is_left_alone():
    config = {'rotation': ['username'], 'screen_durations': {'username': 6}, 'logo_duration': 5}
    display, changed = _retire(config)
    assert (display, changed) == (config, [])
    assert retire_zero_times(None, ROTATION_SECTIONS, DEFAULTS['rotation']) == []


def test_an_old_config_with_zeros_still_loads_and_says_what_it_switched_off(tmp_path, caplog):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'display': {'rotation': ['username', 'heatmap'], 'logo_duration': 0,
                                            'screen_durations': {'heatmap': 0}}}))
    with caplog.at_level(logging.WARNING, logger='peloton-led.config'):
        display = load_config(path)['display']
    assert display['rotation'] == ['username'] and display['show_logo'] is False
    assert display['logo_duration'] == DEFAULTS['logo_duration'] and display['screen_durations'] == {}
    assert 'switched off: heatmap' in caplog.text


def test_more_time_on_the_name_page_means_longer_highlights_not_a_repeat():
    snapshot = {'summaries': [], 'status': 'ready', 'totals': {'Total Workouts': 600, 'Cycling': 400},
                'weekly_progress': {'workouts': 3, 'minutes': 90}}
    display = {**DEFAULTS, 'rotation': ['username'], 'screen_durations': {'username': 24}}
    (_, state, duration), = build_rotation_pages(snapshot, None, display, 'Joel', 64)
    assert len(state['details']) == 3 and duration == 24 and state['detail_seconds'] == 8
    display['screen_durations']['username'] = 5  # under 4 s a highlight: raised, never cut short
    (_, state, duration), = build_rotation_pages(snapshot, None, display, 'Joel', 64)
    assert duration == 12 and state['detail_seconds'] == 4


def _frame(screen, state, height, at):
    from display.display import initialize_fonts
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    screen.on_enter(matrix, state)
    screen.update(at)
    screen.render(matrix, state)
    return matrix.image.tobytes()


def test_the_name_page_holds_its_last_highlight_instead_of_starting_over():
    from display.ui.username import UsernameScreen
    details = [{'label': f'FACT {i}', 'lines': [f'LINE {i}']} for i in range(3)]
    state = {'username': 'Joel', 'details': details, 'detail_seconds': 8}
    first, last = (_frame(UsernameScreen('info'), state, 64, at) for at in (1, 17))
    assert first != last
    assert _frame(UsernameScreen('info'), state, 64, 25) == last, 'past the end: still the last, not the first'
    assert _frame(UsernameScreen('info'), state, 64, 9) not in (first, last), 'the second, 8 s in'


def test_head_to_head_on_32_rows_shares_its_time_across_the_stats():
    from display.ui.versus_screen import VersusScreen
    display = {**DEFAULTS, 'rotation': ['versus'], 'screen_durations': {'versus': 24}}
    snapshot = {'summaries': [], 'status': 'ready', 'totals': {}}
    (_, state, duration), = build_rotation_pages(snapshot, None, display, 'Joel', 32, rivals=RIVALS)
    assert duration == 24 and state['stat_seconds'] == 8
    first, last = (_frame(VersusScreen(), state, 32, at) for at in (1, 17))
    assert first != last and _frame(VersusScreen(), state, 32, 25) == last
    (_, state, duration), = build_rotation_pages(snapshot, None, display, 'Joel', 64, rivals=RIVALS)
    assert duration == 24 and 'stat_seconds' not in state  # 64 rows: one page with every stat


# The board's page names, by the rotation screen that makes them.
SECTION_OF = {'username': 'username', 'streak': 'streaks', 'streak_risk': 'streaks', 'versus': 'versus',
              'discipline': 'total_workouts', 'lifetime': 'lifetime', 'countdown': 'next_milestone',
              'journey': 'journey', 'heatmap': 'heatmap', 'goal': 'goals', 'celebration': 'milestones'}


@pytest.mark.parametrize('rows', [32, 64])
def test_the_settings_page_says_the_times_the_board_plays(tmp_path, rows):
    """Every screen's page, built by the board from demo data, lasts what the settings page's line says."""
    display = {**DEFAULTS, 'rotation': list(DEFAULTS['rotation']), 'weekly_goals': {'workouts': 5, 'minutes': 150},
               'milestones': [100, 2000], 'milestone_within': 50, 'overview_duration': 3,
               'screen_durations': {'versus': 7, 'lifetime': 2, 'username': 30, 'goals': 6}}
    dashboard = Dashboard(tmp_path / 'missing-token', display, demo=True)
    snapshot = dashboard.snapshot()
    pages = build_rotation_pages(snapshot, dashboard, display, 'Joel', rows, rivals=RIVALS)
    seen = set()
    for name, state, duration in pages:
        section = SECTION_OF.get(name)
        if section is None:
            continue
        seen.add(section)
        frames = len(state['details']) if section == 'username' else 2 if 'step_seconds' in state else 1
        assert duration == page_seconds(display, section, rows, frames), section
        line = page.shows_for(section, display, rows)
        if frames > 1 and section == 'journey':  # the demo has bike and walk/run miles: both steps
            assert f'({page.number_text(round(duration, 1))} s in all)' in line, line
        elif section != 'username':  # its line gives the rule (it depends on the day's highlights)
            assert line.startswith(f'{page.number_text(round(duration, 1))} s'), (section, line)
    assert {'username', 'versus', 'total_workouts', 'lifetime', 'goals', 'journey'} <= seen


def _rotation_row(html, name):
    return html.split(f'value="{name}">', 1)[1].split('</li>', 1)[0]


@pytest.mark.parametrize('rows', [32, 64])
def test_latest_workouts_has_no_seconds_box_its_pages_last_every_stat_once(rows):
    config = {'matrix': {'rows': rows, 'cols': 64},
              'display': {'screen_durations': {'latest_workouts': 15}, 'compact_workout_pages': True}}
    row = _rotation_row(page.settings_page(config), 'latest_workouts')
    assert 'name="duration_latest_workouts"' not in row and 'Every stat' in row
    assert 'every stat once: 4 s each' in row


def test_each_seconds_box_starts_at_what_its_screen_needs():
    for rows, versus in ((64, '1'), (32, '12')):
        html = page.settings_page({'matrix': {'rows': rows, 'cols': 64}, 'display': {}})
        mins = dict(re.findall(r'id="duration_(\w+)" name="duration_\w+" value="[^"]*" inputmode="decimal" '
                               r'step="any" min="([^"]+)"', html))
        assert mins['lifetime'] == '5' and mins['milestones'] == '5.8' and mins['username'] == '4'
        assert mins['versus'] == versus and mins['goals'] == '1'
        assert re.search(r'id="logo_duration" [^>]*min="1"', html)


def test_a_saved_time_under_the_minimum_shows_and_saves_as_the_board_plays_it():
    config = {'matrix': {'rows': 32, 'cols': 64},
              'display': {'screen_durations': {'lifetime': 3.2, 'versus': 5}}}
    html = page.settings_page(config)
    assert 'id="duration_lifetime" name="duration_lifetime" value="5"' in html
    assert 'id="duration_versus" name="duration_versus" value="12"' in html
    new, problems = apply_form(config, posted(config))
    assert problems == [] and new['display']['screen_durations'] == {'lifetime': 5, 'versus': 12}


def test_a_time_under_the_minimum_is_refused_with_how_to_hide_the_screen():
    config = {'matrix': {'rows': 32, 'cols': 64}, 'display': {}}
    for field, value, message in (('duration_versus', '8', 'Head to head needs at least 12 seconds'),
                                  ('duration_lifetime', '0', 'Lifetime by discipline needs at least 5 seconds'),
                                  ('logo_duration', '0', 'Logo needs at least 1 second. To hide the logo')):
        _, problems = apply_form(config, posted(config, **{field: value}))
        assert problems and problems[0].startswith(message), problems


def test_the_logo_has_a_switch_and_an_old_zero_shows_it_off():
    html = page.settings_page({'display': {'logo_duration': 0}})
    timing = html.split('id="timing"', 1)[1].split('</section>', 1)[0]
    assert 'id="show_logo"' in timing and 'id="show_logo" name="show_logo">' in timing  # unticked
    assert timing.index('id="show_logo"') < timing.index('id="logo_duration"')
    config = {'display': {'logo_duration': 0, 'rotation': ['username', 'goals'], 'screen_durations': {'goals': 0}}}
    new, problems = apply_form(config, posted(config))
    assert problems == []
    assert new['display']['show_logo'] is False and 'logo_duration' not in new['display']
    assert new['display']['rotation'] == ['username'] and 'goals' not in new['display']['screen_durations']
    new, _ = apply_form({}, posted({}))
    assert new['display']['show_logo'] is True


def test_an_old_zero_shows_its_screen_switched_off():
    html = page.settings_page({'display': {'rotation': ['username', 'heatmap'],
                                           'screen_durations': {'heatmap': 0}}})
    assert 'name="rotation_on_heatmap"' in html
    assert 'id="rotation_on_heatmap" name="rotation_on_heatmap" aria-label' in html  # not checked
    assert 'value="0"' not in _rotation_row(html, 'heatmap')
