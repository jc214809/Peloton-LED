# Name page facts: built and ideas

The name page (`username` in `rotation`) shows the rider's name over rotating highlights. This
file lists what it shows today and every idea for more, so the next pick is a choice from a list
rather than a fresh brainstorm. Ideas are laid out as a time frame × a stat, then six more
dimensions that widen it, then the plan to build all of it in steps. Collected 2026-11-08.

Code: `peloton/username_facts.py` picks the highlights, `display/ui/username.py` draws them, and
`peloton/activity.py` computes the log figures (fed through `WorkoutLog.derived`).

## How a page is built

Since step 6 (2026-11-08) a page is chosen by score, not by turns:

1. `TOTAL WORKOUTS`: every page.
2. **Headline 1** and 3. **Headline 2**: the two best-scoring facts, of different groups (`KINDS` in
   `peloton/username_facts.py`). On the day of the account's anniversary, the anniversary is headline 1.
4. to 6. **An instructor top three**: the first chosen discipline headline's own, else the general ones
   (all time, 30 days, year, 90 days, last year, last week) take turns.

`THIS WEEK` is gone (the Goals screen covers it; Joel, 2026-11-08). A fact has a base score for its
kind, a bonus (first place, a big change, a best set in the last 14 days), and loses 100 for 20 name
pages after it shows (its kind loses 40), counted by the dashboard's own saved counter (`name_facts_passes`
and `name_facts_shown` in the cache), so a restart doesn't repeat it. A fact with too little data
isn't a candidate. A board with few facts (a log still downloading) shows a shorter page. Facts
from the workout log appear only once the log holds the whole history.
`python scripts/list_facts.py --demo` prints every candidate with its score and the first passes.

## Fitting rules

- A highlight is a label (tom-thumb, `stats` font) and two lines (4x6, `info` font), or one big number.
- Labels and lines hold **15 characters** (60 px) on both 64x64 and 64x32. `LEAST THIS MONTH`
  (16) doesn't fit; `MOST IN 30 DAYS` (15) fits exactly.
- A too-long label can carry a `short_label` that the screen uses instead (`3RD TREAD BOOTCAMP` →
  `3RD BOOTCAMP`).
- Name the period in the label (`IN 2026`, `IN NOV`) so a fact never needs a third line.
- A value line that is still too wide (a long instructor name) scrolls on the board (`UsernameScreen`: hold, glide, hold; back again from 8 s), so the fit test doesn't need to shorten names; labels still can't scroll and need a `short_label`.
- Test each fact at both heights with the longest likely values (see
  `test_every_label_and_line_fits_or_has_a_short_label_that_does`).

## Data on hand

No idea below needs a new API call.

| Source | What it holds |
|---|---|
| Workout log (`<cache>.workouts.json`, `peloton/workout_log.py`) | Per workout: start time (date, weekday, hour), discipline, class ID (`ride_id`), title, class length, output (kJ), distance, calories, instructor (or group), output and splits PR flags, Strive score (`effort_points`), seconds in each heart-rate zone, streak eligibility |
| Dashboard cache | Discipline totals, streaks (`best_weekly`, `current_weekly`, `current_daily`), personal records by discipline and length (`cycling\|30 min: 289.9 kJ`), weekly progress |
| Profile (fetched daily) | Only `id`, `username`, `timezone`, `height_unit`, `created_at` are kept (`PROFILE_KEYS` in `peloton/dashboard.py`; `created_at` since step 5). Adding a key costs nothing: `total_followers`, `cycling_workout_ftp`, `estimated_cycling_ftp`, `badge_level` |

## Built

Every fact below is a candidate headline (step 6 scores them; see "How a page is built"); the frame
only says what window it measures.

| Every page | Label | Lines | Shown when |
|---|---|---|---|
| Highlight 1 | `TOTAL WORKOUTS` | `2,123` (big, gold) | the overview has a total |

**Frames** (`FRAME_ORDER` in `peloton/username_facts.py`): all time, last 30 days, this year, last 90
days, last year, last week, then `events` (below), which has no top three of its own.

| Headline (highlight 3) | Label | Lines | Shown when |
|---|---|---|---|
| All time | `TOP DISCIPLINE` | `CYCLING` / `641 WORKOUTS` | any discipline totals |
| Workouts and time | `LAST 30 DAYS`, `LAST 90 DAYS`, `IN 2026`, `IN 2025`, `LAST WEEK` | `12 WORKOUTS` / `340 MINUTES` (`164 HOURS` from 600 minutes) | 1+ workout in the frame |
| Most-done discipline | `MOST IN 30 DAYS` (`MOST IN 2026`, ...) | `STRENGTH` / `6 WORKOUTS` | 2+ workouts, and not the all-time top discipline |
| Active days | the frame's title | `ACTIVE DAYS` / `10 OF 30` | 2+ active days |
| Unique instructors | the frame's title | `31 UNIQUE` / `INSTRUCTORS` | 2+ |

("Different classes" was a fact until 2026-11-08 and was dropped: a given. `period_stats` still counts them.)
| Averages (5+ workouts) | the frame's title | `AVERAGE CLASS` / `28 MINUTES`; `AVERAGE WEEK` / `2.8 WORKOUTS` (28+ days) | |
| Share (10+ workouts) | the frame's title | `50% STRENGTH` / `OF WORKOUTS` | top discipline has 2+ |
| Rank (30 and 90 days) | the frame's title | `3RD BEST EVER` / `21 WORKOUTS` | top five of 6+ blocks |
| Busiest day / week / month | `BUSIEST DAY` etc. | `6 WORKOUTS` / `MAR 3 2025` | 2+ (day), 3+ (week, month; month for year and all time) |
| Longest, output, Strive | `LONGEST WORKOUT`, `HIGHEST OUTPUT`, `BEST STRIVE` | `45 MINUTES` / `CYCLING`; `290 KJ` / `30 MIN CYCLING`; `212 POINTS` / `STRENGTH` | the stat exists (output: bike) |
| Best weekly streak (all time) | `LIFETIME` | `74 WEEK STREAK` / `YOUR BEST` | 4+ weeks |
| One instructor (the frame's 3 most-seen) | the frame's title | `JESS SIMS` / `340 MINUTES` | 2+ workouts with them, name known |

| Top three (highlights 4-6) | Labels | Lines | Shown when |
|---|---|---|---|
| All time, every class | `TOP` / `2ND` / `3RD INSTRUCTOR` | `JESS SIMS` / `300 CLASSES` | any named instructor |
| One discipline in any frame (most-done first; headline `STRENGTH` / `12 WORKOUTS` / `IN 30 DAYS` or `LIFETIME`) | `TOP` / `2ND` / `3RD STRENGTH` | `JESS SIMS` / `150 CLASSES` | 2+ workouts and 3 instructors with 2+ classes each in it, in that frame |
| A frame's own classes | `TOP` / `2ND` / `3RD IN 30 DAYS` (`IN 90 DAYS`, `IN 2026`, ...) | `JESS SIMS` / `4 CLASSES` | 3 instructors with 2+ classes each in the frame |

**Events** (step 5) are a last pseudo-frame, `events`: it takes a turn only while there is an event to
say, its headline is the event and its top three the all-time one again (`frame_rankings('events')`),
and each visit shows the next event. They come from `activity.event_stats` (dates in the display
timezone; the thresholds are named constants in `username_facts.py`):

| Event | Label | Lines | Shown when |
|---|---|---|---|
| Anniversary (pinned) | `ANNIVERSARY` | `6 YEARS` / `ON PELOTON` | today is the day of the profile's `created_at` (a partial log too), 1+ years. It replaces the headline of **every pass all day** (the frame's top three stays), so it's never missed; it isn't in the `events` turn |
| On this day | `ON THIS DAY` | `2 YEARS AGO` / `45 MIN CYCLING` | a workout on today's date in an earlier year (the nearest year, its longest workout) |
| Comeback | `COMEBACK` | `YOGA` / `AFTER 185 DAYS` | a discipline with 5+ workouts done in the last 14 days after 60+ days without (years past 999 days) |
| New discipline | `NEW DISCIPLINE` | `WALKING` / `FIRST TIME` | first workout in the last 14 days, by a rider with 30+ days of earlier history |
| Since | `SINCE` | `49 DAYS SINCE` / `LAST STRETCHING` | 5+ workouts, last one 14 to 999 days ago (two at most, most-done first) |
| Last class with | `LAST CLASS WITH` | `ADRIAN WILLIAMS` / `MAR 3 2026` | one of the 5 most-seen instructors, 5+ classes, 30+ days ago, named (two at most) |

Long discipline names use their last word (`LAST BOOTCAMP`). Except the anniversary, which is pinned all day (Joel, 2026-11-08: too rare to leave to a turn), an event
shows once every few passes in the `events` turn, even on the day it's about; step 6's "today is the
day" score should pull "on this day" forward. Pass 0 differs from the old page only on the anniversary.

Pass 0 is all time: `TOP DISCIPLINE` and the all-time top three, byte for byte what the board showed
before any of this.

Check any log against these with `python scripts/list_facts.py --log <log> --cache <cache> --tz <zone>`
(or `--demo`): it prints each frame's figures, every fact above, and the first passes.

Tried and dropped (Joel, 2026-11-08): **least-done discipline** (not interesting), and **calendar months** (`IN NOV` is nearly empty on the 1st or the 3rd; use a rolling 30 days).

## Ideas: a time frame × a stat

Almost every idea is one **time frame** with one **stat**: "hours" works for this week, the last 30 days,
this year or all time, and so does "different instructors". So both are listed once below, then a
grid says which pairs are worth showing. The built facts are pairs too: `LAST 30 DAYS` is
workouts + minutes for the last 30 days, and `TOP` / `2ND` / `3RD INSTRUCTOR` is the instructor top
three for all time.

### Time frames

| Frame | In a label | Covers | Notes |
|---|---|---|---|
| This week | `THIS WEEK` | Monday 00:00 to now | Complete even while the log is still filling |
| Last week | `LAST WEEK` | the Monday-to-Sunday before | |
| Last 30 days | `30 DAYS` | today and the 29 days before | Built. Used instead of the calendar month, which is nearly empty on the 1st |
| Last 90 days | `90 DAYS` | rolling, like 30 days | A season without a calendar edge |
| This year | `IN 2026` | 1 January to now | Thin in early January |
| Last year | `IN 2025` | the whole previous year | |
| All time | `LIFETIME` / `ALL TIME` | everything | Workout count and discipline totals come from Peloton's overview, the rest from the log |

All are in the display timezone, like `THIS WEEK`. Every frame except this week needs the complete
log, as the 30-day facts do now. Calendar months are out (Joel, 2026-11-08): this week and this year
have the same thin start, but a week is short and the year label says which year it is.

### Stats, by kind

The kind decides what the highlight looks like.

**Totals**: a number for the frame. Lines: `412 WORKOUTS` / `164 HOURS`.

| Stat | From | Notes |
|---|---|---|
| Workouts | log (overview for all time) | |
| Minutes / hours | `class_length_s` | Hours past ~600 minutes |
| Output (kJ) | `total_work_j` | Bike and rower only |
| Calories | `calories` | |
| Miles (or km) | `distance` | Same groups as the journey |
| Strive points | `effort_points` | Heart-rate monitor only |
| Hard minutes | `hr_zone_s` zones 4–5 | Heart-rate monitor only |
| PRs | `pr_output`, `pr_splits` | |
| Active days | `start` | Optionally as a share: `248` / `79% OF DAYS` |

**Distinct counts**: how many different things. Lines: `318 DIFFERENT` / `CLASSES`.

| Stat | From | Notes |
|---|---|---|
| Different classes | `ride_id` | Just Ride / Just Walk have no class |
| Different instructors | `instructor_id`, `group_ids` | Group classes count each member, like the tally |
| Disciplines | `discipline` | |
| New classes | `ride_id`, earlier rows | First time ever in that class; also as a share (`82% NEW`) |
| New instructors | `instructor_id`, earlier rows | First-ever class with them |

**Tops**: who or what came first. Lines: name / count. One highlight, or three for a top three.

| Stat | From | Notes |
|---|---|---|
| Top discipline | `discipline` | Skip when it's the all-time top (see `MOST IN 30 DAYS`) |
| Instructor top three | instructor tally | Built for all time and the last 30 days |
| Instructor top three in one discipline | instructor tally per discipline | Built for all time |
| Most repeated class | `ride_id`, `title` | Titles trimmed to 15 characters |
| Favourite weekday | `start` | `MONDAY` / `22% OF WORKOUTS` |
| Time of day | `start` hour | `MORNINGS` / `6-9 AM`, or `41% BEFORE 9` |
| Go-to class length | `class_length_s` | `20 MIN` |

**Bests**: the biggest smaller piece inside the frame. Lines: value / when.

| Stat | From | Notes |
|---|---|---|
| Biggest week | weeks in the frame | `14 WORKOUTS` / `OCT 2024` |
| Biggest month | months in the frame | Year and all time only (a finished month is fine as a best) |
| Busiest day | days in the frame | `6 WORKOUTS` / `MAR 3 2025` |
| Longest workout | `class_length_s` | `90 MIN RIDE` |
| Highest output | `total_work_j`, or the cache's personal records | All time real: 289.9 kJ, 30 min ride |
| Best Strive class | `effort_points` | Heart-rate monitor only |
| Best weekly streak | cache `streaks.best_weekly` | All time only (real: 74 weeks) |

**Comparisons**: any total against the frame before, up to the same point so it's fair
(the last 30 days against the 30 before). Lines: `412 VS 380` or `+3 WORKOUTS`.

### Which pairs are worth showing

★ built · ✓ worth showing · ◇ already on another page · – adds nothing

| Stat | Week | Last week | 30 days | Year | Last year | All time |
|---|---|---|---|---|---|---|
| Workouts | ★ `THIS WEEK` | ✓ | ★ `LAST 30 DAYS` | ✓ | ✓ | ★ `TOTAL WORKOUTS` |
| Minutes / hours | ★ | ✓ | ★ | ✓ | ✓ | ✓ |
| Output | ◇ Head to head | ✓ | ✓ | ✓ | ✓ | ✓ |
| Calories | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Miles | ✓ | ✓ | ✓ | ✓ | ✓ | ◇ Journey |
| Strive points | ✓ | ✓ | ✓ | ✓ | ✓ | – |
| Hard minutes | ✓ | ✓ | ✓ | ✓ | ✓ | – |
| PRs | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Active days | ◇ Heatmap | ✓ | ✓ | ✓ | ✓ | ✓ |
| Different classes | – | – | ✓ | ✓ | ✓ | ✓ |
| Different instructors | – | – | ✓ | ✓ | ✓ | ✓ |
| Disciplines | – | – | ✓ | ✓ | ✓ | ◇ Lifetime |
| New classes | ✓ | – | ✓ | ✓ | ✓ | – |
| New instructors | ✓ | – | ✓ | ✓ | ✓ | – |
| Top discipline | ✓ | – | ★ `MOST IN 30 DAYS` | ✓ | ✓ | ★ `TOP DISCIPLINE` |
| Instructor top three | – | – | ★ | ✓ | ✓ | ★ |
| Instructor top three, one discipline | – | – | – | ✓ | ✓ | ★ |
| Most repeated class | – | – | ✓ | ✓ | ✓ | ✓ |
| Favourite weekday | – | – | – | ✓ | ✓ | ✓ |
| Time of day | – | – | ✓ | ✓ | ✓ | ✓ |
| Go-to class length | – | – | – | ✓ | ✓ | ✓ |
| Biggest week | – | – | – | ✓ | ✓ | ✓ |
| Biggest month | – | – | – | ✓ | ✓ | ✓ |
| Busiest day | – | – | ✓ | ✓ | ✓ | ✓ |
| Longest workout | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Highest output | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Best Strive class | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Best weekly streak | – | – | – | – | – | ✓ |
| Comparison with the frame before | ✓ | – | ✓ | ✓ | – | – |

That's well over a hundred ✓ pairs, far more than a rotation can show. Something has to choose.

### Choosing pairs

1. **One frame per pass (recommended).** Each pass picks the next frame, and every slot fills from
   it. Pass 1 is all time, pass 2 the last 30 days, pass 3 this year, pass 4 last year, and so on; slot A
   takes the frame's next total, distinct count or best, and slot B its instructor top three. The
   page reads as one story ("2026: 412 workouts, 318 different classes, top instructor Jess Sims"),
   and the label only needs to name the frame. Today's page is already close: its pass 2 is all
   the last 30 days.
2. **A fixed list.** Pick about a dozen pairs by hand and rotate through them. Simple, but every
   new pair is a code change.
3. **Settings page.** A grid of frame and stat switches on the name page's Rotation row. Most
   flexible, and the most to build and test.

### Labels

Put the frame in the label and the stat in the lines, so a label never has to say both:

| Kind | Label | Lines |
|---|---|---|
| Totals | `IN 2026` | `412 WORKOUTS` / `164 HOURS` (two totals in one highlight) |
| Distinct count | `IN 2026` | `318 DIFFERENT` / `CLASSES` |
| Top | `TOP OF 2026` | `JESS SIMS` / `61 CLASSES` |
| Top three | `TOP` / `2ND` / `3RD IN 2026` | `JESS SIMS` / `61 CLASSES` |
| Best | `BEST WEEK 2026` | `14 WORKOUTS` / `OCT 2024` |
| Comparison | `VS 30 BEFORE` | `+3 WORKOUTS` |

Check each label against the 15-character limit: `TOP OF LIFETIME` is exactly 15, and
`TOP OF LAST WEEK` (16) is too long, though that pair is – in the grid anyway.

### Code shape

One helper in `peloton/activity.py`, `period_stats(workouts, start, end)`, makes one pass over the
log for a frame and returns every stat above. Frames are a list of (key, label word, start, end),
and `recent_activity` became `period_stats` for the last 30 days (step 1). The facts module then picks the
pass's frame and builds highlights from its stats.

Head to head (ROADMAP item 6) wants the same thing, "the last 30 days instead of this week" for a set of
stats, so it should use the same helper.

## Beyond frame × stat: six more dimensions

Time frame × stat is the core, but on its own it makes a page that is varied rather than
interesting. These six widen it. A fact in full is:

**who** × **which workouts** × **time frame or event** × **stat** × **how it's worked out** ×
**compared with what**, and then a step that picks the interesting ones.

### 1. Which workouts count (filters)

A third axis that narrows the workouts before the stat is worked out.

| Filter | Example | From |
|---|---|---|
| Discipline | `STRENGTH 2026` / `140 WORKOUTS` / `61 HOURS` | `discipline` |
| Instructor | `WITH JESS SIMS` / `61 CLASSES` / `1,830 MIN` | `instructor_id`, `group_ids` |
| Class length | `20 MIN RIDES` / `212 IN 2026` | `class_length_s` |
| With a heart-rate monitor | Strive and zone stats only count these | `hr_zone_s` present |

Today's "instructor top three in one discipline" is already a filter (discipline) on a top.

### 2. How it's worked out

The same stat can be a total, an average, a maximum, a share or a rank.

| Measure | Example |
|---|---|
| Total | `164 HOURS` in 2026 |
| Average | `AVERAGE CLASS` / `24 MIN` in 30 days; `AVERAGE WEEK` / `7.9 WORKOUTS` |
| Maximum | `LONGEST` / `90 MIN RIDE` |
| Share | `38% STRENGTH` in 30 days; `79% OF DAYS` active in 2026 |
| Rank | `3RD BEST 30 DAYS` (this window among every 30-day window you've had) |

"Bests" in the stats list are the maximum applied to a smaller unit inside the frame (the biggest
week in 2026).

### 3. Compared with what

A modifier that can go on any total.

| Reference | Example | Notes |
|---|---|---|
| The window before | `VS 30 BEFORE` / `+3 WORKOUTS` | Same length, so it's fair |
| Same point last year | `2026 VS 2025` / `412 VS 380` | Up to today's date |
| Your own average | `THIS WEEK` / `ABOVE AVERAGE` / `+2` | 12-week average, like the heatmap |
| Your record | `BEST 30 DAYS` / `EVER` / `52 WORKOUTS` | This window is your best of its kind |
| A goal | | Already the goals page; leave it there |
| The other rider | | Already Head to head; leave it there |

### 4. Time measured from an event

Not a calendar window but a distance from something that happened.

| Kind | Example | From |
|---|---|---|
| Since | `12 DAYS SINCE` / `YOUR LAST ROW`; `41 CLASSES` / `SINCE YOUR LAST PR` | `start`, `discipline`, PR flags |
| Last time | `LAST RIDE WITH` / `CODY RIGSBY` / `MAR 3` | `instructor_id`, `start` |
| On this day | `A YEAR AGO TODAY` / `45 MIN RIDE` / `JESS SIMS` | `start`, `title` |
| Anniversary | `6 YEARS` / `ON PELOTON` (on the day) | profile `created_at` (add to `PROFILE_KEYS`) |
| First | `FIRST YOGA` / `IN 3 MONTHS` | `discipline`, `start` |

### 5. Choosing what's interesting

The step that makes the page feel fresh. With hundreds of possible facts, most are dull most of the
time; a few are notable at any moment. Score each candidate and show the best ones:

| Signal | Example | Weight |
|---|---|---|
| A record being set | `BEST 30 DAYS EVER` | highest |
| Today is the day | anniversary, `A YEAR AGO TODAY` | high, only that day |
| A first or a comeback | `FIRST YOGA IN 3 MONTHS`, a new instructor | high |
| A run of something | `5 STRENGTH IN A ROW`, `LAST 4 WITH JESS SIMS` | medium, grows with the run |
| A big change | `+40% VS 30 BEFORE` | medium, grows with the change |
| Nothing special | `IN 2026` / `412 WORKOUTS` | low baseline, so there's always something |

Two rules keep it from getting stuck: a fact shown recently scores lower (a cool-down, remembered
across restarts), and one page doesn't show two facts of the same kind.

### 6. Who it covers

On a board with two riders: facts about both together.

| Example | Notes |
|---|---|
| `TOGETHER` / `31 WORKOUTS` / `IN 30 DAYS` | Sums both riders' figures |
| `BOTH TOOK` / `JESS SIMS` / `40 CLASSES` | An instructor in both top threes |
| `SAME CLASS` / `4 TIMES IN 2026` | Same `ride_id` on the same day |

Shown once per cycle, like Head to head (the rider whose rotation gets `rivals`).

### What the log can't tell us yet

Some filters people would want aren't in the log: live vs on-demand, class type (HIIT, power zone,
low impact), music genre, cadence and resistance. Each would mean extending `trim()` in
`peloton/workout_log.py` and bumping `LOG_VERSION` (one re-download per board), so they're at the
end of the plan, if ever.

## Plan

Each step is one branch and one PR into `develop-beta`. Every step keeps the page at six highlights
(24 s, so `peloton/screen_times.py` doesn't change), keeps the 64x64 pass-0 page byte-identical
until a step says otherwise, needs no new API calls, and shows a fact only once the workout log is
complete (except this week).

### The page's shape, from step 1 on

| Highlight | What | Changes |
|---|---|---|
| 1 | `TOTAL WORKOUTS` | never |
| 2, 3 | **Headlines**: the two best-scoring facts, of different groups (step 6; `THIS WEEK` is dropped) | every page |
| 4–6 | **An instructor top three**: a chosen discipline's own, else the general ones in turn | every page |

### Step 0: ship what's built: done (PR #65, `varied-username-facts`)

Slot A (top discipline, last 30 days, most in 30 days) and slot B (instructor top threes for all
time, 30 days and each discipline). Step 1 reshaped these into frames.

### Step 1: time frames and `period_stats`: done (branch `facts-step-1-frames`)

- `peloton/activity.py`: `frame_bounds` (week, last week, 30 days, 90 days, year, last year, all
  time: start inclusive, end exclusive, local midnight), `period_stats(workouts, start, end,
  timezone_name, now)` for one window, and `frame_stats` for every frame with the timestamps parsed
  once. A window's stats: workouts, minutes, per-discipline counts, per-instructor counts, how many
  different instructors and classes (by `ride_id`), active days; `frame_stats` adds `days` and, for
  the two year frames, `year`. `recent_activity` is gone.
- `WorkoutLog.derived` returns `time_frames` (`{frame key: stats}`, empty until the backfill is
  complete). `as_workout` now carries `ride_id` so classes can be counted.
- `peloton/username_facts.py`: one frame per pass, as under "Built".
- `scripts/list_facts.py`, with `--demo`.
- Deliberately not done here: filters (step 2), so the all-time top three still takes turns through
  each discipline, and last week's and the other frames' top threes have no per-discipline form.

### Step 2: filters: done (branch `facts-step-2-filters`)

Built: `period_stats(..., discipline=, instructor=)`; `frame_stats` splits each frame once into `by_discipline` (5 most-done) and `by_instructor` (3 most-seen), so a filter never picks a one-off and the log isn't looped per subject. `frame_subjects` makes a discipline page: headline `STRENGTH` / `12 WORKOUTS` / `IN 30 DAYS` (`LIFETIME` for all time) then `TOP` / `2ND` / `3RD STRENGTH` from that discipline in that frame; the discipline needs 2+ workouts and three instructors with 2+ classes. The headline names the frame so the top three's label needn't (`3RD STRENGTH 2026` is 17 characters). `frame_facts` adds one fact per most-seen instructor: `LAST 30 DAYS` / `JESS SIMS` / `340 MINUTES` (2+ workouts, named; the minutes add to the top three's class counts, so it overlaps the top three's names). Stories alternate general, subject, general, subject, so a discipline page comes round soon. The all-time per-discipline top threes now come from the log's `by_discipline`, so their discipline counts are the log's, not the overview's. The old `discipline_instructor_counts` (all-time per discipline) is removed: `by_discipline` replaces it.

Planned:

- `period_stats` takes a filter (discipline or instructor) and returns the same stats for it.
- New facts: one discipline in a frame (`STRENGTH 2026`), one instructor in a frame
  (`WITH JESS SIMS`), and the per-discipline top three moved onto the frame (`TOP STRENGTH 2026`).
- Which discipline or instructor: the pass's turn through the rider's top ones in that frame, so
  a filter never picks something done once.

### Step 3: measures and bests: done (branch `facts-step-3-bests`)

Built: `frame_stats` adds, per frame, `busiest_day` / `busiest_week` / `busiest_month` (`{count, date}`; weeks and months only if they start inside the frame, months only for year, last year and all time), `longest`, `best_output` (bike only, kJ) and `best_strive` (these three only from real classes, never a no-class workout like Just Ride), all from the one pass over a frame's rows (`_bests`); the 30- and 90-day frames also get `rank` (`block_rank`). `as_workout` now carries `effort_points` (already in the log, so no `LOG_VERSION` bump). Facts (`_measure_facts`, after a frame's distinct counts and before its instructors): `AVERAGE CLASS`, `AVERAGE WEEK` (frame of 28+ days), the top discipline's share (`38% CYCLING` / `OF WORKOUTS`, 10+ workouts), rank (`LAST 30 DAYS` / `3RD BEST EVER` / `21 WORKOUTS`, top five only), `BUSIEST DAY` (2+), `BUSIEST WEEK` (3+, `OF OCT 12 2026`), `BUSIEST MONTH` (3+, `OCT 2025`), `LONGEST WORKOUT`, `HIGHEST OUTPUT`, `BEST STRIVE`, and for all time `74 WEEK STREAK` / `YOUR BEST` (cache `streaks.best_weekly`, 4+). A frame with under 5 workouts has no measures or bests. Two departures from the plan: rank compares non-overlapping blocks counted back from today (6+ blocks), not every sliding window, because the 2nd-best sliding window is just a day off the best, so the plan's per-day totals aren't needed; and the rank's words sit in the lines (`3RD BEST` + `EVER`) since `3RD BEST 30 DAYS` is 16 characters. `list_facts.py --cache` now carries the cache's streaks; the demo log has output and Strive.

Planned (as written):

- Average, maximum, share and rank beside the totals; bests (biggest week, month and day, longest
  workout, highest output, best Strive class) inside a frame.
- "Rank" needs every window of the same length: compute 30-day totals for each day once per
  refresh, not per fact.
- Best weekly streak from the cache.

### Step 4: comparisons: done (branch `facts-step-4-comparisons`)

Built: `frame_stats` adds `before` (`{workouts, minutes}`) to the 30-day, 90-day and year frames (`comparison_window`): the same number of days just before for 30 and 90 days, and last year from 1 January up to today's date and time for the year (29 February compares with the 28th), so a part-year is never set against a whole one. One fact, `_comparison_fact`, after a frame's measures: `VS 30 BEFORE` / `1,234 VS 999` / `+235 WORKOUTS` (`VS 90 BEFORE`, `2026 VS 2025`). Shown only when both sides have `MIN_COMPARE_WORKOUTS` (5) and the change is at least `MIN_COMPARE_CHANGE` (20%) and `MIN_COMPARE_DIFF` (3 workouts). Departures from the plan, which listed more: "best ever" is already step 3's rank; the 12-week average is for this week, which isn't a frame that takes turns (THIS WEEK is on every page), so it's left out; last week, last year and all time have no fair comparison. A comparison of minutes wasn't added (workouts say it, and the headline already shows minutes). The demo log is steady, so it rarely clears the 20% threshold.

### Step 5: events: done (branch `facts-step-5-events`)

Built: as under "Built" > Events. `activity.event_stats` (one pass over the log, plus `anniversary`) goes into `WorkoutLog.derived` as `events` (a partial log has just the anniversary); `PROFILE_KEYS` keeps `created_at` and `Dashboard._derive` passes it as `member_since`. The log already had `title`, but nothing uses it: the lines show the discipline, since a class title doesn't fit 15 characters. Departures from the list below: "last time with an instructor" is the instructor's last class date (`LAST CLASS WITH`), shown only after 30 days, since a recent one is dull; there's no "since your last PR" (the PR flags are per workout, not per discipline, and it needs a count of classes since, so it's left for a later step if wanted); anniversaries on 29 February only show in leap years.

Planned:


- Since, last time, on this day, firsts and comebacks, all from the log.
- Anniversary: keep `created_at` in `PROFILE_KEYS` (`peloton/dashboard.py`); a test checks the
  slimmed profile still holds no personal fields beyond it.

### Step 6: choosing what's interesting: done (branch `facts-step-6-scoring`)

Built: every fact carries a `kind` and (in `scored_facts`) a `key`; `KINDS` maps a kind to its group and base
score; `fact_score` adds the bonuses (`RANK_FIRST_BONUS`, `MAX_COMPARE_BONUS` scaled by the change,
`RECENT_RECORD_BONUS` for a best dated within `RECENT_RECORD_DAYS`) and subtracts the cool-down.
`username_details` is the total, the best two headlines of different groups, and a top three
(a discipline headline's own, else `_general_ranking`). `frame_stories` and `username_frames` are gone
(pass-per-frame turns no longer exist), so are THIS WEEK and pass 0's old page. The cool-down counts name
pages in the dashboard's own saved counter (`Dashboard.acknowledge_name_facts` after the page is shown,
`name_facts_passes` / `name_facts_shown` in the cache), not `pass_index`, which restarts at 0 and
counts cycles; the pass index is only the preview's fallback. Departure from the plan: the kind itself also
cools down (`KIND_COOLDOWN_PENALTY`), since otherwise HIGHEST OUTPUT from five frames took every page in
turn. In the demo log, 24 pages show 20+ different headlines and no fact twice within 5 pages.
Weights are a first guess; tune them with `list_facts.py` on real logs.
Also dropped at Joel's request (2026-11-08): the lifetime discipline headline (`STRETCHING` / `219 WORKOUTS` / `LIFETIME`), because the Lifetime pages show the count; each discipline's all-time top three stays and takes its turn after the overall one (`_general_ranking`). `DIFFERENT INSTRUCTORS` is `UNIQUE INSTRUCTORS`.
First tuning (Joel's 2,137-workout log on PelotonPi, 2026-11-08): the recent-record bonus applies only to
the all-time and year frames (`RECORD_FRAMES`), since the busiest day of the last 30 or 90 days is nearly
always recent; and facts that read the same in several frames (`BUSIEST DAY 3 WORKOUTS NOV 8 2026` in
30 days, 90 days and the year) are one candidate. Still open: a best's label doesn't name its window
(`LONGEST WORKOUT` 163 MIN for 30 days and 299 for lifetime read alike); a fix needs the 15-character fit test.

Planned:

- Every fact from steps 1–5 becomes a candidate with a kind, a key (e.g. `best:30d:workouts`) and a
  score from the signals in dimension 5.
- Highlights 2 and 3 show the two top-scoring candidates, of different kinds (THIS WEEK is dropped: see "Decisions for step 6").
- Cool-down: `name_facts_shown` in the dashboard cache (`{key: last shown}`, per rider, like
  `milestone_shown_at`) lowers a fact's score for a day after it shows, so a restart doesn't repeat
  it.
- `scripts/list_facts.py` prints the scores, which is how the weights get tuned on real logs.
- This is the step that changes pass 0, so the byte-identical check stops applying to the name
  page here; the other pages must stay identical.

### Step 7: together (now a ROADMAP item)

- Only on boards with two or more riders, from each rider's `period_stats`.
- Candidates for the headline of the rider whose rotation gets `rivals`, so they show once a cycle.
- Shares figures with Head to head (ROADMAP item 6), which should be built on `period_stats` too.

### Step 8 (optional): settings and new log fields (now a ROADMAP item)

- Settings page: switches for the dimensions (e.g. no comparisons, no together facts) on the name
  page's Rotation row. Not a switch per fact.
- New log fields (live vs on-demand, class type) only if a fact needs them; one `LOG_VERSION` bump
  for all of them at once.

### Decisions for step 6 (Joel, 2026-11-08)

- **THIS WEEK goes, always.** The Goals screen covers the week. Highlight 2 becomes a second
  headline, so the page is `TOTAL WORKOUTS`, two scored headlines of different kinds, then the
  instructor top three: still six highlights, 24 s, `screen_times.py` untouched. (A board with no
  weekly goals loses the weekly count on the name page; accepted.) The anniversary pin stays: it
  takes the first headline.
- **Cool-down is a number of passes**, not a day: `name_facts_shown` holds the pass counter at the
  last showing, per rider, in the dashboard cache (a named constant for the length, about 20).
  A restart must not reset it, so the counter is saved too. Check how the pass counter behaves
  across restarts and multi-rider cycles before relying on it.
- **Same frames on 32 rows** as on 64.
- The top three keeps three names.
