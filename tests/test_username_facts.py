"""The name page's varied highlights: time frames over the workout log (peloton.activity), the facts
each frame has enough data for, and which frame and fact each pass shows."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.username import UsernameScreen
from peloton.activity import (MIN_RANK_BLOCKS, SUBJECT_DISCIPLINES, SUBJECT_INSTRUCTORS, block_rank, frame_bounds,
                              frame_stats, period_stats)
from peloton.username_facts import (COOLDOWN_PASSES, FRAME_ORDER, KINDS, MAX_COMPARE_BONUS, MIN_RANKED_CLASSES,
                                    MIN_STREAK_WEEKS, RANK_FIRST_BONUS, RECENT_RECORD_BONUS, _comparison_fact,
                                    _since_fact,
                                    fact_score, frame_facts, frame_rankings, frame_subjects, frame_words,
                                    record_name_facts, scored_facts, shown_keys, username_details)
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


def test_log_derives_time_frames_only_once_complete():
    log = WorkoutLog('unused')
    log.merge([_w('a', NOW - timedelta(days=1)), _w('b', NOW - timedelta(days=2), discipline='cycling',
                                                   instructor='cody')])
    partial = log.derived(tzname=ZONE, now=NOW)
    assert partial['time_frames'] == {}
    log.backfill['complete'] = True
    full = log.derived(tzname=ZONE, now=NOW)
    assert set(full['time_frames']) == set(frame_bounds(ZONE, NOW))
    assert full['time_frames']['30d']['workouts'] == 2
    # The log keeps each class's ID, so distinct classes survive the trip through the log's rows.
    assert full['time_frames']['30d']['classes'] == 2
    assert full['time_frames']['30d']['disciplines'] == {'strength': 1, 'cycling': 1}
    assert set(full['time_frames']['30d']['by_discipline']) == {'strength', 'cycling'}


# measures and bests (step 3)

def _row(identity, when, **extra):
    return dict(_w(identity, when), **extra)


def test_frame_stats_find_the_busiest_day_week_and_month_and_the_longest_workout():
    workouts = [_w('a', _local(2026, 10, 5), minutes=20), _w('b', _local(2026, 10, 5, 18), minutes=45),
                _w('c', _local(2026, 10, 6), minutes=20), _w('d', _local(2026, 10, 7), minutes=20),
                _w('e', _local(2026, 11, 3), minutes=30, discipline='cycling')]
    year = frame_stats(workouts, ZONE, NOW)['year']
    assert year['busiest_day'] == {'count': 2, 'date': '2026-10-05'}
    assert year['busiest_week'] == {'count': 4, 'date': '2026-10-05'}
    assert year['busiest_month'] == {'count': 4, 'date': '2026-10-01'}
    assert year['longest'] == {'minutes': 45, 'discipline': 'strength'}
    assert year['best_output'] is None and year['best_strive'] is None
    # A 30-day window is no place for a month; and with nothing in a frame every best is None.
    assert frame_stats(workouts, ZONE, NOW)['30d']['busiest_month'] is None
    assert frame_stats([], ZONE, NOW)['all']['busiest_day'] is None


def test_longest_output_and_strive_come_from_real_classes_not_free_workouts():
    free = _w('free', _local(2026, 10, 3), discipline='cycling', minutes=90)
    free['ride'].pop('id')
    free.update(total_work=999000, effort_zones={'total_effort_points': 500})
    real = _w('real', _local(2026, 10, 2), discipline='cycling', minutes=30)
    real.update(total_work=200000, effort_zones={'total_effort_points': 100})
    log = WorkoutLog('unused')
    log.merge([free, real])
    log.backfill['complete'] = True
    year = log.derived(tzname=ZONE, now=NOW)['time_frames']['year']
    assert year['longest']['minutes'] == 30 and year['best_output']['kj'] == 200 and year['best_strive']['points'] == 100
    # They still count as workouts: the busiest day is about activity, not classes.
    assert year['workouts'] == 2
    log.workouts.pop(next(i for i, r in log.workouts.items() if r['ride_id'] is not None))
    only_free = log.derived(tzname=ZONE, now=NOW)['time_frames']['year']
    assert only_free['longest'] is None and only_free['best_output'] is None and only_free['best_strive'] is None


def test_a_windows_cut_off_week_is_not_counted_as_a_week():
    # 30 days back from Sunday 8 Nov is Saturday 10 Oct: the week of Mon 5 Oct starts before the window.
    workouts = [_w('a0', _local(2026, 10, 10)), _w('a1', _local(2026, 10, 11)), _w('a2', _local(2026, 10, 12)),
                _w('b', _local(2026, 10, 7))]
    stats = frame_stats(workouts, ZONE, NOW)
    assert stats['30d']['busiest_week'] == {'count': 1, 'date': '2026-10-12'}
    assert stats['year']['busiest_week'] == {'count': 3, 'date': '2026-10-05'}


def test_highest_output_is_a_bike_figure_and_best_strive_comes_through_the_log():
    log = WorkoutLog('unused')
    ride = _w('r', _local(2026, 10, 1), discipline='cycling', minutes=30)
    ride.update(total_work=289900, effort_zones={'total_effort_points': 212.4})
    row = _w('t', _local(2026, 10, 2), discipline='walking', minutes=60)
    row.update(total_work=900000, effort_zones={'total_effort_points': 300})
    log.merge([ride, row])
    log.backfill['complete'] = True
    year = log.derived(tzname=ZONE, now=NOW)['time_frames']['year']
    assert year['best_output'] == {'kj': 289.9, 'minutes': 30, 'discipline': 'cycling'}
    assert year['best_strive'] == {'points': 300, 'discipline': 'walking'}
    assert year['longest'] == {'minutes': 60, 'discipline': 'walking'}


def test_block_rank_compares_the_latest_block_with_equal_blocks_before_it():
    zone = ZoneInfo(ZONE)
    today = NOW.astimezone(zone).date()

    def rows(per_block):
        stamps = []
        for block, count in enumerate(per_block):
            for _ in range(count):
                stamps.append((datetime(today.year, today.month, today.day, 12, tzinfo=zone) - timedelta(days=block * 30 + 1), None))
        return stamps

    assert block_rank(rows([5, 9, 4, 7, 3, 6]), 30, today, zone) == {'rank': 4, 'of': 6, 'best': 9}
    assert block_rank(rows([9, 5, 4, 7, 3, 6]), 30, today, zone)['rank'] == 1
    # Ties share the better rank, and an empty block in between still counts as a block.
    assert block_rank(rows([5, 5, 0, 5, 1, 2]), 30, today, zone)['rank'] == 1
    # Too little history to call a rank.
    assert block_rank(rows([5] * (MIN_RANK_BLOCKS - 1)), 30, today, zone) is None
    assert block_rank([], 30, today, zone) is None


def test_only_the_30_and_90_day_frames_have_a_rank():
    workouts = [_w(f'w{i}', NOW - timedelta(days=i * 7)) for i in range(120)]
    frames = frame_stats(workouts, ZONE, NOW)
    assert frames['30d']['rank']['of'] >= MIN_RANK_BLOCKS and frames['90d']['rank'] is not None
    assert 'rank' not in frames['year'] and 'rank' not in frames['all']


def test_frames_carry_the_workouts_of_the_same_stretch_before_them():
    # 30 days: 3 workouts in the last 30, 5 in the 30 before; 90 days: 1 in the 90 before. Year: this year up to 8 Nov
    # against last year up to 8 Nov (a workout on 20 Nov 2025 is after that point, so it isn't counted).
    workouts = ([_w(f'a{i}', NOW - timedelta(days=i + 1)) for i in range(3)]
                + [_w(f'b{i}', NOW - timedelta(days=31 + i), minutes=30) for i in range(5)]
                + [_w('old', NOW - timedelta(days=120)), _w('after', _local(2025, 11, 20))])
    frames = frame_stats(workouts, ZONE, NOW)
    assert frames['30d']['before'] == {'workouts': 5, 'minutes': 150}
    assert frames['90d']['before'] == {'workouts': 1, 'minutes': 20}
    assert frames['year']['before']['workouts'] == 0       # the 20 Nov 2025 workout is after 8 Nov
    assert all('before' not in frames[key] for key in ('week', 'last_week', 'last_year', 'all'))


def test_the_year_is_compared_with_last_year_up_to_the_same_date_and_time():
    workouts = [_w('in-range', _local(2025, 11, 8, 9)), _w('too-late', _local(2025, 11, 8, 15)),
                _w('next-day', _local(2025, 11, 9)), _w('early', _local(2025, 1, 1, 0)),
                _w('before-year', _local(2024, 12, 31, 23))]
    assert frame_stats(workouts, ZONE, NOW)['year']['before']['workouts'] == 2


def test_a_leap_day_compares_with_the_28th():
    leap = datetime(2028, 2, 29, 17, 0, tzinfo=timezone.utc)
    workouts = [_w('a', _local(2027, 2, 28, 9)), _w('b', _local(2027, 3, 1))]
    assert frame_stats(workouts, ZONE, leap)['year']['before']['workouts'] == 1


def test_a_comparison_window_starts_and_ends_on_local_midnight():
    # The 30 days before start on 10 Sep and end at the start of 10 Oct (the 30-day frame's first day).
    workouts = [_w('late', _local(2026, 9, 9, 23)), _w('first', _local(2026, 9, 10, 0)),
                _w('last', _local(2026, 10, 9, 23)), _w('in-frame', _local(2026, 10, 10, 0))]
    stats = frame_stats(workouts, ZONE, NOW)['30d']
    assert stats['before']['workouts'] == 2 and stats['workouts'] == 1


# This day a year ago: 812 workouts then, 1,067 now.
DAY_ONE_YEAR = {'years_ago': 1, 'minutes': 20, 'discipline': 'yoga', 'workouts_then': 812, 'workouts_now': 1067}


def _compared(now, before, key='30d', **extra):
    stats = dict(THIRTY, workouts=now, before={'workouts': before, 'minutes': 0}, **extra)
    if key == 'year':
        stats['year'] = 2026
    return [f for f in frame_facts(_snapshot(time_frames={key: stats}), key) if f['kind'] == 'comparison']


def test_a_comparison_names_the_frame_and_the_change():
    assert [(f['label'], f['lines']) for f in _compared(15, 9)] == [('LAST 30 DAYS', ['15 WORKOUTS', 'UP FROM 9'])]
    assert _compared(8, 12)[0]['lines'] == ['8 WORKOUTS', 'DOWN FROM 12']
    assert _compared(412, 380, 'year') == []                     # +8%: not a big change
    assert [(f['label'], f['lines']) for f in _compared(1700, 1380, 'year')] == [
        ('THIS YEAR', ['1,700 WORKOUTS', 'UP FROM 1,380'])]
    assert _compared(500, 380, 'year')[0]['lines'] == ['500 WORKOUTS', 'UP FROM 380']
    assert [(f['label'], f['lines']) for f in _compared(55, 25, '90d')] == [('LAST 90 DAYS', ['55 WORKOUTS', 'UP FROM 25'])]


def test_the_count_and_its_comparison_are_one_fact_so_a_frame_never_says_its_count_twice():
    # With a real change the comparison carries the count and there is no separate total...
    stats = dict(THIRTY, workouts=19, before={'workouts': 12, 'minutes': 0})
    facts = frame_facts(_snapshot(time_frames={'30d': stats}), '30d')
    assert [f['kind'] for f in facts if f['kind'] in ('total', 'comparison')] == ['comparison']
    assert facts[0]['lines'] == ['19 WORKOUTS', 'UP FROM 12']
    # ...and with none it is the plain count with the time, as before.
    plain = dict(THIRTY, before={'workouts': 12, 'minutes': 0})
    facts = frame_facts(_snapshot(time_frames={'30d': plain}), '30d')
    assert [f['kind'] for f in facts if f['kind'] in ('total', 'comparison')] == ['total']
    assert facts[0]['lines'] == ['12 WORKOUTS', '340 MINUTES']


def test_two_headlines_never_share_a_label(monkeypatch):
    # Regression: LAST 30 DAYS showed in both slots (the count and a unique-instructors fact, or the
    # count and its comparison) on a rider whose log had both.
    stats = dict(THIRTY, workouts=19, before={'workouts': 12, 'minutes': 0})
    snapshot = _snapshot(time_frames={'30d': stats})
    for index in range(8):
        labels = [d['label'] for d in username_details(snapshot, index)[1:3]]
        assert len(set(labels)) == len(labels), labels
    # The guard itself: a second fact with the first's label is passed over for the next best.
    clash = [(90, {'kind': 'total', 'label': 'LAST 30 DAYS', 'key': 'a', 'lines': ['1']}, None),
             (80, {'kind': 'instructors', 'label': 'LAST 30 DAYS', 'key': 'b', 'lines': ['2']}, None),
             (70, {'kind': 'since:yoga', 'label': 'LAST YOGA', 'key': 'c', 'lines': ['3']}, None)]
    monkeypatch.setattr('peloton.username_facts.scored_facts', lambda snap: clash)
    assert [d['key'] for d in username_details({})] == ['a', 'c']


def test_a_comparison_needs_enough_on_both_sides_and_a_real_change():
    assert _compared(12, 12) == [] and _compared(13, 12) == []   # no change
    assert _compared(12, 10) == []                               # +2: under MIN_COMPARE_DIFF
    assert _compared(20, 18) == []                               # +2 of 18: tiny
    assert _compared(9, 4) == [] and _compared(4, 9) == []       # a side under 5 workouts
    assert _compared(20, 9, 'last_year') == []                   # only 30 days, 90 days and the year compare
    stats = dict(THIRTY)
    assert all(f['kind'] != 'comparison' for f in frame_facts(_snapshot(time_frames={'30d': stats}), '30d'))


def _measured(**extra):
    stats = dict(THIRTY, rank={'rank': 3, 'of': 12, 'best': 20},
                 busiest_day={'count': 2, 'date': '2026-10-05'}, busiest_week={'count': 6, 'date': '2026-10-12'},
                 busiest_month={'count': 22, 'date': '2025-10-01'}, longest={'minutes': 90, 'discipline': 'cycling'},
                 best_output={'kj': 289.9, 'minutes': 30, 'discipline': 'cycling'},
                 best_strive={'points': 212.4, 'discipline': 'bike_bootcamp'})
    stats.update(extra)
    return stats


def test_measures_and_bests_say_what_they_are_and_when():
    facts = frame_facts(_snapshot(time_frames={'30d': _measured()}), '30d')
    shown = {(f['label'], tuple(f['lines'])) for f in facts}
    assert {('LAST 30 DAYS', ('3RD BEST EVER', '12 WORKOUTS')), ('BUSIEST DAY', ('2 WORKOUTS', 'OCT 5 2026')),
            ('BUSIEST WEEK', ('6 WORKOUTS', 'OF OCT 12 2026')), ('BUSIEST MONTH', ('22 WORKOUTS', 'OCT 2025')),
            ('LONGEST WORKOUT', ('90 MINUTES', 'CYCLING')), ('HIGHEST OUTPUT', ('290 KJ', '30 MIN CYCLING')),
            ('BEST STRIVE', ('212 POINTS', 'BIKE BOOTCAMP'))} <= shown
    first = frame_facts(_snapshot(time_frames={'30d': _measured(rank={'rank': 1, 'of': 12, 'best': 12})}), '30d')
    assert ('LAST 30 DAYS', ('BEST EVER', '12 WORKOUTS')) in {(f['label'], tuple(f['lines'])) for f in first}


def test_a_best_needs_enough_behind_it():
    def lines(**extra):
        return {tuple(f['lines']) for f in frame_facts(_snapshot(time_frames={'30d': _measured(**extra)}), '30d')}

    assert ('2 WORKOUTS', 'OCT 5 2026') in lines()
    # A single-workout day, a two-workout week and a rank of 6th are not worth saying.
    thin = lines(busiest_day={'count': 1, 'date': '2026-10-05'}, busiest_week={'count': 2, 'date': '2026-10-12'},
                 rank={'rank': 6, 'of': 12, 'best': 20})
    words = ' | '.join(' '.join(line) for line in thin)
    assert 'OCT 5 2026' not in words and 'OF OCT 12' not in words and 'BEST EVER' not in words
    # A frame with fewer than five workouts has no averages, share or bests at all.
    few = frame_facts(_snapshot(time_frames={'30d': _measured(workouts=4)}), '30d')
    assert all(f['lines'][0] != 'AVERAGE CLASS' and f['label'] not in ('BUSIEST DAY', 'LONGEST WORKOUT', 'HIGHEST OUTPUT')
               for f in few)
    # No average week for a frame shorter than four weeks, and no share under ten workouts.
    week = {tuple(f['lines'][:1]) for f in frame_facts(_snapshot(time_frames={'30d': _measured(days=14, workouts=9)}), '30d')}
    assert ('AVERAGE WEEK',) not in week and ('AVERAGE CLASS',) in week
    assert not any(line[1] == 'OF WORKOUTS' for line in lines(workouts=9))


def test_a_long_discipline_name_in_a_share_uses_its_last_word():
    stats = dict(THIRTY, workouts=20, disciplines={'tread_bootcamp': 12, 'cycling': 8})
    shares = [f['lines'][0] for f in frame_facts(_snapshot(time_frames={'30d': stats}), '30d') if f['lines'][1] == 'OF WORKOUTS']
    assert shares == ['60% BOOTCAMP']


def test_the_best_weekly_streak_is_an_all_time_fact():
    facts = frame_facts(_snapshot(streaks={'best_weekly': 74, 'current_weekly': 3}), 'all')
    assert facts[-1]['label'] == 'LIFETIME' and facts[-1]['lines'] == ['74 WEEK STREAK', 'YOUR BEST']
    for streaks in ({'best_weekly': MIN_STREAK_WEEKS - 1}, {}, None):
        assert all('STREAK' not in ' '.join(f['lines']) for f in frame_facts(_snapshot(streaks=streaks), 'all'))
    assert all('STREAK' not in ' '.join(f['lines']) for f in frame_facts(_snapshot(streaks={'best_weekly': 74}), '30d'))


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
# What frame_stats adds to a frame: the figures for its most-done disciplines and instructors.


def _subject(workouts, minutes, counts=None):
    return {'workouts': workouts, 'minutes': minutes, 'instructor_counts': counts or {}}


THIRTY = dict(THIRTY, by_discipline={
    'strength': _subject(6, 120, {'jess': 3, 'andy': 2, 'cody': 2}), 'cycling': _subject(4, 150, {'cody': 2, 'andy': 1}),
    'yoga': _subject(1, 20, {'robin': 1})},
    by_instructor={'jess': _subject(4, 90), 'andy': _subject(3, 70), 'cody': _subject(2, 50)})
LIFETIME = {'workouts': 1234, 'classes': 900, 'instructors': 38,
            'by_discipline': {slug: _subject(sum(counts.values()), 0, counts) for slug, counts in BY_DISCIPLINE.items()}}


def _snapshot(**extra):
    snapshot = {'totals': {'Total Workouts': 1234, 'Cycling': 700, 'Strength': 500},
                'weekly_progress': {'workouts': 3, 'minutes': 75},
                'instructor_counts': {'jess': 300, 'cody': 250, 'andy': 200, 'robin': 5},
                'instructor_names': NAMES}
    snapshot.update(extra)
    return snapshot


def _full(**extra):
    return _snapshot(time_frames={'30d': THIRTY, 'year': YEAR, 'all': LIFETIME}, **extra)


def _flat(**extra):
    """_full without per-discipline figures: no discipline headline, so the top threes are the general ones."""
    return _snapshot(time_frames={'30d': dict(THIRTY, by_discipline={}), 'year': YEAR}, **extra)


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
    # With the log's all-time figures there is the unique instructors count too (unique classes are no fact).
    lifetime = {'workouts': 1234, 'classes': 900, 'instructors': 38}
    labels = [(f['label'], f['lines']) for f in frame_facts(_snapshot(time_frames={'all': lifetime}), 'all')]
    assert labels == [('TOP DISCIPLINE', ['CYCLING', '700 WORKOUTS']), ('LIFETIME', ['38 UNIQUE', 'INSTRUCTORS'])]


def test_a_frames_facts_in_order():
    facts = frame_facts(_full(), '30d')
    assert [(f['label'], f['lines']) for f in facts] == [
        ('LAST 30 DAYS', ['12 WORKOUTS', '340 MINUTES']),
        ('MOST IN 30 DAYS', ['STRENGTH', '6 WORKOUTS']),
        ('LAST 30 DAYS', ['ACTIVE DAYS', '10 OF 30']),
        ('LAST 30 DAYS', ['4 UNIQUE', 'INSTRUCTORS']),
        ('LAST 30 DAYS', ['AVERAGE CLASS', '28 MINUTES']),
        ('LAST 30 DAYS', ['AVERAGE WEEK', '2.8 WORKOUTS']),
        ('LAST 30 DAYS', ['50% STRENGTH', 'OF WORKOUTS']),
        ('LAST 30 DAYS', ['JESS SIMS', '90 MINUTES']),
        ('LAST 30 DAYS', ['ANDY SPEER', '70 MINUTES']),
        ('LAST 30 DAYS', ['CODY RIGSBY', '50 MINUTES'])]
    # A year of time is told in hours, and its favourite is the all-time one, so no MOST.
    year = frame_facts(_full(), 'year')
    assert (year[0]['label'], year[0]['lines']) == ('IN 2026', ['412 WORKOUTS', '164 HOURS'])
    assert [f['lines'][0] for f in year] == ['412 WORKOUTS', 'ACTIVE DAYS', '31 UNIQUE',
                                             'AVERAGE CLASS', 'AVERAGE WEEK', '49% CYCLING']


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


def test_a_frames_general_ranking_is_every_class_and_a_discipline_is_a_subject():
    assert [[d['label'] for d in r] for r in frame_rankings(_full(), 'all')] == [
        ['TOP INSTRUCTOR', '2ND INSTRUCTOR', '3RD INSTRUCTOR']]
    pairs = frame_subjects(_full(), 'all')
    # Most-done first. Rowing has one workout, so it isn't a subject.
    assert [(h['label'], h['lines']) for h, _ in pairs] == [
        ('CYCLING', ['353 WORKOUTS', 'LIFETIME']), ('STRENGTH', ['310 WORKOUTS', 'LIFETIME'])]
    assert [[d['label'] for d in ranking] for _, ranking in pairs][1] == [
        'TOP STRENGTH', '2ND STRENGTH', '3RD STRENGTH']
    assert pairs[1][1][0]['lines'] == ['JESS SIMS', '150 CLASSES']
    assert pairs[1][1][0]['short_label'] == 'TOP STRENGTH'


def test_a_discipline_in_a_frame_is_a_subject_with_its_own_top_three():
    pairs = frame_subjects(_full(), '30d')
    # Strength has a whole top three of 2+ classes; cycling has two instructors, yoga one workout.
    assert [(h['label'], h['lines']) for h, _ in pairs] == [('STRENGTH', ['6 WORKOUTS', 'IN 30 DAYS'])]
    assert [(d['label'], d['lines']) for d in pairs[0][1]] == [
        ('TOP STRENGTH', ['JESS SIMS', '3 CLASSES']), ('2ND STRENGTH', ['ANDY SPEER', '2 CLASSES']),
        ('3RD STRENGTH', ['CODY RIGSBY', '2 CLASSES'])]
    assert frame_subjects(_snapshot(), '30d') == [] and frame_subjects(_full(), 'last_week') == []
    year = dict(YEAR, by_discipline={'bike_bootcamp': _subject(30, 900, {'jess': 9, 'andy': 8, 'cody': 7}),
                                     'tread_bootcamp': _subject(1, 9, {'jess': 1})})
    headline = frame_subjects(_snapshot(time_frames={'year': year}), 'year')[0][0]
    assert headline['lines'] == ['30 WORKOUTS', 'IN 2026']


def test_a_long_discipline_name_carries_its_last_word_as_a_short_label():
    found = {'walking_outdoor': _subject(5, 99, {'jess': 3, 'andy': 3, 'cody': 3})}
    headline = frame_subjects(_snapshot(time_frames={'30d': dict(THIRTY, by_discipline=found)}), '30d')[0][0]
    assert headline['label'] == 'WALKING OUTDOOR' and 'short_label' not in headline    # exactly 15
    found = {'running_outdoor_long': _subject(5, 99, {'jess': 3, 'andy': 3, 'cody': 3})}
    headline = frame_subjects(_snapshot(time_frames={'30d': dict(THIRTY, by_discipline=found)}), '30d')[0][0]
    assert headline['short_label'] == 'LONG'


def test_a_frames_most_seen_instructors_are_facts_with_the_time_spent_with_them():
    facts = frame_facts(_full(), '30d')
    assert [f['lines'] for f in facts[-3:]] == [
        ['JESS SIMS', '90 MINUTES'], ['ANDY SPEER', '70 MINUTES'], ['CODY RIGSBY', '50 MINUTES']]
    assert facts[-1]['label'] == 'LAST 30 DAYS'
    # An instructor seen once, or with no known name, isn't a fact.
    thin = dict(THIRTY, by_instructor={'jess': _subject(1, 20), 'ghost': _subject(9, 200)})
    assert frame_facts(_snapshot(time_frames={'30d': thin}), '30d')[-1]['lines'] != ['JESS SIMS', '20 MINUTES']
    assert all('GHOST' not in ' '.join(f['lines']) for f in frame_facts(_snapshot(time_frames={'30d': thin}), '30d'))
    long_time = dict(THIRTY, by_instructor={'jess': _subject(80, 3600)})
    assert frame_facts(_snapshot(time_frames={'30d': long_time}), '30d')[-1]['lines'] == ['JESS SIMS', '60 HOURS']


def test_a_discipline_headline_is_a_candidate_that_brings_its_own_top_three():
    found = {fact['key']: ranking for _, fact, ranking in scored_facts(_full())}
    assert [d['label'] for d in found['30d:subject:strength']] == ['TOP STRENGTH', '2ND STRENGTH', '3RD STRENGTH']
    # A general fact has no top three of its own.
    assert found['30d:total'] is None and found['all:top_discipline'] is None
    # A frame with a headline but no instructors still has its facts.
    assert [fact['key'] for _, fact, _ in scored_facts(_snapshot(time_frames={'30d': dict(THIRTY, instructor_counts={})}))
            if fact['key'].startswith('30d')]


def test_period_stats_filters_by_discipline_or_instructor():
    workouts = [_w('a', NOW - timedelta(days=1), instructor='jess', minutes=30),
                _w('b', NOW - timedelta(days=2), discipline='cycling', instructor='cody', minutes=45),
                _w('c', NOW - timedelta(days=3), discipline='cycling', instructor='jess', minutes=20)]
    group = _w('d', NOW - timedelta(days=4), discipline='yoga', instructor=None)
    group['ride']['instructor'] = {'id': 'duo', 'name': 'Duo', 'is_instructor_group': True,
                                   'individual_instructor_ids': ['jess', 'andy']}
    workouts.append(group)
    cycling = period_stats(workouts, None, None, ZONE, NOW, discipline='cycling')
    assert (cycling['workouts'], cycling['minutes'], cycling['instructor_counts']) == (2, 65, {'cody': 1, 'jess': 1})
    assert period_stats(workouts, None, None, ZONE, NOW, instructor='jess')['workouts'] == 3   # a group counts
    assert period_stats(workouts, None, None, ZONE, NOW, discipline='cycling', instructor='jess')['workouts'] == 1
    assert period_stats(workouts, None, None, ZONE, NOW, discipline='rowing')['workouts'] == 0


def test_frame_stats_split_each_frame_by_discipline_and_instructor_in_one_pass():
    workouts = [_w(str(n), NOW - timedelta(days=n), discipline='strength' if n % 2 else 'cycling',
                   instructor='jess' if n < 5 else 'andy') for n in range(1, 9)]
    workouts.append(_w('old', NOW - timedelta(days=60), discipline='yoga', instructor='cody'))
    stats = frame_stats(workouts, ZONE, NOW)
    month, ninety = stats['30d'], stats['90d']
    assert set(month['by_discipline']) == {'strength', 'cycling'} and 'yoga' in ninety['by_discipline']
    # Each split matches period_stats with the same filter.
    start = frame_bounds(ZONE, NOW)['30d'][0]
    assert month['by_discipline']['strength'] == period_stats(workouts, start, None, ZONE, NOW, discipline='strength')
    assert month['by_instructor']['jess'] == period_stats(workouts, start, None, ZONE, NOW, instructor='jess')
    # Only the most-seen: the 4th instructor and the 6th discipline are left out.
    many = [_w(f'x{n}', NOW - timedelta(days=1), discipline=f'd{n}', instructor=None) for n in range(7)]
    assert len(frame_stats(many, ZONE, NOW)['30d']['by_discipline']) == SUBJECT_DISCIPLINES
    assert len(frame_stats(workouts, ZONE, NOW)['all']['by_instructor']) <= SUBJECT_INSTRUCTORS
    assert frame_stats([], ZONE, NOW)['all']['by_discipline'] == {}


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


def test_frames_without_anything_to_show_have_no_candidates():
    assert {fact['key'].split(':')[0] for _, fact, _ in scored_facts(_snapshot())} == {'all'}
    assert {fact['key'].split(':')[0] for _, fact, _ in scored_facts(_full())} == {'all', '30d', 'year'}
    assert scored_facts({}) == []
    assert FRAME_ORDER[0] == 'all' and 'week' not in FRAME_ORDER


def test_a_page_is_six_highlights_and_a_thin_rider_gets_a_shorter_one():
    last_week = dict(YEAR, instructor_counts={'jess': 3, 'andy': 2}, instructors=2)
    snapshot = _snapshot(time_frames={'30d': THIRTY, 'last_week': last_week})
    assert frame_facts(snapshot, 'last_week') and not frame_rankings(snapshot, 'last_week')
    assert all(len(username_details(snapshot, index)) == 6 for index in range(8))
    # No instructor data: the total and the two best facts, no top three.
    bare = {'totals': {'Total Workouts': 90, 'Cycling': 60}, 'weekly_progress': {},
            'time_frames': {'30d': dict(THIRTY, instructor_counts={}, instructors=0)}}
    assert [len(username_details(bare, index)) for index in range(2)] == [3, 3]


def test_every_kind_has_a_group_and_a_score_and_every_fact_a_known_kind():
    snapshot = _full(streaks={'best_weekly': 74}, events={'today': '2026-11-08', 'anniversary': 6,
                     'on_this_day': [DAY_ONE_YEAR]})
    for _, fact, _ in scored_facts(snapshot):
        assert fact['kind'].split(':')[0] in KINDS, fact['kind']
    assert all(group and score > 0 for group, score in KINDS.values())
    keys = [fact['key'] for _, fact, _ in scored_facts(snapshot)]
    assert len(keys) == len(set(keys)) and 'events:on_this_day' in keys and 'all:streak' in keys


def test_the_page_is_the_total_two_headlines_of_different_groups_and_a_top_three():
    details = username_details(_full(), 0)
    assert [d['label'] for d in details][0] == 'TOTAL WORKOUTS' and len(details) == 6
    assert 'THIS WEEK' not in [d['label'] for d in details]
    groups = [KINDS[d['kind'].split(':')[0]][0] for d in details[1:3]]
    assert len(set(groups)) == 2
    # With only the overview's totals, the one fact there is, then the all-time top three.
    assert _labels(_snapshot(), 0) == ['TOTAL WORKOUTS', 'TOP DISCIPLINE',
                                       'TOP INSTRUCTOR', '2ND INSTRUCTOR', '3RD INSTRUCTOR']


def test_the_best_scoring_facts_show_first():
    snapshot = _full(events={'today': '2026-11-08', 'on_this_day': [DAY_ONE_YEAR]})
    scores = scored_facts(snapshot)
    assert [score for score, _, _ in scores] == sorted((score for score, _, _ in scores), reverse=True)
    details = username_details(snapshot, 0)
    assert details[1]['key'] == scores[0][1]['key'] == 'events:on_this_day'
    # The second is the best of another group.
    assert details[2]['key'] == next(f['key'] for _, f, _ in scores if KINDS[f['kind'].split(':')[0]][0] != 'event')


def test_a_discipline_headline_brings_its_own_top_three_else_the_general_ones_take_turns():
    snapshot = _full()
    assert not any(ranking is None for _, fact, ranking in scored_facts(snapshot) if fact['kind'].startswith('subject'))
    rotation = [[d['label'] for d in username_details(_flat(), index)[3:]] for index in range(3)]
    assert rotation == [['TOP INSTRUCTOR', '2ND INSTRUCTOR', '3RD INSTRUCTOR'], ['TOP IN 30 DAYS', '2ND IN 30 DAYS', '3RD IN 30 DAYS'],
                        ['TOP IN 2026', '2ND IN 2026', '3RD IN 2026']]
    # Put a discipline first by cooling everything else down: its page ends with that discipline's top three.
    cooled = {fact['key']: 5 for _, fact, ranking in scored_facts(snapshot) if ranking is None}
    details = username_details(dict(snapshot, name_facts_passes=5, name_facts_shown=cooled), 0)
    assert details[1]['kind'].startswith('subject:') or details[2]['kind'].startswith('subject:')
    name = (details[1] if details[1]['kind'].startswith('subject:') else details[2])['label']
    assert [d['label'] for d in details[3:]] == [f'{rank} {name}' for rank in ('TOP', '2ND', '3RD')]


def test_a_fact_just_shown_loses_to_fresh_ones_and_recovers_over_the_cooldown():
    fact = {'kind': 'rank', 'key': '30d:rank'}
    base = fact_score(fact)
    assert fact_score(fact, passes=7, shown={'30d:rank': 7}) < base - 90
    mid = fact_score(fact, passes=7 + COOLDOWN_PASSES // 2, shown={'30d:rank': 7})
    assert base - 60 < mid < base - 40
    assert fact_score(fact, passes=7 + COOLDOWN_PASSES, shown={'30d:rank': 7}) == base
    # A kind shown from another frame cools it too, less.
    kind_cooled = fact_score(fact, passes=3, shown={'kind:rank': 3})
    assert base - 50 < kind_cooled < base - 10


def test_a_lifetime_discipline_count_is_not_a_headline_but_its_instructors_still_get_a_page():
    snapshot = _full()
    keys = [fact['key'] for _, fact, _ in scored_facts(snapshot)]
    assert not any(key.startswith('all:subject:') for key in keys) and '30d:subject:strength' in keys
    # The all-time discipline top threes are in the turns, right after the overall one.
    pages = [[d['label'] for d in username_details(dict(_flat(), time_frames={'all': LIFETIME}), index)[3:]]
             for index in range(4)]
    assert pages[0] == ['TOP INSTRUCTOR', '2ND INSTRUCTOR', '3RD INSTRUCTOR']
    assert pages[1] == ['TOP CYCLING', '2ND CYCLING', '3RD CYCLING']      # the most-done discipline first
    assert pages[2] == ['TOP STRENGTH', '2ND STRENGTH', '3RD STRENGTH']
    # ...and never with a lifetime-count headline in front.
    assert all(d['label'] not in ('STRENGTH', 'CYCLING') or d['lines'][1] != 'LIFETIME'
               for index in range(6) for d in username_details(snapshot, index))


def test_the_pages_rotate_through_facts_as_the_cooldown_works():
    snapshot = _full(events={'today': '2026-11-08', 'on_this_day': [DAY_ONE_YEAR]})
    snapshot['name_facts_passes'], snapshot['name_facts_shown'] = 0, {}
    shown = []
    for _ in range(6):
        details = username_details(snapshot, 0)
        shown.append(tuple(d['key'] for d in details[1:3]))
        snapshot['name_facts_passes'], snapshot['name_facts_shown'] = record_name_facts(
            snapshot['name_facts_passes'], snapshot['name_facts_shown'], shown_keys(details))
    assert len(set(shown)) == 6 and shown[0][0] == 'events:on_this_day'
    # ...and none of the six repeats a fact, nor the same kind back to back.
    flat = [key for pair in shown for key in pair]
    assert len(flat) == len(set(flat))


def test_recording_a_showing_counts_the_page_stamps_the_facts_and_forgets_the_old():
    passes, shown = record_name_facts(0, {}, ['a', 'kind:x'])
    assert (passes, shown) == (1, {'a': 1, 'kind:x': 1})
    passes, shown = record_name_facts(passes, shown, ['b'])
    assert (passes, shown) == (2, {'a': 1, 'kind:x': 1, 'b': 2})
    passes, shown = record_name_facts(COOLDOWN_PASSES + 1, {'old': 1, 'a': 5}, [])
    assert shown == {'a': 5}
    assert shown_keys([{'key': '30d:rank', 'kind': 'rank'}, {'label': 'x'}]) == ['30d:rank', 'kind:rank']


def test_a_recent_best_scores_higher_than_an_old_one():
    fact = {'kind': 'busiest_day', 'key': 'all:busiest_day', 'when': '2026-11-05'}
    old = dict(fact, when='2025-01-05')
    today = date(2026, 11, 8)
    assert fact_score(fact, today) - fact_score(old, today) == RECENT_RECORD_BONUS
    assert fact_score(fact) == fact_score(old)      # no date for today: no bonus
    assert fact_score({'kind': 'rank', 'key': 'k', 'bonus': 15}) == KINDS['rank'][1] + 15


def test_only_the_all_time_and_year_bests_get_the_recent_record_bonus():
    today = date(2026, 11, 8)
    scores = {frame: fact_score({'kind': 'busiest_day', 'key': f'{frame}:busiest_day', 'when': '2026-11-05'}, today)
              for frame in ('all', 'year', '30d', '90d', 'last_year')}
    base = KINDS['busiest_day'][1]
    assert scores == {'all': base + RECENT_RECORD_BONUS, 'year': base + RECENT_RECORD_BONUS,
                      '30d': base, '90d': base, 'last_year': base}


def test_facts_that_read_the_same_in_several_frames_are_one_candidate():
    day = {'count': 3, 'date': '2026-11-08'}
    frames = {key: dict(YEAR, busiest_day=day) for key in ('30d', '90d', 'year')}
    snapshot = _snapshot(time_frames=frames, events={'today': '2026-11-08'})
    days = [(score, fact['key']) for score, fact, _ in scored_facts(snapshot) if fact['kind'] == 'busiest_day']
    # One survives: the year's, which has the recent-record bonus; the 30- and 90-day copies are gone.
    assert days == [(KINDS['busiest_day'][1] + RECENT_RECORD_BONUS, 'year:busiest_day')]
    # Resting the survivor doesn't bring a copy back in its place.
    cooled = dict(snapshot, name_facts_passes=1, name_facts_shown={'year:busiest_day': 1})
    assert [fact['key'] for _, fact, _ in scored_facts(cooled) if fact['kind'] == 'busiest_day'] == ['year:busiest_day']
    # Different figures are different facts: each frame keeps its own.
    other = dict(frames, **{'30d': dict(YEAR, busiest_day={'count': 2, 'date': '2026-11-01'})})
    keys = {fact['key'] for _, fact, _ in scored_facts(_snapshot(time_frames=other)) if fact['kind'] == 'busiest_day'}
    assert keys == {'30d:busiest_day', 'year:busiest_day'}


def test_a_best_ever_rank_and_a_big_change_carry_a_bonus():
    ranked = [f for f in frame_facts(_snapshot(time_frames={'30d': dict(THIRTY, rank={'rank': 1, 'of': 9, 'best': 12})}), '30d')
              if f['kind'] == 'rank']
    assert ranked[0]['bonus'] == RANK_FIRST_BONUS
    second = [f for f in frame_facts(_snapshot(time_frames={'30d': dict(THIRTY, rank={'rank': 2, 'of': 9, 'best': 12})}), '30d')
              if f['kind'] == 'rank']
    assert second[0]['bonus'] == 0
    big = _comparison_fact('30d', dict(THIRTY, workouts=20, before={'workouts': 10, 'minutes': 100}))
    small = _comparison_fact('30d', dict(THIRTY, workouts=13, before={'workouts': 10, 'minutes': 100}))
    assert big['bonus'] > small['bonus'] > 0 and big['bonus'] <= MAX_COMPARE_BONUS


def test_the_name_page_turns_its_top_threes_by_the_saved_counter_not_the_loops_pass_index():
    snapshot = dict(_flat(), name_facts_passes=1)
    assert _labels(snapshot, 0) == _labels(snapshot, 7)
    assert _labels(dict(snapshot, name_facts_passes=2), 0) != _labels(snapshot, 0)
    # Without a counter (a preview) the pass index turns them.
    bare = _flat()
    assert [d['label'] for d in username_details(bare, 0)[3:]] != [d['label'] for d in username_details(bare, 1)[3:]]
    # A damaged counter is as good as none.
    assert _labels(dict(bare, name_facts_passes='x', name_facts_shown={'a': 1}), 1) == _labels(bare, 1)


def test_without_a_fact_the_page_is_just_the_total():
    assert _labels({'totals': {'Total Workouts': 5}, 'weekly_progress': {}}, 3) == ['TOTAL WORKOUTS']


def test_rotation_builds_the_name_page_and_tells_the_loop_which_facts_it_showed():
    dashboard = Mock()
    dashboard.pending_discipline_milestones.return_value = []
    display = {'rotation': ['username'], 'screen_durations': {'username': 1}, 'duration': 1,
               'overview_duration': 1, 'last_workout_duration': 1, 'color': 'white'}
    snapshot = _full(me={'username': 'Rider'}, summaries=[], status='ready')
    page = build_rotation_pages(snapshot, dashboard, display, 'Rider', 64, pass_index=2)[0]
    assert [d['label'] for d in page[1]['details']] == [d['label'] for d in username_details(snapshot, 2)]
    assert page[1]['fact_keys'] == shown_keys(page[1]['details']) and len(page[1]['fact_keys']) == 4
    # Six highlights every pass, so the page is as long as before.
    assert page[2] == pytest.approx(30.0)


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
           'active_days': 365, 'days': 366, 'year': 2026,
           'by_discipline': {slug: _subject(1234, 99999, counts) for slug, counts in by_discipline.items()},
           'by_instructor': {'adrian': _subject(999, 99999), 'andy': _subject(888, 5)},
           'rank': {'rank': 5, 'of': 99, 'best': 99}, 'busiest_day': {'count': 12, 'date': '2026-09-28'},
           'busiest_week': {'count': 25, 'date': '2026-09-28'}, 'busiest_month': {'count': 120, 'date': '2026-09-01'},
           'longest': {'minutes': 120, 'discipline': 'walking_outdoor'},
           'best_output': {'kj': 1234.5, 'minutes': 120, 'discipline': 'cycling'},
           'best_strive': {'points': 1234.5, 'discipline': 'tread_bootcamp'},
           'before': {'workouts': 4321, 'minutes': 1}}
    snapshot = _snapshot(time_frames={key: big for key in ('all', '30d', '90d', 'year', 'last_year', 'last_week')},
                         streaks={'best_weekly': 999})
    details = []
    for key in FRAME_ORDER:
        details += frame_facts(snapshot, key) + [d for ranking in frame_rankings(snapshot, key) for d in ranking]
        for headline, ranking in frame_subjects(snapshot, key):
            details += [headline] + ranking
    labels = {d['label'] for d in details}
    # Every frame's longest labels are there.
    assert {'MOST IN 90 DAYS', 'LAST 90 DAYS', 'MOST LAST WEEK', 'IN 2026', 'LIFETIME', '3RD IN 90 DAYS'} <= labels
    assert {'BIKE BOOTCAMP', 'WALKING OUTDOOR', '3RD BOOTCAMP'} <= {d.get('short_label', d['label']) for d in details} | labels
    assert len(details) > 100
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


# events (anniversary, this day, comebacks, firsts, since, last class with)

def _event_log():
    """Sunday 2026-11-08 (New York). Strength: a run of workouts, then a 70-day gap, then one 3 days
    ago (a comeback). Yoga: five old workouts, the last 40 days ago (since). Cycling with Cody: five,
    the last 50 days ago. Walking: first done 5 days ago. Two workouts on 8 November 2025."""
    rows = [_w(f'a{n}', _local(2025, 1, 1 + n), 'strength', 'jess') for n in range(5)]
    rows.append(_w('s-gap', _local(2026, 8, 1), 'strength', 'jess'))
    rows.append(_w('s-back', _local(2026, 11, 5), 'strength', 'jess'))
    rows += [_w(f'y{n}', _local(2026, 9, 20 - n), 'yoga', 'andy') for n in range(5)]
    rows += [_w(f'c{n}', _local(2026, 9, 19 - n), 'cycling', 'cody') for n in range(5)]
    rows.append(_w('walk', _local(2026, 11, 3), 'walking', 'robin'))
    rows += [_w('d-short', _local(2025, 11, 8, 7), 'cycling', 'robin', minutes=20),
             _w('d-long', _local(2025, 11, 8, 18), 'yoga', 'andy', minutes=45)]
    rows.append(_w('future', NOW + timedelta(days=2), 'running', 'robin'))
    rows.append(_w('unfinished', _local(2026, 11, 6), 'meditation', 'robin', status='IN_PROGRESS'))
    return rows


MEMBER_SINCE = int(_local(2020, 11, 8, 9).timestamp())


def test_event_stats_are_dates_in_the_display_timezone():
    from peloton.activity import event_stats
    events = event_stats(_event_log(), ZONE, NOW, MEMBER_SINCE)
    assert events['today'] == '2026-11-08' and events['anniversary'] == 6
    # The longest workout of the nearest earlier year with one: 45 minutes of yoga, not the cycling.
    # The log's workout count at the end of that day (the 7 workouts up to 8 Nov 2025: 5 + the 2 that day) and now.
    assert events['on_this_day'] == [{'years_ago': 1, 'minutes': 45, 'discipline': 'yoga',
                                      'workouts_then': 7, 'workouts_now': 20}]
    assert events['first_ever'] == '2025-01-01'
    assert events['disciplines']['strength'] == {'workouts': 7, 'first': '2025-01-01', 'last': '2026-11-05',
                                                 'before_last': '2026-08-01'}
    assert events['disciplines']['walking'] == {'workouts': 1, 'first': '2026-11-03', 'last': '2026-11-03',
                                                'before_last': None}
    # A workout still going and one in the future are no event; the instructors' last class is a date.
    assert 'meditation' not in events['disciplines'] and 'running' not in events['disciplines']
    assert events['instructors']['cody'] == {'workouts': 5, 'last': '2026-09-19'}


def test_event_stats_the_day_is_the_display_timezones():
    from peloton.activity import event_stats
    # 03:30 UTC on 9 November is still the 8th in New York: today's date, and the anniversary.
    late = datetime(2026, 11, 9, 3, 30, tzinfo=timezone.utc)
    events = event_stats([_w('x', _local(2025, 11, 8, 22))], ZONE, late, MEMBER_SINCE)
    assert events['today'] == '2026-11-08' and events['anniversary'] == 6
    assert [row['years_ago'] for row in events['on_this_day']] == [1]


@pytest.mark.parametrize('created, now, years', [
    (MEMBER_SINCE, NOW, 6),
    (MEMBER_SINCE, NOW + timedelta(days=1), None),          # the day after
    (int(NOW.timestamp()), NOW, None),                      # joined today: no years yet
    (None, NOW, None), ('junk', NOW, None)])
def test_anniversary_is_only_on_the_day_and_after_a_full_year(created, now, years):
    from peloton.activity import anniversary
    assert anniversary(created, ZONE, now) == years


def test_event_stats_with_no_workouts():
    from peloton.activity import event_stats
    events = event_stats([], ZONE, NOW)
    assert events['first_ever'] is None and events['disciplines'] == {} and events['on_this_day'] == []
    assert events['anniversary'] is None


def _events_snapshot(**extra):
    from peloton.activity import event_stats
    return _snapshot(events=event_stats(_event_log(), ZONE, NOW, MEMBER_SINCE), **extra)


def test_event_facts_in_order():
    facts = frame_facts(_events_snapshot(), 'events')
    assert [(f['label'], f['lines']) for f in facts] == [
        ('A YEAR AGO', ['YOU HAD 7', 'NOW 20']),
        ('WELCOME BACK', ['STRENGTH', '1ST IN 96 DAYS']),
        ('NEW DISCIPLINE', ['WALKING', 'FIRST TIME']),
        ('LAST RIDE', ['50 DAYS AGO']),
        ('LAST YOGA', ['49 DAYS AGO']),
        ('LAST CLASS WITH', ['ANDY SPEER', '49 DAYS AGO']),
        ('LAST CLASS WITH', ['CODY RIGSBY', '50 DAYS AGO'])]


def test_event_facts_leave_out_what_is_thin_or_recent():
    snapshot = _events_snapshot()
    snapshot['events'] = dict(snapshot['events'], anniversary=None, on_this_day=[])
    # Yoga came back 8 days ago after a gap under 60 days, cycling was done 20 days ago, and so on.
    disciplines = {
        'yoga': {'workouts': 9, 'first': '2025-01-01', 'last': '2026-11-01', 'before_last': '2026-10-01'},
        'cycling': {'workouts': 9, 'first': '2025-01-01', 'last': '2026-10-20', 'before_last': '2026-10-19'},
        'rowing': {'workouts': 4, 'first': '2025-01-01', 'last': '2026-01-01', 'before_last': '2025-12-01'},
        'walking': {'workouts': 9, 'first': '2026-11-06', 'last': '2026-11-06', 'before_last': '2026-11-05'},
        'running': {'workouts': 9, 'first': '2026-11-06', 'last': '2026-11-06', 'before_last': None}}
    # A first needs history behind it: this rider's first workout was on 2026-11-05.
    snapshot['events'].update(disciplines=disciplines, first_ever='2026-11-05',
                              instructors={'jess': {'workouts': 4, 'last': '2025-01-01'},
                                           'cody': {'workouts': 9, 'last': '2026-11-01'},
                                           'nobody': {'workouts': 9, 'last': '2025-01-01'}})
    facts = frame_facts(snapshot, 'events')
    # Only cycling (since 19 days) qualifies: rowing has under 5 workouts, jess too, cody is recent, and
    # 'nobody' has no name.
    assert [(f['label'], f['lines']) for f in facts] == [('LAST RIDE', ['19 DAYS AGO'])]


def test_event_facts_are_capped_and_long_names_get_three_lines():
    snapshot = _events_snapshot()
    many = {slug: {'workouts': 9 - index, 'first': '2025-01-01', 'last': '2026-06-01', 'before_last': '2026-05-30'}
            for index, slug in enumerate(('bike_bootcamp', 'tread_bootcamp', 'stretching', 'yoga'))}
    snapshot['events'].update(disciplines=many, on_this_day=[
        dict(DAY_ONE_YEAR, years_ago=2, workouts_then=95, workouts_now=1234)])
    snapshot['events']['instructors'] = {who: {'workouts': 9, 'last': '2026-01-01'} for who in NAMES}
    facts = frame_facts(snapshot, 'events')
    assert (facts[0]['label'], facts[0]['lines']) == ('2 YEARS AGO', ['YOU HAD 95', 'NOW 1,234'])
    since = [f for f in facts if f['kind'].startswith('since:')]
    # At most two, and a bootcamp's `LAST <noun>` is too wide: LAST over the full name over the days.
    assert [(f['label'], f['lines']) for f in since] == [
        ('LAST', ['BIKE BOOTCAMP', '160 DAYS AGO']), ('LAST', ['TREAD BOOTCAMP', '160 DAYS AGO'])]
    assert len([f for f in facts if f['label'] == 'LAST CLASS WITH']) == 2


@pytest.mark.parametrize('slug, label, lines', [
    ('cycling', 'LAST RIDE', ['52 DAYS AGO']), ('running', 'LAST RUN', ['52 DAYS AGO']),
    ('walking', 'LAST WALK', ['52 DAYS AGO']), ('rowing', 'LAST ROW', ['52 DAYS AGO']),
    ('hiking', 'LAST HIKE', ['52 DAYS AGO']), ('stretching', 'LAST STRETCH', ['52 DAYS AGO']),
    ('strength', 'LAST STRENGTH', ['52 DAYS AGO']),
    ('yoga', 'LAST YOGA', ['52 DAYS AGO']),                   # never LAST YOGA CLASS
    ('meditation', 'LAST MEDITATION', ['52 DAYS AGO']), ('cardio', 'LAST CARDIO', ['52 DAYS AGO']),
    ('tread_bootcamp', 'LAST', ['TREAD BOOTCAMP', '52 DAYS AGO']),
    ('bike_bootcamp', 'LAST', ['BIKE BOOTCAMP', '52 DAYS AGO']),
    ('row_bootcamp', 'LAST', ['ROW BOOTCAMP', '52 DAYS AGO']),
    ('running_outdoor', 'LAST', ['OUTDOOR RUN', '52 DAYS AGO']),
    ('walking_outdoor', 'LAST', ['OUTDOOR WALK', '52 DAYS AGO']),
    ('pilates', 'LAST PILATES', ['52 DAYS AGO'])])          # a discipline it has no noun for keeps its name
def test_since_names_the_workout_as_a_noun_and_falls_back_to_three_lines(slug, label, lines):
    fact = _since_fact(slug, 52)
    assert (fact['label'], fact['lines'], fact['kind']) == (label, lines, f'since:{slug}')


def test_since_counts_days_singular_and_with_thousands():
    assert _since_fact('cycling', 1)['lines'] == ['1 DAY AGO']
    assert _since_fact('cycling', 999)['lines'] == ['999 DAYS AGO']
    assert _since_fact('cycling', 1200)['lines'] == ['1,200 DAYS AGO']


def test_a_comeback_always_names_the_whole_discipline():
    def comeback(slug, last, before_last, workouts=9):
        snapshot = _events_snapshot()
        snapshot['events'].update(disciplines={slug: {'workouts': workouts, 'first': '2020-01-01', 'last': last,
                                                      'before_last': before_last}}, first_ever='2020-01-01')
        return [(f['label'], f['lines']) for f in frame_facts(snapshot, 'events') if f['kind'].startswith('comeback')]
    assert comeback('stretching', '2026-11-06', '2026-01-23') == [('WELCOME BACK', ['STRETCHING', '1ST IN 287 DAYS'])]
    for slug, name in (('row_bootcamp', 'ROW BOOTCAMP'), ('tread_bootcamp', 'TREAD BOOTCAMP'),
                       ('bike_bootcamp', 'BIKE BOOTCAMP'), ('walking_outdoor', 'WALKING OUTDOOR')):
        assert comeback(slug, '2026-11-06', '2026-01-23')[0][1][0] == name
    # Over 999 days it is told in years; at exactly MIN_COMEBACK_DAYS it still fires, a day less doesn't.
    assert comeback('yoga', '2026-11-06', '2022-11-06')[0][1] == ['YOGA', '1ST IN 4 YEARS']
    assert comeback('yoga', '2026-11-06', '2026-09-07')[0][1] == ['YOGA', '1ST IN 60 DAYS']
    assert comeback('yoga', '2026-11-06', '2026-09-08') == []
    assert comeback('yoga', '2026-11-06', '2026-01-23', workouts=4) == []


def test_last_class_with_counts_days_since():
    snapshot = _events_snapshot()
    snapshot['events']['instructors'] = {'jess': {'workouts': 9, 'last': '2026-10-08'},        # 31 days
                                         'andy': {'workouts': 8, 'last': '2022-11-08'},        # 4 years
                                         'cody': {'workouts': 7, 'last': '2026-10-10'}}        # 29: too recent
    facts = [f for f in frame_facts(snapshot, 'events') if f['label'] == 'LAST CLASS WITH']
    assert [f['lines'] for f in facts] == [['JESS SIMS', '31 DAYS AGO'], ['ANDY SPEER', '1,461 DAYS AGO']]


def test_on_this_day_is_the_workout_totals_then_and_now():
    def day(**found):
        snapshot = _snapshot(events={'today': '2026-11-08', 'on_this_day': [dict(DAY_ONE_YEAR, **found)]})
        return [(f['label'], f['lines']) for f in frame_facts(snapshot, 'events')]
    assert day() == [('A YEAR AGO', ['YOU HAD 812', 'NOW 1,067'])]
    assert day(years_ago=2) == [('2 YEARS AGO', ['YOU HAD 812', 'NOW 1,067'])]
    assert day(years_ago=12, workouts_then=1, workouts_now=99999) == [('12 YEARS AGO', ['YOU HAD 1', 'NOW 99,999'])]
    # Totals missing (an older cache) or nonsense: no fact, never half a sentence.
    for bad in ({'workouts_then': None}, {'workouts_now': None}, {'workouts_then': '812'}, {'workouts_now': True},
                {'workouts_then': 0}, {'workouts_then': 900, 'workouts_now': 899}, {'years_ago': 0}, {'years_ago': None}):
        assert day(**bad) == [], bad
    old = {'years_ago': 1, 'minutes': 20, 'discipline': 'yoga'}
    assert frame_facts(_snapshot(events={'today': '2026-11-08', 'on_this_day': [old]}), 'events') == []


def test_on_this_day_skips_an_entry_it_cannot_say_for_the_next():
    snapshot = _snapshot(events={'today': '2026-11-08', 'on_this_day': [
        {'years_ago': 1, 'workouts_then': None, 'workouts_now': 9}, dict(DAY_ONE_YEAR, years_ago=2)]})
    assert [f['label'] for f in frame_facts(snapshot, 'events')] == ['2 YEARS AGO']


def test_the_anniversary_is_the_first_headline_of_every_page_all_day():
    snapshot = _full(events={'anniversary': 6})
    for index in range(6):
        details = username_details(snapshot, index)
        assert [d['label'] for d in details].count('ANNIVERSARY') == 1 and len(details) == 6
        assert details[1]['lines'] == ['6 YEARS', 'ON PELOTON'] and details[2]['kind'] != 'anniversary'
    # With the overview only, the anniversary still shows, beside the one other fact.
    assert [d['label'] for d in username_details(_snapshot(events={'anniversary': 6}))][1] == 'ANNIVERSARY'
    # With no other fact at all it is the only headline, and its pin is never recorded as shown.
    bare = {'totals': {'Total Workouts': 5}, 'events': {'anniversary': 6}}
    assert [d['label'] for d in username_details(bare)] == ['TOTAL WORKOUTS', 'ANNIVERSARY']
    assert shown_keys(username_details(bare)) == []
    assert 'ANNIVERSARY' not in [d['label'] for d in username_details(_full(events={}))]


def test_events_without_a_date_for_today_have_no_facts():
    snapshot = _snapshot(events={'anniversary': 3})
    assert frame_facts(snapshot, 'events') == []
    assert frame_facts(_snapshot(), 'events') == [] and frame_facts(_snapshot(events={}), 'events') == []


def test_events_are_candidates_only_when_there_is_something_to_say():
    assert not any(fact['key'].startswith('events:') for _, fact, _ in scored_facts(_full()))
    snapshot = _flat(events={'today': '2026-11-08', 'on_this_day': [DAY_ONE_YEAR]})
    assert 'events:on_this_day' in [fact['key'] for _, fact, _ in scored_facts(snapshot)]
    # The event has no top three of its own, so the page takes a general one.
    details = username_details(snapshot, 0)
    assert details[1]['label'] == 'A YEAR AGO' and details[3]['label'] == 'TOP INSTRUCTOR'
    assert frame_subjects(snapshot, 'events') == []


def test_an_empty_events_section_changes_nothing():
    assert [_labels(_full(), n) for n in range(6)] == [_labels(_full(events={}), n) for n in range(6)]


def test_event_figures_reach_the_snapshot_through_the_log(tmp_path):
    log = WorkoutLog(tmp_path / 'log.json')
    log.merge(_event_log())
    log.backfill['complete'] = True
    derived = log.derived(tzname=ZONE, now=NOW, member_since=MEMBER_SINCE)
    assert derived['events']['anniversary'] == 6 and derived['events']['disciplines']['yoga']['workouts'] == 6
    # A log still filling has no history figures, but the anniversary needs none.
    log.backfill['complete'] = False
    partial = log.derived(tzname=ZONE, now=NOW, member_since=MEMBER_SINCE)
    assert partial['events'] == {'anniversary': 6}
    assert log.derived(tzname=ZONE, now=NOW + timedelta(days=1), member_since=MEMBER_SINCE)['events'] == {}


@pytest.mark.parametrize('height', (64, 32))
def test_event_labels_and_lines_fit(height):
    initialize_fonts(height)
    small, value = loaded_fonts['stats'], loaded_fonts['info']
    snapshot = _events_snapshot()
    slugs = ('tread_bootcamp', 'bike_bootcamp', 'row_bootcamp', 'running_outdoor', 'walking_outdoor', 'stretching',
             'meditation', 'strength', 'cardio', 'yoga', 'cycling', 'rowing', 'hiking')
    # Every discipline both "since" (999 days is the widest count) and back after 3 years (the widest comeback).
    snapshot['events'].update(
        on_this_day=[dict(DAY_ONE_YEAR, years_ago=10, workouts_then=99999, workouts_now=123456)], anniversary=10,
        disciplines={slug: {'workouts': 99, 'first': '2020-01-01', 'last': '2024-02-12', 'before_last': '2020-01-01'}
                     for slug in slugs},
        instructors={'long': {'workouts': 9, 'last': '2000-01-01'}})
    snapshot['instructor_names'] = dict(NAMES, long='Adrian Williams')
    facts = frame_facts(snapshot, 'events')
    assert {'on_this_day', 'last_class_with'} <= {f['kind'].split(':')[0] for f in facts}
    # The comebacks and "since" facts are capped, so check every discipline through its own builders too.
    facts += [_since_fact(slug, days) for slug in slugs for days in (1, 52, 999)]
    for slug in slugs:
        later = dict(snapshot['events']['disciplines'][slug], last='2026-11-06', before_last='2023-11-06')
        one = dict(snapshot, events=dict(snapshot['events'], disciplines={slug: later}))
        facts += [f for f in frame_facts(one, 'events') if f['kind'].startswith('comeback')]
    assert len(facts) > 40
    for fact in facts:
        # A label and every line holds 15 characters of the 4 px stats font (60 px).
        assert len(fact['label']) <= 15 and all(len(line) <= 15 for line in fact['lines']), fact
        assert get_text_width(small, fact['label']) <= 60, fact['label']
        for line in fact['lines']:
            assert get_text_width(value, line) <= 60, line
        assert len(fact['lines']) <= 2


def test_the_widest_name_page_facts_draw_on_both_heights():
    # Tread Bootcamp is the widest name; draw each of its facts and check nothing runs off the panel.
    for height in (64, 32):
        initialize_fonts(height)
        for fact in (_since_fact('tread_bootcamp', 999),
                     {'label': 'WELCOME BACK', 'lines': ['TREAD BOOTCAMP', '1ST IN 999 DAYS']}):
            matrix, screen = ImageMatrix(height=height), UsernameScreen()
            state = {'username': 'Rider', 'details': [fact]}
            screen.on_enter(matrix, state)
            screen.update(1.0)
            screen.render(matrix, state)
            image = matrix.image
            assert image.getbbox() is not None
            # Nothing in the outermost columns: the text sits inside the panel margins.
            edge = image.crop((0, 12, 2, height)).getbbox(), image.crop((image.width - 2, 12, image.width, height)).getbbox()
            assert edge == (None, None), (height, fact['label'])
