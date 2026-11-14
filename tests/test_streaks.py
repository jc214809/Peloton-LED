"""Streak screen (weekly and daily) and the streak data behind it."""
from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest

from display.display import initialize_fonts
from display.ui.streak_risk_screen import StreakRiskScreen
from display.ui.streak_screen import (FLAME_FRAME_SECONDS, FLAME_H, FLAME_RAMP, FLAME_W, SPARK_SECONDS,
                                      StreakScreen, _spark, daily_streak_lines, flame_color, flame_pixels,
                                      since_text, streak_lines, streak_views)
from peloton.activity import daily_streak_start
from peloton.cache import load_snapshot, save_snapshot
from peloton.config import load_config
from peloton.totals import parse_streaks
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix


def test_parse_streaks_keeps_only_whole_non_negative_counts():
    overview = {'streaks': {'current_weekly': 2, 'best_weekly': 74, 'current_daily': 3,
                            'start_date_of_current_weekly': 1789410461,
                            'start_date_of_current_daily': 1793750400}}
    assert parse_streaks(overview) == {'current_weekly': 2, 'best_weekly': 74, 'current_daily': 3,
                                       'start_date_of_current_daily': 1793750400}
    assert parse_streaks({'streaks': {'current_daily': 3, 'start_date_of_current_daily': None}}) == {
        'current_daily': 3}
    assert parse_streaks({'streaks': {'current_weekly': '2', 'best_weekly': -1,
                                      'current_daily': True}}) == {}
    assert parse_streaks({'streaks': None}) == {}
    assert parse_streaks({}) == {}
    assert parse_streaks(None) == {}


def test_streak_lines_mark_a_tied_record_and_skip_zero():
    assert streak_lines({'current_weekly': 2, 'best_weekly': 74}) == (2, 'WEEK STREAK', 'BEST 74 WEEKS', False)
    assert streak_lines({'current_weekly': 41, 'best_weekly': 41})[2:] == ('PERSONAL BEST', True)
    assert streak_lines({'current_weekly': 5})[2] == ''
    assert streak_lines({'current_weekly': 0, 'best_weekly': 74}) is None
    assert streak_lines({}) is None
    assert streak_lines(None) is None


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('streaks', [
    {'current_weekly': 2, 'best_weekly': 74},
    {'current_weekly': 1234, 'best_weekly': 1500},
    # The widest daily footers: 4-digit count, a three-wide month and a year.
    {'current_daily': 1234, 'daily_start': '2023-11-30', 'today': '2026-11-02'},
    {'current_weekly': 103, 'current_daily': 703, 'daily_start': '2024-11-30', 'today': '2026-11-02',
     'view': 'daily'}])
def test_streak_screen_fits_the_panel(height, streaks):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    assert StreakScreen().render(matrix, streaks)
    found = {c for _, c in matrix.image.getcolors(64 * 64)}
    assert set(flame_pixels(0).values()) <= found
    # Nothing is drawn in the 1-px side margins, so no text ran off the edge.
    pixels = matrix.image.load()
    assert all(pixels[x, y] == (0, 0, 0) for x in (0, 63) for y in range(height))


def test_streak_screen_renders_nothing_without_a_streak():
    matrix = ImageMatrix(height=64)
    initialize_fonts(64)
    assert not StreakScreen().render(matrix, {'current_weekly': 0})


def test_daily_streak_shows_from_two_days_with_its_start_date():
    today = '2026-11-02'
    assert daily_streak_lines({'current_daily': 703, 'daily_start': '2024-12-01', 'today': today}) == (
        703, 'DAY STREAK', 'SINCE DEC 2024', False)
    assert daily_streak_lines({'current_daily': 3, 'daily_start': '2026-10-31', 'today': today})[2] == 'SINCE OCT 31'
    # Missing or damaged dates just drop the footer.
    assert daily_streak_lines({'current_daily': 3})[2] == ''
    assert daily_streak_lines({'current_daily': 3, 'daily_start': 'soon', 'today': today})[2] == ''
    assert daily_streak_lines({'current_daily': 3, 'daily_start': None, 'today': today})[2] == ''
    for current in (0, 1, True, '5', None):
        assert daily_streak_lines({'current_daily': current}) is None
    assert daily_streak_lines(None) is None


def test_since_text_switches_to_the_year_after_a_year():
    today = date(2026, 11, 2)
    assert since_text(date(2025, 11, 3), today) == 'SINCE NOV 3'
    assert since_text(date(2025, 11, 2), today) == 'SINCE NOV 2025'


def test_streak_views_put_weekly_first_and_skip_empty_ones():
    both = {'current_weekly': 3, 'best_weekly': 9, 'current_daily': 12}
    assert [(view, lines[1]) for view, lines in streak_views(both)] == [
        ('weekly', 'WEEK STREAK'), ('daily', 'DAY STREAK')]
    assert [view for view, _ in streak_views({**both, 'current_daily': 1})] == ['weekly']
    assert [view for view, _ in streak_views({**both, 'current_weekly': 0})] == ['daily']
    assert streak_views({'current_weekly': 0, 'current_daily': 1}) == []


def _render(state):
    matrix = ImageMatrix(height=64)
    assert StreakScreen().render(matrix, state)
    return matrix.image.tobytes()


def test_streak_screen_draws_the_view_it_is_given():
    initialize_fonts(64)
    both = {'current_weekly': 3, 'best_weekly': 9, 'current_daily': 12}
    weekly = _render({'current_weekly': 3, 'best_weekly': 9})
    daily = _render({'current_daily': 12})
    assert weekly != daily
    assert _render({**both, 'view': 'weekly'}) == weekly
    assert _render({**both, 'view': 'daily'}) == daily
    # No view, an unknown one, or one with nothing to show: the first available.
    assert _render(both) == weekly
    assert _render({**both, 'view': 'monthly'}) == weekly
    assert _render({'current_daily': 12, 'view': 'weekly'}) == daily


def _pin_today(monkeypatch, day):
    monkeypatch.setattr('peloton_led.week_start', lambda zone=None: (None, datetime(*day, 12)))


def test_rotation_alternates_weekly_and_daily_across_passes(monkeypatch):
    _pin_today(monkeypatch, (2026, 11, 2))
    display = {'rotation': ['streaks'], 'last_workout_duration': 15, 'overview_duration': 4,
               'screen_durations': {'streaks': 6}}
    snapshot = {'summaries': [], 'totals': {}, 'status': 'ready',
                'streaks': {'current_weekly': 3, 'best_weekly': 9, 'current_daily': 12},
                'activity_days': {'2026-11-01': 30}}
    # Nothing logged today yet: the streak runs through yesterday.
    expected = {'current_weekly': 3, 'best_weekly': 9, 'current_daily': 12,
                'today': '2026-11-02', 'daily_start': '2026-10-21'}
    # One streak per pass, each for the configured time: weekly, daily, weekly.
    for pass_index, view in enumerate(('weekly', 'daily', 'weekly')):
        assert build_rotation_pages(snapshot, Mock(), display, 'R', 64, pass_index=pass_index) == [
            ('streak', {**expected, 'view': view}, 6)]
    # Weekly alone shows on every pass.
    snapshot['streaks']['current_daily'] = 1
    assert build_rotation_pages(snapshot, Mock(), display, 'R', 64, pass_index=1)[0][1]['view'] == 'weekly'
    # A daily streak still shows when the weekly one is over, and never
    # turns into the weekend reminder for a zero-week streak.
    snapshot['streaks'] = {'current_weekly': 0, 'best_weekly': 9, 'current_daily': 5}
    snapshot['streak_week_workouts'] = 0
    monkeypatch.setattr('peloton_led.week_day', lambda zone: 6)
    pages = build_rotation_pages(snapshot, Mock(), display, 'R', 64)
    assert [(name, state['view'], state['daily_start']) for name, state, _ in pages] == [
        ('streak', 'daily', '2026-10-28')]
    # Peloton's own start date wins over counting back.
    snapshot['streaks']['start_date_of_current_daily'] = int(
        datetime(2026, 10, 27, 15, tzinfo=timezone.utc).timestamp())
    assert build_rotation_pages(snapshot, Mock(), {**display, 'timezone': 'America/New_York'},
                                'R', 64)[0][1]['daily_start'] == '2026-10-27'


def test_daily_streak_start_counts_back_from_today_or_yesterday():
    today = date(2026, 11, 2)
    assert daily_streak_start(3, today) == date(2026, 10, 31)  # no log yet: today counts
    assert daily_streak_start(3, today, {}) == date(2026, 10, 31)
    assert daily_streak_start(3, today, {'2026-11-02': 20}) == date(2026, 10, 31)
    assert daily_streak_start(3, today, {'2026-11-01': 20}) == date(2026, 10, 30)


def test_daily_streak_start_prefers_pelotons_date_on_the_display_calendar():
    today = date(2026, 11, 2)
    # 2024-12-01 03:00 UTC is still Nov 30 in New York.
    stamp = int(datetime(2024, 12, 1, 3, tzinfo=timezone.utc).timestamp())
    assert daily_streak_start(703, today, {}, stamp, 'America/New_York') == date(2024, 11, 30)
    assert daily_streak_start(703, today, {}, stamp, 'UTC') == date(2024, 12, 1)
    # A start after today, or one that isn't a timestamp, falls back to counting back.
    tomorrow = int(datetime(2026, 11, 3, 12, tzinfo=timezone.utc).timestamp())
    for bad in (tomorrow, 'soon', True, None):
        assert daily_streak_start(3, today, {}, bad, 'UTC') == date(2026, 10, 31)


def test_rotation_includes_streaks_only_when_there_is_one():
    display = {'rotation': ['streaks'], 'last_workout_duration': 15, 'overview_duration': 4,
               'screen_durations': {'streaks': 6}}
    snapshot = {'summaries': [], 'totals': {}, 'status': 'ready',
                'streaks': {'current_weekly': 3, 'best_weekly': 9}}
    assert build_rotation_pages(snapshot, Mock(), display, 'R', 64) == [
        ('streak', {'current_weekly': 3, 'best_weekly': 9, 'view': 'weekly'}, 6)]
    snapshot['streaks'] = {'current_weekly': 0}
    assert build_rotation_pages(snapshot, Mock(), display, 'R', 64) == []
    snapshot['streaks'] = {'current_weekly': 0, 'current_daily': 1}
    assert build_rotation_pages(snapshot, Mock(), display, 'R', 64) == []
    del snapshot['streaks']  # caches written before this feature
    assert build_rotation_pages(snapshot, Mock(), display, 'R', 64) == []


def test_streaks_survive_the_cache_and_bad_entries_are_dropped(tmp_path):
    path = tmp_path / 'cache.json'
    base = {'me': None, 'totals': {}, 'summaries': [], 'last_updated': 1.0}
    save_snapshot(path, {**base, 'streaks': {'current_weekly': 3}})
    assert load_snapshot(path)['streaks'] == {'current_weekly': 3}
    save_snapshot(path, {**base, 'streaks': {'current_weekly': 'lots'}})
    restored = load_snapshot(path)
    assert restored is not None and 'streaks' not in restored


def test_config_accepts_streaks_section_and_duration(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"display": {"rotation": ["streaks"], "screen_durations": {"streaks": 5}}}')
    assert load_config(str(path))['display']['rotation'] == ['streaks']


def _frames(seconds=8.0, step=FLAME_FRAME_SECONDS):
    return [flame_pixels(i * step) for i in range(int(seconds / step))]


def test_flame_stays_in_its_box_on_a_steady_base():
    frames = _frames()
    for pixels in frames:
        assert pixels and all(0 <= x < FLAME_W and 0 <= y < FLAME_H for x, y in pixels)
        # The bottom row is always lit across the middle: the base doesn't jump.
        assert {(x, FLAME_H - 1) for x in range(4, 8)} <= set(pixels)
    # The shape moves from one 20 fps frame to the next, but only a few pixels.
    changes = [len(set(a) ^ set(b)) for a, b in zip(frames, frames[1:])]
    assert sum(changes) > 0
    assert sum(changes) / len(changes) < 8


def test_flame_has_a_hot_core_and_tongues_that_rise_and_fall():
    frames = _frames()
    for pixels in frames:
        # The hottest colour sits low in the middle; the top rows are only tips.
        hottest = max(pixels, key=lambda p: sum(pixels[p]))
        assert hottest[1] >= 8 and 3 <= hottest[0] <= 8
    tops = [min(y for _, y in pixels) for pixels in frames]
    assert min(tops) == 0 and max(tops) >= 2
    # The side tongues rise and fall: how much is lit up beside the middle one changes.
    sides = [sum(1 for x, y in p if y <= 6 and (x <= 3 or x >= 8)) for p in frames]
    assert max(sides) - min(sides) >= 4


def test_flame_colours_follow_the_ramp():
    assert flame_color(-1) == FLAME_RAMP[0][1] and flame_color(2) == FLAME_RAMP[-1][1]
    for heat, rgb in FLAME_RAMP:
        assert flame_color(heat) == rgb
    reds = [flame_color(h / 20)[1] for h in range(21)]
    assert reds == sorted(reds)  # cooler to hotter only ever adds green: red, orange, yellow


def test_flame_is_repeatable_and_safe_with_odd_times():
    assert flame_pixels(3.21) == flame_pixels(3.21)
    for bad in (None, -1, float('nan'), float('inf'), '1', True):
        assert flame_pixels(bad) == flame_pixels(0)
    assert flame_pixels(1e12)  # any page length still draws


def test_sparks_rise_in_some_spans_and_not_others():
    spans = [[_spark(span * SPARK_SECONDS + i * 0.05) for i in range(int(SPARK_SECONDS / 0.05))]
             for span in range(20)]
    with_spark = [s for s in spans if any(s)]
    assert 0 < len(with_spark) < len(spans)
    for span in with_spark:
        rows = [spark[1] for spark in span if spark]
        assert rows == sorted(rows, reverse=True) and rows[0] == 6 and rows[-1] <= 1
        assert all(2 <= spark[0] < FLAME_W - 2 for spark in span if spark)


@pytest.mark.parametrize('screen, state', [
    (StreakScreen, {'current_weekly': 1234, 'best_weekly': 1500}),
    (StreakRiskScreen, {'current': 1234, 'days_left': 2})])
@pytest.mark.parametrize('height', [32, 64])
def test_flame_burns_on_the_page_and_restarts_on_entry(screen, state, height):
    initialize_fonts(height)
    page = screen()
    assert page.animated is True and page.atomic_frames is True
    assert page.frame_seconds == FLAME_FRAME_SECONDS
    drawn = []
    page.on_enter(None, state)
    for _ in range(10):
        matrix = ImageMatrix(height=height)
        assert page.render(matrix, state)
        pixels = matrix.image.load()
        # Every frame keeps the 1-px side margins clear.
        assert all(pixels[x, y] == (0, 0, 0) for x in (0, 63) for y in range(height))
        drawn.append(matrix.image.tobytes())
        page.update(FLAME_FRAME_SECONDS)
    assert len(set(drawn)) == len(drawn)
    page.update(-5)
    page.update(None)
    page.on_enter(None, state)
    matrix = ImageMatrix(height=height)
    page.render(matrix, state)
    assert matrix.image.tobytes() == drawn[0]


def test_render_streaks_draws_the_readme_screenshots(tmp_path, capsys):
    """Both README sheets: each page on 64x64 above and 64x32 below, from the screen code."""
    from PIL import Image

    from scripts import render_logo, render_streaks
    render_streaks.main(['--out-dir', str(tmp_path)])
    scale, gap, left = render_logo.SHEET_SCALE, render_logo.GAP, render_logo.LABEL_WIDTH
    for name, (screen_class, states) in render_streaks.SHEETS.items():
        sheet = Image.open(tmp_path / name).convert('RGB')
        assert sheet.size == (left + len(states) * (64 * scale + gap),
                              gap + 64 * scale + gap * 2 + 32 * scale + gap)
        top = gap
        for height in (64, 32):
            initialize_fonts(height)
            for index, state in enumerate(states):
                matrix = ImageMatrix(64, height)
                page = screen_class()
                page.update(render_streaks.FLAME_SECONDS)
                assert page.render(matrix, state)
                x = left + index * (64 * scale + gap)
                panel = sheet.crop((x, top, x + 64 * scale, top + height * scale))
                assert panel.tobytes() == matrix.image.resize(panel.size, Image.NEAREST).tobytes()
            top += height * scale + gap * 2
    assert capsys.readouterr().out.count('Wrote') == 2


def test_render_streaks_stops_on_a_page_it_cannot_draw():
    from scripts import render_streaks
    with pytest.raises(RuntimeError, match='drew nothing'):
        render_streaks.panels(StreakScreen, [{}], 64)
