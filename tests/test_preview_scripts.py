"""The offline preview tools: render_rotation, render_demo and preview_pr."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests
from PIL import Image

from peloton.cache import save_snapshot
from peloton.demo import demo_data
from scripts import preview_pr, render_rotation
from scripts.render_rotation import SCALE, frame_times, load_snapshot_for


def _sheet_tiles(path, height, columns=5):
    image = Image.open(path)
    tile_w, tile_h = 64 * SCALE + 12, height * SCALE + 28
    assert image.width == tile_w * columns
    assert image.height % tile_h == 0
    return image


# render_rotation

@pytest.mark.parametrize('height', [32, 64])
def test_demo_rotation_renders_every_page(tmp_path, height, capsys):
    out = tmp_path / f'demo-{height}.png'
    render_rotation.main(['--demo', '--height', str(height), '--out', str(out)])
    _sheet_tiles(out, height)
    frames, pages = map(int, capsys.readouterr().out.split()[0:4:3])
    assert pages >= 10 and frames >= pages


def test_cache_rotation_with_a_rival_and_no_overlays(tmp_path, capsys):
    snapshot = {**load_snapshot_for(SimpleNamespace(demo=True)), 'last_updated': 1773496800}
    cache, rival = tmp_path / 'joel-cache.json', tmp_path / 'jen-cache.json'
    save_snapshot(cache, snapshot)
    save_snapshot(rival, {**snapshot, 'weekly_progress': {'workouts': 6, 'minutes': 200}})
    out = tmp_path / 'sheet.png'
    render_rotation.main(['--cache', str(cache), '--rival', str(rival), '--rival-name', 'Jen',
                          '--username', 'Joel', '--no-overlays', '--columns', '3', '--out', str(out)])
    _sheet_tiles(out, 32, columns=3)
    assert '-> ' + str(out) in capsys.readouterr().out


def test_cache_rotation_reads_the_workout_log_and_config_route(tmp_path, capsys):
    from peloton.workout_log import WorkoutLog, default_log_path
    snapshot = {**load_snapshot_for(SimpleNamespace(demo=True)), 'last_updated': 1773496800}
    cache = tmp_path / 'joel-cache.json'
    save_snapshot(cache, snapshot)
    log = WorkoutLog(default_log_path(cache))
    log.claim('demo')
    log.merge([{'id': f'w{i}', 'status': 'COMPLETE', 'start_time': 1773496800 - i * 86400, 'distance': 10.0,
                'fitness_discipline': 'cycling', 'ride': {'instructor': {'id': 'jess', 'name': 'Jess Sims'}}}
               for i in range(3)])
    log.backfill['complete'] = True
    log.save()
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'display': {'journey': {'from': 'Home', 'to': 'Gym', 'miles': 50}}}))
    options = SimpleNamespace(demo=False, cache=str(cache), log=None, config=str(config))
    loaded = load_snapshot_for(options)
    assert loaded['instructor_counts'] == {'jess': 3} and loaded['distance_totals'] == {'cycling': 30.0}
    assert render_rotation.preview_journey(options)['to'] == 'Gym'
    out = tmp_path / 'sheet.png'
    render_rotation.main(['--cache', str(cache), '--config', str(config), '--out', str(out)])
    _sheet_tiles(out, 32)
    # Without a log the cache still renders (no instructor or journey pages).
    log.path.unlink()
    assert 'instructor_counts' not in load_snapshot_for(SimpleNamespace(demo=False, cache=str(cache)))
    bad = tmp_path / 'bad.json'
    bad.write_text('{"display": {"color": "plaid"}}')
    with pytest.raises(SystemExit, match='unsupported display.color'):
        render_rotation.preview_journey(SimpleNamespace(config=str(bad)))


def test_unreadable_cache_is_a_clear_error(tmp_path):
    with pytest.raises(SystemExit, match='Could not read a dashboard cache'):
        render_rotation.main(['--cache', str(tmp_path / 'missing.json'), '--out', str(tmp_path / 'x.png')])


def test_source_is_required():
    with pytest.raises(SystemExit):
        render_rotation.main([])


def test_frame_times_per_page_kind():
    assert frame_times('logo', {}, 1.0, 4) == [0.5]
    assert len(frame_times('pr', {}, 10, 4)) == 2
    assert frame_times('username', {'details': ['a', 'b', 'c']}, 10, 4)[0] == 0.6
    assert len(frame_times('username', {'details': ['a', 'b', 'c']}, 10, 4)) == 3
    assert frame_times('last_workout', {'compact_page': 1}, 8, 4) == [0.6, 4.6]
    assert len(frame_times('versus', {'riders': []}, 30, 4)) >= 1
    assert frame_times('last_workout', {}, 0, 4) == [0.6]


def test_preview_dashboard_celebrates_only_the_newest_reached_milestone():
    dashboard = render_rotation.PreviewDashboard([100, 250, 500])
    assert dashboard.pending_milestones({'totals': {'Total Workouts': 300}}) == [250]
    assert dashboard.pending_milestones({'totals': {}}) == []
    assert dashboard.should_celebrate_pr({'is_pr': True}) is True


# render_demo

def test_demo_contact_sheet(tmp_path):
    from scripts.render_demo import render_contact_sheet
    out = tmp_path / 'demo.png'
    render_contact_sheet(out)
    assert Image.open(out).size == (272 * 6, 294 * 3)


# preview_pr

def _config(tmp_path, users):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'users': users} if users is not None else {}))
    return path


def test_token_path_defaults_to_the_first_user(tmp_path):
    path = _config(tmp_path, [{'name': 'Joel'}, {'name': 'Jen', 'token_path': 'jen.txt'}])
    config = json.loads(path.read_text())
    assert preview_pr.token_path_for(config, path) == (tmp_path / 'cookies-joel.txt', 'Joel')
    assert preview_pr.token_path_for(config, path, ' jen ') == (tmp_path / 'jen.txt', 'Jen')
    with pytest.raises(SystemExit, match="No user named 'Bob'; configured: Joel, Jen"):
        preview_pr.token_path_for(config, path, 'Bob')


def test_token_path_without_users_is_the_default_file(tmp_path):
    assert preview_pr.token_path_for({}, tmp_path / 'config.json') == (preview_pr.ROOT / 'cookies.txt', 'default')


def _workout(pr=False, status='COMPLETE', wid='w'):
    workout = {'id': wid, 'status': status, 'is_total_work_personal_record': pr,
               'fitness_discipline': 'cycling', 'created_at': 1773496800}
    return workout


def test_find_latest_pr_pages_back_until_it_finds_one():
    client = MagicMock()
    client.get_workouts_page.side_effect = [
        {'data': [_workout(), _workout(pr=True, status='IN_PROGRESS')], 'show_next': True},
        {'data': [_workout(), _workout(pr=True, wid='pr')], 'show_next': True},
    ]
    workout, pages = preview_pr.find_latest_pr(client, 'user', max_pages=5)
    assert workout['id'] == 'pr' and pages == 2


@pytest.mark.parametrize('pages,expected', [
    ([{'data': [_workout()], 'show_next': False}], 1),
    ([{'data': []}], 1),
    ([{'data': [_workout()], 'show_next': True}] * 3, 3),
])
def test_find_latest_pr_stops_at_the_end_of_history(pages, expected):
    client = MagicMock()
    client.get_workouts_page.side_effect = pages
    assert preview_pr.find_latest_pr(client, 'user', max_pages=3) == (None, expected)


def test_find_latest_pr_rejects_a_malformed_page():
    client = MagicMock()
    client.get_workouts_page.return_value = {'data': {'not': 'a list'}}
    with pytest.raises(ValueError, match='Malformed'):
        preview_pr.find_latest_pr(client, 'user', max_pages=1)


@pytest.fixture
def pr_setup(tmp_path):
    data = demo_data()
    pr = next(w for w in data['workouts'] if w.get('is_total_work_personal_record'))
    token = tmp_path / 'cookies-joel.txt'
    token.write_text('token')
    config = _config(tmp_path, [{'name': 'Joel'}])
    client = MagicMock()
    client.get_me.return_value = {'id': 'user-1'}
    client.get_workouts_page.return_value = {'data': [pr], 'show_next': False}
    client.get_perf_graph.return_value = data['performance'][pr['id']]
    return SimpleNamespace(config=config, token=token, client=client, tmp=tmp_path)


def _run_preview(setup, *extra):
    with patch('peloton.api.PelotonClient', return_value=setup.client), \
         patch('peloton.api.make_session'):
        preview_pr.main(['--config', str(setup.config), *extra])


def test_preview_saves_frames_and_reports_the_api_cost(pr_setup, caplog):
    out = pr_setup.tmp / 'pr.png'
    with caplog.at_level('INFO', logger='peloton-led.preview-pr'):
        _run_preview(pr_setup, '--png', str(out), '--previous-best', '250')
    assert Image.open(out).size == (4 * 264 - 8, 256)
    assert '3 API calls total' in caplog.text
    assert '"previous_best_kj": 250.0' in caplog.text
    pr_setup.client.close.assert_called_once()


def test_preview_plays_in_the_emulator_without_png(pr_setup):
    with patch('scripts.preview_pr.play_in_emulator') as play:
        _run_preview(pr_setup, '--replay', '2')
    assert play.call_args.args[1] == 2.0


def test_preview_with_explicit_token(pr_setup):
    with patch('scripts.preview_pr.play_in_emulator') as play:
        _run_preview(pr_setup, '--token', str(pr_setup.token))
    play.assert_called_once()


def test_preview_missing_token_file(pr_setup):
    pr_setup.token.unlink()
    with pytest.raises(SystemExit, match='Token file not found'):
        _run_preview(pr_setup)


def test_preview_profile_without_id(pr_setup):
    pr_setup.client.get_me.return_value = {}
    with pytest.raises(SystemExit, match='no user ID'):
        _run_preview(pr_setup)
    pr_setup.client.close.assert_called_once()


def test_preview_with_no_pr_in_history(pr_setup):
    pr_setup.client.get_workouts_page.return_value = {'data': [_workout()], 'show_next': False}
    with pytest.raises(SystemExit, match='No PR found for Joel in the last 50 workouts'):
        _run_preview(pr_setup)


def test_preview_rejected_token(pr_setup):
    response = requests.Response()
    response.status_code = 401
    pr_setup.client.get_me.side_effect = requests.HTTPError(response=response)
    with pytest.raises(SystemExit, match='rejected the token'):
        _run_preview(pr_setup)


def test_preview_other_errors_propagate(pr_setup):
    pr_setup.client.get_me.side_effect = requests.ConnectionError('offline')
    with pytest.raises(requests.ConnectionError):
        _run_preview(pr_setup)
    pr_setup.client.close.assert_called_once()


def test_preview_bad_config(tmp_path):
    bad = tmp_path / 'config.json'
    bad.write_text('{not json')
    with pytest.raises(SystemExit):
        preview_pr.main(['--config', str(bad)])
