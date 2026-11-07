# Data points by workout type

Which workout stats Peloton sends, and which of them the board shows on its
workout pages. Checked on 2026-11-07.

## How to read the table

Each column is a kind of equipment. The board picks a workout page's layout by
equipment, so every discipline in a column gets the same stats:

| Column | Disciplines |
|---|---|
| **Bike** | Cycling, Bike Bootcamp |
| **Tread / Outdoor** | Running, Walking, Tread Bootcamp, Outdoor Run, Outdoor Walk, Hiking |
| **Row** | Rowing, Row Bootcamp |
| **No equipment** | Strength, Cardio, Yoga, Stretching, Meditation |

The marks:

- ✅ **shown**: Peloton sends it and the board shows it.
- ❌ **not shown**: Peloton sends it, but the board doesn't show it (a gap).
- —: Peloton doesn't send it for this kind of workout.

**The numbers** come from the 91 real workouts saved in `perf_graphs/` (the raw
data Peloton sent for each one). The heading says how many of those workouts
were of each kind, e.g. *Bike, 13 workouts*. A mark with no count means every
one of them had the stat. A count like *7 of 11* means only some did, and the note
says why when we know. So it is "how often Peloton actually sends this", not a
score or a measurement.

## The table

| Data point | Bike<br>13 workouts | Tread / Outdoor<br>11 workouts | Row<br>13 workouts | No equipment<br>54 workouts |
|---|---|---|---|---|
| Strive Score | ✅ shown (12 of 13) | ✅ shown | ✅ shown | ✅ shown (49 of 54) |
| Total output (kJ) | ✅ shown | ✅ shown (7 of 11: treadmill only) | ✅ shown | — |
| Avg output (watts) | ❌ not shown | ❌ not shown (7 of 11: treadmill only) | ❌ not shown | — |
| Distance | ✅ shown | ✅ shown | ✅ shown | — |
| Avg speed | ✅ shown | ❌ not shown | — | — |
| Avg pace | — | ✅ shown | — | — |
| Avg cadence | ✅ shown | — | — | — |
| Avg resistance | ✅ shown | — | — | — |
| Avg incline | — | ✅ shown (7 of 11: treadmill only) | — | — |
| Elevation gain | — | ✅ shown (10 of 11) | — | — |
| Split per 500 m | — | — | ✅ shown | — |
| Stroke rate | — | — | ✅ shown | — |
| Stroke count | — | — | ❌ not shown | — |
| Avg heart rate | ✅ shown (12 of 13) | ✅ shown | ✅ shown | ✅ shown (50 of 54) |
| Max heart rate | ❌ not shown (12 of 13) | ❌ not shown | ❌ not shown | ✅ shown (50 of 54) |
| Calories | ✅ shown | ✅ shown | ✅ shown | ✅ shown (50 of 54) |
| Heart-rate zones | ✅ shown (12 of 13) | ✅ shown | ✅ shown | ✅ shown (49 of 54) |
| Output / heart-rate graph | ✅ shown | ✅ shown | ✅ shown | ✅ shown |
| Muscle groups worked | ❌ not shown (11 of 13) | ❌ not shown (6 of 11) | ❌ not shown | ❌ not shown (47 of 54) |
| Per-mile splits | ❌ not shown (11 of 13) | ❌ not shown (10 of 11) | — | — |
| GPS route | — | ❌ not shown (3 of 11: outdoor only) | — | — |

Why some workouts lack a stat:

- **Heart rate, Strive Score, zones** need a heart-rate monitor; a workout done
  without one has none of them (Strive is worked out from heart-rate zones).
- **Output and incline** come from the Tread itself, so outdoor runs and walks
  don't have them.
- **Calories** are missing on 4 of the 54 no-equipment workouts; the saved
  data doesn't say why.

## The gaps

Stats Peloton sends that the board doesn't show, and why:

- **Avg output** (watts) anywhere: every page with output shows Total Output
  (kJ) instead, as rides always have. Rows showed average watts until
  2026-11-07, when Total Output and Strive Score replaced it.
- **Max heart rate** everywhere except no-equipment workouts: average heart rate
  is on every page's bottom row, and the zones page shows intensity better.
- **Stroke count** on rows: the board doesn't read it from the data; stroke rate
  and split already cover it.

Extras that could be new features rather than fixes: muscle groups, per-mile
splits, and the GPS route. Peloton also sends the **max** (peak) for every
equipment stat in the table (output, cadence, resistance, speed, incline,
stroke rate, split); the board shows only the averages, and of the maxes only
max heart rate, which is why that one has its own row.

## Stats and screens per workout

What one workout's page cycles through, for a workout with full data (heart-rate
monitor on; Tread for treadmill). Every page also keeps average heart rate and
calories on its bottom row.

| Workout type | Stats | Screens on 64x64 | Screens on 64x32 | Seconds on 64x64 |
|---|---|---|---|---|
| Bike | 6: total output, Strive, avg speed, avg cadence, avg resistance, distance | 9 | 10 | 38 |
| Treadmill | 6: distance, avg pace, Strive, total output, elevation gain, avg incline | 9 | 10 | 38 |
| Outdoor run or walk | 4: distance, avg pace, Strive, elevation gain | 7 | 8 | 30 |
| Row | 5: total output, Strive, distance, stroke rate, split per 500 m | 8 | 9 | 34 |
| No equipment | 2: Strive, max heart rate | 5 | 6 | 22 |

**Screens** = the intro (class length, title and, on 64x64, instructor) + one
per stat + the output or heart-rate graph + the heart-rate zones bar. 64x32 has
no room for the instructor in the intro, so it gets its own screen. A missing
stat, graph or zones bar drops its screen.

**Seconds** use the default 4 seconds a screen (`last_workout_detail_interval`);
the graph and zones screens hold 1 second longer. 64x32 adds 4 seconds for the
instructor screen.

## Number formats

The board writes each stat the way Peloton sends it:

| Stat | Example |
|---|---|
| Strive Score | one decimal, even when whole: `27.7`, `11.0` |
| Distance (mi, km) | two decimals: `6.33 mi` |
| Distance (rows) | whole metres: `1906m` |
| Incline | one decimal, even when flat: `2.5%`, `0.0%` |
| Speed | one decimal: `15.0 mph` |
| Pace, split | minutes and seconds: `10:20/mi`, `2:37/500` |
| Output, cadence, resistance, heart rate, calories, elevation | whole numbers, rounded half up |

## Limits

- The columns are equipment groups, not single disciplines: the saved workouts
  don't record which discipline each one was, and looking that up needs a
  working Peloton login.
- 91 workouts is a sample. A stat marked blank was in none of them; a rare
  workout type could still carry it.
- To refresh the "board shows" side, read `_stat_details` and the bottom row in
  `display/ui/last_workout_screen.py`.
