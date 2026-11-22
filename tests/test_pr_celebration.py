import pytest

import display.ui.pr_celebration as pr
from display.display import initialize_fonts, loaded_fonts
from display.ui.celebration_screen import INTRO_SECONDS, TROPHY_MID
from display.ui.pr_celebration import CARD_HOLD_SECONDS, PrCelebrationScreen, fmt_time, pr_page_seconds, pr_turns
from scripts.render_demo import ImageMatrix

GOLD, WHITE, GREEN, BLUE = (255, 215, 0), (255, 255, 255), (40, 220, 90), (0, 120, 255)
TROPHY_COLORS = {(230, 170, 0), (255, 235, 120), (255, 255, 230)}
RUNNING = (30, 220, 90)

# Joel's first Vision Tread run, 2026-11-22: 20 min Walk + Run, output 180 kJ, 1K in 10:33, 1 mile in 16:45.
TREAD_RUN = {
    'workout_id': 'defd6cbe',
    'is_pr': True,
    'is_output_pr': True,
    'total_output_kj': 180.3,
    'duration_min': 20,
    'discipline': 'Running',
    'best_times': [{'label': '1K', 'seconds': 633.0}, {'label': '1 MILE', 'seconds': 1005.0}],
}
# The largest the card has to hold, on both heights.
LARGEST = [
    {
        'is_pr': True,
        'is_output_pr': True,
        'total_output_kj': 2105,
        'previous_best_kj': 1980,
        'duration_min': 60,
        'discipline': 'Tread Bootcamp',
    },
    {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 1512, 'duration_min': 120, 'discipline': 'Outdoor Walking'},
    {'is_pr': True, 'is_splits_pr': True, 'row_split_sec_per_500m': 125, 'duration_min': 30, 'discipline': 'Row Bootcamp'},
    {
        'is_pr': True,
        'discipline': 'Bike Bootcamp',
        'best_times': [
            {'label': 'MARATHON', 'seconds': 17999},
            {'label': 'HALF MARATHON', 'seconds': 7999},
            {'label': '10K', 'seconds': 3895},
            {'label': '1 MILE', 'seconds': 1005},
        ],
    },
    {'is_pr': True, 'discipline': 'Tread Bootcamp', 'duration_min': 120},
]


def _render(summary, elapsed, height=64, detail_interval=4.0, confetti=True, monkeypatch=None):
    if not confetti:
        monkeypatch.setattr(pr, 'draw_confetti', lambda matrix, elapsed: None)
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    screen = PrCelebrationScreen(detail_interval=detail_interval)
    screen.on_enter(matrix, summary)
    screen.update(elapsed)
    assert screen.render(matrix, summary)
    return matrix.image.load()


def _turn(index, detail_interval=4.0, into=0.5):
    """elapsed for `into` seconds into turn `index`."""
    return INTRO_SECONDS + index * (detail_interval + CARD_HOLD_SECONDS) + into


def _points(pixels, color, height):
    return {(x, y) for y in range(height) for x in range(64) if pixels[x, y] == color}


def test_turns_list_every_record_the_workout_broke_output_first():
    turns = pr_turns(TREAD_RUN)
    assert [(heads[0], value) for heads, value, _ in turns] == [('OUTPUT PR', '180 KJ'), ('1K BEST', '10:33'), ('1 MILE BEST', '16:45')]
    assert turns[0][2] == [(BLUE, ['20 MIN CLASS', '20 MIN'])]
    assert turns[1][2] == [(BLUE, ['BEST TIME'])]
    assert turns[2][0] == ['1 MILE BEST', '1 MILE']
    splits = pr_turns({'is_pr': True, 'is_splits_pr': True, 'row_split_sec_per_500m': 128, 'duration_min': 30})
    assert [(h[0], v) for h, v, _ in splits] == [('SPLITS PR', '2:08/500')]
    assert pr_turns({'is_pr': True, 'best_times': [{'label': 'Half Marathon', 'seconds': 7999}]})[0][0] == [
        'HALF MARATHON BEST',
        'HALF MARATHON',
        'HALF',
    ]
    # A PR flag without a usable value still celebrates, rather than crashing.
    assert pr_turns({'is_pr': True, 'is_output_pr': True}) == [(['NEW PR'], '', [])]
    assert pr_turns({'is_pr': False}) == [] and pr_turns({}) == []


def test_output_turn_shows_the_gain_then_the_class_length():
    def gain(summary):
        subs = pr_turns({'is_pr': True, 'is_output_pr': True, 'duration_min': 30, **summary})[0][2]
        return (subs[0][1][0] if subs[0][0] == GREEN else None), pr_turns({'is_pr': True, 'is_output_pr': True, **summary})[0][1]

    assert gain({'total_output_kj': 412.4, 'previous_best_kj': 398}) == ('+14 KJ', '412 KJ')
    # Joel's real 20 min row PR: 150.9 kJ beat 150.1 kJ.
    assert gain({'total_output_kj': 150.9, 'previous_best_kj': 150.1}) == ('+0.8 KJ', '151 KJ')
    # Jen's real 5 min ride: the graph rounds 25.4 kJ to 25, which would hide the gain.
    assert gain({'total_output_kj': 25.0, 'total_work_kj': 25.4, 'previous_best_kj': 25.0}) == ('+0.4 KJ', '25 KJ')
    # The app's Total Output (189 kJ), not round(188.5), which Python sends to the even 188; the gain rounds.
    assert gain({'total_output_kj': 189.0, 'total_work_kj': 188.5, 'previous_best_kj': 181.9}) == ('+7 KJ', '189 KJ')
    assert gain({'total_output_kj': 2105, 'previous_best_kj': 980}) == ('+1,125 KJ', '2,105 KJ')
    assert gain({'total_output_kj': 412}) == (None, '412 KJ')


def test_damaged_best_times_are_skipped():
    """The cache can hold anything."""
    summary = {
        'is_pr': True,
        'best_times': [
            None,
            {'label': 3},
            {'label': ' '},
            {'label': '5K', 'seconds': True},
            {'label': '5K', 'seconds': -1},
            {'label': ' 5k ', 'seconds': 1500},
        ],
    }
    assert [(h[0], v) for h, v, _ in pr_turns(summary)] == [('5K BEST', '25:00')]
    assert pr_turns({'is_pr': True, 'best_times': 'oops'}) == [(['NEW PR'], '', [])]


@pytest.mark.parametrize('seconds, text', [(633.0, '10:33'), (1005, '16:45'), (59.6, '1:00'), (3895, '1:04:55'), (17999, '4:59:59')])
def test_best_times_read_as_the_app_shows_them(seconds, text):
    assert fmt_time(seconds) == text


def test_non_pr_summary_renders_nothing():
    matrix = ImageMatrix(height=64)
    initialize_fonts(64)
    assert not PrCelebrationScreen().render(matrix, {'is_pr': False})
    assert not PrCelebrationScreen().render(matrix, None)
    assert PrCelebrationScreen(detail_interval=None).detail_interval == 4.0


@pytest.mark.parametrize('height', [64, 32])
def test_trophy_rises_before_the_text(height, monkeypatch):
    pixels = _render(TREAD_RUN, INTRO_SECONDS - 0.1, height, confetti=False, monkeypatch=monkeypatch)
    lit = {pixels[x, y] for y in range(height) for x in range(64)} - {(0, 0, 0)}
    assert lit and lit <= TROPHY_COLORS


def test_64_row_card_reads_discipline_trophy_record_value_class(monkeypatch):
    pixels = _render(TREAD_RUN, _turn(0), confetti=False, monkeypatch=monkeypatch)
    rows = lambda color: {y for _, y in _points(pixels, color, 64)}  # noqa: E731  one-line test helper
    trophy = {y for y in range(64) for x in range(64) if pixels[x, y] in TROPHY_COLORS}
    name, gold, white, blue = rows(RUNNING), rows(GOLD), rows(WHITE), rows(BLUE)
    assert max(name) < min(trophy) and max(trophy) < min(gold - {62}) and max(gold - {62}) < min(white) and max(white) < min(blue)
    # Three records, three dots on the bottom row: the first lit.
    dots = sorted(x for x, y in _points(pixels, GOLD, 64) if y == 62)
    assert len(dots) == 2 and dots[0] < 32


def test_turns_advance_and_the_last_one_holds(monkeypatch):
    def lit_dot(elapsed):
        pixels = _render(TREAD_RUN, elapsed, confetti=False, monkeypatch=monkeypatch)
        return min(x for x, y in _points(pixels, GOLD, 64) if y == 62)

    first, second, third = (lit_dot(_turn(i)) for i in range(3))
    assert first < second < third
    assert lit_dot(_turn(2, into=5.9)) == third == lit_dot(_turn(9))  # a slow frame past the page's end


def test_single_record_card_has_no_dots(monkeypatch):
    pixels = _render({**TREAD_RUN, 'best_times': []}, _turn(0), confetti=False, monkeypatch=monkeypatch)
    assert not {y for _, y in _points(pixels, GOLD, 64)} & {62}


@pytest.mark.parametrize('detail_interval', [2.0, 4.0])
def test_gain_then_class_length_share_the_output_turn(detail_interval, monkeypatch):
    summary = {**TREAD_RUN, 'previous_best_kj': 170}
    half = (detail_interval + CARD_HOLD_SECONDS) / 2
    for height in (64, 32):
        early = _render(summary, _turn(0, detail_interval, 0.1), height, detail_interval, False, monkeypatch)
        late = _render(summary, _turn(0, detail_interval, half + 0.1), height, detail_interval, False, monkeypatch)
        assert _points(early, GREEN, height) and not _points(early, BLUE, height)
        assert _points(late, BLUE, height) and not _points(late, GREEN, height)


def _trophy_cells():
    left, top = pr._SHORT_TROPHY_LEFT, pr._SHORT_TROPHY_TOP
    return {(left + x, top + y) for y, row in enumerate(TROPHY_MID) for x, c in enumerate(row) if c == '#'}


def test_32_row_trophy_is_centred_with_2_px_either_side(monkeypatch):
    pixels = _render(TREAD_RUN, _turn(0), 32, confetti=False, monkeypatch=monkeypatch)
    trophy = {(x, y) for y in range(32) for x in range(64) if pixels[x, y] in TROPHY_COLORS}
    assert trophy == _trophy_cells()
    xs, ys = {x for x, _ in trophy}, {y for _, y in trophy}
    assert min(xs) == 2 and pr._SHORT_TEXT_LEFT == max(xs) + 3
    assert min(ys) == 31 - max(ys)  # as many rows above as below


@pytest.mark.parametrize('summary', [TREAD_RUN, *LARGEST])
def test_32_row_text_stays_on_the_panel_and_off_the_trophy(summary, monkeypatch):
    trophy = _trophy_cells()
    for index in range(len(pr_turns(summary))):
        for into in (0.5, 5.5):
            pixels = _render(summary, _turn(index, into=into), 32, confetti=False, monkeypatch=monkeypatch)
            text = {(x, y) for y in range(32) for x in range(64) if pixels[x, y] not in TROPHY_COLORS | {(0, 0, 0)}}
            assert text, (index, into)
            near = {(x + dx, y + dy) for x, y in trophy for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
            assert not text & near, (summary.get('discipline'), index, into)


@pytest.mark.parametrize('summary', [TREAD_RUN, *LARGEST])
def test_64_row_text_stays_on_the_panel(summary, monkeypatch):
    initialize_fonts(64)
    for heads, value, subs in pr_turns(summary):
        assert any(pr.get_text_width(loaded_fonts['info'], h) <= 62 for h in heads)
        assert pr.get_text_width(loaded_fonts['titles'], value) <= 62
        assert all(any(pr.get_text_width(loaded_fonts['info'], w) <= 62 for w in words) for _, words in subs)
    assert pr.get_text_width(loaded_fonts['info'], summary['discipline'].upper()) <= 62


def test_32_row_lines_centre_beside_the_trophy_and_wide_ones_reach_the_edge():
    initialize_fonts(32)
    info = loaded_fonts['info']
    # 1K BEST: centred in columns 18-63, an even margin each side (to a pixel).
    lit = pr.get_text_width(info, '1K BEST') - 1
    x = pr.short_line_x(info, '1K BEST')
    assert abs((x - pr._SHORT_TEXT_LEFT) - (63 - (x + lit - 1))) <= 1
    # Too wide for the columns: moved left only as far as the edge needs.
    lit = pr.get_text_width(info, 'TREAD BOOTCAMP') - 1
    assert pr.short_line_x(info, 'TREAD BOOTCAMP') + lit == 64


@pytest.mark.parametrize(
    'wordings, expected',
    [
        (['1 MILE BEST', '1 MILE'], '1 MILE BEST'),
        (['MARATHON BEST', 'MARATHON'], 'MARATHON'),  # BEST would touch the top of the trophy
        (['HALF MARATHON BEST', 'HALF MARATHON', 'HALF'], 'HALF'),
    ],
)
def test_32_row_headline_falls_back_to_a_wording_that_clears_the_trophy(wordings, expected):
    initialize_fonts(32)
    assert pr.short_wording(loaded_fonts['info'], wordings, pr._SHORT_HEAD)[0] == expected


def test_32_row_nothing_clears_keeps_the_last_wording(monkeypatch):
    initialize_fonts(32)
    monkeypatch.setattr(pr, 'clears_trophy', lambda *a: False)
    assert pr.short_wording(loaded_fonts['info'], ['A LONG ONE', 'SHORT'], pr._SHORT_HEAD)[0] == 'SHORT'


def test_no_discipline_draws_no_name_line(monkeypatch):
    pixels = _render({**TREAD_RUN, 'discipline': None}, _turn(0), 32, confetti=False, monkeypatch=monkeypatch)
    assert not {y for y in range(8) for x in range(64) if pixels[x, y] != (0, 0, 0)}


def _client(pages):
    from unittest.mock import Mock

    client = Mock()
    client.get_workouts_page.side_effect = pages
    return client


def test_preview_finds_newest_completed_pr_across_pages():
    from scripts.preview_pr import find_latest_pr

    client = _client(
        [
            {
                'data': [{'id': 'a', 'status': 'COMPLETE'}, {'id': 'b', 'status': 'IN_PROGRESS', 'is_total_work_personal_record': True}],
                'show_next': True,
            },
            {
                'data': [
                    {'id': 'c', 'status': 'COMPLETE', 'is_total_work_personal_record': True},
                    {'id': 'd', 'status': 'COMPLETE', 'is_total_work_personal_record': True},
                ],
                'show_next': True,
            },
        ]
    )
    workout, pages = find_latest_pr(client, 'u', max_pages=5)
    assert workout['id'] == 'c' and pages == 2
    assert client.get_workouts_page.call_count == 2


@pytest.mark.parametrize(
    'pages,expected_pages',
    [
        ([{'data': [{'id': 'a'}], 'show_next': False}], 1),
        ([{'data': []}], 1),
        ([{'data': [{'id': 'a'}], 'show_next': True}] * 3, 3),
    ],
)
def test_preview_reports_no_pr_without_overrunning_history(pages, expected_pages):
    from scripts.preview_pr import find_latest_pr

    workout, read = find_latest_pr(_client(pages), 'u', max_pages=3)
    assert workout is None and read == expected_pages


def test_preview_rejects_malformed_page():
    from scripts.preview_pr import find_latest_pr

    with pytest.raises(ValueError):
        find_latest_pr(_client([{'data': 'oops'}]), 'u', max_pages=1)


@pytest.mark.parametrize('best_times, turns', [([], 1), (TREAD_RUN['best_times'], 3)])
def test_rotation_gives_the_card_its_entrance_and_a_turn_per_record(best_times, turns):
    from unittest.mock import Mock

    from peloton_led import build_rotation_pages

    dashboard = Mock()
    dashboard.should_celebrate_pr.return_value = True
    summary = {**TREAD_RUN, 'workout_id': 'w', 'best_times': best_times}
    snapshot = {'me': {}, 'summaries': [summary], 'totals': {}, 'status': 'ready'}
    display = {
        'rotation': ['latest_workouts'],
        'last_workout_duration': 15,
        'last_workout_detail_interval': 3,
        'overview_duration': 4,
        'duration': 4,
        'color': 'white',
    }
    pages = build_rotation_pages(snapshot, dashboard, display, 'Rider', 64)
    assert [p[0] for p in pages] == ['last_workout', 'pr']
    assert pages[1][1] is summary
    assert pages[1][2] == pytest.approx(INTRO_SECONDS + turns * (3 + CARD_HOLD_SECONDS))
    assert pr_page_seconds({'is_pr': False}, 3) == pytest.approx(INTRO_SECONDS + 3 + CARD_HOLD_SECONDS)


def test_records_parse_skips_unset_lengths_and_converts_to_kj():
    from peloton.stats.records import parse_personal_records

    overview = {
        'personal_records': [
            {
                'slug': 'caesar',
                'records': [
                    {'name': '45 min', 'raw_value': 225595.0, 'workout_id': 'row', 'workout_date': '2026-04-19'},
                    {'name': '60 min', 'raw_value': -1, 'workout_id': None, 'workout_date': None},
                ],
            },
            {'slug': 'cycling', 'records': 'oops'},
            'junk',
        ]
    }
    assert parse_personal_records(overview) == {'caesar|45 min': {'value_kj': 225.6, 'workout_id': 'row', 'workout_date': '2026-04-19'}}
    assert parse_personal_records({}) == {} and parse_personal_records(None) == {}


def test_records_merge_keeps_what_each_new_record_replaced():
    from peloton.stats.records import merge_personal_records, previous_best_kj

    old = {'value_kj': 250.0, 'workout_id': 'a', 'workout_date': 'd1'}
    new = {'value_kj': 262.0, 'workout_id': 'b', 'workout_date': 'd2'}
    other = {'value_kj': 90.0, 'workout_id': 'z', 'workout_date': 'd0'}
    first = merge_personal_records({}, {'c|30': old, 'c|10': other})
    assert 'previous' not in first['c|30']
    second = merge_personal_records(first, {'c|30': new})
    assert second['c|30']['previous'] == old
    assert second['c|10'] == other  # missing from a partial response: kept
    # Unchanged holder on the next refresh keeps the comparison.
    assert merge_personal_records(second, {'c|30': new})['c|30']['previous'] == old
    assert previous_best_kj('b', second) == 250.0
    assert previous_best_kj('a', second) is None
    assert previous_best_kj('b', None) is None


# The overview's Best Times group as Peloton sent it on 2026-11-22 (trimmed).
BEST_TIMES_GROUP = {
    'name': 'Best Times',
    'slug': 'running_metric_splits',
    'records': [
        {
            'name': 'DISTANCE_1K',
            'slug': '1K',
            'value': '10:33',
            'raw_value': 633.0,
            'unit': 'time',
            'workout_id': 'run',
            'workout_date': 'd',
        },
        {'name': 'DISTANCE_1_MILE', 'slug': '1 Mile', 'value': '16:45', 'raw_value': 1005.0, 'unit': 'time', 'workout_id': 'run'},
        {'name': 'DISTANCE_5K', 'slug': '5K', 'raw_value': -1, 'workout_id': None},
    ],
}


def test_best_times_are_not_output_records():
    """Regression: 633 s (10:33) was stored as a 0.6 kJ output record, so a later 1K record would have
    shown a gain against it."""
    from peloton.stats.records import merge_personal_records, parse_personal_records, previous_best_kj

    assert parse_personal_records({'personal_records': [BEST_TIMES_GROUP]}) == {}
    stale = {
        'running_metric_splits|DISTANCE_1K': {'value_kj': 0.6, 'workout_id': 'old', 'workout_date': 'd'},
        'running|20 min': {'value_kj': 180.3, 'workout_id': 'run', 'workout_date': 'd'},
    }
    merged = merge_personal_records(stale, {})
    assert list(merged) == ['running|20 min']
    assert previous_best_kj('run', merged) is None


def test_best_times_for_a_workout_in_peloton_order():
    from peloton.stats.records import best_times_for

    overview = {'personal_records': [{'slug': 'running', 'records': []}, BEST_TIMES_GROUP]}
    assert best_times_for('run', overview) == [{'label': '1K', 'seconds': 633.0}, {'label': '1 MILE', 'seconds': 1005.0}]
    assert best_times_for('other', overview) == []
    assert best_times_for(None, overview) == [] and best_times_for('run', None) == []
    damaged = {
        'personal_records': [
            'junk',
            {'slug': 'running_metric_splits', 'records': 'oops'},
            {
                'slug': 'running_metric_splits',
                'records': [
                    'junk',
                    {'slug': '', 'name': None, 'raw_value': 600, 'workout_id': 'run'},
                    {'slug': '5K', 'raw_value': True, 'workout_id': 'run'},
                    {'name': 'DISTANCE_10K', 'raw_value': 3600, 'workout_id': 'run'},
                ],
            },
        ]
    }
    assert best_times_for('run', damaged) == [{'label': 'DISTANCE_10K', 'seconds': 3600.0}]


def _cache_with(tmp_path, summaries):
    import json

    from tests.test_dashboard_cache_format import EXPECTED

    payload = json.loads(EXPECTED.read_text(encoding='utf-8'))
    payload['snapshot']['summaries'] = summaries
    path = tmp_path / 'cache.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def test_render_pr_draws_the_workout_then_its_card_on_both_heights(tmp_path, capsys):
    from PIL import Image

    from scripts import render_pr

    plain = {**TREAD_RUN, 'workout_id': 'plain', 'is_pr': False, 'title': 'Walk + Run'}
    run = {**TREAD_RUN, 'title': 'Walk + Run'}
    cache = _cache_with(tmp_path, [plain, run])
    assert render_pr.pr_summary(render_pr.load_snapshot(cache)) == run
    assert render_pr.pr_summary(render_pr.load_snapshot(cache), 'plain') == plain
    assert render_pr.pr_summary(None) is None
    out = tmp_path / 'pr.png'
    render_pr.main(['--cache', str(cache), '--out', str(out)])
    assert capsys.readouterr().out.strip() == str(out)
    # The card's four frames (the trophy rising, then three turns) end each row.
    tall, short = render_pr.panels(run, 64), render_pr.panels(run, 32)
    assert Image.open(out).width >= render_pr.LABEL_WIDTH + max(len(tall), len(short)) * 64 * render_pr.SHEET_SCALE
    assert tall[-1].tobytes() != tall[-2].tobytes() != tall[-3].tobytes()


def test_render_pr_stops_without_a_pr_workout(tmp_path):
    from scripts import render_pr

    cache = _cache_with(tmp_path, [{**TREAD_RUN, 'is_pr': False}])
    with pytest.raises(SystemExit, match='No PR workout'):
        render_pr.main(['--cache', str(cache)])
    with pytest.raises(SystemExit, match='with ID nope'):
        render_pr.main(['--cache', str(cache), '--workout', 'nope'])
