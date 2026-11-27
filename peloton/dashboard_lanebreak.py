"""`LanebreakMixin`: a Lanebreak's score, difficulty, beats hit, leaderboard place and time in each lane, from
Peloton's GraphQL gateway (an undocumented API: docs/PELOTON-API.md, the board's use: docs/dev/DATA.md).

Per new Lanebreak: the run (~230 bytes), the machine's slim track list (~28-44 KB) to find the track's ID, and the
place on that track's leaderboard (~300 bytes). When the title matches more than one track, the rider's own runs on
each (~100-600 bytes, at most 3) say which is the run's. Each machine's lanes are fetched once a week. Nothing here
ever fails a refresh, a 401 included: the gateway is not the API that decides the token is rejected.
"""

import logging
import time
from collections import OrderedDict

import requests

from .feeds.lanebreak import (
    LANE_METRICS,
    MAX_TRACK_CANDIDATES,
    lane_samples,
    metric_values,
    owns_run,
    parse_lanes,
    parse_place,
    parse_run,
    platform_for,
    title_key,
    track_candidates,
)
from .stats.summaries import is_lanebreak

logger = logging.getLogger('peloton-led.dashboard')

# A run or place that could not be had (a failed request; a just-finished run Odyssey doesn't know yet) is
# asked again after this long.
LANEBREAK_RETRY_SECONDS = 3600
# A machine's lanes barely change: once a week, sooner after a failure.
LANES_REFRESH_SECONDS = 7 * 24 * 3600
LANES_RETRY_SECONDS = 3600


class LanebreakMixin:
    def _init_lanebreak_state(self):
        # {workout ID: {'signature', 'run' (or None), 'place' (or None), 'retry_at' (monotonic, or None)}}
        self._lanebreaks = OrderedDict()
        # {platform: (bands by difficulty or None, monotonic time to ask again)}
        self._lane_bands = {}

    def _lanebreak_stats(self, client, workout, perf, signature):
        """The summary's `lanebreak_stats` for a finished Lanebreak: {'score', 'difficulty', 'completion',
        'place', 'lanes'} (`place` {'place', 'of'} or None, `lanes` 6 sample counts or None); None when the
        workout isn't a finished Lanebreak or its run can't be had."""
        identity = workout.get('id')
        platform = platform_for(workout.get('fitness_discipline'))
        if not identity or not platform or workout.get('status') != 'COMPLETE' or not is_lanebreak(workout):
            return None
        entry = self._lanebreak_entry(client, workout, identity, platform, signature)
        if entry['run'] is None:
            return None
        run = entry['run']
        return {**run, 'place': entry['place'], 'lanes': self._lanes_for(client, platform, run['difficulty'], perf)}

    def _lanebreak_entry(self, client, workout, identity, platform, signature):
        """The kept run and place for one Lanebreak, fetching what's missing once its retry time has come."""
        now = time.monotonic()
        entry = self._lanebreaks.get(identity)
        if entry is None or entry['signature'] != signature:
            entry = {'signature': signature, 'run': None, 'place': None, 'retry_at': None}
        if entry['run'] is None and (entry['retry_at'] is None or now >= entry['retry_at']):
            entry['run'] = self._fetch_lanebreak_run(client, identity)
            entry['retry_at'] = None if entry['run'] else now + LANEBREAK_RETRY_SECONDS
            if entry['run']:
                entry['place'], failed = self._fetch_lanebreak_place(client, workout, identity, platform, entry['run']['difficulty'])
                entry['retry_at'] = now + LANEBREAK_RETRY_SECONDS if failed else None
        elif entry['run'] is not None and entry['retry_at'] is not None and now >= entry['retry_at']:
            # The run is kept; only its place failed last time.
            entry['place'], failed = self._fetch_lanebreak_place(client, workout, identity, platform, entry['run']['difficulty'])
            entry['retry_at'] = now + LANEBREAK_RETRY_SECONDS if failed else None
        self._lanebreaks[identity] = entry
        self._lanebreaks.move_to_end(identity)
        while len(self._lanebreaks) > self._performance_cache_size:
            self._lanebreaks.popitem(last=False)
        return entry

    def _fetch_lanebreak_run(self, client, identity):
        try:
            run = parse_run(client.get_lanebreak_run(identity))
        except (requests.RequestException, ValueError) as exc:
            logger.warning('Lanebreak run fetch failed (%s)', _reason(exc))
            return None
        if run is None:
            logger.info('Lanebreak %s has no run on the gateway yet', identity[:8])
        return run

    def _fetch_lanebreak_place(self, client, workout, identity, platform, difficulty):
        """(place or None, failed): failed is True only when a request failed, so the place is asked again later.
        A title that matches no track, same-named tracks none of which lists the run, or a place that can't be read
        is a settled None; an untitled run (the bike's older `Lanebreak Ride`) skips the track list altogether.
        The leaderboard ranks a run on any track it's given, so a title matching several tracks is settled by the
        rider's own runs on each: only the run's own track lists it."""
        title = workout.get('title') or (workout.get('ride') or {}).get('title')
        if title_key(title) is None:
            logger.info('Lanebreak %s has no track name in its title, so no place', identity[:8])
            return None, False
        try:
            candidates = track_candidates(client.get_lanebreak_tracks(platform), title)[:MAX_TRACK_CANDIDATES]
            track = candidates[0] if len(candidates) == 1 else _own_track(client, candidates, identity, platform)
            if track:
                place = parse_place(client.get_lanebreak_place(track, difficulty, identity, platform), identity)
                if place:
                    return place, False
        except (requests.RequestException, ValueError) as exc:
            logger.warning('Lanebreak place fetch failed (%s)', _reason(exc))
            return None, True
        logger.info('Lanebreak %s: no track of its title holds the run, so no place', identity[:8])
        return None, False

    def _lanes_for(self, client, platform, difficulty, perf):
        """Samples per lane from the performance graph's incline (Tread) or resistance (bike), or None. The
        machine's lanes are asked for weekly; a failed ask keeps the last ones and tries again in an hour."""
        now = time.monotonic()
        bands, next_at = self._lane_bands.get(platform, (None, 0.0))
        if now >= next_at:
            try:
                fresh = parse_lanes(client.get_lanebreak_lanes(platform), platform)
            except (requests.RequestException, ValueError) as exc:
                logger.warning('Lanebreak lanes fetch failed (%s)', _reason(exc))
                fresh = None
            bands, next_at = (fresh, now + LANES_REFRESH_SECONDS) if fresh else (bands, now + LANES_RETRY_SECONDS)
            self._lane_bands[platform] = (bands, next_at)
        lanes = (bands or {}).get(difficulty)
        if not lanes:
            return None
        return lane_samples(metric_values(perf, LANE_METRICS[platform][0]), lanes)


def _own_track(client, candidates, identity, platform):
    """The first same-named track whose list of the rider's own runs holds this run, or None."""
    for track_id in candidates:
        if owns_run(client.get_lanebreak_mine(track_id, platform), identity):
            return track_id
    return None


def _reason(exc):
    status = getattr(getattr(exc, 'response', None), 'status_code', None)
    return f'{type(exc).__name__} {status}' if status else (str(exc)[:80] if isinstance(exc, ValueError) else type(exc).__name__)
