"""A broken screen or a damaged cache must never take the board down."""
import json
from unittest.mock import Mock

import pytest

from display.ui.manager import ScreenManager
from display.ui.screen import Screen
from peloton.cache import CACHE_VERSION, load_snapshot


class Exploding(Screen):
    def __init__(self, where):
        self.where = where

    def on_enter(self, matrix, state=None):
        if self.where == 'enter':
            raise RuntimeError('enter')

    def on_exit(self, matrix):
        if self.where == 'exit':
            raise RuntimeError('exit')

    def render(self, matrix, state=None):
        if self.where == 'render':
            raise RuntimeError('render')
        return True


def test_initial_screen_and_clear_failures_are_survived():
    matrix = Mock(width=64, height=64)
    matrix.Clear.side_effect = RuntimeError('clear')
    manager = ScreenManager(matrix, initial=Exploding('enter'))
    assert manager.current is not None


def test_unknown_screen_is_ignored():
    manager = ScreenManager(Mock(width=64, height=64))
    manager.show('nope')
    assert manager.current_name is None


@pytest.mark.parametrize('where', ['enter', 'exit', 'render'])
def test_screen_errors_do_not_stop_the_rotation(where):
    matrix = Mock(width=64, height=64, spec=['width', 'height', 'Clear', 'SetPixel'])
    manager = ScreenManager(matrix, initial=Exploding(where), login_required=lambda: True,
                            stale_data=lambda: True)
    manager.register('next', Exploding(where))
    manager.show('next', {'x': 1})
    manager.tick({'x': 1})
    assert manager.current_name == 'next'
    # Indicators are still drawn over a screen that failed to render.
    assert matrix.SetPixel.called


def test_atomic_screen_draws_on_an_offscreen_canvas_and_swaps():
    canvas = Mock(width=64, height=64)
    matrix = Mock(width=64, height=64)
    matrix.CreateFrameCanvas.return_value = canvas
    matrix.SwapOnVSync.return_value = canvas
    screen = Mock(atomic_frames=True)
    manager = ScreenManager(matrix)
    manager.register('static', screen)
    manager.show('static')
    manager.tick({})
    manager.tick({})
    matrix.CreateFrameCanvas.assert_called_once()
    assert screen.render.call_args.args[0] is canvas
    assert matrix.SwapOnVSync.call_count == 2


def test_default_on_exit_clears_and_logs_failures(caplog):
    class Plain(Screen):
        def render(self, matrix, state=None):
            return True
    matrix = Mock()
    Plain().on_exit(matrix)
    matrix.Clear.assert_called_once()
    matrix.Clear.side_effect = RuntimeError('gone')
    Plain().on_exit(matrix)
    assert 'Failed to clear the matrix' in caplog.text


def _cache(tmp_path, **changes):
    snapshot = {'me': {'id': 'u'}, 'totals': {}, 'summaries': [], 'last_updated': 1.0, **changes}
    path = tmp_path / 'cache.json'
    path.write_text(json.dumps({'version': CACHE_VERSION, 'snapshot': snapshot}))
    return path


@pytest.mark.parametrize('changes', [
    {'me': 'not a dict'}, {'celebrated_pr_ids': [1]}, {'celebrated_milestones': ['x']},
    {'weekly_progress': []}, {'last_updated': True}, {'last_updated': None},
    {'instructor_counts': {'Ally': True}}, {'instructor_tally_cursor': 5},
])
def test_damaged_cache_fields_reject_the_cache(tmp_path, changes):
    assert load_snapshot(_cache(tmp_path, **changes)) is None


def test_damaged_instructor_names_drop_the_instructor_tally_so_it_rebuilds(tmp_path):
    snapshot = load_snapshot(_cache(tmp_path, instructor_names={'cody': 5}, instructor_counts={'cody': 1},
                                    instructor_tally_cursor='w1'))
    assert snapshot is not None
    for key in ('instructor_names', 'instructor_counts', 'instructor_tally_cursor'):
        assert key not in snapshot
    assert load_snapshot(_cache(tmp_path, instructor_names={'cody': 'Cody Rigsby'}))['instructor_names'] == {
        'cody': 'Cody Rigsby'}


def test_damaged_optional_tables_are_dropped_not_the_cache(tmp_path):
    snapshot = load_snapshot(_cache(tmp_path, personal_records={'x': 'bad'}, streaks={'current': 'x'},
                                    distance_totals={'cycling': 'far'}, distance_tally_cursor='w'))
    assert snapshot is not None
    for key in ('personal_records', 'streaks', 'distance_totals', 'distance_tally_cursor'):
        assert key not in snapshot


@pytest.mark.parametrize('payload', [[], {'version': 99}, {'version': CACHE_VERSION, 'snapshot': []},
                                     {'version': CACHE_VERSION, 'snapshot': {'summaries': {}, 'totals': {}}}])
def test_wrong_shape_or_version_rejects_the_cache(tmp_path, payload):
    path = tmp_path / 'cache.json'
    path.write_text(json.dumps(payload))
    assert load_snapshot(path) is None
