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
    # The card shows the app's Total Output (189 kJ), not round(188.5), which Python sends
    # to the even 188; and the gain rounds (6.6 -> 7) instead of truncating to 6.
    assert pr_card_lines({'is_pr': True, 'is_output_pr': True, 'total_output_kj': 189.0,
                          'total_work_kj': 188.5, 'previous_best_kj': 181.9})[1:] == ('189 KJ', '+7 KJ')
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


def _render_32(summary, card_t, detail_interval=4.0):
    """The 32-row page card_t seconds after the card settles."""
    from display.ui.pr_celebration import SETTLE_SECONDS
    matrix = ImageMatrix(height=32)
    initialize_fonts(32)
    screen = PrCelebrationScreen(detail_interval=detail_interval)
    screen.on_enter(matrix, summary)
    screen.update(BURST_SECONDS + SETTLE_SECONDS + card_t)
    assert screen.render(matrix, summary)
    return matrix.image.load()


def _points(pixels, color, height=32):
    return {(x, y) for y in range(height) for x in range(64) if pixels[x, y] == color}


def test_32_row_card_fits_panel_with_star_badges_beside_headline():
    pixels = _render_32({'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412, 'duration_min': 30}, 1.0)
    gold, white, blue = (_points(pixels, c) for c in (GOLD, WHITE, BLUE))
    assert gold and white and blue
    rows = lambda pts: {y for _, y in pts}  # noqa: E731  one-line test helper
    assert max(rows(gold)) < min(rows(white)) and max(rows(white)) < min(rows(blue)) and max(rows(blue)) <= 31
    # A star in each margin of the 36 px headline (x 14-49), clear of its letters.
    assert any(x < 12 for x, _ in gold) and any(x > 51 for x, _ in gold)


def test_32_row_badges_step_aside_for_a_headline_too_wide_for_them(monkeypatch):
    import display.ui.pr_celebration as pr
    monkeypatch.setattr(pr, 'get_text_width', lambda font, text: 50 if text.endswith('PR') else 20)
    pixels = _render_32({'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412}, 1.0)
    assert not any(x < 7 or x > 56 for x, _ in _points(pixels, GOLD))  # 7 px margins: no star fits


def _bottom(pixels, color):
    return {p for p in _points(pixels, color) if p[1] >= 24}


def test_32_row_bottom_line_takes_turns_between_gain_class_length_and_discipline():
    summary = {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412, 'previous_best_kj': 398,
               'duration_min': 30, 'discipline': 'Tread Bootcamp'}
    # Default 4 s interval: the card is up 6 s, 2 s a turn.
    turns = [_render_32(summary, i * 2.0 + 0.5) for i in range(3)]
    assert _bottom(turns[0], GREEN) and not _bottom(turns[0], BLUE) and not _bottom(turns[0], WHITE)
    assert _bottom(turns[1], BLUE) and not _bottom(turns[1], GREEN)
    # Running's icon green is too close to the gain's: white instead.
    assert _bottom(turns[2], WHITE) and not _bottom(turns[2], GREEN) and not _bottom(turns[2], BLUE)
    assert max(x for x, _ in _bottom(turns[2], WHITE)) <= 62
    # Without a class length or discipline the gain stays put.
    steady = _render_32({**summary, 'duration_min': None, 'discipline': None}, 4.5)
    assert _points(steady, GREEN)


@pytest.mark.parametrize('detail_interval', [2.0, 4.0, 7.0])
@pytest.mark.parametrize('previous, expected', [
    (398, [GREEN, BLUE, (240, 70, 25)]),  # gain, class length, cycling
    (None, [BLUE, (240, 70, 25)]),
])
def test_32_row_turns_share_the_card_and_never_come_back_as_it_ends(detail_interval, previous, expected):
    """Regression: 2 s turns looped from the end of the burst, so the gain came back for the card's
    last 0.3 s and flickered just before the page changed (Joel, 2026-11-19)."""
    from display.ui.pr_celebration import CARD_HOLD_SECONDS
    summary = {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412, 'previous_best_kj': previous,
               'duration_min': 30, 'discipline': 'Cycling'}
    shown = detail_interval + CARD_HOLD_SECONDS  # how long build_rotation_pages leaves the settled card up
    share = shown / len(expected)
    for index, color in enumerate(expected):
        for t in (index * share + 0.05, (index + 1) * share - 0.05):
            pixels = _render_32(summary, t, detail_interval)
            assert _bottom(pixels, color), (index, t)
            assert not any(_bottom(pixels, other) for other in expected if other != color), (index, t)
    # Past the page's end (a slow frame) it still holds the last turn.
    assert _bottom(_render_32(summary, shown + 1.0, detail_interval), expected[-1])


def test_compact_turn_holds_the_last_turn_and_survives_a_missing_interval():
    from display.ui.pr_celebration import SETTLE_SECONDS, compact_turn
    assert [compact_turn(SETTLE_SECONDS + t, 3, 4.0) for t in (0.0, 1.99, 2.01, 4.01, 5.99, 6.3, 60)] == [
        0, 0, 1, 2, 2, 2, 2]
    assert compact_turn(0.0, 2, 4.0) == 0  # still settling
    assert PrCelebrationScreen(detail_interval=None).detail_interval == 4.0


@pytest.mark.parametrize('discipline, color', [
    ('Cycling', (240, 70, 25)),  # its icon colour, as on the lifetime pages
    ('Bike Bootcamp', (240, 70, 25)),  # a bootcamp takes its machine's
    ('Outdoor Walking', (200, 200, 235)),  # no icon colour of its own: the default
    ('Rowing', WHITE),  # icon blue is too close to the class length's
    ('Running', WHITE),  # icon green is too close to the gain's
])
def test_32_row_discipline_takes_its_icon_colour_unless_it_clashes(discipline, color):
    summary = {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 412, 'duration_min': 30,
               'discipline': discipline}
    assert _bottom(_render_32(summary, 5.5), color)  # the second of two turns


def test_32_row_plain_pr_names_the_discipline_and_fits_the_widest():
    pixels = _render_32({'is_pr': True, 'discipline': 'Tread Bootcamp', 'duration_min': 45}, 1.0)
    white = _points(pixels, WHITE)
    assert white and min(x for x, _ in white) >= 1 and max(x for x, _ in white) <= 62
    # Named once: the bottom line keeps the class length instead of repeating it.
    later = _render_32({'is_pr': True, 'discipline': 'Tread Bootcamp', 'duration_min': 45}, 5.5)
    assert {y for _, y in _points(later, WHITE)} == {y for _, y in white} and _points(later, BLUE)
    assert not _points(_render_32({'is_pr': True, 'discipline': None}, 1.0), WHITE)


@pytest.mark.parametrize('summary', [
    {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 1234, 'previous_best_kj': 1233.2, 'duration_min': 120,
     'discipline': 'Outdoor Walking'},
    {'is_pr': True, 'is_output_pr': True, 'total_output_kj': 51, 'duration_min': 10, 'discipline': 'Tread Bootcamp'},
    {'is_pr': True, 'is_splits_pr': True, 'row_split_sec_per_500m': 128, 'duration_min': 120,
     'discipline': 'Rowing'},
    {'is_pr': True, 'discipline': 'Outdoor Walking', 'duration_min': 120},
])
def test_32_row_sparkles_never_touch_text(summary):
    sparkle_colors = {(255, 255, 200), (150, 130, 40), (0, 0, 0)}
    for tick in range(36):
        pixels = _render_32(summary, tick * 0.25)
        sparkle = _points(pixels, (255, 255, 200)) | _points(pixels, (150, 130, 40))
        for x, y in sparkle:
            near = {pixels[x + dx, y + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                    if 0 <= x + dx < 64 and 0 <= y + dy < 32}
            assert near <= sparkle_colors, (x, y, tick)  # anything else is text or a badge


def test_rotation_gives_pr_card_one_interval_and_the_extra_hold_after_the_burst():
    from unittest.mock import Mock
    from display.ui.pr_celebration import CARD_HOLD_SECONDS, SETTLE_SECONDS
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
    assert pages[1][2] == pytest.approx(BURST_SECONDS + SETTLE_SECONDS + 3 + CARD_HOLD_SECONDS)


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
