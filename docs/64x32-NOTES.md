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
| Logo | Separate 64x32 art exists | **done** (2026-11-06): mark on the left, words beside it |
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
2. **The HR/calories bar shows during stats, and in the intro only under a
   one-line title.** With a two-line title the title's last line uses rows
   24-29 and the bar needs 26-31. (Until 2026-11-11 the intro also skipped
   the bar for a one-line title whenever the workout had stats, so a
   one-line title like `Outdoor Walking` or `Pop Ride` had none either;
   only stat-less workouts such as meditation showed it. Closing the rows
   up by one each under a two-line title was tried and overlaps the
   descenders, so those titles wait for the stat frames: Joel's call,
   2026-11-11.) Either figure alone is drawn when the other is missing.
3. **Long instructor names** (for example "JERMAINE JOHNSON", which is wider
   than 64px even in the 4x6 font) wrap to two lines under the INSTRUCTOR
   caption, and the bar is hidden for that one slide.
4. **New stats rise 2px instead of 3px** as they come in, so the value never
   touches the bar mid-animation.
5. **The page is one stat longer** on 32 rows (the instructor's turn), so the
   rotation still shows every stat exactly once.
6. The title's second line is shortened when the login padlock or stale-data
   clock is showing, so it doesn't run under the icons. A two-line instructor
   name is not: it is drawn the same every time (2026-11-09, Joel) and an icon
   may cover its ends, since the icon says the board isn't fully working.

The old two-page 32-row layout (`display.compact_workout_pages`) was removed
on 2026-11-08 at Joel's request; an old config's setting is ignored.

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
(The milestone card has since become the celebration screen; see below.)

### Milestone celebration (done)
64x64 stacks an 18x16 trophy over three lines: the number (10x20) with a
small raised `TH` (5x8, its top level with the digits'), `WORKOUT` (5x8)
and the rider's name (5x8). 32 rows have no room to stack, so a 12x10
trophy sits on the left and the three lines are centred in the columns to
its right: the name on top (4x6), the number (7x13B) with a raised `TH`
(4x6), and `WORKOUT` (4x6). The number has a comma (`2,000`) like the
board's other totals, except when dropping it keeps the big font: five
digits (`10000`) don't fit it with one on either size. The fonts give the
comma a whole digit-wide cell, which left a wide gap either side of it, so
it's drawn closed up, with the same gap as between digits (`_COMMA_INK`). A name too long for its line is left off.

### Next milestone (done)
The `next_milestone` page (`CountdownScreen`; the total's or a discipline's) stacks
`4 MORE` (10x20 and 7x13B), `500TH` (10x20, raised `TH`) and the name (6x13B,
smaller fonts for long names, in its Lifetime colour) over a bar on 64x64.
32 rows can't fit a second 13-pixel number line and a bar, so it reads
`4 MORE` (7x13B), `TO 500` (6x9 and 7x13B, no ordinal ending) and the name
(`WORKOUTS` for the total; 6x9, `TREAD BOOTCAMP` in 4x6), with no bar. Not 5x8: its narrow G and T
left uneven gaps (`S TRENG TH`). The celebration's noun is the
discipline's name (`STRENGTH`); `TREAD BOOTCAMP` and `BIKE BOOTCAMP` are too
wide beside the trophy (47 columns, 4x6), so they fall back to their last
word, `BOOTCAMP`. 64x64 fits the whole name.

### Workouts with HR but no stats (done)
Meditation-style workouts with HR/calories but no rotating stats never
reached the stats phase, so the bar never showed. When there are no stats and
the title fits on one line, the bar now shows in the intro (since 2026-11-11
a one-line title shows it whether or not there are stats).

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

### Board logo (both boards, requested 2026-11-06)
- The startup logo is now the red Peloton mark, PELOTON, a heart-rate zone
  bar and LED. On 64x64 they stack: mark on top, then PELOTON, the bar and
  L E D. 64x32 has no room to stack, so the mark sits on the left (the
  32-row art, unchanged) with PELOTON, the bar and L E D in the 37 columns
  beside it. PELOTON ends one pixel from the panel's edge.
- Both boards use the 32-row mark (23x28); the old 64-row art is gone.

### Versus week strip (both boards, requested 2026-10-31)
- Seven dashes along the bottom of the versus page, Monday first: finished
  days grey-blue, today red, days to come near-black.
- 64x64 deliberately changes here: the strip is 2 rows (60-61) and replaces
  the `THIS WEEK` title, so names and stats move up 7 rows. Every other
  64x64 page is byte-for-byte unchanged.
- 64x32: the strip is 1 row (31), under the big values with row 30 left
  blank. Nothing above it moved.
- 64x32 names sit one row lower (baseline 7, was 6). The leader's 7-row
  trophy is bottom-aligned with the name, so at baseline 6 its rim landed on
  row -1 and was cut off (reported 2026-11-03). It now spans rows 0-6.

### Muscle groups slide (both boards, requested 2026-11-07)
- A new last slide on Strength workout pages when Peloton sends muscle groups
  (other disciplines: add them to `MUSCLE_DISCIPLINES`): the
  top three, most worked first, coloured by Peloton's bucket (1 yellow,
  2 orange, 3 red), bars scaled to the top muscle. Holds 1 s longer, like the
  graph and zones slides. Every other frame is unchanged on both boards.
- 64x64: `MUSCLES WORKED` 8 rows under the discipline (row 20 for a one-line
  header), then name left, percent right, and a 2-row bar under each, 9 rows
  apart.
- 64x32: no room for a label, so three 5-row half-brightness bars from row 8
  with the name and percent in white over them. Unlike the graph and zones
  slides it keeps the heart-rate/calorie row.

### Insight frames (both boards, `display.workout_insights`, card + bars 2026-11-11)
- Replace version 2's two-line insight slide. At most 2 insights a workout (`MAX_BOARD_INSIGHTS`), after
  the graph / zones / muscles slides; every frame holds 1 s longer, like those. 64x64 shows each as a card
  (the sentence) then bars; 64x32 as bars, then the sentence on 1-2 pages. Content from
  `peloton/insight_lines.board_view`.
- No discipline title and no heart-rate/calorie row on any insight frame (both boards). The other slides
  are unchanged, insights or not (`test_the_other_slides_are_unchanged_by_the_insights`).
- Colours: the headline, today's bar and lit blocks amber (down, missed, under the callouts), green (up,
  go up, heavier, easiest), red (hardest by HR) or white (in line); the usual's bar, labels and footers grey
  (145, 165, 190); an empty share bar or unlit block (70, 80, 95); the header gold (255, 200, 0). Sentence
  words with a digit take the discipline colour, the rest white.
- 64x64 header: the 5x7 lightbulb at (3, 2), `INSIGHT` in `titles` at x 11 on baseline 9, `1/2` / `2/2`
  right-aligned in `stats` grey when there are two, a 1-px discipline-colour rule on row 12 (columns 2-61)
  in place of the title. Card: the sentence in up to 5 centred lines from baseline 21, 7 apart (vertically
  centred in 21-49 when shorter); the footer (`9 SIMILAR RIDES`, `VS 12 SIMILAR`, `5 CLOSEST RIDES`,
  `VS THE CALLOUTS`, `VS PAST CLASSES`) grey on baseline 61. Bars: the headline centred on baseline 22
  in `titles` (`stats` when wider than 62 px); `TODAY` / `TYPICAL` labels with the value right-aligned on
  baselines 32 and 45 and a 4-row bar under each (59 px at full); a share bar (`TIME UNDER` / `THE
  CALLOUT`) on rows 35-41; or blocks from row 34, 7 px 3 apart, shrinking (5/2, 3/1, 2/1, 1/1) when many
  sets would not fit 60 px, with `3 IN A ROW` under a streak. The reason (`AN EASIER DAY`, `LESS PER BEAT`,
  `TURN IT UP`, a movement name ...) white on baseline 61. The hardest / easiest by HR bars are Strive per
  minute of class with no unit beside the numbers, so their reason line is `STRIVE PER MIN` (Joel,
  2026-11-11; it was `HARDEST OF 12`, which the headline and sentence already say).
- 64x32 bars: the bulb at (1, 0), the headline in `stats` on baseline 6 centred in columns 9-63 (a headline
  wider than that room, `STRONG BOOTCAMP`, keeps its first word); bars on rows 9-13 and 17-21, 40 px from
  x 1, the numbers right-aligned on baselines 13 and 21 with no labels or units; a share bar on rows 11-18;
  blocks 5 px 2 apart from x 4 on rows 11-15 (shrinking as on 64 rows); the reason on baseline 30.
- 64x32 sentence pages: the bulb, `INSIGHT` in gold `stats` on baseline 6, `1/2` right-aligned when there
  are two pages, a discipline-colour rule on row 8, three lines on baselines 16, 23 and 30.
- Tough class (green): one sentence page, `WAY TO` / `CHALLENGE` / `YOURSELF!` (the numbers are on the bars);
  the bars frame's reason line is `9.1 → USUALLY 7.0` on baseline 30 with the arrow drawn in pixels (5x5,
  rows 25-29, the text's own rows, centred with 2 dark columns either side of the inks (columns 13-17 after
  `9.1`, 14-18 after `9.0`: the 1 has 2 px of ink, other digits 3; `_parts_layout`; Joel, 2026-11-12: it sat
  a row low and off-centre); `9.1` from column 1, ending at column 63). 64x64 draws the same line on
  baseline 61 and a 5-line card whose first line, `WAY TO CHALLENGE`, is the one 16-character (64 px) line.
  With no output insight behind it the bars are the two ratings on a 0-10 scale (the figure's `top`: a 7.8
  fills 31 of the 64x32 bar's 40 px, not all of it) and the reason line is plain `CLASS RATING`, no arrow;
  the 64x64 bars label the usual `USUAL` (the figure's `usual_label`), with or without output.
- A reason wider than 60 px (only a movement name) scrolls like the name page's highlights (hold, glide,
  hold; `UsernameScreen.scroll_offset`), the 2-px margins blanked.
- Spacing (Joel, 2026-11-11): weights are one word, `40LB`, in the sentence, the reason and the 64x64 bars
  (watts and mph keep their space, `124 W`). The colon's dot sits mid-cell, which left 6 blank columns
  before the next word against 5 between other words, so the word after a colon is drawn
  `COLON_GAP_TRIM` (3) px closer: 3 blank columns. Wrapping still counts characters, and a tighter line
  is only narrower, so nothing that fitted stops fitting. `40LB` makes the worst streak sentence
  (`100LB ON MEDIUM`) six lines, so it falls back to `3 IN A ROW`.

- Instructor milestone (`instructor_milestone`, gold, words only; Joel, 2026-11-12): no bars frame on either
  board (`figure` is None), so `rotating_details` makes one `insight_card` (64x64) or one `insight_words` page
  (64x32, page 0). 64x64 card: `YOUR 200TH` / `CLASS WITH` / `JESS SIMS!` (a long name wraps by words at
  15 characters: `CHELSEA JACKSON` / `ROBERTS!`; first class `YOUR FIRST`) with the footer `SINCE MAR 2019`
  (the first class with them) or `WELCOME!` for a first. 64x32 page: `YOUR 200TH CLASS` / `WITH JESS SIMS!`;
  these lines run edge to edge, 16 characters = 64 px (`insight_lines.EDGE_MAX`, like the name page), the
  name wrapping at 16 (`WITH CHELSEA` / `JACKSON ROBERTS!`, 3 lines). The ordinal (or `FIRST`, via the
  view's `highlight`) is gold, the rest soft white. A 1000th class (17 characters) falls back to the 64x64
  wording on 64x32.

### Journey: miles by type (both boards, requested 2026-11-08)
Joel found the 64x64 journey page showed less than the 64x32 one: no percent,
and on the way home it still listed Columbus at the top and Disney World by
the castle while saying `414 TO HOME`. Both boards now use one design
("C", picked from three mockups), and the map and castle are gone:
- Heading `TO DISNEY WORLD` (or `TO COLUMBUS` on the way home), big miles
  with `MI`, `138.4 TO GO` with the percent beside it (rounded down, so never
  100% short of the destination), and an orange bar for this leg. Past the
  first leg, `TRIP 2` sits at the bar's right end.
- The miles split three ways, by how they were covered
  (`peloton.journey.MILE_GROUPS`): BIKE (Cycling, Bike Bootcamp), ROW
  (Rowing, Row Bootcamp), and WALK/RUN for everything else (tread, outdoor,
  hiking), so every mile is in a row. Joel picked the WALK/RUN name; four
  groups (tread and outdoor apart) would not fit three rows.
- 64x64: one page, the groups listed under the bar with colour squares.
- 64x32: two steps sharing the page's time (`step_seconds`, like Head to
  head's `stat_seconds`): the trip, then `MILES BY TYPE` with a bar in the
  groups' colours and a row each. At least 4 s a step, so 8 s with two
  groups; with one group there's no split, so the trip stays up.
- Animation (both boards, all done by `INTRO_SECONDS`, 1 s into a step, at
  20 fps): the bar fills with an ease-out while the miles count up from the
  leg's start (`counted_miles`), the bar's white tip then pulses (2 s, down
  to 35%); 64x64 slides the group rows in from the left 0.15 s apart, 64x32
  grows the split bar a colour at a time with each row appearing as its
  colour lands. The arrival, turning-for-home and step hand-off effects are
  ROADMAP item 7. `render_rotation.py` captures settled frames.
- Decimals (2026-11-11, Joel's call): each group's miles read `123.45`; the
  big total keeps one decimal on both boards (`1,234.6`), and the `TO GO` line
  its one decimal. A figure drops to fewer decimals only where it won't fit,
  decided once from the final figure so the count-up never changes format.
  The total must fit a big font beside `MI` (2 px left, 2 px gap, 2 px margin
  right; `big`, then `bold` on 64 rows, `countdown` on 32): 32 rows keep `big`
  up to `4,444.4`; 64 rows take `bold` from `1,234.6` and drop the decimal at
  `13,333`. A group figure must leave its whole label and a 3 px gap (so
  `WALK/RUN` drops to one decimal from 100 miles on 64 rows; `123.45` still
  fits on 32). The groups are rounded together (`group_cents`, largest
  remainder in hundredths) so the rows add up to the total, e.g. 22.64 + 3.54
  = 26.18 where 22.636 and 3.539 rounded alone would read 26.17. Lit columns
  stay within 2..61 at both heights for 4- and 5-digit worst cases (tests
  check a 1 px margin).

## Open questions for Joel

1. ~~**`compact_workout_pages`**~~: removed with the old layout (2026-11-08).
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
