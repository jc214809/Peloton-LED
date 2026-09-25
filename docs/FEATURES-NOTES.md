# Board features notes

Running log for the `board-features` branch (based on `fit-64x32`). Every
feature works on both 64x64 and 64x32 panels.

## Queue

| # | Feature | Status |
|---|---|---|
| — | Trophy instead of "PR" letters; red Peloton P | **done** (committed on `fit-64x32`) |
| 4 | Output graph for the last workout | **done** |
| 6 | Heart-rate zone bar | **done** |
| 1 | Streak screen | next |
| 3 | Joel vs. Jen this week | queued |
| 5 | Next-milestone countdown | queued |
| 9 | Distance journey (Columbus → Walt Disney World by default) | queued |

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

## Open questions for Joel

(none yet)
