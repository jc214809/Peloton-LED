# Name page facts engine: build brief

For a Claude Sonnet 5.5 session building one step of the plan in `docs/NAME-PAGE-FACTS.md`
("Plan"). Read this file, that plan, and `CLAUDE.md` first. Do **one step per session and per
branch**, then stop.

Kick-off message for each session:

> Build step N of the name page facts engine: read docs/NAME-PAGE-FACTS-HANDOFF.md and follow it.

## Before you start

1. `git checkout develop-beta && git pull`. Confirm the previous step's PR has merged: its
   ROADMAP line is gone, or Joel says so. If it hasn't merged, stop and say so.
2. Branch: `facts-step-N-<short-name>` (e.g. `facts-step-1-frames`).
3. `config.json` is Joel's real, untracked config. Never `git add -A` or `git commit -a`; add files
   by name.
4. Read the files the step touches before changing them: `peloton/username_facts.py`,
   `peloton/activity.py`, `peloton/workout_log.py` (`derived`), `display/ui/username.py`,
   `tests/test_username_facts.py`, and `build_rotation_pages` in `peloton_led.py`.

## Rules for every step

- **Six highlights, 24 s.** `TOTAL WORKOUTS`, `THIS WEEK` (until step 6 replaces it with a second headline), a headline, then three highlights
  (an instructor top three). Don't change `peloton/screen_times.py`.
- **15 characters** for every label and line (60 px in the `stats` and `info` fonts, both heights).
  Long labels get a `short_label`. Add each new label to the fit test
  (`test_every_label_and_line_fits_or_has_a_short_label_that_does`) with its longest likely value.
- **No calendar months.** Use rolling windows (30 or 90 days). Joel's rule: `IN NOV` is empty on
  the 1st.
- **No new API calls.** Everything comes from the workout log, the dashboard cache or the profile.
  Log figures appear only once `WorkoutLog.complete` is true (this week excepted).
- **Skip thin facts.** Every fact has a threshold (see `MIN_RANKED_CLASSES` and
  `MIN_RECENT_WORKOUTS`), so a fact never shows a 1 or a 0 unless it's the point of the fact.
- **Business logic stays out of the screen.** Figures go in `peloton/activity.py`, the choice of
  facts in `peloton/username_facts.py`, and drawing in `display/ui/username.py` (labels only; it
  shouldn't learn about facts).
- **Python 3.11.** No PEP 701 f-strings: no line breaks or reused quotes inside `{}`.
- **Times in the display timezone** (`display.timezone`, else the profile's), never the machine's.
- **Keep it small.** No new libraries or frameworks. Match the existing style.

## Verify before saying done

```bash
python -m pytest tests/ -q
TZ=UTC uv run --no-project --python 3.11 --with-requirements requirements-dev.txt python -m pytest tests/ -q
python -m pytest tests/ --cov --cov-report=term-missing -q   # stays ≥ 90%; new code ~100%
```

Byte-identical check (steps 1–5; from step 6 only the name page may differ). Render on a git
worktree of `develop-beta` and on your branch, then `cmp`:

```bash
python scripts/render_rotation.py --height 64 --demo --out /tmp/new-64.png
python scripts/render_rotation.py --height 32 --demo --out /tmp/new-32.png
python scripts/render_rotation.py --height 64 --cache cookies-joel-dashboard-cache.json --config config.json --out /tmp/new-joel-64.png
```

Look at the new facts on both heights: render each new highlight with `UsernameScreen` into
`scripts.render_demo.ImageMatrix` (64x64 and 64x32), view the PNG, and give Joel the file path.
Note that importing `peloton_led` parses `sys.argv`, so pass paths to a preview script by
environment variable, not argument.

Never say "verified" or "working" for anything you didn't run.

## Finish

1. Update the docs in the same branch:
   - `docs/NAME-PAGE-FACTS.md`: move what you built into "Built", and mark the step done in "Plan".
   - README's `username` section: what the board shows now.
   - `CLAUDE.md`: the `username_facts.py` / `activity.py` lines.
   - `ROADMAP.md`: the facts-engine item lists the remaining steps.
2. Commit with a message that ends with the attribution line the session gives you. Push and open
   a PR into `develop-beta` using `.github/pull_request_template.md`. **Release notes** is one
   or two sentences for Joel about what changes on the board. Don't merge it; Joel does.
3. Tell Joel it's a good point to `/clear`, and give the next session's kick-off line.

## Step notes

Details are in `docs/NAME-PAGE-FACTS.md` ("Plan"). These notes are the traps.

**Step 1: frames and `period_stats`**
- `FRAMES` lives in `peloton/activity.py`: each frame is (key, label word, start, end). Frames:
  week, last week, 30 days, 90 days, year, last year, all time.
- `period_stats(workouts, start, end)` is one loop that returns totals and distinct counts.
  `recent_activity` becomes a call to it; keep the snapshot key or rename it everywhere
  (`dashboard.py` defaults, `render_rotation.py`'s `add_log_figures`, tests).
- Test frame edges: midnight in New York, the DST change (1 November 2026), and 1 January.
- `scripts/list_facts.py --log <path>` prints every candidate fact. Joel's logs are on the boards,
  not this Mac, so also give it a `--demo` mode built from synthetic rows.
- Pass 0 must stay byte-identical (`TOP DISCIPLINE` + all-time instructors).

**Step 2: filters**
- Pass the filter into `period_stats` (discipline or instructor); don't loop the log again for
  each discipline.
- Pick the filter's subject from the rider's top ones in that frame, so it's never something done
  once.

**Step 3: measures and bests**
- Rank ("3RD BEST 30 DAYS") needs a total for every window: build day totals once per refresh,
  then slide the window. Don't call `period_stats` once per day.

**Step 4: comparisons**
- Fair comparisons only: the same length, up to the same point. Show one only when the change
  passes a threshold; put the threshold in a named constant.

**Step 5: events**
- Add `created_at` to `PROFILE_KEYS` in `peloton/dashboard.py`, and nothing else from the profile.
- "On this day" uses the display timezone's date, not UTC.

**Step 6: scoring** — Joel answered the open questions on 2026-11-08: see "Decisions for step 6" in the plan (drop THIS WEEK for a second headline, cool-down in passes, same frames on 32 rows). The old note: the plan's open questions (headline
size, 32-row frames, cool-down length) need his answers.
- The shown history goes in the dashboard cache, per rider, written the way
  `acknowledge_milestone` writes `milestone_shown_at`. A restart must not reset it.
- Scores are named constants; `list_facts.py` prints them.
- Pass 0 changes here. Say so in the PR, and check the other pages are still byte-identical.

**Step 7: together**
- Only when `rivals` is passed (`run_multi_user_loop` passes it to one rider per cycle). Test
  with two profiles, like `test_each_rider_rotation_uses_their_own_goals_milestones_and_journey`.

**Step 8** is optional. Ask Joel before starting.

## Stop and ask Joel when

- A label can't fit 15 characters without losing its meaning.
- A step needs a new log field (`LOG_VERSION` bump, one re-download per board).
- The byte-identical check fails on a page the step shouldn't touch.
- Anything in this brief conflicts with `CLAUDE.md` (`CLAUDE.md` wins; say what conflicted).
