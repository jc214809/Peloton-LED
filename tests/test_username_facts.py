"""The name page's varied highlights: time frames over the workout log (peloton.activity), the facts
each frame has enough data for, and which frame and fact each pass shows."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.username import UsernameScreen
from peloton.activity import discipline_instructor_counts, frame_bounds, frame_stats, period_stats
from peloton.username_facts import (FRAME_ORDER, MIN_RANKED_CLASSES, frame_facts, frame_rankings,
                                    frame_words, username_details, username_frames)
from peloton.workout_log import WorkoutLog
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix

ZONE = 'America/New_York'
# Sunday 2026-11-08, 12:00 New York time (the clocks went back on 1 November).
NOW = datetime(2026, 11, 8, 17, 0, tzinfo=timezone.utc)
NAMES = {'jess': 'Jess Sims', 'andy': 'Andy Speer', 'adrian': 'Adrian Williams', 'cody': 'Cody Rigsby',
         'robin': 'Robin Arzon'}


def _w(identity, when, discipline='strength', instructor='jess', minutes=20, status='COMPLETE', ride_id=None):
    ride = {'fitness_discipline': discipline, 'duration': minutes * 60, 'id': ride_id or f'class-{identity}'}
    if instructor:
        ride['instructor'] = {'id': instructor, 'name': NAMES[instructor]}
    return {'id': identity, 'status': status, 'start_time': int(when.timestamp()),
            'fitness_discipline': discipline, 'ride': ride}


def _local(year, month, day, hour=12):
    """A New York wall-clock time, as the UTC instant the log stores."""
    return datetime(year, month, day, hour, tzinfo=ZoneInfo(ZONE)).astimezone(timezone.utc)


# time frames

def test_frame_bounds_are_midnight_in_the_display_timezone():
    bounds = frame_bounds(ZONE, NOW)
    local = {key: tuple(None if edge is None else (edge.year, edge.month, edge.day, edge.hour, edge.minute)
                        for edge in edges) for key, edges in bounds.items()}
    assert local == {
        'week': ((2026, 11, 2, 0, 0), None),
        'last_week': ((2026, 10, 26, 0, 0), (2026, 11, 2, 0, 0)),
        '30d': ((2026, 10, 10, 0, 0), None),          # today and the 29 days before
        '90d': ((2026, 8, 11, 0, 0), None),
        'year': ((2026, 1, 1, 0, 0), None),
        'last_year': ((2025, 1, 1, 0, 0), (2026, 1, 1, 0, 0)),
        'all': (None, None)}


def test_frames_stay_on_local_midnight_across_the_clock_change():
    # 10 October is daylight time (-4), 2 November standard time (-5): both still start at 00:00.
    bounds = frame_bounds(ZONE, NOW)
    assert bounds['30d'][0].utcoffset() == timedelta(hours=-4)
    assert bounds['week'][0].utcoffset() == timedelta(hours=-5)
    assert bounds['30d'][0].astimezone(timezone.utc).hour == 4
    assert bounds['week'][0].astimezone(timezone.utc).hour == 5


def test_a_late_evening_workout_counts_on_the_local_day_not_the_utc_one():
    # 00:30 on 10 October in New York is the first moment of the 30-day window; 23:30 on 9 October
    # (already 10 October in UTC) is the last moment outside it.
    inside = _w('in', _local(2026, 10, 10, 0) + timedelta(minutes=30))
    outside = _w('out', _local(2026, 10, 9, 23) + timedelta(minutes=30))
    assert outside['start_time'] > inside['start_time'] - 3600 * 2   # about the same UTC time
    stats = frame_stats([inside, outside], ZONE, NOW)
    assert stats['30d']['workouts'] == 1 and stats['90d']['workouts'] == 2


def test_the_new_year_has_a_new_year_frame_and_last_year_is_the_whole_old_year():
    new_year = datetime(2027, 1, 1, 8, 0, tzinfo=timezone.utc)   # 03:00 on 1 January in New York
    workouts = [_w('today', new_year - timedelta(hours=1)),
                _w('new-years-eve', _local(2026, 12, 31, 20)),
                _w('spring', _local(2026, 4, 1)),
                _w('earlier', _local(2025, 6, 1))]
    stats = frame_stats(workouts, ZONE, new_year)
    assert (stats['year']['workouts'], stats['year']['year'], stats['year']['days']) == (1, 2027, 1)
    assert (stats['last_year']['workouts'], stats['last_year']['year'], stats['last_year']['days']) == (2, 2026, 365)
    assert stats['all']['workouts'] == 4 and stats['all']['days'] is None
    assert stats['30d']['workouts'] == 2


def test_frame_days_count_the_days_so_far():
    stats = frame_stats([], ZONE, NOW)
    assert {key: stats[key]['days'] for key in stats} == {
        'week': 7, 'last_week': 7, '30d': 30, '90d': 90, 'year': 312, 'last_year': 365, 'all': None}


def test_period_stats_counts_completed_workouts_in_a_window():
    workouts = [_w('a', NOW - timedelta(days=1), minutes=30),
                _w('b', NOW - timedelta(days=12), discipline='cycling', instructor='cody', minutes=45),
                _w('c', NOW - timedelta(days=3), instructor=None, discipline='meditation', minutes=10),
                _w('quit', NOW - timedelta(hours=1), status='IN_PROGRESS'),
                _w('future', NOW + timedelta(hours=1)),
                _w('old', NOW - timedelta(days=45))]
    start = frame_bounds(ZONE, NOW)['30d'][0]
    assert period_stats(workouts, start, None, ZONE, NOW) == {
        'workouts': 3, 'minutes': 85, 'disciplines': {'strength': 1, 'cycling': 1, 'meditation': 1},
        'instructor_counts': {'jess': 1, 'cody': 1}, 'instructors': 2, 'classes': 3, 'active_days': 3}
    assert period_stats([], None, None, ZONE, NOW)['workouts'] == 0
    assert period_stats(workouts, None, None, ZONE, NOW)['workouts'] == 4      # everything up to now


def test_different_classes_count_a_class_once_and_leave_out_workouts_with_no_class():
    workouts = [_w('a', NOW - timedelta(days=1), ride_id='hiit'), _w('b', NOW - timedelta(days=2), ride_id='hiit'),
                _w('c', NOW - timedelta(days=3), ride_id='power')]
    workouts.append({'id': 'just-ride', 'status': 'COMPLETE', 'start_time': int((NOW - timedelta(days=4)).timestamp()),
                     'fitness_discipline': 'cycling', 'ride': {}})
    stats = period_stats(workouts, None, None, ZONE, NOW)
    assert (stats['workouts'], stats['classes'], stats['active_days']) == (4, 2, 4)


def test_the_first_of_a_month_still_has_the_last_30_days():
    # The reason for rolling windows: on 1 November, October's workouts still count.
    first_of_month = datetime(2026, 11, 1, 17, 0, tzinfo=timezone.utc)
    workouts = [_w(str(day), first_of_month - timedelta(days=day)) for day in range(1, 20)]
    assert frame_stats(workouts, ZONE, first_of_month)['30d']['workouts'] == 19


def test_discipline_instructor_counts_split_the_tally_by_discipline():
    workouts = [_w('a', NOW, instructor='jess'), _w('b', NOW, instructor='jess'),
                _w('c', NOW, instructor='andy'), _w('d', NOW, discipline='cycling', instructor='jess'),
                _w('e', NOW, discipline='meditation', instructor=None),
                _w('f', NOW, discipline='strength', instructor='andy', status='IN_PROGRESS')]
    assert discipline_instructor_counts(workouts) == {'strength': {'jess': 2, 'andy': 1},
                                                      'cycling': {'jess': 1}}


def test_log_derives_time_frames_only_once_complete():
    log = WorkoutLog('unused')
    log.merge([_w('a', NOW - timedelta(days=1)), _w('b', NOW - timedelta(days=2), discipline='cycling',
                                                   instructor='cody')])
    partial = log.derived(tzname=ZONE, now=NOW)
    assert partial['time_frames'] == {} and partial['discipline_instructor_counts'] == {}
    log.backfill['complete'] = True
    full = log.derived(tzname=ZONE, now=NOW)
    assert set(full['time_frames']) == set(frame_bounds(ZONE, NOW))
    assert full['time_frames']['30d']['workouts'] == 2
    # The log keeps each class's ID, so distinct classes survive the trip through the log's rows.
    assert full['time_frames']['30d']['classes'] == 2
    assert full['time_frames']['30d']['disciplines'] == {'strength': 1, 'cycling': 1}
    assert full['discipline_instructor_counts'] == {'strength': {'jess': 1}, 'cycling': {'cody': 1}}


# facts

THIRTY = {'workouts': 12, 'minutes': 340, 'disciplines': {'strength': 6, 'cycling': 4, 'yoga': 1, 'rowing': 1},
          'instructor_counts': {'jess': 4, 'andy': 3, 'cody': 2, 'robin': 1}, 'instructors': 4, 'classes': 11,
          'active_days': 10, 'days': 30}
YEAR = {'year': 2026, 'workouts': 412, 'minutes': 9840, 'disciplines': {'cycling': 200, 'strength': 140},
        'instructor_counts': {'jess': 61, 'cody': 50, 'andy': 40}, 'instructors': 31, 'classes': 318,
        'active_days': 248, 'days': 312}
BY_DISCIPLINE = {'strength': {'jess': 150, 'andy': 120, 'adrian': 40},
                 'cycling': {'cody': 250, 'robin': 100, 'jess': 3},
                 'rowing': {'jess': 1}}


def _snapshot(**extra):
    snapshot = {'totals': {'Total Workouts': 1234, 'Cycling': 700, 'Strength': 500},
                'weekly_progress': {'workouts': 3, 'minutes': 75},
                'instructor_counts': {'jess': 300, 'cody': 250, 'andy': 200, 'robin': 5},
                'instructor_names': NAMES}
    snapshot.update(extra)
    return snapshot


def _full(**extra):
    return _snapshot(time_frames={'30d': THIRTY, 'year': YEAR}, discipline_instructor_counts=BY_DISCIPLINE, **extra)


def _labels(snapshot, index):
    return [d['label'] for d in username_details(snapshot, index)]


def test_frame_words_fit_in_front_of_a_rank_or_most():
    assert frame_words('30d') == ('LAST 30 DAYS', 'IN 30 DAYS')
    assert frame_words('year', {'year': 2026}) == ('IN 2026', 'IN 2026')
    assert frame_words('last_year', {'year': 2025})[1] == 'IN 2025'
    assert frame_words('last_week')[1] == 'LAST WEEK' and frame_words('all')[0] == 'LIFETIME'


def test_all_time_facts_start_with_the_top_discipline():
    facts = frame_facts(_snapshot(), 'all')
    assert [(f['label'], f['lines']) for f in facts] == [('TOP DISCIPLINE', ['CYCLING', '700 WORKOUTS'])]
    # With the log's all-time figures there are distinct counts too, after the top discipline.
    lifetime = {'workouts': 1234, 'classes': 900, 'instructors': 38}
    labels = [(f['label'], f['lines']) for f in frame_facts(_snapshot(time_frames={'all': lifetime}), 'all')]
    assert labels == [('TOP DISCIPLINE', ['CYCLING', '700 WORKOUTS']), ('LIFETIME', ['900 DIFFERENT', 'CLASSES']),
                      ('LIFETIME', ['38 DIFFERENT', 'INSTRUCTORS'])]


def test_a_frames_facts_in_order():
    facts = frame_facts(_full(), '30d')
    assert [(f['label'], f['lines']) for f in facts] == [
        ('LAST 30 DAYS', ['12 WORKOUTS', '340 MINUTES']),
        ('MOST IN 30 DAYS', ['STRENGTH', '6 WORKOUTS']),
        ('LAST 30 DAYS', ['ACTIVE DAYS', '10 OF 30']),
        ('LAST 30 DAYS', ['11 DIFFERENT', 'CLASSES']),
        ('LAST 30 DAYS', ['4 DIFFERENT', 'INSTRUCTORS'])]
    # A year of time is told in hours, and its favourite is the all-time one, so no MOST.
    year = frame_facts(_full(), 'year')
    assert (year[0]['label'], year[0]['lines']) == ('IN 2026', ['412 WORKOUTS', '164 HOURS'])
    assert [f['lines'][0] for f in year] == ['412 WORKOUTS', 'ACTIVE DAYS', '318 DIFFERENT', '31 DIFFERENT']


def test_a_frames_most_done_discipline_is_skipped_when_it_is_the_all_time_one():
    # Bike Bootcamp is labelled so in the totals but is a slug in the log; they still match.
    totals = {'Total Workouts': 50, 'Bike Bootcamp': 30, 'Cycling': 20}
    recent = dict(THIRTY, disciplines={'bike_bootcamp': 3})
    labels = [f['label'] for f in frame_facts(_snapshot(totals=totals, time_frames={'30d': recent}), '30d')]
    assert 'MOST IN 30 DAYS' not in labels
    # No all-time totals yet: the frame's favourite still shows.
    labels = [f['label'] for f in frame_facts(_snapshot(totals={}, time_frames={'30d': recent}), '30d')]
    assert 'MOST IN 30 DAYS' in labels


def test_thin_facts_are_skipped():
    # One workout: its count and time, but no "most", no active days, no distinct counts.
    one = {'workouts': 1, 'minutes': 20, 'disciplines': {'strength': 1}, 'instructor_counts': {'jess': 1},
           'instructors': 1, 'classes': 1, 'active_days': 1, 'days': 30}
    facts = frame_facts(_snapshot(time_frames={'30d': one}), '30d')
    assert [(f['label'], f['lines']) for f in facts] == [('LAST 30 DAYS', ['1 WORKOUT', '20 MINUTES'])]
    # Nothing in the frame, or no figures yet (the log isn't complete): no facts at all.
    assert frame_facts(_snapshot(time_frames={'30d': dict(one, workouts=0)}), '30d') == []
    assert frame_facts(_snapshot(), '30d') == [] and frame_facts({'totals': {}}, 'all') == []


def test_rankings_come_from_the_frames_own_classes():
    rankings = frame_rankings(_full(), '30d')
    assert [[d['label'] for d in r] for r in rankings] == [['TOP IN 30 DAYS', '2ND IN 30 DAYS', '3RD IN 30 DAYS']]
    assert rankings[0][2]['lines'] == ['CODY RIGSBY', '2 CLASSES']
    assert [d['label'] for d in frame_rankings(_full(), 'year')[0]][0] == 'TOP IN 2026'
    assert frame_rankings(_snapshot(), '30d') == []


def test_all_time_rankings_are_every_class_then_each_discipline_most_done_first():
    rankings = frame_rankings(_full(), 'all')
    assert [[d['label'] for d in r] for r in rankings] == [
        ['TOP INSTRUCTOR', '2ND INSTRUCTOR', '3RD INSTRUCTOR'],
        # Cycling's third has 3 classes, enough. Rowing has one class, so no ranking.
        ['TOP CYCLING', '2ND CYCLING', '3RD CYCLING'],
        ['TOP STRENGTH', '2ND STRENGTH', '3RD STRENGTH']]
    assert rankings[2][0]['lines'] == ['JESS SIMS', '150 CLASSES']


def test_a_ranking_with_a_thin_third_place_is_skipped():
    thin = dict(THIRTY, instructor_counts={'jess': 4, 'andy': 3, 'cody': MIN_RANKED_CLASSES - 1})
    assert frame_rankings(_snapshot(time_frames={'30d': thin}), '30d') == []
    # Two instructors isn't a top three either.
    assert frame_rankings(_snapshot(time_frames={'30d': dict(THIRTY, instructor_counts={'jess': 4, 'andy': 3})}),
                          '30d') == []


def test_all_time_ranking_keeps_any_count_as_before():
    snapshot = _snapshot(instructor_counts={'jess': 1})
    assert [[d['lines'] for d in r] for r in frame_rankings(snapshot, 'all')] == [[['JESS SIMS', '1 CLASS']]]
    assert frame_rankings({}, 'all') == []


def test_frames_without_anything_to_show_are_skipped_and_the_rest_keep_their_order():
    assert username_frames(_snapshot()) == ['all']
    assert username_frames(_full()) == ['all', '30d', 'year']
    assert username_frames({}) == []
    assert FRAME_ORDER[0] == 'all' and 'week' not in FRAME_ORDER
    everything = _snapshot(time_frames={key: YEAR for key in ('30d', '90d', 'year', 'last_year', 'last_week')})
    assert username_frames(everything) == ['all', '30d', 'year', '90d', 'last_year', 'last_week']


def test_a_frame_needs_a_headline_and_a_top_three_so_every_page_is_six_highlights():
    # Last week had workouts but only two instructors: no top three, so it doesn't take a turn.
    last_week = dict(YEAR, instructor_counts={'jess': 3, 'andy': 2}, instructors=2)
    snapshot = _snapshot(time_frames={'30d': THIRTY, 'last_week': last_week})
    assert frame_facts(snapshot, 'last_week') and not frame_rankings(snapshot, 'last_week')
    assert username_frames(snapshot) == ['all', '30d']
    assert all(len(username_details(snapshot, index)) == 6 for index in range(8))
    # A rider with no instructor data at all still gets the frames that have facts, on shorter pages.
    bare = {'totals': {'Total Workouts': 90, 'Cycling': 60}, 'weekly_progress': {},
            'time_frames': {'30d': dict(THIRTY, instructor_counts={}, instructors=0)}}
    assert username_frames(bare) == ['all', '30d']
    assert [len(username_details(bare, index)) for index in range(2)] == [3, 3]


def test_pass_zero_is_the_page_the_board_always_began_with():
    assert _labels(_snapshot(), 0) == ['TOTAL WORKOUTS', 'THIS WEEK', 'TOP DISCIPLINE',
                                       'TOP INSTRUCTOR', '2ND INSTRUCTOR', '3RD INSTRUCTOR']
    assert _labels(_full(), 0) == _labels(_snapshot(), 0)


def test_each_pass_is_one_frames_story_and_a_frame_coming_round_shows_its_next_fact():
    snapshot = _full()

    def page(headline, frame_words_or_ranks):
        ranks = frame_words_or_ranks if isinstance(frame_words_or_ranks, list) else [
            f'{rank} {frame_words_or_ranks}' for rank in ('TOP', '2ND', '3RD')]
        return ['TOTAL WORKOUTS', 'THIS WEEK', headline] + ranks

    assert [_labels(snapshot, index) for index in range(7)] == [
        page('TOP DISCIPLINE', ['TOP INSTRUCTOR', '2ND INSTRUCTOR', '3RD INSTRUCTOR']),
        page('LAST 30 DAYS', 'IN 30 DAYS'),
        page('IN 2026', 'IN 2026'),
        # All time again: the top discipline is its only fact, and the next ranking is cycling's.
        page('TOP DISCIPLINE', ['TOP CYCLING', '2ND CYCLING', '3RD CYCLING']),
        page('MOST IN 30 DAYS', 'IN 30 DAYS'),
        page('IN 2026', 'IN 2026'),
        page('TOP DISCIPLINE', ['TOP STRENGTH', '2ND STRENGTH', '3RD STRENGTH'])]
    # A frame's headline moves on each visit: its second one is the 30 days' most-done discipline.
    assert username_details(snapshot, 4)[2]['lines'] == ['STRENGTH', '6 WORKOUTS']
    assert username_details(snapshot, 5)[2]['lines'] == ['ACTIVE DAYS', '248 OF 312']


def test_without_a_frame_the_page_is_just_the_total_and_this_week():
    assert _labels({'totals': {'Total Workouts': 5}, 'weekly_progress': {}}, 3) == ['TOTAL WORKOUTS', 'THIS WEEK']


def test_rotation_passes_its_pass_index_to_the_name_page():
    dashboard = Mock()
    dashboard.pending_discipline_milestones.return_value = []
    display = {'rotation': ['username'], 'screen_durations': {'username': 1}, 'duration': 1,
               'overview_duration': 1, 'last_workout_duration': 1, 'color': 'white'}
    snapshot = _full(me={'username': 'Rider'}, summaries=[], status='ready')
    page = build_rotation_pages(snapshot, dashboard, display, 'Rider', 64, pass_index=2)[0]
    assert [d['label'] for d in page[1]['details']][2:] == ['IN 2026', 'TOP IN 2026', '2ND IN 2026', '3RD IN 2026']
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
    big = {'workouts': 1234, 'minutes': 99999, 'disciplines': {'tread_bootcamp': 30, 'walking_outdoor': 1},
           'instructor_counts': {'adrian': 999, 'andy': 888, 'cody': 777}, 'instructors': 1234, 'classes': 9999,
           'active_days': 365, 'days': 366, 'year': 2026}
    snapshot = _snapshot(time_frames={key: big for key in ('all', '30d', '90d', 'year', 'last_year', 'last_week')},
                         discipline_instructor_counts=by_discipline)
    details = []
    for key in FRAME_ORDER:
        details += frame_facts(snapshot, key) + [d for ranking in frame_rankings(snapshot, key) for d in ranking]
    labels = {d['label'] for d in details}
    # Every frame's longest labels are there.
    assert {'MOST IN 90 DAYS', 'LAST 90 DAYS', 'MOST LAST WEEK', 'IN 2026', 'LIFETIME', '3RD IN 90 DAYS'} <= labels
    assert len(details) > 60
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
