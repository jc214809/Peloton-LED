import os
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from peloton.timestamps import parse_timestamp, workout_date
from peloton.selection import latest_workout, last_active_day, select_latest, normalize_discipline
from peloton.summaries import summarize_workout
from peloton.totals import extract_discipline_totals, lifetime_overview_pages, total_workout_count
from peloton.api import PelotonClient
from peloton.config import load_config, load_dotenv
from api.pr import is_pr_workout
from display.ui.last_workout_screen import _fmt_pace, _fmt_split, _middle_stats
from models import get_model_for_discipline
from models.core import GeneralWorkout


@pytest.mark.parametrize('value', [1773496800, 1773496800000, '1773496800', '2026-03-14T14:00:00Z', '2026-03-14T10:00:00-04:00'])
def test_timestamp_formats(value):
    assert parse_timestamp(value) == datetime(2026, 3, 14, 14, tzinfo=timezone.utc)


@pytest.mark.parametrize('value', [None, '', 'bad', '2026-03-14', True, float('nan'), float('inf'), 1e99])
def test_invalid_or_date_only_is_not_an_instant(value):
    assert parse_timestamp(value) is None


def test_local_day_and_dst():
    rows = [{'id': 1, 'start_time': '2026-03-09T03:30:00Z'},
            {'id': 2, 'start_time': '2026-03-09T04:30:00Z'},
            {'id': 3, 'start_time': '2026-03-09T06:00:00Z', 'status': 'IN_PROGRESS'}]
    assert [w['id'] for w in last_active_day(rows, 'America/New_York')] == [2]
    assert str(workout_date(rows[0], 'America/New_York')) == '2026-03-08'
    assert parse_timestamp('2026-03-08T03:30:00', 'America/New_York').hour == 7
    assert parse_timestamp('2026-11-01T02:30:00', 'America/New_York').hour == 7


def test_date_only_groups_without_inventing_order():
    row = {'start_date': '2026-03-14'}
    assert last_active_day([row]) == [row]
    assert latest_workout([row]) is None


def test_latest_completed_deduplicated_and_discipline_alias():
    rows = [{'id': 1, 'start_time': 1773496800, 'fitness_discipline': 'cycling'},
            {'id': 2, 'start_time': 1773496801000, 'fitness_discipline': 'running'},
            {'id': 3, 'start_time': 1773496810, 'status': 'IN_PROGRESS'}]
    assert latest_workout(rows)['id'] == 2
    assert len(last_active_day(rows + rows)) == 2
    assert select_latest(rows, 'bike')['id'] == 1
    assert select_latest(rows, 'rowing')['id'] == 2


def test_last_active_day_is_chronological_not_latest_first():
    # Taken in this order: tread bootcamp, core, strength. The dashboard
    # should show them in the order they were actually taken.
    rows = [{'id': 1, 'start_time': 1773496800, 'fitness_discipline': 'tread_bootcamp'},
            {'id': 2, 'start_time': 1773497800, 'fitness_discipline': 'stretching'},
            {'id': 3, 'start_time': 1773498800, 'fitness_discipline': 'strength'}]
    assert [w['id'] for w in last_active_day(rows)] == [1, 2, 3]


def metric_perf(distance=5, units='km', duration=1800):
    return {'duration': duration, 'summaries': [{'slug': 'distance', 'value': distance, 'display_unit': units}]}


def test_metric_pace_and_duration_fallback():
    summary = summarize_workout({'fitness_discipline': 'walking', 'ride': {'duration': 9999}}, metric_perf())
    assert summary['duration_min'] == 30
    assert summary['avg_speed'] == 10
    assert summary['avg_speed_unit'] == 'km/h'
    assert summary['avg_pace'] == 6
    assert summary['avg_pace_unit'] == 'min/km'
    assert _middle_stats(summary)[0][1] == '6:00/km'


def test_imperial_pace_and_rounding():
    summary = summarize_workout({'fitness_discipline': 'running'}, metric_perf(3, 'mi'))
    assert summary['avg_pace'] == 10
    assert summary['avg_pace_unit'] == 'min/mi'
    assert _fmt_pace(9.9999) == '10:00'
    assert _fmt_split(119.9) == '2:00'


def test_row_split_independent_of_existing_speed_and_pace():
    perf = metric_perf(4000, 'm', 1200)
    perf['average_summaries'] = [{'slug': 'avg_speed', 'value': 12, 'display_unit': 'km/h'},
                                 {'slug': 'avg_pace', 'value': 5, 'display_unit': 'min/km'}]
    perf['metrics'] = [{'slug': 'output', 'average_value': 100, 'display_unit': 'w'}]
    summary = summarize_workout({'fitness_discipline': 'rowing'}, perf)
    assert summary['row_split_sec_per_500m'] == 150
    assert summary['avg_output_w'] == 100


def test_null_missing_zero_and_output_units():
    summary = summarize_workout({'fitness_discipline': 'cycling', 'total_work': 250000}, {'effort_zones': None})
    assert summary['total_output_kj'] == 250
    assert summary['calories'] is None
    assert summary['strive_score'] is None
    perf = metric_perf(0, 'mi')
    perf['summaries'] += [{'slug': 'calories', 'value': 0}, {'slug': 'total_output', 'value': 1000, 'display_unit': 'j'}]
    summary = summarize_workout({'fitness_discipline': 'cycling'}, perf)
    assert summary['calories'] == 0
    assert summary['total_output_kj'] == 1
    assert summary['avg_pace'] is None


def test_explicit_metrics_take_precedence():
    perf = metric_perf()
    perf['average_summaries'] = [{'slug': 'avg_speed', 'value': 9, 'display_unit': 'km/h'}]
    perf['metrics'] = [{'slug': 'speed', 'average_value': 11, 'display_unit': 'km/h'}]
    assert summarize_workout({'fitness_discipline': 'running'}, perf)['avg_speed'] == 9


@pytest.mark.parametrize('fields, output, splits', [
    ({'is_total_work_personal_record': True}, True, False),
    ({'is_splits_personal_record': True}, False, True),
    ({'achievement_templates': [{'slug': 'output_pr'}]}, True, False),
    ({'achievement_templates': [None], 'is_total_work_personal_record': 'false'}, False, False),
])
def test_consistent_pr_classification(fields, output, splits):
    summary = summarize_workout(fields)
    assert summary['is_output_pr'] == output
    assert summary['is_splits_pr'] == splits
    assert summary['is_pr'] == is_pr_workout(fields) == (output or splits)


def test_totals_preserve_zero_and_deduplicate():
    overview = {'workout_counts': [{'name': 'Cycling', 'count': 0}, {'name': 'cycling', 'count': 100}],
                'discipline_counts': {'bike': 10, 'Running': '20', 'Bad': -1, 'Fraction': 2.5}}
    assert extract_discipline_totals(overview) == {'Cycling': 0, 'Running': 20}


def test_lifetime_totals_preserve_each_discipline_and_exact_count():
    totals = {'Cycling': 100, 'Bike Bootcamp': 5, 'Running': 20, 'Walking': 10,
              'Outdoor Run': 3, 'Strength': 7, 'Pilates': 2, 'Yoga': 4,
              'Stretching': 6, 'Boxing': 1, 'Total Workouts': 158}
    items = [item for page in lifetime_overview_pages(totals) for item in page]
    counts = {item['label']: item['count'] for item in items}
    assert counts == {key: value for key, value in totals.items() if key != 'Total Workouts'}
    assert total_workout_count(totals) == 158


def test_pagination_deduplicates_and_respects_last_page():
    now = datetime.now(timezone.utc).timestamp()
    rows = [{'id': str(i), 'start_time': now - i} for i in range(3)]
    client = PelotonClient(Mock())
    client.get_workouts_page = Mock(side_effect=[{'data': rows[:2], 'show_next': True},
                                                {'data': rows[1:], 'show_next': False}])
    assert len(client.get_recent_workouts('u', page_size=2)) == 3
    assert not client.history_truncated
    assert client.get_workouts_page.call_count == 2


def test_pagination_stops_repeated_page_and_exposes_limit():
    client = PelotonClient(Mock())
    client.get_workouts_page = Mock(return_value={'data': [{'id': '1', 'start_time': datetime.now(timezone.utc).timestamp()}], 'show_next': True})
    assert len(client.get_recent_workouts('u', page_size=1)) == 1
    assert client.history_truncated
    assert client.get_workouts_page.call_count == 2


def test_pagination_stops_old_page():
    client = PelotonClient(Mock())
    client.get_workouts_page = Mock(return_value={'data': [{'id': 'old', 'start_time': 1}], 'show_next': True})
    assert client.get_recent_workouts('u', page_size=1) == []
    assert client.get_workouts_page.call_count == 1


def test_get_all_workouts_walks_every_page_with_no_date_cutoff():
    rows = [{'id': str(i)} for i in range(5)]
    client = PelotonClient(Mock())
    client.get_workouts_page = Mock(side_effect=[
        {'data': rows[:2], 'show_next': True},
        {'data': rows[2:4], 'show_next': True},
        {'data': rows[4:], 'show_next': False},
    ])
    result = client.get_all_workouts('u', page_size=2)
    assert [w['id'] for w in result] == ['0', '1', '2', '3', '4']
    assert not client.history_truncated


def test_get_all_workouts_stops_at_known_id_without_paging_further():
    rows = [{'id': str(i)} for i in range(5)]
    client = PelotonClient(Mock())
    client.get_workouts_page = Mock(side_effect=[
        {'data': rows[4:1:-1], 'show_next': True},  # newest-first: ids 4, 3, 2
        {'data': rows[1::-1], 'show_next': False},  # ids 1, 0
    ])
    result = client.get_all_workouts('u', page_size=3, stop_at_id='2')
    assert [w['id'] for w in result] == ['4', '3']
    assert client.get_workouts_page.call_count == 1


@pytest.mark.parametrize('display', [{'duration': -1}, {'color': 'unknown'}, {'font': 'missing'},
    {'timezone': 'Invalid/Zone'}, {'refresh_interval': 0}, {'performance_cache_size': 0},
    {'duration': True}, {'instructor_tally_max_pages': 0}])
def test_config_validation(tmp_path, display):
    import json
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'display': display}))
    with pytest.raises(ValueError):
        load_config(path)


def test_dual_user_config_requires_unique_names_and_tokens(tmp_path):
    import json
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'users': [
        {'name': 'Rider', 'token_path': 'one.token'},
        {'name': 'rider', 'token_path': 'two.token'},
    ]}))
    with pytest.raises(ValueError, match='unique'):
        load_config(path)


def test_dual_user_example_is_valid():
    from pathlib import Path
    example = Path(__file__).resolve().parents[1] / 'config.dual-users-example.json'
    config = load_config(example)
    assert [user['name'] for user in config['users']] == ['Joel', 'Jen']


def test_user_token_path_defaults_to_slug_of_name(tmp_path):
    import json
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'users': [{'name': 'Joel'}, {'name': 'Jen'}]}))
    config = load_config(path)
    assert [user.get('token_path') for user in config['users']] == [None, None]


def test_user_default_token_paths_must_be_unique(tmp_path):
    import json
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'users': [
        {'name': 'Rider'}, {'name': 'Rider!'},
    ]}))
    with pytest.raises(ValueError, match='unique'):
        load_config(path)


def test_user_weekly_goals_and_milestones_are_optional_overrides(tmp_path):
    import json
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'users': [
        {'name': 'Joel', 'weekly_goals': {'workouts': 5}, 'milestones': [500, 100]},
        {'name': 'Jen'},
    ]}))
    config = load_config(path)
    assert config['users'][0]['weekly_goals'] == {'workouts': 5}
    assert config['users'][0]['milestones'] == [100, 500]
    assert 'weekly_goals' not in config['users'][1]
    assert 'milestones' not in config['users'][1]


def test_load_dotenv_sets_unset_vars_and_strips_quotes(tmp_path, monkeypatch):
    monkeypatch.delenv('DOTENV_TEST_EMAIL', raising=False)
    monkeypatch.delenv('DOTENV_TEST_PASSWORD', raising=False)
    env_file = tmp_path / '.env'
    env_file.write_text(
        '# comment\n'
        '\n'
        'DOTENV_TEST_EMAIL=rider@example.com\n'
        'DOTENV_TEST_PASSWORD="quoted secret"\n'
    )
    load_dotenv(env_file)
    assert os.environ['DOTENV_TEST_EMAIL'] == 'rider@example.com'
    assert os.environ['DOTENV_TEST_PASSWORD'] == 'quoted secret'


def test_load_dotenv_does_not_override_existing_env_vars(tmp_path, monkeypatch):
    monkeypatch.setenv('DOTENV_TEST_EMAIL', 'already-set@example.com')
    env_file = tmp_path / '.env'
    env_file.write_text('DOTENV_TEST_EMAIL=from-file@example.com\n')
    load_dotenv(env_file)
    assert os.environ['DOTENV_TEST_EMAIL'] == 'already-set@example.com'


def test_load_dotenv_is_a_noop_when_file_missing(tmp_path):
    load_dotenv(tmp_path / 'missing.env')  # Should not raise.


def test_user_weekly_goals_rejects_unsupported_keys(tmp_path):
    import json
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'users': [
        {'name': 'Joel', 'weekly_goals': {'rides': 5}},
    ]}))
    with pytest.raises(ValueError, match='weekly_goals'):
        load_config(path)


def test_user_milestones_rejects_non_positive_values(tmp_path):
    import json
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'users': [
        {'name': 'Joel', 'milestones': [0, 100]},
    ]}))
    with pytest.raises(ValueError, match='milestones'):
        load_config(path)


@pytest.mark.parametrize('source, value, units, expected', [
    ('average_summaries', 2.1, 'min/500m', 126),
    ('average_summaries', 125, 'sec/500m', 125),
    ('metrics', 2.2, 'min/500m', 132),
])
def test_explicit_rowing_split_takes_precedence(source, value, units, expected):
    perf = metric_perf(4000, 'm', 1200)  # Derived split would be 150 seconds.
    perf[source] = [{'slug': 'split_pace' if source == 'metrics' else 'avg_split_pace',
                     'average_value' if source == 'metrics' else 'value': value,
                     'display_unit': units}]
    assert summarize_workout({'fitness_discipline': 'rowing'}, perf)['row_split_sec_per_500m'] == pytest.approx(expected)


def test_date_only_discipline_match_does_not_hide_latest_timed_workout():
    rows = [{'id': 'cycling', 'start_date': '2026-03-14', 'fitness_discipline': 'cycling'},
            {'id': 'running', 'start_time': 1773496800, 'fitness_discipline': 'running'}]
    assert select_latest(rows, 'cycling')['id'] == 'running'


def test_numeric_overflow_metric_is_missing():
    summary = summarize_workout({'total_work': 10 ** 1000})
    assert summary['total_output_kj'] is None


def test_weekly_progress_uses_local_monday_and_completed_duration():
    from datetime import datetime, timezone
    from peloton.goals import weekly_progress
    now = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)  # Wednesday
    workouts = [
        {'status': 'COMPLETE', 'start_time': datetime(2026, 9, 14, 13, tzinfo=timezone.utc).timestamp(),
         'ride': {'duration': 1800}},
        {'status': 'COMPLETE', 'start_time': datetime(2026, 9, 13, 13, tzinfo=timezone.utc).timestamp(),
         'ride': {'duration': 3600}},
        {'status': 'IN_PROGRESS', 'start_time': datetime(2026, 9, 15, 13, tzinfo=timezone.utc).timestamp(),
         'ride': {'duration': 1200}},
    ]
    assert weekly_progress(workouts, 'UTC', now) == {'workouts': 1, 'minutes': 30}


def test_caesar_bootcamp_normalizes_to_row_bootcamp():
    # Peloton's raw fitness_discipline for its rowing bootcamp classes is
    # "caesar_bootcamp"; it must resolve to the registered "row_bootcamp"
    # discipline (blue color, rowing stat layout), not a generic fallback
    # that title-cases the raw key into "Caesar Bootcamp".
    assert normalize_discipline('caesar_bootcamp') == 'row_bootcamp'


def test_circuit_normalizes_to_tread_bootcamp():
    # Peloton's raw fitness_discipline for its tread bootcamp classes
    # (including walking-bootcamp variants) is "circuit"; Peloton's own
    # fitness_discipline_display_name for these is "Tread Bootcamp", so it
    # must resolve there rather than falling back to "Circuit".
    assert normalize_discipline('circuit') == 'tread_bootcamp'


@pytest.mark.parametrize('discipline,family', [
    ('Cycling', 'cycling'), ('Bike Bootcamp', 'cycling'),
    ('Running', 'running'), ('Walking', 'running'), ('Outdoor Run', 'running'),
    ('Outdoor Walk', 'running'), ('Tread Bootcamp', 'running'), ('Hiking', 'running'),
    ('Rowing', 'rowing'), ('Row Bootcamp', 'rowing'),
    ('Strength', 'general'), ('Cardio', 'general'), ('Yoga', 'general'),
    ('Meditation', 'general'), ('Stretching', 'general'), ('Pilates', 'general'),
    ('Barre', 'general'), ('Boxing', 'general'), ('Dance Cardio', 'general'),
    ('Mobility', 'general'),
])
def test_known_disciplines_have_registered_summary_models(discipline, family):
    model = get_model_for_discipline(discipline)
    assert model is not GeneralWorkout
    slugs = model.perf_slugs()
    assert {'calories', 'hr_avg', 'hr_max'} <= slugs
    if family == 'cycling':
        assert {'avg_cadence', 'avg_resistance'} <= slugs
    elif family == 'running':
        assert {'avg_pace', 'elevation'} <= slugs
    elif family == 'rowing':
        assert {'avg_stroke_rate', 'avg_split_pace'} <= slugs


@pytest.mark.parametrize('discipline,expected_rows', [
    ('Bike Bootcamp', 3), ('Tread Bootcamp', 2), ('Row Bootcamp', 2),
    ('Strength', 2), ('Yoga', 2), ('Meditation', 2), ('Unknown Future Workout', 2),
])
def test_discipline_stat_layouts_have_safe_fallbacks(discipline, expected_rows):
    summary = {'discipline': discipline, 'total_output_kj': 200, 'strive_score': 25,
               'avg_speed': 10, 'avg_speed_unit': 'mph', 'avg_cadence': 80,
               'avg_resistance': 40, 'distance': 3.1, 'distance_unit': 'mi',
               'avg_pace': 10, 'avg_pace_unit': 'min/mi', 'elevation': 100,
               'elevation_unit': 'ft', 'avg_incline': 2, 'avg_stroke_rate': 24,
               'row_split_sec_per_500m': 130, 'avg_output_w': 110, 'hr_max': 165}
    assert len(_middle_stats(summary)) == expected_rows
