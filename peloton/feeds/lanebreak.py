"""Lanebreak (Peloton's internal name: Odyssey) from Peloton's GraphQL gateway: a run's score, difficulty and
share of beats hit, its place on its track's leaderboard, and the machine's lanes. Shapes: docs/PELOTON-API.md.

Stdlib only. Every parser returns None (or skips an entry) for anything it can't read, since this is an
undocumented API and the cache can hold anything.
"""

import re

# The `peloton-platform` header picks the machine: the track list, lanes and leaderboards differ by machine.
TREAD_PLATFORM = 'home_tread'
BIKE_PLATFORM = 'home_bike'
_PLATFORMS = {'cycling': BIKE_PLATFORM, 'walking': TREAD_PLATFORM, 'running': TREAD_PLATFORM}
# The performance-graph series that decides the lane: incline on the Tread, resistance on the bike.
LANE_METRICS = {TREAD_PLATFORM: ('incline', 'minIncline', 'maxIncline'), BIKE_PLATFORM: ('resistance', 'minResistance', 'maxResistance')}
LANES = 6
# A difficulty is an enum such as WALKING or INTERMEDIATE (the longest seen, 12 characters).
_DIFFICULTY = re.compile(r'^[A-Z][A-Z_]{1,15}$')
_TAGS = re.compile(r'<[^>]*>')
_LENGTH = re.compile(r'^\s*(\d+)\s*min\s+', re.IGNORECASE)
_VOLUME = re.compile(r'\s+vol\.?\s*(\d+)\s*$', re.IGNORECASE)


def platform_for(fitness_discipline) -> str | None:
    """The machine a Lanebreak ran on, from the workout's `fitness_discipline`; None for anything else."""
    return _PLATFORMS.get(str(fitness_discipline or '').strip().lower())


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _data(body, *path):
    """body['data'][path...], or None when any step is missing or not an object."""
    node = body.get('data') if isinstance(body, dict) else None
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def parse_run(body) -> dict | None:
    """`odysseyWorkout`'s run as {'score', 'difficulty', 'completion'} (completion 0-1, the share of beats
    hit); None when it isn't a Lanebreak (`OdysseyItemNotFoundError`) or anything is unreadable."""
    run = _data(body, 'odysseyWorkout', 'workout')
    if not isinstance(run, dict):
        return None
    score, difficulty, completion = run.get('score'), run.get('difficulty'), run.get('completionPercent')
    if not (_number(score) and score >= 0 and isinstance(difficulty, str) and _DIFFICULTY.match(difficulty)):
        return None
    if not (_number(completion) and 0 <= completion <= 1):
        completion = None
    return {'score': int(score), 'difficulty': difficulty, 'completion': completion}


def _name(text) -> str:
    """A track or title name for matching: tags stripped (`</b>Pop Punk</b>`), case and spacing folded."""
    return ' '.join(_TAGS.sub(' ', str(text or '')).split()).lower()


def title_key(title) -> tuple[str, int, int | None] | None:
    """(name, minutes, volume) from a Lanebreak workout's title: `15 min Pop Punk` -> ('pop punk', 15, None),
    `20 min Red Hot Chili Peppers Vol. 2` -> ('red hot chili peppers', 20, 2). None without a length or a name,
    and for the untitled `Lanebreak Ride` the bike gave older rides."""
    text = str(title or '').strip()
    length = _LENGTH.match(text)
    if not length:
        return None
    rest = text[length.end() :]
    volume = _VOLUME.search(rest)
    if volume:
        rest = rest[: volume.start()]
    name = _name(rest)
    if not name or name in ('lanebreak ride', 'lanebreak walk', 'lanebreak run'):
        return None
    return name, int(length.group(1)), int(volume.group(1)) if volume else None


# At most this many same-named tracks are checked for the run (bike: three 20-minute "Top 50 Music: Remixed").
MAX_TRACK_CANDIDATES = 3


def track_candidates(body, title) -> list[str]:
    """The `levels` track list's IDs with a workout title's name, length (to the minute) and volume; [] when none
    match or the title has no track name. Several can match (bike: two 20-minute "Low Impact Pop"): the caller
    asks each for the rider's own runs (`owns_run`), since the leaderboard ranks a run on any track it's given."""
    key = title_key(title)
    levels = _data(body, 'levels', 'levels')
    if key is None or not isinstance(levels, list):
        return []
    name, minutes, volume = key
    found = []
    for level in levels:
        if not isinstance(level, dict) or not isinstance(level.get('id'), str) or not _number(level.get('duration')):
            continue
        level_volume = level.get('volume') if _number(level.get('volume')) else None
        if _name(level.get('title')) == name and round(level['duration'] / 60) == minutes and level_volume == volume:
            found.append(level['id'])
    return found


def owns_run(body, workout_id) -> bool:
    """Whether `odysseyUserLeaderboard` (the rider's own runs on one track) lists this workout: only the run's own
    track does (`count: 0` on another). False for anything unreadable."""
    rows = _data(body, 'odysseyUserLeaderboard', 'leaderboard', 'leaderboard')
    return isinstance(rows, list) and any(isinstance(row, dict) and row.get('workoutId') == workout_id for row in rows)


def parse_place(body, workout_id) -> dict | None:
    """The run's place from `odysseyLeaderboard`'s `extraWorkoutEntry`: {'place', 'of'} (place 1-based). None
    unless the entry is this workout and the board has 2 or more runs: a made-up track answers `count: 1` (the run
    alone). A real but wrong track answers a plausible place, so the track must be the run's own (`owns_run`)."""
    board = _data(body, 'odysseyLeaderboard', 'leaderboard')
    if not isinstance(board, dict):
        return None
    entry, count = board.get('extraWorkoutEntry'), board.get('count')
    if not isinstance(entry, dict) or entry.get('workoutId') != workout_id:
        return None
    rank = entry.get('rank')
    if not (_number(rank) and _number(count) and count >= 2 and 0 <= rank < count):
        return None
    return {'place': int(rank) + 1, 'of': int(count)}


def parse_lanes(body, platform) -> dict | None:
    """`odysseyConfiguration` as {difficulty: [(low, high), ...6 lanes]}, the band of incline (Tread) or
    resistance (bike) each lane covers; None when unreadable. A difficulty without 6 readable lanes is left out."""
    metric = LANE_METRICS.get(platform)
    configs = _data(body, 'odysseyConfiguration', 'difficultyConfigs')
    if metric is None or not isinstance(configs, list):
        return None
    _, low_key, high_key = metric
    bands = {}
    for config in configs:
        if not isinstance(config, dict) or not isinstance(config.get('slug'), str) or not isinstance(config.get('laneConfigs'), list):
            continue
        lanes = sorted(
            (lane for lane in config['laneConfigs'] if isinstance(lane, dict) and _number(lane.get('index'))),
            key=lambda lane: lane['index'],
        )
        pairs = [(lane.get(low_key), lane.get(high_key)) for lane in lanes]
        if len(pairs) == LANES and all(_number(lo) and _number(hi) and lo <= hi for lo, hi in pairs):
            bands[config['slug']] = pairs
    return bands or None


def metric_values(perf, slug) -> list:
    """One performance-graph series' values (`incline`, `resistance`), or []."""
    for metric in (perf or {}).get('metrics') or []:
        if isinstance(metric, dict) and metric.get('slug') == slug and isinstance(metric.get('values'), list):
            return metric['values']
    return []


def lane_samples(values, bands) -> list[int] | None:
    """How many graph samples fell in each lane: a value inside a band counts there, one between bands (the
    Tread's 0.25%) goes to the nearest band's middle. None without any number to place."""
    counts = [0] * len(bands)
    for value in values:
        if not _number(value):
            continue
        inside = [i for i, (lo, hi) in enumerate(bands) if lo <= value <= hi]
        lane = inside[0] if inside else min(range(len(bands)), key=lambda i: abs(value - (bands[i][0] + bands[i][1]) / 2))
        counts[lane] += 1
    return counts if sum(counts) else None
