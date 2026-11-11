"""Workout compare grouping: is_peer, peers, baseline, stat, fill-in, comparison_group (hand-made rows)."""
import copy
import itertools

import pytest

from peloton.workout_compare import (DAY, MAX_PEERS, PLAN_KEYS, baseline, comparison_group, distance,
                                     fill_in, is_peer, peers, standardise, stat)

T = 1_800_000_000
_ids = itertools.count(1)


def row(days=0, **over):
    """A complete 30-minute Music cycling class `days` before T."""
    base = {'id': f'w{next(_ids)}', 'disc': 'cycling', 'start': T - days * DAY, 'dur': 1800,
            'complete': True, 'wtype': 'class', 'ctype': 'Music (Cycling)', 'mode': 'plain',
            'outdoor': False, 'arms_sections': 0, 'plan': None, 'work': {}}
    base.update(over)
    return base


def plan(**over):
    base = {k: 1.0 for k in PLAN_KEYS}
    base.update(over)
    return base


def target(**over):
    return row(0, **over)


# --- is_peer ---------------------------------------------------------------------------------

def test_same_kind_is_peer():
    assert is_peer(target(), row(5))


def test_past_mistake_intervals_arms_and_plain_not_peers():
    a = target(ctype='Intervals', mode='arms')
    b = row(5, ctype='Intervals', mode='plain')
    assert not is_peer(a, b)
    assert not is_peer(b, a)


def test_bike_bootcamp_never_peer_of_ride():
    ride = target()
    boot = row(5, disc='bike_bootcamp', mode='floor')
    assert not is_peer(ride, boot)
    assert not is_peer(boot, ride)
    # even if everything else matches
    assert not is_peer(ride, row(5, disc='bike_bootcamp'))


def test_twenty_vs_thirty_minutes_not_peers():
    assert not is_peer(target(dur=1800), row(5, dur=1200))
    assert not is_peer(target(dur=1200), row(5, dur=1800))


def test_forty_five_vs_sixty_minutes_peers():
    assert is_peer(target(dur=3600), row(5, dur=2700))
    assert is_peer(target(dur=2700), row(5, dur=3600))


def test_exactly_point_seven_is_peer():
    assert is_peer(target(dur=1000), row(5, dur=700))
    assert not is_peer(target(dur=1000), row(5, dur=699))


def test_different_outdoor_not_peers():
    assert not is_peer(target(outdoor=False), row(5, outdoor=True))


def test_different_mode_ctype_disc_not_peers():
    assert not is_peer(target(), row(5, mode='floor'))
    assert not is_peer(target(), row(5, ctype='Intervals'))
    assert not is_peer(target(), row(5, disc='rowing'))


def test_non_class_candidate_not_peer():
    assert not is_peer(target(), row(5, wtype='freestyle'))


def test_incomplete_never_peer():
    assert not is_peer(target(), row(5, complete=False))


def test_itself_never_peer():
    t = target()
    assert not is_peer(t, t)


def test_freestyle_or_untyped_target_has_no_peers():
    assert not is_peer(target(wtype='freestyle'), row(5))
    assert not is_peer(target(ctype=None), row(5, ctype=None))


@pytest.mark.parametrize('which', ['target', 'row'])
def test_zero_duration_has_no_peers(which):
    t = target(dur=0 if which == 'target' else 1800)
    r = row(5, dur=0 if which == 'row' else 1800)
    assert not is_peer(t, r)


# --- rule 4b ---------------------------------------------------------------------------------

def arms(n, days=0, **over):
    return row(days, ctype='Intervals', mode='arms', arms_sections=n, **over)


def test_arms_rides_one_and_two_sections_are_peers():
    assert is_peer(arms(1), arms(2, 5))
    assert is_peer(arms(2), arms(1, 5))
    assert is_peer(arms(2), arms(2, 5))


def test_arms_rides_one_and_three_sections_not_peers():
    assert not is_peer(arms(1), arms(3, 5))
    assert not is_peer(arms(3), arms(1, 5))


def test_missing_arms_sections_counts_as_zero():
    missing = arms(0)
    del missing['arms_sections']
    assert is_peer(missing, arms(1, 5))
    assert not is_peer(missing, arms(2, 5))
    assert is_peer(arms(1), dict(arms(0, 5), arms_sections=None))
    assert not is_peer(arms(2), dict(arms(0, 5), arms_sections=None))


def test_rule_4b_ignores_plain_rides():
    assert is_peer(target(arms_sections=0), row(5, arms_sections=5))


def test_rule_4b_ignores_non_bike_arms():
    a = row(0, disc='rowing', ctype='Row', mode='arms', arms_sections=1)
    b = row(5, disc='rowing', ctype='Row', mode='arms', arms_sections=3)
    assert is_peer(a, b)


def test_rule_4b_applies_to_bike_bootcamp_arms():
    a = row(0, disc='bike_bootcamp', ctype='Bootcamp', mode='arms', arms_sections=1)
    b = row(5, disc='bike_bootcamp', ctype='Bootcamp', mode='arms', arms_sections=3)
    assert not is_peer(a, b)


# --- peers -----------------------------------------------------------------------------------

def test_peers_exclude_later_target_incomplete_and_other_kinds():
    t = target()
    keep = row(3)
    rows = [t, keep, row(-2), row(4, complete=False), row(4, ctype='Intervals'), row(0)]
    assert peers(t, rows) == [keep]


def test_peers_newest_first():
    t = target()
    old, mid, new = row(100), row(50), row(10)
    assert peers(t, [old, new, mid]) == [new, mid, old]


def test_peers_capped_at_max():
    t = target()
    rows = [row(d) for d in range(1, 21)]
    found = peers(t, rows)
    assert len(found) == MAX_PEERS == 12
    assert found == rows[:12]


def test_peers_respect_window():
    t = target()
    inside, outside = row(364), row(366)
    assert peers(t, [inside, outside]) == [inside]
    assert peers(t, [inside, outside], days=730) == [inside, outside]


# --- baseline --------------------------------------------------------------------------------

def test_baseline_five_in_year_stays():
    t = target()
    rows = [row(d) for d in (10, 20, 30, 40, 50)] + [row(d) for d in (400, 500, 600)]
    found, window = baseline(t, rows)
    assert window == 365 and len(found) == 5


def test_baseline_falls_back_to_two_years():
    t = target()
    rows = [row(d) for d in (10, 20, 30)] + [row(d) for d in (400, 450, 500, 550, 600, 650)]
    found, window = baseline(t, rows)
    assert window == 730 and len(found) == 9
    # the spec's example: 3 in 365 and 6 in 730 (not 9)
    rows = [row(d) for d in (10, 20, 30)] + [row(d) for d in (400, 450, 500)]
    found, window = baseline(t, rows)
    assert window == 730 and len(found) == 6


def test_baseline_wider_window_with_nothing_extra_stays():
    t = target()
    rows = [row(d) for d in (10, 20, 30)] + [row(d) for d in (800, 900)]
    found, window = baseline(t, rows)
    assert window == 365 and len(found) == 3


# --- stat ------------------------------------------------------------------------------------

def test_stat_values():
    s = stat(120, [100, 100, 110, 130])
    assert s == {'value': 120, 'median': 105.0, 'n': 4, 'pct': 14.3, 'below': 3}


def test_stat_skips_none_peer_values():
    s = stat(100, [None, 100, None, 80])
    assert s['n'] == 2 and s['median'] == 90.0 and s['below'] == 1


@pytest.mark.parametrize('value,values', [(None, [1, 2]), (5, []), (5, [None, None]), (5, [0, 0])])
def test_stat_none_when_missing_or_zero_median(value, values):
    assert stat(value, values) is None


# --- standardise / distance ------------------------------------------------------------------

def test_standardise_is_z_score_with_equal_weights():
    z = standardise([{'a': 0}, {'a': 2}], keys=('a', 'b'))
    assert z[0]['a'] == -1.0 and z[1]['a'] == 1.0


def test_standardise_zero_spread_uses_one_and_missing_is_zero():
    z = standardise([{'a': 5}, {'a': 5}, {}], keys=('a', 'b'))
    # a: values 5, 5, 0 -> mean 10/3, spread nonzero; b: all missing -> all zeros
    assert all(item['b'] == 0.0 for item in z)
    z = standardise([{'a': 4}, {'a': 4}], keys=('a',))
    assert z == [{'a': 0.0}, {'a': 0.0}]
    z = standardise([{'a': 2}, {'a': 4}, {'a': None}], keys=('a',))
    assert z[2]['a'] < z[0]['a'] < z[1]['a']


def test_distance_identical_plans_zero_and_rms():
    z = standardise([plan(), plan()])
    assert distance(z[0], z[1]) == 0
    assert distance({'a': 0, 'b': 0}, {'a': 3, 'b': 4}, keys=('a', 'b')) == pytest.approx((25 / 2) ** 0.5)


# --- fill_in ---------------------------------------------------------------------------------

def real_peers(n, days=10):
    return [row(days + i, plan=plan()) for i in range(n)]


def candidate(days, off, **over):
    """A different-ctype class whose plan is `off` away from the target's in effort_share."""
    over.setdefault('ctype', 'Intervals')
    return row(days, plan=plan(effort_share=1.0 + off), **over)


def test_fill_in_adds_two_nearest_flagged_copies():
    t = target(plan=plan())
    real = real_peers(3)
    near, nearer, far, farthest = candidate(20, 0.2), candidate(21, 0.1), candidate(22, 3), candidate(23, 5)
    rows = [t] + real + [far, near, farthest, nearer]
    snapshot = copy.deepcopy(rows)
    filled = fill_in(t, rows, real)
    assert [f['id'] for f in filled] == [nearer['id'], near['id']]
    assert all(f['fill_in'] is True for f in filled)
    assert rows == snapshot
    assert 'fill_in' not in nearer
    assert filled[0] is not nearer


@pytest.mark.parametrize('n', [0, 1, 5, 6])
def test_fill_in_not_applied_outside_two_to_four_real(n):
    t = target(plan=plan())
    real = real_peers(n)
    assert fill_in(t, [t] + real + [candidate(20, 0.1)], real) == []


def test_fill_in_needs_target_plan():
    t = target(plan=None)
    real = real_peers(3)
    assert fill_in(t, [t] + real + [candidate(20, 0.1)], real) == []


def test_fill_in_not_for_non_bike():
    t = row(0, disc='rowing', ctype='Row', plan=plan())
    real = [row(10 + i, disc='rowing', ctype='Row', plan=plan()) for i in range(3)]
    extra = row(20, disc='rowing', ctype='Pop', plan=plan())
    assert fill_in(t, [t] + real + [extra], real) == []


def test_fill_in_bike_bootcamp_is_eligible_but_only_own_disc():
    t = row(0, disc='bike_bootcamp', mode='floor', ctype='Bootcamp', plan=plan())
    real = [row(10 + i, disc='bike_bootcamp', mode='floor', ctype='Bootcamp', plan=plan()) for i in range(3)]
    ride = row(20, plan=plan())
    boot = row(21, disc='bike_bootcamp', mode='floor', ctype='Other', plan=plan())
    filled = fill_in(t, [t] + real + [ride, boot], real)
    assert [f['id'] for f in filled] == [boot['id']]


def test_fill_in_candidate_filters():
    t = target(plan=plan())
    real = real_peers(3)
    good = candidate(20, 0.5)
    bad = [
        candidate(-3, 0),                          # later than the target
        candidate(731, 0),                         # outside 730 days
        candidate(20, 0, complete=False),
        row(20, plan=None, ctype='Intervals'),     # no plan
        candidate(20, 0, disc='rowing'),
        candidate(20, 0, wtype='freestyle'),
        candidate(20, 0, mode='arms'),
        candidate(20, 0, dur=1200),                # 0.67 of the target
        dict(candidate(20, 0), id=t['id']),        # the target itself
        dict(real[0], ctype='Intervals'),          # already a real peer (same id)
    ]
    filled = fill_in(t, [t] + real + [good] + bad, real)
    assert [f['id'] for f in filled] == [good['id']]


def test_fill_in_accepts_same_ctype_candidate_not_already_peer():
    # a same-ctype class that is not in `real` (e.g. beyond the 12 cap or window) still qualifies
    t = target(plan=plan())
    real = real_peers(2)
    same = candidate(20, 0.1, ctype='Music (Cycling)')
    filled = fill_in(t, [t] + real + [same], real)
    assert [f['id'] for f in filled] == [same['id']]


def test_fill_in_returns_fewer_when_few_candidates():
    t = target(plan=plan())
    real = real_peers(2)
    only = candidate(20, 0.1)
    filled = fill_in(t, [t] + real + [only], real)
    assert [f['id'] for f in filled] == [only['id']]


def test_fill_in_no_candidates():
    t = target(plan=plan())
    real = real_peers(3)
    assert fill_in(t, [t] + real, real) == []


def test_fill_in_distance_tie_prefers_newer():
    t = target(plan=plan())
    real = real_peers(4)
    older, newer = candidate(40, 0.5), candidate(30, 0.5)
    filled = fill_in(t, [t] + real + [older, newer], real)
    assert [f['id'] for f in filled] == [newer['id']]


# --- comparison_group ------------------------------------------------------------------------

def test_comparison_group_peers_plus_fill_in():
    t = target(plan=plan())
    real = real_peers(3)
    near, nearer = candidate(20, 0.2), candidate(21, 0.1)
    group, window, n_real = comparison_group(t, [t] + real + [near, nearer])
    assert window == 365 and n_real == 3
    assert [g['id'] for g in group[:3]] == [r['id'] for r in real]
    assert [g['id'] for g in group[3:]] == [nearer['id'], near['id']]
    assert [bool(g.get('fill_in')) for g in group] == [False] * 3 + [True] * 2


def test_comparison_group_uses_fallback_window():
    t = target(plan=plan())
    rows = [row(d, plan=plan()) for d in (10, 400, 450, 500, 550, 600)]
    group, window, n_real = comparison_group(t, rows)
    assert window == 730 and n_real == 6 == len(group)


def test_comparison_group_without_fill_in():
    t = target()
    rows = [row(d) for d in range(1, 8)]
    group, window, n_real = comparison_group(t, rows)
    assert (len(group), window, n_real) == (7, 365, 7)
