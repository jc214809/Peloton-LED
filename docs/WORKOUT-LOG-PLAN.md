# Workout log: plan

Status: **PR A implemented** (branch `workout-log`, PR #29); **PR B implemented** (branch
`streak-risk-heatmap`, stacked on PR A).
Replaces the cursor-based instructor and distance tallies with a slim
per-workout log, cuts refresh traffic by 4–7×, and stores what the planned
screens need. Ships as two PRs: A (storage, no visible change) and B (first
screens built on it).

## Results (PR A, measured 2026-11-01)

Baselines were recorded from `main` (60d64d6) before any change, live against
the API, and as recorded responses that can be replayed through any version
of the code. Old and new code were run on identical input.

**Same screens.** Every rotation page state (64×64 and 64×32, both riders,
including versus) was identical, and all 142 rendered frames were
pixel-identical.

**Traffic, live API:**

| | Old (`main`) | New |
|---|---|---|
| Each refresh, Joel | 5 calls, 1.04 MB, 1.7 s | 2 calls, 0.26 MB, 0.6 s |
| Each refresh, Jen | 7 calls, 2.13 MB, 2.9 s | 2 calls, 0.30 MB, 0.6 s |
| Cold start: first screen | ~29 s (blocked on the full walk) | 1.6–2.3 s |
| Cold start: full history | 49–54 calls, ~29 s | 27–29 calls, ~42 s in the background (1 s pauses) |
| Peak memory, cold start (Jen) | 17 MB | 4 MB |

At about 223 refreshes a day that is roughly 450 calls and 60–70 MB per
rider per day, down from ~1,100–1,560 calls and ~230–475 MB.

**Real-data scenarios (Jen's history, replayed):**

| Scenario | Old | New |
|---|---|---|
| Newest workout deleted in Peloton | every total doubled (Cody Rigsby 423 → 846, miles 10.9 → 19.7) | unchanged; re-walk scheduled for quiet hours |
| Journey `start_date` changed | 51 calls, 19.4 MB | 2 calls, 0.3 MB, same result |
| Board off while 25 workouts happened | correct, 11 calls | correct, 7 calls |

The live log matched the audit exactly: Joel 2,127 and Jen 2,192 workouts
(Peloton's own totals); Jess Sims 205 / Adrian Williams 179 / Denis Morton
151 and Cody Rigsby 423 / Robin Arzón 150 / Jess Sims 148.

**Estimates this plan got wrong** (corrected below):

- Log size is about 470 bytes per workout (the 32-character IDs dominate),
  so about 1 MB per rider, not 650 KB. Still far under the 10 MB threshold.
- The overview is 132–143 KB, not small. It is now most of each refresh.
- The old full-history walk peaked at 17 MB, not "over 100 MB".

**Deviations from the plan:**

- The count check compares with the `total` that every workouts page
  already carries (all statuses, so it matches the log's row count
  directly), not the overview's Total Workouts.
- A backfill is marked complete when the walk reaches the oldest workout. A
  remaining mismatch is left to the count check and re-walk, rather than
  blocking completion.
- `history_days` is retired, so the latest-workout screens show your most
  recent day however long ago it was. Before, a rider idle for 90+ days saw
  "no workouts".

**Found during the work, not changed here:** per-rider `users[].weekly_goals`
and `users[].milestones` never reach the rotation. `run_multi_user_loop`
builds pages from the shared `display` config, and in the baseline neither
rider got any `goal` pages. Same behavior before and after this change.

**Next easy saving:** skip the overview when the newest page shows nothing
new (about 1 call per refresh). Not done in PR A.

## Why

An audit on 2026-11-01 (after PRs #27 and #28) traced every data flow against
the live API for both riders.

**What works:** the tallies are complete. They cover 2,127 workouts for Joel
and 2,192 for Jen, matching Peloton's lifetime Total Workouts exactly, with no
duplicates and no missing pages.

**What's wrong with the storage strategy:**

1. **Only running totals are kept.** Raw workouts are discarded once
   counted, so every counting fix needs a full-history re-download and a
   `TALLY_VERSION` bump. That happened twice in one day (#27 in-progress
   workouts, #28 placeholder instructors). Changing the journey `start_date`
   also re-downloads.
2. **A deleted workout can double every total.** `get_all_workouts(stop_at_id=cursor)`
   walks back until it finds the cursor workout. If that workout is deleted
   in Peloton, the walk reaches the end of history and adds all of it on top
   of the existing totals.
3. **Edits to old workouts are never seen.** Once counted, a workout is never
   looked at again.
4. **The cache stores the whole `/api/me` profile.** That's 83 fields,
   including email, birthday, phone, weight, height, last name and location.
   The board uses four: `id`, `username`, `timezone`, `height_unit`.
5. **Refreshes re-download the same data constantly.** Each workout row
   arrives with the class and instructor joined (about 8 KB per row, of which
   about 4.5 KB is the instructor's bio). At the default 5-minute refresh
   (about 223 refreshes a day with quiet hours):

   | Rider | 90-day pages | Tally page | Calls/day | Data/day |
   |---|---|---|---|---|
   | Joel | 1 | 1 | ~900 | ~180 MB |
   | Jen | 3 | 1 | ~1,340 | ~360 MB |

   Recent history is fetched twice per refresh: once for the screens and
   once for the tallies.
6. **"This week" counts workouts Peloton excludes from streaks.** Peloton
   leaves out workouts synced from other apps
   (`is_3p_fit_feed_workout_excluded_from_streaks`; Joel has 17). Harmless
   today, but wrong for a "streak at risk" screen.
7. **The code is fiddly.** Two cursors, rules for when they share pages, the
   in-progress hold (`settled_rows`), and version bumps. #27's bug came from
   exactly this.

## What future screens need

From the ideas list (2026-10-31), plus the screens that already exist:

| Feature | Needs | Today | With the log |
|---|---|---|---|
| Top instructors (exists) | instructor IDs per workout | totals only | yes |
| Journey (exists) | distance and date per workout | totals only | yes, and `start_date` changes are free |
| 1. Streak at risk | streak status plus this week's streak-eligible workouts | no exclusion flag | yes |
| 2. Activity heatmap | minutes and discipline per day, 8–12 weeks | no (only the latest day) | yes |
| 3. Monday recap | last week vs. the week before | no | yes |
| 4. On this day | the workout one year ago | needs extra calls | yes, no calls |
| 5. Output trend | output for past rides of the same class length | no | yes |
| 6. Cross-board PRs | the other rider's PR flags | in memory | yes |
| 7. Live workout mode | in-progress status, polled faster | too costly | cheap small poll |
| 8. Board health | local state only | yes | yes |

## Design

### 1. The log

One JSON file per rider, holding every workout as a slim row keyed by workout
ID, plus an instructor directory.

```json
{
  "version": 1,
  "user_id": "a0be2993...",
  "backfill": {"complete": true, "next_page": null, "finished_at": 1793600000},
  "instructors": {"ee70149e...": "Katie Wang"},
  "workouts": {
    "795070ae...": {
      "start": 1793546328, "end": 1793546928, "tz": "America/New_York",
      "status": "COMPLETE", "discipline": "strength",
      "ride_id": "f56c4097...", "title": "10 min Chest & Back Strength",
      "class_length_s": 600, "total_work_j": null, "distance": null,
      "calories": 143.67, "instructor_id": "ee70149e...", "group_ids": null,
      "pr_output": false, "pr_splits": false,
      "effort_points": 4.1, "hr_zone_s": [392, 195, 9, 0, 0],
      "counts_for_streaks": true
    }
  }
}
```

Field rules:

- `discipline` is normalized with `selection.normalize_discipline`.
- `distance` is stored **raw**, as Peloton reports it. Conversion to miles
  stays at compute time (`journey.workout_miles`: rowing in meters, metric
  accounts in km), so a unit fix never needs a re-download.
- `class_length_s` is `ride.duration`, the field `goals.weekly_progress` uses
  today, so "this week" minutes come out identical. Actual time is
  `end - start`.
- `instructor_id` is null for placeholders (Just Walk, Lanebreak, ride goals,
  and so on: no `id`). For group classes `instructor_id` is the group's ID and
  `group_ids` lists its members. Counting rules match #28.
- `counts_for_streaks` is `not is_3p_fit_feed_workout_excluded_from_streaks`.
- No bios, image URLs, video stats or user IDs per row.

Size: about 470 bytes per row (measured), so about 1 MB per rider today,
growing about 120 KB a year.

**Format: JSON, not SQLite.** The log is a copy of data Peloton keeps, so if
the file is lost or damaged, 22 calls rebuild it. At under 2 MB with one
writer per file, SQLite's strengths (partial writes, queries, multiple
writers) don't apply. Its costs land where this project has been fragile:
migrations, plus `-wal`/`-shm` files under the service's locked-down
permissions. JSON reuses `cache.save_snapshot`'s pattern (temp file, fsync,
rename, owner-only permissions) and is easy to inspect, seed and copy.
Switch only if a log passes about 10 MB or gains a second writer. Only the
log's load/save code knows the format.

**Location:** `users[].log_path`, defaulting to the rider's cache path with
`.workouts.json` in place of `.json` (for example
`/var/lib/peloton-led/dashboard-cache-joel.workouts.json`). It is saved only
when a row changed.

**Ownership:** the file records `user_id`. If the token belongs to a
different Peloton account than the log, the board starts a fresh log instead
of mixing two people's history.

### 2. Backfill (first time a rider is seen)

- Triggered when there's no log, the log is for another user, or its
  `version` is unknown.
- **Batches of 100** (`history_batch_size`, default 100). Tested in the
  audit: 100 per page returned every workout for both riders. That's about 22
  calls per rider. Don't go higher without testing.
- **Page by page:** each page is trimmed to log rows as it arrives and the
  raw data is dropped. The old `get_all_workouts` held every raw row in
  memory (measured peak 17 MB for Jen; the new walk peaks at 4 MB).
- **Saved after every batch** (`backfill.next_page`). An interrupted backfill
  resumes from there. Rows are keyed by ID, so overlap from workouts added
  mid-backfill is harmless.
- **About 1 s pause between batches**, roughly 20 s per rider.
- **Doesn't block the board.** Screens that don't need history show at once:
  the latest workout, totals, streaks. Instructors, journey and later the
  heatmap appear when the backfill completes, the way journey already waits
  for its data.
- Complete only when it reaches the oldest workout **and** the count check
  (section 4) passes.
- Optional, only if Pi backfills prove slow: `seed_board.sh` copies a log
  built on the Mac.

### 3. Each refresh

| Call | Today | Planned |
|---|---|---|
| `/api/me` | every refresh, full profile cached | at startup, then once a day; slim profile cached |
| overview | every refresh | unchanged (totals, streaks, PRs, count check) |
| workouts | 90 days (1–3 pages of 50) plus a tally page | **newest 20** (`recent_fetch_size`), merged into the log by ID |
| performance graph | latest day only | unchanged |

Merging by ID covers new workouts, in-progress ones finishing, and later
edits within the newest 20. The cursors and `settled_rows` go away: an
in-progress row is stored as `IN_PROGRESS` and overwritten when it completes.

Derived from the log on every refresh, all cheap at this size:

- this week's workouts, minutes and output (same rules as `weekly_progress`)
- instructor counts (same rules as `instructors.merge_instructor_counts`)
- journey miles, honoring `start_date` with no re-download
- the latest active day: which workouts the latest-workout screens show

**Latest-workout screens** keep using the raw rows from the newest-20 fetch,
because `summarize_workout` needs fields the log doesn't keep. If the latest
active day has more than 20 workouts, fetch further pages until the day
boundary is passed.

`/api/me` doesn't need to be more frequent: `id` never changes, `username`
and `height_unit` rarely do, and a timezone change (travel) showing up to a
day late is fine (`display.timezone` overrides it). It isn't needed as a
login check either; a 401 on any call already sets the padlock.

Measured: 2 calls and 0.26–0.30 MB per refresh, down from 5–7 calls and
1.0–2.1 MB. The overview (132–143 KB) is now about half of that.

### 4. Accuracy check

Every refresh compares the log's row count with the `total` on the workouts
page it already fetched (every status, so in-progress workouts count on both
sides). They matched exactly in the audit.

- **Equal:** nothing to do.
- **Different for 3 refreshes in a row** (to ride out a brief lag right after
  a workout): schedule a **re-walk** in the next quiet hours, at most once a
  day. The re-walk pages the full history in batches of 100, adds missing
  rows, and removes rows Peloton no longer returns, which handles deletions.
- Log mismatches and re-walk results so they show up in `journalctl`.

### 5. Slim profile

Cache only `id`, `username`, `timezone` and `height_unit` from `/api/me`.
Existing caches are slimmed on first save. Check `utils/username.py`,
`journey.uses_metric` and the versus timezone lookup for anything else read
from `me` before trimming.

### 6. Removed

`instructor_counts`, `instructor_names`, `instructor_tally_cursor`,
`distance_totals`, `distance_tally_cursor`, `distance_tally_since`,
`tally_version` (from the cache and `cache.PERSISTED_KEYS`),
`TALLY_VERSION`, `selection.settled_rows`, the shared-download logic in
`Dashboard._refresh_once`, and `get_recent_workouts`/`get_all_workouts` once
nothing calls them. Old cache keys are ignored on load and dropped on the
next save.

Config: `history_days`, `history_limit`, `history_max_pages` and
`instructor_tally_max_pages` stop doing anything. Keep accepting them with a
deprecation warning so existing `config.json` files still load. Add
`history_batch_size` (100), `recent_fetch_size` (20) and `users[].log_path`.

### Unchanged

The screens; personal records and `previous_best_kj` (still from the
overview); performance graphs (latest day only); the refresh schedule;
tokens and renewal.

## Rollout

### PR A: the log (no visible change)

1. Log module (`peloton/workout_log.py`): row trimming, load/save, merge by
   ID, ownership check, derived values (week, instructors, journey miles,
   latest day).
2. API: a single-page fetch, and a page-by-page history iterator for
   backfill and re-walks.
3. Dashboard: backfill (resumable, non-blocking), newest-20 refresh, count
   check and re-walk scheduling, slim `me`, removals.
4. Config keys and deprecation warnings.
5. `scripts/render_rotation.py`: read the log beside `--cache` so offline
   previews still work.
6. Docs: README (configuration table, state files), CLAUDE.md (Architecture,
   Dashboard), `docs/install.md` (files under `/var/lib/peloton-led`).

**Before deleting the old tallies**, run old and new side by side on real
data for both riders. Instructor counts and journey miles must match
exactly, including #28's corrected numbers (Joel: Jess Sims 205, Adrian
Williams 179, Denis Morton 151; Jen: Cody Rigsby 423, Robin Arzón 150, Jess
Sims 148).

### PR B: first screens on the log

"Streak at risk" (uses `counts_for_streaks`) and the activity heatmap. Then
the rest of the ideas list as chosen.

**Done:**

- **Streak reminder:** from `streak_reminder_day` (default Saturday), if this
  week has no streak-eligible workout (`streak_week_workouts == 0`), the
  `streaks` page becomes `streak_risk`: "1 WORKOUT KEEPS YOUR N-WEEK
  STREAK", plus days left. Synced third-party workouts don't count, matching
  Peloton. An unknown count (no log yet) never triggers it.
- **Heatmap:** new `heatmap` rotation section, 12 Monday-aligned weeks of
  daily minutes (`activity.daily_minutes`), shown once the log is complete.
- No new API calls. Verified against PR A on the re-recorded real data: with
  the existing rotation, every page state and all 142 frames are identical
  and traffic is unchanged. The new screens were checked on real data at
  both board sizes (Joel's week emptied to force the reminder).

## Verification (PR A)

- **Tests**, with the API mocked:
  - row trimming, including placeholders, group classes, missing fields, bad
    types, and rowing/metric distance
  - merge by ID: in-progress then complete, an edit to an existing row, a
    duplicate page
  - backfill resume after a failure mid-batch; batches don't pile up raw rows
  - log owned by another user → fresh log; unknown version or damaged file →
    rebuild
  - count check: equal, brief lag (no re-walk), lasting mismatch → re-walk
    once a day, deletion removed by the re-walk
  - derived week/instructors/journey equal the current functions on the same
    rows
  - latest day with more than 20 workouts
  - deprecated config keys load with a warning
  - slim `me`; old cache keys dropped
- **Coverage** stays at or above 90% (`.coveragerc`).
- **Pixels:** `render_rotation.py --height 64` and `--height 32` with the
  same data before and after; the output must be byte-identical.
- **Real data:** the side-by-side parity check above, plus a cold-start
  backfill timed on a board.
- **Traffic:** log calls and bytes per refresh for a day and compare with
  the table in "Why".

## Upgrading boards

Merge, then on each board:

```bash
cd ~/Peloton-LED && git pull && sudo ./peloton-install.sh --skip-matrix
sudo systemctl restart peloton-led
```

The first start backfills each rider (about 22 calls and about 20 s each)
while the board keeps showing the non-history screens.

**Rollback:** the previous version ignores the log file. With the old
tally keys gone from the cache, it rebuilds its tallies from a full walk, as
on a first install.

## Decisions made

| Question | Decision |
|---|---|
| Storage | JSON, one log per rider; revisit past about 10 MB or a second writer |
| Backfill batch | 100 per page, about 1 s apart, saved per batch |
| Per-refresh fetch | newest 20 |
| Re-walk trigger | 3 consecutive count mismatches; quiet hours; at most once a day |
| Distance | stored raw, converted at compute time |
| Latest-workout screens | still built from raw rows of the newest fetch |
| Profile | `id`, `username`, `timezone`, `height_unit` only; fetched at startup, then daily |
