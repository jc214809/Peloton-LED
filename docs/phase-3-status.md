# Phase 3 implementation status

Phase 3 separates network access from display rendering. The persistent disk caching and stale-data UI that were originally deferred are now implemented in Phase 4.

## Implemented

- A dedicated background worker fetches profile, overview, history, and performance data for every workout on the latest active day.
- Rendering reads deep-copied snapshots and performs no Peloton API calls.
- Successful refreshes publish profile, totals, workout summaries, history metadata, and health fields atomically.
- Snapshot health includes `status`, `refresh_in_progress`, `last_attempt`, `last_updated`, `last_refresh_duration`, `last_error`, `next_refresh_at`, and `generation`.
- Performance graphs use a configurable bounded LRU cache keyed by workout ID. Unchanged settled workouts reuse cached data; recent workouts, changed metadata, and missing performance graphs are refetched.
- The published snapshot contains every completed workout on the most recent active local calendar date, newest first, even when that activity date is older than today.
- Refreshes are serialized, so manual and scheduled refreshes cannot mutate shared state concurrently.
- `request_refresh()` wakes a sleeping worker without blocking the display thread.
- Token-file changes wake the worker automatically. A rejected token pauses requests until the file changes.
- Network failures retain the last complete in-memory snapshot and use bounded exponential backoff.
- Shutdown wakes sleeping workers, waits through the API request timeout, closes the HTTP client, and reports if an in-flight call failed to stop.

## Acceptance evidence

- Screen rotation completes while a simulated API request is blocked.
- Snapshot mutation by a renderer cannot alter the live dashboard state.
- Unchanged workout performance is not downloaded repeatedly.
- LRU eviction, refresh wake-ups, serialized lifecycle state, token replacement, offline retention, rate-limit delay, and blocked-worker shutdown are covered by tests.
- Demo and live rendering continue to consume the same snapshot structure.

## Completed in Phase 4

- Persisting the last successful snapshot across application restarts.
- A visible stale-data clock.
- Full offline-start recovery and corrupt-cache handling.
- Durable one-time PR celebration state.

See [Phase 4 recovery and durable-event status](phase-4-status.md).
