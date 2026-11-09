# Roadmap

Planned work. Each item is one branch and one PR into `develop-beta`; delete it when it merges. Item numbers are labels, not a strict order: see "How the items connect" for what has to come first.

## How the items connect

```
Icon touch-ups (by hand) ── independent
6 More head-to-head stats ── after facts-engine step 1 (period_stats) merges
7 Journey moments ── after the journey redesign (journey-mile-groups) merges
Name page facts engine ── steps 1-6 built; retune weights on real logs (first pass: PR #72)
Workout graphs ── research first; builds on `performance_graph` in peloton/summaries.py and the workout pages
Name page together facts ── after the facts engine; shares figures with item 6 (head to head)
Name page facts settings and log fields ── maybe; after the facts engine
```

Suggested order: facts-engine step 1, then 6, then the remaining steps. Item 6 adds frames to a screen that shares its page time across frames (`peloton/screen_times.py`), so more stats mean a longer minimum page. Icon touch-ups whenever Joel has time.

## Up next

### 6. More stats to compete on in Head to head
The `versus` page (`display/ui/versus_screen.py`) compares two riders on the same three stats every time: this week's workouts, minutes and output (`STATS`, fed by `weekly_rivals` in `peloton_led.py` from `weekly_progress`). Add more things to compete on and rotate through them, so the rivalry has more angles. Candidates, all from the workout log:
- calories
- Strive score (`effort_points`)
- distance (miles or km by `uses_metric`; say which disciplines count, like the journey's)
- active days this week (days with at least one workout)
- PRs this week (`pr_output` / `pr_splits`)
- longest single workout
- one discipline's minutes or count (e.g. strength), changing discipline each pass
- the last 30 days instead of this week, for some or all of the above (rolling, not the calendar month: Joel's preference)

**Chosen layout for 64x64 (mocked up 2026-11-08 with the board's fonts): five rows, each number beside its word.** One line per stat: the left rider's number at the left edge, the word centred on the panel, the right rider's number at the right edge (`5  WORKOUTS  4`, `2,105  CAL  1,480`). Numbers keep today's 5x8 font (`titles`), labels today's tom-thumb (`stats`), the bigger number gold. Rows 9 apart from baseline 20 (20, 29, 38, 47, 56), between the names (baseline 9) and the week strip (rows 60-61). Workouts is always the top row; the other four change every 4 s (`DETAIL_INTERVAL_SECONDS`), so a 12 s page shows 1 + 4 x 3 = 13 slots, more than the candidate list, so some frames can repeat or the page can be shorter.

Layouts tried and rejected:
- Today's stacked rows (label above the two numbers, 15 rows each) fit exactly three; the page is full.
- Four stacked rows at an 11-row pitch: each label sits on the numbers above it.
- Two stats per row (32-pixel cells): only fits in the smallest font, with 16 pixels per number, so `1,234` becomes `1.2K` and labels become `WKTS`/`STRV`/`MI`; with 5x8 numbers `1,2K` runs into `612`.
- Six beside-the-word rows, 8 apart: rows nearly touch and the bottom one sits on the week strip.
- A table (labels left, a column per rider, all tom-thumb, 7 rows) and tug-of-war bars (5 rows, a bar split by share) both work and could be a closing "scoreboard" frame, but everything is in the 3x5 font.

Fitting rules learned from the mock-ups:
- Measure by lit pixels, not `get_text_width`: the advance includes a blank column per character. In 5x8, `2,105` is 25 advance but 24 lit pixels; `1,480` lights 23 starting 1 in. Measuring by advance plus padding wrongly shortened calories to `2.1K`.
- Keep a 1-pixel margin at each panel edge; numbers flush to column 0/63 look clipped.
- Centre the word on the panel (x = 32 minus half its lit width), and only slide it into the gap between the numbers if it would come within 2 pixels of one. Centring in the gap put `KJ` right of centre beside `1,234 ... 612`.
- Fallback when the word doesn't fit, in order: the short label (`OUTPUT KJ` → `KJ`, `CALORIES` → `CAL`, `LONGEST MIN` → `LONG`); 1 pixel of space instead of 2; drop the commas (`9999` lights 19 vs 24); last, `10K`-style numbers. Never draw a row without its word (the mock-up's 9,999 vs 8,888 calories row lost `CAL` entirely).
- Typical weeks need no fallback beyond the short label: with two four-digit numbers there's 15 pixels between them, `CAL` is 11, `KJ` 7, `OUTPUT` 23 (too wide next to `1,234`). `WORKOUTS`, `MINUTES`, `STRIVE`, `MILES`, `ACTIVE DAYS` and `PRS` fit in full beside their usual numbers.

Notes:
- Skip a stat when both riders are 0, or when one rider's log can't supply it (e.g. no heart-rate strap, so no Strive score).
- Decide what crowns the week's leader (`weekly_leader`, the gold trophy): keep it on workouts → minutes → output so it doesn't change from frame to frame (recommended), or give each stat its own marker.
- This changes today's 64x64 page, so its byte-identical check doesn't apply to `versus`; check the other pages are unchanged and preview with `scripts/render_rotation.py --height 64 --rival <cache>`.
- 32 rows keeps one stat at a time (labels and big numbers already rotate there); the page's minimum duration grows with the number of stats shown, so pick a per-pass set there too.
- Optional: a settings-page choice of which stats compete (the Rotation card's Head to head row, or a small section).
- Depends on: nothing. Per-week and per-month figures come from a helper over the workout log in `peloton/activity.py`, fed via `WorkoutLog.derived` like `streak_week_workouts`; every candidate field is already in the log, so no `LOG_VERSION` bump. Facts-engine step 1 added `period_stats` / `frame_stats` in `peloton/activity.py` (per-window counts from the log, rolling windows, in `WorkoutLog.derived` as `time_frames`; Joel prefers a rolling 30 days to the calendar month); extend them rather than adding a new pass over the log.

### 7. Journey moments: arrival, turning for home, and the 32-row hand-off
The redesigned journey page (`display/ui/journey_screen.py`, 2026-11-08) opens each step with a fill, a count-up, a pulsing tip and the groups coming in. Joel chose these three for later:
- **Arrival.** Within about 1% of the destination, the bar's end glows gold. The first time the page shows after a leg is finished, a short confetti burst (reuse `celebration_screen`'s confetti) plays before `TRIP n` appears.
- **Turning for home.** The first time the page shows on a new leg, a small arrow sweeps along the bar in the new direction (toward `TO COLUMBUS` on the way home, back out on the next leg).
- **32-row hand-off.** Between the two steps, the orange bar splits in place into the BIKE / WALK/RUN / ROW colours, then the rows fade in, so the split reads as the same miles broken down. Today step 2 starts fresh with its own growing bar.

Notes:
- "The first time after" needs memory across passes: record the last leg shown (`trip`) in the dashboard cache, like `milestone_shown_at` / `acknowledge_milestone`, so a restart doesn't replay it and every pass after doesn't either. Per rider on multi-rider boards.
- Keep each effect inside the step's opening second (`INTRO_SECONDS`), or raise the journey's `least_seconds` for the showing that carries it; a 32-row step must keep at least 3 s still.
- The arrival confetti must stay off the text, like the milestone celebration's.
- Check both boards with `scripts/render_rotation.py` and frame strips (the journey's `frame_times` captures settled frames only); the other pages must stay byte-identical.
- Depends on: the journey redesign (branch `journey-mile-groups`).

### Name page: facts engine
The plan is in `docs/NAME-PAGE-FACTS.md` ("Plan"): one PR per step. Steps 0 (PR #65), 1 (time frames and `period_stats`, PR #66), 2 (filters, PR #67), 3 (measures and bests, PR #68), 4 (comparisons, PR #69), 5 (events, PR #70) and 6 (scoring and a cool-down, PR #71) are built; PR #72 is the first tuning. Steps 7 and 8 of the plan are their own items below. Left from step 6: tune `KINDS` weights from `list_facts.py` on Joel's real logs on the boards.
- Build brief for a Sonnet 5.5 session, one step each: `docs/NAME-PAGE-FACTS-HANDOFF.md`.
- After the update, on each board: `python scripts/list_facts.py --log <log> --cache <cache> --tz <zone>` should show no `<-- differs` in "overview vs log" (the log rebuilds once, LOG_VERSION 2). Checked on Joel's full history from the Mac on 2026-11-08: all 13 rows matched. Remove this item once the boards agree.
- Depends on: step 4 merged. Item 6 (Head to head) should build on step 1's `period_stats`.

### Workout graphs: more of what Peloton records during a class
Peloton records heart rate, output, cadence and more every 5 seconds of a class, and the board draws only one of them. This item is to decide which of the others deserve a graph slide on the workout pages, then build those. Research first: a mock-up of each candidate at 64x64 and 64x32 from the saved real workouts in `perf_graphs/` (91 of them), and Joel picks.

**What the board draws today.** One graph slide per workout: output (W) when the workout has it, otherwise heart rate (BPM), then the heart-rate zones bar. `peloton/summaries.py` `performance_graph` averages the series into 60 columns (`GRAPH_POINTS`, one per pixel column of a 64-px panel) and colours each column by heart-rate zone; `display/ui/last_workout_screen.py` draws it. `rotating_details` appends the slides (`kind`: `graph`, `zones`, `muscles`), each holds `GRAPH_FRAME_EXTRA_SECONDS` longer, and `build_rotation_pages` sizes the page from the same list. Everything else the workout pages show is a number.

**What Peloton sends that isn't a graph yet** (counts are of the 91 saved workouts, in `docs/DATA-POINTS.md` terms):
- Time series, one sample every 5 s: `cadence`, `resistance` and `speed` (bike, 13 workouts); `pace` (tread, 11) and `incline` (treadmill only, 7); `altitude` (outdoor, 3); `stroke_rate` and `split_pace` (row, 13). Heart rate (86) and output (33) are the two already used.
- `splits_data`: per-mile (or per-km) splits with elevation change (21 workouts): bars would show a negative split or a fading pace at a glance.
- `location_data`: GPS coordinates (3, outdoor only): a route outline.
- `segment_list`: the class's own structure (warm-up, climbs, cool-down; 84 workouts), which could shade the graph's background in bands.
- Not useful yet: `target_metrics_performance_data` is empty in all 91 saved workouts, so there is no target range to overlay; check a fresh Power Zone ride before ruling it out.
- Peloton also sends each stat's max, which the board doesn't show except max heart rate (`docs/DATA-POINTS.md`, "The gaps"); a graph's peak can be a caption.

**Candidates**, by equipment:
- Bike: cadence and resistance (the two a rider actually steers), speed; output with class segments shaded.
- Treadmill and outdoor: pace with incline, or elevation profile from altitude; per-mile split bars; the GPS route.
- Row: split per 500 m and stroke rate.
- Heart rate as its own graph on workouts where output is shown (today heart rate only appears as zone colours and the zones bar).

**Decisions to make first.**
- One slide per metric, or one slide that alternates metrics? Each slide adds `GRAPH_FRAME_EXTRA_SECONDS` (a bike page is 38 s today), so several more could make workout pages too long; some of the averages screens (avg cadence, avg resistance) could be replaced by their graph, since it shows the same figure and more.
- Which metric per equipment, and whether `MUSCLE_DISCIPLINES`-style per-discipline lists are the right pattern for choosing.
- 64x32 has half the height (about 15 usable rows with a title and caption), so a graph there may need to drop the zone colouring or the caption.

**Constraints.** 60 columns, no axes (a caption states the peak and unit; labels fit 15 characters of the `stats` font); workouts without a heart-rate monitor or without a series must drop the slide, as they do now (see "Why some workouts lack a stat" in `docs/DATA-POINTS.md`); the downsampling must stay in `peloton/summaries.py` (business logic out of the screen) and be tested with real saved payloads.

**To do the work.** Extend `performance_graph` (or add siblings) to return any named series; add the slide `kind`s to `rotating_details`; drawing in `display/ui/`; update `docs/DATA-POINTS.md` (its "Output / heart-rate graph" row and stats-per-workout table) and the README's workout-page section. Preview with `scripts/render_rotation.py` at both heights; the other pages must stay byte-identical. Depends on: nothing.

A separate, later idea: charts of trends over time from the workout log (workouts per week as bars, this year against last year, the mix of disciplines by month, which weekdays and hours you work out), reusing `peloton/activity.py` windows the way the heatmap page does. Not part of this item.

### Name page: together facts (was facts-engine step 7)
Facts about both riders on a two-rider board (`TOGETHER` / `31 WORKOUTS`, `BOTH TOOK` an instructor, `SAME CLASS`), from each rider's `period_stats`, shown once a cycle on the rider whose rotation gets `rivals`. Details: `docs/NAME-PAGE-FACTS.md` ("Step 7").
- Depends on: the facts engine (through step 6). Shares figures with item 6 (Head to head).

### Name page: facts settings and new log fields (maybe; was facts-engine step 8)
Settings-page switches for whole kinds of facts (no comparisons, no events), not one per fact; new log fields (live vs on-demand, class type) only if a fact needs them, with one `LOG_VERSION` bump. Ask before starting.
- Depends on: the facts engine.

## Joel, by hand

### Touch up the discipline icons
Some of the 26x24 discipline icons (`DISCIPLINE_ICON_ROWS` in `display/ui/discipline_icons.py`, rasterized from the supplied SVGs) need pixel-level touch-ups. Joel will edit these by hand: each icon is a grid of `#`/`.` strings, so it's hand-editable.
- Preview with `scripts/render_rotation.py --height 64` and `--height 32` after each edit.
- Depends on: nothing.

## If it ever happens

### Updater: git run as root in the user's checkout
Not a task now. Lightning Lane LED's updater hit it (PR #214 there, `self_update/board.py`); this repo's can't, because `peloton-install.sh` never runs git in the checkout or edits a tracked file (it only reads `$SOURCE_DIR` and copies into `/opt/peloton-led`). If the installer ever does either, two things go wrong on a board:
- `self_update` runs the installer as root from systemd, with no `SUDO_UID` (which a hand `sudo` sets, and git takes as the reason to trust the checkout). A `git` call in it fails with "detected dubious ownership" and exits 128, so the update fails.
- A tracked file the installer edited (Lightning Lane's put a shebang on `disney.py`) stays dirty when the install dies, so the rollback's `git checkout` refuses to overwrite it, and the board is stuck half-updated.

The fix there, to copy: `Board.install` passes `SUDO_UID`, `SUDO_GID` and `SUDO_USER` of the checkout's owner in `env` (still root), and `Board.checkout` first discards the file's change when the whole diff is the installer's added line. Add a test for each. Better still: don't write to the checkout at all.
