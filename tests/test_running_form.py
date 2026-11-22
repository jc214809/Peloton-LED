"""The Tread's running-form slide: the figures from the performance graph, the screen's checks on the
cached copy, where the slide sits in the rotation, and how it draws on both board sizes."""

import pytest

from display.display import initialize_fonts
from display.ui.last_workout.charts import _FORM_GREEN, _FORM_TRACK
from display.ui.last_workout.rotation import GRAPH_FRAME_EXTRA_SECONDS, detail_hold_seconds, rotating_details
from display.ui.last_workout.screen import LastWorkoutScreen
from display.ui.last_workout.stats import running_form as checked_form
from peloton.demo import demo_data
from peloton.stats.summaries import running_form, summarize_workout
from scripts.render_demo import ImageMatrix

# Shaped like Joel's first Vision Tread run (2026-11-22, 20 min Walk + Run): walks unscored (None).
FORM = {
    'running_efficiency_score': 69,
    'avg_vertical_ratio_median_pct': 10.46,
    'avg_rate_spm': 145.3125,
    'avg_vertical_displacement_cm': 8.99,
    'avg_stride_length_cm': 172.81238,
    'form_tip': {'copy': 'You were a bit bouncy on your run today.'},
}
SERIES = [None] * 20 + [76, 69, 71, 68] * 5 + [None] * 20 + [84, 74, 67, 70] * 5 + [None] * 10


def tread_perf(form=FORM, series=SERIES):
    perf = {'metrics': [{'slug': 'heart_rate', 'values': [120] * 10}]}
    if form is not None:
        perf['running_form_summary'] = form
    if series is not None:
        perf['metrics'].append({'slug': 'running_efficiency_score', 'values': series})
    return perf


# ---- the figures ---------------------------------------------------------------------------------------------
def test_running_form_takes_the_score_steps_and_stride_in_metres():
    form = running_form(tread_perf())
    assert (form['score'], form['spm'], form['stride_m']) == (69, 145, 1.7)


def test_the_series_keeps_the_walks_as_gaps():
    series = running_form(tread_perf())['series']
    assert len(series) == 60  # 100 samples into one column each across the panel
    assert series[0] is None and series[-1] is None
    assert all(v is None or 60 <= v <= 90 for v in series)
    assert sum(v is not None for v in series) > 20


def test_a_short_series_is_kept_sample_for_sample():
    assert running_form(tread_perf(series=[None, 70, 80]))['series'] == [None, 70, 80]


@pytest.mark.parametrize('series', [None, [], [None, None], [None, 70, None], 'x', [150, 200]])
def test_fewer_than_two_scored_points_is_no_series(series):
    form = running_form(tread_perf(series=series))
    assert form['score'] == 69 and form['series'] == []


@pytest.mark.parametrize(
    'form',
    [
        None,  # any other treadmill, a walk, every other workout
        'bouncy',
        {},
        {'running_efficiency_score': None},
        {'running_efficiency_score': 'high'},
        {'running_efficiency_score': -3},
        {'running_efficiency_score': 101},
        {'running_efficiency_score': True},
    ],
)
def test_no_running_form_without_a_0_to_100_score(form):
    assert running_form(tread_perf(form=form)) is None


def test_missing_steps_or_stride_are_none():
    form = running_form(tread_perf(form={'running_efficiency_score': 55.6, 'avg_rate_spm': 'x', 'avg_stride_length_cm': 0}))
    assert (form['score'], form['spm'], form['stride_m']) == (56, None, None)


def test_the_summary_carries_the_running_form_and_others_have_none():
    data = demo_data()
    by_id = {w['id']: w for w in data['workouts']}
    run = summarize_workout(by_id['demo-running'], data['performance']['demo-running'])
    assert run['running_form']['score'] == 71
    ride = summarize_workout(by_id['demo-cycling'], data['performance']['demo-cycling'])
    assert ride['running_form'] is None


# ---- the screen's checks on the cached copy ------------------------------------------------------------------
@pytest.mark.parametrize('cached', [None, 'x', [], {}, {'score': None}, {'score': 101}, {'score': -1}, {'score': True}, {'score': '69'}])
def test_the_screen_shows_nothing_without_a_good_score(cached):
    assert checked_form({'running_form': cached}) == {}


def test_the_screen_drops_bad_figures_but_keeps_the_score():
    cached = {'score': 69.4, 'spm': -5, 'stride_m': 'long', 'series': [70, 'x', 101, None, True]}
    assert checked_form({'running_form': cached}) == {'score': 69, 'spm': None, 'stride_m': None, 'series': []}
    cached = {'score': 69, 'spm': 145.2, 'stride_m': 1.7, 'series': [70, 'x', 80.4]}
    assert checked_form({'running_form': cached}) == {'score': 69, 'spm': 145, 'stride_m': 1.7, 'series': [70, None, 80]}
    assert checked_form({'running_form': {'score': 69, 'series': 'x'}})['series'] == []


# ---- the rotation --------------------------------------------------------------------------------------------
def tread_run(form=None, discipline='Running'):
    data = demo_data()
    workout = next(w for w in data['workouts'] if w['id'] == 'demo-running')
    summary = summarize_workout(workout, data['performance']['demo-running'])
    summary['discipline'] = discipline
    if form is not None:
        summary['running_form'] = form
    return summary


@pytest.mark.parametrize('height', [32, 64])
def test_the_slide_follows_the_stats_and_only_with_running_form(height):
    kinds = [d.get('kind') for d in rotating_details(tread_run(), height)]
    assert kinds.count('running_form') == 1
    assert kinds[-1] == 'running_form'
    without = tread_run()
    without['running_form'] = None
    assert 'running_form' not in [d.get('kind') for d in rotating_details(without, height)]


def test_the_slide_follows_the_zones():
    summary = tread_run()
    summary['hr_zone_seconds'] = [60, 120, 300, 30, 0]
    kinds = [d.get('kind') for d in rotating_details(summary, 64)]
    assert kinds.index('running_form') == kinds.index('zones') + 1


def test_the_slide_holds_one_second_longer():
    assert detail_hold_seconds({'kind': 'running_form'}, 4) == 4 + GRAPH_FRAME_EXTRA_SECONDS


# ---- drawing -------------------------------------------------------------------------------------------------
class EdgeMatrix(ImageMatrix):
    """Counts lit pixels drawn off the panel (ImageMatrix drops them silently)."""

    def Clear(self):
        super().Clear()
        self.off_panel = 0

    def SetPixel(self, x, y, r, g, b):
        if not (0 <= x < self.width and 0 <= y < self.height) and (r or g or b):
            self.off_panel += 1
        super().SetPixel(x, y, r, g, b)


def render_form(summary, height):
    initialize_fonts(height)
    matrix = EdgeMatrix(height=height)
    details = rotating_details(summary, height)
    turn = [d.get('kind') for d in details].index('running_form')
    screen = LastWorkoutScreen()
    screen.on_enter(matrix, summary)
    screen.update(4 + sum(detail_hold_seconds(d, 4) for d in details[:turn]) + 0.5)
    assert screen.render(matrix, summary)
    assert matrix.off_panel == 0
    return matrix


def lit(matrix, color=None, below=0):
    """Lit pixels, of one colour if given, from row `below` down (the Running header is the same green)."""
    pixels = matrix.image.load()
    return {
        (x, y)
        for x in range(matrix.width)
        for y in range(below, matrix.height)
        if pixels[x, y] != (0, 0, 0) and (color is None or pixels[x, y] == color)
    }


HEART = (220, 20, 20)


def test_64_rows_graph_the_score_with_the_walks_on_a_dim_baseline():
    matrix = render_form(tread_run(), 64)
    green, track = lit(matrix, _FORM_GREEN, below=16), lit(matrix, _FORM_TRACK)
    assert green and track
    baseline = max(y for _, y in green)
    assert {y for _, y in track} == {baseline}
    # The heart-rate row stays under it.
    assert lit(matrix, HEART) and max(y for _, y in green) < min(y for _, y in lit(matrix, HEART))


def test_64_rows_without_a_series_show_the_meter():
    form = {'score': 50, 'spm': 150, 'stride_m': 1.2, 'series': []}
    matrix = render_form(tread_run(form), 64)
    green, track = lit(matrix, _FORM_GREEN, below=16), lit(matrix, _FORM_TRACK)
    assert green and track
    # A 4-row meter, half full.
    assert len({y for _, y in green}) == 4
    assert abs(len({x for x, _ in green}) - len({x for x, _ in green | track}) / 2) <= 1


@pytest.mark.parametrize('score', [0, 69, 100])
def test_32_rows_fill_the_meter_to_the_score(score):
    form = {'score': score, 'spm': 145, 'stride_m': 1.7, 'series': [70, 80]}
    matrix = render_form(tread_run(form), 32)
    green, track = lit(matrix, _FORM_GREEN, below=10), lit(matrix, _FORM_TRACK)
    span = len({x for x, _ in green | track})
    assert len({x for x, _ in green}) == (0 if score == 0 else round((span - 1) * score / 100) + 1)
    # The slide takes the heart-rate bar's rows.
    assert not lit(matrix, HEART)


@pytest.mark.parametrize('height', [32, 64])
@pytest.mark.parametrize('discipline', ['Running', 'Tread Bootcamp', 'Outdoor Running'])
@pytest.mark.parametrize(
    'form',
    [
        {'score': 100, 'spm': 199, 'stride_m': 2.5, 'series': [100 if i % 10 < 7 else None for i in range(60)]},
        {'score': 100, 'spm': 999, 'stride_m': 9.9, 'series': []},
        {'score': 0, 'spm': None, 'stride_m': None, 'series': [0, 0]},
    ],
)
def test_the_largest_figures_stay_on_the_panel_and_in_their_margins(height, discipline, form):
    matrix = render_form(tread_run(form, discipline), height)
    pixels = lit(matrix)
    assert min(x for x, _ in pixels) >= 1 and max(x for x, _ in pixels) <= 62
