"""The challenges page (ROADMAP item 24): parsing Peloton's challenges, the hourly fetch, the cache, the rotation
and the screen on both heights."""
import json
from unittest.mock import Mock

import pytest
import requests

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.challenge_screen import (BLUE, GOLD, INTRO_SECONDS, RING_TRACK, SWEEP_SECONDS, TIER_COLORS, ChallengeScreen,
                                         compact_number, counted_shown, fitted_title, ring_pixels, tier_color)
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


@pytest.mark.parametrize('month, short', [('January', 'JAN'), ('February', 'FEB'), ('March', 'MAR'),
                                          ('April', 'APR'), ('May', 'MAY'), ('June', 'JUN'), ('July', 'JUL'),
                                          ('August', 'AUG'), ('September', 'SEP'), ('October', 'OCT'),
                                          ('November', 'NOV'), ('December', 'DEC')])
def test_every_month_is_kept_abbreviated_and_the_year_dropped(month, short):
    assert short_title(f'{month} 2026 Rep Goal Challenge') == f'{short} REP GOAL'
    assert short_title(f'{month.upper()} 2027 Rep Goal Challenge') == f'{short} REP GOAL'


# ---- parsing --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('title, short', [
    ('The Annual 2026', 'ANNUAL 2026'),
    ('The Countdown to Turkey Burn Challenge', 'TURKEY BURN'),
    ('November 2026 Rep Goal Challenge', 'NOV REP GOAL'),
    ('November 2026 Meditation Challenge', 'NOV MEDITATION'),
    ('  October   2025 Rowing Challenge ', 'OCT ROWING'),
    ('the Rowing Challenge: December 2026', 'DEC ROWING CHALLENGE:'),
    ('Rep Goal November 2026 Challenge', 'NOV REP GOAL'),
    ('NOVEMBER 2026 rep goal challenge', 'NOV REP GOAL'),
    ('May 2027 Strength Challenge', 'MAY STRENGTH'),
    ('May the Fourth Challenge', 'MAY THE FOURTH'),
    ('Challenge Accepted', 'CHALLENGE ACCEPTED'),
    (None, ''),
])
def test_short_titles_drop_the_and_the_year_and_challenge_but_keep_the_month(title, short):
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
    assert [c['title'] for c in shown] == ['NOV REP GOAL', 'ANNUAL 2026', 'NO END'], 'soonest ending first'
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


def draw(state, height, at=INTRO_SECONDS):
    """The page `at` seconds after it appeared (by default settled)."""
    initialize_fonts(height)
    matrix = EdgeMatrix(height=height)
    screen = ChallengeScreen()
    screen.on_enter(matrix, state)
    screen.update(at)
    assert screen.render(matrix, state)
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
    entry('September 2026 Strength Rep Goal Challenge', 1640, '1,640', 'reps', ('Bronze', 1500), ('Silver', 3000),
          '1,360'),
    entry('September 2026 Supercalifragilisticexpialidocious Challenge', 12, '12', 'reps', ('Unearned', 0),
          ('Bronze', 15), '3'),
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


@pytest.mark.parametrize('height', [64, 32])
@pytest.mark.parametrize('title', ['September 2026 Strength Rep Goal Challenge',
                                   'September 2026 Supercalifragilisticexpialidocious Challenge',
                                   'November 2026 Rep Goal Challenge'])
def test_a_long_title_keeps_its_month_and_fits(title, height):
    state = slim_challenge(entry(title))
    initialize_fonts(height)
    fonts = [loaded_fonts['titles'], loaded_fonts['stats']] if height == 64 else [loaded_fonts['stats']]
    font, text = fitted_title(state['title'], fonts, 64)
    assert text.startswith(state['title'].split()[0] + ' ')
    assert get_text_width(font, text) <= 64


def test_too_long_a_title_drops_words_from_the_end_not_the_month():
    initialize_fonts(32)
    stats = loaded_fonts['stats']
    assert fitted_title('SEP REP GOAL', [stats], 64) == (stats, 'SEP REP GOAL')
    assert fitted_title('SEP STRENGTH REP GOAL', [stats], 64) == (stats, 'SEP STRENGTH REP')
    assert fitted_title('SEP SUPERCALIFRAGILISTIC GOAL', [stats], 64)[1].startswith('SEP ')
    assert fitted_title('TURKEY BURN CLASSES EXTRA LONG', [stats], 64) == (stats, 'TURKEY BURN')


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
    assert half[(32, 12)] == GOLD and half[(52, 32)] == GOLD, 'the top and the right'
    assert half[(12, 32)] == RING_TRACK, 'the left is still track'
    empty = {p[2:] for p in ring_pixels(0.0, GOLD)}
    assert GOLD not in empty and RING_TRACK in empty
    full = {p[:2]: p[2:] for p in ring_pixels(1.0, TIER_COLORS['SILVER'])}
    assert full[(12, 32)] == TIER_COLORS['SILVER']
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
            screen = ChallengeScreen()
            screen.update(INTRO_SECONDS)
            assert screen.render(matrix, state)
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


# ---- the intro -----------------------------------------------------------------------------------------------
FRAMES = [i * ChallengeScreen.frame_seconds for i in range(round((INTRO_SECONDS + 0.5) / ChallengeScreen.frame_seconds))]
INTRO_CASES = [
    slim_challenge(entry()),
    slim_challenge(entry('Supercalifragilisticexpialidocious', 1, '1', 'workouts', ('Unearned', 0), ('Bronze', 15), '14')),
    slim_challenge(entry('November 2026 Cycling Challenge', 43.5, '43.5', 'miles', ('Unearned', 0), ('Bronze', 50),
                         '6.5')),
    slim_challenge(LARGEST[2]),  # 18,000: drops its comma
    slim_challenge(LARGEST[3]),  # 123,456: smaller font
    slim_challenge(entry('November 2026 Rowing Challenge', 12345678, '12,345,678', 'meters', ('Gold', 100000),
                         ('Platinum', 250000000), '1')),  # 12346K
    slim_challenge(TURKEY),  # Unearned, 0 of 18
]


def ink(matrix):
    return matrix.image.tobytes()


def ring_light(matrix):
    """The ring's total brightness (every tier colour is at least as bright as the track in each channel)."""
    pixels = matrix.image.load()
    return sum(sum(pixels[x, y]) for x, y, *_ in ring_pixels(0.0, GOLD))


@pytest.mark.parametrize('height', [64, 32])
@pytest.mark.parametrize('state', INTRO_CASES, ids=lambda state: state['title'])
def test_the_settled_frame_is_the_static_page(state, height):
    settled = ink(draw(state, height, INTRO_SECONDS))
    assert ink(draw(state, height, INTRO_SECONDS + 0.05)) == settled
    assert ink(draw(state, height, 30)) == settled
    assert ink(draw(state, height, 0)) != settled or tier_progress(state) == 0, 'the intro starts from empty'


def test_the_intro_is_done_by_intro_seconds_and_runs_at_20_fps():
    assert ChallengeScreen.animated and ChallengeScreen.atomic_frames and ChallengeScreen.frame_seconds == 0.05
    assert INTRO_SECONDS <= 1.0


@pytest.mark.parametrize('height', [64, 32])
@pytest.mark.parametrize('state', INTRO_CASES, ids=lambda state: state['title'])
def test_every_intro_frame_stays_on_the_panel_and_the_title_and_lines_never_move(state, height):
    frames = [draw(state, height, t) for t in FRAMES]  # draw() asserts nothing is off the panel
    rows = range(0, 9) if height == 64 else range(0, 7)
    first = [(x, y) for x, y in sorted(lit(frames[0], rows=rows))]
    bottom = range(58, 64) if height == 64 else range(25, 32)
    for matrix in frames:
        assert sorted(lit(matrix, rows=rows)) == first
        assert lit(matrix, rows=bottom) == lit(frames[0], rows=bottom)


@pytest.mark.parametrize('state', INTRO_CASES, ids=lambda state: state['title'])
def test_the_64_row_ring_only_grows_and_the_number_stays_inside_the_final_width(state):
    initialize_fonts(64)
    previous = -1
    for t in FRAMES:
        if t <= SWEEP_SECONDS:  # after the sweep only the flash changes the colours
            light = ring_light(draw(state, 64, t))
            assert light >= previous, 'the arc never shrinks'
            previous = light
        font, text = ring_final(state, t)
        assert font == ring_final(state)[0], 'one font throughout'
        assert get_text_width(font, text) <= get_text_width(font, ring_final(state)[1])
    assert ring_light(draw(state, 64, 0)) < ring_light(draw(state, 64)) or tier_progress(state) == 0


def ring_final(state, at=None):
    """(font, text) of the number at `at` seconds, or the settled one: what the screen draws inside the ring."""
    from display.ui.challenge_screen import ring_number, sweep
    font, final = ring_number(state['shown'])
    if at is None:
        return font, final
    text = counted_shown(state['shown'], sweep(at))
    if final != state['shown']:
        text = text.replace(',', '') if final == state['shown'].replace(',', '') else compact_number(text)
    return font, text


def test_the_number_counts_from_zero_to_the_value_never_over_it():
    initialize_fonts(64)
    state = INTRO_CASES[0]
    counted = [float(ring_final(state, t)[1].replace(',', '')) for t in FRAMES]
    assert counted[0] == 0 and counted[-1] == 5503
    assert counted == sorted(counted) and max(counted) == 5503
    assert counted_shown('5,503', 0.5) == '2,752'
    assert counted_shown('43.5', 0.5) == '21.8' and counted_shown('43.5', 0) == '0.0'
    assert counted_shown('1,640', 1) == '1,640' and counted_shown('1234', 0.5) == '617'
    for odd in ('abc', 'nan', 'inf', '1.2K', ''):
        assert counted_shown(odd, 0.5) == odd


@pytest.mark.parametrize('raw', LARGEST, ids=lambda raw: raw['challenge_summary']['title'])
def test_the_biggest_values_count_up_inside_the_ring_and_the_bar(raw):
    state = slim_challenge(raw)
    for height in (64, 32):
        initialize_fonts(height)
        for t in FRAMES:
            draw(state, height, t)  # nothing off the panel
    initialize_fonts(64)
    ring = ring_pixels(round(tier_progress(state), 3), tier_color(state['next']['title']))
    inside = {(x, y) for x, y, *_ in ring}
    for t in FRAMES:
        matrix = draw(state, 64, t)
        text = lit(matrix, (255, 255, 255), range(12, 56))
        assert not text & inside, 'the counting number never touches the ring'


def test_the_32_row_bar_fills_from_the_left_in_step_with_the_number():
    state = INTRO_CASES[3]  # 18,000 of 15,000-18,000: full
    full = {x for x, _ in lit(draw(state, 32), BLUE, range(21, 24))}
    previous = -1
    for t in FRAMES:
        matrix = draw(state, 32, t)
        bar = {x for x, _ in lit(matrix, BLUE, range(21, 24))}
        assert bar == set(range(3, 3 + len(bar))), 'filled from the left, no gaps'
        assert len(bar) >= previous and bar <= full
        previous = len(bar)
    assert previous == len(full) == 58
    assert not lit(draw(state, 32, 0), BLUE, range(21, 24)), 'empty to begin with'
    assert lit(draw(state, 32, 0), (255, 255, 255), range(8, 19)), '0 before it counts'


def test_the_ring_flashes_once_when_the_sweep_lands_then_holds_still():
    from display.ui.challenge_screen import flash
    state = INTRO_CASES[0]
    settled = ink(draw(state, 64))
    strengths = [flash(t) for t in FRAMES]
    assert all(s == 0 for t, s in zip(FRAMES, strengths) if t < SWEEP_SECONDS or t >= INTRO_SECONDS)
    assert max(strengths) > 0 and all(0 <= s <= 1 for s in strengths)
    flashing = [t for t in FRAMES if SWEEP_SECONDS <= t < INTRO_SECONDS]
    assert flashing and all(ink(draw(state, 64, t)) != settled for t in flashing)
    assert all(ink(draw(state, 64, t)) == settled for t in FRAMES if t >= INTRO_SECONDS)
    assert ink(draw(state, 32, SWEEP_SECONDS)) == ink(draw(state, 32))  # no flash on the bar


def test_the_screen_replays_the_intro_each_time_it_is_shown():
    initialize_fonts(64)
    state, screen = INTRO_CASES[0], ChallengeScreen()
    matrix = EdgeMatrix(height=64)
    screen.update(5)
    screen.on_enter(matrix, state)
    screen.render(matrix, state)
    assert ink(matrix) == ink(draw(state, 64, 0))
    screen.update(-3)  # a backwards clock never rewinds it
    assert screen.elapsed == 0


def test_the_ring_is_centred_between_the_title_and_the_bottom_line():
    matrix = draw(INTRO_CASES[0], 64)
    rows = {y for _, y, *_ in ring_pixels(1.0, GOLD)}
    assert (min(rows), max(rows)) == (12, 54), 'the ring is 43 rows: its centre is 33.5'
    title, line = lit(matrix, rows=range(0, 10)), lit(matrix, rows=range(56, 64))
    assert (max(y for _, y in title), min(y for _, y in line)) == (7, 58)
    # 50 rows between the title and the line, 43 of them the ring: 4 blank above, 3 below (Joel's pick; 7 can't split evenly)
    assert min(rows) - 1 - max(y for _, y in title) == 4 and 58 - max(rows) - 1 == 3


def reference_ring(fraction, color):
    """The ring as first written: every pixel sampled afresh. ring_pixels must match it exactly."""
    import math
    from display.ui.challenge_screen import RING_CENTRE, RING_RADIUS, RING_WIDTH, SUBSAMPLES
    cx, cy = RING_CENTRE
    outer, width = RING_RADIUS, RING_WIDTH
    inner, mid = outer - width, outer - width / 2
    end = math.tau * fraction
    caps = [(cx + mid * math.sin(a), cy - mid * math.cos(a)) for a in (0, end)] if fraction > 0 else []
    total, pixels = SUBSAMPLES ** 2, []
    for y in range(int(cy - outer) - 1, int(cy + outer) + 2):
        for x in range(int(cx - outer) - 1, int(cx + outer) + 2):
            if not inner - 1 <= math.hypot(x + 0.5 - cx, y + 0.5 - cy) <= outer + 1:
                continue
            lit_n = track = 0
            for i in range(SUBSAMPLES):
                for j in range(SUBSAMPLES):
                    px, py = x + (i + 0.5) / SUBSAMPLES, y + (j + 0.5) / SUBSAMPLES
                    in_band = inner <= math.hypot(px - cx, py - cy) <= outer
                    in_arc = in_band and math.atan2(px - cx, cy - py) % math.tau <= end
                    if in_arc or any(math.hypot(px - qx, py - qy) <= width / 2 for qx, qy in caps):
                        lit_n += 1
                    elif in_band:
                        track += 1
            if lit_n or track:
                pixels.append((x, y) + tuple(min(255, round(color[k] * lit_n / total + RING_TRACK[k] * track / total))
                                             for k in range(3)))
    return tuple(pixels)


@pytest.mark.parametrize('fraction', [0.0, 0.001, 0.05, 0.25, 0.3333, 0.5, 0.731, 0.999, 1.0])
def test_the_ring_matches_the_slow_reference(fraction):
    assert ring_pixels(fraction, GOLD) == reference_ring(fraction, GOLD)


def test_render_challenges_writes_the_intro_gifs(tmp_path):
    from PIL import Image

    from scripts import render_challenges
    render_challenges.write_gifs(str(tmp_path))
    for height in (64, 32):
        gif = Image.open(tmp_path / f'challenge-intro-{height}.gif')
        assert gif.size == (64 * 6, height * 6) and gif.n_frames > 10 and gif.info['duration'] == 50
