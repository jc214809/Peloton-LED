# Roadmap

Planned work. Each item is one branch and one PR into `develop-beta`; delete it when it merges. Item numbers are labels, not a strict order: see "How the items connect" for what has to come first.

## How the items connect

```
Icon touch-ups (by hand) ── independent
6 More head-to-head stats ── independent (facts-engine step 1's `period_stats` is built)
7 Journey moments ── after the journey redesign (journey-mile-groups) merges
Workout graphs ── research first; builds on `performance_graph` in peloton/summaries.py and the workout pages
Name page together facts ── shares figures with item 6 (head to head)
Name page facts settings and log fields ── maybe
Workout compare: Cardio classes ── unlikely (measured 2026-11-12: too rare to say much); independent
Ideas (not yet sized) ── trend charts share windows with item 6; yearly goal and weekly recap use `frame_stats`
```

Suggested order: 6, then the remaining items. Item 6 adds frames to a screen that shares its page time across frames (`peloton/screen_times.py`), so more stats mean a longer minimum page. Icon touch-ups whenever Joel has time.

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
- Depends on: nothing. Per-week and per-month figures come from a helper over the workout log in `peloton/activity.py`, fed via `WorkoutLog.derived` like `streak_week_workouts`; every candidate field is already in the log, so no `LOG_VERSION` bump. The facts engine's step 1 added `period_stats` / `frame_stats` in `peloton/activity.py` (per-window counts from the log, rolling windows, in `WorkoutLog.derived` as `time_frames`; Joel prefers a rolling 30 days to the calendar month); extend them rather than adding a new pass over the log.

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
- Depends on: nothing (the facts engine is built). Shares figures with item 6 (Head to head).

### Name page: facts settings and new log fields (maybe; was facts-engine step 8)
Settings-page switches for whole kinds of facts (no comparisons, no events), not one per fact; new log fields (live vs on-demand, class type) only if a fact needs them, with one `LOG_VERSION` bump. Ask before starting.
- Depends on: nothing (the facts engine is built).

### Workout compare: Cardio classes (unlikely, kept; measured 2026-11-12)
Cardio (HIIT, Low Impact, Dance and Family Cardio) is outside workout compare today (`workout_compare.DISCIPLINES`). It has no output, speed, callouts or weights, only heart rate, so the one rule that could apply is the heart-rate effort one (`effort_insight`: Strive per minute against similar classes, "hardest" / "easiest of your last N").

**Status: unlikely, not dropped.** Every Cardio data point Peloton sends was measured on 2026-11-12 and none adds anything over Strive per minute; the limit is how few Cardio classes the riders take (about 10 a year each; none since 2026-09-27 for Joel, 2026-07-20 for Jen), so even the loosened rule would speak about 3 times a year for Joel and once for Jen. Revisit if Cardio becomes a regular part of either rider's week: re-run the counts below first.

Tried as-is on 2026-11-11, re-run 2026-11-12 with the same result (Cardio added to `DISCIPLINES` in a scratch run over the Mac's row stores, last 12 months):

| | Joel | Jen |
|---|---|---|
| Cardio classes | 13 (93 all time) | 11 (41 all time) |
| With Strive | 12 | 11 |
| Would get an insight | 1 (`effort_high`) | 0 |
| `too_few` | 5 | 10 |
| `nothing` | 4 | 1 |
| `freestyle` | 3 | 0 |

Too few peers: "similar" needs the same class type and a length within 30%, and these classes spread over five types (Joel) or several lengths (Jen's are nearly all Low Impact Cardio).

The idea: loosen "similar" for Cardio only, comparing every Cardio class with every other by Strive per minute, any type and length, so each gets "hardest / easiest Cardio class of your last N by heart rate" or an "about your usual effort" line.

The loosened rule, measured 2026-11-12 (each class against the rider's last 12 Cardio classes of any type and length, 365 days, 5 needed): Joel 2 hardest, 1 easiest, 7 about usual (of 10 with Strive); Jen 0 hardest, 1 easiest, 10 about usual. Leaving out warm-ups and classes under 8 minutes, or a two-year window, moves at most one class. Joel's one "easiest" was a 5-minute Family Cardio class: warm-ups and family classes run about 0.4 Strive per minute against 1.1-1.2 for HIIT, so mixed types add noise.

Every other Cardio data point, measured 2026-11-12 over all 134 Cardio workouts (93 Joel, 41 Jen; their performance graphs were fetched into `training-data/` that day, since the sync never asked for them). Correlations are with Strive per minute, Joel / Jen:

| Data point | Present | Verdict |
|---|---|---|
| Heart-rate series (every 5 s), average and peak heart rate | 134/134 | Same signal: average 0.89 / 0.93, peak 0.83 / 0.74. A peak-heart-rate rule gives the same extremes (Joel 2 highest, 1 lowest; Jen none). |
| Time in heart-rate zones 1-4 (zone 5 never appears) | 75 graphs | Same signal: zones 3-4 share 0.87 / 0.94. |
| Calories | 134/134 | No more insights (Joel 1 most, 1 fewest per minute; Jen none). Jen's track heart rate (0.91) and barely the class plan (0.12); Joel's are half heart rate (0.56), half class plan (0.51), and calories per minute per bpm jump by year (0.119 in 2021, 0.092 in 2023, 0.138 in 2024), which looks like changes to his profile weight, not effort. Totals mostly track class length. Calories belong in item 6 (Head to head), where a week of classes smooths the noise. |
| Planned intensity per segment (`intensity_in_mets`) | 127/134 | Weak: 0.43 / 0.19. |
| Class difficulty estimate | 127/134 | Partial (about 0.5): could make a cross-type comparison fairer, but doesn't make insights more frequent. |
| Heart-rate recovery | none | Not measurable: no Cardio class has a cool-down segment (69 are `Warm Up` + `Cardio`, the rest rounds or one block). |
| Class-average zone times (class details' `averages`) | 49 | Unusable: only 16 distinct values across all 3,203 class files, so not per class. |
| Muscle groups | 62/134 | Not a comparison; could feed the muscle-groups page (`MUSCLE_DISCIPLINES`), just as rarely. |

If it's built (the shape that measured best: loosened rule, extremes only):
- Decide first whether an "about your usual" line is worth showing (today `effort_insight` only speaks at the extremes, and the board shows nothing otherwise). It would be the only discipline that speaks when nothing stands out.
- Rules in `peloton/workout_compare.py` (a Cardio peer rule beside `is_peer`) and `peloton/workout_insights.py` (`NOUN`, and whatever the "usual" line needs); board wording in `peloton/insight_lines.board_view` (headline, sentence, `STRIVE PER MIN` bars, footer such as `12 CARDIO CLASSES`). Tests on hand-made rows, plus the real-row fixture if it gains Cardio workouts.
- Board rows: `build_board_rows.py` / `trim_for_board` keep only `DISCIPLINES`, so the boards need a re-push (`scripts/push_workout_rows.sh`) once Cardio is in. No `ROW_VERSION` bump: the rows already carry Strive and length.
- Depends on: nothing.

## Ideas (not yet sized)

Brainstormed 2026-11-11, after workout insights ran on PelotonPi. Pick one, size it (a short plan in its own `docs/` file if it's big), then move it up to "Up next".

### Workout insights, next steps
- **Seed and switch on every board.** Jen's board (`scripts/push_workout_rows.sh`, then the Workout insights switch); re-push after any `ROW_VERSION` bump.
- **Disciplines version 1 leaves out** (freestyle, stretching, yoga, meditation, cardio): decide which, if any, deserve peers. Measure first, as the bike fill-in did. Cardio was measured on 2026-11-12: unlikely (see "Workout compare: Cardio classes").
- **Learn from the boards.** The `changed while settling` and `insights changed` log lines were added to find out whether Peloton revises a finished workout; after a couple of weeks of PelotonPi logs, decide whether the settling hour is needed.
- **Walk + Run is split in two.** Jen's Walk + Run classes are logged as `walking` (57) or `running` (52), and peers must share the discipline, so each half compares with only its own. Decide whether a class type that appears under both should count as one.

### Whose data is this? (multi-rider boards)
The username page names the rider, but once it's gone nothing says whose workout, goal, journey or milestone is on screen, which matters most on the pages that show what they did that day. Single-rider boards show nothing extra. Mocked up 2026-11-12 on Jen's real pages (a Tread Bootcamp workout, a goal, the journey) on both boards; Joel kept all five as options, undecided:
- **A. Initial in a corner** (`J` in the rider's colour, top-left): touches TREAD BOOTCAMP and TO COLUMBUS on both boards; hard to read.
- **B. Coloured dot in a corner** (3x3): same collisions as A, and means nothing until the colours are learned.
- **C. Coloured line along the top** (row 0): sits on the journey's and the 64x32 titles' top row; panel edges can look dim or sit under a bezel.
- **D. Coloured line down the left** (column 0). Measured on every page and frame: column 0 is empty everywhere except the 64x64 celebration confetti, so it covers nothing, but it touches Head to head (both boards) and the 64x64 PR star burst (content in column 1), and leaves one dark column beside the workout pages (heart, TREAD BOOTCAMP, stats), the name page, the journey's group squares and the heatmap (content in column 2); goals, countdown, streaks, lifetime and discipline pages have 2+ columns. It also makes centred pages look shifted right, runs into the stale-data clock (bottom-left), and moving content in a column breaks the 64x64 byte-identical rule on about six pages.
- **E. The rider's name over the top for the page's first second** (`JEN` in their colour above a coloured rule, then the page as usual): touches no layout, says the name rather than a colour to learn; hides the page title for about a second.
Open questions whichever is picked: which pages (personal ones: workouts, streaks, goals, journey, lifetime, heatmap, milestones, countdowns; not the name page, Head to head or the logo), every page or the first of each section, and a colour per rider (a setting beside each rider's name, with defaults). Draw it once on top of every page (like the padlock, in `ScreenManager`) so no screen changes. Mock-up script: ask Claude to regenerate (real screens over `cookies-jen-dashboard-cache.json`).

### 64x64: a taller workout graph (was "less padding at the top and bottom")
Surveyed 2026-11-12 on every 64x64 page and frame (Jen's real data plus a Tread Bootcamp workout), blank rows at the top / bottom / biggest gap inside: celebration 3/0/4, workout pages 7/2/5, PR card 1/1/7, name page 8/5/6, streaks 3/4/7, Head to head 2/2/5, Total Workouts 9/8/10, countdown 3/3/6, lifetime 3/0/4, journey 1/3/9, heatmap 3/3/5, weekly goal 4/5/13. Findings:
- Most pages have 1-4 rows, normal margins (and the panel's outer rows can be dim or under a bezel): nothing to gain.
- The name page and Total Workouts have rows to spare, but their text is limited by the width (the name and `2,212` already use the biggest font that fits), so the rows can't make them bigger.
- The workout intro's 7 top rows only appear with one-line titles: they're the room a two-line title (BIKE / BOOTCAMP) uses, and they keep every workout page lined up. Leave them.
- The weekly goal's 13-row gap is around the big number by design (#91).
- **The graph frame has room to grow.** The graph is rows 32-53 (22 rows tall); between the discipline title and the `OUTPUT` / `210W` label there's a blank band of 11 rows with a one-line title (rows 12-22) and 9 with a two-line one (rows 16-24). Moving the label up under the title (and the graph's top with it) gives a graph about 30 rows tall, about a third taller, on both title lengths.

The work: in `display/ui/last_workout_screen.py` the 64-row stats phase places the graph from `mid_y` (`label_y = mid_y - 8`, graph `label_y + 4` to `last_row_y - 2`); give the graph frame its own `label_y` a fixed gap under the title (`block_y`), keeping the heart-rate row at the bottom. Mock up first with a one-line and a two-line title (Tread Bootcamp and Bike Bootcamp) and the heart-rate graph (no output), then Joel picks. The zones and muscles slides can stay where they are, or follow the graph so the slides line up; decide from the mock-ups. Only the 64x64 graph frames change: other pages and frames stay byte-identical; update the README's workout screenshots. 64x32 is unchanged (no spare rows). Depends on: nothing; goes with "Workout graphs" (more metrics) if both are done.

### Trend charts from the workout log
Already named under Workout graphs as a later idea; make it its own item. Pages from `peloton/activity.py` windows, like the heatmap: workouts per week as 12 bars, this year against last year by month, discipline mix by month, weekday and hour-of-day pattern. 64x64 first; 64x32 needs one chart per page.

### Yearly goal and pace
`ON PACE FOR 312` / `12 AHEAD OF LAST YEAR`: a yearly workouts (or minutes) target next to the weekly goals, from the log and `comparison_window`. Settings: a field on the Goals card per rider. Fits as a Goals-screen frame or a countdown page.

### Strength: show the reps, weights and form we now know Peloton sends
Strength pages have the fewest stats of any discipline (Strive, heart rate, calories, the top three muscle groups). The saved raw data has much more: `GET /api/workout/<id>?joins=ride,ride.instructor` returns `movement_tracker_data.completed_movements_summary_data` with `total_repetitions`, `num_movements`, `total_volume` (weight x reps, already summed), `completion_percentage`, `longest_streak`, `weight_unit`, `form_feedback_data` and `top_form_tip`, plus one `repetition_summary_data[]` entry per movement (`movement_name`, `completed_reps`, `target_reps`, `weight` by category, `total_volume`, `is_hold`); `movement_tracker_tier` (gold / bronze / inprogress) is a top-level workout field. Details, coverage (25 of 30 of Joel's workouts) and gaps (60% of movements lack `target_reps`; `Compound` is unreliable; timed holds have no reps) are in `docs/fitness-analysis/README.md`, section 13. Candidates for the workout page:
- totals: reps, movements, total volume (`12,450 LB`), completion percent, longest streak, the tier as a badge;
- the heaviest or most-reps movement (`BENT OVER ROW / 8 X 20LB`);
- form: `top_form_tip` and a form score (check what `form_feedback_data` holds, and whether the tip text fits the board);
- a volume bar or chart per movement (60 columns, like the workout graphs), or volume against the same class type's earlier workouts, which the workout insights already compare by weight.
Open points: the log has no `/api/workout/<id>` call today. Workout insights already fetch it once per new complete workout (`Dashboard._workout_insight`), and `workout_features.build_row` reads the strength `asks`, so reuse that response rather than adding a call; a stat for the workouts the board already has needs either that fetch for each (`LOG_VERSION` bump and a re-download per board for `WorkoutLog.trim()` fields) or only the latest workout, and the choice decides the cost. Jen's strength workouts haven't been checked yet. Workouts without a tracker (no movement-tracking device, older classes) must drop the stats, as other pages do. Update `docs/DATA-POINTS.md` (Strength's row and the stats-per-workout table) and the README's workout-page section; check both heights; other pages byte-identical. Relates to the muscle-groups slide (`MUSCLE_DISCIPLINES`) and Workout graphs.

### Weekly goal: active days
A new weekly goal beside the workouts goal: days with at least one workout (`active_days` is already in `period_stats`, and `activity.py` has per-day figures for the heatmap). Goal pages show `3/5 ACTIVE DAYS` with the week's progress, and the goal can be met or missed independently of the workout count (two workouts on one day is one active day). Decide first: which workouts count (the streak's eligible ones, or any), whether the week is Monday to Sunday like the other goals, and whether a goal-met celebration or the streak reminder should know about it. Settings: a field on each rider's Goals card next to `weekly_goals` (per rider, validated in `peloton.config.validate_config`, and `form.py` round trip); an older config without it loads unchanged. Screen: check `goals` on 64x64 and 64x32, where a second goal competes for rows. Relates to the yearly goal idea and Head to head's active-days candidate (item 6), which share `period_stats`.

### Weekly recap
A Monday page (and an optional Pushover) summing last week: workouts, minutes, best output, PRs, goal met or missed, streak. `frame_stats` already has "last week"; mostly a screen plus the Pushover text.

### Weekly insights: looking back over the whole past week
Insights today compare one workout with similar earlier ones. This is the same idea for the week just finished: a page (or two) shown for the first day or two of the new week, then gone. Open-ended on purpose: first look through the data and see what's worth saying, then pick. Starting points:
- Run the checks over each past week of the workout log (`peloton/activity.py` windows; `frame_stats` already has "this week" and "last week") and the saved rows (`RowStore`), and see which weeks have something to say: more or fewer workouts, minutes or active days than the usual week, a PR, the most output in a week, a new discipline or instructor, a goal met or missed, a streak extended, a quiet week after a busy one.
- The private analysis prototype `weekly.py` (kept outside this repo) already walks the log by Monday week (running minutes and the longest steady stretch by pace); see whether any of its week-level measures are worth a board line.
- Rules only, like workout compare: a small set of findings, at most two or three, each with the figures it compared and a "nothing worth saying" state that shows nothing.
Decide before building: how long it shows (Monday and Tuesday? until the first workout of the week?), where it sits in the rotation, whether it's one page or a card plus bars like workout insights, and a settings switch (default off, like `workout_insights`) plus per-rider choice. Needs the week in the rider's timezone, and a memory of what was shown (like `milestone_shown_at`) so a restart doesn't replay it. Goes with Weekly recap above (the plain totals page and Pushover): decide whether this replaces it or adds the "what stood out" to it. Check both heights with `render_rotation.py`.

### Pushover for the board's own events
`peloton/notify.py` sends token alerts only. Candidates, each rate-limited like those: milestone reached, PR set, streak about to break, data stale for 24 h (the dashboard already counts failures), display not beating `/run/peloton-led/health`. Settings card switches per kind. Compute calls/day before adding any poll (none needed: all from the refresh).

### Settings page: preview of the rotation
Serve the `render_rotation.py` contact sheet from the settings page ("what will my board show"), from the saved config and the cached data, refreshed on save. Runs in the settings service, so check the Pi Zero's memory and render time first; Pillow is already in the venv.

### Live workout
Research: does the API expose an in-progress workout (current output, heart rate, time left)? If so, a page that takes over the rotation while the rider is mid-class. If not, drop the item. Settings: on/off per rider.

### Next booked class
Research: Peloton's reservation/schedule endpoints for "ride at 6:30 AM with Jess". A page before the class, from one extra call per refresh (check the rate limit).

### Fitness trend page
The private analysis (kept outside this repo; effort over time by class type, 90 W hold by quarter) suggests a "stronger / flat / weaker than last quarter" page. Only if a measure survives the checks in the README (interval classes dominated the hold figure, so it isn't a fitness number as it stands). Joel decides whether a board should say this at all.

### Housekeeping
- Drop the retired keys (`compact_workout_pages`, `last_workout_duration`, `screen_durations.latest_workouts`, `discipline_milestone_celebrate_within`, `font`) from the loader once every board's config has been saved through the settings page; keep `RETIRED_DISPLAY_KEYS` until then.

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
