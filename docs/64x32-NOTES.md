# 64x32 fit notes

Running log for the `fit-64x32` branch: making every screen fit a 64-wide,
32-row panel. The 64x64 layout is the reference and is **not** being changed;
every change here is behind a `matrix.height < 64` check.

Preview any size with real cached data:

```bash
python scripts/render_rotation.py --height 32 --cache cookies-joel-dashboard-cache.json --out /tmp/joel-32.png
```

## Status

| Screen | 64x32 before | Status |
|---|---|---|
| Last workout | Old 3-line layout; title cut off; no stat rotation, HR or calories | **done** |
| PR celebration | Has a compact card | to check |
| Username + details | Has a compact layout | to check |
| Total workouts / lifetime | One discipline per page on 32 rows | to check |
| Goals / milestones | Has 32-row positions | to check |
| Logo | Separate 64x32 art exists | to check |
| Login / stale overlays | Bottom corners | to check |

## Changes and decisions

### 64x64 is untouched: how that's checked
Before any change I rendered the full 64x64 rotation (Joel cache, Jen cache,
demo data) to PNG, and after every change I re-render and compare the files
byte for byte. They have been identical after every commit so far.

### Last workout screen (done)
Uses the same two phases as 64x64, with the room shared out differently:

- **Intro (first 4s):** discipline title (colored, 5x8 font) / `30 MIN` in blue
  with a gold `PR` on the right for PR rides / class title on up to two lines.
- **Stats:** discipline title stays at the top / grey label / one large value
  (6x9 font, falls back to smaller fonts if it's too wide) / ♥ HR + calories bar.

What's different from 64x64, and why:
1. **The instructor is the first rotating stat**, not part of the intro. Under
   a two-line class title there are no rows left for it.
2. **The HR/calories bar only shows during stats**, not during the intro.
   With a two-line title the title's last line uses rows 24-28 and the bar
   needs 26-31.
3. **Long instructor names** (for example "JERMAINE JOHNSON", which is wider
   than 64px even in the 4x6 font) wrap to two lines under the INSTRUCTOR
   caption, and the bar is hidden for that one slide.
4. **New stats rise 2px instead of 3px** as they come in, so the value never
   touches the bar mid-animation.
5. **The page is one stat longer** on 32 rows (the instructor's turn), so the
   rotation still shows every stat exactly once.
6. The title's second line is shortened when the login padlock or stale-data
   clock is showing, so it doesn't run under the icons.

The old 32-row layout is still there when `display.compact_workout_pages` is
`true`, so turning that on keeps the old behavior. See Open questions.

Code: `LastWorkoutScreen._render_short` and `rotating_details` in
`display/ui/last_workout_screen.py`; tests in `tests/test_64x32.py`.

## Open questions for Joel

1. **`compact_workout_pages`**: the new 32-row layout makes this option
   unnecessary. Remove the option and the old layout, or keep them?
2. **Stale-data clock over the heart:** on both 64x64 and 64x32, the clock icon
   (shown after 3 failed refreshes) sits on top of the ♥ HR. I left it alone
   because it's the same on 64x64.
