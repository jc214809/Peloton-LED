"""The workout-compare frames on the latest-workout page: card + bars on 64x64, bars + sentence on 64x32."""
import pytest

from display.display import initialize_fonts
from display.ui.last_workout_screen import (GRAPH_FRAME_EXTRA_SECONDS, INSIGHT_KINDS, LastWorkoutScreen,
                                           _draw_insight_frame, detail_hold_seconds, insight_views,
                                           rotating_details)
from peloton.demo import demo_data
from peloton.insight_lines import board_view
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix
from tests.test_insight_lines import SHOWN
from tests.test_workout_graph import demo_ride, demo_strength

GOLD = (255, 200, 0)
AMBER = (255, 140, 0)
GREEN = (60, 220, 110)
RED = (230, 40, 40)
WHITE = (200, 205, 215)   # the insight text colour
GREY = (145, 165, 190)
USUAL_BAR = (20, 50, 140)   # the usual's bar (navy)
DIM = (70, 80, 95)
HEART = (220, 20, 20)
CYCLING = (220, 50, 20)


def view(code, **facts):
    return board_view(code, {**SHOWN[code], **facts})


def with_views(summary, *views):
    return {**summary, 'insights': list(views)}


def ride_with_two():
    return with_views(demo_ride(), view('output_down', reason='easier'), view('effort_high'))


def lit(matrix, colour, rows, columns):
    pixels = matrix.image.load()
    return [(x, y) for y in rows for x in columns if pixels[x, y] == tuple(colour)]


def render_detail(summary, height, kind, index=0, page=None, seconds=0.5):
    """The frame of `kind` (and view `index`, sentence `page`) `seconds` after it comes up."""
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    details = rotating_details(summary, height)
    turn = next(i for i, d in enumerate(details) if d.get('kind') == kind and d.get('index', 0) == index
                and (page is None or d.get('page') == page))
    screen = LastWorkoutScreen()
    screen.on_enter(matrix, summary)
    screen.update(4 + sum(detail_hold_seconds(d, 4) for d in details[:turn]) + seconds)
    assert screen.render(matrix, summary)
    return matrix


def test_the_frames_come_after_the_chart_slides_in_order():
    ride = ride_with_two()
    tall = rotating_details(ride, 64)
    assert [d.get('kind') for d in tall][-6:] == ['graph', 'zones', 'insight_card', 'insight_bars',
                                                 'insight_card', 'insight_bars']
    assert [d['index'] for d in tall[-4:]] == [0, 0, 1, 1]
    assert all(d['label'] == 'insight' and d['value'] == '' for d in tall[-4:])
    short = rotating_details(ride, 32)
    pages = [len(v['pages32']) for v in ride['insights']]
    assert pages == [2, 1]
    assert [(d.get('kind'), d.get('index'), d.get('page')) for d in short][-5:] == [
        ('insight_bars', 0, None), ('insight_words', 0, 0), ('insight_words', 0, 1),
        ('insight_bars', 1, None), ('insight_words', 1, 0)]
    strength = with_views(demo_strength(), view('go_up_lighter'))
    assert [d.get('kind') for d in rotating_details(strength, 64)][-3:] == ['muscles', 'insight_card', 'insight_bars']


def test_at_most_two_views_are_kept():
    ride = with_views(demo_ride(), view('resistance_low'), view('cadence_low'), view('pace_low'))
    assert [v['code'] for v in insight_views(ride)] == ['resistance_low', 'cadence_low']


def _damaged():
    good = view('pace_low')
    return [
        None, 'text', {}, [None], ['text'], [{}],
        [{**good, 'figure': None}], [{**good, 'figure': {'kind': 'pie', 'pct': 3}}],
        [{**good, 'figure': {'kind': 'share', 'pct': 101}}], [{**good, 'figure': {'kind': 'share', 'pct': -1}}],
        [{**good, 'figure': {'kind': 'share', 'pct': True}}], [{**good, 'figure': {'kind': 'share', 'pct': 5,
                                                                                    'unit': 7}}],
        [{**good, 'figure': {'kind': 'bars', 'today': 1, 'usual': 2}}],
        [{**good, 'figure': {'kind': 'blocks', 'total': 3, 'lit': 4}}],
        [{**good, 'figure': {'kind': 'blocks', 'total': 31, 'lit': 1}}],
        [{**good, 'figure': {'kind': 'blocks', 'total': 3.0, 'lit': 1}}],
        [{**good, 'colour': 'amber'}], [{**good, 'colour': [255, 140]}], [{**good, 'colour': [255, 140, 300]}],
        [{**good, 'colour': [True, 0, 0]}], [{**good, 'headline': ''}], [{**good, 'footer': None}],
        [{**good, 'reason': 7}], [{**good, 'lines64': []}], [{**good, 'lines64': ['A'] * 6}],
        [{**good, 'lines64': ['A', 3]}], [{**good, 'pages32': []}], [{**good, 'pages32': [['A']] * 3}],
        [{**good, 'pages32': [['A', 'B', 'C', 'D']]}], [{**good, 'pages32': ['ABC']}],
    ]


@pytest.mark.parametrize('insights', _damaged())
def test_a_damaged_list_is_ignored(insights):
    summary = {**demo_ride(), 'insights': insights}
    assert insight_views(summary) == []
    for height in (32, 64):
        assert rotating_details(summary, height) == rotating_details(demo_ride(), height)


def test_a_damaged_view_is_skipped_and_a_version_2_insight_never_drawn():
    good = view('pace_low')
    assert insight_views({'insights': [{**good, 'colour': None}, good]}) == [good]
    old = {'code': 'output_up', 'lines': ['STRONG RIDE', '205 VS 180 W'], 'facts': {}}
    summary = {**demo_ride(), 'insight': old}
    assert insight_views(summary) == []
    assert rotating_details(summary, 64) == rotating_details(demo_ride(), 64)


def test_every_frame_holds_like_the_chart_slides_and_sizes_the_page():
    for kind in INSIGHT_KINDS:
        assert detail_hold_seconds({'kind': kind}, 4) == 4 + GRAPH_FRAME_EXTRA_SECONDS
        assert detail_hold_seconds({'kind': kind}, 0) == 0
    data = demo_data()

    class Dash:
        pending_milestones = pending_discipline_milestones = lambda self, *_: []
        should_celebrate_pr = lambda self, *_: False

    display = {'rotation': ['latest_workouts'], 'last_workout_detail_interval': 4.0, 'screen_durations': {}}
    for height, frames in ((64, 4), (32, 5)):
        snapshot = {'me': data['me'], 'summaries': [ride_with_two()], 'totals': {}, 'weekly_progress': {}}
        plain = build_rotation_pages({**snapshot, 'summaries': [demo_ride()]}, Dash(), display, 'R', height)
        shown = build_rotation_pages(snapshot, Dash(), display, 'R', height)
        assert shown[0][2] == pytest.approx(plain[0][2] + frames * (4 + GRAPH_FRAME_EXTRA_SECONDS))


def assert_no_heart_row(matrix):
    assert not lit(matrix, HEART, range(matrix.height - 8, matrix.height), range(12))


def test_64_card_layout():
    matrix = render_detail(ride_with_two(), 64, 'insight_card')
    assert lit(matrix, GOLD, [2], range(3, 8)) and lit(matrix, GOLD, range(2, 10), range(11, 50))  # bulb, INSIGHT
    assert lit(matrix, GREY, range(3, 10), range(50, 63))                    # 1/2
    assert len(lit(matrix, CYCLING, [12], range(64))) == 60                   # the discipline rule, 2-61
    assert not lit(matrix, CYCLING, range(0, 12), range(64))                  # no discipline title
    assert lit(matrix, WHITE, range(14, 50), range(64))                       # the sentence ...
    assert lit(matrix, AMBER, range(14, 50), range(64))                       # ... numbers in the insight's colour
    assert not lit(matrix, CYCLING, range(14, 50), range(64))                 # (not the discipline's)
    assert lit(matrix, GREY, range(54, 62), range(64))                        # 9 SIMILAR RIDES
    assert_no_heart_row(matrix)
    single = render_detail(with_views(demo_ride(), view('pace_low')), 64, 'insight_card')
    assert not lit(single, GREY, range(3, 10), range(50, 63))                 # one insight: no 1/2


def test_64_bars_layout():
    matrix = render_detail(ride_with_two(), 64, 'insight_bars')
    assert lit(matrix, AMBER, range(14, 23), range(64))                       # OUTPUT DOWN
    assert len(lit(matrix, AMBER, [35], range(64))) >= 30                     # today's bar, rows 34-37
    assert len(lit(matrix, USUAL_BAR, [48], range(64))) == 60                      # the usual's, full width
    assert lit(matrix, WHITE, range(54, 62), range(64))                       # AN EASIER DAY
    assert not lit(matrix, CYCLING, range(0, 12), range(64))
    assert_no_heart_row(matrix)
    hardest = render_detail(ride_with_two(), 64, 'insight_bars', index=1)
    assert len(lit(hardest, RED, [35], range(64))) == 60                      # today is the larger
    assert lit(hardest, GREY, range(3, 10), range(50, 63))                    # 2/2


def test_32_bars_and_words_layout():
    bars = render_detail(ride_with_two(), 32, 'insight_bars')
    assert lit(bars, GOLD, [0], range(1, 6))                                  # the bulb at (1, 0)
    assert lit(bars, AMBER, range(0, 7), range(9, 64))                        # headline
    assert len(lit(bars, AMBER, [11], range(0, 42))) >= 20                    # today, rows 9-13 from x 1
    assert len(lit(bars, USUAL_BAR, [19], range(0, 42))) == 41                     # usual, 40 px from x 1
    assert lit(bars, AMBER, range(7, 14), range(50, 64))                      # 124 on the right
    assert lit(bars, WHITE, range(24, 31), range(64))                         # reason on baseline 30
    assert not lit(bars, CYCLING, range(32), range(64))                       # no title, no rule
    assert_no_heart_row(bars)
    first = render_detail(ride_with_two(), 32, 'insight_words', page=0)
    second = render_detail(ride_with_two(), 32, 'insight_words', page=1)
    for words in (first, second):
        assert lit(words, GOLD, range(0, 7), range(9, 40))                    # INSIGHT
        assert lit(words, GREY, range(0, 7), range(50, 64))                   # 1/2, 2/2
        assert len(lit(words, CYCLING, [8], range(64))) == 64                 # the rule on row 8
        assert lit(words, WHITE, range(10, 31), range(64))
        assert_no_heart_row(words)
    assert lit(first, AMBER, range(10, 31), range(64))                        # 124 and 188, the insight's colour
    assert not lit(first, CYCLING, range(10, 31), range(64))
    assert first.image.tobytes() != second.image.tobytes()
    one_page = render_detail(ride_with_two(), 32, 'insight_words', index=1)
    assert not lit(one_page, GREY, range(0, 7), range(50, 64))


@pytest.mark.parametrize('height', [32, 64])
def test_share_bar_frame(height):
    matrix = render_detail(with_views(demo_ride(), view('resistance_low')), height, 'insight_bars')
    if height == 64:
        assert lit(matrix, AMBER, [38], range(2, 19)) and lit(matrix, DIM, [38], range(19, 62))
        assert lit(matrix, GREY, range(26, 33), range(64)) and lit(matrix, GREY, range(43, 50), range(64))
    else:
        assert lit(matrix, AMBER, range(11, 19), range(1, 12)) and lit(matrix, DIM, range(11, 19), range(13, 42))
        assert lit(matrix, AMBER, range(11, 18), range(48, 64))               # 28%
    assert lit(matrix, WHITE, range(height - 8, height), range(64))           # TURN IT UP
    empty = render_detail(with_views(demo_ride(), view('resistance_low', pct=0)), height, 'insight_bars')
    bar_rows = range(35, 42) if height == 64 else range(11, 19)
    assert not lit(empty, AMBER, bar_rows, range(0, 42)) and lit(empty, DIM, bar_rows, range(0, 42))


@pytest.mark.parametrize('height', [32, 64])
def test_blocks_frames(height):
    strength = with_views(demo_strength(), view('go_up_streak'), view('missed_targets', sets=6, missed=2))
    streak = render_detail(strength, height, 'insight_bars')
    missed = render_detail(strength, height, 'insight_bars', index=1)
    top = 34 if height == 64 else 11
    size = 7 if height == 64 else 5
    assert len(lit(streak, GREEN, [top + 1], range(64))) == 3 * size
    assert len(lit(streak, GREEN, [top + size], range(64))) == 0
    assert len(lit(missed, AMBER, [top + 1], range(64))) == 2 * size   # the missed sets
    assert len(lit(missed, DIM, [top + 1], range(64))) == 4 * size
    if height == 64:
        assert lit(streak, GREY, range(44, 51), range(64))                    # 3 IN A ROW
    else:
        assert min(x for x, _ in lit(streak, GREEN, [top], range(64))) == 4
    # More sets take smaller blocks, never wider than the panel.
    for sets in (9, 20, 30):
        frame = render_detail(with_views(demo_strength(), view('missed_targets', sets=sets, missed=4)),
                              height, 'insight_bars')
        assert len(lit(frame, AMBER, [top], range(64))) + len(lit(frame, DIM, [top], range(64))) >= sets
        assert not lit(frame, DIM, [top], [63])


def test_a_headline_too_wide_for_32_rows_keeps_its_first_word():
    bootcamp = with_views(demo_ride(), view('output_up', noun='bootcamp'))
    assert bootcamp['insights'][0]['headline'] == 'STRONG BOOTCAMP'
    short = render_detail(bootcamp, 32, 'insight_bars')
    assert max(x for x, _ in lit(short, GREEN, range(0, 7), range(64))) < 50
    tall = render_detail(bootcamp, 64, 'insight_bars')
    assert lit(tall, GREEN, range(14, 23), range(64))


@pytest.mark.parametrize('height', [32, 64])
def test_a_long_movement_reason_scrolls_under_blank_margins(height):
    summary = with_views(demo_strength(), view('go_up_lighter', movement='Wide Grip Bent Over Row'))
    frames = [render_detail(summary, height, 'insight_bars', seconds=t) for t in (0.1, 2.0, 4.5)]
    assert len({f.image.tobytes() for f in frames}) == 3
    rows = range(height - 8, height)
    for frame in frames:
        assert not lit(frame, WHITE, rows, [0, 1, 62, 63])
        assert lit(frame, WHITE, rows, range(2, 62))
    # Held at the start, then at the end.
    assert (render_detail(summary, height, 'insight_bars', seconds=0.1).image.tobytes()
            == render_detail(summary, height, 'insight_bars', seconds=0.3).image.tobytes())
    assert (render_detail(summary, height, 'insight_bars', seconds=4.5).image.tobytes()
            == render_detail(summary, height, 'insight_bars', seconds=4.9).image.tobytes())


def test_a_short_reason_does_not_scroll():
    for height in (32, 64):
        summary = ride_with_two()
        assert (render_detail(summary, height, 'insight_bars', seconds=0.1).image.tobytes()
                == render_detail(summary, height, 'insight_bars', seconds=4.5).image.tobytes())


@pytest.mark.parametrize('height', [32, 64])
def test_the_other_slides_are_unchanged_by_the_insights(height):
    for plain, shown in ((demo_ride(), ride_with_two()),
                         (demo_strength(), with_views(demo_strength(), view('go_up_lighter')))):
        details = rotating_details(plain, height)
        assert rotating_details(shown, height)[:len(details)] == details
        times = [0.5] + [4.5 + sum(detail_hold_seconds(d, 4) for d in details[:turn]) for turn in
                         range(len(details))]
        for seconds in times:
            frames = []
            for summary in (plain, shown):
                matrix = ImageMatrix(height=height)
                initialize_fonts(height)
                screen = LastWorkoutScreen()
                screen.on_enter(matrix, summary)
                screen.update(seconds)
                screen.render(matrix, summary)
                frames.append(matrix.image.tobytes())
            assert frames[0] == frames[1], seconds


def test_a_frame_for_a_missing_view_draws_nothing():
    matrix = ImageMatrix(height=64)
    initialize_fonts(64)
    detail = {'kind': 'insight_card', 'index': 2}
    assert not _draw_insight_frame(matrix, ride_with_two(), 'Cycling', detail, 0, 5)
    assert not _draw_insight_frame(matrix, ride_with_two(), 'Cycling', {**detail, 'index': 'x'}, 0, 5)


def test_the_demo_shows_the_frames_only_with_the_switch_on():
    from peloton.dashboard import Dashboard
    off = Dashboard('unused', {}, demo=True).snapshot()['summaries']
    on = Dashboard('unused', {'workout_insights': True}, demo=True).snapshot()['summaries']
    assert not any('insights' in s for s in off)
    shown = {s['workout_id']: [v['code'] for v in insight_views(s)] for s in on if 'insights' in s}
    assert shown == {'demo-cycling': ['output_down', 'effort_high'],
                     'demo-strength': ['go_up_lighter', 'go_up_streak']}


@pytest.mark.parametrize('height', [32, 64])
def test_the_word_after_a_colon_sits_closer(height):
    from display.display import loaded_fonts
    from display.display import get_text_width
    from display.ui.last_workout_screen import COLON_GAP_TRIM, _centred, _words_width
    initialize_fonts(height)
    font = loaded_fonts['stats']
    assert _words_width(font, 'GO UP: HEAVY') == get_text_width(font, 'GO UP: HEAVY') - COLON_GAP_TRIM
    assert _words_width(font, 'A: B: C') == get_text_width(font, 'A: B: C') - 2 * COLON_GAP_TRIM

    def gaps(text):
        matrix = ImageMatrix(height=height)
        _centred(matrix, font, 7, WHITE, text)
        columns = [x for x, _ in lit(matrix, WHITE, range(9), range(64))]
        filled = sorted(set(columns))
        return [b - a - 1 for a, b in zip(filled, filled[1:]) if b - a > 2]

    assert gaps('A B') == [5]           # between two words
    assert gaps('A: B') == [2, 3]       # before the colon's dot, then 3 to the next word (was 6)


def test_64_bars_write_weights_as_one_word():
    from display.display import get_text_width, loaded_fonts
    strength = with_views(demo_strength(), view('go_up_lighter'))
    matrix = render_detail(strength, 64, 'insight_bars')
    font = loaded_fonts['stats']
    # 20LB right-aligned at 62: its first column is where a 4-character word starts.
    start = 62 - get_text_width(font, '20LB')
    assert min(x for x, _ in lit(matrix, GREEN, range(26, 33), range(40, 64))) == start
    ride = render_detail(ride_with_two(), 64, 'insight_bars')
    assert min(x for x, _ in lit(ride, AMBER, range(26, 33), range(30, 64))) == 62 - get_text_width(font, '124 W')
