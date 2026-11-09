"""The name page's highlights, varied from pass to pass.

Every pass shows the total and this week, then one fact about disciplines and one instructor
ranking (three highlights), each picked in turn by the rotation's pass number from the ones there's
enough data for. So a full page is six highlights, as before, whatever it shows. Everything comes
from the dashboard cache and the workout log; the log's figures stay empty until its backfill is
complete, and then the page falls back to what's left.
"""
from .instructors import top_instructors
from .selection import normalize_discipline
from .totals import total_workout_count

RANKS = ('TOP', '2ND', '3RD')
# A ranking for the last 30 days or one discipline needs three instructors with at least this many
# classes each; fewer is too little to call a ranking (e.g. one strength class in 30 days).
MIN_RANKED_CLASSES = 2
# The last 30 days' most-done discipline needs at least this many workouts.
MIN_RECENT_WORKOUTS = 2


def discipline_name(slug):
    """'bike_bootcamp' -> 'BIKE BOOTCAMP', as the Lifetime pages label it."""
    return str(slug).replace('_', ' ').upper()


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


def instructor_rankings(snapshot):
    """Every instructor ranking there's enough data for, in rotation order: all time, the last 30 days,
    then each discipline, most-done first. Each is a list of up to three highlights."""
    names = snapshot.get('instructor_names') or {}
    rankings = [_instructor_ranking(lambda rank: f'{rank} INSTRUCTOR', snapshot.get('instructor_counts'),
                                    names, 1)]
    recent = snapshot.get('recent_activity') or {}
    rankings.append(_instructor_ranking(lambda rank: f'{rank} IN 30 DAYS', recent.get('instructor_counts'),
                                        names, MIN_RANKED_CLASSES))
    by_discipline = snapshot.get('discipline_instructor_counts') or {}
    for slug in sorted(by_discipline, key=lambda key: (-sum(by_discipline[key].values()), key)):
        noun = discipline_name(slug)
        # 3RD TREAD BOOTCAMP is too wide for the label; the screen falls back to 3RD BOOTCAMP.
        rankings.append(_instructor_ranking(lambda rank, noun=noun: f'{rank} {noun}', by_discipline[slug],
                                            names, MIN_RANKED_CLASSES,
                                            short_for=lambda rank, noun=noun: f'{rank} {noun.split()[-1]}'))
    return [ranking for ranking in rankings if ranking]


def discipline_facts(snapshot):
    """Every single-highlight fact there's data for, in rotation order: the all-time top
    discipline, the last 30 days' workouts and minutes, and their most done (when it differs)."""
    facts = []
    totals = snapshot.get('totals') or {}
    disciplines = [(label, count) for label, count in totals.items()
                   if label != 'Total Workouts' and isinstance(count, int) and not isinstance(count, bool)]
    favorite = max(disciplines, key=lambda item: item[1], default=None)
    if favorite:
        facts.append({'label': 'TOP DISCIPLINE', 'value': f'{favorite[0]} / {favorite[1]:,}',
                      'lines': [favorite[0].upper(), _plural(favorite[1], 'WORKOUT')]})
    recent = snapshot.get('recent_activity') or {}
    workouts = recent.get('workouts') or 0
    if workouts:
        minutes = recent.get('minutes') or 0
        facts.append({'label': 'LAST 30 DAYS', 'value': f'{workouts} WORKOUTS / {minutes} MIN',
                      'lines': [_plural(workouts, 'WORKOUT'), _plural(minutes, 'MINUTE')]})
    done = sorted((recent.get('disciplines') or {}).items(), key=lambda item: (-item[1], item[0]))
    # The last 30 days' favourite only when it isn't the all-time one, which TOP DISCIPLINE already says.
    if (done and done[0][1] >= MIN_RECENT_WORKOUTS
            and (not favorite or done[0][0] != normalize_discipline(favorite[0]))):
        slug, count = done[0]
        # 15 characters, the most a label holds.
        facts.append({'label': 'MOST IN 30 DAYS', 'value': f'{discipline_name(slug)} / {count}',
                      'lines': [discipline_name(slug), _plural(count, 'WORKOUT')]})
    return facts


def username_details(snapshot, pass_index=0):
    """This pass's highlights: the total, this week, then the pass's discipline fact and
    instructor ranking."""
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
    facts = discipline_facts(snapshot)
    if facts:
        details.append(facts[pass_index % len(facts)])
    rankings = instructor_rankings(snapshot)
    if rankings:
        details.extend(rankings[pass_index % len(rankings)])
    return details
