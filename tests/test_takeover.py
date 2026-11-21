"""The next-class takeover: from `display.next_class_takeover_minutes` before a booked class starts until
TAKEOVER_END_AFTER_START after, the next-class page holds the panel, whoever's rotation is showing.
Time is a fake clock (sleeping moves it on), the dashboards are fakes that read only their own snapshot."""
import logging
import time as real_time
from unittest.mock import Mock, patch

import pytest

import peloton_led
from peloton.feeds.booked_classes import (SHOWN_AFTER_START, TAKEOVER_END_AFTER_START, TAKEOVER_MAX_MINUTES,
                                    takeover_booking, when)
from peloton.config import DEFAULTS, validate_config
from peloton_led import (TAKEOVER_CHECK_SECONDS, NextClassTakeover, run_display_loop, run_multi_user_loop,
                         show_and_wait)

NOW = 1794762000.0  # Sunday 2026-11-15, 12:00 PM in New York
ZONE = 'America/New_York'
MINUTE = 60


def booking(identity='a', start=NOW + 3600, **overrides):
    return {'id': identity, 'start': start, 'tag': 'LIVE', 'discipline': 'cycling', 'minutes': 20,
            'instructor': 'Ben Alldis', **overrides}


class Clock:
    """peloton_led's time: sleeping moves it on, `time()` is NOW plus that."""

    def __init__(self):
        self.now = 0.0

    def time(self):
        return NOW + self.now

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(0, seconds)

    def __getattr__(self, name):
        return getattr(real_time, name)


@pytest.fixture
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(peloton_led, 'time', fake)
    monkeypatch.setattr('display.rotation_pages.time', fake)  # the page builders read the clock too
    monkeypatch.setattr(peloton_led, 'shown_pin', lambda: None)
    return fake


class FakeDashboard:
    """What the loop may touch: the snapshot and the booked classes, nothing that reaches Peloton."""

    login_indicator_required = False

    def __init__(self, bookings=()):
        self.bookings = list(bookings)
        self.reads = 0

    def booked_classes(self):
        self.reads += 1
        return list(self.bookings)

    def snapshot(self):
        return {'me': {'username': 'Rider', 'timezone': ZONE}, 'summaries': [], 'totals': {}, 'status': 'ready',
                'booked_classes': list(self.bookings)}

    def should_celebrate_pr(self, summary):
        return False

    def acknowledge_name_facts(self, keys):
        pass


class FakeManager:
    """Records what is shown and each tick's state; `animated` follows the next-class page like the real one."""

    def __init__(self, clock):
        self.clock, self.shown, self.ticks, self.clears = clock, [], [], 0
        self.matrix = self
        self.current = Mock(animated=False, frame_seconds=0.05)

    def show(self, name, state):
        from display.ui.next_class_screen import pulses
        self.shown.append((self.clock.now, name, state))
        self.current = Mock(animated=name == 'next_class' and pulses(state), frame_seconds=0.05)

    def tick(self, state):
        self.ticks.append((self.clock.now, state))

    def Clear(self):
        self.clears += 1


def rider(name, bookings=(), **display):
    return {'name': name, 'dashboard': FakeDashboard(bookings),
            'display': {'rotation': ['next_class'], **display}}


# ---- which booking takes over -------------------------------------------------------------------------------------
def test_takeover_starts_at_exactly_the_minutes_before_and_not_a_second_earlier():
    for minutes in (1, 5, 10):
        assert takeover_booking([booking(start=NOW + minutes * MINUTE)], NOW, minutes) is not None
        assert takeover_booking([booking(start=NOW + minutes * MINUTE + 1)], NOW, minutes) is None
        assert takeover_booking([booking(start=NOW + minutes * MINUTE + 0.5)], NOW, minutes) is None


def test_takeover_ends_the_end_constant_after_the_start():
    assert TAKEOVER_END_AFTER_START == 120 and TAKEOVER_END_AFTER_START <= SHOWN_AFTER_START
    assert takeover_booking([booking(start=NOW)], NOW, 5) is not None
    assert takeover_booking([booking(start=NOW - TAKEOVER_END_AFTER_START + 1)], NOW, 5) is not None
    assert takeover_booking([booking(start=NOW - TAKEOVER_END_AFTER_START)], NOW, 5) is None
    assert takeover_booking([booking(start=NOW - SHOWN_AFTER_START)], NOW, 5) is None


def test_zero_minutes_is_off_and_odd_input_is_nothing():
    assert takeover_booking([booking(start=NOW + 1)], NOW, 0) is None
    for junk in (None, 'x', {}, [None], [booking(minutes=0)], [booking(id=3)]):
        assert takeover_booking(junk, NOW, 5) is None


def test_the_sooner_start_wins_and_a_tie_goes_to_the_first_listed():
    later, sooner = booking('later', NOW + 200), booking('sooner', NOW + 100)
    assert takeover_booking([later, sooner], NOW, 5)['id'] == 'sooner'
    assert takeover_booking([booking('first', NOW + 100), booking('second', NOW + 100)], NOW, 5)['id'] == 'first'
    over = booking('over', NOW - TAKEOVER_END_AFTER_START - 1)  # a class that has just gone doesn't hide the next
    assert takeover_booking([over, later], NOW, 5)['id'] == 'later'


def test_either_rider_triggers_it_and_the_sooner_class_wins(clock):
    joel, jen = rider('Joel', [booking('j', NOW + 280)]), rider('Jen', [booking('n', NOW + 120)])
    takeover = NextClassTakeover([joel, jen], {})
    assert takeover.due() == (1, jen['dashboard'].bookings[0]) and takeover.pending()
    jen['dashboard'].bookings = []
    assert takeover.due() == (0, joel['dashboard'].bookings[0])
    joel['dashboard'].bookings = []
    assert takeover.due() is None and not takeover.pending()


def test_a_tie_goes_to_the_first_configured_rider(clock):
    joel, jen = rider('Joel', [booking('j', NOW + 100)]), rider('Jen', [booking('n', NOW + 100)])
    assert NextClassTakeover([joel, jen], {}).due()[0] == 0
    assert NextClassTakeover([jen, joel], {}).due()[0] == 0  # first configured, whoever that is


def test_only_a_rider_with_next_class_in_rotation_and_a_takeover_setting_counts(clock):
    soon = [booking(start=NOW + 100)]
    no_page = rider('Joel', soon, rotation=['username'])
    off = rider('Jen', soon, next_class_takeover_minutes=0)
    assert NextClassTakeover([no_page, off], {}).due() is None
    assert no_page['dashboard'].reads == 0 and off['dashboard'].reads == 1  # not even asked without the page
    assert NextClassTakeover([no_page, rider('Jen', soon)], {}).due()[0] == 1
    # A rider's own display wins; one without falls back to the shared one (and the default of 5 minutes).
    bare = {'name': 'Solo', 'dashboard': FakeDashboard(soon)}
    assert NextClassTakeover([bare], {'rotation': ['next_class']}).due() is not None
    assert NextClassTakeover([bare], {'rotation': ['next_class'], 'next_class_takeover_minutes': 0}).due() is None
    assert NextClassTakeover([bare], {}).due() is not None  # the default rotation has next_class
    assert DEFAULTS['next_class_takeover_minutes'] == 5
    far = rider('Far', [booking(start=NOW + 4 * MINUTE)], next_class_takeover_minutes=3)
    assert NextClassTakeover([far], {}).due() is None


# ---- holding the panel --------------------------------------------------------------------------------------------
def test_the_hold_counts_down_live_and_ends_at_the_end_constant(clock, caplog):
    start = NOW + 3 * MINUTE + 30
    joel = rider('Joel', [booking('j', start)])
    manager = FakeManager(clock)
    with caplog.at_level(logging.INFO, logger='peloton-led'):
        assert NextClassTakeover([joel], {}).hold(manager) is True
    assert len(manager.shown) == 1 and manager.shown[0][1:] == (
        'next_class', {'booking': joel['dashboard'].bookings[0], 'now': NOW, 'timezone': ZONE})
    ends = 3 * MINUTE + 30 + TAKEOVER_END_AFTER_START
    assert ends <= clock.now <= ends + TAKEOVER_CHECK_SECONDS + 0.1  # noticed at the next check
    words = []
    for _, state in manager.ticks:
        moment = when(state['booking'], state['now'], ZONE)
        word = 'NOW' if moment['mode'] == 'now' else f"{moment['minutes']} MIN"
        if not words or words[-1] != word:
            words.append(word)
    assert words == ['4 MIN', '3 MIN', '2 MIN', '1 MIN', 'NOW']  # the existing `when` wording, live
    assert max(t for t, _ in manager.ticks) <= clock.now
    assert [r.getMessage() for r in caplog.records] == [
        f'Next-class takeover: Joel, class at {start}.', f'Next-class takeover ended for Joel (class at {start}).']


def test_a_hold_with_nothing_due_does_nothing(clock):
    manager = FakeManager(clock)
    assert NextClassTakeover([rider('Joel', [booking()])], {}).hold(manager) is False
    assert manager.shown == [] and clock.now == 0


def test_the_pulse_ticks_every_frame_in_the_hold_and_a_still_page_once_a_check(clock):
    joel = rider('Joel', [booking('j', NOW + 60)])
    manager = FakeManager(clock)
    NextClassTakeover([joel], {}).hold(manager)
    assert len(manager.shown) == 1, 'shown once, so the pulse is not reset again'
    assert len(manager.ticks) > 100  # ~20 fps for 3 minutes
    untagged = rider('Joel', [booking('j', NOW + 60, tag=None)])
    manager = FakeManager(clock)
    clock.now = 0
    NextClassTakeover([untagged], {}).hold(manager)
    seconds = 60 + TAKEOVER_END_AFTER_START
    assert seconds - 10 <= len(manager.ticks) <= seconds + 3  # about one a second, no per-frame work


def test_a_cancelled_booking_ends_the_hold_within_a_check(clock):
    joel = rider('Joel', [booking('j', NOW + 200)])
    manager = FakeManager(clock)
    real_sleep = clock.sleep

    def cancel_at_60_seconds(seconds):
        real_sleep(seconds)
        if clock.now >= 60:
            joel['dashboard'].bookings = []

    clock.sleep = cancel_at_60_seconds
    NextClassTakeover([joel], {}).hold(manager)
    assert 60 <= clock.now <= 60 + TAKEOVER_CHECK_SECONDS + 0.1


def test_a_sooner_booking_replaces_it_and_a_changed_one_is_shown_afresh(clock, caplog):
    joel = rider('Joel', [booking('j', NOW + 280)])
    jen = rider('Jen', [])
    manager = FakeManager(clock)
    real_sleep = clock.sleep

    def jen_books_a_class_at_30_seconds(seconds):
        real_sleep(seconds)
        if clock.now >= 30 and not jen['dashboard'].bookings:
            jen['dashboard'].bookings = [booking('n', NOW + 90)]

    clock.sleep = jen_books_a_class_at_30_seconds
    active = {'dashboard': 'rotation'}
    with caplog.at_level(logging.INFO, logger='peloton-led'):
        NextClassTakeover([joel, jen], {}, active).hold(manager)
    # Jen's class is sooner and takes over; once hers is over, Joel's (still in its window) holds again.
    assert [state['booking']['id'] for _, _, state in manager.shown] == ['j', 'n', 'j']
    messages = [r.getMessage() for r in caplog.records]
    assert [m.split(':')[0].split(' for')[0] for m in messages] == ['Next-class takeover', 'Next-class takeover ended'] * 3
    assert active == {'dashboard': 'rotation'}, 'the rotation rider is back once it ends'


def test_the_padlock_follows_the_rider_whose_class_it_is_and_comes_back(clock):
    joel, jen = rider('Joel', []), rider('Jen', [booking('n', NOW + 100)])
    active = {'dashboard': joel['dashboard']}
    seen = []
    manager = FakeManager(clock)
    original = manager.tick
    manager.tick = lambda state: (seen.append(active['dashboard']), original(state))
    NextClassTakeover([joel, jen], {}, active).hold(manager)
    assert set(seen) == {jen['dashboard']} and active['dashboard'] is joel['dashboard']


def test_overlays_keep_working_in_the_hold(clock, monkeypatch):
    pins = iter([None] * 30 + ['4321'] * 100000)
    monkeypatch.setattr(peloton_led, 'shown_pin', lambda: next(pins))
    manager = FakeManager(clock)
    NextClassTakeover([rider('Joel', [booking('j', NOW + 60)])], {}).hold(manager)
    assert manager.clears == 1  # the PIN appearing clears and repaints at once, once


def test_the_hold_ends_and_the_rider_comes_back_if_the_screen_fails(clock):
    joel = rider('Joel', [booking('j', NOW + 60)])
    active = {'dashboard': 'rotation'}
    manager = FakeManager(clock)
    manager.tick = Mock(side_effect=RuntimeError('boom'))
    with pytest.raises(RuntimeError):
        NextClassTakeover([joel], {}, active).hold(manager)
    assert active == {'dashboard': 'rotation'}


def test_the_zone_is_the_displays_else_the_riders_profile(clock):
    joel = rider('Joel', [booking('j', NOW + 60)], timezone='America/Chicago')
    manager = FakeManager(clock)
    NextClassTakeover([joel], {}).hold(manager)
    assert manager.shown[0][2]['timezone'] == 'America/Chicago'


def test_nothing_in_the_takeover_touches_the_network(clock):
    joel = rider('Joel', [booking('j', NOW + 60)])
    with patch('requests.Session.request', side_effect=AssertionError('network')), \
         patch('requests.sessions.Session.send', side_effect=AssertionError('network')):
        NextClassTakeover([joel], {}).hold(FakeManager(clock))


def test_the_dashboard_hands_out_a_copy_of_just_its_booked_classes(tmp_path):
    from peloton.dashboard import Dashboard
    dashboard = Dashboard(tmp_path / 'token', {'rotation': ['next_class']}, demo=True)
    first = dashboard.booked_classes()
    assert first and first == dashboard.snapshot()['booked_classes']
    first.clear()
    assert dashboard.booked_classes(), 'a copy'
    dashboard._data.pop('booked_classes')
    assert dashboard.booked_classes() == []


# ---- cutting a long page short --------------------------------------------------------------------------------------
def test_a_long_page_is_cut_short_within_the_check_interval(clock):
    manager = FakeManager(clock)
    calls = []
    assert show_and_wait(manager, 'username', {}, 60, None, interrupt=lambda: calls.append(clock.now) or clock.now >= 10)
    assert 10 <= clock.now <= 10 + TAKEOVER_CHECK_SECONDS + 0.3
    assert all(b - a == pytest.approx(TAKEOVER_CHECK_SECONDS, abs=0.25) for a, b in zip(calls, calls[1:]))
    assert show_and_wait(manager, 'username', {}, 3, None, interrupt=lambda: False) is False
    assert show_and_wait(manager, 'username', {}, 3) is False


# ---- in the rotation ------------------------------------------------------------------------------------------------
def loop_over(clock, joel, jen=None, pages=None, cycles=1):
    manager = FakeManager(clock)
    profiles = [joel] + ([jen] if jen else [])
    takeover = NextClassTakeover(profiles, {}, {'dashboard': joel['dashboard']})
    if pages is None:
        run_display_loop(manager, joel['dashboard'], joel['display'], cycles=cycles, takeover=takeover)
    else:
        with patch('peloton_led.build_rotation_pages', return_value=pages):
            run_display_loop(manager, joel['dashboard'], joel['display'], cycles=cycles, takeover=takeover)
    return manager


def shown_names(manager):
    return [(round(at), name) for at, name, _ in manager.shown]


def test_a_takeover_cuts_a_long_page_and_the_page_plays_again_after_it(clock):
    joel = rider('Joel', [booking('j', NOW + 40 + 5 * MINUTE)])  # due 40 s in
    pages = [('username', {'fact_keys': []}, 100), ('goal', {}, 5)]
    manager = loop_over(clock, joel, pages=pages)
    names = [name for _, name, _ in manager.shown]
    assert names == ['username', 'next_class', 'username', 'goal']
    cut_at = manager.shown[1][0]
    assert 40 <= cut_at <= 40 + TAKEOVER_CHECK_SECONDS + 0.3
    resumed_at = manager.shown[2][0]
    ends = cut_at + 5 * MINUTE + TAKEOVER_END_AFTER_START
    assert ends - 1 <= resumed_at <= ends + TAKEOVER_CHECK_SECONDS + 0.3


def test_a_takeover_due_between_pages_starts_before_the_next_page(clock):
    joel = rider('Joel', [booking('j', NOW + 5 * MINUTE + 1.2)])  # due at 1.2 s: the first page ends at 1.5
    pages = [('username', {'fact_keys': []}, 1.5), ('goal', {}, 5), ('goal', {}, 5)]
    manager = loop_over(clock, joel, pages=pages)
    assert [n for _, n, _ in manager.shown] == ['username', 'next_class', 'goal', 'goal']
    assert 1.5 <= manager.shown[1][0] < 1.8


def test_the_other_riders_class_takes_over_while_this_rider_is_showing(clock):
    joel, jen = rider('Joel'), rider('Jen', [booking('n', NOW + 20 + 5 * MINUTE)])
    manager = loop_over(clock, joel, jen, pages=[('username', {'fact_keys': []}, 60), ('goal', {}, 2)])
    held = [state for _, name, state in manager.shown if name == 'next_class']
    assert len(held) == 1 and held[0]['booking']['id'] == 'n'


def test_a_celebration_finishes_before_a_takeover_starts(clock):
    joel = rider('Joel', [booking('j', NOW + 5 * MINUTE + 5)])
    pages = [('celebration', {'number': 100, 'milestone': 100}, 30), ('pr', {'workout_id': 'w'}, 30), ('goal', {}, 5)]
    joel['dashboard'].acknowledge_milestone = Mock()
    joel['dashboard'].acknowledge_pr = Mock()
    manager = loop_over(clock, joel, pages=pages)
    # due 5 s into the celebration, which finishes first; the takeover comes before the next page
    assert [n for _, n, _ in manager.shown] == ['celebration', 'next_class', 'pr', 'goal']
    assert 30 <= manager.shown[1][0] < 31
    joel['dashboard'].acknowledge_milestone.assert_called_once_with(100)
    joel['dashboard'].acknowledge_pr.assert_called_once_with('w')
    pages = [('pr', {'workout_id': 'w'}, 30), ('goal', {}, 5)]
    clock.now = 0
    manager = loop_over(clock, joel, pages=pages)
    assert [n for _, n, _ in manager.shown][:2] == ['pr', 'next_class'] and manager.shown[1][0] >= 30


def test_a_cut_page_is_not_acknowledged_until_it_plays_through(clock):
    joel = rider('Joel', [booking('j', NOW + 5 * MINUTE + 10)])
    dashboard = joel['dashboard']
    dashboard.acknowledge_name_facts = Mock()
    loop_over(clock, joel, pages=[('username', {'fact_keys': ['k']}, 100)])
    dashboard.acknowledge_name_facts.assert_called_once_with(['k'])  # once, after its replay


def test_the_next_class_page_is_not_replayed_after_the_takeover_showed_it(clock):
    soon = booking('j', NOW + 5 * MINUTE + 10)
    joel = rider('Joel', [soon])
    page_state = {'booking': soon, 'now': NOW, 'timezone': ZONE}
    manager = loop_over(clock, joel, pages=[('next_class', page_state, 100), ('goal', {}, 2)])
    # The page began as a rotation page, the takeover took over from it, and it isn't played a third time.
    assert [n for _, n, _ in manager.shown] == ['next_class', 'next_class', 'goal']


def test_a_rotations_next_class_page_counts_from_the_time_it_plays_and_skips_a_class_that_has_gone(clock):
    soon = booking('j', NOW + 20 * MINUTE)
    joel = rider('Joel', [soon], next_class_takeover_minutes=0)
    stale = {'booking': soon, 'now': NOW, 'timezone': ZONE}
    manager = loop_over(clock, joel, pages=[('goal', {}, 120), ('next_class', stale, 5)])
    state = manager.shown[-1][2]
    assert state['now'] == NOW + 120 and state['booking'] == soon
    gone = booking('g', NOW + 30)
    clock.now = 0
    manager = loop_over(clock, rider('Joel', [gone], next_class_takeover_minutes=0),
                        pages=[('goal', {}, SHOWN_AFTER_START + 31), ('next_class', {**stale, 'booking': gone}, 5)])
    assert [n for _, n, _ in manager.shown] == ['goal']


def test_with_the_setting_off_or_no_page_nothing_interrupts_the_rotation(clock):
    for joel in (rider('Joel', [booking('j', NOW + 100)], next_class_takeover_minutes=0),
                 rider('Joel', [booking('j', NOW + 100)], rotation=['username'])):
        clock.now = 0
        manager = loop_over(clock, joel, pages=[('goal', {}, 60), ('goal', {}, 60)])
        assert [n for _, n, _ in manager.shown] == ['goal', 'goal'] and clock.now == 120


def test_the_loop_reads_only_the_snapshot_never_the_network(clock):
    joel = rider('Joel', [booking('j', NOW + 5 * MINUTE + 30)])
    with patch('requests.Session.request', side_effect=AssertionError('network')):
        manager = loop_over(clock, joel, pages=[('goal', {}, 90)])
    assert [n for _, n, _ in manager.shown] == ['goal', 'next_class', 'goal']


def test_the_real_rotation_takes_over_and_resumes(clock):
    joel = rider('Joel', [booking('j', NOW + 25 + 5 * MINUTE)], rotation=['latest_workouts', 'username', 'next_class'])
    manager = loop_over(clock, joel)
    names = [n for _, n, _ in manager.shown]
    assert names.count('next_class') >= 1 and names.index('next_class') > 0  # after the pages it cut into


def test_the_multi_user_loop_gives_every_rider_the_same_takeover(clock):
    first, second = Mock(), Mock()
    profiles = [{'name': 'First', 'dashboard': first}, {'name': 'Second', 'dashboard': second}]
    active = {'dashboard': first}
    with patch('peloton_led.run_display_loop') as run:
        run_multi_user_loop(Mock(), profiles, {}, active, cycles=1)
    takeovers = [call.kwargs['takeover'] for call in run.call_args_list]
    assert len(takeovers) == 2 and takeovers[0] is takeovers[1]
    assert isinstance(takeovers[0], NextClassTakeover) and takeovers[0].profiles == profiles
    assert takeovers[0].active is active


# ---- config ---------------------------------------------------------------------------------------------------------
def checked(**display):
    return validate_config({'display': display}, 'config.json')['display']


def test_the_takeover_setting_defaults_to_five_and_takes_zero_to_ten():
    assert checked()['next_class_takeover_minutes'] == 5
    for minutes in range(0, TAKEOVER_MAX_MINUTES + 1):
        assert checked(next_class_takeover_minutes=minutes)['next_class_takeover_minutes'] == minutes


@pytest.mark.parametrize('bad', [-1, 11, 2.5, True, False, '5', None, [5]])
def test_the_takeover_setting_rejects_bad_values(bad):
    with pytest.raises(ValueError, match='next_class_takeover_minutes'):
        checked(next_class_takeover_minutes=bad)
