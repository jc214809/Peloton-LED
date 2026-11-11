"""Workout compare insights: every rule of spec section 5 on hand-made rows, each threshold just under and over."""
import itertools

import pytest

from peloton import workout_compare as compare
from peloton.insight_lines import number
from peloton.workout_insights import insights, strength_insights

T = 1_800_000_000
DAY = 86400
_ids = itertools.count(1)
PLAN = {k: float(i + 1) for i, k in enumerate(compare.PLAN_KEYS)}


def ride(days_ago, output, hr=None, eff=None, strive=None, **over):
    row = {'id': f'w{next(_ids)}', 'start': T - days_ago * DAY, 'disc': 'cycling', 'wtype': 'class',
           'ctype': 'Music', 'mode': 'plain', 'outdoor': False, 'dur': 1200, 'complete': True,
           'work': {'output': output, 'heart_rate': hr}, 'eff': eff, 'strive': strive,
           'target_under': None, 'pace_fit': None, 'sets': None, 'plan': None, 'arms_sections': 0}
    row.update(over)
    return row


def foot(days_ago, speed, hr=None, eff=None, **over):
    over.setdefault('disc', 'running')
    return ride(days_ago, None, hr=hr, eff=eff, work={'speed': speed, 'heart_rate': hr}, **over)


def peers_of(outputs, first_day=1, **kw):
    return [ride(first_day + i, o, **kw) for i, o in enumerate(outputs)]


def st(name, cat, lb, done, target, type='rep_counting', hold=False):
    return {'name': name, 'cat': cat, 'lb': lb, 'done': done, 'target': target, 'type': type, 'hold': hold}


def strength(days_ago, sets, **over):
    base = {'disc': 'strength', 'ctype': 'Full Body', 'work': {}, 'sets': sets}
    base.update(over)
    return ride(days_ago, None, **base)


def history(lbs, days=(10, 20, 30), name='Row', cat='heavy', done=10, target=10):
    return [strength(d, [st(name, cat, lb, done, target)]) for d, lb in zip(days, lbs)]


def codes(result):
    return [c for c, *_ in result]


def pairs(result):
    return [(c, t) for c, t, _ in result]


def text(result, code):
    return {c: t for c, t, _ in result}[code]


def run_bike(target_output, peer_outputs, **target_kw):
    target = ride(0, target_output, **target_kw)
    return insights(target, [target] + peers_of(peer_outputs))


# 5.1 output against peers

def test_output_down_at_minus_10_with_wording():
    result = run_bike(90, [100] * 5)
    assert codes(result) == ['output_down']
    assert text(result, 'output_down') == ('Your output was down today: 90 W in the work segments against '
                                            'your usual 100 W for rides like this.')


def test_output_just_inside_minus_10_is_in_line():
    result = run_bike(90.1, [100] * 5)
    assert codes(result) == ['in_line']
    assert text(result, 'in_line').startswith('Good ride, right in line with your other rides like it')
    assert '(90 W against a usual 100 W)' in text(result, 'in_line')


def test_big_drop_without_rank_is_a_normal_ride():
    # -12% but the target beats 2 of 5 peers (40%)
    result = run_bike(88, [80, 85, 100, 100, 100])
    assert codes(result) == ['in_line']
    assert text(result, 'in_line') == ('A normal ride for you: 88 W in the work segments against your '
                                        'usual 100 W, inside your usual range.')


def test_output_down_when_target_beats_exactly_20_percent():
    assert codes(run_bike(88, [80, 100, 100, 100, 100])) == ['output_down']


def test_output_up_needs_80_percent_beaten():
    result = run_bike(110, [100, 100, 100, 100, 120])  # beats 4 of 5 = 80%, +10%
    assert codes(result) == ['output_up']
    assert text(result, 'output_up') == ('Strong ride: 110 W in the work segments against your usual '
                                         '100 W for rides like this.')


def test_big_rise_without_rank_is_a_normal_ride():
    result = run_bike(112, [100, 100, 100, 120, 120])  # beats 3 of 5
    assert codes(result) == ['in_line']
    assert text(result, 'in_line').startswith('A normal ride for you')


def test_output_just_under_plus_10_is_in_line():
    result = run_bike(109.9, [100] * 5)
    assert codes(result) == ['in_line']


def test_fewer_than_five_peers_with_output_gives_no_output_message():
    target = ride(0, 50)
    rows = [target] + peers_of([100] * 4) + [ride(9, None)]  # 5 peers, only 4 with output
    assert codes(insights(target, rows)) == ['nothing']


def test_target_without_output_has_no_output_message():
    target = ride(0, None)
    assert codes(insights(target, [target] + peers_of([100] * 5))) == ['nothing']


def test_nothing_with_five_peers_names_count():
    target = ride(0, None)
    assert pairs(insights(target, [target] + peers_of([100] * 5))) == [
        ('nothing', 'Nothing stood out against your 5 similar rides.')]


# easier effort / cost more clauses

def easy_down(heart_pct_hr, eff, peer_hr=None, peer_eff=None, n_hr=5):
    peers = [ride(i + 1, 100, hr=(100 if i < n_hr else None) if peer_hr is None else peer_hr,
                  eff=100 if peer_eff is None else peer_eff) for i in range(5)]
    target = ride(0, 90, hr=heart_pct_hr, eff=eff)
    return insights(target, [target] + peers)


def test_easier_effort_clause_at_minus_4():
    result = easy_down(96, 100)
    assert codes(result) == ['output_down']
    assert text(result, 'output_down').endswith(' Your heart rate was lower too, so it looks like an easier effort.')


def test_easier_effort_clause_not_at_minus_3_9():
    assert text(easy_down(96.1, 100), 'output_down').endswith('for rides like this.')


def test_cost_more_clause_at_eff_minus_8():
    result = easy_down(100, 92)
    assert text(result, 'output_down').endswith(' Your heart rate was not lower, so the same work cost you more.')


def test_cost_more_clause_not_at_eff_minus_7_9():
    assert text(easy_down(100, 92.1), 'output_down').endswith('for rides like this.')


def test_cost_clause_only_when_heart_clause_did_not_fire():
    out = text(easy_down(90, 80), 'output_down')
    assert 'easier effort' in out and 'cost you more' not in out


def test_no_clause_with_fewer_than_five_peers_with_heart_rate():
    assert text(easy_down(90, 80, n_hr=4), 'output_down').endswith('for rides like this.')


def test_no_clause_with_fewer_than_five_peers_with_eff():
    peers = [ride(i + 1, 100, hr=100, eff=100 if i < 4 else None) for i in range(5)]
    target = ride(0, 90, hr=96, eff=80)
    assert text(insights(target, [target] + peers), 'output_down').endswith('for rides like this.')


def test_no_clause_when_target_has_no_heart_rate():
    peers = [ride(i + 1, 100, hr=100, eff=100) for i in range(5)]
    target = ride(0, 90)
    assert text(insights(target, [target] + peers), 'output_down').endswith('for rides like this.')


def test_efficient_clause_at_eff_plus_8():
    peers = peers_of([100, 100, 100, 100, 120], hr=100, eff=100)
    target = ride(0, 110, hr=100, eff=108)
    assert text(insights(target, [target] + peers), 'output_up').endswith(' You got more out of every heartbeat than usual.')


def test_efficient_clause_not_at_eff_plus_7_9():
    peers = peers_of([100, 100, 100, 100, 120], hr=100, eff=100)
    target = ride(0, 110, hr=100, eff=107.9)
    assert text(insights(target, [target] + peers), 'output_up').endswith('for rides like this.')


def test_foot_discipline_uses_pace_wording_and_mph():
    target = foot(0, 3.6)
    result = insights(target, [target] + [foot(i, 4.0) for i in range(1, 6)])
    assert text(result, 'output_down') == ('Your pace was down today: 3.6 mph in the work segments against '
                                           'your usual 4.0 mph for runs like this.')


def test_walking_and_bootcamp_nouns():
    target = foot(0, 3.6, disc='walking')
    result = insights(target, [target] + [foot(i, 3.6, disc='walking') for i in range(1, 6)])
    assert text(result, 'in_line').startswith('Good walk,')
    target = ride(0, 100, disc='row_bootcamp')
    result = insights(target, [target] + peers_of([100] * 5, disc='row_bootcamp'))
    assert text(result, 'in_line').startswith('Good bootcamp,')


# 5.2 callouts (no peers: the callout message is the only one, so no too_few)

@pytest.mark.parametrize('disc', ['cycling', 'bike_bootcamp'])
def test_resistance_low_at_25_not_24(disc):
    on = ride(0, 100, disc=disc, target_under={'resistance': 25})
    assert pairs(insights(on, [on])) == [('resistance_low', 'Turn the resistance up in the work segments: you were '
                                                     'under the callout range 25% of the time.')]
    off = ride(0, 100, disc=disc, target_under={'resistance': 24})
    assert codes(insights(off, [off])) == ['too_few']


@pytest.mark.parametrize('disc', ['cycling', 'bike_bootcamp'])
def test_cadence_low_at_35_not_34(disc):
    on = ride(0, 100, disc=disc, target_under={'cadence': 35})
    assert pairs(insights(on, [on])) == [('cadence_low', 'Pick the cadence up in the work segments: you were under '
                                                  'the callout range 35% of the time.')]
    off = ride(0, 100, disc=disc, target_under={'cadence': 34})
    assert codes(insights(off, [off])) == ['too_few']


def test_both_bike_callouts_in_order():
    t = ride(0, 100, target_under={'cadence': 50, 'resistance': 50})
    assert codes(insights(t, [t])) == ['resistance_low', 'cadence_low']


def test_bike_callouts_not_for_rowing():
    t = ride(0, 100, disc='rowing', target_under={'cadence': 90, 'resistance': 90})
    assert codes(insights(t, [t])) == ['too_few']


@pytest.mark.parametrize('disc', ['rowing', 'row_bootcamp', 'running'])
def test_pace_low_at_35_not_34(disc):
    on = ride(0, 100, disc=disc, pace_fit=(35, 40))
    assert pairs(insights(on, [on])) == [('pace_low', 'You were under the pace target 35% of the time: push the '
                                               'pace, or drop a pace level if that target is too fast.')]
    off = ride(0, 100, disc=disc, pace_fit=(34, 40))
    assert codes(insights(off, [off])) == ['too_few']


@pytest.mark.parametrize('disc', ['walking', 'tread_bootcamp'])
def test_pace_low_never_for_walking_or_tread_bootcamp(disc):
    t = ride(0, 100, disc=disc, pace_fit=(90, 5))
    assert codes(insights(t, [t])) == ['too_few']


def test_pace_fit_without_share_is_silent():
    t = ride(0, 100, disc='running', pace_fit=(None, 5))
    assert codes(insights(t, [t])) == ['too_few']


def test_no_callout_data_is_silent():
    t = ride(0, 100)
    assert codes(insights(t, [t])) == ['too_few']


# 5.3 strength

def missed_case(missed, total):
    sets = [st('Row', 'other', 20, 5, 10) for _ in range(missed)]
    sets += [st('Curl', 'other', 20, 10, 10) for _ in range(total - missed)]
    return strength(0, sets)


@pytest.mark.parametrize('missed, total, fires', [(2, 8, True), (1, 4, False), (2, 9, False), (3, 9, True)])
def test_missed_targets_threshold(missed, total, fires):
    t = missed_case(missed, total)
    assert (codes(strength_insights(t, [t])) == ['missed_targets']) is fires


def test_missed_targets_wording_names_worst_movement():
    sets = [st('Row', 'other', 20, 5, 10)] * 2 + [st('Curl', 'other', 20, 5, 10)] + [st('Curl', 'other', 20, 10, 10)] * 5
    t = strength(0, sets)
    assert pairs(strength_insights(t, [t])) == [('missed_targets', 'You came up short on 3 of 8 sets, mostly Row: '
                                                            'drop a weight there next time.')]


def test_rounds_holds_and_unweighted_sets_never_count():
    sets = [st('Row', 'other', 20, 1, 10, type='rounds')] * 4
    sets += [st('Plank', 'other', 20, 1, 10, hold=True)] * 4
    sets += [st('Push', 'other', 0, 1, 10)] * 4 + [st('Push', 'other', None, 1, 10)] * 4
    sets += [st('NoTarget', 'other', 20, 1, 0), st('NoDone', 'other', 20, None, 10)]
    sets += [st('Warm', 'other', 20, 1, 10, type='time_tracked_rep')]
    sets += [st('Curl', 'other', 20, 10, 10)] * 2
    t = strength(0, sets)
    assert pairs(strength_insights(t, [t])) == []


def test_rounds_never_count_for_weights():
    old = [strength(d, [st('Row', 'heavy', 40, 10, 10)]) for d in (10, 20, 30)]
    t = strength(0, [st('Row', 'heavy', 35, 200, 10, type='rounds')])
    assert pairs(strength_insights(t, old + [t])) == []


def test_no_tracker_when_no_sets():
    for sets in (None, []):
        t = strength(0, sets)
        assert pairs(strength_insights(t, [t])) == [
            ('no_tracker', 'No rep or weight data for this class, so only heart rate can be compared.')]


def test_strength_insights_ignores_other_disciplines():
    t = ride(0, 100)
    assert pairs(strength_insights(t, [t])) == []


def lighter(today_lb=35, done=120, target=100, earlier=(40, 40, 40), days=(10, 20, 30)):
    rows = [strength(d, [st(f'Old{d}', 'heavy', lb, 10, 10)]) for d, lb in zip(days, earlier)]
    t = strength(0, [st('Row', 'heavy', today_lb, done, target)])
    return strength_insights(t, rows + [t])


def test_go_up_lighter_fires_at_ratio_1_2():
    assert pairs(lighter()) == [('go_up_lighter', 'Go up a weight on Row next time: 35 lb today against your usual 40 lb '
                                           'for heavy weights, and you beat the rep targets by 20%.')]


def test_go_up_lighter_not_at_ratio_1_19():
    assert lighter(done=119) == []


def test_go_up_lighter_not_at_only_4_lb_under():
    assert lighter(today_lb=36) == []


def test_go_up_lighter_not_when_one_set_under_target():
    rows = history((40, 40, 40))
    t = strength(0, [st('Row', 'heavy', 35, 200, 100), st('Row', 'heavy', 35, 99, 100)])
    assert pairs(strength_insights(t, rows + [t])) == []


def test_no_weight_message_with_two_earlier_classes():
    assert lighter(earlier=(40, 40), days=(10, 20)) == []


def test_category_history_older_than_a_year_is_not_counted():
    rows = history((40, 40), days=(10, 20)) + [strength(400, [st('Squat', 'heavy', 40, 10, 10)])]
    t = strength(0, [st('Row', 'heavy', 35, 120, 100)])
    assert pairs(strength_insights(t, rows + [t])) == []


def test_movement_history_reaches_back_two_years():
    rows = history((40, 40, 40), days=(10, 400, 500))
    t = strength(0, [st('Row', 'heavy', 35, 120, 100)])
    result = strength_insights(t, rows + [t])
    assert codes(result) == ['go_up_lighter'] and 'on that movement' in result[0][1]


def test_incomplete_and_later_classes_are_not_history():
    rows = history((40, 40, 40))
    rows[0]['complete'] = False
    rows[1]['start'] = T + DAY
    rows.append(strength(5, None))
    t = strength(0, [st('Row', 'heavy', 35, 120, 100)])
    assert pairs(strength_insights(t, rows + [t])) == []


def test_movement_first_uses_its_own_usual():
    rows = [strength(d, [st('Row', 'heavy', 40, 10, 10), st('Press', 'heavy', 60, 10, 10)]) for d in (10, 20, 30)]
    t = strength(0, [st('Row', 'heavy', 35, 120, 100)])
    result = strength_insights(t, rows + [t])
    assert pairs(result) == [('go_up_lighter', 'Go up a weight on Row next time: 35 lb today against your usual 40 lb '
                                        'on that movement, and you beat the rep targets by 20%.')]


def test_movement_never_mixed_across_categories():
    rows = [strength(d, [st('Row', 'light', 10, 10, 10)]) for d in (10, 20, 30)]
    t = strength(0, [st('Row', 'heavy', 35, 10, 10)])
    assert pairs(strength_insights(t, rows + [t])) == []


def test_movement_with_two_classes_falls_back_to_category():
    rows = [strength(10, [st('Row', 'heavy', 40, 10, 10)]), strength(20, [st('Row', 'heavy', 40, 10, 10)]),
            strength(30, [st('Press', 'heavy', 40, 10, 10)])]
    t = strength(0, [st('Row', 'heavy', 35, 120, 100)])
    result = strength_insights(t, rows + [t])
    assert 'for heavy weights' in result[0][1] and 'on that movement' not in result[0][1]


def test_movement_chosen_is_most_reps_among_those_with_history():
    rows = [strength(d, [st('Row', 'heavy', 40, 10, 10), st('Press', 'heavy', 45, 10, 10)]) for d in (10, 20, 30)]
    t = strength(0, [st('Curl', 'heavy', 35, 90, 10), st('Row', 'heavy', 35, 120, 100), st('Press', 'heavy', 40, 200, 160)])
    # Curl has the most reps but no history of its own; Press beats Row on reps
    result = strength_insights(t, rows + [t])
    assert codes(result) == ['go_up_lighter']
    assert result[0][1].startswith('Go up a weight on Press next time: 40 lb today against your usual 45 lb on that movement')


def streak_rows(lbs=(40, 35), done=12, days=(10, 20)):
    return [strength(d, [st('Row', 'heavy', lb, done, 10)]) for d, lb in zip(days, lbs)]


def test_go_up_streak_fires_and_skips_classes_without_the_category():
    rows = streak_rows() + [strength(15, [st('Curl', 'light', 10, 10, 10)])]
    t = strength(0, [st('Row', 'heavy', 40, 12, 10)])
    assert pairs(strength_insights(t, rows + [t])) == [
        ('go_up_streak', 'Go up from 40 lb on your heavy weights next time: 3 classes in a row you beat every '
                         'rep target by 20% or more.')]


def test_go_up_streak_broken_by_a_heavier_class():
    rows = streak_rows(lbs=(50, 40))
    t = strength(0, [st('Row', 'heavy', 40, 12, 10)])
    assert pairs(strength_insights(t, rows + [t])) == []


def test_go_up_streak_needs_ratio_in_every_class():
    t = strength(0, [st('Row', 'heavy', 40, 12, 10)])
    assert pairs(strength_insights(t, streak_rows(done=11) + [t])) == []
    assert pairs(strength_insights(strength(0, [st('Row', 'heavy', 40, 11, 10)]), [])) == []


def test_go_up_streak_needs_every_target_hit():
    rows = streak_rows()
    rows[0]['sets'].append(st('Row', 'heavy', 40, 9, 10))
    t = strength(0, [st('Row', 'heavy', 40, 12, 10)])
    assert pairs(strength_insights(t, rows + [t])) == []


def test_go_up_streak_with_only_two_classes_in_all():
    t = strength(0, [st('Row', 'heavy', 40, 12, 10)])
    assert pairs(strength_insights(t, streak_rows(lbs=(40,), days=(10,)) + [t])) == []


def test_go_up_streak_suppressed_when_go_up_lighter_fired():
    recent = streak_rows(lbs=(30, 30))
    old = history((50, 50, 50), days=(400, 450, 500))
    t = strength(0, [st('Row', 'heavy', 35, 12, 10)])
    assert codes(strength_insights(t, recent + old + [t])) == ['go_up_lighter']
    assert codes(strength_insights(t, recent + [t])) == ['go_up_streak']


def heavier(today_lb=45, sets=None):
    rows = history((40, 40, 40))
    t = strength(0, sets or [st('Row', 'heavy', today_lb, 10, 10)])
    return strength_insights(t, rows + [t])


def test_went_heavier_at_plus_5():
    assert pairs(heavier()) == [('went_heavier', 'You went heavier on Row (45 lb against your usual 40 lb on '
                                          'that movement) and still hit every target. Keep that weight.')]


def test_went_heavier_category_wording():
    rows = [strength(d, [st(n, 'heavy', 40, 10, 10)]) for d, n in ((10, 'A'), (20, 'B'), (30, 'C'))]
    t = strength(0, [st('Row', 'heavy', 45, 10, 10)])
    assert strength_insights(t, rows + [t])[0][1].startswith('You went heavier on your heavy weights (45 lb against '
                                                              'your usual 40 lb for heavy weights)')


def test_went_heavier_not_at_plus_4():
    assert heavier(44) == []


def test_went_heavier_not_with_a_missed_set():
    assert heavier(sets=[st('Row', 'heavy', 45, 10, 10), st('Row', 'heavy', 45, 9, 10)]) == []


# 5.4 effort

def effort(target_strive, peer_strives, output=100, peer_output=100, **kw):
    target = ride(0, output, strive=target_strive)
    peers = [ride(i + 1, peer_output, strive=s) for i, s in enumerate(peer_strives)]
    return insights(target, [target] + peers + kw.get('extra', []))


def test_effort_high_with_in_line():
    result = effort(20, [10, 11, 12, 13, 14])
    assert pairs(result) == [('in_line', text(result, 'in_line')),
                      ('effort_high', 'Hardest ride of this kind by heart rate in your last 5: Strive 20.0.')]


def test_effort_low():
    result = effort(5, [10, 11, 12, 13, 14])
    assert codes(result) == ['in_line', 'effort_low']
    assert text(result, 'effort_low') == 'Easiest ride of this kind by heart rate in your last 5: Strive 5.0.'


def test_effort_in_the_middle_says_nothing():
    assert codes(effort(12, [10, 11, 12, 13, 14])) == ['in_line']


def test_effort_not_shown_with_output_down_or_up():
    assert codes(effort(20, [10, 11, 12, 13, 14], output=90)) == ['output_down']
    assert codes(effort(20, [10, 11, 12, 13, 14], output=120, peer_output=100)) == ['output_up']


def test_effort_shown_with_nothing_else():
    target = ride(0, None, strive=20)
    result = insights(target, [target] + [ride(i, 100, strive=10) for i in range(1, 6)])
    assert codes(result) == ['effort_high']


def test_effort_needs_five_peers_with_strive():
    assert codes(effort(20, [10, 11, 12, 13])) == ['too_few']
    target = ride(0, 100, strive=20)
    rows = peers_of([100] * 5, strive=None)[:1] + [ride(i, 100, strive=10) for i in range(2, 6)]
    assert codes(insights(target, [target] + rows)) == ['in_line']


def test_no_heart_rate_gives_no_effort_message():
    assert codes(effort(None, [10, 11, 12, 13, 14])) == ['in_line']
    assert codes(effort(0, [10, 11, 12, 13, 14])) == ['in_line']
    target = ride(0, 100, strive=5, dur=0)
    assert codes(insights(target, [target])) == ['too_few']


def test_peers_without_duration_or_strive_are_skipped_in_effort():
    target = ride(0, 100, strive=20)
    odd = [ride(1, 100, strive=0), ride(2, 100, strive=None)]
    rows = odd + [ride(i, 100, strive=10) for i in range(3, 8)]
    assert codes(insights(target, [target] + rows)) == ['in_line', 'effort_high']


def test_effort_strength_without_tracker_still_compares_heart_rate():
    # 5 peers with strive, no sets on the target: no_tracker and effort_high
    target = strength(0, None, strive=20)
    rows = [strength(i, None, strive=10) for i in range(1, 6)]
    assert codes(insights(target, [target] + rows)) == ['no_tracker', 'effort_high']


# 4.1 fill-in

def fill_rows(outputs, first_day=100):
    return [ride(first_day + i, o, ctype='Other', plan=dict(PLAN)) for i, o in enumerate(outputs)]


def fill_case(target_output, real, fills, **target_kw):
    target = ride(0, target_output, plan=dict(PLAN), **target_kw)
    real_rows = peers_of(real, plan=dict(PLAN))
    return target, [target] + real_rows + fill_rows(fills)


def test_fill_in_wording_with_three_real_peers():
    target, rows = fill_case(80, [100] * 3, [100] * 2)
    result = insights(target, rows)
    assert codes(result) == ['output_down']
    assert text(result, 'output_down') == ('Your output was down today: 80 W in the work segments against your '
                                           'usual 100 W for the closest rides you have (only 3 of this exact kind).')


def test_fill_in_in_line_wording():
    target, rows = fill_case(100, [100] * 3, [100] * 2)
    assert text(insights(target, rows), 'in_line') == (
        'Good ride, right in line with the closest rides you have (only 3 of this exact kind): 100 W against a usual 100 W.')


def test_fill_in_output_up_needs_real_peers_to_agree():
    target, rows = fill_case(150, [100] * 3, [100] * 2)
    result = insights(target, rows)
    assert codes(result) == ['output_up']
    assert 'for the closest rides you have (only 3 of this exact kind)' in text(result, 'output_up')


def test_fill_in_down_withheld_when_real_peers_alone_do_not_agree():
    target, rows = fill_case(60, [60, 60], [100] * 3)
    result = insights(target, rows)
    assert codes(result) == ['in_line']
    assert text(result, 'in_line') == ('A normal ride for you: 60 W in the work segments against your usual 100 W '
                                       'for the closest rides you have (only 2 of this exact kind), inside your '
                                       'usual range.')
    target, rows = fill_case(50, [60, 60], [100] * 3)
    assert codes(insights(target, rows)) == ['output_down']


def test_fill_in_up_withheld_when_real_peers_alone_do_not_agree():
    target, rows = fill_case(95, [90, 100], [10] * 3)
    assert codes(insights(target, rows)) == ['in_line']


def test_one_real_peer_is_too_few():
    target, rows = fill_case(80, [100], [100] * 4)
    assert codes(insights(target, rows)) == ['too_few']


def test_target_without_plan_gets_no_fill_in():
    target = ride(0, 80)
    rows = [target] + peers_of([100] * 3, plan=dict(PLAN)) + fill_rows([100] * 2)
    assert codes(insights(target, rows)) == ['too_few']


def test_effort_never_uses_fill_ins():
    target, rows = fill_case(100, [100] * 3, [100] * 2, strive=50)
    for r in rows[1:]:
        r['strive'] = 10
    assert codes(insights(target, rows)) == ['in_line']


# 5.5 nothing to say, caps

def test_too_few_wording():
    target = ride(0, 100)
    assert pairs(insights(target, [target] + peers_of([100] * 3))) == [
        ('too_few', 'Not enough rides like this one to compare yet (3 in the last two years, 5 needed).')]


def test_too_few_not_added_when_a_callout_fires():
    target = ride(0, 100, target_under={'resistance': 40})
    assert codes(insights(target, [target] + peers_of([100] * 3))) == ['resistance_low']


def test_nothing_with_five_peers_for_strength():
    rows = [strength(i, [st('Curl', 'other', 20, 10, 10)]) for i in range(1, 6)]
    target = strength(0, [st('Curl', 'other', 20, 10, 10)])
    assert pairs(insights(target, [target] + rows)) == [
        ('nothing', 'Nothing stood out against your 5 similar classes.')]


def test_strength_too_few_uses_class_noun():
    target = strength(0, [st('Curl', 'other', 20, 10, 10)])
    assert text(insights(target, [target]), 'too_few').startswith('Not enough classes like this one')


def test_freestyle():
    target = ride(0, 100, wtype='freestyle', ctype=None)
    assert pairs(insights(target, [target])) == [('freestyle', 'Freestyle workouts are not compared yet.')]
    untyped = ride(0, 100, ctype=None)  # a class without a class type has no peers: too few, not freestyle
    assert codes(insights(untyped, [untyped])) == ['too_few']


def test_freestyle_is_never_compared_even_with_callouts():
    bike = ride(0, 100, wtype='freestyle', ctype=None, target_under={'resistance': 30})
    assert codes(insights(bike, [bike])) == ['freestyle']
    lift = strength(0, None, wtype='freestyle', ctype=None)
    assert codes(insights(lift, [lift])) == ['freestyle']


def test_class_without_class_type_keeps_single_workout_rules():
    bike = ride(0, 100, ctype=None, target_under={'resistance': 30})
    assert codes(insights(bike, [bike] + peers_of([100] * 5))) == ['resistance_low']
    lift = strength(0, None, ctype=None)
    assert codes(insights(lift, [lift])) == ['no_tracker']
    plain = ride(0, 100, ctype=None)
    assert codes(insights(plain, [plain] + peers_of([100] * 5))) == ['too_few']


def test_effort_tie_is_neither_hardest_nor_easiest():
    assert codes(effort(10, [10, 10, 10, 10, 10])) == ['in_line']
    assert codes(effort(10, [10, 11, 12, 13, 14])) == ['in_line']


def test_incomplete():
    target = ride(0, 100, complete=False, target_under={'resistance': 40})
    assert pairs(insights(target, [target] + peers_of([100] * 5))) == [
        ('incomplete', 'This workout was cut short, so it is not compared.')]


def test_unsupported():
    target = ride(0, 100, disc='yoga')
    assert pairs(insights(target, [target])) == [('unsupported', 'No comparison for this kind of workout.')]


def test_at_most_three_messages_in_order_output_callouts_effort_dropped():
    target = ride(0, 100, strive=20, target_under={'resistance': 40, 'cadence': 40})
    rows = [ride(i, 100, strive=10) for i in range(1, 6)]
    # candidates: in_line, resistance_low, cadence_low, effort_high
    assert codes(insights(target, [target] + rows)) == ['in_line', 'resistance_low', 'cadence_low']


def test_at_most_three_messages_strength_before_effort():
    earlier = [strength(d, [st('Row', 'heavy', 40, 10, 10), st('Press', 'medium', 25, 10, 10)], strive=10)
               for d in (10, 20, 30, 40, 50)]
    target = strength(0, [st('Row', 'heavy', 35, 12, 10), st('Press', 'medium', 20, 12, 10),
                          st('Curl', 'other', 20, 5, 10), st('Curl', 'other', 20, 5, 10)], strive=20)
    result = insights(target, [target] + earlier)
    assert codes(result) == ['missed_targets', 'go_up_lighter', 'go_up_lighter']
    assert 'effort_high' not in codes(result)


# Facts: the numbers behind each sentence, so the board can never disagree with the text

def facts_of(result, code):
    return {c: f for c, _, f in result}[code]


def test_output_facts_match_the_sentence():
    result = run_bike(124, [188] * 5)
    f = facts_of(result, 'output_down')
    assert f == {'value': 124, 'usual': 188, 'unit': 'W', 'foot': False, 'noun': 'ride'}
    assert f'{number(f["value"], f["unit"])} W in the work segments against your usual {number(f["usual"], f["unit"])} W' \
        in text(result, 'output_down')
    result = run_bike(205, [180] * 5)
    f = facts_of(result, 'output_up')
    assert (f['value'], f['usual'], f['noun']) == (205, 180, 'ride')
    assert '205 W' in text(result, 'output_up') and '180 W' in text(result, 'output_up')
    result = run_bike(112, [111] * 5)
    f = facts_of(result, 'in_line')
    assert (f['value'], f['usual'], f['unit']) == (112, 111, 'W')
    assert '112 W against a usual 111 W' in text(result, 'in_line')


def test_foot_facts_are_mph_with_one_decimal_in_the_text():
    target = foot(0, 3.6)
    result = insights(target, [target] + [foot(i, 4.1) for i in range(1, 6)])
    f = facts_of(result, 'output_down')
    assert (f['value'], f['usual'], f['unit'], f['foot'], f['noun']) == (3.6, 4.1, 'mph', True, 'run')
    assert '3.6 mph' in text(result, 'output_down') and '4.1 mph' in text(result, 'output_down')


def test_in_line_facts_in_every_wording_variant():
    target = ride(0, 100)
    exact = insights(target, [target] + peers_of([100] * 5))
    assert facts_of(exact, 'in_line')['noun'] == 'ride'
    # 15% under but not at the bottom of the peers: "a normal ride" wording, still the same facts.
    target = ride(0, 85)
    result = insights(target, [target] + peers_of([100, 100, 100, 60, 60]))
    assert 'A normal ride' in text(result, 'in_line')
    assert (facts_of(result, 'in_line')['value'], facts_of(result, 'in_line')['usual']) == (85, 100)


def test_callout_facts_carry_the_percent_in_the_text():
    t = ride(0, 100, target_under={'resistance': 28, 'cadence': 37})
    result = insights(t, [t])
    assert facts_of(result, 'resistance_low') == {'pct': 28} and '28%' in text(result, 'resistance_low')
    assert facts_of(result, 'cadence_low') == {'pct': 37} and '37%' in text(result, 'cadence_low')
    t = ride(0, 100, disc='running', pace_fit=(42, 40))
    result = insights(t, [t])
    assert facts_of(result, 'pace_low') == {'pct': 42} and '42%' in text(result, 'pace_low')


def test_strength_facts_match_the_sentences():
    result = lighter()
    f = result[0][2]
    assert result[0][0] == 'go_up_lighter'
    assert f == {'movement': 'Row', 'lb': 35, 'usual': 40, 'unit': 'lb', 'category': 'heavy',
                 'on_movement': False, 'pct': 20}
    assert 'on Row next time: 35 lb today against your usual 40 lb' in result[0][1] and 'by 20%' in result[0][1]

    rows = streak_rows()
    t = strength(0, [st('Row', 'heavy', 40, 12, 10)])
    code, sentence, f = strength_insights(t, rows + [t])[0]
    assert (code, f) == ('go_up_streak', {'lb': 40, 'unit': 'lb', 'category': 'heavy', 'n': 3, 'pct': 20})
    assert 'from 40 lb on your heavy weights' in sentence.lower() and '3 classes' in sentence and '20%' in sentence

    code, sentence, f = heavier()[0]
    assert code == 'went_heavier'
    assert f == {'movement': 'Row', 'lb': 45, 'usual': 40, 'unit': 'lb', 'category': 'heavy', 'on_movement': True}
    assert '(45 lb against your usual 40 lb on that movement)' in sentence

    code, sentence, f = strength_insights(*_missed())[0]
    assert (code, f) == ('missed_targets', {'missed': 3, 'sets': 8, 'movement': 'Row'})
    assert '3 of 8 sets, mostly Row' in sentence


def _missed():
    sets = [st('Row', 'other', 20, 5, 10) for _ in range(3)] + [st('Curl', 'other', 20, 10, 10) for _ in range(5)]
    t = strength(0, sets)
    return t, [t]


def test_effort_facts_match_the_sentence():
    result = effort(20, [10, 11, 12, 13, 14])
    assert facts_of(result, 'effort_high') == {'n': 5, 'value': 20}
    assert 'last 5: Strive 20.0.' in text(result, 'effort_high')
    result = effort(5, [10, 11, 12, 13, 14])
    assert facts_of(result, 'effort_low') == {'n': 5, 'value': 5}


def test_count_facts_and_empty_facts():
    target = ride(0, 100)
    result = insights(target, [target] + peers_of([100] * 3))
    assert result[0][2] == {'n': 3, 'noun': 'ride'} and '(3 in the last' in result[0][1]
    target = ride(0, None)
    nothing = insights(target, [target] + peers_of([100] * 5))
    assert nothing[0][2] == {'n': 5, 'noun': 'ride'} and 'your 5 similar rides' in nothing[0][1]
    assert insights(strength(0, None), [])[0][2] == {}
    assert insights(ride(0, 100, complete=False), [])[0][2] == {}
    assert insights(ride(0, 100, wtype='freestyle'), [])[0][2] == {}
    assert insights(ride(0, 100, disc='yoga'), [])[0][2] == {}
