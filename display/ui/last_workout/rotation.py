"""What the stats phase cycles through (the rotating details) and how long each one holds."""

from .insight_data import INSIGHT_KINDS, insight_views
from .stats import _stat_details, _tracker_details, running_form, strength_tracker

# Disciplines whose workout page ends with the muscle-groups slide. Peloton sends
# the data for most workouts; it's only shown where the page is light on stats.
MUSCLE_DISCIPLINES = {'strength'}


def rotating_details(summary: dict, matrix_height: int = 64) -> list[dict]:
    """Details the stats phase cycles through, in order.

    64-row panels show the instructor in the intro, so only stats rotate.
    32-row panels have no room for it there, so it leads the rotation.
    The workout graph and heart-rate zone bar close out the rotation when the
    workout recorded them, then the Tread's running form, then a tracked strength class's top lift, or else
    the top muscle groups for MUSCLE_DISCIPLINES.
    """
    details = _stat_details(summary)
    stats = [d for d in details if d['label'] != 'instructor']
    if matrix_height < 64:
        stats = [d for d in details if d['label'] == 'instructor'] + stats
    graph = summary.get('graph')
    if isinstance(graph, dict) and graph.get('values'):
        label = 'output' if graph.get('metric') == 'output' else 'heart rate'
        stats.append({'label': label, 'value': '', 'kind': 'graph'})
    zones = summary.get('hr_zone_seconds')
    if isinstance(zones, list) and len(zones) == 5 and sum(zones) > 0:
        stats.append({'label': 'hr zones', 'value': '', 'kind': 'zones'})
    if running_form(summary):
        stats.append({'label': 'run efficiency', 'value': '', 'kind': 'running_form'})
    tracker = strength_tracker(summary)
    if tracker.get('top'):
        stats.append({'label': 'top lift', 'value': '', 'kind': 'top_lift'})
    # A tracked class has stats enough without the muscles slide, which keeps the page from running long.
    if (
        summary.get('muscles')
        and (summary.get('discipline') or '').strip().lower() in MUSCLE_DISCIPLINES
        and not (tracker.get('top') or _tracker_details(summary))
    ):
        stats.append({'label': 'muscles worked', 'value': '', 'kind': 'muscles'})
    for index, view in enumerate(insight_views(summary)):
        # Workout compare: 64 rows show the card then the bars; 32 rows the bars then the sentence pages.
        # An insight with no figure (an instructor milestone) is words only: one card, or its 64x32 pages.
        bars = view['figure'] is not None
        frames = (
            ['insight_card'] + ['insight_bars'] * bars
            if matrix_height >= 64
            else ['insight_bars'] * bars + ['insight_words'] * len(view['pages32'])
        )
        for page, kind in enumerate(frames):
            detail = {'label': 'insight', 'value': '', 'kind': kind, 'index': index}
            if kind == 'insight_words':
                detail['page'] = page - bars
            stats.append(detail)
    return stats


# Default seconds each intro/stat holds for; overridable via the
# `last_workout_detail_interval` display config key.
LAST_WORKOUT_DETAIL_INTERVAL_SECONDS = 4.0


# The graph, zone-bar, running-form and muscle frames hold this much longer than a stat:
# there's more to read than one number.
GRAPH_FRAME_EXTRA_SECONDS = 1.0


def detail_hold_seconds(detail: dict, interval: float) -> float:
    """Seconds one rotating detail stays up."""
    if interval > 0 and detail.get('kind') in ('graph', 'zones', 'running_form', 'muscles', 'top_lift') + INSIGHT_KINDS:
        return interval + GRAPH_FRAME_EXTRA_SECONDS
    return interval


def stats_phase_seconds(details: list[dict], interval: float) -> float:
    """Seconds for one pass through every rotating detail."""
    return sum(detail_hold_seconds(d, interval) for d in details)


def detail_at(details: list[dict], interval: float, stats_elapsed: float):
    """(index, seconds into it) of the detail showing stats_elapsed seconds
    into the stats phase, wrapping after the last one."""
    remaining = max(0.0, stats_elapsed) % stats_phase_seconds(details, interval)
    for index, detail in enumerate(details):
        hold = detail_hold_seconds(detail, interval)
        if remaining < hold:
            return index, remaining
        remaining -= hold
    return len(details) - 1, remaining  # Float rounding at the very end of a pass.
