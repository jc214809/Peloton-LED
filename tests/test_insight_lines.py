"""Workout compare on the board: what each insight's frames say, and that it fits the panel."""
import pytest

from display.display import get_text_width, initialize_fonts, loaded_fonts
from peloton.insight_lines import (EDGE_MAX, HIDDEN_CODES, LINE_MAX, LINES_32, LINES_64, MAX_BLOCKS, MAX_BOARD_INSIGHTS,
                                   board_insights, board_view, wrap)
from peloton.workout_insights import insights
from tests.test_workout_insights import effort, foot, heavier, lighter, ride, run_bike

BIKE = {'value': 124, 'usual': 188, 'unit': 'W', 'foot': False, 'noun': 'ride', 'n': 9, 'real': 9, 'reason': None}
LONG = 'Alternating Lateral Lunge Pulse'  # made up: 31 characters
assert len(LONG) >= 30
SHOWN = {
    'output_down': {**BIKE, 'reason': 'easier'},
    'output_up': {**BIKE, 'value': 205, 'usual': 180, 'reason': 'efficient'},
    'in_line': {**BIKE, 'value': 112, 'usual': 108, 'close': True},
    'resistance_low': {'pct': 28},
    'cadence_low': {'pct': 37},
    'pace_low': {'pct': 42},
    'go_up_lighter': {'movement': 'Bent Over Row', 'lb': 20, 'usual': 30, 'unit': 'lb', 'category': 'medium',
                      'on_movement': True, 'pct': 35},
    'go_up_streak': {'lb': 40, 'unit': 'lb', 'category': 'heavy', 'n': 3, 'pct': 20},
    'went_heavier': {'movement': 'Bent Over Row', 'lb': 50, 'usual': 40, 'unit': 'lb', 'category': 'heavy',
                     'on_movement': True},
    'missed_targets': {'missed': 3, 'sets': 9, 'movement': 'Bent Over Row'},
    'effort_high': {'n': 12, 'value': 29.4, 'noun': 'ride', 'rate': 0.98, 'usual_rate': 0.76},
    'effort_low': {'n': 5, 'value': 9.0, 'noun': 'ride', 'rate': 0.45, 'usual_rate': 0.76},
}
# (headline, sentence, reason line, footer) from the plan's wording table.
EXPECTED = {
    'output_down': ('OUTPUT DOWN', 'OUTPUT DOWN VS YOUR TYPICAL: 124 W VS 188 W. HR LOWER TOO: AN EASIER DAY.',
                    'AN EASIER DAY', '9 SIMILAR RIDES'),
    'output_up': ('STRONG RIDE', 'STRONG RIDE VS YOUR TYPICAL: 205 W VS 180 W. MORE WATTS PER HEARTBEAT.',
                  'WATTS PER BEAT', '9 SIMILAR RIDES'),
    'in_line': ('CONSISTENT', 'CONSISTENT: 112 W VS 108 W.', 'RIGHT IN LINE', '9 SIMILAR RIDES'),
    'resistance_low': ('RESISTANCE LOW', 'RESISTANCE UNDER THE CALLOUT 28% OF THE WORK: TURN IT UP.', 'TURN IT UP',
                       'VS THE CALLOUTS'),
    'cadence_low': ('CADENCE LOW', 'CADENCE UNDER THE CALLOUT 37% OF THE WORK: PICK IT UP.', 'PICK IT UP',
                    'VS THE CALLOUTS'),
    'pace_low': ('UNDER PACE', 'UNDER THE PACE TARGET 42% OF THE TIME: PUSH, OR DROP A LEVEL.', 'PUSH THE PACE',
                 'VS THE CALLOUTS'),
    'go_up_lighter': ('GO UP A WEIGHT', 'GO UP A WEIGHT ON BENT OVER ROW: 20LB VS 30LB. REPS +35%.',
                      'BENT OVER ROW', 'VS PAST CLASSES'),
    'go_up_streak': ('GO UP: HEAVY', 'GO UP FROM 40LB ON HEAVY: 3 CLASSES IN A ROW OVER TARGET.', 'FROM 40LB',
                     'VS PAST CLASSES'),
    'went_heavier': ('HEAVIER: KEEP', 'HEAVIER ON BENT OVER ROW: 50LB VS 40LB. EVERY TARGET HIT.',
                     'BENT OVER ROW', 'VS PAST CLASSES'),
    'missed_targets': ('DROP A WEIGHT', 'SHORT ON 3 OF 9 SETS, MOSTLY BENT OVER ROW: DROP A WEIGHT.',
                       '3 OF 9 SHORT', 'VS PAST CLASSES'),
    'effort_high': ('HARDEST BY HR', 'HARDEST RIDE OF YOUR LAST 12 BY HEART RATE.', 'STRIVE PER MIN',
                    'VS 12 SIMILAR'),
    'effort_low': ('EASIEST BY HR', 'EASIEST RIDE OF YOUR LAST 5 BY HEART RATE.', 'STRIVE PER MIN',
                   '5 SIMILAR RIDES'),
}
MOVEMENT_REASON = ('go_up_lighter', 'went_heavier')


@pytest.mark.parametrize('code', sorted(SHOWN))
def test_every_code_gives_a_view_with_the_planned_wording(code):
    view = board_view(code, SHOWN[code])
    assert (view['headline'], view['sentence'], view['reason'], view['footer']) == EXPECTED[code]
    assert view['code'] == code
    # The comparing insights put their figures on a line of their own, each with its unit.
    figures = {'output_down': '124 W VS 188 W', 'output_up': '205 W VS 180 W', 'in_line': '112 W VS 108 W',
               'go_up_lighter': '20LB VS 30LB', 'went_heavier': '50LB VS 40LB'}
    if code in figures:
        assert figures[code] in view['lines64']
    else:
        assert view['lines64'] == wrap(view['sentence'])
    assert sum(view['pages32'], []) == view['lines64']


def test_colours_follow_the_direction():
    colour = {code: tuple(board_view(code, facts)['colour']) for code, facts in SHOWN.items()}
    amber, green, red = (255, 140, 0), (60, 220, 110), (230, 40, 40)
    assert {c for c, rgb in colour.items() if rgb == amber} == {
        'output_down', 'missed_targets', 'resistance_low', 'cadence_low', 'pace_low'}
    assert {c for c, rgb in colour.items() if rgb == green} == {
        'output_up', 'go_up_lighter', 'go_up_streak', 'went_heavier', 'effort_low'}
    assert colour['effort_high'] == red and colour['in_line'] == (200, 205, 215)


def test_figures():
    assert board_view('output_down', SHOWN['output_down'])['figure'] == {
        'kind': 'bars', 'today': 124, 'usual': 188, 'today_text': '124', 'usual_text': '188', 'unit': 'W'}
    assert board_view('effort_high', SHOWN['effort_high'])['figure'] == {
        'kind': 'bars', 'today': 0.98, 'usual': 0.76, 'today_text': '0.98', 'usual_text': '0.76', 'unit': ''}
    assert board_view('went_heavier', SHOWN['went_heavier'])['figure']['unit'] == 'LB'
    assert board_view('pace_low', SHOWN['pace_low'])['figure'] == {'kind': 'share', 'pct': 42}
    assert board_view('go_up_streak', SHOWN['go_up_streak'])['figure'] == {
        'kind': 'blocks', 'total': 3, 'lit': 3, 'label': 'IN A ROW'}
    assert board_view('missed_targets', SHOWN['missed_targets'])['figure'] == {
        'kind': 'blocks', 'total': 9, 'lit': 3, 'label': ''}
    many = board_view('missed_targets', {'missed': 20, 'sets': 60, 'movement': 'Row'})['figure']
    assert (many['total'], many['lit']) == (MAX_BLOCKS, 10)


def test_wording_variants():
    foot_facts = {'value': 3.6, 'usual': 4.07, 'unit': 'mph', 'foot': True, 'noun': 'run', 'n': 9, 'real': 9,
                  'reason': 'cost_more'}
    view = board_view('output_down', foot_facts)
    assert view['headline'] == 'PACE DOWN' and view['reason'] == 'LESS PER BEAT'
    # Too long for VS YOUR TYPICAL and both units: the lead alone, and MPH once.
    assert view['sentence'] == 'PACE DOWN: 3.6 VS 4.1 MPH. HR NOT LOWER: LESS PER HEARTBEAT.'
    assert view['lines64'] == ['PACE DOWN', '3.6 VS 4.1 MPH', 'HR NOT LOWER:', 'LESS PER', 'HEARTBEAT.']
    assert view['figure']['unit'] == 'MPH' and view['figure']['usual_text'] == '4.1'
    assert view['footer'] == '9 SIMILAR RUNS'
    plain = board_view('output_down', BIKE)
    assert plain['reason'] is None and plain['sentence'] == 'OUTPUT DOWN VS YOUR TYPICAL: 124 W VS 188 W.'
    assert board_view('output_up', {**BIKE, 'reason': None})['reason'] is None
    wide = board_view('in_line', {**BIKE, 'value': 150, 'usual': 170, 'close': False})
    assert (wide['headline'], wide['sentence'], wide['reason']) == (
        'IN YOUR RANGE', 'IN YOUR TYPICAL RANGE: 150 W VS 170 W.', '20 W UNDER')
    # The figures get a line of their own, each with its unit; the reason says by how much, not the headline again.
    assert wide['lines64'] == ['IN YOUR TYPICAL', 'RANGE', '150 W VS 170 W'] and wide['pages32'] == [wide['lines64']]
    assert board_view('in_line', SHOWN['in_line'])['lines64'] == ['CONSISTENT', '112 W VS 108 W']
    assert board_view('in_line', {**BIKE, 'value': 185, 'usual': 170, 'close': False})['reason'] == '15 W OVER'
    big = board_view('in_line', {**BIKE, 'value': 1234, 'usual': 1100, 'close': False})
    assert big['lines64'][-1] == '1234 VS 1100 W'  # both units would pass 15 characters
    run = board_view('in_line', {**BIKE, 'value': 4.5, 'usual': 4.1, 'unit': 'mph', 'foot': True, 'close': False})
    assert run['lines64'][-1] == '4.5 VS 4.1 MPH' and run['reason'] == '0.4 MPH OVER'
    level = board_view('in_line', {**BIKE, 'value': 12.5, 'usual': 12.5, 'unit': 'mph', 'close': False})
    assert level['reason'] == 'RIGHT IN LINE'
    # Bike fill-ins: the closest rides, not similar ones.
    assert board_view('output_down', {**BIKE, 'n': 5, 'real': 3})['footer'] == '5 CLOSEST RIDES'
    assert board_view('output_down', {**BIKE, 'noun': 'class'})['footer'] == 'VS 9 SIMILAR'
    assert board_view('output_down', {**BIKE, 'noun': 'bootcamp'})['footer'] == 'VS 9 SIMILAR'
    category = board_view('went_heavier', {**SHOWN['went_heavier'], 'on_movement': False})
    assert category['sentence'].startswith('HEAVIER ON HEAVY WEIGHTS: 50LB VS 40LB')
    assert category['reason'] == 'HEAVY WEIGHTS'
    lighter_category = board_view('go_up_lighter', {**SHOWN['go_up_lighter'], 'on_movement': False})
    assert lighter_category['reason'] == 'BENT OVER ROW'


def test_a_long_movement_drops_the_clause_then_the_vs_then_itself():
    def sentence(code, name):
        return board_view(code, {**SHOWN[code], 'movement': name})['sentence']
    for name in ('Wide Grip Bent Over Row', 'Seated Overhead Press'):
        assert sentence('go_up_lighter', name).endswith(': 20LB VS 30LB. REPS +35%.')
    assert sentence('go_up_lighter', LONG).endswith('PULSE: 20LB VS 30LB.')
    assert sentence('go_up_lighter', 'Single Arm Dumbbell Overhead Press').endswith('PRESS: 20LB VS 30LB.')
    assert sentence('go_up_lighter', LONG + ' Hold Squat') == 'GO UP A WEIGHT: 20LB VS 30LB.'
    assert sentence('went_heavier', LONG).endswith('PULSE: 50LB VS 40LB.')
    assert sentence('went_heavier', 'Single Arm Dumbbell Overhead Press').endswith('PRESS: 50LB VS 40LB.')
    assert sentence('went_heavier', LONG + ' Hold Squat') == 'WENT HEAVIER: 50LB VS 40LB. KEEP IT.'
    streak = board_view('go_up_streak', {'lb': 100, 'category': 'medium', 'n': 3})
    assert streak['sentence'] == 'GO UP FROM 100LB ON MEDIUM: 3 IN A ROW OVER TARGET.'
    assert board_view('go_up_streak', {'lb': 40, 'category': 'medium', 'n': 3})['sentence'] == (
        'GO UP FROM 40LB ON MEDIUM: 3 CLASSES IN A ROW OVER TARGET.')
    missed = board_view('missed_targets', {'missed': 12, 'sets': 30, 'movement': LONG})
    assert missed['sentence'] == 'SHORT ON 12 OF 30 SETS: DROP A WEIGHT.'


def test_a_strong_workout_says_same_heart_only_when_it_was():
    def last(facts):
        view = board_view('output_up', {**SHOWN['output_up'], **facts})
        return view['lines64'][3:], view['reason']
    assert last({}) == (['MORE WATTS PER', 'HEARTBEAT.'], 'WATTS PER BEAT')
    assert last({'same_hr': False}) == (['MORE WATTS PER', 'HEARTBEAT.'], 'WATTS PER BEAT')
    assert last({'same_hr': True}) == (['SAME HEART,', 'MORE POWER.'], 'SAME HEART')
    run = {'unit': 'mph', 'value': 4.5, 'usual': 4.1, 'foot': True, 'noun': 'run'}
    assert last(run)[0] == ['MORE SPEED PER', 'HEARTBEAT.'] and last(run)[1] == 'SPEED PER BEAT'
    assert last({**run, 'same_hr': True}) == (['SAME HEART,', 'MORE SPEED.'], 'SAME HEART')
    # Only an efficient workout gets either line.
    assert board_view('output_up', {**SHOWN['output_up'], 'reason': None, 'same_hr': True})['reason'] is None


def test_wrap_cuts_a_word_longer_than_a_line():
    assert wrap('A ' + 'X' * 20 + ' B') == ['A', 'X' * 15, 'XXXXX B']
    assert wrap('Y' * 16) == ['Y' * 15, 'Y']
    assert wrap('') == []


WORST = [
    ('output_down', {**BIKE, 'value': 9999, 'usual': 9999, 'noun': 'bootcamp', 'reason': 'cost_more', 'n': 99,
                     'real': 12}),
    ('output_down', {**BIKE, 'value': 12.5, 'usual': 12.5, 'unit': 'mph', 'foot': True, 'noun': 'bootcamp',
                     'reason': 'easier', 'n': 99, 'real': 99}),
    ('output_up', {**BIKE, 'value': 9999, 'usual': 9999, 'noun': 'bootcamp', 'reason': 'efficient', 'n': 99}),
    ('output_up', {**BIKE, 'value': 12.5, 'usual': 12.5, 'unit': 'mph', 'foot': True, 'noun': 'class',
                   'reason': 'efficient', 'n': 99}),
    ('in_line', {**BIKE, 'value': 12.5, 'usual': 12.5, 'unit': 'mph', 'foot': True, 'noun': 'bootcamp',
                 'close': False, 'n': 99}),
    ('resistance_low', {'pct': 100}),
    ('cadence_low', {'pct': 100}),
    ('pace_low', {'pct': 100}),
    ('go_up_streak', {'lb': 100, 'category': 'medium', 'n': 3}),
    ('went_heavier', {'movement': LONG, 'lb': 100, 'usual': 95, 'category': 'medium', 'on_movement': True}),
    ('went_heavier', {'movement': 'Row', 'lb': 100, 'usual': 95, 'category': 'medium', 'on_movement': False}),
    ('go_up_lighter', {'movement': LONG, 'lb': 100, 'usual': 105, 'pct': 100}),
    ('go_up_lighter', {'movement': 'Wide Grip Bent Over Row', 'lb': 100, 'usual': 105, 'pct': 100}),
    ('go_up_lighter', {'movement': 'Single Arm Dumbbell Overhead Press', 'lb': 100, 'usual': 105, 'pct': 100}),
    ('go_up_lighter', {'movement': LONG + ' Hold Squat', 'lb': 100, 'usual': 105, 'pct': 100}),
    ('went_heavier', {'movement': LONG + ' Hold Squat', 'lb': 100, 'usual': 95, 'on_movement': True}),
    ('missed_targets', {'missed': 99, 'sets': 99, 'movement': 'Wide Grip Bent Over Row'}),
    ('effort_high', {'n': 99, 'noun': 'bootcamp', 'rate': 9.99, 'usual_rate': 9.99}),
    ('effort_low', {'n': 99, 'noun': 'class', 'rate': 0.01, 'usual_rate': 9.99}),
]


@pytest.mark.parametrize('height', (64, 32))
def test_every_line_fits_the_stats_font(height):
    initialize_fonts(height)
    font = loaded_fonts['stats']
    for code, facts in list(SHOWN.items()) + WORST:
        view = board_view(code, facts)
        assert view, code
        # Nothing is cut: the board's lines carry every word of the sentence (laid out in lines, or wrapped).
        def words(text):
            return text.replace(':', ' ').replace('.', ' ').split()
        assert words(' '.join(view['lines64'])) == words(view['sentence']), view['sentence']
        assert len(view['lines64']) <= LINES_64
        assert 1 <= len(view['pages32']) <= 2 and all(1 <= len(page) <= LINES_32 for page in view['pages32'])
        shown = view['lines64'] + [view['headline'], view['footer']]
        if code not in MOVEMENT_REASON and view['reason']:
            shown.append(view['reason'])
        for line in shown:
            assert len(line) <= LINE_MAX and get_text_width(font, line) <= 60, (code, line)


def test_hidden_unknown_and_missing_facts_give_none():
    for code in HIDDEN_CODES:
        assert board_view(code, {'n': 3, 'noun': 'ride'}) is None
    assert board_view('made_up', {}) is None
    assert board_view('output_down', {}) is None
    assert board_view('output_down', None) is None
    # A version 2 fact set (no group size) shows nothing rather than a wrong footer.
    assert board_view('output_down', {'value': 1, 'usual': 2, 'unit': 'W', 'foot': False, 'noun': 'ride'}) is None
    assert board_view('effort_high', {'n': 5, 'value': 20}) is None
    assert board_view('go_up_streak', {'lb': 40}) is None
    assert board_view('pace_low', {'pct': 'many'}) is None


def test_board_insights_keeps_order_and_stops_at_two():
    messages = [('freestyle', 'x', {}), ('too_few', 'y', {'n': 1}), ('cadence_low', 'z', {'pct': 40}),
                ('output_down', 'a', {}), ('resistance_low', 'w', {'pct': 30}), ('pace_low', 'v', {'pct': 50})]
    assert MAX_BOARD_INSIGHTS == 2
    assert [v['code'] for v in board_insights(messages)] == ['cadence_low', 'resistance_low']
    assert [v['code'] for v in board_insights(messages, limit=3)] == ['cadence_low', 'resistance_low', 'pace_low']
    assert board_insights([('nothing', 'x', {'n': 5}), ('no_tracker', 'y', {})]) == []
    assert board_insights([]) == []


def test_real_insights_make_views_from_their_own_facts():
    view = board_insights(run_bike(124, [188] * 5))[0]
    assert view['sentence'] == 'OUTPUT DOWN VS YOUR TYPICAL: 124 W VS 188 W.' and view['footer'] == '5 SIMILAR RIDES'
    target = foot(0, 3.6)
    view = board_insights(insights(target, [target] + [foot(i, 4.1) for i in range(1, 6)]))[0]
    assert view['headline'] == 'PACE DOWN' and view['figure']['today_text'] == '3.6'
    assert board_insights(lighter())[0]['headline'] == 'GO UP A WEIGHT'
    assert board_insights(heavier())[0]['figure']['today_text'] == '45'
    in_line, hardest = board_insights(effort(20, [10, 11, 12, 13, 14]))
    assert in_line['headline'] == 'CONSISTENT' and in_line['sentence'] == 'CONSISTENT: 100 W VS 100 W.'
    assert hardest['sentence'] == 'HARDEST RIDE OF YOUR LAST 5 BY HEART RATE.'
    assert (hardest['figure']['today_text'], hardest['figure']['usual_text']) == ('1.00', '0.60')
    t = ride(0, 100, target_under={'resistance': 28})
    assert board_insights(insights(t, [t]))[0]['figure'] == {'kind': 'share', 'pct': 28}
    t = ride(0, 100)
    assert board_insights(insights(t, [t])) == []


# --- Instructor milestones: words only, gold ---

@pytest.mark.parametrize('n, text', [(1, '1ST'), (2, '2ND'), (3, '3RD'), (4, '4TH'), (10, '10TH'), (11, '11TH'),
                                     (12, '12TH'), (13, '13TH'), (21, '21ST'), (22, '22ND'), (23, '23RD'),
                                     (100, '100TH'), (101, '101ST'), (102, '102ND'), (103, '103RD'),
                                     (111, '111TH'), (112, '112TH'), (113, '113TH'), (200, '200TH'),
                                     (1000, '1000TH')])
def test_ordinals(n, text):
    from peloton.insight_lines import ordinal
    assert ordinal(n) == text


def milestone(n, name, since='2019-03-02'):
    return board_view('instructor_milestone', {'n': n, 'name': name, 'since': since})


def test_a_round_number_card_and_page():
    view = milestone(200, 'Jess Sims')
    assert view['lines64'] == ['YOUR 200TH', 'CLASS WITH', 'JESS SIMS!']
    assert view['pages32'] == [['YOUR 200TH CLASS', 'WITH JESS SIMS!']]
    assert view['footer'] == 'SINCE MAR 2019' and view['figure'] is None and view['reason'] is None
    assert view['colour'] == [255, 200, 0] and view['highlight'] == ['200TH']
    assert view['sentence'] == 'YOUR 200TH CLASS WITH JESS SIMS!'


def test_a_first_class_card_and_page():
    view = milestone(1, 'Zacharias Niedzwiecki', since=None)
    assert view['lines64'] == ['YOUR FIRST', 'CLASS WITH', 'ZACHARIAS', 'NIEDZWIECKI!']
    assert view['pages32'] == [['YOUR FIRST CLASS', 'WITH ZACHARIAS', 'NIEDZWIECKI!']]
    assert view['footer'] == 'WELCOME!' and view['highlight'] == ['FIRST']
    assert milestone(1, 'Jess Sims')['footer'] == 'WELCOME!'  # a first never says "since"


def test_a_long_name_wraps():
    assert milestone(100, 'Chelsea Jackson Roberts')['lines64'] == ['YOUR 100TH', 'CLASS WITH', 'CHELSEA JACKSON',
                                                                     'ROBERTS!']
    assert milestone(100, 'Chelsea Jackson Roberts')['pages32'] == [['YOUR 100TH CLASS', 'WITH CHELSEA',
                                                                      'JACKSON ROBERTS!']]
    assert milestone(25, 'Leanne Hainsby-Alldis')['lines64'] == ['YOUR 25TH', 'CLASS WITH', 'LEANNE',
                                                                  'HAINSBY-ALLDIS!']


def test_no_date_falls_back_to_a_plain_footer():
    assert milestone(50, 'Jess Sims', since=None)['footer'] == 'KEEP IT UP!'


@pytest.mark.parametrize('facts', [{}, {'n': 0, 'name': 'A'}, {'n': True, 'name': 'A'}, {'n': 5.0, 'name': 'A'},
                                   {'n': 5, 'name': ''}, {'n': 5, 'name': '  '}, {'n': 5, 'name': None},
                                   {'n': 5, 'name': 'A', 'since': 'sometime'},
                                   {'n': 5, 'name': 'A', 'since': '2019-13-01'}])
def test_bad_milestone_facts_give_no_view(facts):
    assert board_view('instructor_milestone', facts) is None


NAMES = ('Chelsea Jackson Roberts', 'Zacharias Niedzwiecki', 'Leanne Hainsby-Alldis', 'Jess Sims', 'Cody Rigsby')
COUNTS = (1, 2, 3, 5, 10, 11, 12, 13, 21, 25, 50, 100, 101, 111, 200, 400, 1000, 1111)


@pytest.mark.parametrize('height', (64, 32))
def test_every_milestone_line_fits_the_stats_font(height):
    initialize_fonts(height)
    font = loaded_fonts['stats']
    for name in NAMES:
        for n in COUNTS:
            view = milestone(n, name)
            assert len(view['pages32']) == 1 or n >= 1000, (name, n)
            if height == 64:
                lines = view['lines64']
                assert len(lines) <= LINES_64
                # the 64x64 card keeps to the usual 15 characters (60 px)
                assert all(len(line) <= LINE_MAX and get_text_width(font, line) <= 60
                           for line in lines + [view['footer']]), (name, n)
            else:
                lines = sum(view['pages32'], [])
                assert all(len(page) <= LINES_32 for page in view['pages32'])
                # the 64x32 page's lines run edge to edge: 16 characters, 64 px
                assert all(len(line) <= EDGE_MAX and get_text_width(font, line) <= 64 for line in lines), (name, n)
            text = ' '.join(lines).replace('CLASS WITH', ' ').replace('YOUR', ' ').replace('CLASS', ' ')
            text = text.replace('WITH', ' ').replace(view['highlight'][0], ' ')
            assert text.split() == (name.upper() + '!').split(), (name, n, lines)


def test_a_name_longer_than_a_line_is_cut_across_lines():
    view = milestone(10, 'Supercalifragilisticexpialidocious Smith')
    assert view['lines64'][2] == 'SUPERCALIFRAGIL' and len(view['lines64']) == 5
