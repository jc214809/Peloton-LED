# 64x32 fit notes

Running log for the `fit-64x32` branch: making every screen fit a 64-wide,
32-row panel. The 64x64 layout is the reference and is **not** being changed;
every change here is behind a `matrix.height < 64` check.

Preview any size with real cached data:

```bash
python scripts/render_rotation.py --height 32 --cache cookies-joel-dashboard-cache.json --out /tmp/joel-32.png
```

Run the real app at 64x32 in the emulator:

```bash
./peloton_led.py --emulated --led-rows 32 --led-cols 64          # your data
./peloton_led.py --emulated --led-rows 32 --led-cols 64 --demo   # demo data
```

**Previews to look at:** `docs/screenshots/64x32/`. It holds `joel-rotation.png`,
`jen-rotation.png`, `demo-rotation.png` (every page and every stat slide
of a full rotation) and `edge-cases.png` (PR variants, 4-digit output, long
titles, Bike Bootcamp, status screens, goals). They are not committed because
the repo is public and two of them show your real workout data.

## Status

| Screen | 64x32 before | Status |
|---|---|---|
| Last workout | Old 3-line layout; title cut off; no stat rotation, HR or calories | **done** |
| PR celebration | Has a compact card | **checked, no change** |
| Username + details | Two value lines touched | **done** |
| Total workouts count page | Two-line names crowded the count | **done** |
| Lifetime disciplines | One text page per discipline (12 pages) | **done**: icon pages, 2 per page |
| Goals / milestones | Unit missing ("2/5" of what?) | **done** |
| Logo | Separate 64x32 art exists | **checked, no change** |
| Login / stale overlays | Bottom corners | **checked**; workout title and calories move out of their way |

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

### Username details (done)
The two white value lines (e.g. `2 WORKOUTS` / `35 MINUTES`) were 5px apart
in a 6px font, so they ran together. On 32 rows the label moved up 2px
(baseline 17), the accent line moved up 1px, and the value lines now sit at
baselines 24 and 31, with a blank row between them. New details rise 2px
instead of 3px so the second line stays on the panel while it animates in.

### Discipline count pages (done)
On 32 rows, two-line names (Total Workouts, Tread/Bike/Row Bootcamp) now
start at baseline 8 instead of 12, which leaves 5 blank rows above the count
instead of 1 (the "p" in Bootcamp was nearly touching it). One-line names
are unchanged.

### Goals and milestones (done)
On 32 rows the weekly goal showed `2/5` or `135/150` with no unit, so you
couldn't tell workouts from minutes, and the milestone showed `2,000` alone.
The weekly goal now moves up (title baseline 6, value 16) to fit the unit
(`WORKOUTS` / `MINUTES`) between the value and the progress bar. The
milestone adds `TOTAL WORKOUTS` in gold under the number, as on 64x64.

### Workouts with HR but no stats (done)
Meditation-style workouts with HR/calories but no rotating stats never
reached the stats phase, so the bar never showed. When there are no stats and
the title fits on one line, the bar now shows in the intro.

### PR celebration (checked, no change)
The burst, the "OUTPUT PR / 512 KJ / 45 MIN CLASS" card, splits PRs and
plain "NEW PR" all fit. The existing 32-row card has room for three lines,
so when there's a gain (`+14 KJ`) it replaces the `45 MIN CLASS` line
(64x64 shows both). No sparkles on 32 rows; they would sit on the text.

### Lifetime disciplines use icon pages (done)
64x64 shows the lifetime counts as pages of four icon tiles (2x2). 64x32
used to show one text page per discipline instead ("Cycling / 639"), which
for your 12 disciplines was 12 pages. Each icon tile is 32x30, so a 32-row
panel fits one row of two: the same icons, colors and counts as 64x64, in 6
pages. The page dots moved from row 63 (off the panel on 32 rows) to the
bottom row. The "Total Workouts" page is still the text page.

**This changes 64x32 more than any other item here.** If you prefer the old
text pages, revert the `lifetime_overview_pages(... page_size=...)` change in
`build_rotation_pages`.

### Other
- The startup warning "Detailed workout view is simplified on 32-row
  panels" was removed because it's no longer true.
- README's 64x32 sections were updated to describe the new behavior.
- Verified end to end: `peloton_led.py --emulated --demo --led-rows 32
  --cycles 1` ran a full rotation for both configured users and exited
  cleanly (in the emulator on port 8893, so your 8888 session was untouched).

### Trophy for PRs, red Peloton P (both boards, requested 2026-09-25)
- The gold `PR` letters on the workout screen are now a 7x7 pixel trophy:
  a gold cup with handles on a darker gold stem and base. The small star beside
  a record-setting output value is a trophy too. On 64x64 the corner trophy
  now shows only during the intro. In the stats phase it touched wide labels
  like `AVG RESISTANCE`, and the trophy beside the output value marks the PR
  there. (Rowing splits PRs are still marked in the intro only.)
- The startup Peloton P is Peloton red (#DF1C2F) instead of white on both
  boards. A custom `display.logo_path` image is unaffected.
- The PR celebration screen keeps its star burst.

## Open questions for Joel

1. **`compact_workout_pages`**: the new 32-row layout makes this option
   unnecessary. Remove the option and the old layout, or keep them?
2. **Stale-data clock over the heart:** on both 64x64 and 64x32, the clock icon
   (shown after 3 failed refreshes) sits on top of the ♥ HR. I left it alone
   because it's the same on 64x64.
3. **Your `config.json` was briefly pushed** (my mistake: a `git commit -a`
   in commit `3985c6e`). It held no secrets: first names, the env-var
   *names* for credentials, goals, milestones and the timezone. Commit
   `Restore config.json` puts the branch back to main's version, and your
   local edits are still in your working copy. The file is still visible in
   that one commit's history. If you want it gone completely, I can drop
   the two commits and force-push `fit-64x32`; I didn't rewrite the pushed
   history without asking.
4. **Lifetime icon pages on 32 rows** replace the old one-discipline-per-page
   text screens. Keep that, or go back to the text pages?

## Where things stand

Everything on the status table is done or checked. 64x64 output is
byte-identical to before this branch (Joel, Jen and demo rotations), and
all 286 tests pass. The branch is pushed; no PR yet. It's based on
`last-workout-stat-rotation` (PR #2), so merge #2 first or point this PR
at that branch.
