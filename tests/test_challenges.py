"""The challenges page (ROADMAP item 24): parsing Peloton's challenges, the hourly fetch, the cache, the rotation
and the screen on both heights."""
import json
from unittest.mock import Mock

import pytest
import requests

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.challenge_screen import (BLUE, GOLD, RING_TRACK, TIER_COLORS, ChallengeScreen, compact_number,
                                         ring_pixels, tier_color)
from peloton import dashboard as dashboard_module
from peloton.cache import load_snapshot, save_snapshot
from peloton.challenges import (UNEARNED, format_number, parse_challenges, short_title, shown_challenges,
                                slim_challenge, tier_progress, valid_challenge)
from peloton.config import DEFAULTS
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix
from tests.test_dashboard import setup_dashboard

NOW = 1_794_000_000  # 2026-11-08
LATER = NOW + 30 * 86400


def entry(title='The Annual 2026', value=5503, shown='5,503', unit='min', tier=('5K', 5000.0),
          following=('6K', 6000.0), to_next='497', end=LATER, joined=True):
    """One entry of challenges/current, shaped like the real response (docs/PELOTON-API.md)."""
    def level(pair):
        return None if pair is None else {'id': pair[0], 'title': pair[0], 'metric_value': pair[1],
                                          'metric_display_unit': unit, 'has_reward': True}
    return {'challenge_summary': {'id': 'c' + title[:6], 'title': title, 'start_time': NOW - 86400,
                                  'end_time': end, 'fitness_disciplines': None},
            'participants': {'total_count': 650000},
            'progress': {'has_joined': joined, 'metric_value': value, 'metric_display_value': shown,
                         'metric_display_unit': unit, 'metric_display_value_to_next_tier': to_next,
                         'metric_display_unit_to_next_tier': unit,
                         'current_tier': level(tier), 'next_tier': level(following)}}


def response(*entries):
    return {'challenges': list(entries), 'next': {}, 'previous': {}, 'user': {'id': 'u'}}


TURKEY = entry('The Countdown to Turkey Burn Challenge', 0, '0', 'workouts', ('Unearned', 0.0), ('Gold', 18.0),
               '18', end=NOW + 11 * 86400)


# ---- parsing --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('title, short', [
    ('The Annual 2026', 'ANNUAL 2026'),
    ('The Countdown to Turkey Burn Challenge', 'TURKEY BURN'),
    ('November 2026 Rep Goal Challenge', 'REP GOAL'),
    ('November 2026 Meditation Challenge', 'MEDITATION'),
    ('  October   2025 Rowing Challenge ', 'ROWING'),
    ('Challenge Accepted', 'CHALLENGE ACCEPTED'),
    (None, ''),
])
def test_short_titles_drop_the_and_the_month_and_challenge(title, short):
    assert short_title(title) == short


def test_a_challenge_keeps_what_the_page_draws():
    challenge = slim_challenge(entry())
    assert challenge == {'id': 'cThe An', 'title': 'ANNUAL 2026', 'end_time': float(LATER), 'value': 5503.0,
                         'shown': '5,503', 'unit': 'MIN', 'tier': {'title': '5K', 'value': 5000.0},
                         'next': {'title': '6K', 'value': 6000.0}, 'to_next': '497'}
    assert valid_challenge(challenge) and tier_progress(challenge) == pytest.approx(0.503)


def test_peloton_quirks():
    """A tier title with a trailing space, an int or a float value, Unearned before the first tier, workouts
    read as classes."""
    challenge = slim_challenge(entry(tier=('1K ', 1000), value=1234.0, shown='1,234', to_next='766'))
    assert challenge['tier'] == {'title': '1K', 'value': 1000.0} and challenge['value'] == 1234.0
    turkey = slim_challenge(TURKEY)
    assert turkey['tier'] == {'title': UNEARNED, 'value': 0.0} and turkey['unit'] == 'CLASSES'
    assert slim_challenge(entry(tier=None))['tier'] == {'title': UNEARNED, 'value': 0.0}


def test_unformatted_or_odd_numbers_are_formatted_by_the_board():
    challenge = slim_challenge(entry(value=12.5, shown='<b>12.5</b>', unit='miles', tier=('Unearned', 0),
                                     following=('Bronze', 50), to_next=None))
    assert challenge['shown'] == '12.5' and challenge['to_next'] == '37.5' and challenge['unit'] == 'MILES'
    assert format_number(18000) == '18,000' and format_number(0.25) == '0.2'
    assert slim_challenge(entry(unit='laps'))['unit'] == 'LAPS'


@pytest.mark.parametrize('broken', [
    None, 'text', {}, {'challenge_summary': {'title': 'X'}}, {'progress': {'metric_value': 1}},
    entry(value=None), entry(value=True), entry(value=float('nan')), entry(title='   '),
])
def test_entries_that_cannot_be_shown_are_dropped(broken):
    assert slim_challenge(broken) is None


def test_parse_skips_unjoined_and_broken_entries():
    parsed = parse_challenges(response(entry(), entry(title='Not Mine', joined=False), {'progress': None}, TURKEY))
    assert [c['title'] for c in parsed] == ['ANNUAL 2026', 'TURKEY BURN']
    assert parse_challenges(response()) == []


@pytest.mark.parametrize('payload', [None, [], {'challenges': None}, {'challenges': {}}, {'data': []}])
def test_a_response_that_is_not_one_raises(payload):
    with pytest.raises(ValueError):
        parse_challenges(payload)


# ---- which to show ------------------------------------------------------------------------------------------
def test_shown_challenges_need_progress_a_next_tier_and_time_left():
    annual = slim_challenge(entry())
    soon = slim_challenge(entry('November 2026 Rep Goal Challenge', 1640, '1,640', 'reps', ('Bronze', 1500),
                                ('Silver', 3000), '1,360', end=NOW + 3600))
    top = slim_challenge(entry('Done', 20000, '20,000', following=None))
    ended = slim_challenge(entry('Ended', end=NOW - 1))
    endless = slim_challenge(entry('No End', end=None))
    zero = slim_challenge(TURKEY)
    shown = shown_challenges([annual, top, ended, zero, endless, soon, {'title': 'junk'}, None], NOW)
    assert [c['title'] for c in shown] == ['REP GOAL', 'ANNUAL 2026', 'NO END'], 'soonest ending first'
    assert shown_challenges(None, NOW) == [] and shown_challenges({'a': 1}, NOW) == []


def test_tier_progress_is_clamped():
    challenge = slim_challenge(entry())
    assert tier_progress({**challenge, 'value': 7000.0}) == 1.0
    assert tier_progress({**challenge, 'value': 10.0}) == 0.0
    assert tier_progress({**challenge, 'next': {'title': '5K', 'value': 5000.0}}) == 0.0


@pytest.mark.parametrize('damage', [
    {'title': ''}, {'title': 5}, {'shown': 5503}, {'unit': None}, {'value': 'x'}, {'value': True},
    {'tier': None}, {'tier': {'title': '5K'}}, {'next': {'title': '', 'value': 1}}, {'to_next': None},
    {'end_time': 'soon'},
])
def test_a_damaged_challenge_is_not_valid(damage):
    assert not valid_challenge({**slim_challenge(entry()), **damage})


# ---- the API call and the hourly fetch ---------------------------------------------------------------------
def test_the_client_asks_for_joined_challenges():
    from peloton.api import BASE, PelotonClient
    session = Mock()
    session.get.return_value.status_code = 200
    session.get.return_value.json.return_value = response(entry())
    assert PelotonClient(session).get_current_challenges('u1') == response(entry())
    session.get.assert_called_once_with(f'{BASE}/api/user/u1/challenges/current', params={'has_joined': 'true'},
                                        timeout=20)


def challenge_dashboard(tmp_path, monkeypatch, config=None):
    clock = {'now': 1000.0}
    monkeypatch.setattr(dashboard_module.time, 'monotonic', lambda: clock['now'])
    dashboard, client, token = setup_dashboard(tmp_path, config)
    client.get_current_challenges.return_value = response(entry(), TURKEY)
    return dashboard, client, clock


def test_challenges_are_fetched_hourly_and_cached(tmp_path, monkeypatch):
    dashboard, client, clock = challenge_dashboard(tmp_path, monkeypatch)
    dashboard.refresh()
    assert [c['title'] for c in dashboard.snapshot()['challenges']] == ['ANNUAL 2026', 'TURKEY BURN']
    clock['now'] += 300
    dashboard.refresh()
    assert client.get_current_challenges.call_count == 1, 'not again within the hour'
    clock['now'] += dashboard_module.CHALLENGES_REFRESH_SECONDS
    client.get_current_challenges.return_value = response(entry(value=5600, shown='5,600', to_next='400'))
    dashboard.refresh()
    assert client.get_current_challenges.call_count == 2
    assert [c['shown'] for c in dashboard.snapshot()['challenges']] == ['5,600']
    assert [c['shown'] for c in load_snapshot(dashboard.cache_path)['challenges']] == ['5,600']


@pytest.mark.parametrize('failure', [
    requests.HTTPError(response=Mock(status_code=400)), requests.ConnectionError('offline'),
    ValueError('bad JSON'), None,
])
def test_a_failed_fetch_keeps_the_last_list_and_retries_sooner(tmp_path, monkeypatch, failure):
    dashboard, client, clock = challenge_dashboard(tmp_path, monkeypatch)
    dashboard.refresh()
    before = dashboard.snapshot()['challenges']
    if failure is None:
        client.get_current_challenges.return_value = {'challenges': 'nope'}  # malformed
    else:
        client.get_current_challenges.side_effect = failure
    clock['now'] += dashboard_module.CHALLENGES_REFRESH_SECONDS
    dashboard.refresh()
    snapshot = dashboard.snapshot()
    assert snapshot['challenges'] == before and snapshot['status'] == 'ready', 'the refresh still succeeds'
    client.get_current_challenges.side_effect = None
    client.get_current_challenges.return_value = response()
    clock['now'] += dashboard_module.CHALLENGES_RETRY_SECONDS - 1
    dashboard.refresh()
    assert client.get_current_challenges.call_count == 2
    clock['now'] += 1
    dashboard.refresh()
    assert client.get_current_challenges.call_count == 3 and dashboard.snapshot()['challenges'] == []


def test_a_401_on_challenges_means_a_login_is_needed(tmp_path, monkeypatch):
    dashboard, client, _ = challenge_dashboard(tmp_path, monkeypatch)
    client.get_current_challenges.side_effect = requests.HTTPError(response=Mock(status_code=401))
    dashboard.refresh()
    assert dashboard.login_required


def test_no_fetch_while_the_page_is_off(tmp_path, monkeypatch):
    dashboard, client, _ = challenge_dashboard(tmp_path, monkeypatch, {'rotation': ['username', 'goals']})
    dashboard.refresh()
    client.get_current_challenges.assert_not_called()
    assert dashboard.snapshot()['challenges'] == []


def test_a_new_token_fetches_the_challenges_again(tmp_path, monkeypatch):
    import os
    dashboard, client, _ = challenge_dashboard(tmp_path, monkeypatch)
    dashboard.refresh()
    token = dashboard.token_path
    token.write_text('another-token')
    os.utime(token, ns=(1, 1))
    dashboard.refresh()
    assert client.get_current_challenges.call_count == 2


# ---- cache -------------------------------------------------------------------------------------------------
def _snapshot(**extra):
    return {'me': {'id': 'u'}, 'totals': {}, 'summaries': [], 'last_updated': 1.0, **extra}


def test_the_cache_keeps_challenges_and_drops_a_damaged_list(tmp_path):
    path = tmp_path / 'cache.json'
    good = parse_challenges(response(entry()))
    save_snapshot(path, _snapshot(challenges=good))
    assert load_snapshot(path)['challenges'] == good
    for damaged in ({'a': 1}, [good[0], {'title': 'half'}], 'text'):
        payload = json.loads(path.read_text())
        payload['snapshot']['challenges'] = damaged
        path.write_text(json.dumps(payload))
        restored = load_snapshot(path)
        assert 'challenges' not in restored and restored['me'] == {'id': 'u'}, damaged


# ---- rotation ----------------------------------------------------------------------------------------------
def test_one_page_per_shown_challenge(monkeypatch):
    import peloton_led
    monkeypatch.setattr(peloton_led.time, 'time', lambda: NOW)
    display = {**DEFAULTS, 'rotation': ['goals', 'challenges'], 'screen_durations': {'challenges': 7}}
    snapshot = {'summaries': [], 'status': 'ready', 'totals': {},
                'challenges': parse_challenges(response(entry(), TURKEY, entry('Gone', end=NOW - 5)))}
    pages = build_rotation_pages(snapshot, None, display, 'Joel', 64)
    assert [(name, state['title'], seconds) for name, state, seconds in pages] == [
        ('challenge', 'ANNUAL 2026', 7)]
    assert build_rotation_pages({**snapshot, 'challenges': 'junk'}, None, display, 'Joel', 64) == []


def test_challenges_is_a_rotation_screen_on_by_default(tmp_path):
    from peloton.config import load_config
    from settings_page.form import SCREEN_NAMES
    assert 'challenges' in DEFAULTS['rotation'] and 'challenges' in SCREEN_NAMES
    path = tmp_path / 'config.json'
    path.write_text('{"display": {"rotation": ["challenges"], "screen_durations": {"challenges": 6}}}')
    assert load_config(str(path))['display']['screen_durations'] == {'challenges': 6}


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
    assert ChallengeScreen().render(matrix, state)
    assert matrix.off_panel == 0
    return matrix


def lit(matrix, color=None, rows=None):
    pixels = matrix.image.load()
    return {(x, y) for x in range(matrix.width) for y in (rows or range(matrix.height))
            if pixels[x, y] != (0, 0, 0) and (color is None or pixels[x, y] == color)}


# The largest values a page can hold: 5- and 6-digit numbers, the widest tier names, the longest titles seen
# (and a made-up longer one), every unit.
LARGEST = [
    entry(),
    entry('November 2026 Rep Goal Challenge', 1640, '1,640', 'reps', ('Bronze', 1500), ('Silver', 3000), '1,360'),
    entry('The Annual 2026', 18000, '18,000', 'min', ('15K', 15000), ('18K', 18000), '10,000'),
    entry('November 2026 Rowing Challenge', 123456, '123,456', 'meters', ('Gold', 100000), ('Platinum', 250000),
          '126,544'),
    entry('November 2026 Meditation Challenge', 11, '11', 'workouts', ('Unearned', 0), ('Bronze', 15), '4'),
    entry('November 2026 Cycling Challenge', 123.4, '123.4', 'miles', ('Silver', 100), ('Gold', 200), '76.6'),
    entry('The Countdown to Turkey Burn Challenge', 11, '11', 'workouts', ('Unearned', 0), ('Gold', 18), '7'),
    entry('The Extraordinarily Long Holiday Countdown Spectacular Challenge', 3, '3', 'days', ('Unearned', 0),
          ('Bronze', 10), '7'),
    entry('Supercalifragilisticexpialidocious', 250, '250', 'kilocalories', ('Unearned', 0), ('Bronze', 500), '250'),
]


@pytest.mark.parametrize('raw', LARGEST, ids=lambda raw: raw['challenge_summary']['title'])
def test_64_rows_fit_the_largest_values_inside_the_ring(raw):
    state = slim_challenge(raw)
    matrix = draw(state, 64)
    ring = {(x, y): (r, g, b) for x, y, r, g, b in ring_pixels(round(tier_progress(state), 3),
                                                               tier_color(state['next']['title']))}
    pixels = matrix.image.load()
    assert all(pixels[x, y] == color for (x, y), color in ring.items()), 'text drawn over the ring'
    rows = [y for _, y in ring]
    assert not lit(matrix, rows=range(0, min(rows))) - lit(matrix, GOLD), 'the title row is all title'
    assert lit(matrix, GOLD, range(0, 9)), 'a title'
    assert lit(matrix, (255, 255, 255), range(max(rows) + 1, 64)), 'the line along the bottom'
    title = lit(matrix, GOLD, range(0, 9))
    assert get_text_width(loaded_fonts['titles'], state['title']) > 64 or min(x for x, _ in title) >= 1


@pytest.mark.parametrize('raw', LARGEST, ids=lambda raw: raw['challenge_summary']['title'])
def test_32_rows_fit_the_largest_values(raw):
    state = slim_challenge(raw)
    matrix = draw(state, 32)
    bar = lit(matrix, rows=range(21, 24))
    assert {x for x, _ in bar} == set(range(3, 61)), 'the bar spans the panel'
    assert lit(matrix, GOLD, range(0, 7)), 'the title'
    assert lit(matrix, (255, 255, 255), range(8, 19)), 'the number'
    bottom = lit(matrix, rows=range(25, 32))
    assert bottom and max(x for x, _ in bottom) <= 62


def test_the_32_row_bottom_line_puts_the_tier_left_when_both_fit():
    initialize_fonts(32)
    annual = draw(slim_challenge(entry()), 32)
    assert lit(annual, GOLD, range(25, 32)), '5K in gold on the left'
    rep = draw(slim_challenge(LARGEST[1]), 32)
    assert not lit(rep, TIER_COLORS['BRONZE'], range(25, 32)), '1,360 TO SILVER alone, centred'
    assert len(lit(rep, BLUE, range(21, 24))) == 5 * 3, '140 of the 1,500 to 3,000: 5 of 58 columns'


def test_the_ring_fills_clockwise_from_twelve_in_the_next_tiers_colour():
    initialize_fonts(64)
    half = {p[:2]: p[2:] for p in ring_pixels(0.5, GOLD)}
    assert half[(32, 15)] == GOLD and half[(52, 35)] == GOLD, 'the top and the right'
    assert half[(12, 35)] == RING_TRACK, 'the left is still track'
    empty = {p[2:] for p in ring_pixels(0.0, GOLD)}
    assert GOLD not in empty and RING_TRACK in empty
    full = {p[:2]: p[2:] for p in ring_pixels(1.0, TIER_COLORS['SILVER'])}
    assert full[(12, 35)] == TIER_COLORS['SILVER']
    assert tier_color('Bronze ') == TIER_COLORS['BRONZE'] and tier_color('6K') == GOLD


def test_the_ring_number_drops_its_comma_then_shrinks():
    initialize_fonts(64)
    from display.ui.challenge_screen import ring_number
    assert ring_number('5,503') == (loaded_fonts['title_bold'], '5,503')
    assert ring_number('18,000') == (loaded_fonts['title_bold'], '18000')
    assert ring_number('123,456') == (loaded_fonts['titles'], '123456')
    assert ring_number('12,345,678')[1] == '12346K'
    assert compact_number('abc') == 'abc' and compact_number('999') == '999'


@pytest.mark.parametrize('state', [None, {}, {'title': 'X'}, {**slim_challenge(entry()), 'next': None}])
def test_a_page_with_nothing_to_draw_says_so(state):
    initialize_fonts(64)
    assert ChallengeScreen().render(EdgeMatrix(height=64), state) is False


# ---- the README screenshot ---------------------------------------------------------------------------------
def test_render_challenges_draws_both_panel_sizes(tmp_path, capsys):
    from PIL import Image

    from scripts import render_challenges, render_logo
    out = tmp_path / 'challenges.png'
    render_challenges.main(['--out', str(out)])
    sheet = Image.open(out).convert('RGB')
    scale, gap, left = render_logo.SHEET_SCALE, render_logo.GAP, render_logo.LABEL_WIDTH
    top = gap
    for height in (64, 32):
        initialize_fonts(height)
        for index, state in enumerate(render_challenges.PAGES):
            assert valid_challenge(state)
            matrix = ImageMatrix(64, height)
            assert ChallengeScreen().render(matrix, state)
            x = left + index * (64 * scale + gap)
            panel = sheet.crop((x, top, x + 64 * scale, top + height * scale))
            assert panel.tobytes() == matrix.image.resize(panel.size, Image.NEAREST).tobytes()
        top += height * scale + gap * 2
    assert 'Wrote' in capsys.readouterr().out


def test_render_challenges_stops_on_a_page_it_cannot_draw(monkeypatch):
    from scripts import render_challenges
    monkeypatch.setattr(render_challenges, 'PAGES', [{'title': 'X'}])
    with pytest.raises(RuntimeError, match='drew nothing'):
        render_challenges.panels(64)


def test_the_remaining_line_shortens_to_fit():
    from display.ui.challenge_screen import remaining_line
    initialize_fonts(64)
    font, state = loaded_fonts['stats'], slim_challenge(entry())
    assert remaining_line(state, font, 64) == '497 TO 6K'
    assert remaining_line({**state, 'next': {'title': 'PLATINUM PLUS', 'value': 1}}, font, 64) == '497 TO GO'
    assert remaining_line({**state, 'to_next': '12,345,678,901'}, font, 40) == '12,345,678,901'
