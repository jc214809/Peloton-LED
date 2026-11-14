"""Workout compare: the plain messages for one workout (spec section 5).

No model: every message is a rule over the target's row and its peers' rows. Standard library only.
`insights(target, rows)` returns at most MAX_MESSAGES (code, text, facts) triples, never none. `facts` holds the
numbers the text was built from (raw, unrounded; `insight_lines.number` rounds them for text and board alike).
"""
import collections
import statistics

from . import workout_compare as compare
from .insight_lines import OUTPUT_CODES, number, ordinal

MAX_MESSAGES = 3
TYPICAL = 'typical'        # the word for the usual figure (the peers' median) in the Mac text
CONSISTENT = 'consistent'  # the word for an in-line workout
# Output / speed against peers
BIG_CHANGE_PCT = 10        # at least this far from the peer median ...
RANK_SHARE = 0.8           # ... and beyond this share of the peers
COST_PCT = 8               # output per heartbeat this far under the peer median = "cost you more"
EASY_HR_PCT = 4            # work heart rate this far under the peer median = "easier effort"
SAME_HR_BPM = 3            # work heart rate within this many bpm of the peer median = "the same heart"
# Class difficulty (Peloton's rating, row['difficulty']) against the rider's usual: their last USUAL_CLASSES classes
# in the discipline (any class type or length, indoor and outdoor together; Joel, 2026-11-13)
TOUGH_POINTS = 1.0         # a class rated this many points or more above the usual's median is "tough"
USUAL_CLASSES = 12
USUAL_DAYS = 365
MIN_RATED = 5              # rated classes in the usual before its median means anything
USUAL_MIN_SECS = 600       # shorter classes (rated 3-4) are left out on both sides, as are ...
USUAL_SKIP_TYPES = ('Warm Up', 'Cool Down')  # ... class types containing these
# Callouts
RESISTANCE_UNDER_PCT = 25  # share of callout time under the resistance range
CADENCE_UNDER_PCT = 35
PACE_UNDER_PCT = 35        # Peloton's own below_target share (row, run)
# Strength
GO_UP_SESSIONS = 3         # classes in a row at this weight or lighter, every target beaten
GO_UP_RATIO = 1.2          # reps done / rep target
LIGHTER_LB = 5             # today's weight this far under (or over) the usual
CATEGORY_HISTORY = 3       # earlier tracked classes with the category (or movement) before "usual" means anything
CATEGORY_DAYS = 365
MOVEMENT_DAYS = 730
MISSED_SHARE = 0.25        # share of counted sets under target
MIN_MISSED = 2
CATEGORIES = ('light', 'medium', 'heavy')

MAIN = {'cycling': ('output', 'W'), 'bike_bootcamp': ('output', 'W'), 'rowing': ('output', 'W'),
        'row_bootcamp': ('output', 'W'), 'running': ('speed', 'mph'), 'walking': ('speed', 'mph'),
        'tread_bootcamp': ('speed', 'mph')}
NOUN = {'cycling': 'ride', 'bike_bootcamp': 'bootcamp', 'rowing': 'row', 'row_bootcamp': 'bootcamp',
        'running': 'run', 'walking': 'walk', 'tread_bootcamp': 'bootcamp', 'strength': 'class'}


def plural(noun):
    return noun + ('es' if noun.endswith('s') else 's')


def _fmt(value, unit):
    return f'{number(value, unit)} {unit}'


def counted_sets(row):
    """Sets the rep rules count: rep_counting, not a hold, with a target, a rep count and a weight.

    Drops warm-up sets (time_tracked_rep, holds) and `rounds` entries (EMOM, AMRAP, Compound),
    whose targets are placeholders.
    """
    return [s for s in row.get('sets') or []
            if s.get('type') == 'rep_counting' and not s.get('hold') and s.get('target')
            and s.get('done') is not None and s.get('lb')]


def _by_category(row):
    cats = collections.defaultdict(list)
    for s in counted_sets(row):
        if s.get('cat') in CATEGORIES:
            cats[s['cat']].append(s)
    return cats


def _ratio(sets):
    return sum(s['done'] for s in sets) / sum(s['target'] for s in sets)


def _all_hit(sets):
    return all(s['done'] >= s['target'] for s in sets)


# 5.1 Output or pace against peers

def output_insight(target, group, real):
    """down / up / in line, for every discipline with an output or speed series.

    `real` is how many of `group` are real peers; the rest are bike fill-ins (section 4.1), which
    may support a verdict but never carry one: down / up also need the real peers to agree.
    """
    if target['disc'] not in MAIN:
        return None
    key, unit = MAIN[target['disc']]
    noun = NOUN[target['disc']]
    result = compare.stat(target['work'].get(key), [p['work'].get(key) for p in group])
    if not result or result['n'] < compare.MIN_PEERS:
        return None
    filled = real < len(group)
    if filled:
        kind = f'the closest {plural(noun)} you have (only {real} of this exact kind)'
        real_stat = compare.stat(result['value'], [p['work'].get(key) for p in group if not p.get('fill_in')])
    else:
        kind = f'{plural(noun)} like this'
        real_stat = None
    usual = f"{_fmt(result['value'], unit)} in the work segments against your {TYPICAL} {_fmt(result['median'], unit)}"
    eff = compare.stat(target.get('eff'), [p.get('eff') for p in group])
    heart = compare.stat(target['work'].get('heart_rate'), [p['work'].get('heart_rate') for p in group])
    enough_hr = eff and heart and eff['n'] >= compare.MIN_PEERS and heart['n'] >= compare.MIN_PEERS
    # Rounded so "at most 20%" holds at exactly 1 of 5 (1 - 0.8 is 0.19999... in floating point).
    down = result['pct'] <= -BIG_CHANGE_PCT and result['below'] <= round((1 - RANK_SHARE) * result['n'], 9)
    up = result['pct'] >= BIG_CHANGE_PCT and result['below'] >= round(RANK_SHARE * result['n'], 9)
    if filled and down:
        down = bool(real_stat) and real_stat['value'] < real_stat['median']
    if filled and up:
        up = bool(real_stat) and real_stat['value'] > real_stat['median']
    # `n` is the comparison group behind the usual, `real` its real peers (fewer when bike fill-ins were used).
    facts = {'value': result['value'], 'usual': result['median'], 'unit': unit, 'foot': unit == 'mph', 'noun': noun,
             'n': result['n'], 'real': real, 'reason': None}
    if down:
        what = 'output' if unit == 'W' else 'pace'
        text = f'Your {what} was down today: {usual} for {kind}.'
        if enough_hr and heart['pct'] <= -EASY_HR_PCT:
            text += ' Your heart rate was lower too, so it looks like an easier effort.'
            facts['reason'] = 'easier'
        elif enough_hr and eff['pct'] <= -COST_PCT:
            text += ' Your heart rate was not lower, so the same work cost you more.'
            facts['reason'] = 'cost_more'
        return ('output_down', text, facts)
    if up:
        text = f'Strong {noun}: {usual} for {kind}.'
        if enough_hr and eff['pct'] >= COST_PCT:
            text += f' You got more out of every heartbeat than {TYPICAL}.'
            facts['reason'] = 'efficient'
            # The board says "same heart" only when it was: more per beat can come with a higher heart rate too.
            facts['same_hr'] = abs(heart['value'] - heart['median']) <= SAME_HR_BPM
        return ('output_up', text, facts)
    facts['close'] = abs(result['pct']) < BIG_CHANGE_PCT
    if abs(result['pct']) < BIG_CHANGE_PCT:
        if filled:
            return ('in_line', f"Good {noun}, right in line with {kind}: {_fmt(result['value'], unit)} "
                               f"against a {TYPICAL} {_fmt(result['median'], unit)}.", facts)
        return ('in_line', f"Good {noun}, right in line with your other {plural(noun)} like it "
                           f"({_fmt(result['value'], unit)} against a {TYPICAL} "
                           f"{_fmt(result['median'], unit)}).", facts)
    if filled:
        return ('in_line', f'A {CONSISTENT} {noun} for you: {usual} for {kind}, inside your {TYPICAL} range.', facts)
    return ('in_line', f'A {CONSISTENT} {noun} for you: {usual}, inside your {TYPICAL} range.', facts)


def _is_rating(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= 10


def _counts_for_usual(row):
    """A complete, rated class of USUAL_MIN_SECS or more that isn't a warm-up or cool-down."""
    ctype = row.get('ctype') or ''
    return (row.get('complete') and row.get('wtype') == 'class' and (row.get('dur') or 0) >= USUAL_MIN_SECS
            and not any(skip in ctype for skip in USUAL_SKIP_TYPES) and _is_rating(row.get('difficulty')))


def usual_classes(target, rows):
    """The rider's last USUAL_CLASSES counted classes in the target's discipline from the USUAL_DAYS before it,
    newest first: any class type or length, indoor and outdoor together."""
    start = target['start'] - USUAL_DAYS * compare.DAY
    found = [r for r in rows if r['id'] != target['id'] and r['disc'] == target['disc']
             and start <= r['start'] < target['start'] and _counts_for_usual(r)]
    found.sort(key=lambda r: -r['start'])
    return found[:USUAL_CLASSES]


def tough_class(target, rows, main):
    """('tough_class', text, facts) when the class was rated TOUGH_POINTS+ above the median rating of the rider's
    usual (`usual_classes`, at least MIN_RATED of them), else None. With an output insight (`main`) it takes its
    place and reuses its figures; without one it stands alone. An easier class gets nothing."""
    if not _counts_for_usual(target):
        return None
    usual_rows = usual_classes(target, rows)
    if len(usual_rows) < MIN_RATED:
        return None
    rating = target['difficulty']
    usual = statistics.median(r['difficulty'] for r in usual_rows)
    # Rounded so exactly 1 point up holds in floating point (8.1 - 7.1 is 0.99999... in binary).
    if round(rating - usual, 9) < TOUGH_POINTS:
        return None
    noun = NOUN[target['disc']]
    facts = {**(main[2] if main else {'noun': noun}), 'difficulty': rating, 'usual_difficulty': usual,
             'rated': len(usual_rows), 'reason': None}
    return ('tough_class', f'Tough {noun}: rated {rating:.1f} against your usual {usual:.1f} over your last '
                           f'{len(usual_rows)} {plural(noun)}.', facts)


# 5.2 Callouts

def callout_insights(target):
    """Single-workout messages about following the instructor's callouts. No peers needed."""
    out = []
    under = target.get('target_under') or {}
    if target['disc'] in compare.BIKE:
        if under.get('resistance', 0) >= RESISTANCE_UNDER_PCT:
            out.append(('resistance_low', 'Turn the resistance up in the work segments: you were under the '
                                          f"callout range {under['resistance']}% of the time.",
                    {'pct': under['resistance']}))
        if under.get('cadence', 0) >= CADENCE_UNDER_PCT:
            out.append(('cadence_low', 'Pick the cadence up in the work segments: you were under the '
                                       f"callout range {under['cadence']}% of the time.",
                    {'pct': under['cadence']}))
    fit = target.get('pace_fit')
    if target['disc'] in ('rowing', 'row_bootcamp', 'running') and fit and (fit[0] or 0) >= PACE_UNDER_PCT:
        out.append(('pace_low', f'You were under the pace target {fit[0]}% of the time: push the pace, '
                                'or drop a pace level if that target is too fast.', {'pct': fit[0]}))
    return out


# 5.3 Strength

def _history(target, rows, days):
    """Earlier tracked, complete strength classes in the `days` before the target, oldest first."""
    start = target['start'] - days * compare.DAY
    return sorted((r for r in rows if r['disc'] == 'strength' and r.get('sets') and r['complete']
                   and r['id'] != target['id'] and start <= r['start'] < target['start']),
                  key=lambda r: r['start'])


def _usual(cat, sets, target, rows):
    """(usual lb, today's lb, movement name, on_movement) for one category used today, or None.

    Movement first: the movement with the most reps today that has 3+ earlier classes of its own
    at this category in the last 730 days. Otherwise the category's own 365-day history. Movement
    and category are always matched together.
    """
    reps = collections.Counter()
    for s in sets:
        reps[s['name']] += s['done']
    ranked = [name for name, _ in reps.most_common()]
    movement_history = [_by_category(r).get(cat, []) for r in _history(target, rows, MOVEMENT_DAYS)]
    for name in ranked:
        sessions = [max(s['lb'] for s in past if s['name'] == name)
                    for past in movement_history if any(s['name'] == name for s in past)]
        if len(sessions) >= CATEGORY_HISTORY:
            today = max(s['lb'] for s in sets if s['name'] == name)
            return statistics.median(sessions), today, name, True
    sessions = [max(s['lb'] for s in cats[cat])
                for cats in map(_by_category, _history(target, rows, CATEGORY_DAYS)) if cat in cats]
    if len(sessions) >= CATEGORY_HISTORY:
        return statistics.median(sessions), max(s['lb'] for s in sets), ranked[0], False
    return None


def _streak(cat, sets, lb, past):
    """True when this and the previous GO_UP_SESSIONS - 1 classes with the category were at `lb` or
    lighter and each beat every rep target by GO_UP_RATIO."""
    streak = [sets]
    for cats in reversed(past):
        if cat not in cats:
            continue
        if max(s['lb'] for s in cats[cat]) > lb:
            break
        streak.append(cats[cat])
        if len(streak) == GO_UP_SESSIONS:
            break
    return len(streak) == GO_UP_SESSIONS and all(
        _all_hit(session) and _ratio(session) >= GO_UP_RATIO for session in streak)


def strength_insights(target, rows):
    """Weights and reps. Needs the movement tracker; compares with the rider's own history."""
    if target['disc'] != 'strength':
        return []
    if not target.get('sets'):
        return [('no_tracker', 'No rep or weight data for this class, so only heart rate can be compared.', {})]
    out = []
    work = counted_sets(target)
    missed = [s for s in work if s['done'] < s['target']]
    if work and len(missed) / len(work) >= MISSED_SHARE and len(missed) >= MIN_MISSED:
        name = collections.Counter(s['name'] for s in missed).most_common(1)[0][0]
        out.append(('missed_targets', f'You came up short on {len(missed)} of {len(work)} sets, mostly '
                                      f'{name}: drop a weight there next time.',
                    {'missed': len(missed), 'sets': len(work), 'movement': name}))

    past = [_by_category(r) for r in _history(target, rows, CATEGORY_DAYS)]
    today = _by_category(target)
    for cat in CATEGORIES:
        sets = today.get(cat)
        if not sets:
            continue
        lb = max(s['lb'] for s in sets)
        all_hit, ratio = _all_hit(sets), _ratio(sets)
        found = _usual(cat, sets, target, rows)
        if found:
            usual, mine, name, on_movement = found
            against = (f'your {TYPICAL} {usual:.0f} lb on that movement' if on_movement
                       else f'your {TYPICAL} {usual:.0f} lb for {cat} weights')
            if mine <= usual - LIGHTER_LB and all_hit and ratio >= GO_UP_RATIO:
                out.append(('go_up_lighter', f'Go up a weight on {name} next time: {mine:.0f} lb today against '
                                             f'{against}, and you beat the rep targets by '
                                             f'{round((ratio - 1) * 100)}%.',
                            {'movement': name, 'lb': mine, 'usual': usual, 'unit': 'lb', 'category': cat,
                             'on_movement': on_movement, 'pct': round((ratio - 1) * 100)}))
                continue
        if _streak(cat, sets, lb, past):
            out.append(('go_up_streak', f'Go up from {lb:.0f} lb on your {cat} weights next time: '
                                        f'{GO_UP_SESSIONS} classes in a row you beat every rep target '
                                        f'by {round((GO_UP_RATIO - 1) * 100)}% or more.',
                        {'lb': lb, 'unit': 'lb', 'category': cat, 'n': GO_UP_SESSIONS,
                         'pct': round((GO_UP_RATIO - 1) * 100)}))
        elif found and mine >= usual + LIGHTER_LB and all_hit:
            what = f'on {name}' if on_movement else f'on your {cat} weights'
            out.append(('went_heavier', f'You went heavier {what} ({mine:.0f} lb against {against}) '
                                        'and still hit every target. Keep that weight.',
                        {'movement': name, 'lb': mine, 'usual': usual, 'unit': 'lb', 'category': cat,
                         'on_movement': on_movement}))
    return out


# 5.4 Heart-rate effort

def effort_insight(target, group):
    """Strive per class second against peers; the only comparison strength has without the tracker."""
    if not target.get('strive') or not target['dur']:
        return None
    mine = target['strive'] / target['dur']
    values = [p['strive'] / p['dur'] for p in group if p.get('strive') and p['dur']]
    result = compare.stat(mine, values)
    if not result or result['n'] < compare.MIN_PEERS:
        return None
    noun = NOUN[target['disc']]
    above = sum(1 for v in values if v > mine)  # strictly: a tie is neither hardest nor easiest
    # Strive per minute of class, today and the peers' median, for the board's bars.
    facts = {'n': result['n'], 'value': target['strive'], 'noun': noun, 'rate': mine * 60,
             'usual_rate': statistics.median(values) * 60}
    if result['below'] == result['n']:
        return ('effort_high', f"Hardest {noun} of this kind by heart rate in your last {result['n']}: "
                               f"Strive {target['strive']:.1f}.", facts)
    if above == result['n']:
        return ('effort_low', f"Easiest {noun} of this kind by heart rate in your last {result['n']}: "
                              f"Strive {target['strive']:.1f}.", facts)
    return None


# 5.5 Instructor milestones (from the workout log's counts, not the rows)

MILESTONE_COUNTS = (5, 10, 25, 50, 100)   # then every 100th
MILESTONE_EVERY = 100


def is_milestone(n):
    """A first class, or the 5th, 10th, 25th, 50th, 100th, then every 100th."""
    return n == 1 or n in MILESTONE_COUNTS or (n > MILESTONE_COUNTS[-1] and n % MILESTONE_EVERY == 0)


def milestone_insight(numbers):
    """(code, text, facts) for the instructor this class is a milestone with, or None.

    `numbers` is instructors.class_numbers: [{'name', 'n', 'since'}], one per instructor of the class (a
    class with two instructors counts for each). Nameless ones are skipped; when several qualify the
    biggest count wins.
    """
    hits = [c for c in numbers or [] if c.get('name') and isinstance(c.get('n'), int) and is_milestone(c['n'])]
    if not hits:
        return None
    best = max(hits, key=lambda c: c['n'])
    name, n = best['name'], best['n']
    text = f'Your first class with {name}: welcome!' if n == 1 else f'Your {ordinal(n).lower()} class with {name}.'
    return ('instructor_milestone', text, {'n': n, 'name': name, 'since': best.get('since')})


def with_milestone(messages, milestone):
    """`messages` with the milestone after the output insight (the leading output codes, or the tough class
    that takes its place), before the rest."""
    if not milestone:
        return list(messages)
    spot = 0
    while spot < len(messages) and messages[spot][0] in OUTPUT_CODES + ('tough_class',):
        spot += 1
    return [*messages[:spot], milestone, *messages[spot:]]


def insights(target, rows):
    """[(code, text, facts)] for one workout: at most MAX_MESSAGES, in the order of spec section 5; never empty."""
    if target['disc'] not in compare.DISCIPLINES:
        return [('unsupported', 'No comparison for this kind of workout.', {})]
    if not target['complete']:
        return [('incomplete', 'This workout was cut short, so it is not compared.', {})]
    if target['wtype'] != 'class':
        return [('freestyle', 'Freestyle workouts are not compared yet.', {})]
    callouts = callout_insights(target)
    strength = strength_insights(target, rows)
    # A class without a class type has no peers (spec section 4) but still gets the single-workout rules.
    group, _, real = compare.comparison_group(target, rows)
    main = output_insight(target, group, real)
    # "Of this kind" is only true of real peers: fill-ins never decide the effort message. A strong or weak output's
    # text already speaks to heart rate, so effort is dropped beside it, but not beside a tough class (Joel, 2026-11-13).
    # A much harder class than usual is applauded in place of the output insight, or on its own when there is none
    # (an easier one is not remarked on).
    main = tough_class(target, rows, main) or main
    effort = effort_insight(target, group[:real])
    if main and main[0] in ('output_up', 'output_down'):
        effort = None
    out = ([main] if main else []) + callouts + strength + ([effort] if effort else [])
    noun = NOUN[target['disc']]
    if not out and real < compare.MIN_PEERS:
        return [('too_few', f'Not enough {plural(noun)} like this one to compare yet '
                            f'({real} in the last two years, {compare.MIN_PEERS} needed).', {'n': real, 'noun': noun})]
    if not out:
        return [('nothing', f'Nothing stood out against your {real} similar {plural(noun)}.', {'n': real, 'noun': noun})]
    return out[:MAX_MESSAGES]
