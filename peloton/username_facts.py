"""The name page's highlights, varied from pass to pass.

Every pass shows the total and this week, then one time frame's story: a headline fact, then that
frame's instructor top three (three highlights). Each pass takes the next frame (all time, the last
30 days, this year, ...); a frame that comes round again shows its next fact, so a full page is six
highlights, as before, whatever it shows. After a frame's general facts come its subjects: one of its
most-done disciplines (the discipline's count, then that discipline's instructor top three), and
its most-seen instructors. Everything comes from the dashboard cache and the workout
log (peloton.activity.frame_stats); the log's figures stay empty until its backfill is complete,
and then the page falls back to what's left.

Pass 0 is all time: the top discipline and the all-time top three, as the page always began.
"""
from .instructors import top_instructors
from .selection import normalize_discipline
from .totals import total_workout_count

RANKS = ('TOP', '2ND', '3RD')
# The order frames take turns in. Not 'week' (THIS WEEK is on every page).
FRAME_ORDER = ('all', '30d', 'year', '90d', 'last_year', 'last_week')
# A ranking for a frame or one discipline needs three instructors with at least this many classes
# each; fewer is too little to call a ranking (e.g. one strength class in 30 days).
MIN_RANKED_CLASSES = 2
# A frame's most-done discipline, different classes, different instructors and active days need at
# least this many.
MIN_COUNT = 2
# Past this many minutes a frame's time is told in hours.
HOURS_FROM_MINUTES = 600
# Averages, a share and the bests need a frame with at least this many workouts to be worth saying.
MIN_MEASURE_WORKOUTS = 5
# A share of the workouts ("38% STRENGTH") needs more than that, or one class moves it 10%.
MIN_SHARE_WORKOUTS = 10
# An average week needs this many days of the frame (fewer than four weeks is mostly the edge).
MIN_AVERAGE_WEEK_DAYS = 28
# The busiest day, and the busiest week or month, must reach these to be a best worth naming.
MIN_BEST_DAY = 2
MIN_BEST_PERIOD = 3
# A rank is shown for the top of the blocks only ("3RD BEST EVER"; below this it's just not notable).
MAX_SHOWN_RANK = 5
# The weekly streak record is shown from this many weeks.
MIN_STREAK_WEEKS = 4
# A comparison with the frame before is shown only when both have at least MIN_COMPARE_WORKOUTS and the
# count changed by at least MIN_COMPARE_CHANGE (a fraction) and MIN_COMPARE_DIFF workouts.
MIN_COMPARE_WORKOUTS = 5
MIN_COMPARE_CHANGE = 0.2
MIN_COMPARE_DIFF = 3
ORDINALS = {2: '2ND', 3: '3RD', 4: '4TH', 5: '5TH'}
MONTHS = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')
# A label holds 15 characters of the stats font; a longer discipline name uses its last word.
MAX_LABEL_CHARS = 15


def discipline_name(slug):
    """'bike_bootcamp' -> 'BIKE BOOTCAMP', as the Lifetime pages label it."""
    return str(slug).replace('_', ' ').upper()


def frame_words(key, stats=None):
    """(title, "in" words) for a frame: LAST 30 DAYS / IN 30 DAYS, IN 2026 / IN 2026. The title heads
    a total; the "in" words end a ranking's label (3RD IN 30 DAYS) or follow MOST."""
    year = (stats or {}).get('year')
    return {'all': ('LIFETIME', 'LIFETIME'), '30d': ('LAST 30 DAYS', 'IN 30 DAYS'),
            '90d': ('LAST 90 DAYS', 'IN 90 DAYS'), 'last_week': ('LAST WEEK', 'LAST WEEK'),
            'year': (f'IN {year}', f'IN {year}'), 'last_year': (f'IN {year}', f'IN {year}')}[key]


def _plural(count, word, plural=None):
    return f'{count:,} {word}' if count == 1 else f'{count:,} {plural or word + "S"}'


def _instructor_ranking(label_for, counts, names, least, short_for=None):
    ranks = top_instructors(counts, names, limit=len(RANKS))
    if least > 1 and (len(ranks) < len(RANKS) or ranks[-1][1] < least):
        return []
    details = []
    for rank, (name, count) in zip(RANKS, ranks):
        detail = {'label': label_for(rank), 'value': f'{name} / {count:,}',
                  'lines': [name.upper(), _plural(count, 'CLASS', 'CLASSES')]}
        if short_for:
            detail['short_label'] = short_for(rank)
        details.append(detail)
    return details


def frame_rankings(snapshot, key):
    """The general instructor top threes a frame has enough data for, each a list of up to three
    highlights: every class in the frame (all time keeps any count; the others need
    MIN_RANKED_CLASSES for third place). One discipline's top three is a subject (frame_subjects)."""
    names = snapshot.get('instructor_names') or {}
    if key == 'all':
        ranking = _instructor_ranking(lambda rank: f'{rank} INSTRUCTOR', snapshot.get('instructor_counts'),
                                      names, 1)
        return [ranking] if ranking else []
    stats = (snapshot.get('time_frames') or {}).get(key) or {}
    if not stats:
        return []
    in_words = frame_words(key, stats)[1]
    ranking = _instructor_ranking(lambda rank: f'{rank} {in_words}', stats.get('instructor_counts'),
                                  names, MIN_RANKED_CLASSES)
    return [ranking] if ranking else []


def _time_line(minutes):
    return _plural(round(minutes / 60), 'HOUR') if minutes >= HOURS_FROM_MINUTES else _plural(minutes, 'MINUTE')


def frame_subjects(snapshot, key):
    """A frame's most-done disciplines as (headline, top three) pairs, most-done first: the headline
    is the discipline's name over its workouts and the frame ('STRENGTH' / '12 WORKOUTS' / 'IN 30
    DAYS'), the top three the instructors in that discipline in that frame. A discipline needs
    MIN_COUNT workouts and a whole top three (MIN_RANKED_CLASSES each), so it's never a one-off."""
    names = snapshot.get('instructor_names') or {}
    stats = (snapshot.get('time_frames') or {}).get(key) or {}
    in_words = frame_words(key, stats)[1] if stats else None
    pairs = []
    by_discipline = stats.get('by_discipline') or {}
    for slug in sorted(by_discipline, key=lambda name: (-by_discipline[name].get('workouts', 0), name)):
        found, noun = by_discipline[slug], discipline_name(slug)
        if (found.get('workouts') or 0) < MIN_COUNT:
            continue
        # 3RD TREAD BOOTCAMP is too wide for the label; the screen falls back to 3RD BOOTCAMP.
        ranking = _instructor_ranking(
            lambda rank, noun=noun: f'{rank} {noun}', found.get('instructor_counts'), names, MIN_RANKED_CLASSES,
            short_for=lambda rank, noun=noun: f'{rank} {noun.split()[-1]}')
        if ranking:
            headline = {'label': noun, 'value': f'{found["workouts"]} WORKOUTS',
                        'lines': [_plural(found['workouts'], 'WORKOUT'), in_words]}
            if len(noun) > MAX_LABEL_CHARS:
                headline['short_label'] = noun.split()[-1]
            pairs.append((headline, ranking))
    return pairs


def _all_time_top_discipline(snapshot):
    totals = snapshot.get('totals') or {}
    disciplines = [(label, count) for label, count in totals.items()
                   if label != 'Total Workouts' and isinstance(count, int) and not isinstance(count, bool)]
    return max(disciplines, key=lambda item: item[1], default=None)


def _date_words(iso, month_only=False):
    """'2025-03-03' -> 'MAR 3 2025' (the English month names, whatever the machine's locale);
    'MAR 2025' for a month."""
    year, month, day = (int(part) for part in iso.split('-'))
    return f'{MONTHS[month - 1]} {year}' if month_only else f'{MONTHS[month - 1]} {day} {year}'


def _round_half_up(value):
    return int(value + 0.5)


def _share_line(count, workouts, slug):
    """'38% STRENGTH', or the discipline's last word when the whole doesn't fit a line."""
    name, percent = discipline_name(slug), round(100 * count / workouts)
    return f'{percent}% {name}' if len(f'{percent}% {name}') <= MAX_LABEL_CHARS else f'{percent}% {name.split()[-1]}'


def _measure_facts(stats, title):
    """The measures and bests a frame has enough data for: average class and week, the share of the
    most-done discipline, the frame's rank among equal blocks of days, then the busiest day, week and
    month, the longest workout, the highest bike output and the best Strive score. A fact with too
    little behind it is left out (MIN_MEASURE_WORKOUTS and friends), so it never says 1 or 0."""
    workouts = stats.get('workouts') or 0
    if workouts < MIN_MEASURE_WORKOUTS:
        return []
    facts = []
    minutes = stats.get('minutes') or 0
    if minutes:
        facts.append({'label': title, 'value': f'{round(minutes / workouts)} MIN AVERAGE',
                      'lines': ['AVERAGE CLASS', _plural(round(minutes / workouts), 'MINUTE')]})
    if (stats.get('days') or 0) >= MIN_AVERAGE_WEEK_DAYS:
        average = workouts * 7 / stats['days']
        facts.append({'label': title, 'value': f'{average:.1f} PER WEEK',
                      'lines': ['AVERAGE WEEK', f'{average:.1f} WORKOUTS']})
    done = sorted((stats.get('disciplines') or {}).items(), key=lambda item: (-item[1], item[0]))
    if workouts >= MIN_SHARE_WORKOUTS and done and done[0][1] >= MIN_COUNT:
        facts.append({'label': title, 'value': f'{done[0][0]} {done[0][1]} OF {workouts}',
                      'lines': [_share_line(done[0][1], workouts, done[0][0]), 'OF WORKOUTS']})
    rank = stats.get('rank')
    if rank and rank['rank'] <= MAX_SHOWN_RANK:
        words = 'BEST EVER' if rank['rank'] == 1 else f'{ORDINALS[rank["rank"]]} BEST EVER'
        facts.append({'label': title, 'value': f'{words} / {workouts}', 'lines': [words, _plural(workouts, 'WORKOUT')]})
    for key, label, least, month in (('busiest_day', 'BUSIEST DAY', MIN_BEST_DAY, False),
                                     ('busiest_week', 'BUSIEST WEEK', MIN_BEST_PERIOD, False),
                                     ('busiest_month', 'BUSIEST MONTH', MIN_BEST_PERIOD, True)):
        best = stats.get(key)
        if best and best['count'] >= least:
            when = _date_words(best['date'], month_only=month)
            facts.append({'label': label, 'value': f'{best["count"]} / {when}',
                          'lines': [_plural(best['count'], 'WORKOUT'), f'OF {when}' if key == 'busiest_week' else when]})
    longest = stats.get('longest')
    if longest and longest.get('minutes'):
        facts.append({'label': 'LONGEST WORKOUT', 'value': f'{longest["minutes"]} MIN',
                      'lines': [_plural(longest['minutes'], 'MINUTE'), discipline_name(longest.get('discipline') or '')]})
    output = stats.get('best_output')
    if output:
        kind = discipline_name(output.get('discipline') or '')
        facts.append({'label': 'HIGHEST OUTPUT', 'value': f'{_round_half_up(output["kj"])} KJ',
                      'lines': [f'{_round_half_up(output["kj"]):,} KJ',
                                f'{output["minutes"]} MIN {kind}' if output.get('minutes') else kind]})
    strive = stats.get('best_strive')
    if strive:
        facts.append({'label': 'BEST STRIVE', 'value': f'{_round_half_up(strive["points"])} POINTS',
                      'lines': [f'{_round_half_up(strive["points"]):,} POINTS',
                                discipline_name(strive.get('discipline') or '')]})
    return facts


def _comparison_fact(key, stats):
    """This frame's workouts against the same stretch before it (frame_stats' `before`: the 30 or 90
    days just before, or last year up to today's date): '2026 VS 2025' / '412 VS 380' / '+32 WORKOUTS'.
    Left out unless both sides have MIN_COMPARE_WORKOUTS and the change passes the thresholds."""
    before = stats.get('before') if key in ('30d', '90d', 'year') else None
    now = stats.get('workouts') or 0
    if not before or min(now, before['workouts']) < MIN_COMPARE_WORKOUTS:
        return None
    change = now - before['workouts']
    if abs(change) < MIN_COMPARE_DIFF or abs(change) < MIN_COMPARE_CHANGE * before['workouts']:
        return None
    label = f'{stats["year"]} VS {stats["year"] - 1}' if key == 'year' else f'VS {key[:-1]} BEFORE'
    return {'label': label, 'value': f'{now} VS {before["workouts"]}',
            'lines': [f'{now:,} VS {before["workouts"]:,}', f'{change:+,} WORKOUTS']}


def frame_facts(snapshot, key):
    """The single-highlight facts a frame has enough data for, in the order its visits show them.
    All time: the top discipline. Others: workouts and time, the most-done discipline (when it
    isn't the all-time top, which TOP DISCIPLINE already says), active days. Then different classes
    and different instructors, for every frame."""
    facts = []
    favorite = _all_time_top_discipline(snapshot)
    stats = (snapshot.get('time_frames') or {}).get(key) or {}
    title = frame_words(key, stats)[0] if key == 'all' or stats else None
    if key == 'all':
        if favorite:
            facts.append({'label': 'TOP DISCIPLINE', 'value': f'{favorite[0]} / {favorite[1]:,}',
                          'lines': [favorite[0].upper(), _plural(favorite[1], 'WORKOUT')]})
    elif stats and stats.get('workouts'):
        workouts, minutes = stats['workouts'], stats.get('minutes') or 0
        facts.append({'label': title, 'value': f'{workouts} WORKOUTS / {minutes} MIN',
                      'lines': [_plural(workouts, 'WORKOUT'), _time_line(minutes)]})
        done = sorted((stats.get('disciplines') or {}).items(), key=lambda item: (-item[1], item[0]))
        if (done and done[0][1] >= MIN_COUNT
                and (not favorite or done[0][0] != normalize_discipline(favorite[0]))):
            slug, count = done[0]
            # MOST IN 30 DAYS is exactly 15 characters, the most a label holds.
            facts.append({'label': f'MOST {frame_words(key, stats)[1]}',
                          'value': f'{discipline_name(slug)} / {count}',
                          'lines': [discipline_name(slug), _plural(count, 'WORKOUT')]})
        if (stats.get('active_days') or 0) >= MIN_COUNT and stats.get('days'):
            facts.append({'label': title, 'value': f'{stats["active_days"]} / {stats["days"]} DAYS',
                          'lines': ['ACTIVE DAYS', f'{stats["active_days"]:,} OF {stats["days"]:,}']})
    if stats:
        if (stats.get('classes') or 0) >= MIN_COUNT:
            facts.append({'label': title, 'value': f'{stats["classes"]:,} DIFFERENT CLASSES',
                          'lines': [f'{stats["classes"]:,} DIFFERENT', 'CLASSES']})
        if (stats.get('instructors') or 0) >= MIN_COUNT:
            facts.append({'label': title, 'value': f'{stats["instructors"]:,} DIFFERENT INSTRUCTORS',
                          'lines': [f'{stats["instructors"]:,} DIFFERENT', 'INSTRUCTORS']})
        facts.extend(_measure_facts(stats, title))
        comparison = _comparison_fact(key, stats)
        if comparison:
            facts.append(comparison)
        facts.extend(_instructor_facts(snapshot, stats, title))
    best_weekly = (snapshot.get('streaks') or {}).get('best_weekly')
    if key == 'all' and isinstance(best_weekly, int) and best_weekly >= MIN_STREAK_WEEKS:
        facts.append({'label': title, 'value': f'{best_weekly} WEEK STREAK',
                      'lines': [f'{best_weekly} WEEK STREAK', 'YOUR BEST']})
    return facts


def _instructor_facts(snapshot, stats, title):
    """One highlight per most-seen instructor in the frame (frame_stats' by_instructor): their name
    over the time spent with them. The top three above show the classes; this adds the minutes."""
    names = snapshot.get('instructor_names') or {}
    by_instructor = stats.get('by_instructor') or {}
    facts = []
    for identity in sorted(by_instructor, key=lambda who: (-by_instructor[who].get('workouts', 0), who)):
        found, name = by_instructor[identity], names.get(identity)
        if name and (found.get('workouts') or 0) >= MIN_COUNT:
            facts.append({'label': title, 'value': f'{name} / {found["minutes"]} MIN',
                          'lines': [name.upper(), _time_line(found.get('minutes') or 0)]})
    return facts


def frame_stories(snapshot, key):
    """A frame's pages as (headline, top three) pairs, either of which can be None: the general
    facts and top threes pair off in order (the shorter list wraps), and the subjects (frame_subjects)
    take every other turn, so a discipline's page comes round soon, not after all the general ones."""
    facts, rankings = frame_facts(snapshot, key), frame_rankings(snapshot, key)
    stories = [(facts[index % len(facts)] if facts else None, rankings[index % len(rankings)] if rankings else None)
               for index in range(max(len(facts), len(rankings)))]
    subjects = frame_subjects(snapshot, key)
    merged = []
    for index in range(max(len(stories), len(subjects))):
        merged += stories[index:index + 1] + subjects[index:index + 1]
    return merged


def username_frames(snapshot):
    """The frames that take a turn, in order. A frame needs a headline and an instructor top three,
    so every page is six highlights: LAST WEEK, which rarely has three instructors, drops out. When
    no frame has both (a rider with no instructor data), any frame with something to show takes
    a turn, and its page is shorter."""
    stories = {key: frame_stories(snapshot, key) for key in FRAME_ORDER}
    whole = [key for key in FRAME_ORDER if any(fact and ranking for fact, ranking in stories[key])]
    return whole or [key for key in FRAME_ORDER if stories[key]]


def username_details(snapshot, pass_index=0):
    """This pass's highlights: the total, this week, then the pass's frame: a headline fact and an
    instructor top three. A frame that comes round again shows its next fact and top three."""
    details = []
    total = total_workout_count(snapshot.get('totals') or {})
    if total is not None:
        details.append({'label': 'TOTAL WORKOUTS', 'value': f'{total:,}',
                        'lines': [f'{total:,}'], 'font_key': 'big', 'color_key': 'gold'})
    progress = snapshot.get('weekly_progress') or {}
    weekly_workouts = progress.get('workouts', 0)
    weekly_minutes = progress.get('minutes', 0)
    details.append({'label': 'THIS WEEK',
                    'value': f'{weekly_workouts} WORKOUTS / {weekly_minutes} MIN',
                    'lines': [f'{weekly_workouts} WORKOUTS', f'{weekly_minutes} MINUTES']})
    frames = username_frames(snapshot)
    if frames:
        key, visit = frames[pass_index % len(frames)], pass_index // len(frames)
        stories = frame_stories(snapshot, key)
        fact, ranking = stories[visit % len(stories)]
        if fact:
            details.append(fact)
        details.extend(ranking or [])
    return details
