"""The next-class page (ROADMAP item 19): Peloton's reservations and scheduled classes, the fetch, the cache, the
rotation, the words, and the screen on both heights against everything each line can show."""

import json
import time
from unittest.mock import Mock

import pytest
import requests

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.next_class_screen import (
    COLUMN_LEFT,
    LINE_WIDTH,
    PULSE_FLOOR,
    PULSE_FRAME_SECONDS,
    PULSE_PERIOD,
    PULSE_WINDOW,
    TAG_COLORS,
    NextClassScreen,
    fitted,
    pulse_level,
    pulses,
)
from peloton import dashboard as dashboard_module
from peloton import dashboard_fetch
from peloton.cache import load_snapshot, save_snapshot
from peloton.config import DEFAULTS
from peloton.feeds.booked_classes import (
    NOUNS,
    SHOWN_AFTER_START,
    class_lines,
    day_word,
    instructor_lines,
    next_booking,
    reservation_ids,
    slim_class,
    valid_booking,
    when,
)
from peloton_led import _tick_seconds, build_rotation_pages
from scripts.render_demo import ImageMatrix
from tests.test_dashboard import setup_dashboard

ZONE = 'America/New_York'
NOW = 1794762000.0  # Sunday 2026-11-15, 12:00 PM in New York
HOUR = 3600


def scheduled(identity='p1', start=NOW + 22 * HOUR, live=True, encore=False, discipline='cycling', duration=1200, instructor='Ben Alldis'):
    """GET /api/peloton/{id}?joins=ride,ride.instructor, shaped like the real response (docs/PELOTON-API.md)."""
    return {
        'id': identity,
        'scheduled_start_time': start,
        'status': 'PRE_START',
        'is_live': live,
        'is_encore': encore,
        'start_time': None,
        'countdown': None,
        'total_home_reservations': 812,
        'ride': {
            'title': 'Countdown to TB Full Body: W3 D4',
            'fitness_discipline': discipline,
            'duration': duration,
            'instructor': {'name': instructor} if instructor else None,
        },
    }


def reservations(*ids):
    return {'data': [{'id': i, 'user_id': 'u', 'peloton_id': i} for i in ids], 'total': len(ids), 'show_next': False}


def booking(**overrides):
    return {
        'id': 'p1',
        'start': NOW + 22 * HOUR,
        'tag': 'LIVE',
        'discipline': 'cycling',
        'minutes': 20,
        'instructor': 'Ben Alldis',
        **overrides,
    }


# ---- parsing ---------------------------------------------------------------------------------------------------
def test_reservations_give_each_booked_class_once():
    assert reservation_ids(reservations('a', 'b', 'a')) == ['a', 'b']
    assert reservation_ids({'data': [{'peloton_id': ' c '}, {'id': 'x'}, 'junk', {'peloton_id': 5}]}) == ['c']
    assert reservation_ids(reservations()) == []


@pytest.mark.parametrize('payload', [None, [], {'data': 'nope'}, {'total': 0}, Mock()])
def test_a_reservations_response_that_is_not_one_raises(payload):
    with pytest.raises(ValueError):
        reservation_ids(payload)


def test_a_scheduled_class_keeps_what_the_page_draws():
    kept = slim_class(scheduled())
    assert kept == booking()
    assert valid_booking(kept)


def test_live_encore_and_untagged_classes_and_peloton_disciplines():
    assert slim_class(scheduled(live=True, encore=True))['tag'] == 'ENCORE'
    assert slim_class(scheduled(live=False))['tag'] is None
    assert slim_class(scheduled(discipline='circuit'))['discipline'] == 'tread_bootcamp'
    assert slim_class(scheduled(discipline='caesar'))['discipline'] == 'rowing'
    assert slim_class(scheduled(instructor=None))['instructor'] == ''
    assert slim_class(scheduled(duration=45))['minutes'] == 1
    assert slim_class(scheduled(), 'from-reservations')['id'] == 'from-reservations'


@pytest.mark.parametrize(
    'damage',
    [
        {'scheduled_start_time': None},
        {'scheduled_start_time': True},
        {'scheduled_start_time': 'soon'},
        {'ride': None},
        {'ride': {'fitness_discipline': 'cycling'}},
        {'ride': {'fitness_discipline': '', 'duration': 600}},
        {'ride': {'fitness_discipline': 'yoga', 'duration': -5}},
    ],
)
def test_a_class_that_cannot_be_shown_is_dropped(damage):
    assert slim_class({**scheduled(), **damage}) is None
    assert slim_class('junk') is None


@pytest.mark.parametrize(
    'damage',
    [
        {'start': 'x'},
        {'start': float('nan')},
        {'tag': 'PREMIERE'},
        {'discipline': ''},
        {'minutes': 0},
        {'minutes': 2.5},
        {'minutes': True},
        {'minutes': 5000},
        {'instructor': None},
        {'id': 3},
    ],
)
def test_a_damaged_booking_is_not_valid(damage):
    assert not valid_booking(booking(**damage))


def test_the_next_booking_is_the_soonest_until_it_has_been_going_ten_minutes():
    soon, later = booking(id='soon', start=NOW + HOUR), booking(id='later', start=NOW + 5 * HOUR)
    assert next_booking([later, soon, 'junk', booking(minutes=0)], NOW) == soon
    assert next_booking([later, soon], NOW + HOUR + SHOWN_AFTER_START - 1) == soon
    assert next_booking([later, soon], NOW + HOUR + SHOWN_AFTER_START) == later
    assert next_booking([], NOW) is None and next_booking('junk', NOW) is None


# ---- the words -------------------------------------------------------------------------------------------------
def test_the_class_line_is_the_length_and_a_noun_or_the_noun_alone():
    assert class_lines(booking()) == ['20 MIN RIDE', 'RIDE']
    assert class_lines(booking(discipline='tread_bootcamp', minutes=45)) == ['45 MIN TREAD BOOTCAMP', 'TREAD BOOTCAMP']
    assert class_lines(booking(discipline='new_thing'))[-1] == 'NEW THING'


def test_the_instructor_is_the_first_name_or_a_shared_one_in_full():
    assert instructor_lines('Ben Alldis') == ['WITH BEN', 'BEN']
    assert instructor_lines('Jess Sims') == ['JESS SIMS', 'JESS']
    assert instructor_lines('Marcel Dinkins')[0] == 'MARCEL DINKINS'
    assert instructor_lines('Jess') == ['WITH JESS', 'JESS']
    assert instructor_lines('') == [] and instructor_lines('   ') == []


@pytest.mark.parametrize(
    'starts_in, mode, minutes, day',
    [
        (22 * HOUR, 'clock', None, 'TOMORROW'),
        (HOUR + 1, 'clock', None, 'TODAY'),
        (HOUR, 'minutes', 60, 'TODAY'),
        (45 * 60, 'minutes', 45, 'TODAY'),
        (44 * 60 + 1, 'minutes', 45, 'TODAY'),  # rounded up: never says 0 before the start
        (1, 'minutes', 1, 'TODAY'),
        (0, 'now', None, 'TODAY'),
        (-300, 'now', None, 'TODAY'),
        (3 * 24 * HOUR, 'clock', None, 'WEDNESDAY'),
        (6 * 24 * HOUR, 'clock', None, 'SATURDAY'),
        (7 * 24 * HOUR, 'clock', None, 'NOV 22'),
    ],
)
def test_when_the_class_starts(starts_in, mode, minutes, day):
    moment = when(booking(start=NOW + starts_in), NOW, ZONE)
    assert moment['mode'] == mode and moment['day'] == day
    if minutes is not None:
        assert moment['minutes'] == minutes


def test_times_are_in_the_boards_zone():
    morning = booking(start=NOW + 18.5 * HOUR)  # 6:30 AM Monday in New York
    local = when(morning, NOW, ZONE)
    assert (local['time'], local['meridiem'], local['day']) == ('6:30', 'AM', 'TOMORROW')
    assert (when(morning, NOW, None)['time'], when(morning, NOW, None)['meridiem']) == ('11:30', 'AM'), 'UTC'
    assert when(morning, NOW, 'Not/A_Zone')['time'] == '11:30', 'a bad zone falls back to UTC'
    noon = when(booking(start=NOW), NOW - 2 * HOUR, ZONE)
    assert (noon['time'], noon['meridiem']) == ('12:00', 'PM')
    midnight = when(booking(start=NOW + 12 * HOUR), NOW, ZONE)
    assert (midnight['time'], midnight['meridiem'], midnight['day']) == ('12:00', 'AM', 'TOMORROW')


def test_day_words_count_calendar_days_not_hours():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(ZONE)
    late = datetime(2026, 11, 15, 23, 50, tzinfo=zone)
    assert day_word(datetime(2026, 11, 16, 0, 10, tzinfo=zone), late) == 'TOMORROW'
    assert day_word(datetime(2026, 11, 15, 23, 55, tzinfo=zone), late) == 'TODAY'


# ---- the client and the fetch ----------------------------------------------------------------------------------
def test_the_client_asks_for_reservations_and_each_class():
    from peloton.api import BASE, PelotonClient

    session = Mock()
    session.get.return_value.status_code = 200
    session.get.return_value.json.return_value = reservations('a')
    client = PelotonClient(session)
    assert client.get_reservations('u1') == reservations('a')
    session.get.assert_called_with(f'{BASE}/api/user/u1/reservations', timeout=20)
    session.get.return_value.json.return_value = scheduled()
    assert client.get_scheduled_class('a') == scheduled()
    session.get.assert_called_with(f'{BASE}/api/peloton/a', params={'joins': 'ride,ride.instructor'}, timeout=20)
    session.get.return_value.status_code = 404
    assert client.get_scheduled_class('gone') is None


def booking_dashboard(tmp_path, monkeypatch, config=None, ids=('p1', 'p2')):
    clock = {'now': 1000.0}
    monkeypatch.setattr(dashboard_module.time, 'monotonic', lambda: clock['now'])
    dashboard, client, token = setup_dashboard(tmp_path, config)
    client.get_reservations.return_value = reservations(*ids)
    classes = {'p1': scheduled('p1', start=NOW + 22 * HOUR), 'p2': scheduled('p2', start=NOW + HOUR, discipline='yoga', duration=600)}
    client.get_scheduled_class.side_effect = lambda identity: classes.get(identity)
    return dashboard, client, clock


def test_reservations_every_refresh_and_each_class_once(tmp_path, monkeypatch):
    dashboard, client, _ = booking_dashboard(tmp_path, monkeypatch)
    dashboard.refresh()
    assert [b['id'] for b in dashboard.snapshot()['booked_classes']] == ['p2', 'p1'], 'by start, not by ID'
    dashboard.refresh()
    assert client.get_reservations.call_count == 2
    assert client.get_scheduled_class.call_count == 2, 'details are asked for once per class'
    client.get_reservations.return_value = reservations('p1')
    dashboard.refresh()
    assert [b['id'] for b in dashboard.snapshot()['booked_classes']] == ['p1'], 'a cancelled class goes'
    assert [b['id'] for b in load_snapshot(dashboard.cache_path)['booked_classes']] == ['p1']


@pytest.mark.parametrize(
    'failure',
    [
        requests.HTTPError(response=Mock(status_code=500)),
        requests.ConnectionError('offline'),
        ValueError('bad'),
    ],
)
def test_a_failed_reservations_fetch_keeps_the_last_list(tmp_path, monkeypatch, failure):
    dashboard, client, _ = booking_dashboard(tmp_path, monkeypatch)
    dashboard.refresh()
    before = dashboard.snapshot()['booked_classes']
    client.get_reservations.side_effect = failure
    dashboard.refresh()
    snapshot = dashboard.snapshot()
    assert snapshot['booked_classes'] == before and snapshot['status'] == 'ready', 'the refresh still succeeds'


@pytest.mark.parametrize(
    'failure',
    [
        requests.HTTPError(response=Mock(status_code=500)),
        requests.ConnectionError('offline'),
        ValueError('bad'),
        None,  # 404: the class is gone
    ],
)
def test_a_class_without_details_is_asked_for_again_after_an_hour(tmp_path, monkeypatch, failure):
    dashboard, client, clock = booking_dashboard(tmp_path, monkeypatch, ids=('p1',))

    def details(identity):
        if failure is not None:
            raise failure
        return None

    client.get_scheduled_class.side_effect = details
    dashboard.refresh()
    assert dashboard.snapshot()['booked_classes'] == []
    clock['now'] += dashboard_fetch.BOOKING_RETRY_SECONDS - 1
    dashboard.refresh()
    assert client.get_scheduled_class.call_count == 1
    client.get_scheduled_class.side_effect = lambda identity: scheduled(identity)
    clock['now'] += 1
    dashboard.refresh()
    assert client.get_scheduled_class.call_count == 2
    assert [b['id'] for b in dashboard.snapshot()['booked_classes']] == ['p1']


@pytest.mark.parametrize('call', ['get_reservations', 'get_scheduled_class'])
def test_a_401_on_bookings_means_a_login_is_needed(tmp_path, monkeypatch, call):
    dashboard, client, _ = booking_dashboard(tmp_path, monkeypatch)
    getattr(client, call).side_effect = requests.HTTPError(response=Mock(status_code=401))
    dashboard.refresh()
    assert dashboard.login_required


def test_no_fetch_while_the_page_is_off(tmp_path, monkeypatch):
    dashboard, client, _ = booking_dashboard(tmp_path, monkeypatch, {'rotation': ['username', 'goals']})
    dashboard.refresh()
    client.get_reservations.assert_not_called()
    assert dashboard.snapshot()['booked_classes'] == []


def test_a_restart_keeps_the_classes_details(tmp_path, monkeypatch):
    dashboard, client, _ = booking_dashboard(tmp_path, monkeypatch)
    dashboard.refresh()
    again = dashboard_module.Dashboard(dashboard.token_path, {}, client_factory=lambda _: client)
    assert [b['id'] for b in again.snapshot()['booked_classes']] == ['p2', 'p1']
    again.refresh()
    assert client.get_scheduled_class.call_count == 2, 'the cached details are not asked for again'


def test_the_demo_has_a_booked_class():
    dashboard = dashboard_module.Dashboard('missing-token', {}, demo=True)
    assert next_booking(dashboard.snapshot()['booked_classes'], time.time())['tag'] == 'LIVE'


# ---- cache and rotation ----------------------------------------------------------------------------------------
def test_the_cache_keeps_bookings_and_drops_a_damaged_list(tmp_path):
    path = tmp_path / 'cache.json'
    save_snapshot(path, {'me': {'id': 'u'}, 'totals': {}, 'summaries': [], 'last_updated': 1.0, 'booked_classes': [booking()]})
    assert load_snapshot(path)['booked_classes'] == [booking()]
    for damaged in ({'a': 1}, [booking(), {'id': 'half'}], 'text', None):
        payload = json.loads(path.read_text())
        payload['snapshot']['booked_classes'] = damaged
        path.write_text(json.dumps(payload))
        restored = load_snapshot(path)
        assert 'booked_classes' not in restored and restored['me'] == {'id': 'u'}, damaged


def test_one_page_for_the_next_booked_class(monkeypatch):
    import peloton_led

    monkeypatch.setattr(peloton_led.time, 'time', lambda: NOW)
    display = {**DEFAULTS, 'rotation': ['goals', 'next_class'], 'screen_durations': {'next_class': 7}, 'timezone': ZONE}
    over = booking(id='over', start=NOW - SHOWN_AFTER_START)
    snapshot = {'summaries': [], 'status': 'ready', 'totals': {}, 'booked_classes': [booking(), booking(id='soon', start=NOW + HOUR), over]}
    pages = build_rotation_pages(snapshot, None, display, 'Joel', 64)
    assert pages == [('next_class', {'booking': booking(id='soon', start=NOW + HOUR), 'now': NOW, 'timezone': ZONE}, 7)]
    for empty in ([], [over], 'junk', None):
        assert build_rotation_pages({**snapshot, 'booked_classes': empty}, None, display, 'Joel', 64) == []


def test_next_class_is_a_rotation_screen_on_by_default(tmp_path):
    from peloton.config import load_config
    from settings_page.form import SCREEN_NAMES

    assert 'next_class' in DEFAULTS['rotation'] and 'next_class' in SCREEN_NAMES
    path = tmp_path / 'config.json'
    path.write_text('{"display": {"rotation": ["next_class"], "screen_durations": {"next_class": 6}}}')
    assert load_config(str(path))['display']['screen_durations'] == {'next_class': 6}


# ---- the screen ------------------------------------------------------------------------------------------------
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
    matrix = EdgeMatrix(height=height)
    assert NextClassScreen().render(matrix, state)
    assert matrix.off_panel == 0, state
    return matrix


def lit_rows(matrix, columns=range(64)):
    pixels = matrix.image.load()
    return {y for y in range(matrix.height) for x in columns if pixels[x, y] != (0, 0, 0)}


def lit_columns(matrix):
    pixels = matrix.image.load()
    return {x for x in range(matrix.width) for y in range(matrix.height) if pixels[x, y] != (0, 0, 0)}


# Every live discipline Peloton schedules (the 12 the board has icons for), the lengths they come in, and the
# longest instructor names among the 57 in GET /api/instructor (2026-11-14), with the four shared first names.
DISCIPLINES = sorted(NOUNS)
LENGTHS = (5, 10, 15, 20, 30, 45, 60, 75, 90, 120)
INSTRUCTORS = (
    'Charlotte Weidenbach',
    "Christine D'Ercole",
    'Robin Arzón',
    'Mariana Fernández',
    'Ben Alldis',
    'Alex Toussaint',
    'Alex Karwoski',
    'Hannah Frankson',
    'Hannah Corbin',
    'Jess Sims',
    'Jess King',
    'Marcel Dinkins',
    'Marcel Maurer',
    '',
)
# Every start from NOW through the last hour, then every half hour across a week.
STARTS = [-SHOWN_AFTER_START + 1, 0] + [m * 60 for m in range(1, 61)] + [HOUR + h * 1800 for h in range(0, 336)]
WIDEST = booking(tag='ENCORE', discipline='tread_bootcamp', minutes=120, instructor='Hannah Frankson')


def _check_64(matrix):
    """The 64x64 bands: icon 0-21, tag 23-29, time 31-40, day 43-48, class 51-55, instructor 58-62, with
    blank rows between (1 each side of the tag)."""
    assert not lit_rows(matrix) & {22, 30, 41, 42, 49, 50, 56, 57, 63}


@pytest.mark.parametrize('starts_in', STARTS)
def test_64_rows_fit_every_start(starts_in):
    initialize_fonts(64)
    _check_64(draw({'booking': {**WIDEST, 'start': NOW + starts_in}, 'now': NOW, 'timezone': ZONE}, 64))


@pytest.mark.parametrize('discipline', DISCIPLINES)
def test_64_rows_fit_every_class_and_instructor(discipline):
    initialize_fonts(64)
    small = loaded_fonts['stats']
    for minutes in LENGTHS:
        for instructor in INSTRUCTORS:
            state = booking(discipline=discipline, minutes=minutes, instructor=instructor)
            _check_64(draw({'booking': state, 'now': NOW, 'timezone': ZONE}, 64))
            # Nothing real is ever cut: the line is one of its own wordings.
            assert fitted(small, class_lines(state), LINE_WIDTH) in class_lines(state)


def test_the_class_line_drops_the_length_only_where_it_must():
    initialize_fonts(64)
    small = loaded_fonts['stats']
    alone = {
        (d, m) for d in DISCIPLINES for m in LENGTHS if fitted(small, class_lines(booking(discipline=d, minutes=m)), LINE_WIDTH) == NOUNS[d]
    }
    assert {d for d, _ in alone} == {'bike_bootcamp', 'tread_bootcamp', 'row_bootcamp', 'meditation', 'strength'}
    assert {m for d, m in alone if d == 'strength'} == {120}
    assert all((d, m) in alone for d in ('bike_bootcamp', 'tread_bootcamp', 'row_bootcamp', 'meditation') for m in LENGTHS)


def test_every_shared_first_name_fits_in_full():
    initialize_fonts(64)
    for name in (
        'Alex Toussaint',
        'Alex Karwoski',
        'Hannah Frankson',
        'Hannah Corbin',
        'Jess Sims',
        'Jess King',
        'Marcel Dinkins',
        'Marcel Maurer',
    ):
        assert get_text_width(loaded_fonts['stats'], name.upper()) <= LINE_WIDTH, name


def _check_32(matrix):
    """The 64x32 bands in the text column (tag 0-6, time 9-17, day 19-23, name 26-30) and nothing between the
    icon (columns 0-25) and the column."""
    assert not lit_rows(matrix, range(COLUMN_LEFT, 64)) & {7, 8, 18, 24, 25, 31}
    assert not lit_columns(matrix) & {26, 27}


@pytest.mark.parametrize('starts_in', STARTS)
def test_32_rows_fit_every_start(starts_in):
    initialize_fonts(32)
    _check_32(draw({'booking': {**WIDEST, 'start': NOW + starts_in}, 'now': NOW, 'timezone': ZONE}, 32))


@pytest.mark.parametrize('discipline', DISCIPLINES)
def test_32_rows_fit_every_class_and_instructor(discipline):
    initialize_fonts(32)
    for instructor in INSTRUCTORS:
        state = booking(discipline=discipline, instructor=instructor, tag='ENCORE')
        _check_32(draw({'booking': state, 'now': NOW, 'timezone': ZONE}, 32))
        first = instructor_lines(instructor)[-1:] or ['']
        assert get_text_width(loaded_fonts['info'], first[0]) <= 64 - COLUMN_LEFT, 'first names are never cut'


@pytest.mark.parametrize('height', [64, 32])
def test_the_tag_is_live_red_encore_blue_or_nothing(height):
    initialize_fonts(height)
    for tag in ('LIVE', 'ENCORE', None):
        pixels = draw({'booking': booking(tag=tag), 'now': NOW, 'timezone': ZONE}, height).image.getcolors(9999)
        colours = {colour for _, colour in pixels}
        for other, colour in TAG_COLORS.items():
            assert (colour in colours) == (other == tag), (tag, other)


@pytest.mark.parametrize('height', [64, 32])
def test_a_discipline_with_no_icon_draws_none(height):
    initialize_fonts(height)
    matrix = draw({'booking': booking(discipline='new_thing', tag=None), 'now': NOW, 'timezone': ZONE}, height)
    assert not lit_rows(matrix) & set(range(0, 22)) if height == 64 else not lit_columns(matrix) & set(range(26))


@pytest.mark.parametrize(
    'state',
    [
        None,
        'junk',
        {},
        {'booking': booking()},
        {'booking': booking(), 'now': True},
        {'booking': booking(minutes=0), 'now': NOW},
        {'booking': 'x', 'now': NOW},
    ],
)
def test_a_page_with_nothing_to_draw_says_so(state):
    initialize_fonts(64)
    assert NextClassScreen().render(EdgeMatrix(height=64), state) is False


def test_fitted_cuts_only_as_a_last_resort():
    initialize_fonts(64)
    small = loaded_fonts['stats']
    assert fitted(small, ['TOO WIDE ' * 4, 'SHORT'], 60) == 'SHORT'
    assert get_text_width(small, fitted(small, ['X' * 30], 60)) <= 60
    assert fitted(small, [], 60) == ''


def test_render_next_class_draws_both_panel_sizes(tmp_path, capsys):
    from scripts import render_next_class

    out = tmp_path / 'next.png'
    render_next_class.main(['--out', str(out)])
    assert out.exists() and 'Wrote' in capsys.readouterr().out


def test_render_next_class_stops_on_a_page_it_cannot_draw(monkeypatch):
    from scripts import render_next_class

    monkeypatch.setattr(render_next_class, 'PAGES', [booking(minutes=0)])
    with pytest.raises(RuntimeError):
        render_next_class.panels(64)


# ---- the tag's pulse: last 10 minutes only ----------------------------------------------------------------------
def page(starts_in, **overrides):
    return {'booking': booking(start=NOW + starts_in, **overrides), 'now': NOW, 'timezone': ZONE}


def pixels_of(matrix):
    image = matrix.image
    return [image.getpixel((x, y)) for y in range(image.height) for x in range(image.width)]


def entered(state, height=64):
    initialize_fonts(height)
    screen = NextClassScreen()
    screen.on_enter(None, state)
    return screen


@pytest.mark.parametrize(
    'starts_in, expected',
    [
        (22 * HOUR, False),
        (HOUR, False),
        (PULSE_WINDOW + 60, False),
        (PULSE_WINDOW + 1, False),
        (PULSE_WINDOW, True),
        (60, True),
        (1, True),
        (0, True),
        (-300, True),
        (-SHOWN_AFTER_START, True),
    ],
)
def test_only_the_last_ten_minutes_animate(starts_in, expected):
    assert entered(page(starts_in)).animated is expected
    assert pulses(page(starts_in)) is expected


def test_a_page_with_no_tag_or_no_time_never_animates():
    assert PULSE_WINDOW == 600
    assert not entered(page(60, tag=None)).animated
    for state in (
        None,
        'junk',
        {},
        {'booking': booking(start=NOW + 60)},
        {'booking': booking(), 'now': True},
        {'booking': booking(minutes=0, start=NOW), 'now': NOW},
    ):
        assert pulses(state) is False


def test_each_showing_decides_afresh_and_the_loop_ticks_only_in_the_window():
    screen = entered(page(5 * 60))
    assert screen.animated and _tick_seconds(Mock(current=screen)) == PULSE_FRAME_SECONDS
    screen.on_enter(None, page(HOUR))
    assert screen.animated is False  # the next showing is a still page


def pulse_cycle(state, height):
    """Every frame of one cycle (and the one after it), nothing drawn off the panel."""
    screen = entered(state, height)
    frames = []
    for _ in range(round(PULSE_PERIOD / PULSE_FRAME_SECONDS) + 1):
        matrix = EdgeMatrix(height=height)
        assert screen.render(matrix, state)
        assert matrix.off_panel == 0
        frames.append(matrix)
        screen.update(PULSE_FRAME_SECONDS)
    return frames


@pytest.mark.parametrize('height', [64, 32])
@pytest.mark.parametrize('tag', ['LIVE', 'ENCORE'])
@pytest.mark.parametrize('starts_in', [5 * 60, 0, -120])
def test_the_pulse_changes_only_the_tag_block_and_stays_between_55_and_100_percent(height, tag, starts_in):
    state = page(starts_in, tag=tag, discipline='tread_bootcamp', instructor='Hannah Frankson')
    frames = pulse_cycle(state, height)
    colour = TAG_COLORS[tag]
    base = frames[0].image.load()
    block = {(x, y) for x in range(64) for y in range(height) if base[x, y] == colour}
    assert block
    levels = []
    for matrix in frames:
        pixels = matrix.image.load()
        shades = {pixels[x, y] for x, y in block}
        assert len(shades) == 1  # the block dims together
        levels.append([channel / full for channel, full in zip(shades.pop(), colour) if full][0])
        for x in range(64):
            for y in range(height):
                if (x, y) not in block:
                    assert pixels[x, y] == base[x, y], (x, y)  # text, icon and every other line never change
    assert max(levels) == 1.0
    assert min(levels) == pytest.approx(PULSE_FLOOR, abs=0.02)
    assert all(PULSE_FLOOR - 0.02 <= level <= 1.0 for level in levels)
    assert levels[-1] == pytest.approx(1.0)  # a whole cycle
    assert len({tuple(pixels_of(m)) for m in frames}) > 5  # smooth: many steps, not a blink
    assert pixels_of(frames[0]) == pixels_of(draw(state, height))  # frame 0 is the static page


@pytest.mark.parametrize('height', [64, 32])
def test_the_first_frame_after_entering_is_the_static_page_and_elapsed_resets(height):
    state = page(5 * 60)
    screen = entered(state, height)
    first = EdgeMatrix(height=height)
    screen.render(first, state)
    assert pixels_of(first) == pixels_of(draw(state, height))
    screen.update(PULSE_PERIOD / 2)  # the dimmest point
    dim = EdgeMatrix(height=height)
    screen.render(dim, state)
    assert pixels_of(dim) != pixels_of(first)
    screen.on_enter(None, state)
    assert screen.elapsed == 0.0
    again = EdgeMatrix(height=height)
    screen.render(again, state)
    assert pixels_of(again) == pixels_of(first)


def test_the_pulse_level_is_full_at_the_start_and_once_per_cycle_and_survives_odd_time():
    assert pulse_level(0) == 1.0 and pulse_level(PULSE_PERIOD) == pytest.approx(1.0)
    assert pulse_level(PULSE_PERIOD / 2) == pytest.approx(PULSE_FLOOR)
    assert pulse_level(-5) == 1.0
    screen = NextClassScreen()
    screen.update(-1)
    assert screen.elapsed == 0.0


@pytest.mark.parametrize('height', [64, 32])
def test_a_still_page_stays_still_whatever_the_elapsed_time(height):
    state = page(HOUR)
    screen = entered(state, height)
    screen.update(PULSE_PERIOD / 2)  # an overlay repaint still ticks the screen
    matrix = EdgeMatrix(height=height)
    screen.render(matrix, state)
    assert pixels_of(matrix) == pixels_of(draw(state, height))
    assert not screen.animated


def test_render_next_class_writes_the_pulse_gifs(tmp_path, capsys):
    from PIL import Image

    from scripts import render_next_class

    render_next_class.main(['--gifs', str(tmp_path)])
    out = capsys.readouterr().out
    for height in (64, 32):
        gif = Image.open(tmp_path / f'next-class-pulse-{height}.gif')
        assert gif.n_frames == round(PULSE_PERIOD / PULSE_FRAME_SECONDS) and gif.size == (512, height * 8)
        assert f'next-class-pulse-{height}.gif' in out


def test_the_rotation_preview_draws_the_next_class_page_at_full_brightness():
    from scripts.render_rotation import frame_times

    assert frame_times('next_class', {}, 7, 4.0) == [0.0]
