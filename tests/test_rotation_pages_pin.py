"""Pins build_rotation_pages: the whole page list (name, state, duration) for a spread of inputs, against
values captured from the code before it was split into one builder per screen (docs/CODE-HEALTH-PLAN.md, 2e).

Regenerate the fixture only for a deliberate change to the pages: PIN_REGEN=1 python -m pytest
tests/test_rotation_pages_pin.py
"""
import copy
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from peloton.config import DEFAULTS
from peloton_led import build_rotation_pages
from scripts.render_rotation import load_snapshot_for

FIXTURE = Path(__file__).parent / 'fixtures' / 'rotation_pages_pin.json'
NOW = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)  # a Wednesday
ALL = ['latest_workouts', 'username', 'streaks', 'versus', 'total_workouts', 'next_milestone', 'lifetime',
       'journey', 'heatmap', 'milestones', 'goals', 'challenges', 'next_class', 'club']
RIVALS = [{'name': 'Joel', 'workouts': 3, 'minutes': 95, 'output_kj': 612},
          {'name': 'Rival', 'workouts': 4, 'minutes': 80, 'output_kj': 540}]


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class StubDashboard:
    """A dashboard with fixed answers: which PRs and milestones are due."""

    def __init__(self, pr=True, milestones=(), disciplines=()):
        self.pr, self.milestones, self.disciplines = pr, list(milestones), list(disciplines)

    def should_celebrate_pr(self, summary):
        return self.pr and bool(summary.get('is_pr'))

    def pending_milestones(self, snapshot):
        return self.milestones

    def pending_discipline_milestones(self, snapshot):
        return self.disciplines


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(time, 'time', lambda: NOW.timestamp())
    monkeypatch.setattr('peloton.goals.datetime', FrozenDatetime)


def _demo(insights=False):
    snapshot = load_snapshot_for(SimpleNamespace(demo=True, insights=insights, config=None))
    snapshot.update(
        streaks={'current_weekly': 3, 'best_weekly': 9, 'current_daily': 12},
        activity_days={'2026-11-17': 30, '2026-11-16': 45, '2026-11-12': 20, '2026-11-01': 60},
        streak_week_workouts=2, weekly_progress={'workouts': 3, 'minutes': 95, 'output_kj': 612})
    return snapshot


def _display(rotation=None, **extra):
    return {**DEFAULTS, 'rotation': list(ALL if rotation is None else rotation), 'color': 'white',
            'timezone': 'America/New_York', 'milestones': [100, 250, 500, 1000, 2000],
            'weekly_goals': {'workouts': 5, 'minutes': 150}, **extra}


def _pr(snapshot):
    snapshot['summaries'] = [{**s, 'is_pr': True, 'workout_id': f'w{i}'} for i, s in enumerate(snapshot['summaries'])]
    return snapshot


def _close_to_target(snapshot, total=2195):
    snapshot['totals'] = {**snapshot['totals'], 'Total Workouts': total}
    return snapshot


def _case(snapshot, dashboard, display, height=64, rivals=None, pass_index=0, username='Joel'):
    return snapshot, dashboard, display, username, height, rivals, pass_index


def _cases():
    """{name: a callable giving fresh build_rotation_pages arguments}."""
    cases = {}
    for height in (64, 32):
        for insights in (False, True):
            cases[f'demo-{height}-insights-{insights}'] = (
                lambda h=height, i=insights: _case(_demo(i), StubDashboard(), _display(), h, RIVALS))
        for screen in ALL:
            cases[f'only-{screen}-{height}'] = (
                lambda h=height, s=screen: _case(_close_to_target(_pr(_demo())), StubDashboard(
                    milestones=[2000], disciplines=['strength:500']), _display([s]), h, RIVALS))
            cases[f'without-{screen}-{height}'] = (
                lambda h=height, s=screen: _case(_close_to_target(_pr(_demo())), StubDashboard(
                    milestones=[2000], disciplines=['strength:500']), _display([n for n in ALL if n != s]),
                    h, RIVALS))
    cases['no-rivals'] = lambda: _case(_demo(), StubDashboard(), _display())
    cases['one-rival'] = lambda: _case(_demo(), StubDashboard(), _display(), rivals=RIVALS[:1])
    cases['rivals-on-32'] = lambda: _case(_demo(), StubDashboard(), _display(['versus']), 32, RIVALS)
    for pass_index in range(4):
        cases[f'pass-{pass_index}'] = (lambda p=pass_index: _case(
            _demo(), StubDashboard(milestones=[100, 500], disciplines=['cycling:100', 'strength:500']),
            _display(), rivals=RIVALS, pass_index=p))
    cases['milestone-only-total'] = lambda: _case(_demo(), StubDashboard(milestones=[100]), _display(['milestones']))
    cases['milestone-only-discipline'] = lambda: _case(
        _demo(), StubDashboard(disciplines=['cycling:100']), _display(['milestones']), 32, pass_index=1)
    cases['milestone-step-only'] = lambda: _case(
        _demo(), StubDashboard(milestones=[2000]), _display(['milestones'], milestones=[], milestone_step=100))
    cases['milestone-not-due'] = lambda: _case(_demo(), StubDashboard(), _display(['milestones']))
    cases['milestone-unconfigured'] = lambda: _case(
        _demo(), StubDashboard(milestones=[100]), _display(['milestones'], milestones=[], milestone_step=0))
    cases['milestone-between-rotation'] = lambda: _case(
        _demo(), StubDashboard(milestones=[100]), _display(['username', 'milestones', 'club']))
    cases['countdown-due'] = lambda: _case(
        _close_to_target(_demo()), StubDashboard(), _display(['next_milestone', 'total_workouts']))
    cases['countdown-due-32'] = lambda: _case(
        _close_to_target(_demo()), StubDashboard(), _display(['next_milestone']), 32)
    cases['countdown-custom-within'] = lambda: _case(
        _close_to_target(_demo(), 2150), StubDashboard(),
        _display(['next_milestone'], milestone_step=100, milestone_within=60, milestone_pages=1))
    cases['countdown-not-due'] = lambda: _case(
        _close_to_target(_demo(), 2123), StubDashboard(), _display(['next_milestone'], milestone_step=100))
    cases['pr-due'] = lambda: _case(_pr(_demo()), StubDashboard(), _display(['latest_workouts']))
    cases['pr-not-due'] = lambda: _case(_pr(_demo()), StubDashboard(pr=False), _display(['latest_workouts']))
    cases['detail-interval'] = lambda: _case(
        _pr(_demo()), StubDashboard(), _display(['latest_workouts'], last_workout_detail_interval=7), 32)
    cases['insights-on-32'] = lambda: _case(_demo(True), StubDashboard(), _display(['latest_workouts']), 32)
    for status in ('login_needed', 'ready', 'loading'):
        cases[f'no-workouts-{status}'] = (lambda s=status: _case(
            {**_demo(), 'summaries': [], 'status': s}, StubDashboard(), _display(['latest_workouts'])))
    cases['empty-snapshot'] = lambda: _case(
        {'me': None, 'totals': {}, 'summaries': [], 'status': 'login_needed'}, StubDashboard(), _display(),
        username='Rider')
    cases['empty-snapshot-32'] = lambda: _case(
        {'totals': {}, 'summaries': [], 'status': 'ready'}, StubDashboard(), _display(), 32, username='Rider')
    cases['partial-snapshot'] = lambda: _case(
        {'me': {'timezone': 'America/Chicago'}, 'totals': {'Cycling': 40}, 'summaries': [], 'status': 'ready',
         'streaks': {'current_weekly': 1}}, StubDashboard(), _display(timezone=None), username='Rider')
    cases['partial-snapshot-junk'] = lambda: _case(
        {'totals': {'Total Workouts': 7}, 'summaries': [], 'status': 'ready', 'challenges': 'junk',
         'booked_classes': 'junk', 'club': 'junk', 'weekly_progress': {}, 'activity_days': {},
         'distance_totals': {}}, StubDashboard(), _display(), username='Rider')
    # Streaks: nothing logged this week late in it risks the streak; a daily-only streak; none at all.
    cases['streak-risk'] = lambda: _case(
        {**_demo(), 'streak_week_workouts': 0}, StubDashboard(), _display(['streaks'], streak_reminder_day=2))
    cases['streak-risk-off'] = lambda: _case(
        {**_demo(), 'streak_week_workouts': 0}, StubDashboard(), _display(['streaks'], streak_reminder_day=None))
    cases['streak-daily-only'] = lambda: _case(
        {**_demo(), 'streaks': {'current_weekly': 0, 'best_weekly': 4, 'current_daily': 5}}, StubDashboard(),
        _display(['streaks']), pass_index=1)
    cases['streak-weekly-only'] = lambda: _case(
        {**_demo(), 'streaks': {'current_weekly': 2, 'best_weekly': 4}}, StubDashboard(), _display(['streaks']), 32,
        pass_index=1)
    cases['streak-none'] = lambda: _case(
        {**_demo(), 'streaks': {'current_weekly': 0}}, StubDashboard(), _display(['streaks']))
    cases['streak-starts-at-peloton-date'] = lambda: _case(
        {**_demo(), 'streaks': {'current_weekly': 2, 'current_daily': 4,
                                'start_date_of_current_daily': 1_700_000_000}},
        StubDashboard(), _display(['streaks']), pass_index=1)
    # Goals, journey, heatmap, lifetime and total on odd inputs.
    cases['goals-zero-and-extra'] = lambda: _case(
        _demo(), StubDashboard(), _display(['goals'], weekly_goals={'workouts': 0, 'minutes': 100,
                                                                   'active_days': 4, 'output_kj': 1000}))
    cases['journey-empty'] = lambda: _case(
        {**_demo(), 'distance_totals': {}}, StubDashboard(), _display(['journey']))
    cases['journey-32-steps'] = lambda: _case(_demo(), StubDashboard(), _display(['journey']), 32)
    cases['journey-long-time'] = lambda: _case(
        _demo(), StubDashboard(), _display(['journey'], screen_durations={'journey': 20}), 32)
    cases['heatmap-empty'] = lambda: _case(
        {**_demo(), 'activity_days': {}}, StubDashboard(), _display(['heatmap']))
    cases['lifetime-and-total-64'] = lambda: _case(
        _demo(), StubDashboard(), _display(['total_workouts', 'lifetime']))
    cases['lifetime-and-total-32'] = lambda: _case(
        _demo(), StubDashboard(), _display(['lifetime', 'total_workouts']), 32)
    cases['no-total'] = lambda: _case(
        {**_demo(), 'totals': {'Cycling': 3}}, StubDashboard(), _display(['total_workouts', 'lifetime']))
    cases['custom-durations'] = lambda: _case(
        _demo(), StubDashboard(), _display(screen_durations={name: 9 for name in ALL}, overview_duration=3,
                                           duration=6), rivals=RIVALS)
    cases['order-reversed'] = lambda: _case(
        _demo(), StubDashboard(milestones=[100]), _display(list(reversed(ALL))), rivals=RIVALS)
    cases['unknown-and-duplicate-screens'] = lambda: _case(
        _demo(), StubDashboard(), _display(['club', 'nonsense', 'club', 'username']))
    cases['empty-rotation'] = lambda: _case(_demo(), StubDashboard(), _display([]), rivals=RIVALS)
    cases['default-rotation'] = lambda: _case(
        _demo(), StubDashboard(), {k: v for k, v in _display().items() if k != 'rotation'}, rivals=RIVALS)
    return cases


def _pages(args):
    snapshot, dashboard, display, username, height, rivals, pass_index = args
    pages = build_rotation_pages(snapshot, dashboard, display, username, height, rivals=rivals,
                                 pass_index=pass_index)
    return json.loads(json.dumps([list(page) for page in pages], default=repr))


def _all_outputs():
    return {name: _pages(make()) for name, make in _cases().items()}


def test_rotation_pages_match_the_pinned_output(frozen):
    got = _all_outputs()
    if os.environ.get('PIN_REGEN'):
        FIXTURE.write_text(json.dumps(got, sort_keys=True, separators=(',', ':')) + '\n')
    expected = json.loads(FIXTURE.read_text())
    assert sorted(got) == sorted(expected)
    for name in got:
        assert got[name] == expected[name], name


def test_the_pinned_cases_cover_every_page_kind(frozen):
    kinds = {page[0] for pages in _all_outputs().values() for page in pages}
    assert kinds >= {'last_workout', 'pr', 'status', 'username', 'streak', 'streak_risk', 'versus', 'discipline',
                     'countdown', 'lifetime', 'journey', 'heatmap', 'goal', 'challenge', 'next_class', 'club',
                     'celebration'}


def test_building_pages_leaves_the_snapshot_alone(frozen):
    snapshot = _demo()
    before = copy.deepcopy(snapshot)
    build_rotation_pages(snapshot, StubDashboard(), _display(), 'Joel', 64, rivals=RIVALS)
    assert snapshot == before
