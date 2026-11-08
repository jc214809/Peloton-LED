# Roadmap

Planned work. Each item is one branch and one PR into `develop-beta`; delete it when it merges. Item numbers are labels, not a strict order: see "How the items connect" for what has to come first.

## How the items connect

```
6 Celebration screen ──► 4 Upcoming milestones by discipline (celebrates via 6)
                              ▲
5 Varied username facts ──────┘ share a per-discipline / per-period counting helper

Icon touch-ups (by hand) ──► 4, 6 if they show discipline icons
```

- **6 before 4.** The celebration screen works today with the existing total-workout milestones, so it can ship on its own. Item 4 then adds per-discipline milestones and celebrates them with it. Doing 4 first would mean building a throwaway celebration (or none) and redoing it.
- **4 and 5 share their counting.** Both need "how many of X, per discipline (and instructor), over all time or this month" from the workout log. Whichever goes first adds that helper to `peloton/activity.py` (where `daily_minutes` / `streak_week_workouts` already live, fed via `WorkoutLog.derived`); the second reuses it. The log already keeps `discipline` (row bootcamp, bike bootcamp etc. are their own disciplines), `instructor_id` and `start`, so neither needs a `LOG_VERSION` bump or a re-download.
- **6 plays around the rotation** (`run_multi_user_loop` / `build_rotation_pages` in `peloton_led.py`), where the logo now plays between riders; a celebration belongs after it, so the logo still separates riders.
- **Icon touch-ups before 4 and 6** if those pages end up showing discipline icons; otherwise independent.

Suggested order: 6, 4, 5. Icon touch-ups whenever Joel has time, ideally before 6.

## Up next

### 4. Upcoming milestones by discipline
Show milestones that are close: "600th ride next", "5 away from 25 rowing bootcamps". Today's `next_milestone` page (`goals.next_milestone`, built in `peloton_led.py`) only counts down total workouts to the next configured milestone or `milestone_step` multiple.
- Count per discipline from the workout log (row bootcamp is already its own discipline there), so it needs no extra API calls and works after a re-download.
- Pick targets automatically (round numbers: 25, 50, 100, then every 100) and show only those within a few workouts, closest first, so the page is empty most days rather than listing every discipline.
- Decide whether it replaces or sits beside the current `next_milestone` page.
- Crossing one celebrates with item 6's screen, once (extend `celebrated_milestones` to remember per-discipline ones, not just totals).
- Needs a rotation entry, duration and settings-page row, like the other pages; check the 32-row layout.
- Depends on: 6 (for the celebration). Shares the counting helper with 5.

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
- Depends on: nothing. Shares the counting helper with 4; if 4 ships first, reuse its helper rather than adding a second one.

### 6. A proper celebration splash screen
A reached milestone is currently shown on the plain goal page (`'goal'` with `milestone: True`, from `dashboard.pending_milestones` in `peloton_led.py`), which looks like any other progress bar. Build a real celebration screen: big "CONGRATS", "600TH RIDE", animation (fireworks, confetti, sparkles in the spirit of `pr_celebration.py`'s burst), shown ahead of the rest of the rotation.
- Make it one reusable screen that takes a headline, a number/ordinal and a subtitle, so other events can use it: total-workout milestones, per-discipline milestones (item 4), streak records, weekly goal hit, birthdays/anniversaries.
- Ordinals done properly (1ST, 2ND, 3RD, 11TH, 600TH); "ride" vs "run"/"row"/"class" by discipline.
- Keep the once-only behaviour (`celebrated_milestones`) so it doesn't repeat every cycle forever; decide how long it keeps showing (one cycle, one day).
- Design 64x64 first, then 32 rows; preview with `render_rotation.py`.
- Depends on: nothing; ships first with total-workout milestones. Item 4 builds on it. The logo plays before each rider's rotation (except the first after start-up); show the celebration after it.

## Joel, by hand

### Touch up the discipline icons
Some of the 26x24 discipline icons (`DISCIPLINE_ICON_ROWS` in `display/ui/discipline_icons.py`, rasterized from the supplied SVGs) need pixel-level touch-ups. Joel will edit these by hand: each icon is a grid of `#`/`.` strings, so it's hand-editable.
- Preview with `scripts/render_rotation.py --height 64` and `--height 32` after each edit.
- Depends on: nothing. Best done before 6 and 4 if those pages show discipline icons.
