# Roadmap

Planned work. Each item is one branch and one PR into `develop-beta`; delete it when it merges. Item numbers are labels, not a strict order: see "How the items connect" for what has to come first.

## How the items connect

```
Icon touch-ups (by hand) ── independent
5 Varied username facts ── independent
```

Suggested order: 5. Icon touch-ups whenever Joel has time.

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

## Joel, by hand

### Touch up the discipline icons
Some of the 26x24 discipline icons (`DISCIPLINE_ICON_ROWS` in `display/ui/discipline_icons.py`, rasterized from the supplied SVGs) need pixel-level touch-ups. Joel will edit these by hand: each icon is a grid of `#`/`.` strings, so it's hand-editable.
- Preview with `scripts/render_rotation.py --height 64` and `--height 32` after each edit.
- Depends on: nothing.
