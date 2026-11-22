"""The Club Peloton page (ROADMAP item 25): parsing the members-score response, the fetch and its timing, the
cache, the rotation and the screen on both heights."""

import json
from unittest.mock import Mock

import pytest
import requests

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.club_screen import (
    BAR_LEFT,
    BAR_RIGHT,
    BAR_TRACK,
    BOOST,
    FACET_SHADES,
    GEM_32,
    GEM_64,
    GEM_COLORS,
    GEM_ROWS,
    SHAPE_OF,
    TEXT_COLORS,
    ClubScreen,
    gem_pixels,
    next_line,
    points_line,
)
from peloton import dashboard as dashboard_module
from peloton import dashboard_fetch
from peloton.cache import load_snapshot, save_snapshot
from peloton.config import DEFAULTS
from peloton.demo import demo_club
from peloton.feeds.club import LEVELS, NOT_A_MEMBER, club_page, gem_kind, level_from_me, parse_score, tier_fraction, valid_club
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix
from tests.test_dashboard import setup_dashboard

NOW = 1_794_000_000  # 2026-11-08
BOOST_ENDS = '2026-12-01T04:59:00Z'  # 1_796_101_140


def segment(label, low, high, following):
    return {'label': label, 'min_points': low, 'max_points': high, 'next_level_name': following}


def score(level='Gold III', points=13659, base=2000, top=15000, segments=None, ignore=False, boost=None):
    """A members-score v2 response, shaped like the real one (docs/PELOTON-API.md), minus the media URLs."""
    if segments is None:
        segments = [
            segment('Gold I', 2000, 4000, 'Gold II'),
            segment('Gold II', 4000, 6000, 'Gold III'),
            segment('Gold III', 6000, 15000, 'Champion'),
        ]
    return {
        'badge_level_name': level,
        'total_earned_points': points,
        'previous_total_earned_points': points - 5,
        'points_since_last_visit': 5,
        'level_slug': 8,
        'boost': boost,
        'earn_points': [],
        'progress_bar': {
            'badge_level_name': level,
            'score': points,
            'end_label': None,
            'ignore_segments_on_profile': ignore,
            'segment_tiers_max_points': segments,
            'tier_base_points': base,
            'tier_max_points': top,
        },
    }


ACTIVE = {'boost_id': 'x', 'status': 'active', 'expires_at': BOOST_ENDS, 'title': 'Double points'}
# A Champion's response: the segments are the whole ladder, with odd mins, and not drawn on the profile.
CHAMPION = score(
    'Champion',
    15666,
    15000,
    30000,
    ignore=True,
    segments=[
        segment('Bronze', 50, 100, 'Silver I'),
        segment('Silver', 900, 2000, 'Gold I'),
        segment('Gold', 6000, 15000, 'Champion'),
        segment('Champion', 15000, 30000, 'Legend'),
        segment('Legend', 30000, None, ''),
    ],
)
LEGEND = score('Legend', 31205, 30000, None, ignore=True, segments=CHAMPION['progress_bar']['segment_tiers_max_points'])


# ---- parsing --------------------------------------------------------------------------------------------------
def test_a_score_keeps_what_the_page_draws():
    assert parse_score(score(boost=ACTIVE), NOW) == {
        'level': 'GOLD III',
        'points': 13659,
        'tier_min': 2000,
        'tier_max': 15000,
        'marks': [4000, 6000],
        'next': 'CHAMPION',
        'to_next': 1341,
        'boost_until': 1_796_101_140.0,
    }


def test_a_champion_goes_for_legend_with_no_marks():
    club = parse_score(CHAMPION, NOW)
    assert (club['level'], club['next'], club['to_next'], club['marks']) == ('CHAMPION', 'LEGEND', 14334, [])
    assert tier_fraction(club) == pytest.approx(666 / 15000)


def test_a_legend_has_nothing_above():
    club = parse_score(LEGEND, NOW)
    assert (club['tier_max'], club['next'], club['to_next']) == (None, None, None)
    assert tier_fraction(club) == 1.0 and valid_club(club)


def test_a_level_the_segments_dont_name_uses_the_one_its_points_are_in():
    club = parse_score(score(level='Gold 3', points=5000), NOW)
    assert (club['next'], club['to_next']) == ('GOLD III', 1000)


def test_with_no_segment_the_tier_top_is_the_target():
    club = parse_score(score(segments=[{'label': 'Other', 'min_points': 0, 'max_points': 10, 'next_level_name': 'X'}, 'junk']), NOW)
    assert (club['next'], club['to_next'], club['marks']) == (None, None, [])
    club = parse_score(score(segments=[segment('Gold III', 6000, None, 'Champion')]), NOW)
    assert (club['next'], club['to_next']) == ('CHAMPION', 1341), 'the tier top when the segment has none'


@pytest.mark.parametrize(
    'boost',
    [
        None,
        {**ACTIVE, 'status': 'expired'},
        {**ACTIVE, 'expires_at': '2026-11-01T00:00:00Z'},
        {**ACTIVE, 'expires_at': 'soon'},
        {**ACTIVE, 'expires_at': None},
        'yes',
        {'status': 'active'},
    ],
)
def test_only_a_running_boost_counts(boost):
    assert parse_score(score(boost=boost), NOW)['boost_until'] is None


def test_a_boost_with_no_zone_is_utc():
    assert parse_score(score(boost={**ACTIVE, 'expires_at': '2026-12-01T04:59:00'}), NOW)['boost_until'] == 1_796_101_140.0


def test_odd_tier_figures_are_made_safe():
    club = parse_score(score(points=1500, base=2000, top=1000), NOW)
    assert (club['tier_min'], club['tier_max']) == (0, None), 'a base above the points, a top below them'
    club = parse_score(score(points=5000, base=6000, top=4000), NOW)
    assert (club['tier_min'], club['tier_max']) == (0, None), 'a top below the base'
    club = parse_score(score(points=13659.7, base='2000', top=True), NOW)
    assert (club['points'], club['tier_min'], club['tier_max']) == (13659, 0, None)
    club = parse_score({**score(), 'total_earned_points': None}, NOW)
    assert club['points'] == 13659, "the bar's score when the total is missing"
    club = parse_score({**score(), 'badge_level_name': None}, NOW)
    assert club['level'] == 'GOLD III', "the bar's level name when the top one is missing"


@pytest.mark.parametrize(
    'payload',
    [
        None,
        [],
        {'progress_bar': None},
        {'badge_level_name': 'Gold III', 'total_earned_points': 5},
        {**score(), 'badge_level_name': '', 'progress_bar': {**score()['progress_bar'], 'badge_level_name': None}},
        {**score(), 'total_earned_points': -1, 'progress_bar': {**score()['progress_bar'], 'score': 'lots'}},
    ],
)
def test_a_response_that_is_not_a_score_raises(payload):
    with pytest.raises(ValueError):
        parse_score(payload, NOW)


@pytest.mark.parametrize(
    'damage',
    [
        {'level': ''},
        {'level': 5},
        {'points': -1},
        {'points': 'many'},
        {'points': True},
        {'tier_min': None},
        {'tier_min': 20000},
        {'tier_max': 1000},
        {'tier_max': 'x'},
        {'marks': None},
        {'marks': ['a']},
        {'next': ''},
        {'next': 5},
        {'to_next': -3},
        {'next': None, 'to_next': 5},
        {'boost_until': 'later'},
        {'boost_until': float('nan')},
    ],
)
def test_a_damaged_record_is_not_valid(damage):
    assert not valid_club({**parse_score(score(), NOW), **damage})


def test_not_a_member_and_non_records():
    assert valid_club(NOT_A_MEMBER) and not valid_club(None) and not valid_club('GOLD')


@pytest.mark.parametrize(
    'me, level',
    [
        ({'badge_level': 8}, 'GOLD III'),
        ({'badge_level': 0}, 'BRONZE I'),
        ({'badge_level': 10}, 'LEGEND'),
        ({'badge_level': 11}, None),
        ({'badge_level': -1}, None),
        ({'badge_level': True}, None),
        ({'badge_level': '8'}, None),
        ({}, None),
        (None, None),
        ('me', None),
    ],
)
def test_the_level_from_the_profile(me, level):
    assert level_from_me(me) == level


def test_gem_kinds():
    assert [gem_kind(level) for level in LEVELS] == ['BRONZE'] * 3 + ['SILVER'] * 3 + ['GOLD'] * 3 + ['CHAMPION', 'LEGEND']
    assert gem_kind('PLATINUM') == 'GOLD' and gem_kind('') == 'GOLD' and gem_kind(None) == 'GOLD'


def test_the_page_state():
    club = parse_score(score(boost=ACTIVE), NOW)
    page = club_page(club, {'badge_level': 2}, NOW)
    assert page['boost'] and page['kind'] == 'GOLD' and page['points'] == 13659, 'the score beats the profile'
    assert club_page(club, None, 1_796_101_140)['boost'] is False, 'a boost ends on time'
    assert club_page(None, {'badge_level': 9}, NOW) == {'level': 'CHAMPION', 'kind': 'CHAMPION', 'points': None, 'boost': False}
    assert club_page({'level': 'junk'}, {'badge_level': 9}, NOW)['points'] is None
    assert club_page(NOT_A_MEMBER, {'badge_level': 9}, NOW) is None, 'no score: no page'
    assert club_page(None, {}, NOW) is None


def test_tier_fraction_is_clamped():
    club = parse_score(score(), NOW)
    assert tier_fraction(club) == pytest.approx(11659 / 13000)
    assert tier_fraction(club, 0) == 0.0 and tier_fraction(club, 99999) == 1.0


def test_the_demo_club_is_a_valid_record():
    club = demo_club(NOW)
    assert valid_club(club) and club['boost_until'] == NOW + 7 * 86400 and club['to_next'] == 1341


# ---- the client ------------------------------------------------------------------------------------------------
def client_with(status, body=None):
    from peloton.api import PelotonClient

    session = Mock()
    session.get.return_value.status_code = status
    session.get.return_value.json.return_value = body
    session.get.return_value.raise_for_status.side_effect = requests.HTTPError(response=Mock(status_code=status)) if status >= 400 else None
    return PelotonClient(session), session


def test_the_client_asks_the_members_score_host():
    client, session = client_with(200, score())
    assert client.get_club_score('u1') == score()
    session.get.assert_called_once_with('https://members-score.onepeloton.com/v2/user/u1/score', timeout=20)


def test_no_score_is_none():
    client, _ = client_with(404)
    assert client.get_club_score('u1') is None


def test_a_401_from_the_score_host_does_not_reject_the_token():
    client, _ = client_with(401)
    with pytest.raises(requests.HTTPError):
        client.get_club_score('u1')
    assert client.login_required is False


def test_a_score_that_is_not_an_object_raises():
    client, _ = client_with(200, [1, 2])
    with pytest.raises(ValueError):
        client.get_club_score('u1')


# ---- the fetch -------------------------------------------------------------------------------------------------
def club_dashboard(tmp_path, monkeypatch, config=None):
    clock = {'now': 1000.0}
    monkeypatch.setattr(dashboard_module.time, 'monotonic', lambda: clock['now'])
    dashboard, client, token = setup_dashboard(tmp_path, config)
    client.get_club_score.return_value = score(boost=ACTIVE)
    return dashboard, client, clock


def test_the_score_is_fetched_every_6_hours_and_cached(tmp_path, monkeypatch):
    dashboard, client, clock = club_dashboard(tmp_path, monkeypatch)
    dashboard.refresh()
    assert dashboard.snapshot()['club']['points'] == 13659
    clock['now'] += 300
    dashboard.refresh()
    assert client.get_club_score.call_count == 1, 'not again within 6 hours'
    clock['now'] += dashboard_fetch.CLUB_REFRESH_SECONDS
    client.get_club_score.return_value = score(points=13700)
    dashboard.refresh()
    assert client.get_club_score.call_count == 2
    assert load_snapshot(dashboard.cache_path)['club']['points'] == 13700


def test_a_new_workout_asks_again_at_once(tmp_path, monkeypatch):
    dashboard, client, clock = club_dashboard(tmp_path, monkeypatch)
    dashboard.refresh()
    clock['now'] += 300
    client.history = [dict(client.history[0], id='new-workout')] + client.history
    dashboard.refresh()
    assert client.get_club_score.call_count == 2
    clock['now'] += 300
    dashboard.refresh()
    assert client.get_club_score.call_count == 2, 'the same newest workout: no ask'


@pytest.mark.parametrize(
    'failure',
    [
        requests.HTTPError(response=Mock(status_code=401)),
        requests.HTTPError(response=Mock(status_code=500)),
        requests.HTTPError(response=None),
        requests.ConnectionError('offline'),
        ValueError('bad JSON'),
        None,
    ],
)
def test_a_failed_fetch_keeps_the_last_figures_and_retries_sooner(tmp_path, monkeypatch, failure):
    dashboard, client, clock = club_dashboard(tmp_path, monkeypatch)
    dashboard.refresh()
    before = dashboard.snapshot()['club']
    if failure is None:
        client.get_club_score.return_value = {'progress_bar': 'nope'}  # malformed
    else:
        client.get_club_score.side_effect = failure
    clock['now'] += dashboard_fetch.CLUB_REFRESH_SECONDS
    dashboard.refresh()
    snapshot = dashboard.snapshot()
    assert snapshot['club'] == before and snapshot['status'] == 'ready', 'the refresh still succeeds'
    assert not dashboard.login_required, 'the undocumented host never asks for a login'
    client.get_club_score.side_effect = None
    client.get_club_score.return_value = CHAMPION
    clock['now'] += dashboard_fetch.CLUB_RETRY_SECONDS - 1
    dashboard.refresh()
    assert client.get_club_score.call_count == 2
    clock['now'] += 1
    dashboard.refresh()
    assert client.get_club_score.call_count == 3 and dashboard.snapshot()['club']['level'] == 'CHAMPION'


def test_no_score_means_no_page(tmp_path, monkeypatch):
    dashboard, client, _ = club_dashboard(tmp_path, monkeypatch)
    client.get_club_score.return_value = None
    dashboard.refresh()
    assert dashboard.snapshot()['club'] == NOT_A_MEMBER
    assert load_snapshot(dashboard.cache_path)['club'] == NOT_A_MEMBER


def test_no_fetch_while_the_page_is_off(tmp_path, monkeypatch):
    dashboard, client, _ = club_dashboard(tmp_path, monkeypatch, {'rotation': ['username', 'goals']})
    dashboard.refresh()
    client.get_club_score.assert_not_called()
    assert dashboard.snapshot()['club'] is None


def test_a_new_token_fetches_the_score_again(tmp_path, monkeypatch):
    import os

    dashboard, client, _ = club_dashboard(tmp_path, monkeypatch)
    dashboard.refresh()
    token = dashboard.token_path
    token.write_text('another-token')
    os.utime(token, ns=(1, 1))
    dashboard.refresh()
    assert client.get_club_score.call_count == 2


def test_the_profile_keeps_the_badge_level(tmp_path, monkeypatch):
    dashboard, client, _ = club_dashboard(tmp_path, monkeypatch)
    client.get_me.return_value = {**client.get_me.return_value, 'badge_level': 8, 'badge_url': 'https://x'}
    dashboard.refresh()
    me = dashboard.snapshot()['me']
    assert me['badge_level'] == 8 and 'badge_url' not in me


def test_the_demo_dashboard_has_a_club(tmp_path):
    from peloton.dashboard import Dashboard

    dashboard = Dashboard(tmp_path / 'token', {}, demo=True)
    assert valid_club(dashboard.snapshot()['club'])


# ---- cache -------------------------------------------------------------------------------------------------
def _snapshot(**extra):
    return {'me': {'id': 'u'}, 'totals': {}, 'summaries': [], 'last_updated': 1.0, **extra}


def test_the_cache_keeps_the_club_and_drops_a_damaged_record(tmp_path):
    path = tmp_path / 'cache.json'
    good = parse_score(score(), NOW)
    save_snapshot(path, _snapshot(club=good))
    assert load_snapshot(path)['club'] == good
    for damaged in ({'level': 'GOLD'}, 'text', [good], {**good, 'points': -5}):
        payload = json.loads(path.read_text())
        payload['snapshot']['club'] = damaged
        path.write_text(json.dumps(payload))
        restored = load_snapshot(path)
        assert 'club' not in restored and restored['me'] == {'id': 'u'}, damaged


# ---- rotation ----------------------------------------------------------------------------------------------
def club_pages(snapshot, monkeypatch, now=NOW):
    import peloton_led

    monkeypatch.setattr(peloton_led.time, 'time', lambda: now)
    display = {**DEFAULTS, 'rotation': ['goals', 'club'], 'screen_durations': {'club': 7}}
    return build_rotation_pages({'summaries': [], 'status': 'ready', 'totals': {}, **snapshot}, None, display, 'Joel', 64)


def test_one_club_page(monkeypatch):
    pages = club_pages({'club': parse_score(score(boost=ACTIVE), NOW), 'me': {'badge_level': 2}}, monkeypatch)
    assert [(name, state['level'], state['boost'], seconds) for name, state, seconds in pages] == [('club', 'GOLD III', True, 7)]


def test_the_profile_level_until_the_score_arrives(monkeypatch):
    pages = club_pages({'me': {'id': 'u', 'badge_level': 8}}, monkeypatch)
    assert [(name, state['level'], state['points']) for name, state, _ in pages] == [('club', 'GOLD III', None)]


@pytest.mark.parametrize('snapshot', [{'club': NOT_A_MEMBER, 'me': {'badge_level': 8}}, {'club': 'junk'}, {}])
def test_no_club_page(monkeypatch, snapshot):
    assert club_pages(snapshot, monkeypatch) == []


def test_club_is_a_rotation_screen_on_by_default(tmp_path):
    from peloton.config import load_config
    from settings_page.form import SCREEN_NAMES
    from settings_page.page import shows_for

    assert 'club' in DEFAULTS['rotation'] and 'club' in SCREEN_NAMES
    path = tmp_path / 'config.json'
    path.write_text('{"display": {"rotation": ["club"], "screen_durations": {"club": 6}}}')
    display = load_config(str(path))['display']
    assert display['screen_durations'] == {'club': 6}
    assert shows_for('club', {**DEFAULTS, **display}, 64) == '6 s.'


# ---- the screen --------------------------------------------------------------------------------------------
class EdgeMatrix(ImageMatrix):
    """Counts lit pixels drawn off the panel (ImageMatrix drops them silently)."""

    def Clear(self):
        super().Clear()
        self.off_panel = 0

    def SetPixel(self, x, y, r, g, b):
        if not (0 <= x < self.width and 0 <= y < self.height) and (r or g or b):
            self.off_panel += 1
        super().SetPixel(x, y, r, g, b)


def draw(state, height):
    initialize_fonts(height)
    matrix = EdgeMatrix(height=height)
    assert ClubScreen().render(matrix, state)
    assert matrix.off_panel == 0
    return matrix


def lit(matrix, color=None, rows=None, columns=None):
    pixels = matrix.image.load()
    return {
        (x, y)
        for x in (columns or range(matrix.width))
        for y in (rows or range(matrix.height))
        if pixels[x, y] != (0, 0, 0) and (color is None or pixels[x, y] == color)
    }


def record(level, points, tier, marks, following, to_next, boost=True):
    return {
        'level': level,
        'points': points,
        'tier_min': tier[0],
        'tier_max': tier[1],
        'marks': marks,
        'next': following,
        'to_next': to_next,
        'boost_until': NOW + 1 if boost else None,
    }


# Every level, the widest names (`SILVER III`, `CHAMPION`), the biggest figures (6-digit points, 5-digit
# remainders), the widest next-level names, a boost on each.
LARGEST = [
    record('BRONZE I', 0, (0, 100), [10, 50], 'BRONZE II', 10),
    record('BRONZE III', 99, (0, 100), [10, 50], 'SILVER I', 1),
    record('SILVER III', 1999, (100, 2000), [500, 1000], 'GOLD I', 1),
    record('SILVER II', 500, (100, 2000), [500, 1000], 'SILVER III', 500),
    record('GOLD II', 4000, (2000, 15000), [4000, 6000], 'GOLD III', 2000),
    record('GOLD III', 6000, (2000, 15000), [4000, 6000], 'CHAMPION', 9000),
    record('CHAMPION', 15000, (15000, 30000), [], 'LEGEND', 15000),
    record('LEGEND', 999999, (30000, None), [], None, None),
    record('PLATINUM SUPREME', 123456, (100000, 200000), [], 'CHAMPION SUPREMO', 76544),
]


@pytest.mark.parametrize('club', LARGEST, ids=lambda club: club['level'])
def test_64_rows_fit_the_largest_values(club):
    state = club_page(club, None, NOW)
    matrix = draw(state, 64)
    gem = {(22 + x, 1 + y) for x, y, *_ in gem_pixels(state['kind'], GEM_64)}
    assert lit(matrix, rows=range(0, 21)) == gem, 'the gem alone at the top'
    corner = lit(matrix, BOOST, range(57, 64), range(0, 10))
    if club['level'] == 'PLATINUM SUPREME':
        assert not corner, 'no room beside CHAMPION SUPREMO: no 2X'
    else:
        assert corner, '2X in the bottom left corner'
    assert lit(matrix, TEXT_COLORS[state['kind']], range(21, 34)), 'the level in its colour'
    assert lit(matrix, (255, 255, 255), range(34, 43)), 'the points'
    bar = lit(matrix, rows=range(45, 48))
    assert {x for x, _ in bar} - set(range(BAR_LEFT, BAR_RIGHT + 1)) == set()
    assert {BAR_LEFT, BAR_RIGHT} <= {x for x, _ in bar}, 'the bar spans the panel'
    assert not lit(matrix, rows=[44, 48]), 'a clear row above and below the bar'
    assert lit(matrix, rows=range(49, 64)), 'the line to the next level'
    columns = {x for x, _ in lit(matrix, rows=range(21, 64))}
    assert min(columns) >= 1 and max(columns) <= 62, 'a pixel clear of each edge'


@pytest.mark.parametrize('club', LARGEST, ids=lambda club: club['level'])
def test_32_rows_fit_the_largest_values(club):
    state = club_page(club, None, NOW)
    matrix = draw(state, 32)
    gem = {(1 + x, 1 + y) for x, y, *_ in gem_pixels(state['kind'], GEM_32)}
    assert lit(matrix, rows=range(0, 16), columns=range(0, 16)) == gem, 'the gem alone at the left'
    assert lit(matrix, TEXT_COLORS[state['kind']], range(0, 8), range(16, 64)), 'the level'
    assert lit(matrix, (255, 255, 255), range(8, 15), range(16, 64)), 'the points'
    assert not lit(matrix, rows=[15, 16, 17, 18, 22, 23]), 'clear rows around the bar'
    assert {BAR_LEFT, BAR_RIGHT} <= {x for x, _ in lit(matrix, rows=range(19, 22))}
    bottom = lit(matrix, rows=range(24, 32))
    assert bottom and max(x for x, _ in bottom) <= 62


def test_the_bar_fills_the_tier_with_a_gap_at_each_level():
    state = club_page(record('GOLD III', 13659, (2000, 15000), [4000, 6000], 'CHAMPION', 1341, False), None, NOW)
    matrix = draw(state, 64)
    pixels = matrix.image.load()
    row = [pixels[x, 45] for x in range(BAR_LEFT, BAR_RIGHT + 1)]
    gaps = [BAR_LEFT + i for i, color in enumerate(row) if color == (0, 0, 0)]
    assert gaps == [BAR_LEFT + round(58 * 2000 / 13000), BAR_LEFT + round(58 * 4000 / 13000)]
    assert row.count(GEM_COLORS['GOLD']) == round(58 * 11659 / 13000) - 2 and row[-1] == BAR_TRACK
    assert not lit(matrix, BOOST, range(57, 64), range(0, 10)), 'no boost, no 2X'
    assert lit(matrix, TEXT_COLORS['CHAMPION'], range(56, 64)), 'CHAMPION in its own colour'


def test_the_32_row_bottom_line_puts_2x_left_when_both_fit():
    gold = draw(club_page(LARGEST[5], None, NOW), 32)
    assert lit(gold, BOOST, range(24, 32)), '2X with 9,000 TO GO'
    champion = draw(club_page(LARGEST[6], None, NOW), 32)
    assert not lit(champion, BOOST, range(24, 32)), '15,000 TO LEGEND alone, centred'


def test_a_legend_has_a_full_bar_and_top_level():
    initialize_fonts(64)
    state = club_page(LARGEST[7], None, NOW)
    assert next_line(state, loaded_fonts['stats'], 62) == 'TOP LEVEL'
    matrix = draw(state, 64)
    assert len(lit(matrix, GEM_COLORS['LEGEND'], range(45, 48))) == 58 * 3


def test_the_level_only_page():
    for height in (64, 32):
        matrix = draw(club_page(None, {'badge_level': 9}, NOW), height)
        assert lit(matrix, TEXT_COLORS['CHAMPION'])
        # Away from the gem (top on 64 rows, left on 32): nothing in white, so no points line or bar.
        rows, columns = (range(21, 64), None) if height == 64 else (None, range(16, 64))
        assert not lit(matrix, (255, 255, 255), rows, columns), 'no points, no bar'


def test_lines_shorten_to_fit():
    initialize_fonts(32)
    font = loaded_fonts['info']
    state = club_page(LARGEST[5], None, NOW)
    assert next_line(state, font, 100) == '9,000 TO CHAMPION'
    assert next_line(state, font, 64) == '9000 TO CHAMPION'
    assert next_line(state, font, 62) == '9,000 TO GO'
    assert next_line({**state, 'to_next': None}, font, 62) == ''
    assert points_line(123456, font, 44) == '123,456 PTS'
    assert points_line(123456, font, 40) == '123456 PTS'
    assert points_line(1234567, font, 36) == '1,234,567'
    assert points_line(1234567, font, 30) == '1234567'
    assert points_line(1234567, font, 2) == ''


def test_gems_are_cached_and_lit_in_their_own_colours():
    assert gem_pixels('GOLD', 20) is gem_pixels('GOLD', 20)
    for kind in GEM_COLORS:
        for size in (GEM_64, GEM_32):
            pixels = gem_pixels(kind, size)
            assert len(pixels) > size * size // 3 and all(0 <= x < size and 0 <= y < size for x, y, *_ in pixels)
    assert gem_pixels('PLATINUM', GEM_32) == gem_pixels('GOLD', GEM_32)
    red = [(r, g, b) for *_, r, g, b in gem_pixels('LEGEND', GEM_64)]
    assert all(r >= g and r >= b for r, g, b in red)
    corners = {(r, g, b) for *_, r, g, b in gem_pixels('CHAMPION', GEM_64)}
    assert any(b > r for r, g, b in corners), "Champion's blue corner facets"


@pytest.mark.parametrize('key', sorted(GEM_ROWS))
def test_the_gem_grids_are_square_symmetric_pixel_art(key):
    shape, size = key
    rows = GEM_ROWS[key]
    assert len(rows) == size and all(len(row) == size for row in rows)
    assert all(set(row) <= set(FACET_SHADES) | {'.'} for row in rows), 'only known facets'
    assert all([c == '.' for c in row] == [c == '.' for c in row[::-1]] for row in rows), 'a symmetric outline'
    assert sum(row.count('#') for row in rows) > 0, 'a flat top face'


def test_the_gems_are_crisp_flat_facets():
    """Each facet is one colour: a gem has no more colours than facets (no blended edges)."""
    for kind in GEM_COLORS:
        for size in (GEM_64, GEM_32):
            rows = GEM_ROWS[(SHAPE_OF.get(kind, 'HEX'), size)]
            facets = set(''.join(rows)) - {'.'}
            assert len({tuple(p[2:]) for p in gem_pixels(kind, size)}) <= len(facets)


@pytest.mark.parametrize(
    'state',
    [
        None,
        {},
        'GOLD',
        {'level': 'GOLD III', 'kind': 'GOLD', 'points': None},
        {'level': 'GOLD III', 'kind': 'RUBY', 'points': None, 'boost': False},
        {'level': '', 'kind': 'GOLD', 'points': None, 'boost': False},
        {'level': 'GOLD III', 'kind': 'GOLD', 'points': 5, 'boost': False},
    ],
)
def test_a_page_with_nothing_to_draw_says_so(state):
    initialize_fonts(64)
    assert ClubScreen().render(EdgeMatrix(height=64), state) is False


# ---- the README screenshot ---------------------------------------------------------------------------------
def test_render_club_draws_both_panel_sizes(tmp_path, capsys):
    from PIL import Image

    from scripts import render_club, render_logo

    out = tmp_path / 'club.png'
    render_club.main(['--out', str(out)])
    sheet = Image.open(out).convert('RGB')
    scale, gap, left = render_logo.SHEET_SCALE, render_logo.GAP, render_logo.LABEL_WIDTH
    top = gap
    for height in (64, 32):
        initialize_fonts(height)
        for index, state in enumerate(render_club.PAGES):
            matrix = ImageMatrix(64, height)
            assert ClubScreen().render(matrix, state)
            x = left + index * (64 * scale + gap)
            panel = sheet.crop((x, top, x + 64 * scale, top + height * scale))
            assert panel.tobytes() == matrix.image.resize(panel.size, Image.NEAREST).tobytes()
        top += height * scale + gap * 2
    assert 'Wrote' in capsys.readouterr().out


def test_render_club_stops_on_a_page_it_cannot_draw(monkeypatch):
    from scripts import render_club

    monkeypatch.setattr(render_club, 'PAGES', [None])
    with pytest.raises(RuntimeError, match='drew nothing'):
        render_club.panels(64)


def test_widest_names_fit_their_fonts():
    initialize_fonts(64)
    assert get_text_width(loaded_fonts['bold'], 'CHAMPION') <= 62
