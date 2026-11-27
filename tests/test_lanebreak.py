"""Lanebreak workouts: named on the workout page and the PR card, since the title is only the track."""

import pytest

import display.ui.pr_celebration as pr
from display.display import get_text_width, initialize_fonts, loaded_fonts
from display.ui.last_workout.screen import LastWorkoutScreen
from display.ui.last_workout.stats import page_heading
from display.ui.pr_celebration import pr_turns
from peloton.stats.summaries import is_lanebreak, summarize_workout
from scripts.render_demo import ImageMatrix

PLACEHOLDER = {'name': 'LANEBREAK', 'image_url': 'https://s3.amazonaws.com/peloton-ride-images/odyssey-instructor.png'}


def lanebreak(name='Lanebreak Walk', discipline='walking', title='15 min Pop Punk'):
    """Shaped like Joel's first Tread Lanebreak (2026-11-23); the bike's differ only in name, discipline and title."""
    return {
        'id': 'df62d7cb',
        'name': name,
        'title': title,
        'status': 'COMPLETE',
        'fitness_discipline': discipline,
        'workout_type': 'freestyle',
        'start_time': 1795480902,
        'end_time': 1795481809,
        'timezone': 'America/New_York',
        'total_work': 110101.37,
        'is_total_work_personal_record': True,
        'ride': {'id': '0' * 32, 'title': title, 'duration': 907, 'instructor': dict(PLACEHOLDER)},
    }


CLASS = {
    'id': 'c1',
    'name': 'Walking Workout',
    'fitness_discipline': 'walking',
    'status': 'COMPLETE',
    'start_time': 1795480902,
    'ride': {'id': 'r1', 'title': '20 min Walk', 'instructor': {'id': 'i1', 'name': 'Jess Sims'}},
}


@pytest.mark.parametrize(
    'workout',
    [
        lanebreak(),
        lanebreak('Lanebreak Ride', 'cycling', '20 min Red Hot Chili Peppers Vol. 2'),
        lanebreak(name=None),  # the placeholder instructor alone
        lanebreak(name='lanebreak walk') | {'ride': {}},  # the name alone
    ],
)
def test_a_lanebreak_is_known_by_its_name_or_placeholder_instructor(workout):
    assert is_lanebreak(workout)


@pytest.mark.parametrize(
    'workout',
    [
        CLASS,
        {},
        {'name': 'Just Walk', 'ride': {'instructor': {'name': 'Just Walk'}}},
        # An instructor with an ID is a real one, whatever the name says.
        {'ride': {'instructor': {'id': 'i9', 'name': 'Lanebreak'}}},
    ],
)
def test_anything_else_is_not_a_lanebreak(workout):
    assert not is_lanebreak(workout)


def test_only_a_lanebreak_summary_carries_the_flag():
    summary = summarize_workout(lanebreak())
    assert summary['lanebreak'] is True
    assert summary['title'] == '15 min Pop Punk' and summary['instructor'] == '' and summary['discipline'] == 'Walking'
    # Absent, not False, elsewhere: other summaries and the cache's bytes stay as they were.
    assert 'lanebreak' not in summarize_workout(CLASS)


@pytest.mark.parametrize(
    'discipline, heading',
    [('Cycling', 'Bike Lanebreak'), ('Walking', 'Tread Lanebreak'), ('Running', 'Tread Lanebreak'), ('Rowing', 'Lanebreak')],
)
def test_the_heading_says_which_lanebreak_it_was(discipline, heading):
    # Joel, 2026-11-24: tie it to the machine, as Bike / Tread Bootcamp do.
    assert page_heading({'lanebreak': True}, discipline) == heading


@pytest.mark.parametrize('flag', [None, 'yes', 1, False])
def test_the_heading_is_a_lanebreak_only_for_a_true_flag(flag):
    # The cache can hold anything: only a real True renames the page.
    assert page_heading({'lanebreak': flag}, 'Walking') == 'Walking'


def page(summary, height):
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    screen = LastWorkoutScreen()
    screen.on_enter(matrix, summary)
    screen.update(0.5)
    assert screen.render(matrix, summary)
    return matrix.image


def header_rows(height):
    return range(0, 14 if height == 64 else 8)


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('discipline', ['walking', 'cycling'])
def test_the_page_names_a_lanebreak_in_its_disciplines_colour_inside_the_panel(height, discipline):
    summary = summarize_workout(lanebreak(discipline=discipline))
    plain = {k: v for k, v in summary.items() if k != 'lanebreak'}
    named, unnamed = page(summary, height), page(plain, height)
    rows = header_rows(height)
    lit = {(x, y) for y in rows for x in range(64) if named.getpixel((x, y)) != (0, 0, 0)}
    assert lit and min(x for x, _ in lit) >= 1 and max(x for x, _ in lit) <= 62
    assert lit != {(x, y) for y in rows for x in range(64) if unnamed.getpixel((x, y)) != (0, 0, 0)}
    # Same colour as the discipline's own header.
    assert {named.getpixel(p) for p in lit} == {unnamed.getpixel((x, y)) for y in rows for x in range(64)} - {(0, 0, 0)}


def test_the_pr_card_names_a_lanebreak_and_calls_it_no_class():
    summary = summarize_workout(lanebreak()) | {'total_output_kj': 110.0, 'duration_min': 15}
    assert pr_turns(summary)[0][2] == [(pr._BLUE, ['15 MIN'])]
    assert pr._discipline(summary) == ('TREAD LANEBREAK', pr._discipline({'discipline': 'Walking'})[1])
    bike = summarize_workout(lanebreak('Lanebreak Ride', 'cycling'))
    assert pr._discipline(bike) == ('BIKE LANEBREAK', pr._discipline({'discipline': 'Cycling'})[1])
    plain = {k: v for k, v in summary.items() if k != 'lanebreak'}
    assert pr_turns(plain)[0][2] == [(pr._BLUE, ['15 MIN CLASS', '15 MIN'])]
    assert pr._discipline(plain)[0] == 'WALKING'


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('discipline', ['walking', 'cycling'])
def test_the_pr_card_fits_a_lanebreak(height, discipline, monkeypatch):
    monkeypatch.setattr(pr, 'draw_confetti', lambda matrix, elapsed: None)
    summary = summarize_workout(lanebreak(discipline=discipline)) | {'total_output_kj': 110.0, 'duration_min': 15}
    initialize_fonts(height)
    matrix = ImageMatrix(height=height)
    screen = pr.PrCelebrationScreen(detail_interval=4.0)
    screen.on_enter(matrix, summary)
    screen.update(pr.INTRO_SECONDS + 0.5)
    assert screen.render(matrix, summary)
    lit = [(x, y) for y in range(height) for x in range(64) if matrix.image.getpixel((x, y)) != (0, 0, 0)]
    assert lit and min(x for x, _ in lit) >= 0 and max(x for x, _ in lit) <= 63
    # 32 rows put the name right of the trophy, ending at the panel's edge when it must (`short_line_x`):
    # TREAD LANEBREAK is 60 px in the 4x6 font, as wide as OUTDOOR WALKING, so it runs to column 63, uncut.
    if height < 64:
        name, font = pr._discipline(summary)[0], loaded_fonts['info']
        x = pr.short_line_x(font, name)
        assert x >= 0 and x + get_text_width(font, name) - 1 <= 64


# --- Peloton's GraphQL answers (peloton.feeds.lanebreak) ---
# Shaped like the real responses of 2026-11-24 (docs/PELOTON-API.md); every ID is made up.

import json  # noqa: E402
from unittest.mock import Mock  # noqa: E402

import requests  # noqa: E402

from display.ui.last_workout.rotation import detail_hold_seconds, rotating_details  # noqa: E402
from display.ui.last_workout.stats import fmt_beats, lanebreak_stats  # noqa: E402
from peloton.api import GRAPHQL, PelotonClient  # noqa: E402
from peloton.feeds import lanebreak as lb  # noqa: E402

RUN_ID = 'aaaa1111bbbb2222cccc3333dddd4444'
POP_PUNK = '11111111-2222-3333-4444-555555555555'


def run_body(score=57240, difficulty='WALKING', completion=0.9860279):
    workout = {'score': score, 'difficulty': difficulty, 'completionPercent': completion}
    return {'data': {'odysseyWorkout': {'__typename': 'OdysseyWorkoutSuccessResponse', 'workout': workout}}}


def tracks_body(*levels):
    return {'data': {'levels': {'levels': list(levels)}}}


def level(track_id, title, seconds, volume=None):
    return {'id': track_id, 'title': title, 'duration': seconds, 'volume': volume}


def place_body(rank=728, count=1630, workout_id=RUN_ID):
    return {'data': {'odysseyLeaderboard': {'leaderboard': {'count': count, 'extraWorkoutEntry': {'rank': rank, 'workoutId': workout_id}}}}}


def mine_body(*workout_ids):
    rows = [{'workoutId': w} for w in workout_ids]
    return {'data': {'odysseyUserLeaderboard': {'leaderboard': {'count': len(rows), 'leaderboard': rows}}}}


def lanes_body(platform=lb.TREAD_PLATFORM, slug='WALKING'):
    lo, hi = ('minIncline', 'maxIncline') if platform == lb.TREAD_PLATFORM else ('minResistance', 'maxResistance')
    bands = [(0, 0), (0.5, 1), (1.5, 2), (2.5, 3), (3.5, 4), (4.5, 5)]
    lanes = [{'index': i, lo: a, hi: b} for i, (a, b) in enumerate(bands)]
    return {'data': {'odysseyConfiguration': {'difficultyConfigs': [{'slug': slug, 'laneConfigs': lanes}]}}}


def test_a_run_reads_its_score_difficulty_and_beats_hit():
    assert lb.parse_run(run_body()) == {'score': 57240, 'difficulty': 'WALKING', 'completion': 0.9860279}


@pytest.mark.parametrize(
    'body',
    [
        {'data': {'odysseyWorkout': {'__typename': 'OdysseyItemNotFoundError'}}},  # not a Lanebreak
        {'data': None},
        {},
        'junk',
        run_body(score=None),
        run_body(score=-1),
        run_body(score=True),
        run_body(difficulty='walking'),  # not Peloton's enum
        run_body(difficulty=7),
    ],
)
def test_an_unreadable_run_is_none(body):
    assert lb.parse_run(body) is None


@pytest.mark.parametrize('completion', [None, 1.5, -0.1, '0.98', True])
def test_a_bad_completion_keeps_the_score(completion):
    assert lb.parse_run(run_body(completion=completion)) == {'score': 57240, 'difficulty': 'WALKING', 'completion': None}


@pytest.mark.parametrize(
    'title, key',
    [
        ('15 min Pop Punk', ('pop punk', 15, None)),
        ('20 min Red Hot Chili Peppers Vol. 2', ('red hot chili peppers', 20, 2)),
        ('20 min Rock Riot vol 1', ('rock riot', 20, 1)),
        ('20 min Lanebreak Ride', None),  # the bike's older untitled rides
        ('15 min Lanebreak Walk', None),
        ('Pop Punk', None),  # no length
        ('15 min ', None),
        (None, None),
    ],
)
def test_a_title_gives_the_track_name_length_and_volume(title, key):
    assert lb.title_key(title) == key


def test_the_track_is_found_by_name_length_and_volume():
    body = tracks_body(
        level(POP_PUNK, '</b>Pop Punk</b>', 903),  # Peloton's own broken tag
        level('pop-punk-20', '<b>Pop Punk</b>', 1200),
        level('rhcp-1', '<b>Red Hot Chili Peppers</b>', 1203, None),
        level('rhcp-2', '<b>Red Hot Chili Peppers</b>', 1203, 2),
        'junk',
        {'id': 7, 'title': 'Pop Punk', 'duration': 903},
        {'id': 'no-length', 'title': 'Pop Punk'},
    )
    assert lb.track_candidates(body, '15 min Pop Punk') == [POP_PUNK]
    assert lb.track_candidates(body, '20 min Pop Punk') == ['pop-punk-20']
    assert lb.track_candidates(body, '20 min Red Hot Chili Peppers Vol. 2') == ['rhcp-2']
    assert lb.track_candidates(body, '20 min Red Hot Chili Peppers') == ['rhcp-1']
    assert lb.track_candidates(body, '30 min Pop Punk') == []
    assert lb.track_candidates(body, '20 min Lanebreak Ride') == []
    assert lb.track_candidates({'data': None}, '15 min Pop Punk') == []


def test_same_named_tracks_are_all_candidates():
    # Bike: two 20-minute "Low Impact Pop" tracks; the rider's own runs on each tell them apart.
    body = tracks_body(level('a', '<b>Low Impact</b> Pop', 1205), level('b', '<b>Low Impact</b> Pop', 1202))
    assert lb.track_candidates(body, '20 min Low Impact Pop') == ['a', 'b']


def test_only_the_runs_own_track_lists_it_among_the_riders_runs():
    assert lb.owns_run(mine_body('older', RUN_ID), RUN_ID) is True
    assert lb.owns_run(mine_body(), RUN_ID) is False  # another track: count 0
    assert lb.owns_run(mine_body('older'), RUN_ID) is False


@pytest.mark.parametrize(
    'body', [{'data': None}, {}, 'junk', {'data': {'odysseyUserLeaderboard': {'leaderboard': {'leaderboard': ['x', 7]}}}}]
)
def test_an_unreadable_list_of_runs_holds_nothing(body):
    assert lb.owns_run(body, RUN_ID) is False


def test_the_place_is_one_based():
    assert lb.parse_place(place_body(), RUN_ID) == {'place': 729, 'of': 1630}


@pytest.mark.parametrize(
    'body',
    [
        place_body(rank=0, count=1),  # what a made-up track answers: never shown
        place_body(workout_id='someone-else'),
        place_body(rank=1630),
        place_body(rank=-1),
        place_body(rank='3'),
        place_body(count=None),
        {'data': {'odysseyLeaderboard': {'leaderboard': {'count': 1630, 'extraWorkoutEntry': None}}}},
        {'data': None},
        'junk',
    ],
)
def test_an_unreadable_or_wrong_track_place_is_none(body):
    assert lb.parse_place(body, RUN_ID) is None


def test_lanes_read_each_difficultys_six_bands():
    assert lb.parse_lanes(lanes_body(), lb.TREAD_PLATFORM) == {'WALKING': [(0, 0), (0.5, 1), (1.5, 2), (2.5, 3), (3.5, 4), (4.5, 5)]}
    assert lb.parse_lanes(lanes_body(lb.BIKE_PLATFORM, 'ADVANCED'), lb.BIKE_PLATFORM)['ADVANCED'][5] == (4.5, 5)


def test_unreadable_lanes_are_left_out():
    body = lanes_body()
    good = body['data']['odysseyConfiguration']['difficultyConfigs'][0]
    short = {'slug': 'BEGINNER', 'laneConfigs': good['laneConfigs'][:5]}
    backwards = {'slug': 'EXPERT', 'laneConfigs': [dict(lane, minIncline=9) for lane in good['laneConfigs']]}
    body['data']['odysseyConfiguration']['difficultyConfigs'] += [short, backwards, 'junk', {'slug': 'X'}]
    assert list(lb.parse_lanes(body, lb.TREAD_PLATFORM)) == ['WALKING']
    assert lb.parse_lanes(body, 'web') is None  # no lanes for an unknown machine
    assert lb.parse_lanes({'data': None}, lb.TREAD_PLATFORM) is None


def test_samples_go_to_their_lane_or_the_nearest_one():
    bands = [(0, 0), (0.5, 1), (1.5, 2), (2.5, 3), (3.5, 4), (4.5, 5)]
    # 0.25 sits between lanes 1 and 2: it goes to the nearer middle (lane 1's 0).
    assert lb.lane_samples([0, 0.25, 0.5, 1.0, 1.2, 2.5, None, 'x', 9], bands) == [2, 3, 0, 1, 0, 1]
    assert lb.lane_samples([None, 'x'], bands) is None


def test_machines_and_series():
    assert lb.platform_for('cycling') == lb.BIKE_PLATFORM
    assert lb.platform_for('Walking') == lb.platform_for('running') == lb.TREAD_PLATFORM
    assert lb.platform_for('rowing') is None
    perf = {'metrics': [{'slug': 'incline', 'values': [1, 2]}, 'junk']}
    assert lb.metric_values(perf, 'incline') == [1, 2]
    assert lb.metric_values(perf, 'resistance') == lb.metric_values(None, 'incline') == []


# --- PelotonClient: the gateway ---


def gateway(*bodies, status=200):
    session = Mock()
    replies = []
    for body in bodies:
        reply = requests.Response()
        reply.status_code = status
        reply._content = json.dumps(body).encode()
        reply.url = GRAPHQL
        replies.append(reply)
    session.post.side_effect = replies
    return PelotonClient(session), session


def test_the_client_sends_values_as_variables_with_the_machine():
    client, session = gateway(place_body())
    assert client.get_lanebreak_place(POP_PUNK, 'WALKING', RUN_ID, lb.TREAD_PLATFORM) == place_body()
    call = session.post.call_args
    assert call.args[0] == GRAPHQL and call.kwargs['headers'] == {'peloton-platform': lb.TREAD_PLATFORM}
    request = call.kwargs['json']['variables']['request']
    assert request == {'levelId': POP_PUNK, 'difficulty': 'WALKING', 'from': 0, 'size': 0, 'extraWorkoutId': RUN_ID}
    assert POP_PUNK not in call.kwargs['json']['query']  # values never go into the query text


def test_the_riders_runs_are_asked_newest_first_on_the_machine():
    client, session = gateway(mine_body(RUN_ID))
    assert client.get_lanebreak_mine(POP_PUNK, lb.BIKE_PLATFORM) == mine_body(RUN_ID)
    call = session.post.call_args
    assert call.kwargs['headers'] == {'peloton-platform': lb.BIKE_PLATFORM}
    assert call.kwargs['json']['variables']['request'] == {'levelId': POP_PUNK, 'from': 0, 'size': 50, 'sortBy': 'Date'}
    assert POP_PUNK not in call.kwargs['json']['query']


def test_the_run_query_uses_the_sessions_own_platform():
    client, session = gateway(run_body())
    client.get_lanebreak_run(RUN_ID)
    assert session.post.call_args.kwargs['headers'] == {}
    assert session.post.call_args.kwargs['json']['variables'] == {'id': RUN_ID}


def test_errors_without_data_raise():
    client, _ = gateway({'errors': [{'message': 'INTERNAL_SERVER_ERROR'}], 'data': None})
    with pytest.raises(ValueError, match='INTERNAL_SERVER_ERROR'):
        client.get_lanebreak_run('')


def test_a_gateway_401_never_marks_the_token_rejected():
    client, _ = gateway({}, status=401)
    with pytest.raises(requests.HTTPError):
        client.get_lanebreak_tracks(lb.TREAD_PLATFORM)
    assert client.login_required is False


# --- The Dashboard fetches a Lanebreak once ---

from datetime import UTC, datetime, timedelta  # noqa: E402

import peloton.dashboard_lanebreak as dl  # noqa: E402
from tests.test_dashboard import setup_dashboard  # noqa: E402


def lanebreak_setup(tmp_path, title='15 min Pop Punk', discipline='walking'):
    dashboard, client, token = setup_dashboard(tmp_path)
    start = (datetime.now(UTC) - timedelta(days=2)).timestamp()
    workout = lanebreak(name=None, discipline=discipline, title=title) | {'id': RUN_ID, 'start_time': start, 'end_time': start + 907}
    client.history = [workout]
    client.get_perf_graph.return_value = {'duration': 907, 'metrics': [{'slug': 'incline', 'values': [0, 0.5, 1.0, 1.5, 0.5]}]}
    client.get_lanebreak_run.return_value = run_body()
    client.get_lanebreak_tracks.return_value = tracks_body(level(POP_PUNK, '<b>Pop Punk</b>', 903))
    client.get_lanebreak_place.return_value = place_body()
    client.get_lanebreak_mine.return_value = mine_body(RUN_ID)
    client.get_lanebreak_lanes.return_value = lanes_body()
    return dashboard, client


def gateway_calls(client):
    return sum(
        m.call_count
        for m in (
            client.get_lanebreak_run,
            client.get_lanebreak_tracks,
            client.get_lanebreak_mine,
            client.get_lanebreak_place,
            client.get_lanebreak_lanes,
        )
    )


def test_a_lanebreak_gets_its_score_place_and_lanes_once(tmp_path):
    dashboard, client = lanebreak_setup(tmp_path)
    dashboard.refresh()
    stats = dashboard.snapshot()['summaries'][0]['lanebreak_stats']
    assert stats == {
        'score': 57240,
        'difficulty': 'WALKING',
        'completion': 0.9860279,
        'place': {'place': 729, 'of': 1630},
        'lanes': [1, 3, 1, 0, 0, 0],
    }
    client.get_lanebreak_place.assert_called_once_with(POP_PUNK, 'WALKING', RUN_ID, lb.TREAD_PLATFORM)
    client.get_lanebreak_tracks.assert_called_once_with(lb.TREAD_PLATFORM)
    client.get_lanebreak_mine.assert_not_called()  # one track of that name: nothing to tell apart
    assert gateway_calls(client) == 4
    dashboard.refresh()
    assert gateway_calls(client) == 4  # kept: nothing asked again
    assert dashboard.snapshot()['summaries'][0]['lanebreak_stats'] == stats


def test_other_workouts_never_ask_the_gateway(tmp_path):
    dashboard, client, _ = setup_dashboard(tmp_path)
    dashboard.refresh()
    assert gateway_calls(client) == 0
    assert 'lanebreak_stats' not in dashboard.snapshot()['summaries'][0]


def test_an_untitled_ride_shows_its_score_without_a_place_or_the_track_list(tmp_path):
    dashboard, client = lanebreak_setup(tmp_path, title='20 min Lanebreak Ride', discipline='cycling')
    client.get_lanebreak_lanes.return_value = lanes_body(lb.BIKE_PLATFORM, 'WALKING')
    dashboard.refresh()
    stats = dashboard.snapshot()['summaries'][0]['lanebreak_stats']
    assert stats['score'] == 57240 and stats['place'] is None
    client.get_lanebreak_tracks.assert_not_called()
    client.get_lanebreak_place.assert_not_called()


def test_same_named_tracks_place_the_run_only_on_its_own_track(tmp_path):
    # Regression: Jen's "20 min Top 50 Music: Remixed" (2024-12-31) matches three bike tracks (the Top 50 of 2024,
    # 2023 and 2022). The leaderboard ranks her run on any of them (a wrong one answered 29,129th of 33,366), and the
    # board used to take the first answer, right only because Peloton listed her track first.
    dashboard, client = lanebreak_setup(tmp_path, title='20 min Top 50 Music: Remixed', discipline='cycling')
    client.get_lanebreak_lanes.return_value = lanes_body(lb.BIKE_PLATFORM)
    client.get_lanebreak_tracks.return_value = tracks_body(
        level('top-50-2023', '<b>Top 50</b> Music: Remixed', 1202),
        level('top-50-2024', '<b>Top 50 Music: Remixed</b>', 1204),
        level('top-50-2022', '<b>Top 50 Music:</b> Remixed', 1206),
    )
    client.get_lanebreak_mine.side_effect = lambda track, _: mine_body(RUN_ID) if track == 'top-50-2024' else mine_body()
    client.get_lanebreak_place.side_effect = lambda track, *_: (
        place_body(rank=14981, count=35670) if track == 'top-50-2024' else place_body(rank=29128, count=33366)
    )
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['lanebreak_stats']['place'] == {'place': 14982, 'of': 35670}
    client.get_lanebreak_place.assert_called_once_with('top-50-2024', 'WALKING', RUN_ID, lb.BIKE_PLATFORM)
    assert [c.args[0] for c in client.get_lanebreak_mine.call_args_list] == ['top-50-2023', 'top-50-2024']


def test_same_named_tracks_none_of_which_holds_the_run_settle_with_no_place(tmp_path, monkeypatch):
    dashboard, client = lanebreak_setup(tmp_path)
    client.get_lanebreak_tracks.return_value = tracks_body(level('a', 'Pop Punk', 903), level('b', 'Pop Punk', 905))
    client.get_lanebreak_mine.return_value = mine_body()
    clock = [1000.0]
    monkeypatch.setattr(dl.time, 'monotonic', lambda: clock[0])
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['lanebreak_stats']['place'] is None
    client.get_lanebreak_place.assert_not_called()  # never a plausible place from the wrong track
    clock[0] += 2 * dl.LANEBREAK_RETRY_SECONDS
    dashboard.refresh()
    assert client.get_lanebreak_mine.call_count == 2  # settled: not asked again


def test_a_failed_check_of_the_riders_runs_is_retried(tmp_path, monkeypatch):
    dashboard, client = lanebreak_setup(tmp_path)
    client.get_lanebreak_tracks.return_value = tracks_body(level('a', 'Pop Punk', 903), level(POP_PUNK, 'Pop Punk', 905))
    client.get_lanebreak_mine.side_effect = requests.ConnectionError('down')
    clock = [1000.0]
    monkeypatch.setattr(dl.time, 'monotonic', lambda: clock[0])
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['lanebreak_stats']['place'] is None
    client.get_lanebreak_mine.side_effect = lambda track, _: mine_body(RUN_ID) if track == POP_PUNK else mine_body()
    clock[0] += dl.LANEBREAK_RETRY_SECONDS
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['lanebreak_stats']['place'] == {'place': 729, 'of': 1630}
    client.get_lanebreak_place.assert_called_once_with(POP_PUNK, 'WALKING', RUN_ID, lb.TREAD_PLATFORM)


def test_a_failed_run_shows_nothing_new_and_is_asked_again_after_the_wait(tmp_path, monkeypatch):
    dashboard, client = lanebreak_setup(tmp_path)
    client.get_lanebreak_run.side_effect = requests.ConnectionError('down')
    clock = [1000.0]
    monkeypatch.setattr(dl.time, 'monotonic', lambda: clock[0])
    dashboard.refresh()
    summary = dashboard.snapshot()['summaries'][0]
    assert 'lanebreak_stats' not in summary and summary['lanebreak'] is True
    dashboard.refresh()
    assert client.get_lanebreak_run.call_count == 1  # not before the wait
    client.get_lanebreak_run.side_effect = None
    clock[0] += dl.LANEBREAK_RETRY_SECONDS
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['lanebreak_stats']['score'] == 57240


def test_a_failed_place_keeps_the_score_and_retries_only_the_place(tmp_path, monkeypatch):
    dashboard, client = lanebreak_setup(tmp_path)
    client.get_lanebreak_place.side_effect = requests.HTTPError('401 from the gateway')
    clock = [1000.0]
    monkeypatch.setattr(dl.time, 'monotonic', lambda: clock[0])
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['lanebreak_stats']['place'] is None
    assert dashboard.snapshot()['login_required'] is False  # the gateway never rejects the token
    client.get_lanebreak_place.side_effect = None
    clock[0] += dl.LANEBREAK_RETRY_SECONDS
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['lanebreak_stats']['place'] == {'place': 729, 'of': 1630}
    assert client.get_lanebreak_run.call_count == 1


def test_lanes_are_asked_weekly_and_a_failure_keeps_the_last_ones(tmp_path, monkeypatch):
    dashboard, client = lanebreak_setup(tmp_path)
    clock = [1000.0]
    monkeypatch.setattr(dl.time, 'monotonic', lambda: clock[0])
    dashboard.refresh()
    clock[0] += dl.LANES_REFRESH_SECONDS
    client.get_lanebreak_lanes.side_effect = ValueError('GraphQL error')
    dashboard.refresh()
    assert client.get_lanebreak_lanes.call_count == 2
    assert dashboard.snapshot()['summaries'][0]['lanebreak_stats']['lanes'] == [1, 3, 1, 0, 0, 0]
    clock[0] += 60
    dashboard.refresh()
    assert client.get_lanebreak_lanes.call_count == 2  # waits an hour after a failure


def test_no_lanes_for_a_difficulty_the_machine_does_not_list(tmp_path):
    dashboard, client = lanebreak_setup(tmp_path)
    client.get_lanebreak_lanes.return_value = lanes_body(slug='EXPERT')
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['lanebreak_stats']['lanes'] is None


# --- The workout page ---

STATS = {
    'score': 57240,
    'difficulty': 'WALKING',
    'completion': 0.9860279,
    'place': {'place': 729, 'of': 1630},
    'lanes': [44, 88, 42, 7, 0, 0],
}


def lanebreak_page(**stats):
    summary = summarize_workout(lanebreak()) | {
        'distance': 0.71,
        'distance_unit': 'mi',
        'hr_avg': 132,
        'calories': 282,
        'strive_score': 8.7,
    }
    return summary | {'lanebreak_stats': STATS | stats}


def test_a_lanebreak_page_leads_with_its_own_frames():
    assert [d['label'] for d in rotating_details(lanebreak_page(), 64)][:4] == ['lanebreak score', 'beats hit', 'leaderboard', 'lanes']
    # 64x32 has no room in the intro: the difficulty is its own first frame, where a class's instructor goes.
    assert [d['label'] for d in rotating_details(lanebreak_page(), 32)][:5] == [
        'difficulty',
        'lanebreak score',
        'beats hit',
        'leaderboard',
        'lanes',
    ]
    values = {d['label']: d['value'] for d in rotating_details(lanebreak_page(), 32)}
    assert values['lanebreak score'] == '57,240' and values['beats hit'] == '98.6%' and values['difficulty'] == 'WALKING'


def test_the_new_slides_hold_like_the_zone_bar():
    for detail in rotating_details(lanebreak_page(), 64)[2:4]:
        assert detail_hold_seconds(detail, 4) == detail_hold_seconds({'kind': 'zones'}, 4) == 5


def test_frames_drop_out_with_what_is_missing():
    labels = [d['label'] for d in rotating_details(lanebreak_page(place=None, lanes=None, completion=None), 64)]
    assert labels[:2] == ['lanebreak score', 'distance']


@pytest.mark.parametrize(
    'bad',
    [
        None,
        'junk',
        {'score': '57240', 'difficulty': 'WALKING'},
        {'score': 57240, 'difficulty': 'walking'},
        {'score': True, 'difficulty': 'WALKING'},
    ],
)
def test_an_unreadable_cache_entry_shows_no_lanebreak_frames(bad):
    summary = lanebreak_page() | {'lanebreak_stats': bad}
    assert lanebreak_stats(summary) == {}
    assert 'lanebreak score' not in [d['label'] for d in rotating_details(summary, 32)]


@pytest.mark.parametrize(
    'field, value',
    [
        ('place', {'place': 0, 'of': 5}),
        ('place', {'place': 9, 'of': 5}),
        ('place', 'first'),
        ('lanes', [1, 2, 3]),
        ('lanes', [0] * 6),
        ('lanes', [1, -1, 0, 0, 0, 0]),
    ],
)
def test_a_bad_place_or_lanes_drops_only_that_frame(field, value):
    stats = lanebreak_stats(lanebreak_page(**{field: value}))
    assert stats[field] is None and stats['score'] == 57240


def test_a_lanebreak_without_the_flag_is_not_one():
    summary = lanebreak_page() | {'lanebreak': None}
    assert lanebreak_stats(summary) == {}


@pytest.mark.parametrize('completion, text', [(0.9860279, '98.6%'), (0.99973047, '99.9%'), (1, '100.0%'), (0, '0.0%')])
def test_beats_hit_rounds_down(completion, text):
    assert fmt_beats(completion) == text


def frame_of(summary, height, label):
    initialize_fonts(height)
    details = rotating_details(summary, height)
    turn = [d['label'] for d in details].index(label)
    matrix = ImageMatrix(height=height)
    screen = LastWorkoutScreen()
    screen.on_enter(matrix, summary)
    screen.update(4 + sum(detail_hold_seconds(d, 4) for d in details[:turn]) + 0.5)
    assert screen.render(matrix, summary)
    return matrix.image


def lit(image, rows=None):
    return [(x, y) for y in (rows or range(image.height)) for x in range(image.width) if image.getpixel((x, y)) != (0, 0, 0)]


# The largest values the data can hold: a 6-digit score, the longest difficulty, a 5-digit place of a big board.
LARGEST = {'score': 309193, 'difficulty': 'INTERMEDIATE', 'place': {'place': 53637, 'of': 53637}, 'lanes': [0, 0, 0, 0, 0, 900]}


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('stats', [STATS, STATS | LARGEST])
@pytest.mark.parametrize('label', ['lanebreak score', 'beats hit', 'leaderboard', 'lanes'])
def test_every_lanebreak_frame_fits_the_panel(height, stats, label):
    pixels = lit(frame_of(lanebreak_page(**stats), height, label))
    assert pixels and min(x for x, _ in pixels) >= 1 and max(x for x, _ in pixels) <= 62 and max(y for _, y in pixels) < height


@pytest.mark.parametrize('height', [32, 64])
def test_the_place_is_gold_and_the_busiest_lane_named(height):
    gold = (255, 200, 0)
    assert any(
        frame_of(lanebreak_page(), height, 'leaderboard').getpixel(p) == gold
        for p in lit(frame_of(lanebreak_page(), height, 'leaderboard'))
    )
    lanes = frame_of(lanebreak_page(), height, 'lanes')
    lane_two = (0, 210, 200)  # lane 2 holds 49% of this walk
    assert sum(1 for p in lit(lanes) if lanes.getpixel(p) == lane_two) > 0


@pytest.mark.parametrize('difficulty', ['WALKING', 'INTERMEDIATE'])
def test_the_64_row_intro_shows_the_difficulty_under_its_caption(difficulty):
    summary = lanebreak_page(difficulty=difficulty)
    named = page(summary, 64)
    without = page({k: v for k, v in summary.items() if k != 'lanebreak_stats'}, 64)
    rows = range(30, 55)
    assert lit(named, rows) != lit(without, rows)
    pixels = lit(named, rows)
    assert min(x for x, _ in pixels) >= 1 and max(x for x, _ in pixels) <= 62


def test_the_lanes_query_goes_to_the_machine():
    client, session = gateway(lanes_body())
    assert client.get_lanebreak_lanes(lb.BIKE_PLATFORM) == lanes_body()
    assert session.post.call_args.kwargs['headers'] == {'peloton-platform': lb.BIKE_PLATFORM}


def test_score_and_beats_need_a_readable_lanebreak():
    from display.ui.last_workout.stats import lanebreak_details

    assert lanebreak_details({'lanebreak': True}) == []
    assert lanebreak_details(lanebreak_page(completion=None)) == [{'label': 'lanebreak score', 'value': '57,240'}]


@pytest.mark.parametrize(
    'change',
    [{'status': 'IN_PROGRESS'}, {'id': None}, {'fitness_discipline': 'rowing'}, {'name': 'Walking Workout', 'ride': CLASS['ride']}],
)
def test_only_a_finished_lanebreak_asks_the_gateway(tmp_path, change):
    dashboard, client = lanebreak_setup(tmp_path)
    workout = client.history[0] | change
    assert dashboard._lanebreak_stats(client, workout, {}, ('sig',)) is None
    assert gateway_calls(client) == 0


def test_a_run_the_gateway_does_not_know_yet_is_asked_again_later(tmp_path, monkeypatch):
    dashboard, client = lanebreak_setup(tmp_path)
    client.get_lanebreak_run.return_value = {'data': {'odysseyWorkout': {'__typename': 'OdysseyItemNotFoundError'}}}
    clock = [1000.0]
    monkeypatch.setattr(dl.time, 'monotonic', lambda: clock[0])
    dashboard.refresh()
    assert 'lanebreak_stats' not in dashboard.snapshot()['summaries'][0]
    client.get_lanebreak_place.assert_not_called()
    client.get_lanebreak_run.return_value = run_body()
    clock[0] += dl.LANEBREAK_RETRY_SECONDS
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['lanebreak_stats']['place'] == {'place': 729, 'of': 1630}


def test_no_track_answering_with_the_run_is_settled_without_a_place(tmp_path, monkeypatch):
    dashboard, client = lanebreak_setup(tmp_path)
    client.get_lanebreak_place.return_value = place_body(rank=0, count=1)  # the fake a wrong track gives
    clock = [1000.0]
    monkeypatch.setattr(dl.time, 'monotonic', lambda: clock[0])
    dashboard.refresh()
    assert dashboard.snapshot()['summaries'][0]['lanebreak_stats']['place'] is None
    clock[0] += 2 * dl.LANEBREAK_RETRY_SECONDS
    dashboard.refresh()
    assert client.get_lanebreak_place.call_count == 1  # settled: not asked again


def test_kept_lanebreaks_are_bounded(tmp_path):
    dashboard, client = lanebreak_setup(tmp_path)
    dashboard._performance_cache_size = 1
    first = client.history[0]
    second = first | {
        'id': 'bbbb1111bbbb2222cccc3333dddd4444',
        'start_time': first['start_time'] + 1000,
        'end_time': first['end_time'] + 1000,
    }
    client.history = [second, first]
    dashboard.refresh()
    assert len(dashboard._lanebreaks) == 1 and set(dashboard._lanebreaks) < {first['id'], second['id']}
