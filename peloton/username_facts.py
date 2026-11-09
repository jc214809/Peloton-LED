"""The name page's highlights, chosen by score.

Every page shows the total, two headline facts of different kinds, then an instructor top three: six
highlights, as before. Every fact the other steps build (time frames, measures and bests, comparisons,
events; frame_facts) is a candidate with a kind and a score: a base score for its kind (KINDS), plus a
bonus for a first place, a big change or a fresh record. A fact shown lately scores lower (a cool-down
of COOLDOWN_PASSES pages, remembered in the dashboard cache so a restart doesn't repeat it), so the best
facts take turns. The top three is a headline's own when that headline is a discipline's, else the
general ones take turns (frame_rankings). On the day of the account's anniversary, it is the first headline
(anniversary_fact).
Everything comes from the dashboard cache and the workout log (peloton.activity.frame_stats); the log's
figures stay empty until its backfill is complete, and then the page falls back to what's left.
"""
from datetime import date

from .instructors import top_instructors
from .selection import normalize_discipline
from .totals import total_workout_count

RANKS = ('TOP', '2ND', '3RD')
# The frames whose facts are candidates, in the order the general top threes take turns. Not 'week'
# (the Goals screen covers it). 'events' (dates, not a window) has no top three of its own.
FRAME_ORDER = ('all', '30d', 'year', '90d', 'last_year', 'last_week', 'events')
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
# Events. A discipline is "since" or a "comeback" only with this many workouts behind it; "since" shows
# after MIN_SINCE_DAYS without one (at most MAX_SINCE_FACTS of them); an instructor's last class
# after MIN_LAST_WITH_DAYS (their 5+ workouts, at most MAX_LAST_WITH_FACTS); a comeback is a workout in
# the last EVENT_WINDOW_DAYS that follows a gap of MIN_COMEBACK_DAYS; a first is a discipline begun in
# that window by a rider whose history goes back MIN_HISTORY_DAYS further.
MIN_EVENT_WORKOUTS = 5
MIN_SINCE_DAYS = 14
# Past this many days a discipline is one left behind, not news (and the number is four digits).
MAX_SINCE_DAYS = 999
MAX_SINCE_FACTS = 2
MIN_LAST_WITH_DAYS = 30
MAX_LAST_WITH_FACTS = 2
EVENT_WINDOW_DAYS = 14
MIN_COMEBACK_DAYS = 60
MIN_HISTORY_DAYS = 30
# Scoring. A kind's (group, base score); two headlines are never the same group. A kind is the part of a
# fact's `kind` before a colon ('instructor:jess' is 'instructor'), so a kind's per-subject facts share it.
KINDS = {
    'on_this_day': ('event', 90), 'comeback': ('event', 85), 'new_discipline': ('event', 85),
    'since': ('event', 60), 'last_class_with': ('event', 50),
    'rank': ('record', 80), 'streak': ('record', 65), 'busiest_week': ('record', 55),
    'busiest_month': ('record', 55), 'busiest_day': ('record', 55), 'best_output': ('record', 55),
    'best_strive': ('record', 55), 'longest': ('record', 50),
    'comparison': ('trend', 70),
    'subject': ('discipline', 45), 'most': ('discipline', 40), 'share': ('discipline', 35),
    'top_discipline': ('discipline', 40),
    'total': ('count', 45), 'active_days': ('count', 30),
    'classes': ('variety', 30), 'instructors': ('variety', 30), 'instructor': ('instructor', 35),
    'average_week': ('average', 25), 'average_class': ('average', 20),
    'anniversary': ('anniversary', 100),
}
# A first place ("BEST EVER") scores this much more; a comparison up to MAX_COMPARE_BONUS more (each
# percent of change is COMPARE_BONUS_PER_CHANGE / 100); a best set within RECENT_RECORD_DAYS this much.
RANK_FIRST_BONUS = 15
MAX_COMPARE_BONUS = 30
COMPARE_BONUS_PER_CHANGE = 50
RECENT_RECORD_BONUS = 30
RECENT_RECORD_DAYS = 14
# Only these frames' bests are records worth the bonus: the busiest day of the last 30 or 90 days is
# nearly always a recent one, which says nothing.
RECORD_FRAMES = ('all', 'year')
# A fact just shown loses COOLDOWN_PENALTY, which wears off evenly over COOLDOWN_PASSES name pages
# (shown ones: the pass counter is the dashboard's own, saved with the cache, so a restart keeps it).
COOLDOWN_PASSES = 20
COOLDOWN_PENALTY = 100
# Showing a kind (HIGHEST OUTPUT, from any frame) also cools the whole kind down, less, so one kind's
# many frames don't take every page in turn.
KIND_COOLDOWN_PENALTY = 40
# Headlines on a page, between the total and the instructor top three.
HEADLINES = 2
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
    if key == 'events':
        key = 'all'     # the events have no instructor ranking of their own: the page keeps the all-time one
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
            headline = {'kind': f'subject:{slug}', 'label': noun, 'value': f'{found["workouts"]} WORKOUTS',
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
        facts.append({'kind': 'average_class', 'label': title, 'value': f'{round(minutes / workouts)} MIN AVERAGE',
                      'lines': ['AVERAGE CLASS', _plural(round(minutes / workouts), 'MINUTE')]})
    if (stats.get('days') or 0) >= MIN_AVERAGE_WEEK_DAYS:
        average = workouts * 7 / stats['days']
        facts.append({'kind': 'average_week', 'label': title, 'value': f'{average:.1f} PER WEEK',
                      'lines': ['AVERAGE WEEK', f'{average:.1f} WORKOUTS']})
    done = sorted((stats.get('disciplines') or {}).items(), key=lambda item: (-item[1], item[0]))
    if workouts >= MIN_SHARE_WORKOUTS and done and done[0][1] >= MIN_COUNT:
        facts.append({'kind': 'share', 'label': title, 'value': f'{done[0][0]} {done[0][1]} OF {workouts}',
                      'lines': [_share_line(done[0][1], workouts, done[0][0]), 'OF WORKOUTS']})
    rank = stats.get('rank')
    if rank and rank['rank'] <= MAX_SHOWN_RANK:
        words = 'BEST EVER' if rank['rank'] == 1 else f'{ORDINALS[rank["rank"]]} BEST EVER'
        facts.append({'kind': 'rank', 'label': title, 'value': f'{words} / {workouts}',
                      'lines': [words, _plural(workouts, 'WORKOUT')],
                      'bonus': RANK_FIRST_BONUS if rank['rank'] == 1 else 0})
    for key, label, least, month in (('busiest_day', 'BUSIEST DAY', MIN_BEST_DAY, False),
                                     ('busiest_week', 'BUSIEST WEEK', MIN_BEST_PERIOD, False),
                                     ('busiest_month', 'BUSIEST MONTH', MIN_BEST_PERIOD, True)):
        best = stats.get(key)
        if best and best['count'] >= least:
            when = _date_words(best['date'], month_only=month)
            facts.append({'kind': key, 'label': label, 'value': f'{best["count"]} / {when}', 'when': best['date'],
                          'lines': [_plural(best['count'], 'WORKOUT'), f'OF {when}' if key == 'busiest_week' else when]})
    longest = stats.get('longest')
    if longest and longest.get('minutes'):
        facts.append({'kind': 'longest', 'label': 'LONGEST WORKOUT', 'value': f'{longest["minutes"]} MIN',
                      'lines': [_plural(longest['minutes'], 'MINUTE'), discipline_name(longest.get('discipline') or '')]})
    output = stats.get('best_output')
    if output:
        kind = discipline_name(output.get('discipline') or '')
        facts.append({'kind': 'best_output', 'label': 'HIGHEST OUTPUT', 'value': f'{_round_half_up(output["kj"])} KJ',
                      'lines': [f'{_round_half_up(output["kj"]):,} KJ',
                                f'{output["minutes"]} MIN {kind}' if output.get('minutes') else kind]})
    strive = stats.get('best_strive')
    if strive:
        facts.append({'kind': 'best_strive', 'label': 'BEST STRIVE', 'value': f'{_round_half_up(strive["points"])} POINTS',
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
    return {'kind': 'comparison', 'label': label, 'value': f'{now} VS {before["workouts"]}',
            'bonus': min(MAX_COMPARE_BONUS, int(abs(change) / before['workouts'] * COMPARE_BONUS_PER_CHANGE)),
            'lines': [f'{now:,} VS {before["workouts"]:,}', f'{change:+,} WORKOUTS']}


def _days_between(iso, today):
    return (today - date.fromisoformat(iso)).days


def _fit_line(*options):
    """The first of the candidate lines that fits a label's width (the last, shortest, if none do)."""
    return next((line for line in options if len(line) <= MAX_LABEL_CHARS), options[-1])


def _short_noun(slug):
    """'STRENGTH', or the last word of a long discipline name ('BOOTCAMP' for TREAD BOOTCAMP)."""
    noun = discipline_name(slug)
    return noun if len(noun) <= MAX_LABEL_CHARS - 5 else noun.split()[-1]


def anniversary_fact(snapshot):
    """The anniversary highlight, or None: username_details pins it as the headline of every pass all
    day, because it's too rare to leave to a turn."""
    years = (snapshot.get('events') or {}).get('anniversary')
    if not years:
        return None
    return {'kind': 'anniversary', 'label': 'ANNIVERSARY', 'value': f'{years} ON PELOTON', 'lines': [_plural(years, 'YEAR'), 'ON PELOTON']}


def event_facts(snapshot):
    """The facts measured from a date (frame_stats' neighbour, activity.event_stats), in the order
    they're shown (the anniversary is pinned, not here: anniversary_fact): this day in an earlier year, a comeback, a first,
    time since a discipline's last workout, the last class with a most-seen instructor. Every one has
    a threshold above, so nothing shows a 1 or a 0 unless that's the point."""
    events = snapshot.get('events') or {}
    facts = []
    today = date.fromisoformat(events['today']) if events.get('today') else None
    if today is None:
        return facts
    for found in events.get('on_this_day') or []:
        noun = discipline_name(found['discipline']) if found.get('discipline') else 'WORKOUT'
        facts.append({'kind': 'on_this_day', 'label': 'ON THIS DAY', 'value': f'{found["years_ago"]} YEARS AGO / {noun}',
                      'lines': [f'{_plural(found["years_ago"], "YEAR")} AGO',
                                _fit_line(f'{found["minutes"]} MIN {noun}', f'{found["minutes"]} MIN {noun.split()[-1]}',
                                          noun.split()[-1]) if found['minutes'] else noun.split()[-1]]})
        break
    disciplines = events.get('disciplines') or {}
    ranked = sorted(disciplines, key=lambda slug: (-disciplines[slug]['workouts'], slug))
    began = events.get('first_ever')
    for slug in ranked:
        found = disciplines[slug]
        if found['workouts'] < MIN_EVENT_WORKOUTS or not found.get('before_last'):
            continue
        gap = (date.fromisoformat(found['last']) - date.fromisoformat(found['before_last'])).days
        if _days_between(found['last'], today) <= EVENT_WINDOW_DAYS and gap >= MIN_COMEBACK_DAYS:
            after = f'AFTER {gap} DAYS' if gap <= MAX_SINCE_DAYS else f'AFTER {round(gap / 365)} YEARS'
            facts.append({'kind': f'comeback:{slug}', 'label': 'COMEBACK', 'value': f'{slug} {after}', 'lines': [_short_noun(slug), after]})
    for slug in sorted(disciplines, key=lambda name: (disciplines[name]['first'], name)):
        found = disciplines[slug]
        if (began and _days_between(found['first'], today) <= EVENT_WINDOW_DAYS
                and (date.fromisoformat(found['first']) - date.fromisoformat(began)).days >= MIN_HISTORY_DAYS):
            facts.append({'kind': f'new_discipline:{slug}', 'label': 'NEW DISCIPLINE', 'value': f'{slug} FIRST TIME',
                          'lines': [_short_noun(slug), 'FIRST TIME']})
    since = 0
    for slug in ranked:
        found = disciplines[slug]
        days = _days_between(found['last'], today)
        if found['workouts'] >= MIN_EVENT_WORKOUTS and MIN_SINCE_DAYS <= days <= MAX_SINCE_DAYS and since < MAX_SINCE_FACTS:
            since += 1
            facts.append({'kind': f'since:{slug}', 'label': 'SINCE', 'value': f'{days} DAYS SINCE {slug}',
                          'lines': [f'{days:,} DAYS SINCE', _fit_line(f'LAST {discipline_name(slug)}',
                                                                      f'LAST {discipline_name(slug).split()[-1]}')]})
    names = snapshot.get('instructor_names') or {}
    instructors = events.get('instructors') or {}
    last_with = 0
    for identity in sorted(instructors, key=lambda who: (-instructors[who]['workouts'], who)):
        found = instructors[identity]
        if (names.get(identity) and found['workouts'] >= MIN_EVENT_WORKOUTS
                and _days_between(found['last'], today) >= MIN_LAST_WITH_DAYS and last_with < MAX_LAST_WITH_FACTS):
            last_with += 1
            facts.append({'kind': f'last_class_with:{identity}', 'label': 'LAST CLASS WITH', 'value': f'{names[identity]} / {found["last"]}',
                          'lines': [names[identity].upper(), _date_words(found['last'])]})
    return facts


def frame_facts(snapshot, key):
    """The single-highlight facts a frame has enough data for, in the order its visits show them.
    All time: the top discipline. Others: workouts and time, the most-done discipline (when it
    isn't the all-time top, which TOP DISCIPLINE already says), active days. Then different classes
    and different instructors, for every frame."""
    if key == 'events':
        return event_facts(snapshot)
    facts = []
    favorite = _all_time_top_discipline(snapshot)
    stats = (snapshot.get('time_frames') or {}).get(key) or {}
    title = frame_words(key, stats)[0] if key == 'all' or stats else None
    if key == 'all':
        if favorite:
            facts.append({'kind': 'top_discipline', 'label': 'TOP DISCIPLINE', 'value': f'{favorite[0]} / {favorite[1]:,}',
                          'lines': [favorite[0].upper(), _plural(favorite[1], 'WORKOUT')]})
    elif stats and stats.get('workouts'):
        workouts, minutes = stats['workouts'], stats.get('minutes') or 0
        facts.append({'kind': 'total', 'label': title, 'value': f'{workouts} WORKOUTS / {minutes} MIN',
                      'lines': [_plural(workouts, 'WORKOUT'), _time_line(minutes)]})
        done = sorted((stats.get('disciplines') or {}).items(), key=lambda item: (-item[1], item[0]))
        if (done and done[0][1] >= MIN_COUNT
                and (not favorite or done[0][0] != normalize_discipline(favorite[0]))):
            slug, count = done[0]
            # MOST IN 30 DAYS is exactly 15 characters, the most a label holds.
            facts.append({'kind': 'most', 'label': f'MOST {frame_words(key, stats)[1]}',
                          'value': f'{discipline_name(slug)} / {count}',
                          'lines': [discipline_name(slug), _plural(count, 'WORKOUT')]})
        if (stats.get('active_days') or 0) >= MIN_COUNT and stats.get('days'):
            facts.append({'kind': 'active_days', 'label': title, 'value': f'{stats["active_days"]} / {stats["days"]} DAYS',
                          'lines': ['ACTIVE DAYS', f'{stats["active_days"]:,} OF {stats["days"]:,}']})
    if stats:
        if (stats.get('classes') or 0) >= MIN_COUNT:
            facts.append({'kind': 'classes', 'label': title, 'value': f'{stats["classes"]:,} DIFFERENT CLASSES',
                          'lines': [f'{stats["classes"]:,} DIFFERENT', 'CLASSES']})
        if (stats.get('instructors') or 0) >= MIN_COUNT:
            facts.append({'kind': 'instructors', 'label': title, 'value': f'{stats["instructors"]:,} DIFFERENT INSTRUCTORS',
                          'lines': [f'{stats["instructors"]:,} DIFFERENT', 'INSTRUCTORS']})
        facts.extend(_measure_facts(stats, title))
        comparison = _comparison_fact(key, stats)
        if comparison:
            facts.append(comparison)
        facts.extend(_instructor_facts(snapshot, stats, title))
    best_weekly = (snapshot.get('streaks') or {}).get('best_weekly')
    if key == 'all' and isinstance(best_weekly, int) and best_weekly >= MIN_STREAK_WEEKS:
        facts.append({'kind': 'streak', 'label': title, 'value': f'{best_weekly} WEEK STREAK',
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
            facts.append({'kind': f'instructor:{identity}', 'label': title, 'value': f'{name} / {found["minutes"]} MIN',
                          'lines': [name.upper(), _time_line(found.get('minutes') or 0)]})
    return facts


def kind_of(fact):
    return fact['kind'].split(':')[0]


def fact_score(fact, today=None, passes=0, shown=None):
    """A candidate's score: its kind's base, its own bonus, a bonus for a best set lately (the fact's
    `when`, within RECENT_RECORD_DAYS of `today`, in a RECORD_FRAMES frame), less the cool-down if shown in
    the last COOLDOWN_PASSES."""
    score = KINDS[kind_of(fact)][1] + fact.get('bonus', 0)
    if (today and fact.get('when') and fact['key'].split(':')[0] in RECORD_FRAMES
            and 0 <= _days_between(fact['when'], today) <= RECENT_RECORD_DAYS):
        score += RECENT_RECORD_BONUS
    for key, penalty in ((fact['key'], COOLDOWN_PENALTY), (kind_key(fact), KIND_COOLDOWN_PENALTY)):
        last = (shown or {}).get(key)
        if last is not None and passes - last < COOLDOWN_PASSES:
            score -= penalty * (1 - max(0, passes - last) / COOLDOWN_PASSES)
    return score


def kind_key(fact):
    return f'kind:{kind_of(fact)}'


def shown_keys(details):
    """What a name page's showing records: each chosen fact's key and its kind's."""
    return [key for detail in details if detail.get('key') for key in (detail['key'], kind_key(detail))]


def _counter(snapshot):
    """(passes, shown): how many name pages have been shown, and the count at each fact's last showing."""
    passes, shown = snapshot.get('name_facts_passes'), snapshot.get('name_facts_shown')
    ok = isinstance(passes, int) and not isinstance(passes, bool)
    return (passes if ok else None), (shown if isinstance(shown, dict) and ok else {})


def scored_facts(snapshot):
    """Every candidate headline as (score, fact, ranking), best first (ties by key). `ranking` is the
    discipline's top three for a discipline's headline, else None. Each fact has its `key`
    ('30d:rank', 'events:since:yoga'), the same from one refresh to the next, for the cool-down.
    Facts that read the same (a busiest day that is the same in the 30-day, 90-day and year frames) are
    one candidate: the one that scores best before any cool-down, the earlier frame on a tie."""
    passes, shown = _counter(snapshot)
    today = (snapshot.get('events') or {}).get('today')
    today = date.fromisoformat(today) if today else None
    best = {}
    for frame in FRAME_ORDER:
        pairs = [(fact, None) for fact in frame_facts(snapshot, frame)] + frame_subjects(snapshot, frame)
        for fact, ranking in pairs:
            fact = dict(fact, key=f'{frame}:{fact["kind"]}')
            same = (fact['kind'], tuple(fact['lines']))
            fresh = fact_score(fact, today)
            if same not in best or fresh > best[same][0]:
                best[same] = (fresh, fact, ranking)
    found = [(fact_score(fact, today, passes or 0, shown), fact, ranking) for _, fact, ranking in best.values()]
    return sorted(found, key=lambda item: (-item[0], item[1]['key']))


def _general_ranking(snapshot, turn):
    """The general instructor top threes (all time, 30 days, ...) take turns, one per page."""
    rankings = [ranking for frame in FRAME_ORDER if frame != 'events' for ranking in frame_rankings(snapshot, frame)]
    return rankings[turn % len(rankings)] if rankings else []


def record_name_facts(passes, shown, keys):
    """The counter after a name page showed `keys`: one more page, those facts stamped with it, and
    facts whose cool-down is over forgotten."""
    passes += 1
    shown = {key: at for key, at in shown.items() if passes - at < COOLDOWN_PASSES}
    shown.update({key: passes for key in keys})
    return passes, shown


def username_details(snapshot, pass_index=0):
    """This page's highlights: the total, two headlines (the best-scoring facts, of different groups;
    the anniversary first on its day), then an instructor top three. `pass_index` turns the top threes
    when the snapshot has no name-page counter (a preview)."""
    details = []
    total = total_workout_count(snapshot.get('totals') or {})
    if total is not None:
        details.append({'label': 'TOTAL WORKOUTS', 'value': f'{total:,}',
                        'lines': [f'{total:,}'], 'font_key': 'big', 'color_key': 'gold'})
    chosen, rankings = [], []
    pinned = anniversary_fact(snapshot)
    if pinned:
        chosen.append(pinned)
    groups = {KINDS[kind_of(fact)][0] for fact in chosen}
    for _, fact, ranking in scored_facts(snapshot):
        if len(chosen) == HEADLINES:
            break
        if KINDS[kind_of(fact)][0] not in groups:
            chosen.append(fact)
            groups.add(KINDS[kind_of(fact)][0])
            rankings.append(ranking)
    passes = _counter(snapshot)[0]
    ranking = next((own for own in rankings if own), None) or _general_ranking(
        snapshot, pass_index if passes is None else passes)
    return details + chosen + ranking
