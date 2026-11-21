"""Pins the exact output of discipline totals, workout summaries and screen-time retirement,
including odd or missing fields from Peloton's API (code health 2f-E)."""
import pytest

import peloton.stats.summaries as summaries
from peloton.stats.summaries import summarize_workout
from peloton.stats.totals import extract_discipline_totals


# --- extract_discipline_totals ---------------------------------------------------------------

@pytest.mark.parametrize('overview, expected', [
    ({}, {}),
    # list entries: non-dict entries skipped; label keys tried in order; count keys tried in order
    ({'workouts': ['junk', None, 3,
                   {'discipline_display_name': 'Cycling', 'workout_count': 5},
                   {'discipline_name': 'Running', 'total_workouts': 7},
                   {'name': 'Walking', 'count': 2},
                   {'title': 'Rowing', 'workouts': 4},
                   {'discipline': 'Yoga', 'workout_count': None, 'count': 9},
                   {'discipline': 'Strength', 'workout_count': {'a': 1}, 'count': [1], 'workouts': 6},
                   {'discipline': 'Cardio'},
                   {'workout_count': 3}]},
     {'Cycling': 5, 'Running': 7, 'Walking': 2, 'Rowing': 4, 'Yoga': 9, 'Strength': 6}),
    # dict of dicts: the entry's own count, then nested lists under known fields
    ({'discipline_totals': {'cycling': {'workout_count': 12, 'items': [{'name': 'Running', 'count': 3}]},
                            'Rowing': {'disciplines': [{'name': 'Yoga', 'count': 1}],
                                       'workouts': [{'name': 'Walking', 'count': 8}],
                                       'workout_counts': [{'name': 'Cardio', 'count': 2}]},
                            'Stretching': {'other': 1}}},
     {'Cycling': 12, 'Running': 3, 'Yoga': 1, 'Walking': 8, 'Cardio': 2}),
    # dict value that is a list is visited; scalars are added; bad scalars dropped
    ({'workout_counts_by_discipline': {'Bike': [{'name': 'Cycling', 'count': 4}], 'Running': '20', 'Bad': -1,
                                       'Fraction': 2.5, 'Flag': True, 'Nope': 'abc', 'Inf': float('inf'),
                                       'None': None, 'Cardio': 3.0, '': 5}},
     {'Cycling': 4, 'Running': 20, 'Cardio': 3}),
    # a non-string label is ignored; duplicates keep the first; the range keys are walked in order
    ({'workouts': [{'name': 7, 'count': 2}, {'name': 'Yoga', 'count': 1}],
      'discipline_counts': {'yoga': 50, 'Strength': 2}, 'workouts_per_discipline': 'not a container'},
     {'Yoga': 1, 'Strength': 2}),
])
def test_extract_discipline_totals_pinned(overview, expected):
    assert extract_discipline_totals(overview) == expected


# --- summarize_workout -----------------------------------------------------------------------

def summary_of(monkeypatch, metrics, workout=None, perf=None, detail=None):
    monkeypatch.setattr(summaries, 'extract_summary_from_perf', lambda *_args: metrics)
    return summarize_workout(workout or {'fitness_discipline': 'cycling'}, perf, detail)


def pick(result, *keys):
    return {key: result[key] for key in keys}


PACE_KEYS = ('duration_min', 'distance', 'distance_unit', 'avg_speed', 'avg_speed_unit', 'avg_pace',
             'avg_pace_unit', 'row_split_sec_per_500m')


@pytest.mark.parametrize('metrics, perf, expected', [
    # the pace arrives in seconds: converted to minutes, the unit renamed
    ({'avg_pace': 600, 'avg_pace__unit': 'sec/mi'}, {},
     {'duration_min': None, 'distance': None, 'distance_unit': None, 'avg_speed': None, 'avg_speed_unit': None,
      'avg_pace': 10.0, 'avg_pace_unit': 'min/mi', 'row_split_sec_per_500m': None}),
    ({'avg_pace': 330, 'avg_pace__unit': 's/km'}, {},
     {'duration_min': None, 'distance': None, 'distance_unit': None, 'avg_speed': None, 'avg_speed_unit': None,
      'avg_pace': 5.5, 'avg_pace_unit': 'min/km', 'row_split_sec_per_500m': None}),
    ({'avg_pace': 5, 'avg_pace__unit': 'min/mi'}, {},
     {'duration_min': None, 'distance': None, 'distance_unit': None, 'avg_speed': None, 'avg_speed_unit': None,
      'avg_pace': 5, 'avg_pace_unit': 'min/mi', 'row_split_sec_per_500m': None}),
    # distance and duration give a missing speed and pace; miles are imperial
    ({'distance': 3, 'distance__unit': 'mi'}, {'duration': 1800},
     {'duration_min': 30, 'distance': 3, 'distance_unit': 'mi', 'avg_speed': 6.0, 'avg_speed_unit': 'mph',
      'avg_pace': 10.0, 'avg_pace_unit': 'min/mi', 'row_split_sec_per_500m': 1800 / (3 * 1609.344 / 500)}),
    # metric distances in metres and km; a recorded speed or pace is kept
    ({'distance': 5000, 'distance__unit': 'm', 'avg_speed': 11, 'avg_speed__unit': 'km/h'}, {'duration': 1800},
     {'duration_min': 30, 'distance': 5000, 'distance_unit': 'm', 'avg_speed': 11, 'avg_speed_unit': 'km/h',
      'avg_pace': 6.0, 'avg_pace_unit': 'min/km', 'row_split_sec_per_500m': 180.0}),
    ({'distance': 5, 'distance__unit': 'km', 'avg_pace': 6, 'avg_pace__unit': 'min/km'}, {'duration': 1800},
     {'duration_min': 30, 'distance': 5, 'distance_unit': 'km', 'avg_speed': 10.0, 'avg_speed_unit': 'km/h',
      'avg_pace': 6, 'avg_pace_unit': 'min/km', 'row_split_sec_per_500m': 180.0}),
    # an unknown distance unit gives no metres; zero distance gives no derived figures
    ({'distance': 5, 'distance__unit': 'furlong'}, {'duration': 1800},
     {'duration_min': 30, 'distance': 5, 'distance_unit': 'furlong', 'avg_speed': None, 'avg_speed_unit': None,
      'avg_pace': None, 'avg_pace_unit': None, 'row_split_sec_per_500m': None}),
    ({'distance': 0, 'distance__unit': 'km'}, {'duration': 1800},
     {'duration_min': 30, 'distance': 0, 'distance_unit': 'km', 'avg_speed': None, 'avg_speed_unit': None,
      'avg_pace': None, 'avg_pace_unit': None, 'row_split_sec_per_500m': None}),
    # no duration: nothing derived
    ({'distance': 5, 'distance__unit': 'km'}, {},
     {'duration_min': None, 'distance': 5, 'distance_unit': 'km', 'avg_speed': None, 'avg_speed_unit': None,
      'avg_pace': None, 'avg_pace_unit': None, 'row_split_sec_per_500m': None}),
    # rowing split: minutes per 500 m converted, seconds kept, any other unit dropped (then derived)
    ({'avg_split_pace': 2.5, 'avg_split_pace__unit': 'min/500m'}, {},
     {'duration_min': None, 'distance': None, 'distance_unit': None, 'avg_speed': None, 'avg_speed_unit': None,
      'avg_pace': None, 'avg_pace_unit': None, 'row_split_sec_per_500m': 150.0}),
    ({'avg_split_pace': 140, 'avg_split_pace__unit': 'sec/500m'}, {},
     {'duration_min': None, 'distance': None, 'distance_unit': None, 'avg_speed': None, 'avg_speed_unit': None,
      'avg_pace': None, 'avg_pace_unit': None, 'row_split_sec_per_500m': 140}),
    ({'avg_split_pace': 140, 'avg_split_pace__unit': 'min/mi', 'distance': 1000, 'distance__unit': 'm'},
     {'duration': 400},
     {'duration_min': 7, 'distance': 1000, 'distance_unit': 'm', 'avg_speed': 9.0, 'avg_speed_unit': 'km/h',
      'avg_pace': 400 / 60 / 1, 'avg_pace_unit': 'min/km', 'row_split_sec_per_500m': 200.0}),
])
def test_summarize_workout_speed_pace_split_pinned(monkeypatch, metrics, perf, expected):
    got = pick(summary_of(monkeypatch, metrics, perf=perf), *PACE_KEYS)
    assert got == pytest.approx(expected)


OUTPUT_KEYS = ('total_output_kj', 'total_work_kj', 'avg_output_w')


@pytest.mark.parametrize('metrics, workout, expected', [
    ({'total_output': 1500, 'total_output__unit': 'j'}, {}, {'total_output_kj': 1.5, 'total_work_kj': None,
                                                              'avg_output_w': None}),
    ({'total_output': 200, 'total_output__unit': 'kj'}, {'total_work': 250400},
     {'total_output_kj': 200, 'total_work_kj': 250.4, 'avg_output_w': None}),
    ({'total_output': 200}, {}, {'total_output_kj': 200, 'total_work_kj': None, 'avg_output_w': None}),
    # an unknown unit drops the figure; the raw work fills in
    ({'total_output': 200, 'total_output__unit': 'btu'}, {'total_work': 300000},
     {'total_output_kj': 300.0, 'total_work_kj': 300.0, 'avg_output_w': None}),
    ({'total_output': 200, 'total_output__unit': 'btu'}, {},
     {'total_output_kj': None, 'total_work_kj': None, 'avg_output_w': None}),
    # zero work: output 0 but no work kJ
    ({}, {'total_work': 0}, {'total_output_kj': 0.0, 'total_work_kj': None, 'avg_output_w': None}),
    ({'avg_output': 1.5, 'avg_output__unit': 'kw'}, {}, {'total_output_kj': None, 'total_work_kj': None,
                                                          'avg_output_w': 1500.0}),
    ({'avg_output': 150, 'avg_output__unit': 'w'}, {}, {'total_output_kj': None, 'total_work_kj': None,
                                                         'avg_output_w': 150}),
    ({'avg_output': 150}, {}, {'total_output_kj': None, 'total_work_kj': None, 'avg_output_w': 150}),
    ({'avg_output': 150, 'avg_output__unit': 'hp'}, {}, {'total_output_kj': None, 'total_work_kj': None,
                                                          'avg_output_w': None}),
])
def test_summarize_workout_output_pinned(monkeypatch, metrics, workout, expected):
    workout = {'fitness_discipline': 'cycling', **workout}
    assert pick(summary_of(monkeypatch, metrics, workout=workout), *OUTPUT_KEYS) == expected


IDENTITY_KEYS = ('workout_id', 'date_time', 'tz', 'workout_at', 'title', 'instructor', 'duration_min',
                 'is_pr', 'is_output_pr', 'is_splits_pr', 'strive_score', 'discipline')


@pytest.mark.parametrize('workout, perf, expected', [
    ({}, None, {'workout_id': None, 'date_time': '', 'tz': '', 'workout_at': None, 'title': 'Workout',
                'instructor': '', 'duration_min': None, 'is_pr': False, 'is_output_pr': False,
                'is_splits_pr': False, 'strive_score': None, 'discipline': ''}),
    ({'id': 'w1', 'fitness_discipline': 'running_outdoor', 'name': 'Name', 'timezone': 'America/New_York',
      'created_at': 1700000000, 'duration': 2700,
      'ride': {'instructor': {'id': 'i', 'display_name': 'Pat'}}},
     {'effort_zones': {'total_effort_points': 40}},
     {'workout_id': 'w1', 'date_time': 'Nov 14, 2023 05:13 PM EST', 'tz': 'America/New_York',
      'workout_at': 1700000000.0, 'title': 'Name', 'instructor': 'Pat', 'duration_min': 45, 'is_pr': False,
      'is_output_pr': False, 'is_splits_pr': False, 'strive_score': 40.0, 'discipline': 'Outdoor Run'}),
    ({'fitness_discipline': 'walking_outdoor', 'title': 'T', 'ride': {'title': 'Ride', 'duration': 600,
                                                                      'instructor': {'name': 'Sam'}}},
     {'duration': 0, 'effort_zones': {}},
     {'workout_id': None, 'date_time': '', 'tz': '', 'workout_at': None, 'title': 'Ride', 'instructor': '',
      'duration_min': 10, 'is_pr': False, 'is_output_pr': False, 'is_splits_pr': False, 'strive_score': None,
      'discipline': 'Outdoor Walk'}),
    ({'fitness_discipline': 'tread_bootcamp', 'title': 'T', 'duration': -5, 'ride': {'duration': 0},
      'is_total_work_personal_record': True},
     {'duration': 'x'},
     {'workout_id': None, 'date_time': '', 'tz': '', 'workout_at': None, 'title': 'T', 'instructor': '',
      'duration_min': None, 'is_pr': True, 'is_output_pr': True, 'is_splits_pr': False, 'strive_score': None,
      'discipline': 'Tread Bootcamp'}),
])
def test_summarize_workout_identity_pinned(workout, perf, expected):
    assert pick(summarize_workout(workout, perf), *IDENTITY_KEYS) == expected


def test_summarize_workout_passthrough_keys(monkeypatch):
    metrics = {'calories': 0, 'calories__unit': 'kcal', 'max_speed': 12, 'max_speed__unit': 'mph',
               'avg_incline': 2, 'max_incline': 5, 'elevation': 9, 'elevation__unit': 'ft',
               'avg_cadence': 80, 'avg_resistance': 40, 'avg_stroke_rate': 22, 'hr_avg': 140, 'hr_max': 170}
    result = summary_of(monkeypatch, metrics)
    for key in ('calories', 'max_speed', 'avg_incline', 'max_incline', 'elevation', 'avg_cadence',
                'avg_resistance', 'avg_stroke_rate', 'hr_avg', 'hr_max'):
        assert result[key] == metrics.get(key)
        assert result[key + '_unit'] == metrics.get(key + '__unit')
