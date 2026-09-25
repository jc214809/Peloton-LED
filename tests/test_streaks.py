"""Weekly streak screen and the streak data behind it."""
from unittest.mock import Mock

import pytest

from display.display import initialize_fonts
from display.ui.streak_screen import FLAME_COLORS, StreakScreen, streak_lines
from peloton.cache import load_snapshot, save_snapshot
from peloton.config import load_config
from peloton.totals import parse_streaks
from peloton_led import build_rotation_pages
from scripts.render_demo import ImageMatrix


def test_parse_streaks_keeps_only_whole_non_negative_counts():
    overview = {'streaks': {'current_weekly': 2, 'best_weekly': 74, 'current_daily': 0,
                            'start_date_of_current_weekly': 1789410461}}
    assert parse_streaks(overview) == {'current_weekly': 2, 'best_weekly': 74, 'current_daily': 0}
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
@pytest.mark.parametrize('streaks', [{'current_weekly': 2, 'best_weekly': 74},
                                     {'current_weekly': 1234, 'best_weekly': 1500}])
def test_streak_screen_fits_the_panel(height, streaks):
    matrix = ImageMatrix(height=height)
    initialize_fonts(height)
    assert StreakScreen().render(matrix, streaks)
    found = {c for _, c in matrix.image.getcolors(64 * 64)}
    assert set(FLAME_COLORS.values()) <= found
    # Nothing is drawn in the 1-px side margins, so no text ran off the edge.
    pixels = matrix.image.load()
    assert all(pixels[x, y] == (0, 0, 0) for x in (0, 63) for y in range(height))


def test_streak_screen_renders_nothing_without_a_streak():
    matrix = ImageMatrix(height=64)
    initialize_fonts(64)
    assert not StreakScreen().render(matrix, {'current_weekly': 0})


def test_rotation_includes_streaks_only_when_there_is_one():
    display = {'rotation': ['streaks'], 'last_workout_duration': 15, 'overview_duration': 4,
               'screen_durations': {'streaks': 6}}
    snapshot = {'summaries': [], 'totals': {}, 'status': 'ready',
                'streaks': {'current_weekly': 3, 'best_weekly': 9}}
    assert build_rotation_pages(snapshot, Mock(), display, 'R', 64) == [
        ('streak', {'current_weekly': 3, 'best_weekly': 9}, 6)]
    snapshot['streaks'] = {'current_weekly': 0}
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
