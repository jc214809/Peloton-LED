# Code health: plan

Status: phase 1 (guardrails) and phase 2a–2d merged (2026-11-18); 2e (`build_rotation_pages`, `apply_form`) **done** on branch `rotation-and-form-complexity`, awaiting merge; 2f part A (`draw_icon`, `PrCelebrationScreen.render`, `_scanline_fill_polygon`) **done** on branch `display-draw-complexity`, awaiting merge; 2f part B and phase 3 planned. Roadmap item 33. Structural `noqa`s after 2f-A: `C901` 22, `PLR0912` 15, `PLR0913` 12, `PLR0915` 6.

CI checks behavior (pytest, 90% coverage) but nothing checks shape: no linter, no
complexity limit, no file-size limit, no rule on which package may import which. So
`settings_page/page.py` reached 1,748 lines, `display/ui/last_workout_screen.py` 1,271,
and `validate_config` a cyclomatic complexity of 60. This plan adds the checks first,
with today's offenders listed as a baseline (a "ratchet": nothing new may get worse,
and each fix removes its baseline entry), then works the baseline down one PR at a time.

Built to be run by Sonnet agents, one PR each, with a lead session (Opus) that
starts them, reviews each diff, reruns the checks and opens the PRs.

## Measured baseline (2026-11-18, ruff 0.17.5, `--isolated`)

| Check | Hits |
|---|---|
| `C901` complexity > 10 | 37 |
| `PLR0912` > 12 branches | 26 |
| `PLR0915` > 50 statements | 16 |
| `PLR0913` > 7 arguments (71 at the default 5, 36 at 6, 12 at 7, 8 at 8) | 12 |
| `E`, `F`, `W`, `B` without `E501` and `B905` | 55 |
| `E501` at 88 / 100 / 110 / 120 / 140 columns | 6,198 / 3,010 / 1,025 / 153 / 19 |
| `ruff format --check` | 183 of 211 files would change |
| Source files over 600 lines | `settings_page/page.py` 1748, `display/ui/last_workout_screen.py` 1271, `peloton/dashboard.py` 973, `scripts/refresh_cookies.py` 704, `settings_page/server.py` 670, `peloton_led.py` 618 |
| Baseline after phase 1: inline structural `# noqa` | `C901` 37, `PLR0912` 26, `PLR0913` 12, `PLR0915` 16 (count with `grep -rn "noqa:[^#]*C901" --include=*.py . \| wc -l`; a line can carry several codes). Each fix removes its entry; `ruff check .` and `lint-imports` pass. |

Worst functions: `validate_config` (peloton/config.py, 60), `build_rotation_pages`
(peloton_led.py, 35), `apply_form` (settings_page/form.py, 32), `draw_icon`
(display/ui/lifetime_overview.py, 31), `LastWorkoutScreen.render` (23), `do_POST`
(settings_page/server.py, 21), `refresh_cookies.main` (21), `load_snapshot`
(peloton/cache.py, 21).

The import layering already held before phase 1; phase 1's import-linter contracts now
enforce it (`pyproject.toml`; the `driver` contract checks direct imports only, since
`driver` reaches `peloton.config` through `utils.utils`):
- `peloton/` imports only `models` and `requests` (plus itself).
- `display/` imports from `peloton` only the pure helpers in `challenges`, `club` and
  `booked_classes`, never `api`, `dashboard` or `requests`. One cross-service import:
  `display/ui/settings_pin.py` takes `PIN_FILE` from `settings_page.pins`.

## Decisions made

- **Ratchet with inline `# noqa`, not per-file ignores.** `ruff check --add-noqa` writes
  a `# noqa: C901` (etc.) on each offending line. The debt is visible where it lives,
  parallel refactor PRs don't all edit one ignore list in `pyproject.toml`, and
  `RUF100` (unused `noqa`) fails CI when a refactor fixes a function but leaves its
  `noqa`, so the baseline can only shrink.
- **Thresholds:** ruff defaults (complexity 10, 12 branches, 50 statements) except
  `max-args = 7`. Draw functions take x, y, colour, font, width and so on, so 5 would
  mostly flag signatures that are fine.
- **Not in phase 1:** `E501` (line length), `I` (import sorting, 117 files), `UP`
  (syntax upgrades), `B905` (adding `strict=True` to `zip()` changes behavior) and
  `ruff format`. Each one rewrites much of the repo and would conflict with every
  open branch. See "Later, Joel's call".
- **Max file length 600 lines for source, tests exempt.** It's enforced by a test, the
  same pattern as `tests/test_claude_md.py`, with an allowlist that holds today's
  offenders at their current length (a file may shrink but not grow).

## Rules for every agent

Paste this block into every brief.

- Read `CLAUDE.md`, this plan, and the topic note for the area you touch
  (`docs/dev/*.md`) before changing anything.
- Work in your own git worktree on the branch named in your brief, cut from
  `origin/develop-beta`. Commit there; do not push, open a PR, or touch other branches.
- **No behavior change** unless the brief says so. Refactors move and split code; they
  don't fix or improve it on the way. If you find a bug, note it in your report and
  leave it.
- Never commit `config.json`, `config.local.json`, `cookies*`, `training-data/`,
  `*.workout-rows.json` or `tests/fixtures/workout_compare/real-rows.json`. Never
  `git add -A` or `git commit -a`; add files by name.
- Python 3.11 compatible: no line breaks or reused quote marks inside f-string `{}`.
- Before reporting done, all of these must pass, and you paste their output in your
  report:
  ```bash
  python -m pytest tests/ -q
  TZ=UTC uv run --no-project --python 3.11 --with-requirements requirements-dev.txt python -m pytest tests/ -q
  ruff check .                # once phase 1 has merged
  lint-imports                # once phase 1 has merged
  ```
  Coverage must stay at or above 90% (`--cov`). Never weaken, skip or delete a test to
  make it pass. If a check fails and you can't fix it, stop and report it; don't
  describe it as pre-existing.
- **Screens must render byte-identically.** Any PR touching `display/` or
  `peloton_led.py` renders the rotation before and after, at both heights, and
  compares the files:
  ```bash
  for h in 64 32; do python scripts/render_rotation.py --height $h --demo --insights --out /tmp/before-$h.png; done
  # ...make the change...
  for h in 64 32; do python scripts/render_rotation.py --height $h --demo --insights --out /tmp/after-$h.png; done
  cmp /tmp/before-64.png /tmp/after-64.png && cmp /tmp/before-32.png /tmp/after-32.png
  ```
- Update in the same commit: the topic note for the area, the `CLAUDE.md` file map if
  a file moves or a new one appears, and this plan's status line for your step.
- Your report has: the branch, a one-paragraph summary, files changed, the check
  output, anything you noticed but didn't change, and a draft PR description with a
  `## Release notes` section ("None" for anything boards won't notice).

## Lead's checklist (per agent PR)

1. Read the whole diff. For a refactor, confirm it moves code and nothing else.
2. Rerun the four checks and the render comparison yourself; don't trust the report.
3. Push and open the PR into `develop-beta` only when Joel says so. Merge with the PR
   description as the message.
4. After merging, remove the agent's worktree and branch.

## Phase 1: guardrails (one agent, must merge first)

Branch `code-health-guardrails`. Brief:

> Add lint, complexity, file-size and import-layer checks to the repo and CI, with
> today's offenders recorded as a baseline so the build passes on day one.
>
> 1. Add `pyproject.toml` holding only tool config, no packaging. `[tool.ruff]`:
>    `target-version = "py311"`, `extend-exclude` for anything gitignored that holds
>    Python. `[tool.ruff.lint]`: `select = ["E", "F", "W", "B", "C901", "PLR0912",
>    "PLR0913", "PLR0915", "RUF100"]`, `ignore = ["E501", "B905"]`.
>    `[tool.ruff.lint.mccabe] max-complexity = 10`. `[tool.ruff.lint.pylint]
>    max-args = 7`. Add a comment on each choice pointing at docs/CODE-HEALTH-PLAN.md.
> 2. Fix the roughly 55 hits outside the structural rules (`F401`, `E702`, `E731`,
>    `E741`, `E402`, `B007`, `B008`, `B904`, `W291` and so on) where the fix doesn't
>    change behavior. For each `B023` (loop variable captured in a closure), read the
>    code: if it's a real bug, don't fix it; add a `# noqa: B023` with a comment
>    saying "possible bug, see report" and list it in your report. If it's safe, bind
>    the variable through a default argument. `B008`: only fix if the default is
>    really built once on purpose; otherwise `noqa` it with a one-line reason.
> 3. Run `ruff check --add-noqa .` for the structural rules (`C901`, `PLR0912`,
>    `PLR0913`, `PLR0915`) and nothing else, then `ruff check .` must pass. Count the
>    `noqa`s added per rule and put the counts in this plan's baseline table as the
>    starting point.
> 4. Add `[tool.importlinter]` to `pyproject.toml` with `root_packages = ["peloton",
>    "display", "settings_page", "self_update", "utils", "driver", "models"]`,
>    `include_external_packages = true`, and these contracts:
>    - `peloton` may not import `display`, `settings_page`, `self_update`, `driver`
>      or `utils` (forbidden).
>    - `display` may not import `requests`, `peloton.api` or `peloton.dashboard`
>      (forbidden). The display loop never touches the network.
>    - `driver` may not import `peloton`, `display` or `settings_page` (forbidden).
>    - Allow `display.ui.settings_pin -> settings_page.pins` through `ignore_imports`
>      with a comment saying why.
>    Check each contract by breaking it on purpose (add a forbidden import, see
>    `lint-imports` fail, remove the import).
> 5. Add `tests/test_file_length.py`: every tracked `.py` file outside `tests/` is
>    at most 600 lines, except an allowlist `{path: max_lines}` set to today's lengths
>    (see the baseline table). The test also fails when an allowlisted file is now
>    shorter than its cap, with a message telling you to lower the cap, so the list
>    keeps shrinking. List files with `git ls-files`; the test must not depend on the
>    working directory (see `tests/test_claude_md.py`).
> 6. Pin `ruff==0.17.5` and `import-linter==2.17` in `requirements-dev.txt`. In
>    `.github/workflows/tests.yml` add one `lint` job (Python 3.11 only, before or
>    beside `pytest`) running `ruff check .` and `lint-imports`. Leave the `pytest`
>    job as is.
> 7. Add `.pre-commit-config.yaml` with the ruff hook at the same version, and one
>    line in the README's development section on `pre-commit install`.
> 8. Docs: a "Lint and structure checks" paragraph in `CLAUDE.md` under Running
>    Tests (the commands, the ratchet rule "remove a function's `noqa` when you touch
>    it; never add a structural `noqa` to new code", and the 600-line rule). Keep
>    `CLAUDE.md` under 16,000 characters (`tests/test_claude_md.py`). Add the
>    `## Docs` line to the PR description if the template has it.
>
> Release notes: None.

Size: small to medium. The diff is wide but shallow (a `noqa` on about 90 lines).

## Phase 2: work the baseline down (parallel, after phase 1 merges)

One agent per item, each its own branch. Run at most three at once, so the lead can
review them properly. Start with 2a, 2b and 2c. Every item ends with: the target
file under 600 lines (or as near as the brief says) with its allowlist cap lowered,
its structural `noqa`s removed, and `ruff check .` passing.

Every brief starts with the "Rules for every agent" block above, then:

**2a. Split `display/ui/last_workout_screen.py`** (1,271 lines, 71 functions, 22 hits;
branch `split-last-workout-screen`)
> Split it into a `display/ui/last_workout/` package by what each part draws (look
> for natural seams: the intro and title, the stats rows, the graph, the heart-rate
> row, the 64x32 variants). Keep `LastWorkoutScreen` importable from its current path
> (re-export it from `display/ui/last_workout_screen.py`, or update every import,
> including tests and `scripts/`). Break `render` (complexity 23) into named steps.
> The render comparison must be byte-identical at both heights, with `--insights`
> and also with a real cache if one is in the checkout
> (`--cache cookies-*-dashboard-cache.json --config config.local.json`). Update
> `docs/dev/SCREENS.md` and `docs/dev/ROTATION.md` where they name the file.

**2b. Split `peloton/dashboard.py`** (973 lines, 8 hits; branch `split-dashboard`)
> Separate the background-refresh and fetch code from the snapshot and cache
> handling, and from any per-figure derivations that ended up here. Keep `Dashboard`'s
> public methods and their signatures. The cache file format must not change: write a
> snapshot with the old code and read it with the new (and the reverse) in a test.
> Update `docs/dev/DATA.md`.

**2c. Make `validate_config` table-driven** (`peloton/config.py`, complexity 60;
branch `config-validation-table`)
> Replace the long if-chain with a table of per-key checks (key path, expected type,
> allowed values or range, error message) and a small loop, keeping every error
> message word for word, since the settings page and tests match on them. Before
> changing anything, add a test that feeds every invalid case
> `tests/test_config_validation.py` already covers, plus any branch it misses
> (`--cov-report=term-missing` on `peloton/config.py`), and records the exact
> messages. That test must pass unchanged afterwards.

**2d. Split `settings_page/page.py`** (1,748 lines, the biggest file; branch
`split-settings-page`)
> It builds the settings page's HTML. Split it into one module per card or section
> under `settings_page/page/` (or `settings_page/cards/`). The served HTML must be
> byte-identical: before changing anything, write a test that renders the page for
> `config.json-example`, `config.dual-users-example.json` and a config with every
> optional section filled, and compares it against a stored copy of the current
> output. Update `docs/dev/SETTINGS-PAGE.md`.

**2e. `build_rotation_pages` and `apply_form`** (`peloton_led.py` 35,
`settings_page/form.py` 32; branch `rotation-and-form-complexity`)
> Break each into one small function per page kind or per form section, dispatched
> from a dict. Byte-identical render comparison for `build_rotation_pages`; for
> `apply_form`, the existing `tests/test_settings_form.py` plus a test that applies a
> full form and compares the resulting config JSON with today's.

**2f. The rest of the list** (one branch per two or three files, after 2a–2e)
> `draw_icon` (31), `do_POST` (21), `refresh_cookies.main` (21), `load_snapshot`
> (21), then whatever `grep -rn "noqa: C901\|noqa: PLR09" --include=*.py .` still
> shows, worst first. Same rules: no behavior change, a test that pins today's
> output first if none does.

## Phase 3: reorganize `peloton/` into subpackages (alone, after phase 2 merges)

Branch `peloton-subpackages`. Runs with no other agent open, because it touches
imports in nearly every file.

> Pure move: no code changes besides import lines. Use `git mv` so history follows.
> Proposed grouping (check it against the imports first and propose changes in your
> report before moving anything if a module doesn't fit):
> - `peloton/api/`: `api`, `challenges`, `club`, `booked_classes`, `goals`,
>   `instructors`
> - `peloton/workouts/`: `workout_log`, `workout_rows`, `workout_features`,
>   `workout_insights`, `workout_compare`, `insight_lines`, `records`
> - `peloton/stats/`: `activity`, `journey`, `totals`, `summaries`, `username_facts`,
>   `schedule`, `selection`
> - `peloton/` itself keeps the infrastructure: `config`, `cache`, `dashboard`,
>   `notify`, `timestamps`, `screen_times`, `demo`
>
> Things that will bite:
> - **The updater runs while files change.** A board updates by checking out a new
>   tag; `self_update/` and the settings service are running at that moment. Find
>   every import of a `peloton` module inside `self_update/` and `settings_page/`,
>   including imports inside functions, and confirm none runs after the checkout but
>   before the restart. Report what you found.
> - `peloton/screen_times.py` must stay import-free (the settings service uses it).
> - Systemd units and `peloton-install.sh` name scripts and `-m` modules by path; grep
>   `packaging/` and the installer and keep them working. The installer copies whole
>   directories, so new subfolders are picked up.
> - Tests that patch by dotted path (`mock.patch("peloton.api....")`) must follow the
>   move; grep for every `"peloton.` string, not just imports.
> - Add import-linter `layers` for the new subpackages (`peloton.stats` and
>   `peloton.workouts` may use `peloton.api`'s parsers but not the reverse, adjusted to
>   what the imports actually show) and update `.coveragerc` if needed.
> - Update the `CLAUDE.md` file map and every `docs/dev/*.md` path.
>
> Then the same for `display/ui/`: move the overlays (`login_indicator`,
> `stale_indicator`, `settings_pin`, `wifi_setup_screen`) to `display/ui/overlays/`,
> in the same PR or a second one.

Release notes: none for boards, but say in the PR that the next update moves files.

## Later, Joel's call

- **`ruff format` and import sorting (`I`) across the repo.** One mechanical PR,
  done when no other branch is open, plus a `.git-blame-ignore-revs` file so
  `git blame` skips it. It stops style arguments for good but rewrites 183 files.
- **Line length.** `E501` at 120 columns is 153 lines to fix; at 140, 19.
- **`UP` rules** (`list[...]` for `List[...]`, `datetime.UTC`): about 170 automatic
  fixes, safe on 3.11.
- **Type checking** (mypy or pyright) on `peloton/` only, to start. A larger job;
  worth sizing after phase 3.
