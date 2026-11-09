# Roadmap

Planned work. Each item is one branch and one PR into `develop-beta`; delete it when it merges. Item numbers are labels, not a strict order: see "How the items connect" for what has to come first.

## How the items connect

```
Icon touch-ups (by hand) ── independent
6 More head-to-head stats ── after facts-engine step 1 (period_stats) merges
7 Journey moments ── after the journey redesign (journey-mile-groups) merges
Name page facts engine ── steps 1-8 in docs/NAME-PAGE-FACTS.md, in order; item 6 builds on step 1
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
The plan is in `docs/NAME-PAGE-FACTS.md` ("Plan"): one PR per step. Steps 0 (PR #65) and 1 (time frames and `period_stats`, branch `facts-step-1-frames`) are built. Remaining: 2 filters, 3 measures and bests, 4 comparisons, 5 events, 6 choosing what's interesting (scores and a cool-down, the step that changes pass 0), 7 together facts, 8 optional settings and new log fields. The page stays six highlights (24 s) throughout.
- Build brief for a Sonnet 5.5 session, one step each: `docs/NAME-PAGE-FACTS-HANDOFF.md`.
- Depends on: step 1 merged. Item 6 (Head to head) should build on step 1's `period_stats`.

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
