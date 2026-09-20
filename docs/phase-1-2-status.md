# Phase 1–2 implementation status

Verified September 19, 2026. Scope ends at Phases 1–2; the five-minute refresh already implemented in this session remains in place, but no further Phase 3–4 expansion is included.

## Phase 1: working baseline

- Configuration validation runs before matrix/network startup.
- Runtime, development, and optional authentication dependencies are documented separately.
- RGBMatrixEmulator is pinned to 0.15.2, verified in the existing and clean Python 3.14 environments. Version 0.19.0 failed actual matrix initialization despite passing graphics-only tests.
- Synthetic demo mode needs no token or network. Finite screen rotations and a PNG contact-sheet renderer support repeatable inspection.
- Missing/empty/rejected tokens show the amber padlock; connection failures do not impersonate authentication failures.
- Token refresh verifies a candidate before atomically replacing the existing token with an owner-only file.
- Detailed 64×64 screens and compact 64×32 screens were rendered and visually inspected. Title/stat and PR-badge overlaps were corrected.
- Both a demo rotation and a live-account emulator rotation completed successfully.
- README and example configuration describe the current behavior and limitations.

## Phase 2: data correctness

- Shared timestamps handle seconds, milliseconds, ISO offsets, local dates, and timezone/DST boundaries.
- Workout selection excludes explicit incomplete statuses, deduplicates IDs, and uses normalized discipline aliases.
- Date-only records do not invent an ordering within a day or hide the latest timed workout when a discipline filter cannot identify a timed match.
- History fetches are paginated with date, count, page, and repeated-page bounds.
- Metrics distinguish missing values from zero and preserve units. Pace/split formatting rounds correctly across minute boundaries.
- Explicit performance values take precedence over derived averages, including Peloton's rowing split in minutes per 500 m.
- Output PRs and splits PRs use shared classification; only output PRs show an output star.
- Discipline totals preserve zero counts and reject invalid/duplicate entries.

## Evidence

- 66 tests pass in the project environment and a separate clean environment.
- Archived performance-data checks covered 91 payloads, including 13 explicit rowing split values. Checked distance, total-output, and rowing-split mappings against source payload values where present.
- Live API refresh loaded the profile, workout history, overview, and a cycling workout summary successfully.
- Dependency checks report no conflicts. Syntax and diff-whitespace checks pass.
- The emulator dependency emits Python 3.14 asyncio deprecation warnings; these did not prevent tests or actual emulator runs.

## Limits and deferred work

- Physical Raspberry Pi hardware was not available for validation.
- Python versions other than 3.14 have not been exercised; 3.10+ remains the intended code baseline.
- Cached data is currently in memory only. Persistent cache, stale-data indication, and full recovery testing belong to Phases 3–4.
- Latest-active-day rotation was added after this phase: live mode now shows all completed workouts from the most recent active local calendar date. One-time celebrations remain later work.
- The 32-row layout is deliberately compact; full detailed metrics at that resolution remain deferred.
- Goals, milestones, brightness schedules, installation/service deployment, and hardware soak testing have not been implemented in these phases.
