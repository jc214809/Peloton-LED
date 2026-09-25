import pytest
from display.display import initialize_fonts
from display.ui.pr_celebration import BURST_SECONDS, PrCelebrationScreen, pr_card_lines
from scripts.render_demo import ImageMatrix

GOLD, WHITE, GREEN, BLUE = (255, 215, 0), (255, 255, 255), (40, 220, 90), (0, 120, 255)


def _render(summary, elapsed):
    matrix = ImageMatrix(height=64)
    initialize_fonts(64)
    screen = PrCelebrationScreen()
    screen.on_enter(matrix, summary)
    screen.update(elapsed)
    assert screen.render(matrix, summary)
    return matrix.image.load()


def _rows(pixels, color):
    return {y for y in range(64) for x in range(64) if pixels[x, y] == color}


def test_card_lines_for_each_pr_kind():
    assert pr_card_lines({'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412.4,
                          'previous_best_kj': 398}) == ('OUTPUT PR', '412 KJ', '+14 KJ')
    # Joel's real 20 min row PR: 150.9 kJ beat 150.1 kJ.
    assert pr_card_lines({'is_pr': True, 'is_output_pr': True, 'total_output_kj': 150.9,
                          'previous_best_kj': 150.1})[1:] == ('151 KJ', '+0.8 KJ')
    # Jen's real 5 min ride: the graph rounds 25.4 kJ to 25, which would hide the gain.
    assert pr_card_lines({'is_pr': True, 'is_output_pr': True, 'total_output_kj': 25.0,
                          'total_work_kj': 25.4, 'previous_best_kj': 25.0})[1:] == ('25 KJ', '+0.4 KJ')
    assert pr_card_lines({'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412}) == (
        'OUTPUT PR', '412 KJ', None)
    assert pr_card_lines({'is_pr': True, 'is_splits_pr': True, 'row_split_sec_per_500m': 128}) == (
        'SPLITS PR', '2:08/500', None)
    # A PR flag without a usable value still celebrates, rather than crashing.
    assert pr_card_lines({'is_pr': True, 'is_output_pr': True}) == ('NEW PR', '', None)
    assert pr_card_lines({'is_pr': False}) is None


def test_non_pr_summary_renders_nothing():
    matrix = ImageMatrix(height=64)
    initialize_fonts(64)
    assert not PrCelebrationScreen().render(matrix, {'is_pr': False})
    assert not PrCelebrationScreen().render(matrix, None)


def test_burst_phase_is_star_only():
    pixels = _render({'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412}, 0.6)
    assert _rows(pixels, GOLD)
    assert not _rows(pixels, WHITE)


@pytest.mark.parametrize('previous', [398, None])
def test_card_shows_value_gain_and_class_length(previous):
    summary = {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412, 'duration_min': 30}
    if previous is not None:
        summary['previous_best_kj'] = previous
    pixels = _render(summary, BURST_SECONDS + 1.0)
    gold, white, blue = _rows(pixels, GOLD), _rows(pixels, WHITE), _rows(pixels, BLUE)
    assert gold and white and blue
    assert bool(_rows(pixels, GREEN)) == (previous is not None)
    # Star badge and headline sit above the value, class length below it.
    assert min(gold) < min(white) and max(white) < min(blue)
    assert max(blue) <= 63


def _client(pages):
    from unittest.mock import Mock
    client = Mock()
    client.get_workouts_page.side_effect = pages
    return client


def test_preview_finds_newest_completed_pr_across_pages():
    from scripts.preview_pr import find_latest_pr
    client = _client([
        {'data': [{'id': 'a', 'status': 'COMPLETE'},
                  {'id': 'b', 'status': 'IN_PROGRESS', 'is_total_work_personal_record': True}],
         'show_next': True},
        {'data': [{'id': 'c', 'status': 'COMPLETE', 'is_total_work_personal_record': True},
                  {'id': 'd', 'status': 'COMPLETE', 'is_total_work_personal_record': True}],
         'show_next': True},
    ])
    workout, pages = find_latest_pr(client, 'u', max_pages=5)
    assert workout['id'] == 'c' and pages == 2
    assert client.get_workouts_page.call_count == 2


@pytest.mark.parametrize('pages,expected_pages', [
    ([{'data': [{'id': 'a'}], 'show_next': False}], 1),
    ([{'data': []}], 1),
    ([{'data': [{'id': 'a'}], 'show_next': True}] * 3, 3),
])
def test_preview_reports_no_pr_without_overrunning_history(pages, expected_pages):
    from scripts.preview_pr import find_latest_pr
    workout, read = find_latest_pr(_client(pages), 'u', max_pages=3)
    assert workout is None and read == expected_pages


def test_preview_rejects_malformed_page():
    from scripts.preview_pr import find_latest_pr
    with pytest.raises(ValueError):
        find_latest_pr(_client([{'data': 'oops'}]), 'u', max_pages=1)


def test_32_row_card_fits_panel_without_star_badge():
    matrix = ImageMatrix(height=32)
    initialize_fonts(32)
    summary = {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412, 'duration_min': 30}
    screen = PrCelebrationScreen()
    screen.on_enter(matrix, summary)
    screen.update(BURST_SECONDS + 1.0)
    assert screen.render(matrix, summary)
    pixels = matrix.image.load()
    rows = lambda color: {y for y in range(32) for x in range(64) if pixels[x, y] == color}
    gold, white, blue = rows(GOLD), rows(WHITE), rows(BLUE)
    assert gold and white and blue
    assert max(gold) < min(white) and max(white) < min(blue) and max(blue) <= 31


def test_rotation_gives_pr_card_one_interval_after_the_burst():
    from unittest.mock import Mock
    from display.ui.pr_celebration import SETTLE_SECONDS
    from peloton_led import build_rotation_pages
    dashboard = Mock()
    dashboard.should_celebrate_pr.return_value = True
    summary = {'workout_id': 'w', 'discipline': 'Cycling', 'is_pr': True, 'is_output_pr': True,
               'total_output_kj': 412}
    snapshot = {'me': {}, 'summaries': [summary], 'totals': {}, 'status': 'ready'}
    display = {'rotation': ['latest_workouts'], 'last_workout_duration': 15,
               'last_workout_detail_interval': 3, 'overview_duration': 4, 'duration': 4, 'color': 'white'}
    pages = build_rotation_pages(snapshot, dashboard, display, 'Rider', 64)
    assert [p[0] for p in pages] == ['last_workout', 'pr']
    assert pages[1][1] is summary
    assert pages[1][2] == pytest.approx(BURST_SECONDS + SETTLE_SECONDS + 3)


def test_records_parse_skips_unset_lengths_and_converts_to_kj():
    from peloton.records import parse_personal_records
    overview = {'personal_records': [
        {'slug': 'caesar', 'records': [
            {'name': '45 min', 'raw_value': 225595.0, 'workout_id': 'row', 'workout_date': '2026-04-19'},
            {'name': '60 min', 'raw_value': -1, 'workout_id': None, 'workout_date': None}]},
        {'slug': 'cycling', 'records': 'oops'}, 'junk']}
    assert parse_personal_records(overview) == {
        'caesar|45 min': {'value_kj': 225.6, 'workout_id': 'row', 'workout_date': '2026-04-19'}}
    assert parse_personal_records({}) == {} and parse_personal_records(None) == {}


def test_records_merge_keeps_what_each_new_record_replaced():
    from peloton.records import merge_personal_records, previous_best_kj
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
