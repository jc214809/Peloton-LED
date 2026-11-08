# Roadmap

Planned work. Each item is one branch and one PR into `develop-beta`; delete it when it merges. Item numbers are labels, not a strict order: see "How the items connect" for what has to come first.

## How the items connect

```
Icon touch-ups (by hand) ── independent
5 Varied username facts ── independent
6 More head-to-head stats ── independent (shares 5's per-period helper if 5 lands first)
```

Suggested order: 5, then 6. Icon touch-ups whenever Joel has time.

## Up next

### 5. Varied facts on the username page
The username page's detail lines (built in `peloton_led.py` around the `top_instructors` call) are the same every cycle: total workouts, this week, top discipline, then the top three instructors overall. Rotate through a wider set of facts so each cycle shows something different, for example:
- top three instructors for one discipline (e.g. strength), changing discipline each cycle
- this month's top instructors
- this month's most and least done disciplines
- other all-time or this-month rankings that come cheaply from the workout log

Notes:
- Everything comes from the workout log (no extra API calls); instructor facts stay empty until the backfill is complete, like today.
- Pick a fixed-size set per cycle (rotating which ones appear) so the page length stays predictable; total workouts and this week probably stay every time.
- Skip a fact when there's too little data (e.g. one strength class this month).
- Check name fitting on 32 rows; tests for each fact and for the rotation order.
- Depends on: nothing. Per-period counts (this month's disciplines and instructors) need a helper over the workout log in `peloton/activity.py`, fed via `WorkoutLog.derived` like `daily_minutes`; the log keeps `discipline`, `instructor_id` and `start`, so no `LOG_VERSION` bump. (Item 4's discipline milestones, now part of the Next milestone page, counted from Peloton's overview totals instead, which have no per-period split, so there's no shared helper to reuse.)

### 6. More stats to compete on in Head to head
The `versus` page (`display/ui/versus_screen.py`) compares two riders on the same three stats every time: this week's workouts, minutes and output (`STATS`, fed by `weekly_rivals` in `peloton_led.py` from `weekly_progress`). Add more things to compete on and rotate through them, so the rivalry has more angles. Candidates, all from the workout log:
- calories
- Strive score (`effort_points`)
- distance (miles or km by `uses_metric`; say which disciplines count, like the journey's)
- active days this week (days with at least one workout)
- PRs this week (`pr_output` / `pr_splits`)
- longest single workout
- one discipline's minutes or count (e.g. strength), changing discipline each pass
- this month instead of this week, for some or all of the above

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
- Depends on: nothing. Per-week and per-month figures come from a helper over the workout log in `peloton/activity.py`, fed via `WorkoutLog.derived` like `streak_week_workouts`; every candidate field is already in the log, so no `LOG_VERSION` bump. If item 5 lands first, reuse its per-period helper.

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
