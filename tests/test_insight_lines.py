"""Workout compare on the board: the two short lines per insight, and that they fit the panel."""
import pytest

from display.display import get_text_width, initialize_fonts, loaded_fonts
from peloton.insight_lines import HIDDEN_CODES, LINE_MAX, board_lines, first_board_insight, versus
from peloton.workout_insights import insights
from tests.test_workout_insights import effort, foot, heavier, lighter, ride, run_bike

ROOM = 64 - 4
BIKE = {'value': 124, 'usual': 188, 'unit': 'W', 'foot': False, 'noun': 'ride'}
SHOWN = {
    'output_down': BIKE,
    'output_up': {**BIKE, 'value': 205, 'usual': 180},
    'in_line': {**BIKE, 'value': 112, 'usual': 111},
    'resistance_low': {'pct': 28},
    'cadence_low': {'pct': 37},
    'pace_low': {'pct': 42},
    'go_up_lighter': {'movement': 'Barbell Deadlift', 'lb': 35, 'usual': 40, 'unit': 'lb', 'category': 'heavy',
                      'on_movement': True, 'pct': 20},
    'go_up_streak': {'lb': 40, 'unit': 'lb', 'category': 'heavy', 'n': 3, 'pct': 20},
    'went_heavier': {'movement': 'Row', 'lb': 50, 'usual': 40, 'unit': 'lb', 'category': 'heavy',
                     'on_movement': True},
    'missed_targets': {'missed': 3, 'sets': 8, 'movement': 'Row'},
    'effort_high': {'n': 6, 'value': 20.0},
    'effort_low': {'n': 5, 'value': 5.0},
}
EXPECTED = {
    'output_down': ['OUTPUT DOWN', '124 VS 188 W'],
    'output_up': ['STRONG RIDE', '205 VS 180 W'],
    'in_line': ['ON YOUR USUAL', '112 VS 111 W'],
    'resistance_low': ['RESISTANCE LOW', '28% UNDER'],
    'cadence_low': ['CADENCE LOW', '37% UNDER'],
    'pace_low': ['UNDER PACE', '42% OF THE TIME'],
    'go_up_lighter': ['GO UP A WEIGHT', 'BARBELL DEADLIFT'],
    'go_up_streak': ['GO UP: HEAVY', 'FROM 40 LB'],
    'went_heavier': ['HEAVIER: KEEP', '50 VS 40 LB'],
    'missed_targets': ['DROP A WEIGHT', 'ROW'],
    'effort_high': ['HARDEST BY HR', 'OF YOUR LAST 6'],
    'effort_low': ['EASIEST BY HR', 'OF YOUR LAST 5'],
}
MOVEMENT_CODES = ('go_up_lighter', 'missed_targets')


@pytest.mark.parametrize('code', sorted(SHOWN))
def test_every_code_gives_the_two_lines(code):
    assert board_lines(code, SHOWN[code]) == EXPECTED[code]


def test_wording_for_feet_and_nouns():
    foot_facts = {'value': 3.6, 'usual': 4.1, 'unit': 'mph', 'foot': True, 'noun': 'run'}
    assert board_lines('output_down', foot_facts) == ['PACE DOWN', '3.6 VS 4.1 MPH']
    for noun in ('ride', 'row', 'run', 'walk', 'bootcamp', 'class'):
        assert board_lines('output_up', {**BIKE, 'noun': noun})[0] == f'STRONG {noun.upper()}'


def test_versus_drops_the_unit_then_falls_back_to_the_value():
    assert versus(124, 188, 'W') == '124 VS 188 W'
    assert versus(1124, 1188, 'W') == '1124 VS 1188 W'
    assert versus(11240, 11880, 'W') == '11240 VS 11880'
    assert versus(11240000, 11880000, 'W') == '11240000 W'
    assert versus(3.6, 4.1, 'mph') == '3.6 VS 4.1 MPH'
    assert versus(12.5, 12.5, 'mph') == '12.5 VS 12.5'
    assert versus(124.4, 187.6, 'W') == '124 VS 188 W'


def test_hidden_unknown_and_missing_facts_give_none():
    for code in HIDDEN_CODES:
        assert board_lines(code, {'n': 3, 'noun': 'ride'}) is None
    assert board_lines('pace_low', {'pct': 100}) == ['UNDER PACE', '100% OF TIME']
    assert board_lines('made_up', {}) is None
    assert board_lines('output_down', {}) is None
    assert board_lines('output_down', None) is None
    assert board_lines('go_up_streak', {'lb': 40}) is None
    assert board_lines('effort_high', {'n': None, 'value': 1}) is not None  # prints, never crashes


WORST = [
    ('output_down', {'value': 999, 'usual': 999, 'unit': 'W', 'foot': False, 'noun': 'ride'}),
    ('output_down', {'value': 12.5, 'usual': 12.5, 'unit': 'mph', 'foot': True, 'noun': 'run'}),
    ('output_up', {'value': 999, 'usual': 999, 'unit': 'W', 'foot': False, 'noun': 'bootcamp'}),
    ('in_line', {'value': 12.5, 'usual': 12.5, 'unit': 'mph', 'foot': True, 'noun': 'bootcamp'}),
    ('resistance_low', {'pct': 100}),
    ('cadence_low', {'pct': 100}),
    ('pace_low', {'pct': 100}),
    ('go_up_streak', {'lb': 100, 'category': 'medium'}),
    ('went_heavier', {'movement': 'Row', 'lb': 100, 'usual': 95}),
    ('effort_high', {'n': 12, 'value': 99}),
    ('effort_low', {'n': 12, 'value': 1}),
]


@pytest.mark.parametrize('height', (64, 32))
def test_every_non_movement_line_fits_the_stats_font(height):
    initialize_fonts(height)
    font = loaded_fonts['stats']
    cases = [(code, facts) for code, facts in SHOWN.items()] + WORST
    for code, facts in cases:
        lines = board_lines(code, facts)
        assert len(lines) == 2
        for index, line in enumerate(lines):
            if code in MOVEMENT_CODES and index == 1:
                continue
            assert len(line) <= LINE_MAX, line
            assert get_text_width(font, line) <= ROOM, (code, line)


def test_first_board_insight_skips_hidden_codes():
    messages = [('freestyle', 'x', {}), ('too_few', 'y', {'n': 1}), ('cadence_low', 'z', {'pct': 40}),
                ('resistance_low', 'w', {'pct': 30})]
    assert first_board_insight(messages) == {'code': 'cadence_low', 'lines': ['CADENCE LOW', '40% UNDER'],
                                             'facts': {'pct': 40}}
    assert first_board_insight([('nothing', 'x', {'n': 5}), ('no_tracker', 'y', {})]) is None
    assert first_board_insight([]) is None
    # A shown code whose facts are missing is skipped for the next one.
    assert first_board_insight([('output_down', 'a', {}), ('cadence_low', 'b', {'pct': 40})])['code'] == 'cadence_low'


def test_real_insights_make_board_lines_from_their_own_facts():
    bike = run_bike(124, [188] * 5)
    assert first_board_insight(bike)['lines'] == ['OUTPUT DOWN', '124 VS 188 W']
    target = foot(0, 3.6)
    result = insights(target, [target] + [foot(i, 4.1) for i in range(1, 6)])
    assert first_board_insight(result)['lines'] == ['PACE DOWN', '3.6 VS 4.1 MPH']
    assert first_board_insight(lighter())['lines'] == ['GO UP A WEIGHT', 'ROW']
    assert first_board_insight(heavier())['lines'] == ['HEAVIER: KEEP', '45 VS 40 LB']
    assert first_board_insight(effort(20, [10, 11, 12, 13, 14]))['lines'] == ['ON YOUR USUAL', '100 VS 100 W']
    target = ride(0, None, strive=20)
    result = insights(target, [target] + [ride(i, 100, strive=10) for i in range(1, 6)])
    assert first_board_insight(result)['lines'] == ['HARDEST BY HR', 'OF YOUR LAST 5']
    t = ride(0, 100, target_under={'resistance': 28})
    assert first_board_insight(insights(t, [t]))['lines'] == ['RESISTANCE LOW', '28% UNDER']
    t = ride(0, 100)
    assert first_board_insight(insights(t, [t])) is None
