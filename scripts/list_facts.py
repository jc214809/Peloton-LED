"""Print every name-page fact for a workout log, with no panel and no API calls.

    python scripts/list_facts.py --demo
    python scripts/list_facts.py --log /var/lib/peloton-led/dashboard-cache-joel.workouts.json --tz America/New_York
    python scripts/list_facts.py --log LOG --cache CACHE   # the discipline totals and names from the cache

Shows each time frame's figures, then every highlight a frame has enough data for (headline facts,
instructor top threes and one page per discipline, as the board would draw them), then what the first passes show.
A log that isn't complete (its backfill unfinished) has no time-frame figures on the board; use
--assume-complete to look at one anyway.
"""
import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from peloton.activity import frame_stats  # noqa: E402
from peloton.username_facts import (FRAME_ORDER, frame_facts, frame_rankings, frame_subjects,  # noqa: E402
                                    username_details, username_frames)
from peloton.workout_log import WorkoutLog  # noqa: E402

DEMO_DISCIPLINES = (('cycling', 5), ('strength', 4), ('stretching', 2), ('walking', 2), ('running', 1),
                    ('yoga', 1), ('meditation', 1), ('bike_bootcamp', 1))
DEMO_INSTRUCTORS = {'jess': 'Jess Sims', 'andy': 'Andy Speer', 'adrian': 'Adrian Williams', 'cody': 'Cody Rigsby',
                    'robin': 'Robin Arzon', 'tunde': 'Tunde Oyeneyin', 'emma': 'Emma Lovewell',
                    'matt': 'Matt Wilpers', 'ally': 'Ally Love', 'hannah': 'Hannah Corbin'}


def demo_log(now, years=3, seed=7):
    """About five workouts a week for `years` years: classes drawn from a pool (so some repeat),
    a few instructors much more often than the rest, and a quiet spell."""
    rng = random.Random(seed)
    log = WorkoutLog('unused')
    instructors = list(DEMO_INSTRUCTORS)
    weights = [10, 8, 6, 5, 4, 3, 2, 2, 1, 1]
    disciplines, discipline_weights = zip(*DEMO_DISCIPLINES)
    workouts = []
    day = now - timedelta(days=365 * years)
    while day < now:
        quiet = (now - day).days in range(200, 240)
        if not quiet and rng.random() < 5 / 7:
            discipline = rng.choices(disciplines, discipline_weights)[0]
            instructor = rng.choices(instructors, weights)[0]
            stamp = day.replace(hour=rng.choice((6, 7, 12, 17, 18)), minute=rng.randrange(60))
            ride = {'fitness_discipline': discipline, 'duration': rng.choice((600, 1200, 1800, 2700)),
                    'id': f'class-{discipline}-{rng.randrange(60)}',
                    'instructor': {'id': instructor, 'name': DEMO_INSTRUCTORS[instructor]}}
            workouts.append({'id': f'w{len(workouts)}', 'status': 'COMPLETE', 'start_time': int(stamp.timestamp()),
                             'fitness_discipline': discipline, 'ride': ride})
        day += timedelta(days=1)
    log.merge(workouts)
    return log


def snapshot_for(log, tzname, now, cache_path=None, assume_complete=False):
    """What the dashboard would publish for the name page: the log's figures, the discipline totals
    (from the cache, else counted from the log) and this week's progress."""
    if assume_complete:
        log.backfill['complete'] = True
    snapshot = log.derived(tzname=tzname, now=now)
    totals = None
    if cache_path:
        from peloton.cache import load_snapshot
        cached = load_snapshot(cache_path)
        if cached is None:
            raise SystemExit(f'Could not read a dashboard cache from {cache_path}')
        totals = cached['totals']
    if totals is None:
        counts = {}
        for row in log.workouts.values():
            if row.get('discipline') and row.get('status') in (None, 'COMPLETE'):
                label = row['discipline'].replace('_', ' ').title()
                counts[label] = counts.get(label, 0) + 1
        totals = {'Total Workouts': sum(counts.values()), **counts}
    snapshot['totals'] = totals
    return snapshot


def show(snapshot, passes):
    frames = snapshot.get('time_frames') or {}
    if not frames:
        print('No time-frame figures: the log is empty or its backfill is not complete (try --assume-complete).')
    for key in FRAME_ORDER + ('week',):
        stats = frames.get(key)
        if stats:
            print(f'{key:<10} workouts {stats["workouts"]:>5}  minutes {stats["minutes"]:>6}  classes {stats["classes"]:>4}'
                  f'  instructors {stats["instructors"]:>3}  active days {stats["active_days"]:>3}'
                  f'/{stats["days"] if stats["days"] is not None else "-"}')
    print()
    for key in username_frames(snapshot):
        print(f'== {key}')
        for fact in frame_facts(snapshot, key):
            print(f'   {fact["label"]:<16} {" / ".join(fact["lines"])}')
        for ranking in frame_rankings(snapshot, key):
            print('   ' + '  |  '.join(f'{d["label"]}: {d["lines"][0]} ({d["lines"][1]})' for d in ranking))
        for headline, ranking in frame_subjects(snapshot, key):
            print(f'   {headline["label"]:<16} {" / ".join(headline["lines"])}   then   '
                  + '  |  '.join(f'{d["label"]}: {d["lines"][0]} ({d["lines"][1]})' for d in ranking))
    print()
    for index in range(passes):
        details = username_details(snapshot, index)
        print(f'pass {index}: ' + ' | '.join(d['label'] for d in details))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--log', help='a rider\'s workout log (<cache>.workouts.json)')
    source.add_argument('--demo', action='store_true', help='a synthetic three-year log')
    parser.add_argument('--cache', help='that rider\'s dashboard cache, for the discipline totals')
    parser.add_argument('--tz', help='display timezone (default: UTC)')
    parser.add_argument('--passes', type=int, default=8, help='how many passes to show (default 8)')
    parser.add_argument('--assume-complete', action='store_true', help='treat an unfinished log as complete')
    options = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    if options.demo:
        log, assume = demo_log(now), True
    else:
        path = Path(options.log)
        if not path.exists():
            raise SystemExit(f'No workout log at {path}')
        log, assume = WorkoutLog.load(path), options.assume_complete
        if not log.workouts:
            raise SystemExit(f'{path} is empty or not a workout log this version can read')
    show(snapshot_for(log, options.tz, now, options.cache, assume), options.passes)
    return 0


if __name__ == '__main__':
    sys.exit(main())
