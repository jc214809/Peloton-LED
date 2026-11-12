# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Planned work lives in `ROADMAP.md`; remove an item when its PR merges.

**Keep this file short: it loads in every session.** Feature detail goes in `docs/dev/<topic>.md`, and this file gets one pointer line (see [Topic notes](#topic-notes)). `tests/test_claude_md.py` fails above 16,000 characters or on a pointer to a missing file. Keep the rule a story produced; put the story in the topic note.

## Running the App

```bash
./peloton_led.py --emulated                                      # emulator at http://localhost:8888
./peloton_led.py --emulated --config config.local.json           # real data on a Mac
./peloton_led.py --emulated --username "YourName" --display-duration 10
sudo ./peloton_led.py                                            # Pi with a real panel
```

On a Mac, `config.json` (the Pi's, `/var/lib/peloton-led` paths) can't be used: run with `--config config.local.json` (gitignored; repo-relative token/cache paths, no `matrix.gpio_mapping`), steps in the README's "Running on your Mac with real data". Setup and every config key: README.

Every `--led-*` flag also has a key in the top-level `matrix` config section (flag name minus `led-`, dashes to underscores; `MATRIX_DEFAULTS` in `peloton/config.py`). `utils.utils.matrix_settings` resolves flag → config → default, so the `--led-*` argparse defaults must stay `None`.

## Previewing Screens

```bash
# Whole rotation to a PNG contact sheet, no API calls (cache file or --demo; --insights adds the insight frames)
python scripts/render_rotation.py --height 32 --cache cookies-joel-dashboard-cache.json --config config.local.json --out /tmp/joel-32.png
python scripts/render_rotation.py --height 64 --demo --out /tmp/demo-64.png
```

Both 64x64 and 64x32 are supported. 32-row layouts live behind `matrix.height < 64` checks in each screen; the 64x64 layout is the reference and must not change when adjusting 32 rows (compare `render_rotation.py --height 64` output byte for byte before/after). `docs/64x32-NOTES.md` records every 32-row difference and why. The README's screenshots are real data drawn by the screen code; redraw the ones a visual change affects.

## Running Tests

```bash
python -m pytest tests/
python -m pytest tests/test_username.py                         # one file
python -m pytest tests/ --cov --cov-report=term-missing         # coverage
```

CI (`.github/workflows/tests.yml`) runs the suite on Python 3.11 and 3.13 for every PR and every push to `main` and `develop-beta`. The local venv is newer (3.14), so before pushing also run `TZ=UTC uv run --no-project --python 3.11 --with-requirements requirements-dev.txt python -m pytest tests/ -q`: 3.11 is the boards' Python (no PEP 701 f-strings: no line breaks or reused quotes inside `{}`), and CI runs in UTC (page times use the board's zone, never the machine's). Install test deps with `pip install -r requirements-dev.txt` (it pulls in `requirements-auth.txt`: the browser-login tests import Playwright; Chromium itself is mocked).

Coverage: sources and omits in `.coveragerc`, branch coverage on, `fail_under = 90`; new code needs tests, not omits. CI uploads the 3.11 run's `coverage.xml` to Codecov (`CODECOV_TOKEN` secret), whose patch check also gates a PR.

## Branches and releases

PRs go into `develop-beta` (the old `develop` is stale, ignore it); a release is a `develop-beta` → `main` PR. Every PR needs a `## Release notes` section (`.github/pull_request_template.md`; "None" allowed), and the notes are read from merge commit bodies, so merge with the PR description as the message (`gh pr merge --merge --body ...`). Each merge is auto-tagged (`vX.Y.N-beta`, main's `vX.(Y+1).0`); boards update themselves from those tags. Details: `docs/dev/UPDATER.md`.

## Never commit

`config.json` (the live config, untracked; `config.json-example` is the template), `config.local.json`, `cookies*` (tokens), `training-data/`, `*.workout-rows.json`, `tests/fixtures/workout_compare/real-rows.json`. The repo is public: the workout-compare spec and plans stay outside it.

## Architecture

`peloton_led.py` is the sole entry point: load and validate the config, build the matrix (hardware or emulator) and fonts, start one `Dashboard` per rider (background refresh thread), show the logo, then loop forever through each rider's `display.rotation` (logo between riders). The display loop never touches the network: it reads the dashboard's snapshot, so a slow fetch never stalls the panel. Diagrams of the board's services, the data flow and the release flow: README's Architecture section.

Things that bite across the codebase:
- **Per-rider display config.** `configured_profiles` gives each rider their own `display` (shared section with the rider's `weekly_goals`, `milestones`, `journey` over it); pass that one, never the shared one, to a rider's `run_display_loop`.
- **Root until the matrix exists.** `peloton-led.service` starts as root for `/dev/mem` and drops to `peloton-led` right after `RGBMatrix(...)`; anything moved ahead of that call in `main()` runs as root.
- **Screen times are never 0.** Hiding a screen is leaving it out of `rotation`; `peloton/screen_times.py` is import-free because the settings service uses it too.
- **The cache holds anything.** Screens validate what they read from the snapshot (`insight_views`, `cache.py`), since an old or hand-edited cache can carry anything.
- **The `stats` font is a fixed 4 px:** 15 characters fill the 60 px a label has.

## Topic notes

Read the note before changing its area; update it in the same PR.

| Area | Note |
|---|---|
| Display loop, rotation, screen times, milestones and countdown, PR celebration, workout-page stats | `docs/dev/ROTATION.md` |
| Peloton API, `Dashboard`, workout log, journey, activity figures, name-page facts engine | `docs/dev/DATA.md` (built facts and ideas: `docs/NAME-PAGE-FACTS.md`; log design: `docs/WORKOUT-LOG-PLAN.md`) |
| Workout compare and the board's insights | `docs/dev/WORKOUT-INSIGHTS.md` |
| Settings page, PIN, Power menu, Wi-Fi setup | `docs/dev/SETTINGS-PAGE.md` |
| Installer, systemd units, token renewal, Pushover, root/PWM/audio on the Pi | `docs/dev/BOARD-INSTALL.md` (troubleshooting for people: `docs/install.md`) |
| Releases, auto-tagging, `self_update/`, the Updates card | `docs/dev/UPDATER.md` |
| Screen ABC, `ScreenManager`, driver, fonts, logo, models | `docs/dev/SCREENS.md` |
| Which stats Peloton sends per equipment | `docs/DATA-POINTS.md` |
| Every 64x32 layout difference | `docs/64x32-NOTES.md` |

## File map

- `peloton_led.py`: entry point, `build_rotation_pages`, `show_and_wait`, the loops
- `peloton/`: config, API client, dashboard and cache, workout log and everything derived from it, name-page facts, workout compare, screen times, Pushover
- `display/ui/`: one file per screen, plus `manager.py` and the overlays (padlock, stale clock, settings PIN, Wi-Fi setup)
- `settings_page/`: the board's settings page (its own service, port 8080)
- `self_update/`: `peloton-update`
- `driver/`: rgbmatrix or the emulator
- `utils/`: matrix settings, health heartbeat, Wi-Fi setup state
- `scripts/`: token login/renewal (`refresh_cookies.py`), board seeding, previews (`render_rotation.py`), fact and insight checks, release tagging
- `packaging/`: systemd units and the Pi config template; `peloton-install.sh` is the installer
