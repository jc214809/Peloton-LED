"""Per-discipline milestones: round targets, the upcoming page, and their celebrations."""
import json
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.celebration_screen import (INTRO_SECONDS, TEXT_LEFT_32, CelebrationScreen, discipline_noun,
                                           ordinal_line)
from display.ui.countdown_screen import BAR_FILL, CountdownScreen
from display.ui.lifetime_overview import discipline_color
from peloton.cache import CACHE_VERSION, load_snapshot
from peloton.config import load_config
from peloton.dashboard import Dashboard
from peloton.goals import (discipline_target_after, discipline_target_reached, parse_milestone_key,
                           reached_discipline_milestones, upcoming_discipline_milestones)
from peloton_led import build_rotation_pages, run_display_loop
from scripts.render_demo import ImageMatrix
from scripts.render_rotation import PreviewDashboard

TOTALS = {'Total Workouts': 2123, 'Cycling': 641, 'Strength': 496, 'Walking': 202, 'Cardio': 93,
          'Meditation': 89, 'Bike Bootcamp': 47, 'Row Bootcamp': 9}

# Loops here play whole rotations: sleeping only moves peloton_led's clock on.
pytestmark = pytest.mark.usefixtures('instant_clock')


@pytest.mark.parametrize('count, after, reached', [
    (0, 25, None), (9, 25, None), (24, 25, None), (25, 50, 25), (49, 50, 25), (50, 100, 50),
    (99, 100, 50), (100, 200, 100), (496, 500, 400), (500, 600, 500), (2123, 2200, 2100)])
def test_round_targets_are_25_50_100_then_every_100(count, after, reached):
    assert discipline_target_after(count) == after
    assert discipline_target_reached(count) == reached


def test_upcoming_lists_only_close_disciplines_closest_first():
    upcoming = upcoming_discipline_milestones(TOTALS)
    # Strength 4 away, Bike Bootcamp 3 away; Cardio (7) and Meditation (11) are too far; the total is
    # the next-milestone page's job.
    assert [(u['discipline'], u['target'], u['count'], u['previous']) for u in upcoming] == [
        ('bike_bootcamp', 50, 47, 25), ('strength', 500, 496, 400)]
    assert upcoming[1]['label'] == 'Strength'
    assert [u['discipline'] for u in upcoming_discipline_milestones(TOTALS, within=7)] == [
        'bike_bootcamp', 'strength', 'cardio']
    assert len(upcoming_discipline_milestones(TOTALS, within=100, limit=3)) == 3


def test_upcoming_ties_go_to_the_bigger_target_and_bad_counts_are_skipped():
    totals = {'Yoga': 22, 'Cycling': 597, 'Running': '98', 'Rowing': True, 'Stretching': -1, 'Cardio': None}
    assert [u['discipline'] for u in upcoming_discipline_milestones(totals)] == ['cycling', 'yoga']
    assert upcoming_discipline_milestones({}) == upcoming_discipline_milestones(None) == []


def test_only_a_target_crossed_in_the_last_few_workouts_counts_as_reached():
    # Walking 202 crossed 200 two walks ago; Cycling 641 passed 600 long ago; Row Bootcamp has none yet.
    assert reached_discipline_milestones(TOTALS) == ['walking:200']
    assert reached_discipline_milestones({'Yoga': 25, 'Rowing': 109, 'Running': 110}) == ['rowing:100', 'yoga:25']
    assert reached_discipline_milestones({'Total Workouts': 2200}) == []


@pytest.mark.parametrize('key, parsed', [
    ('strength:500', ('strength', 500)), ('tread_bootcamp:25', ('tread_bootcamp', 25)),
    ('500', None), (':500', None), ('strength:', None), ('strength:5x', None), (500, None), (None, None)])
def test_milestone_keys(key, parsed):
    assert parse_milestone_key(key) == parsed


@pytest.mark.parametrize('discipline, label, noun', [
    ('cycling', 'Cycling', 'RIDE'), ('running', 'Running', 'RUN'), ('walking', 'Walking', 'WALK'),
    ('rowing', 'Rowing', 'ROW'), ('strength', 'Strength', 'STRENGTH'),
    # A bootcamp's count isn't the rides' or rows', so it keeps its name.
    ('bike_bootcamp', 'Bike Bootcamp', 'BIKE BOOTCAMP'), ('tread_bootcamp', None, 'TREAD BOOTCAMP'),
    (None, None, 'CLASS')])
def test_discipline_nouns(discipline, label, noun):
    assert discipline_noun(discipline, label) == noun


def _display(**changes):
    return {'rotation': ['next_milestone', 'milestones'], 'last_workout_duration': 15,
            'overview_duration': 5, 'milestones': [], 'milestone_step': 0, **changes}


def _dashboard(total=(), disciplines=()):
    dashboard = Mock()
    dashboard.pending_milestones.return_value = list(total)
    dashboard.pending_discipline_milestones.return_value = list(disciplines)
    return dashboard


def _snapshot(totals=TOTALS):
    return {'summaries': [], 'totals': dict(totals), 'status': 'ready'}


def test_rotation_adds_one_countdown_page_per_close_discipline():
    pages = build_rotation_pages(_snapshot(), _dashboard(), _display(), 'Joel', 64)
    assert pages == [
        ('countdown', {'total': 47, 'target': 50, 'previous': 25, 'title': 'Bike Bootcamp',
                                  'discipline': 'bike_bootcamp'}, 5),
        ('countdown', {'total': 496, 'target': 500, 'previous': 400, 'title': 'Strength',
                                  'discipline': 'strength'}, 5)]
    timed = build_rotation_pages(_snapshot(), _dashboard(),
                                 _display(screen_durations={'next_milestone': 9}), 'Joel', 64)
    assert {page[2] for page in timed} == {9}
    # Nothing close: no page at all. Off in the rotation: none either.
    assert build_rotation_pages(_snapshot({'Cycling': 641}), _dashboard(), _display(), 'J', 64) == []
    assert build_rotation_pages(_snapshot(), _dashboard(), _display(rotation=['milestones']), 'J', 64) == []


def test_how_close_and_how_many_pages_are_configurable():
    def shown(**changes):
        pages = build_rotation_pages(_snapshot(), _dashboard(), _display(**changes), 'J', 64)
        return [page[1]['title'] for page in pages]
    assert shown(milestone_within=7) == ['Bike Bootcamp', 'Strength', 'Cardio']
    assert shown(milestone_within=11, milestone_pages=4) == [
        'Bike Bootcamp', 'Strength', 'Cardio', 'Meditation']
    assert shown(milestone_within=3) == ['Bike Bootcamp']
    assert shown(milestone_pages=1) == ['Bike Bootcamp']


def test_a_discipline_milestone_is_celebrated_only_within_its_last_10_workouts(tmp_path):
    dashboard, _ = _real_dashboard(tmp_path, {'Walking': 202, 'Yoga': 34, 'Cycling': 610})
    assert dashboard.pending_discipline_milestones() == ['walking:200', 'yoga:25']  # 600 was 10 rides ago
    # The old setting is gone: an old config's value changes nothing.
    dashboard.config['discipline_milestone_celebrate_within'] = 0
    assert dashboard.pending_discipline_milestones() == ['walking:200', 'yoga:25']


def test_a_discipline_celebration_needs_no_configured_milestones():
    pages = build_rotation_pages(_snapshot(), _dashboard(disciplines=['walking:200']),
                                 _display(rotation=['milestones']), 'Joel', 64)
    assert pages[0][:2] == ('celebration', {'number': 200, 'noun': 'WALK', 'subtitle': 'Joel',
                                            'milestone': 'walking:200'})
    named = build_rotation_pages(_snapshot(), _dashboard(disciplines=['bike_bootcamp:50']),
                                 _display(rotation=['milestones']), 'Joel', 64)
    assert named[0][1]['noun'] == 'BIKE BOOTCAMP'


def test_celebrations_landing_together_take_turns_pass_by_pass():
    dashboard = _dashboard(total=[2100], disciplines=['strength:500', 'walking:200'])
    display = _display(rotation=['milestones'], milestone_step=100)
    shown = [build_rotation_pages(_snapshot(), dashboard, display, 'J', 64, pass_index=index)[0][1]['milestone']
             for index in range(4)]
    assert shown == [2100, 'strength:500', 'walking:200', 2100]
    # Total milestones still need the section's configuration; discipline ones don't.
    unset = build_rotation_pages(_snapshot(), dashboard, _display(rotation=['milestones']), 'J', 64)
    assert [page[1]['milestone'] for page in unset] == ['strength:500']


def test_display_loop_acknowledges_a_discipline_celebration_by_its_key():
    dashboard = _dashboard(disciplines=['walking:200'])
    dashboard.login_required = False
    dashboard.snapshot.return_value = {'me': {'username': 'Rider'}, **_snapshot()}
    run_display_loop(Mock(), dashboard, _display(rotation=['milestones']), cycles=1)
    dashboard.acknowledge_milestone.assert_called_once_with('walking:200')


def _at(text, zone='America/New_York'):
    return datetime.fromisoformat(text).replace(tzinfo=ZoneInfo(zone)).timestamp()


def _real_dashboard(tmp_path, totals):
    config = {'cache_path': str(tmp_path / 'cache.json'), 'timezone': 'America/New_York',
              'milestones': [], 'milestone_step': 0}
    dashboard = Dashboard(tmp_path / 'token', config)
    dashboard._publish(totals=dict(totals), me={'id': 'u'}, summaries=[], last_updated=1.0)
    return dashboard, config


def test_discipline_milestone_celebrates_until_midnight_and_survives_restart(tmp_path):
    dashboard, config = _real_dashboard(tmp_path, {'Walking': 202, 'Total Workouts': 2201})
    assert dashboard.pending_discipline_milestones() == ['walking:200']
    assert dashboard.pending_milestones() == []  # totals stay separate
    dashboard.acknowledge_milestone('walking:200', now=_at('2026-11-07T07:00'))
    restarted = Dashboard(tmp_path / 'token', dict(config))
    assert restarted.snapshot()['discipline_milestone_shown_at'] == {'walking:200': _at('2026-11-07T07:00')}
    assert restarted.pending_discipline_milestones(now=_at('2026-11-07T23:59')) == ['walking:200']
    assert restarted.pending_discipline_milestones(now=_at('2026-11-08T00:00')) == []
    # The next acknowledgement after midnight moves it to the done list, separate from the totals'.
    restarted.acknowledge_milestone('strength:500', now=_at('2026-11-08T00:01'))
    after = Dashboard(tmp_path / 'token', dict(config)).snapshot()
    assert after['celebrated_discipline_milestones'] == ['walking:200']
    assert after['celebrated_milestones'] == []
    assert after['discipline_milestone_shown_at'] == {'strength:500': _at('2026-11-08T00:01')}


def test_acknowledging_ignores_bad_keys_and_retires_lower_ones_of_that_discipline(tmp_path):
    dashboard, _ = _real_dashboard(tmp_path, {'Walking': 202, 'Yoga': 27})
    for bad in ('walking', 'walking:', None, True, 2.5):
        dashboard.acknowledge_milestone(bad)
    assert dashboard.snapshot()['discipline_milestone_shown_at'] == {}
    dashboard._publish(discipline_milestone_shown_at={}, celebrated_discipline_milestones=[])
    dashboard.pending_discipline_milestones = Mock(return_value=['walking:100', 'walking:200', 'yoga:25'])
    dashboard.acknowledge_milestone('walking:200', now=_at('2026-11-07T07:00'))
    snapshot = dashboard.snapshot()
    assert snapshot['celebrated_discipline_milestones'] == ['walking:100']  # yoga keeps its own turn
    assert list(snapshot['discipline_milestone_shown_at']) == ['walking:200']


def _cache(tmp_path, **changes):
    snapshot = {'me': {'id': 'u'}, 'totals': {}, 'summaries': [], 'last_updated': 1.0, **changes}
    path = tmp_path / 'cache.json'
    path.write_text(json.dumps({'version': CACHE_VERSION, 'snapshot': snapshot}))
    return path


def test_damaged_discipline_milestone_state_is_dropped_not_the_cache(tmp_path):
    good = load_snapshot(_cache(tmp_path, celebrated_discipline_milestones=['yoga:25'],
                                discipline_milestone_shown_at={'walking:200': 3.5}))
    assert good['celebrated_discipline_milestones'] == ['yoga:25']
    assert good['discipline_milestone_shown_at'] == {'walking:200': 3.5}
    for bad in ({}, ['yoga'], [25], 'yoga:25'):
        snapshot = load_snapshot(_cache(tmp_path, celebrated_discipline_milestones=bad))
        assert snapshot is not None and 'celebrated_discipline_milestones' not in snapshot
    for bad in ([], {'200': 1.0}, {'walking:200': 'soon'}, {'walking:200': True}):
        snapshot = load_snapshot(_cache(tmp_path, discipline_milestone_shown_at=bad))
        assert snapshot is not None and 'discipline_milestone_shown_at' not in snapshot


def _record_text(monkeypatch):
    import display.ui.countdown_screen as screen
    drawn = []
    original = screen.graphics.DrawText

    def record(matrix, font, x, y, color, text):
        drawn.append((text, (color.red, color.green, color.blue)))
        return original(matrix, font, x, y, color, text)
    monkeypatch.setattr(screen.graphics, 'DrawText', record)
    return drawn


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('title, discipline', [('Tread Bootcamp', 'tread_bootcamp'),
                                               ('Walking Outdoor', 'walking_outdoor'), ('Yoga', 'yoga')])
def test_discipline_countdown_fits_and_fills_the_bar(height, title, discipline):
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    state = {'total': 196, 'target': 200, 'previous': 100, 'title': title, 'discipline': discipline}
    assert CountdownScreen().render(matrix, state)
    pixels = matrix.image.load()
    # Nothing touches the side columns: the longest discipline names still fit. (A bootcamp name runs edge to
    # edge on purpose, on both heights: TREAD BOOTCAMP is 64 columns.)
    rows = range({64: 44, 32: 23}[height]) if 'bootcamp' in discipline else range(height)
    assert all(pixels[x, y] == (0, 0, 0) for x in (0, 63) for y in rows)
    bars = [y for y in range(height) if pixels[3, y] == BAR_FILL]
    if height < 64:
        assert bars == []  # no room for the bar on 32 rows
    else:
        assert sum(pixels[x, bars[0]] == BAR_FILL for x in range(64)) == round(58 * 96 / 100)
        text_bottom = max(y for y in range(bars[0]) for x in range(64) if pixels[x, y] not in ((0, 0, 0),))
        assert bars[0] - text_bottom - 1 >= 2  # a gap between the name and the bar


def screen_count():
    from display.ui.countdown_screen import _COUNT
    return _COUNT


def test_discipline_countdown_reads_3_to_go_and_3_away_from(monkeypatch):
    drawn = _record_text(monkeypatch)
    state = {'total': 597, 'target': 600, 'previous': 500, 'title': 'Cycling', 'discipline': 'cycling'}
    red = discipline_color('cycling')
    initialize_fonts(64)
    CountdownScreen().render(ImageMatrix(height=64), state)
    assert drawn == [('3', (255, 255, 255)), ('TO GO', (255, 255, 255)),
                     ('TILL YOUR', (145, 165, 190)), ('600', (255, 215, 0)),
                     ('TH', (255, 215, 0)), ('RIDE', red)]
    drawn.clear()
    initialize_fonts(32)
    CountdownScreen().render(ImageMatrix(height=32), {**state, 'total': 1997, 'target': 2000})
    # 32 rows: 3 AWAY FROM / YOUR 2,000TH / RIDE; the count and the milestone gold, the words white.
    assert screen_count() == (255, 215, 0)
    assert drawn == [('3', screen_count()), ('AWAY', (255, 255, 255)), ('FROM', (255, 255, 255)),
                     ('YOUR', (255, 255, 255)), ('2', (255, 215, 0)), (',', (255, 215, 0)), ('000', (255, 215, 0)),
                     ('TH', (255, 215, 0)), ('RIDE', red)]


def test_the_32_row_name_is_bold_and_a_wide_one_5x8(monkeypatch):
    """The name is the 7x13B the number uses; one too wide for it (STRETCHING) is 5x8, and a bootcamp is drawn
    as on 64 rows, 5x8 in pieces with the tight space (TREAD, BOO, TCAMP)."""
    import display.ui.countdown_screen as screen
    from display.display import loaded_fonts as fonts
    fonts_used = []
    original = screen.graphics.DrawText
    def record(matrix, font, x, y, color, text):
        fonts_used.append((text, font))
        return original(matrix, font, x, y, color, text)
    monkeypatch.setattr(screen.graphics, 'DrawText', record)
    initialize_fonts(32)
    state = {'total': 496, 'target': 500, 'previous': 400, 'title': 'Strength', 'discipline': 'strength'}
    CountdownScreen().render(ImageMatrix(height=32), state)
    assert dict(fonts_used)['STRENGTH'] is fonts['bold']
    fonts_used.clear()
    CountdownScreen().render(ImageMatrix(height=32), {**state, 'title': 'Stretching', 'discipline': 'stretching'})
    assert dict(fonts_used)['STRETCHING'] is fonts['discipline']
    fonts_used.clear()
    CountdownScreen().render(ImageMatrix(height=32), {**state, 'title': 'Tread Bootcamp'})
    pieces = [(text, font) for text, font in fonts_used if text in ('TREAD', 'BOO', 'TCAMP')]
    assert [text for text, _ in pieces] == ['TREAD', 'BOO', 'TCAMP']
    assert all(font is fonts['discipline'] for _, font in pieces)


@pytest.mark.parametrize('title, discipline', [('Row Bootcamp', 'row_bootcamp'), ('Bike Bootcamp', 'bike_bootcamp'),
                                               ('Tread Bootcamp', 'tread_bootcamp')])
def test_a_32_row_bootcamp_name_matches_its_64_row_drawing(title, discipline):
    """The same lit pixels as the 64-row name (both 5x8), centred by them."""
    def name_pixels(height, top, bottom):
        initialize_fonts(height)
        matrix = ImageMatrix(height=height)
        state = {'total': 47, 'target': 50, 'previous': 25, 'title': title, 'discipline': discipline}
        assert CountdownScreen().render(matrix, state)
        pixels = matrix.image.load()
        lit = {(x, y) for x in range(64) for y in range(top, bottom) if pixels[x, y] != (0, 0, 0)}
        return {(x, y - min(y for _, y in lit)) for x, y in lit}, lit
    shape_64, _ = name_pixels(64, 44, 57)
    shape_32, lit = name_pixels(32, 22, 32)
    assert shape_32 == shape_64
    assert {y for _, y in lit} == set(range(23, 29))   # closed up: a 2-row gap under the number, as for a bold name
    left, right = min(x for x, _ in lit), 63 - max(x for x, _ in lit)
    assert left - right in (0, 1)


def test_the_name_takes_its_lifetime_colour_and_a_bootcamp_its_machines():
    assert discipline_color('tread_bootcamp') == discipline_color('running')
    assert discipline_color('row_bootcamp') == discipline_color('rowing')
    assert discipline_color('bike_bootcamp') == discipline_color('cycling') != discipline_color('strength')
    assert discipline_color(None) == discipline_color('surfing') == (200, 200, 235)


@pytest.mark.parametrize('state', [{}, None, {'total': 600, 'target': 600, 'previous': 500},
                                   {'total': '5', 'target': 25, 'previous': 0},
                                   {'total': True, 'target': 25, 'previous': 0}])
def test_discipline_countdown_draws_nothing_for_a_bad_state(state):
    initialize_fonts(64)
    assert not CountdownScreen().render(ImageMatrix(height=64), state)


def test_a_thousandth_fits_with_its_comma_and_raised_ending():
    from display.display import loaded_fonts as fonts
    initialize_fonts(64)
    parts = ordinal_line(1000, [fonts['big'], fonts['bold']], fonts['titles'], 36, None, 0, 64)
    assert [text for _, _, _, _, text in parts] == ['1', ',', '000', 'TH']
    assert parts[0][0] is fonts['big']


@pytest.mark.parametrize('height', [32, 64])
def test_a_long_discipline_name_falls_back_to_its_last_word_beside_the_trophy(height):
    initialize_fonts(height)
    room = 64 - TEXT_LEFT_32 - 1 if height < 64 else 62
    fits = get_text_width(loaded_fonts['info'], 'TREAD BOOTCAMP') <= room
    screen = CelebrationScreen()
    matrix = ImageMatrix(height=height)
    screen.update(INTRO_SECONDS + 0.1)
    from display.ui import celebration_screen
    lines = (screen._lines_32 if height < 64 else screen._lines_64)(matrix, 200, 'TREAD BOOTCAMP', 'JOEL')
    nouns = [text for parts in lines for _, _, _, color, text in parts if color is celebration_screen._GOLD]
    assert nouns == ['TREAD BOOTCAMP' if fits else 'BOOTCAMP']
    assert height == 64 or not fits  # 32 rows really needs the fallback


def test_preview_dashboard_shows_a_reached_discipline_milestone():
    assert PreviewDashboard([]).pending_discipline_milestones({'totals': TOTALS}) == ['walking:200']


def test_discipline_countdowns_are_next_milestone_pages_not_a_section_of_their_own(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"display": {"rotation": ["discipline_milestones"]}}')
    with pytest.raises(ValueError, match='display.rotation'):
        load_config(str(path))
    assert 'discipline_milestones' not in load_config(str(tmp_path / 'missing.json'), allow_missing=True)[
        'display']['rotation']


def test_config_defaults_and_rejects_bad_milestone_countdown_settings(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"display": {}}')
    display = load_config(str(path))['display']
    assert (display['milestone_within'], display['milestone_pages']) == (5, 3)
    assert 'discipline_milestone_celebrate_within' not in display
    path.write_text('{"display": {"discipline_milestone_celebrate_within": -1}}')
    load_config(str(path))  # retired, so an old config's value is ignored, not rejected
    for key, value in (('milestone_within', 0), ('milestone_pages', 0), ('milestone_within', True),
                       ('milestone_pages', 2.5), ('milestone_within', '5')):
        path.write_text(json.dumps({'display': {key: value}}))
        with pytest.raises(ValueError, match=key):
            load_config(str(path))


def test_config_pr_max_age_days_defaults_off_and_rejects_bad_values(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"display": {}}')
    assert load_config(str(path))['display']['pr_max_age_days'] is None
    path.write_text('{"display": {"pr_max_age_days": 7}}')
    assert load_config(str(path))['display']['pr_max_age_days'] == 7
    for value in (0, -1, True, 2.5, '7'):
        path.write_text(json.dumps({'display': {'pr_max_age_days': value}}))
        with pytest.raises(ValueError, match='pr_max_age_days'):
            load_config(str(path))


@pytest.mark.parametrize('discipline, title, noun', [('cycling', 'Cycling', 'RIDE'), ('running', 'Running', 'RUN'),
                                                     ('walking', 'Walking', 'WALK'), ('rowing', 'Rowing', 'ROW'),
                                                     ('strength', 'Strength', 'STRENGTH'),
                                                     ('bike_bootcamp', 'Bike Bootcamp', 'BIKE BOOTCAMP'),
                                                     (None, 'Workout', 'WORKOUT')])
def test_64_row_countdown_names_what_is_counted(monkeypatch, discipline, title, noun):
    drawn = _record_text(monkeypatch)
    initialize_fonts(64)
    state = {'total': 47, 'target': 50, 'previous': 25, 'title': title, 'discipline': discipline}
    assert CountdownScreen().render(ImageMatrix(height=64), state)
    texts = [text for text, _ in drawn]
    assert texts[:3] == ['3', 'TO GO', 'TILL YOUR']
    # A two-word name is drawn in pieces (BIKE, BOO, TCAMP: BOO sits 2 px right, closing the hole before the T).
    assert ''.join(texts[texts.index('TH') + 1:]) == noun.replace(' ', '')


@pytest.mark.parametrize('height', [32, 64])
def test_one_left_says_next_one_is_your_on_64_rows_only(monkeypatch, height):
    drawn = _record_text(monkeypatch)
    initialize_fonts(height)
    state = {'total': 599, 'target': 600, 'previous': 500, 'title': 'Cycling', 'discipline': 'cycling'}
    matrix = ImageMatrix(height=height)
    assert CountdownScreen().render(matrix, state)
    texts = [text for text, _ in drawn]
    if height == 64:
        assert texts == ['NEXT ONE', 'IS YOUR', '600', 'TH', 'RIDE']
    else:
        assert texts[:4] == ['1', 'AWAY', 'FROM', 'YOUR']
    pixels = matrix.image.load()
    assert all(pixels[x, y] == (0, 0, 0) for x in (0, 63) for y in range(height))  # the line fits


def test_one_left_keeps_the_number_name_and_bar_where_the_count_page_has_them():
    initialize_fonts(64)
    pages = []
    for total in (597, 599):
        matrix = ImageMatrix(height=64)
        state = {'total': total, 'target': 600, 'previous': 500, 'title': 'Cycling', 'discipline': 'cycling'}
        assert CountdownScreen().render(matrix, state)
        pages.append(matrix.image)
    # Only the top two lines and the bar's fill differ: 600TH and RIDE are the same pixels.
    assert pages[0].crop((0, 28, 64, 56)).tobytes() == pages[1].crop((0, 28, 64, 56)).tobytes()
    assert any(pages[1].getpixel((x, y)) != (0, 0, 0) for x in range(64) for y in range(28, 56))


@pytest.mark.parametrize('title, discipline, pieces', [('Row Bootcamp', 'row_bootcamp', ['ROW', 'BOO', 'TCAMP']),
                                                       ('Tread Bootcamp', 'tread_bootcamp', ['TREAD', 'BOO', 'TCAMP'])])
def test_bootcamp_names_run_in_one_tight_line_with_boo_moved_right(monkeypatch, title, discipline, pieces):
    drawn = _record_text(monkeypatch)
    initialize_fonts(64)
    matrix = ImageMatrix(height=64)
    state = {'total': 47, 'target': 50, 'previous': 25, 'title': title, 'discipline': discipline}
    assert CountdownScreen().render(matrix, state)
    assert [text for text, _ in drawn][-3:] == pieces
    pixels = matrix.image.load()
    name_rows = range(46, 55)
    assert any(pixels[x, y] != (0, 0, 0) for x in range(64) for y in name_rows)
    assert not any(pixels[x, 44] != (0, 0, 0) and pixels[x, 45] != (0, 0, 0) for x in (0, 63))  # only the name touches the edges


def _name_lit(title, discipline):
    initialize_fonts(64)
    matrix = ImageMatrix(height=64)
    state = {'total': 47, 'target': 50, 'previous': 25, 'title': title, 'discipline': discipline}
    assert CountdownScreen().render(matrix, state)
    pixels = matrix.image.load()
    return ''.join('#' if any(pixels[x, y] != (0, 0, 0) for y in range(46, 56)) else '.' for x in range(64))


@pytest.mark.parametrize('title, discipline, lit', [
    ('Row Bootcamp', 'row_bootcamp', '....####.####.####.....####.####.#######.####.####.####.####....'),
    ('Bike Bootcamp', 'bike_bootcamp', '...####.###.####.####....####.####.#######.####.####.####.####..'),
    ('Tread Bootcamp', 'tread_bootcamp', '.###.####.####.####.####...####.####.#######.####.####.####.####')])
def test_bootcamp_names_are_centred_by_their_lit_pixels(title, discipline, lit):
    """ROW 4/4, BIKE 3/2 (BIKE a pixel right of BOOTCAMP's gap closing), TREAD 1/0: the spare column goes left."""
    got = _name_lit(title, discipline)
    assert got == lit
    left, right = len(got) - len(got.lstrip('.')), len(got) - len(got.rstrip('.'))
    assert 0 <= left - right <= 1


def test_countdown_ink_table_matches_the_fonts():
    """NAME_INK is a measurement, so re-measure it: the first lit column and lit width when drawn from x = 0."""
    from display.display import loaded_fonts
    import display.ui.countdown_screen as screen
    initialize_fonts(64)
    for name, expected in screen.NAME_INK.items():
        runs = screen.tight_name_runs(name, loaded_fonts['titles'], (255, 255, 255), 64)
        matrix = ImageMatrix(height=64)
        screen._draw_runs_at(matrix, runs, 52, 0)
        pixels = matrix.image.load()
        cols = [x for x in range(64) if any(pixels[x, y] != (0, 0, 0) for y in range(44, 56))]
        assert (min(cols), max(cols) - min(cols) + 1) == expected, name


def test_countdown_line_edge_ink():
    """LINE_TRAILING_BLANK is a measurement, so re-measure it: the glyphs a 32-row line starts or ends with are
    lit from their first column and leave that many blank columns after."""
    from display.display import loaded_fonts, get_text_width
    from driver import graphics
    import display.ui.countdown_screen as screen
    initialize_fonts(32)
    for key, chars in (('bold', '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'), ('stats', 'YRTH'),
                       ('discipline', '23456789AFM')):
        for char in chars:
            matrix = ImageMatrix(width=20, height=20)
            graphics.DrawText(matrix, loaded_fonts[key], 0, 15, graphics.Color(255, 255, 255), char)
            pixels = matrix.image.load()
            cols = [x for x in range(20) if any(pixels[x, y] != (0, 0, 0) for y in range(20))]
            width = get_text_width(loaded_fonts[key], char)
            assert (min(cols), width - 1 - max(cols)) == (0, screen.LINE_TRAILING_BLANK), (key, char)
    for char, blank in screen.LEAD_DIGIT_BLANK.items():   # the 5x8 digits that start with a blank column
        matrix = ImageMatrix(width=20, height=20)
        graphics.DrawText(matrix, loaded_fonts['discipline'], 0, 15, graphics.Color(255, 255, 255), char)
        pixels = matrix.image.load()
        assert min(x for x in range(20) if any(pixels[x, y] != (0, 0, 0) for y in range(20))) == blank, char


@pytest.mark.parametrize('name, discipline, lines', [
    ('Cycling', 'cycling', ((3, 8), (12, 20), (23, 31))),
    ('Tread Bootcamp', 'tread_bootcamp', ((4, 9), (12, 20), (23, 28))),   # a smaller name closes up
    ('Stretching', 'stretching', ((4, 9), (12, 20), (23, 28)))])
@pytest.mark.parametrize('target, left', [(50, 3), (600, 1), (2200, 3), (10000, 3), (500, 11)])
def test_the_32_row_lines_are_centred_and_your_floats_mid_number(target, left, name, discipline, lines):
    import display.ui.countdown_screen as screen
    initialize_fonts(32)
    matrix = ImageMatrix(height=32)
    state = {'total': target - left, 'target': target, 'previous': 0, 'title': name, 'discipline': discipline}
    assert CountdownScreen().render(matrix, state)
    pixels = matrix.image.load()
    def lit(rows, color=None):
        return [(x, y) for x in range(64) for y in rows
                if pixels[x, y] != (0, 0, 0) and (color is None or pixels[x, y] == color)]
    for top, bottom in lines:
        cells = lit(range(top, bottom + 1))
        assert min(y for _, y in cells) == top
        assert max(y for _, y in cells) in (bottom, bottom + 1)   # 2,200's comma hangs a row lower
        xs = [x for x, _ in cells]
        assert min(xs) - (63 - max(xs)) in (0, 1), (top, bottom)   # centred, an odd spare column to the left
    number_top, number_bottom = lines[1]
    assert {y for _, y in lit(range(lines[0][0], lines[0][1] + 1), screen._COUNT)}   # the count is gold
    # YOUR (4x6, 5 px) has 2 rows of the 9 px digits above it and 2 below.
    your = {y for x, y in lit(range(number_top, number_bottom + 1), (255, 255, 255))}
    assert your == set(range(number_top + 2, number_bottom - 1))


class _EdgeMatrix(ImageMatrix):
    """An ImageMatrix that counts lit pixels drawn off the panel (ImageMatrix drops them silently)."""
    def Clear(self):
        super().Clear()
        self.off_panel = 0

    def SetPixel(self, x, y, r, g, b):
        if not (0 <= x < self.width and 0 <= y < self.height) and (r or g or b):
            self.off_panel += 1
        super().SetPixel(x, y, r, g, b)


# The largest of each thing a 32-row countdown shows: every discipline in Joel's and Jen's totals plus the
# longest labels Peloton can send (OUTDOOR WALKING, 15 letters), a count from 1 to 4 digits (milestone_within
# has no upper limit) and a milestone up to 100,000.
_LONGEST_NAMES = [('cycling', 'Cycling'), ('strength', 'Strength'), ('stretching', 'Stretching'),
                  ('meditation', 'Meditation'), ('cardio', 'Cardio'), ('yoga', 'Yoga'),
                  ('bike_bootcamp', 'Bike Bootcamp'), ('tread_bootcamp', 'Tread Bootcamp'),
                  ('row_bootcamp', 'Row Bootcamp'), ('walking_outdoor', 'Outdoor Walking'),
                  ('running_outdoor', 'Outdoor Running'), ('dance_cardio', 'Dance Cardio'), (None, 'Workouts')]


@pytest.mark.parametrize('discipline, title', _LONGEST_NAMES)
def test_the_32_row_countdown_fits_the_largest_values(discipline, title):
    initialize_fonts(32)
    for left in (1, 10, 99, 1000):
        for target in (2200, 10000, 100000):
            matrix = _EdgeMatrix(height=32)
            state = {'total': target - left, 'target': target, 'previous': 0, 'title': title, 'discipline': discipline}
            assert CountdownScreen().render(matrix, state)
            assert matrix.off_panel == 0, (title, left, target)
            pixels = matrix.image.load()
            rows = sorted({y for x in range(64) for y in range(32) if pixels[x, y] != (0, 0, 0)})
            breaks = sum(1 for a, b in zip(rows, rows[1:]) if b > a + 1)
            assert breaks == 2, (title, left, target)   # three lines, a blank row between each


def test_a_32_row_milestone_too_wide_for_the_panel_is_left_off_not_clipped():
    """A target no font fits (a corrupt cache) leaves the number line empty; the rest still draws on the panel."""
    initialize_fonts(32)
    matrix = _EdgeMatrix(height=32)
    state = {'total': 10 ** 12 - 3, 'target': 10 ** 12, 'previous': 0, 'title': 'Cycling', 'discipline': 'cycling'}
    assert CountdownScreen().render(matrix, state)
    assert matrix.off_panel == 0
    pixels = matrix.image.load()
    assert not any(pixels[x, y] != (0, 0, 0) for x in range(64) for y in range(12, 21))
