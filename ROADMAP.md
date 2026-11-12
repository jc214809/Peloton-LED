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
Workout compare: Cardio classes ── independent (workout compare is on develop-beta, #81/#82)
Ideas (not yet sized) ── trend charts share windows with item 6; yearly goal and weekly recap use `frame_stats`
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

### Workout compare: Cardio classes
Cardio (HIIT, Low Impact, Dance and Family Cardio) is outside workout compare today (`workout_compare.DISCIPLINES`). It has no output, speed, callouts or weights, only heart rate, so the one rule that could apply is the heart-rate effort one (`effort_insight`: Strive per minute against similar classes, "hardest" / "easiest of your last N").

Tried as-is on 2026-11-11 (Cardio added to `DISCIPLINES` in a scratch run over the Mac's row stores, last 12 months):

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
- Decide first whether an "about your usual" line is worth showing (today `effort_insight` only speaks at the extremes, and the board shows nothing otherwise).
- Rules in `peloton/workout_compare.py` (a Cardio peer rule beside `is_peer`) and `peloton/workout_insights.py` (`NOUN`, and whatever the "usual" line needs); board wording in `peloton/insight_lines.board_view` (headline, sentence, `STRIVE PER MIN` bars, footer such as `12 CARDIO CLASSES`). Tests on hand-made rows, plus the real-row fixture if it gains Cardio workouts.
- Board rows: `build_board_rows.py` / `trim_for_board` keep only `DISCIPLINES`, so the boards need a re-push (`scripts/push_workout_rows.sh`) once Cardio is in. No `ROW_VERSION` bump: the rows already carry Strive and length.
- Worth it? About one Cardio class a month each, so it's small. Re-run the scratch count before starting.
- Depends on: nothing.
## Ideas (not yet sized)

Brainstormed 2026-11-11, after workout insights ran on PelotonPi. Pick one, size it (a short plan in its own `docs/` file if it's big), then move it up to "Up next".

### Workout insights, next steps
- **Seed and switch on every board.** Jen's board (`scripts/push_workout_rows.sh`, then the Workout insights switch); re-push after any `ROW_VERSION` bump.
- **Class difficulty as an insight.** The raw `rides/<ride_id>.json` already carries `difficulty_rating_avg`; a `HARDER THAN USUAL` / `EASIER THAN USUAL` line that explains a low output ("a 8.9 class, you usually do 7.6"). Rules only, add to `workout_insights.py` and `WORKOUT-COMPARE-SPEC.md`.
- **Disciplines version 1 leaves out** (freestyle, stretching, yoga, meditation, cardio): decide which, if any, deserve peers. Measure first, as the bike fill-in did.
- **Instructor insights.** `4TH CLASS WITH JESS`, `FIRST TIME WITH THIS INSTRUCTOR`, output against your average with them. The log has the counts already (`instructor_counts`).
- **Learn from the boards.** The `changed while settling` and `insights changed` log lines were added to find out whether Peloton revises a finished workout; after a couple of weeks of PelotonPi logs, decide whether the settling hour is needed.

### Insight wording
Replace "usual" on the insight pages. Leaning: `CONSISTENT` for the in-line headline and reason (not "on target": there's no target, and it reads like the callout insights), `TYPICAL` for the bar label and "VS TYPICAL 140" (the figure is a median). Touches `peloton/insight_lines.py`, `peloton/workout_insights.py` text, `WORKOUT-COMPARE-SPEC.md` and their tests. (The softer white and the slate "usual" bar are done.)

### Whose data is this? (multi-rider boards)
The username page names the rider, but once it's gone nothing says whose workout, goal, journey or milestone is on screen, which matters most on the pages that show what they did that day. Options to mock up with `render_rotation.py` and pick from:
- a small rider tag (initial or short name in the rider's colour) in a corner of every page, where there's room on 64x64 and 64x32;
- a thin rider-coloured line or border on each page, a colour per rider (a setting beside each rider's name);
- repeat the name briefly at the start of each page, or every few pages, instead of only the first;
- only on pages that are personal (workouts, goals, journey, milestones), not shared ones (Head to head, logo).
Single-rider boards show nothing extra. Constraints: no change to the 64x64 layout beyond the chosen mark, pages' minimum times unchanged, byte-identical other pages for a single rider.

### Journey page: two decimals on the miles
Show two decimal places (`123.45`) on the journey page for the distance travelled and for each discipline's miles (the BIKE / WALK/RUN / ROW groups from `journey_progress`), where it shows fewer today. Check first how each figure is formatted now in `display/ui/journey_screen.py` and whether the groups still add up to the total after rounding. Widths are the risk: a long figure (`1,234.56 MI`) on 64 columns, and on 32 rows the two steps with their rows. Measure by lit pixels (see item 6's fitting rules) and fall back to fewer decimals only if it can't fit, keeping the decision in the notes. Check both heights with `scripts/render_rotation.py` and frame strips; the other pages stay byte-identical. Relates to item 7 (journey moments), which touches the same screen.

### Journey page: colours that don't read as Christmas
The journey's groups take their Lifetime-page colours (`GROUP_COLORS` in `display/ui/journey_screen.py`: bike red, walk/run green, row blue) beside the orange bar, and the red and green together look like Christmas. Pick another set for the three groups on the journey only (the Lifetime pages and the milestone pages keep theirs), e.g. from the orange/amber, teal, blue and violet families, and mock up two or three sets with `render_rotation.py` on both heights; Joel picks. Keep them distinct from each other and from the orange bar, readable as small text on black, and the 64x32 split bar (one colour per group) legible. Also check the other graphs for the same pairing (the heart-rate zone colours in `logo_art.ZONE_COLORS` run blue, green, yellow, orange, red) before deciding whether "graphs" means just the journey. Other pages stay byte-identical.

### 64x64: less padding at the top and bottom
Check whether the 64x64 pages would have more room if they left less empty space above the first line and below the last (the bottom row and the margins above the week strip, bars and footers). Survey first: for each page, measure the blank rows at the top and bottom from `render_rotation.py --height 64` output and list what could use them (a bigger font, another stat line, a taller graph, the "weekly goal is small" text below). The 64x64 layout is the reference, so every page that changes needs a before and after preview, and pages that don't change must stay byte-identical. Watch the hardware: the panel's outer rows can look dimmer or be hidden by a bezel, so check on a real board before trusting a design that uses row 0 or 63. Relates to the page-time minimums in `peloton/screen_times.py` if a page gains frames.

### Trend charts from the workout log
Already named under Workout graphs as a later idea; make it its own item. Pages from `peloton/activity.py` windows, like the heatmap: workouts per week as 12 bars, this year against last year by month, discipline mix by month, weekday and hour-of-day pattern. 64x64 first; 64x32 needs one chart per page.

### Yearly goal and pace
`ON PACE FOR 312` / `12 AHEAD OF LAST YEAR`: a yearly workouts (or minutes) target next to the weekly goals, from the log and `comparison_window`. Settings: a field on the Goals card per rider. Fits as a Goals-screen frame or a countdown page.

### Name page: make "ON THIS DAY" worth reading
`ON THIS DAY` / `1 YEAR AGO` / `20 MIN ROW` (`username_facts.event_facts`, from `events.on_this_day` in `activity.event_stats`) only repeats what was done, which says little. It picks the nearest earlier year's longest workout for today's date. Ideas, all from the workout log (no new calls; a new field needs a `LOG_VERSION` bump, one re-download per board, so prefer what's already there):
- **Compare it to today's state:** `20 MIN ROW` then `YOU'VE DONE 40 SINCE` / `NOW 60 MIN`, or this year's count in that discipline against the same date last year (`412 VS 380 WORKOUTS`, the way comparisons already read).
- **What made it notable:** a PR or record that day, the class's instructor (`WITH JESS`), the output or distance (`8.1 MI`, `182 W`) instead of just minutes, or "your first" of a discipline.
- **Pick the best memory, not the longest workout:** score the day's workouts (a PR, the year's longest, a first, a milestone number such as the 500th) and show the highest; skip the fact when nothing is above ordinary, so a plain 20-minute row doesn't qualify.
- **Pile up the years:** several earlier years on the same date in one line (`1, 2 AND 3 YEARS AGO`) or the same class taken again.
- **Streak or total context:** `YOUR 1,200TH WORKOUT`, or `DAY 4 OF A STREAK`.
Decide the rule with `scripts/list_facts.py` on both riders' real logs: how often it appears today, how often each idea would fire, and its score against the other events (`KINDS`, threshold constants beside `MIN_EVENT_WORKOUTS`). The label must fit 15 characters of the `stats` font. Update `docs/NAME-PAGE-FACTS.md` (the events table) and the tests for `event_facts`. Depends on: the facts engine (built).

### Name page: two-line facts that say what they mean
The facts (`peloton/username_facts.py`) are a label and one or two short lines (`MOST IN 30 DAYS` / `CYCLING`, `ON THIS DAY` / `1 YEAR AGO` / `20 MIN ROW`), each limited to 15 characters of the `stats` font (60 px), so many are clipped into fragments (`VS 30 BEFORE`, `+32 WORKOUTS`) that need the rider to guess the sentence. Look at splitting each fact into a clear two-line statement, e.g. a headline line (what it is) and a detail line (the figure and what it's against), so each reads as a sentence. Survey first: run `scripts/list_facts.py` on both riders' real logs, list every `kind` with its current lines, and mark the ones that read ambiguously on the board. Then redo them one `kind` group at a time (ranks, bests, comparisons, events, instructors), not all at once. Check what the screen already supports (`UsernameScreen.wrap_two_lines`, the scrolling value line, the `short_label` fallback, 32 rows with no spare rows) so the wording is made to fit the layout, not the reverse; decide whether 64x32 gets a shorter version. Tests: each `kind`'s lines fit, and the scoring and cool-down keys (`kind`, `key`) don't change. Update `docs/NAME-PAGE-FACTS.md`. Goes with "make ON THIS DAY worth reading" above, which is the first example.

### Name page: what does COMEBACK mean?
`COMEBACK` / `CYCLING` / `AFTER 45 DAYS` is hard to read on the board: after what, and a comeback to what? Today (`username_facts.event_facts`) it fires for a discipline with at least `MIN_EVENT_WORKOUTS` workouts whose last workout came at least `MIN_COMEBACK_DAYS` after the one before it, shown for `EVENT_WINDOW_DAYS` after that return; the gap reads `AFTER n DAYS`, or `AFTER n YEARS` past `MAX_SINCE_DAYS`. Work out what a comeback should mean to the rider and say so on the page. Questions: is it per discipline or any workout (a week off everything versus a break from rowing); what gap counts (the same 14 days for a daily rider and an occasional one, or relative to their usual rhythm); should it show the first workout back, or celebrate the return once the rider is back to usual (a second or third workout); does a rider who was ill or travelling count; and how does it differ from `SINCE` / `LAST CLASS WITH` (the other "it's been a while" facts), which may say the same thing. Wording: two lines that say what it is (`FIRST ROW IN 45 DAYS`, `BACK AFTER 6 WEEKS`) rather than the label alone. Use `scripts/list_facts.py` on both riders' real logs to see when it fires today and which of the options would fire instead. Update `docs/NAME-PAGE-FACTS.md` and the `event_facts` tests; scoring and cool-down keys stay the same. Goes with the two-line facts item above.

### Strength: show the reps, weights and form we now know Peloton sends
Strength pages have the fewest stats of any discipline (Strive, heart rate, calories, the top three muscle groups). The saved raw data has much more: `GET /api/workout/<id>?joins=ride,ride.instructor` returns `movement_tracker_data.completed_movements_summary_data` with `total_repetitions`, `num_movements`, `total_volume` (weight x reps, already summed), `completion_percentage`, `longest_streak`, `weight_unit`, `form_feedback_data` and `top_form_tip`, plus one `repetition_summary_data[]` entry per movement (`movement_name`, `completed_reps`, `target_reps`, `weight` by category, `total_volume`, `is_hold`); `movement_tracker_tier` (gold / bronze / inprogress) is a top-level workout field. Details, coverage (25 of 30 of Joel's workouts) and gaps (60% of movements lack `target_reps`; `Compound` is unreliable; timed holds have no reps) are in `docs/fitness-analysis/README.md`, section 13. Candidates for the workout page:
- totals: reps, movements, total volume (`12,450 LB`), completion percent, longest streak, the tier as a badge;
- the heaviest or most-reps movement (`BENT OVER ROW / 8 X 20LB`);
- form: `top_form_tip` and a form score (check what `form_feedback_data` holds, and whether the tip text fits the board);
- a volume bar or chart per movement (60 columns, like the workout graphs), or volume against the same class type's earlier workouts, which the workout insights already compare by weight.
Open points: the log has no `/api/workout/<id>` call today. Workout insights already fetch it once per new complete workout (`Dashboard._workout_insight`), and `workout_features.build_row` reads the strength `asks`, so reuse that response rather than adding a call; a stat for the workouts the board already has needs either that fetch for each (`LOG_VERSION` bump and a re-download per board for `WorkoutLog.trim()` fields) or only the latest workout, and the choice decides the cost. Jen's strength workouts haven't been checked yet. Workouts without a tracker (no movement-tracking device, older classes) must drop the stats, as other pages do. Update `docs/DATA-POINTS.md` (Strength's row and the stats-per-workout table) and the README's workout-page section; check both heights; other pages byte-identical. Relates to the muscle-groups slide (`MUSCLE_DISCIPLINES`) and Workout graphs.

### Cardio workouts: no heart rate or calories on the first page
On a Cardio workout the page that opens with the class title and instructor shows no heart-rate and calorie row at the bottom (`_draw_hr_calories` in `display/ui/last_workout_screen.py` draws it only when `summary['hr_avg']` and `summary['calories']` are numbers). Find out why: is the data missing for Cardio (the summary from `peloton/summaries.py`, the raw workout and performance graph in `perf_graphs/` or `training-data/`: no heart-rate monitor on those workouts, `hr_avg` absent or null, Peloton's calories field named differently for the discipline), is the row skipped by a Cardio-specific branch, or is the cached summary stale. `docs/DATA-POINTS.md` ("Why some workouts lack a stat") says which stats Peloton sends per equipment and lists Cardio under "No equipment"; compare with what the recent Cardio workouts actually carry. Fix by whichever applies: map the right field into the summary, fall back to the other stat when one is missing (calories alone, heart rate alone), or leave the row off on purpose and record why. Test with a saved real Cardio payload and a summary missing each field; check 64x64 and 64x32 (the 32-row layout has its own bottom lines); update `docs/DATA-POINTS.md`. Other disciplines unchanged.

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
