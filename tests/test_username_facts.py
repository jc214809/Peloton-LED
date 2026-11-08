"""The name page's varied highlights: the last 30 days' and per-discipline figures from the workout log,
each fact's data threshold, and which facts each pass shows."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.username import UsernameScreen
from peloton.activity import discipline_instructor_counts, recent_activity, recent_start
from peloton.username_facts import (MIN_RANKED_CLASSES, discipline_facts, instructor_rankings,
                                    username_details)
from peloton.workout_log import WorkoutLog
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix

ZONE = 'America/New_York'
# Sunday 2026-11-08, 12:00 New York time.
NOW = datetime(2026, 11, 8, 17, 0, tzinfo=timezone.utc)
NAMES = {'jess': 'Jess Sims', 'andy': 'Andy Speer', 'adrian': 'Adrian Williams', 'cody': 'Cody Rigsby',
         'robin': 'Robin Arzon'}


def _w(identity, when, discipline='strength', instructor='jess', minutes=20, status='COMPLETE'):
    ride = {'fitness_discipline': discipline, 'duration': minutes * 60}
    if instructor:
        ride['instructor'] = {'id': instructor, 'name': NAMES[instructor]}
    return {'id': identity, 'status': status, 'start_time': int(when.timestamp()),
            'fitness_discipline': discipline, 'ride': ride}


# log figures

def test_last_30_days_start_at_midnight_29_days_before_today_in_the_display_timezone():
    # 00:30 UTC on 1 November is still 31 October in New York: the window opens 2 October.
    first, current = recent_start(ZONE, datetime(2026, 11, 1, 0, 30, tzinfo=timezone.utc))
    assert (first.month, first.day, first.hour) == (10, 2, 0)
    assert current.day == 31


def test_recent_activity_counts_completed_workouts_in_the_last_30_days():
    workouts = [_w('a', NOW - timedelta(days=1), minutes=30),
                _w('b', NOW - timedelta(days=12), discipline='cycling', instructor='cody', minutes=45),
                _w('c', NOW - timedelta(days=3), instructor=None, discipline='meditation', minutes=10),
                _w('quit', NOW - timedelta(hours=1), status='IN_PROGRESS'),
                # 10 October, 00:30 local: the window's first day. 9 October is a day too early.
                _w('first-day', datetime(2026, 10, 10, 4, 30, tzinfo=timezone.utc), minutes=5),
                _w('too-early', datetime(2026, 10, 10, 3, 30, tzinfo=timezone.utc))]
    assert recent_activity(workouts, ZONE, now=NOW) == {
        'workouts': 4, 'minutes': 90, 'disciplines': {'strength': 2, 'cycling': 1, 'meditation': 1},
        'instructor_counts': {'jess': 2, 'cody': 1}}
    assert recent_activity([], ZONE, now=NOW) == {'workouts': 0, 'minutes': 0, 'disciplines': {},
                                                  'instructor_counts': {}}


def test_the_first_of_a_month_still_has_the_last_30_days():
    # The reason for a rolling window: on 1 November, October's workouts still count.
    first_of_month = datetime(2026, 11, 1, 17, 0, tzinfo=timezone.utc)
    workouts = [_w(str(day), first_of_month - timedelta(days=day)) for day in range(1, 20)]
    assert recent_activity(workouts, ZONE, now=first_of_month)['workouts'] == 19


def test_discipline_instructor_counts_split_the_tally_by_discipline():
    workouts = [_w('a', NOW, instructor='jess'), _w('b', NOW, instructor='jess'),
                _w('c', NOW, instructor='andy'), _w('d', NOW, discipline='cycling', instructor='jess'),
                _w('e', NOW, discipline='meditation', instructor=None),
                _w('f', NOW, discipline='strength', instructor='andy', status='IN_PROGRESS')]
    assert discipline_instructor_counts(workouts) == {'strength': {'jess': 2, 'andy': 1},
                                                      'cycling': {'jess': 1}}


def test_log_derives_recent_and_discipline_figures_only_once_complete():
    log = WorkoutLog('unused')
    log.merge([_w('a', NOW - timedelta(days=1)), _w('b', NOW - timedelta(days=2), discipline='cycling',
                                                   instructor='cody')])
    partial = log.derived(tzname=ZONE, now=NOW)
    assert partial['recent_activity'] == {} and partial['discipline_instructor_counts'] == {}
    log.backfill['complete'] = True
    full = log.derived(tzname=ZONE, now=NOW)
    assert full['recent_activity']['workouts'] == 2
    assert full['recent_activity']['disciplines'] == {'strength': 1, 'cycling': 1}
    assert full['discipline_instructor_counts'] == {'strength': {'jess': 1}, 'cycling': {'cody': 1}}


# facts

def _snapshot(**extra):
    snapshot = {'totals': {'Total Workouts': 1234, 'Cycling': 700, 'Strength': 500},
                'weekly_progress': {'workouts': 3, 'minutes': 75},
                'instructor_counts': {'jess': 300, 'cody': 250, 'andy': 200, 'robin': 5},
                'instructor_names': NAMES}
    snapshot.update(extra)
    return snapshot


RECENT = {'workouts': 12, 'minutes': 340,
         'disciplines': {'strength': 6, 'cycling': 4, 'yoga': 1, 'rowing': 1},
         'instructor_counts': {'jess': 4, 'andy': 3, 'cody': 2, 'robin': 1}}
BY_DISCIPLINE = {'strength': {'jess': 150, 'andy': 120, 'adrian': 40},
                 'cycling': {'cody': 250, 'robin': 100, 'jess': 3},
                 'rowing': {'jess': 1}}


def test_discipline_facts_in_rotation_order():
    facts = discipline_facts(_snapshot(recent_activity=RECENT))
    assert [(f['label'], f['lines']) for f in facts] == [
        ('TOP DISCIPLINE', ['CYCLING', '700 WORKOUTS']),
        ('LAST 30 DAYS', ['12 WORKOUTS', '340 MINUTES']),
        ('MOST IN 30 DAYS', ['STRENGTH', '6 WORKOUTS'])]


def test_recent_favourite_is_skipped_when_it_is_the_all_time_one():
    recent = dict(RECENT, disciplines={'cycling': 6, 'strength': 4})
    assert [f['label'] for f in discipline_facts(_snapshot(recent_activity=recent))] == ['TOP DISCIPLINE', 'LAST 30 DAYS']
    # Matched by discipline, though totals are labelled ('Bike Bootcamp') and the log uses slugs.
    totals = {'Total Workouts': 50, 'Bike Bootcamp': 30, 'Cycling': 20}
    recent = dict(RECENT, disciplines={'bike_bootcamp': 3})
    assert 'MOST IN 30 DAYS' not in [f['label'] for f in discipline_facts(_snapshot(totals=totals, recent_activity=recent))]
    # No all-time totals yet: the last 30 days' favourite still shows.
    assert [f['label'] for f in discipline_facts(_snapshot(totals={}, recent_activity=recent))] == [
        'LAST 30 DAYS', 'MOST IN 30 DAYS']


def test_recent_facts_need_enough_data():
    # Before the backfill finishes there are no last 30 days at all: only the all-time fact.
    assert [f['label'] for f in discipline_facts(_snapshot())] == ['TOP DISCIPLINE']
    # One workout in 30 days: its count, but no "most" from a single workout.
    one = {'workouts': 1, 'minutes': 20, 'disciplines': {'strength': 1}, 'instructor_counts': {}}
    assert [f['label'] for f in discipline_facts(_snapshot(recent_activity=one))] == ['TOP DISCIPLINE', 'LAST 30 DAYS']
    assert discipline_facts(_snapshot(recent_activity=one))[1]['lines'] == ['1 WORKOUT', '20 MINUTES']
    # One discipline in 30 days, not the all-time favourite: its most.
    single = dict(one, workouts=3, disciplines={'strength': 3})
    assert [f['label'] for f in discipline_facts(_snapshot(recent_activity=single))] == [
        'TOP DISCIPLINE', 'LAST 30 DAYS', 'MOST IN 30 DAYS']
    assert discipline_facts({'totals': {}}) == []


def test_instructor_rankings_in_rotation_order_with_thresholds():
    rankings = instructor_rankings(_snapshot(recent_activity=RECENT, discipline_instructor_counts=BY_DISCIPLINE))
    assert [[d['label'] for d in ranking] for ranking in rankings] == [
        ['TOP INSTRUCTOR', '2ND INSTRUCTOR', '3RD INSTRUCTOR'],
        ['TOP IN 30 DAYS', '2ND IN 30 DAYS', '3RD IN 30 DAYS'],
        # Cycling's third has 3 classes, enough; most-done discipline first. Rowing has one class.
        ['TOP CYCLING', '2ND CYCLING', '3RD CYCLING'],
        ['TOP STRENGTH', '2ND STRENGTH', '3RD STRENGTH']]
    assert rankings[1][2]['lines'] == ['CODY RIGSBY', '2 CLASSES']
    assert rankings[3][0]['lines'] == ['JESS SIMS', '150 CLASSES']


def test_a_ranking_with_a_thin_third_place_is_skipped():
    recent = dict(RECENT, instructor_counts={'jess': 4, 'andy': 3, 'cody': MIN_RANKED_CLASSES - 1})
    rankings = instructor_rankings(_snapshot(recent_activity=recent))
    assert [ranking[0]['label'] for ranking in rankings] == ['TOP INSTRUCTOR']
    # Two instructors in 30 days isn't a top three either.
    recent = dict(RECENT, instructor_counts={'jess': 4, 'andy': 3})
    assert len(instructor_rankings(_snapshot(recent_activity=recent))) == 1


def test_all_time_ranking_keeps_any_count_as_before():
    snapshot = _snapshot(instructor_counts={'jess': 1}, instructor_names=NAMES)
    assert [[d['lines'] for d in r] for r in instructor_rankings(snapshot)] == [[['JESS SIMS', '1 CLASS']]]
    assert instructor_rankings({}) == []


def test_each_pass_shows_the_total_this_week_one_fact_and_one_ranking():
    snapshot = _snapshot(recent_activity=RECENT, discipline_instructor_counts=BY_DISCIPLINE)
    labels = [[d['label'] for d in username_details(snapshot, index)] for index in range(5)]
    assert labels == [
        ['TOTAL WORKOUTS', 'THIS WEEK', 'TOP DISCIPLINE', 'TOP INSTRUCTOR', '2ND INSTRUCTOR', '3RD INSTRUCTOR'],
        ['TOTAL WORKOUTS', 'THIS WEEK', 'LAST 30 DAYS', 'TOP IN 30 DAYS', '2ND IN 30 DAYS', '3RD IN 30 DAYS'],
        ['TOTAL WORKOUTS', 'THIS WEEK', 'MOST IN 30 DAYS', 'TOP CYCLING', '2ND CYCLING', '3RD CYCLING'],
        ['TOTAL WORKOUTS', 'THIS WEEK', 'TOP DISCIPLINE', 'TOP STRENGTH', '2ND STRENGTH', '3RD STRENGTH'],
        ['TOTAL WORKOUTS', 'THIS WEEK', 'LAST 30 DAYS', 'TOP INSTRUCTOR', '2ND INSTRUCTOR', '3RD INSTRUCTOR']]


def test_rotation_passes_its_pass_index_to_the_name_page():
    dashboard = Mock()
    dashboard.pending_discipline_milestones.return_value = []
    display = {'rotation': ['username'], 'screen_durations': {'username': 1}, 'duration': 1,
               'overview_duration': 1, 'last_workout_duration': 1, 'color': 'white'}
    snapshot = _snapshot(me={'username': 'Rider'}, summaries=[], status='ready', recent_activity=RECENT,
                         discipline_instructor_counts=BY_DISCIPLINE)
    page = build_rotation_pages(snapshot, dashboard, display, 'Rider', 64, pass_index=2)[0]
    assert [d['label'] for d in page[1]['details']][2:4] == ['MOST IN 30 DAYS', 'TOP CYCLING']
    # Six highlights every pass, so the page is as long as before.
    assert page[2] == pytest.approx(24.0)


# fitting

LONG_DISCIPLINES = ('bike_bootcamp', 'tread_bootcamp', 'row_bootcamp', 'running_outdoor', 'walking_outdoor',
                    'meditation', 'stretching')


@pytest.mark.parametrize('height', (64, 32))
def test_every_label_and_line_fits_or_has_a_short_label_that_does(height):
    initialize_fonts(height)
    small, value = loaded_fonts['stats'], loaded_fonts['info']
    room = 64 - 4
    by_discipline = {slug: {'jess': 9, 'andy': 8, 'adrian': 7} for slug in LONG_DISCIPLINES}
    recent = dict(RECENT, workouts=1234, minutes=9999,
                 disciplines={'tread_bootcamp': 30, 'walking_outdoor': 1})
    snapshot = _snapshot(recent_activity=recent, discipline_instructor_counts=by_discipline)
    details = discipline_facts(snapshot) + [d for r in instructor_rankings(snapshot) for d in r]
    assert len(details) == 3 + 3 * (2 + len(LONG_DISCIPLINES))
    for detail in details:
        label = detail['label'] if get_text_width(small, detail['label']) <= room else detail.get('short_label')
        assert label and get_text_width(small, label) <= room, detail['label']
        for line in detail['lines']:
            assert get_text_width(value, line) <= room, line


def test_screen_draws_the_short_label_when_the_label_is_too_wide():
    initialize_fonts(32)

    def frame(detail):
        matrix, screen = ImageMatrix(height=32), UsernameScreen()
        state = {'username': 'Rider', 'details': [detail]}
        screen.on_enter(matrix, state)
        screen.update(1.0)
        screen.render(matrix, state)
        return matrix.image.tobytes()

    lines = ['JESS SIMS', '9 CLASSES']
    short = frame({'label': '3RD BOOTCAMP', 'lines': lines})
    assert frame({'label': '3RD TREAD BOOTCAMP', 'short_label': '3RD BOOTCAMP', 'lines': lines}) == short
    # A label that fits keeps its full text.
    assert frame({'label': 'TOP CYCLING', 'short_label': 'TOP X', 'lines': lines}) == frame(
        {'label': 'TOP CYCLING', 'lines': lines})
