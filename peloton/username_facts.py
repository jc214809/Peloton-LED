"""The name page's highlights, varied from pass to pass.

Every pass shows the total and this week, then one time frame's story: a headline fact, then that
frame's instructor top three (three highlights). Each pass takes the next frame (all time, the last
30 days, this year, ...); a frame that comes round again shows its next fact, so a full page is six
highlights, as before, whatever it shows. Everything comes from the dashboard cache and the workout
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
    """The instructor top threes a frame has enough data for, each a list of up to three
    highlights. All time starts with every class, then each discipline, most-done first; the other
    frames have one, from that frame's own classes."""
    names = snapshot.get('instructor_names') or {}
    if key == 'all':
        rankings = [_instructor_ranking(lambda rank: f'{rank} INSTRUCTOR', snapshot.get('instructor_counts'),
                                        names, 1)]
        by_discipline = snapshot.get('discipline_instructor_counts') or {}
        for slug in sorted(by_discipline, key=lambda name: (-sum(by_discipline[name].values()), name)):
            noun = discipline_name(slug)
            # 3RD TREAD BOOTCAMP is too wide for the label; the screen falls back to 3RD BOOTCAMP.
            rankings.append(_instructor_ranking(
                lambda rank, noun=noun: f'{rank} {noun}', by_discipline[slug], names, MIN_RANKED_CLASSES,
                short_for=lambda rank, noun=noun: f'{rank} {noun.split()[-1]}'))
        return [ranking for ranking in rankings if ranking]
    stats = (snapshot.get('time_frames') or {}).get(key) or {}
    if not stats:
        return []
    in_words = frame_words(key, stats)[1]
    ranking = _instructor_ranking(lambda rank: f'{rank} {in_words}', stats.get('instructor_counts'),
                                  names, MIN_RANKED_CLASSES)
    return [ranking] if ranking else []


def _all_time_top_discipline(snapshot):
    totals = snapshot.get('totals') or {}
    disciplines = [(label, count) for label, count in totals.items()
                   if label != 'Total Workouts' and isinstance(count, int) and not isinstance(count, bool)]
    return max(disciplines, key=lambda item: item[1], default=None)


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
        time_line = (_plural(round(minutes / 60), 'HOUR') if minutes >= HOURS_FROM_MINUTES
                     else _plural(minutes, 'MINUTE'))
        facts.append({'label': title, 'value': f'{workouts} WORKOUTS / {minutes} MIN',
                      'lines': [_plural(workouts, 'WORKOUT'), time_line]})
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
    return facts


def username_frames(snapshot):
    """The frames that take a turn, in order. A frame needs a headline and an instructor top three,
    so every page is six highlights: LAST WEEK, which rarely has three instructors, drops out. When
    no frame has both (a rider with no instructor data), any frame with something to show takes
    a turn, and its page is shorter."""
    facts = {key: frame_facts(snapshot, key) for key in FRAME_ORDER}
    rankings = {key: frame_rankings(snapshot, key) for key in FRAME_ORDER}
    whole = [key for key in FRAME_ORDER if facts[key] and rankings[key]]
    return whole or [key for key in FRAME_ORDER if facts[key] or rankings[key]]


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
        facts, rankings = frame_facts(snapshot, key), frame_rankings(snapshot, key)
        if facts:
            details.append(facts[visit % len(facts)])
        if rankings:
            details.extend(rankings[visit % len(rankings)])
    return details
