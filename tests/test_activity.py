"""PR B: the streak reminder and the activity heatmap, built from the workout log."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from display.display import initialize_fonts
from display.ui.heatmap_screen import EMPTY, HeatmapScreen, heatmap_cells, level_color
from display.ui.streak_risk_screen import StreakRiskScreen, days_left_text
from peloton.activity import counts_for_streaks, daily_minutes, streak_week_workouts
from peloton.config import load_config
from peloton.workout_log import WorkoutLog
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix

ZONE = 'America/New_York'
# Saturday 2026-10-31, 12:00 New York time.
SATURDAY = datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)


def _w(identity, when, status='COMPLETE', minutes=20, synced=False):
    return {'id': identity, 'status': status, 'start_time': int(when.timestamp()), 'fitness_discipline': 'cycling',
            'ride': {'duration': minutes * 60}, 'is_3p_fit_feed_workout_excluded_from_streaks': synced}


# calculations

def test_streak_week_counts_only_streak_eligible_completed_workouts_since_monday():
    workouts = [_w('ride', SATURDAY - timedelta(hours=2)),
                _w('watch-walk', SATURDAY - timedelta(hours=1), synced=True),
                _w('running', SATURDAY - timedelta(minutes=5), status='IN_PROGRESS'),
                _w('last-sunday', SATURDAY - timedelta(days=6))]
    assert streak_week_workouts(workouts, ZONE, now=SATURDAY) == 1
    assert streak_week_workouts(workouts[1:], ZONE, now=SATURDAY) == 0
    assert counts_for_streaks({}) and not counts_for_streaks({'is_3p_fit_feed_workout_excluded_from_streaks': True})


def test_daily_minutes_covers_twelve_monday_aligned_weeks_through_today():
    workouts = [_w('a', SATURDAY - timedelta(hours=3), minutes=30), _w('b', SATURDAY - timedelta(hours=2), minutes=15),
                _w('c', SATURDAY - timedelta(days=1), minutes=45),
                _w('first-day', datetime(2026, 8, 10, 16, tzinfo=timezone.utc)),      # Monday, 12 weeks back
                _w('too-old', datetime(2026, 8, 9, 16, tzinfo=timezone.utc)),
                _w('unfinished', SATURDAY, status='IN_PROGRESS'),
                {'id': 'undated', 'status': 'COMPLETE', 'ride': {'duration': 600}}]
    assert daily_minutes(workouts, ZONE, now=SATURDAY) == {
        '2026-08-10': 20, '2026-10-30': 45, '2026-10-31': 45}


def test_log_derives_both_and_keeps_the_heatmap_for_a_complete_log():
    log = WorkoutLog('unused')
    now = datetime.now(timezone.utc)
    log.merge([_w('today', now - timedelta(minutes=30)), _w('synced', now - timedelta(minutes=20), synced=True)])
    partial = log.derived(tzname=ZONE)
    assert partial['streak_week_workouts'] == 1 and partial['activity_days'] == {}
    log.backfill['complete'] = True
    full = log.derived(tzname=ZONE)
    assert sum(full['activity_days'].values()) == 40
    row = log.workouts['synced']
    assert row['counts_for_streaks'] is False


# rotation pages

def _snapshot(week_workouts, current=74, days=None):
    return {'me': {'timezone': ZONE}, 'summaries': [], 'status': 'ready', 'totals': {},
            'streaks': {'current_weekly': current, 'best_weekly': 80},
            'streak_week_workouts': week_workouts, 'activity_days': days if days is not None else {}}


def _display(**extra):
    return {'rotation': ['streaks', 'heatmap'], 'duration': 1, 'overview_duration': 5,
            'last_workout_duration': 1, 'color': 'white', 'timezone': ZONE, **extra}


@pytest.mark.parametrize('weekday, workouts, reminder_day, expected', [
    (5, 0, 5, 'streak_risk'),       # Saturday, nothing yet
    (6, 0, 5, 'streak_risk'),       # Sunday
    (4, 0, 5, 'streak'),            # Friday: too early
    (5, 1, 5, 'streak'),            # already kept
    (5, None, 5, 'streak'),         # unknown (log not loaded): no false alarm
    (3, 0, 3, 'streak_risk'),       # configurable day
    (6, 0, None, 'streak'),         # disabled
])
def test_streak_page_becomes_the_reminder_late_in_an_empty_week(monkeypatch, weekday, workouts, reminder_day, expected):
    monkeypatch.setattr('peloton_led.week_day', lambda zone: weekday)
    pages = build_rotation_pages(_snapshot(workouts), Mock(), _display(streak_reminder_day=reminder_day), 'R', 64)
    assert [p[0] for p in pages] == [expected]
    if expected == 'streak_risk':
        assert pages[0][1] == {'current': 74, 'days_left': 7 - weekday}
        assert pages[0][2] == 5


def test_heatmap_page_needs_activity(monkeypatch):
    monkeypatch.setattr('peloton_led.week_day', lambda zone: 1)
    days = {'2026-10-30': 45}
    pages = build_rotation_pages(_snapshot(1, days=days), Mock(), _display(), 'R', 32)
    assert [p[0] for p in pages] == ['streak', 'heatmap']
    assert pages[1][1]['days'] == days and pages[1][1]['weeks'] == 12
    assert date.fromisoformat(pages[1][1]['today'])
    assert [p[0] for p in build_rotation_pages(_snapshot(1), Mock(), _display(), 'R', 32)] == ['streak']


# screens

def test_heatmap_cells_and_levels():
    cells = heatmap_cells({'2026-10-31': 100, '2026-08-10': 5}, date(2026, 10, 31), 12)
    assert len(cells) == 11 * 7 + 6
    assert cells[0] == (0, 0, level_color(5)) and cells[-1] == (11, 5, level_color(100))
    assert level_color(0) == EMPTY and level_color(None) == EMPTY
    assert level_color(19) != level_color(20) != level_color(45) != level_color(90)


@pytest.mark.parametrize('height', [32, 64])
def test_heatmap_fits_and_marks_today(height):
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    assert HeatmapScreen().render(matrix, {'days': {'2026-10-31': 120}, 'today': '2026-10-31', 'weeks': 12})
    pixels = matrix.image.load()
    lit = [(x, y) for x in range(64) for y in range(height) if pixels[x, y] != (0, 0, 0)]
    assert min(x for x, _ in lit) >= 1 and max(x for x, _ in lit) <= 62
    assert max(y for _, y in lit) < height
    assert any(pixels[x, y] == level_color(120) for x, y in lit)
    assert not HeatmapScreen().render(matrix, {'days': {}, 'today': 'someday'})


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('current, days_left', [(1, 1), (74, 2), (1074, 2)])
def test_streak_reminder_fits_both_boards(height, current, days_left):
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    assert StreakRiskScreen().render(matrix, {'current': current, 'days_left': days_left})
    pixels = matrix.image.load()
    lit_x = [x for x in range(64) for y in range(height) if pixels[x, y] != (0, 0, 0)]
    assert min(lit_x) >= 1 and max(lit_x) <= 62


def test_streak_reminder_rejects_bad_state_and_words_the_deadline():
    initialize_fonts(64)
    assert not StreakRiskScreen().render(ImageMatrix(), {'current': 0, 'days_left': 2})
    assert not StreakRiskScreen().render(ImageMatrix(), None)
    assert days_left_text(1) == 'LAST DAY' and days_left_text(2) == '2 DAYS LEFT'


# config

def test_config_accepts_the_heatmap_and_validates_the_reminder_day(tmp_path):
    import json
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'display': {'rotation': ['heatmap'], 'streak_reminder_day': None}}))
    assert load_config(path)['display']['streak_reminder_day'] is None
    path.write_text(json.dumps({'display': {}}))
    display = load_config(path)['display']
    assert display['streak_reminder_day'] == 5 and 'heatmap' in display['rotation']
    for bad in (7, -1, True, 'saturday'):
        path.write_text(json.dumps({'display': {'streak_reminder_day': bad}}))
        with pytest.raises(ValueError, match='streak_reminder_day'):
            load_config(path)
