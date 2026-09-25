# Board features notes

Running log for the `board-features` branch (based on `fit-64x32`). Every
feature works on both 64x64 and 64x32 panels.

## Queue

| # | Feature | Status |
|---|---|---|
| — | Trophy instead of "PR" letters; red Peloton P | **done** (committed on `fit-64x32`) |
| 4 | Output graph for the last workout | **done** |
| 6 | Heart-rate zone bar | **done** |
| 1 | Streak screen | **done** |
| 3 | Joel vs. Jen this week | **done** |
| 5 | Next-milestone countdown | **done** |
| 9 | Distance journey (Columbus → Disney World by default) | **done** |

**Status (2026-09-25):** every item is done, tested (378 tests pass) and
pushed to `board-features`. The full demo rotation also ran in the
emulator at both 64x64 and 64x32 with no errors. No PR yet; this branch
sits on `fit-64x32`, which sits on `last-workout-stat-rotation` (PR #2).

**Previews:** `docs/screenshots/features/`: one sheet per feature plus the
whole demo rotation at each size. They're local only (not committed) because
some use your real data.

Preview any of it without the API:

```bash
python scripts/render_rotation.py --height 64 --demo --out /tmp/demo-64.png
python scripts/render_rotation.py --height 32 --demo --out /tmp/demo-32.png
```

## #4 Output graph and #6 heart-rate zone bar

Both are extra slides at the **end of each workout's stat rotation**, so
they show on every workout that recorded the data. The page gets longer by
one stat interval per slide. **No extra API calls:** the app already
downloads each workout's performance graph, and these read the output,
heart-rate and zone data from it.

- **Graph:** the label (`OUTPUT`, or `HEART RATE` when the workout has no
  output, e.g. strength) with the peak on the right (`278W`), then 60 columns
  across the panel. Each column is colored by the heart-rate zone you were in
  at that moment (blue, green, yellow, orange, red for zones 1-5), or by the
  discipline color when there's no heart-rate data. The highest column gets
  a gold cap. Output is drawn from zero. Heart rate is drawn from just below
  its lowest value, since it sits in a narrow band and would look flat
  otherwise.
- **Zone bar:** `HR ZONES`, a bar across the full width split by time in
  each zone, and the zone you spent the most time in underneath
  (`ZONE 3 47%`) in that zone's color.
- **64x32:** these two slides hide the HR/calories bar and use its rows for
  the chart and bar. The other slides still show it.
- **Data:** each workout summary now carries `graph` (60 averaged points plus
  zones and the peak) and `hr_zone_seconds`. Summaries cached before this
  change don't have them. They appear after the next data refresh, since
  summaries are rebuilt on every refresh.
- **Demo data:** the demo cycling ride now has a synthetic interval-workout
  series so demo mode and the tests show the graph.

Code: `performance_graph` / `heart_rate_zone_seconds` in `peloton/summaries.py`;
`_draw_graph` / `_draw_zones` / `rotating_details` in
`display/ui/last_workout_screen.py`; tests in `tests/test_workout_graph.py`.

## #1 Streak screen

A new rotation section, `streaks`, placed right after the username page in
the default rotation.

- **64x64:** a pixel flame (red, orange and yellow) on top, the current
  weekly streak in a big number (10x20 font), `WEEK STREAK` in orange,
  then `BEST 74 WEEKS` in grey.
- **64x32:** the flame and the number side by side on top, then the same
  two lines.
- When your current streak ties or beats your best, the footer becomes a
  gold `PERSONAL BEST`.
- The screen is skipped when the weekly streak is 0 or unknown (older
  caches, or Peloton not returning streaks).
- **No extra API calls:** the streaks come from the profile overview
  (`/api/user/{id}/overview`) that every refresh already downloads, and
  they're saved in the dashboard cache.
- Timing: `screen_durations.streaks`, falling back to `overview_duration`.
- Adds a `big` font key (10x20 on 64 rows, 7x13 bold on 32 rows) for large
  numbers. The next features use it too.

Code: `display/ui/streak_screen.py`, `parse_streaks` in `peloton/totals.py`;
tests in `tests/test_streaks.py`.

## #3 Joel vs. Jen this week

A new rotation section, `versus` (default position: after `streaks`).

- Shows only when 2+ riders are configured, and **once per household
  cycle** (in the first rider's rotation), not once per rider. With 3+
  riders it compares the first two in `users`.
- **Stats:** workouts, minutes and output (kJ) since Monday in the display
  timezone, the same week as the weekly goals. Output is new: weekly
  progress now also sums each workout's `total_work`. No extra API calls,
  since the workout history is already downloaded.
- **Leader:** most workouts, then minutes, then output as tie-breakers.
  The leader gets a gold trophy by their name. For each stat the higher
  value is gold. A full tie has no trophy.
- **64x64:** `THIS WEEK`, both names (Joel blue, Jen pink), and all three
  stats in rows.
- **64x32:** names on top, one stat per slide rotating every 4s. The page
  lasts at least 12s so each stat gets its turn. Big values drop to a smaller
  font when they'd run into each other.
- Caches written before this change have no weekly output, so output shows
  0 for both riders until the first refresh.
- Timing: `screen_durations.versus`, falling back to `overview_duration`.
- Preview with two caches:
  `python scripts/render_rotation.py --height 32 --cache cookies-joel-dashboard-cache.json --username Joel --rival cookies-jen-dashboard-cache.json --rival-name Jen --out /tmp/vs.png`

Code: `display/ui/versus_screen.py`, `weekly_rivals` in `peloton_led.py`;
tests in `tests/test_versus.py`.

## #5 Next-milestone countdown

A new rotation section, `next_milestone` (default: right after the Total
Workouts page).

- **Target:** the next milestone in your `milestones` list above your
  total. If you've passed them all (you have: your list is 100/250/500 and
  you're at 2,111), it's the next multiple of the new `milestone_step`
  setting, **default 100**. So Joel is at `89 TO GO` to 2,200 and Jen at
  69.
- **64x64:** `NEXT MILESTONE`, the target in gold, the remaining count big,
  `TO GO`, a progress bar for the current stretch (2,100 → 2,200), and
  `2,111 WORKOUTS`.
- **64x32:** `NEXT: 2,200`, then the big number with `TO GO` beside it, the
  bar, and the total.
- **Celebration:** reaching a step milestone (2,200, 2,300, …) now shows
  the existing gold `MILESTONE` screen once, like configured milestones.
  To avoid celebrating something old, a step milestone only celebrates if
  you crossed it within the last 10 workouts. So turning this on at 2,111
  doesn't celebrate 2,100.
- `milestone_step: 0` turns off both the step countdown and the step
  celebrations. Configured `milestones` work as before.
- Timing: `screen_durations.next_milestone`, falling back to
  `overview_duration`.

Code: `display/ui/countdown_screen.py`; `next_milestone` and
`reached_milestones` in `peloton/goals.py`; tests in
`tests/test_countdown.py`.

## #9 Distance journey

A new rotation section, `journey` (default: after the lifetime pages).
Your lifetime miles become a trip from one place to another.

- **Configure it** under `display.journey` (and per rider under
  `users[].journey`, like weekly goals):
  ```json
  "journey": {"from": "Columbus", "to": "Disney World", "miles": 880,
              "disciplines": ["Cycling", "Running", "Walking"]}
  ```
  That is the default. `disciplines` takes any Peloton discipline names
  ("Rowing", "Tread Bootcamp", "Outdoor Run", ...), one or several.
  880 is roughly the driving distance from Columbus to Walt Disney World;
  set `miles` to whatever you like.
- **64x64:** a vertical map on the left (Florida is south): a blue start
  dot, a dotted route, an orange trail for what you've covered, a white
  "you are here" dot, and a gold castle with pink towers at the bottom.
  On the right: the start name, the miles (big), `MILES`, `138 TO GO`, and
  the destination name at the bottom (wraps to 2 lines).
- **64x32:** `TO DISNEY WORLD` across the top, big miles with the percent,
  `138 TO GO`, and the route running left to right along the bottom to
  the castle.
- **Past the destination** the trip turns around: `TRIP 2`, `TO HOME` /
  `TO COLUMBUS`, and the trail runs back from the castle. Trip 3 heads out
  again, and so on.
- **Where the miles come from:** each workout row in your history has a
  `distance`. They're summed per discipline into a saved tally that's
  updated incrementally, the same way the top-instructor counts are.
  Rowing is reported in meters and converted. Other distances are taken
  as miles, or as km when the profile is metric.
- **API cost:** the first refresh after this update pages through each
  rider's full workout history once to build the tally (about 43 calls
  for 2,100 workouts; Jen's is similar). After that it reuses the page
  the instructor tally already fetches, so **no extra calls per refresh**.
  The journey page stays hidden until the tally has miles.
- Long start names are trimmed on 64x64 (`SAN FRANCISC`). Destination
  names wrap onto two lines.

Code: `peloton/journey.py`, `display/ui/journey_screen.py`, the tally in
`peloton/dashboard.py`; tests in `tests/test_journey.py`.

## Open questions for Joel

1. **Your `config.json` rotation is just `["latest_workouts"]`**, so the new
   screens (streaks, and the ones to come) won't appear on your panel until
   you add them, e.g.
   `"rotation": ["latest_workouts", "username", "streaks", "total_workouts", "lifetime", "milestones", "goals"]`.
   The workout graph and zone slides are part of `latest_workouts`, so those
   already show. I haven't edited your config. The full list now:
   `["latest_workouts", "username", "streaks", "versus", "total_workouts", "next_milestone", "lifetime", "journey", "milestones", "goals"]`.
2. Peloton also reports a **daily** streak (`current_daily`, 0 for you
   right now). It's parsed and saved but not shown. Say if you want it
   on the flame screen when it's 2 days or more.
