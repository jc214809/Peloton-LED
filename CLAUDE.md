# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Emulator mode (development, no Raspberry Pi required)
./peloton_led.py --emulated

# With Peloton API data
./peloton_led.py --emulated --cookies cookies.txt

# Override username and screen duration
./peloton_led.py --emulated --username "YourName" --display-duration 10

# Hardware (Raspberry Pi with physical LED matrix)
sudo ./peloton_led.py
```

Key CLI flags: `--config <path>` (default: `config.json`), `--led-rows`, `--led-cols`, `--cookies`, `--username`, `--display-duration`.

Every `--led-*` flag also has a key in the top-level `matrix` config section (flag name minus `led-`, dashes to underscores; `MATRIX_DEFAULTS` in `peloton/config.py`). `utils.utils.matrix_settings` resolves flag → config → default, so the `--led-*` argparse defaults must stay `None`.

## Previewing Screens

```bash
# Whole rotation to a PNG contact sheet, no API calls (cache file or --demo)
python scripts/render_rotation.py --height 32 --cache cookies-joel-dashboard-cache.json --out /tmp/joel-32.png
python scripts/render_rotation.py --height 64 --demo --out /tmp/demo-64.png
```

Both 64x64 and 64x32 are supported. 32-row layouts live behind `matrix.height < 64` checks in each screen; the 64x64 layout is the reference and must not change when adjusting 32 rows (compare `render_rotation.py --height 64` output byte for byte before/after). `docs/64x32-NOTES.md` records every 32-row difference and why.

## Running Tests

```bash
python -m pytest tests/
# Single test file
python -m pytest tests/test_username.py
```

CI (`.github/workflows/tests.yml`) runs the suite on Python 3.11 and 3.13 for every PR and push to main. Install test deps with `pip install -r requirements-dev.txt`: it pulls in `requirements-auth.txt` because the browser-login tests import Playwright (Chromium itself is mocked).

Coverage: `python -m pytest tests/ --cov --cov-report=term-missing` (sources and omits in `.coveragerc`, branch coverage on). `fail_under = 90` in `.coveragerc` fails the run below 90%; new code needs tests, not omits. CI uploads the 3.11 run's `coverage.xml` to Codecov using the `CODECOV_TOKEN` repo secret, the same setup as LightningLane-Live-LED.

## Pi config

On the Pi, the checkout's `config.json` is the live config: the installer writes `project-config.conf` drop-ins (`BindReadOnlyPaths=-<checkout>/config.json:/etc/peloton-led/config.json`) for `peloton-led.service` and `peloton-token-refresh.service`, because `ProtectHome=true` hides `/home`. The file must use `/var/lib/peloton-led/...` token/cache paths. `config.json` is untracked; `config.json-example` is the template.

Token renewal (`scripts/refresh_cookies.py --ensure`) prefers the Auth0 refresh token saved beside each token file (`cookies-x.refresh.json`). Auth0 rotates it on every use and rejects reuse with `invalid_grant`, so persist the new one before anything else, never share one file between machines, and never retry Chromium hourly after `invalid_grant` (slow boards would fail every time): a board with Playwright/Chromium and credentials tries one browser login per day (`<stem>.browser-attempt` records the last try, written before starting); `--no-browser` boards never do. Each refresh file also records `chain_started_at` and `renewals`, carried through every rotation (a new login starts a new chain). `--status` and the `invalid_grant` error report the chain's age, which is how we learn Auth0's real chain lifetime. `--ensure` reports each run to `peloton/notify.py`, which sends Pushover alerts (`PUSHOVER_APP_TOKEN`/`PUSHOVER_USER_KEY` in auth.env) rate-limited by `token-alert-state.json` beside the tokens: second failure in a row or `invalid_grant`, then daily, plus one recovery notice. When renewal raises `LoginRequired` (incl. `RefreshTokenRejected`) it writes `<stem>.renewal-failed`; `Dashboard.login_indicator_required` shows the padlock from it (checked every 30 s, ignored once the token file is newer), but the refresh loop keeps using `login_required` so data keeps updating on the still-valid token. `scripts/seed_board.sh user@board` seeds, copies and installs a per-board pair from the Mac (via `--seed-dir`); `peloton-install.sh --no-browser` skips Chromium/Playwright.

The installer builds `rpi-rgb-led-matrix` from upstream master, whose Python binding includes Pillow's private `Imaging.h`. `scripts/fetch_pillow_headers.py` pulls headers from the PyPI sdist of the exact Pillow in the venv (passed via `CFLAGS`); don't swap in Debian's `python3-pil` headers, since Pillow 12+ changed the struct layout the binding reads.

## Setup

```bash
pip install -r requirements.txt
cp config.json-example config.json  # then edit with your settings
```

For Sixel support in the emulator (optional): `brew install libsixel` on macOS.

## Architecture

### Entry Point & Display Loop

`peloton_led.py` is the sole entry point. It:
1. Loads `config.json`, builds a `PelotonClient` from `cookies.txt`
2. Creates the `RGBMatrix` (hardware or emulator) and initializes fonts
3. Registers screens with `ScreenManager`, shows a startup logo, then enters the display loop
4. The loop cycles: logo → username → recent workout disciplines → all-time discipline totals

The loop is intentionally network-free after startup — all data is prefetched before `run_display_loop()` is called.

### Driver Abstraction (`driver/`)

`driver/__init__.py` replaces the `driver` module in `sys.modules` with a `DriverWrapper` instance. When `--emulated` is passed (or tests are running), it imports `RGBMatrixEmulator`; otherwise it tries to import `rgbmatrix` (the native Raspberry Pi library) and falls back to the emulator. All code imports `from driver import RGBMatrix, graphics, ...` transparently.

### Screen System (`display/ui/`)

All screens implement the `Screen` ABC (`display/ui/screen.py`):
- `on_enter(matrix, state)` — called when screen becomes active
- `render(matrix, state)` — draws to the matrix
- `update(dt)` — optional animation tick
- `on_exit(matrix)` — clears the matrix by default

`ScreenManager` (`display/ui/manager.py`) holds a registry of named screens, manages transitions (calling `on_exit`/`on_enter`), and drives `tick()` calls. Screens are registered with `manager.register(name, ScreenInstance)` and shown with `manager.show(name, state)`.

`show_and_wait(manager, name, state, duration)` in `peloton_led.py` is the standard way to display a screen for a fixed duration.

### Peloton API Layer

- `peloton/api.py` — `PelotonClient`: raw HTTP calls to `api.onepeloton.com`, using a `requests.Session` from `make_session(token_path)` (Bearer token; the file is called `cookies*.txt` for history). Records `login_required` on HTTP 401.
- `peloton/dashboard.py` — `Dashboard`: background refresh thread, cache, failure counting and the stale/login flags the display reads.

Tokens come from `scripts/refresh_cookies.py` (browser login once, then Auth0 refresh tokens; see Pi config above).

### Config (`config.json`)

Key display settings under `display`:
- `username` — fallback display name
- `font` — font key (`ride`, `park`, `info`, `countdown`)
- `color` — color key (`white`, `red`, `gold`, `disney_blue`)
- `duration` — username screen duration (seconds)
- `overview_duration` — per-discipline page duration (seconds)
- `per_workout_duration` — per-recent-workout page duration (seconds)
- `logo_path` — optional override for startup logo image
- `logo_duration` — startup logo display duration (seconds)

### Fonts & Colors (`display/display.py`)

`initialize_fonts(matrix_height)` loads `.bdf` fonts from `assets/fonts/patched/` into a global `loaded_fonts` dict, keyed by font name. Font selection is board-height-aware (32 vs 64 rows). Colors are defined as `graphics.Color` instances in `colors()`.

### Logo Preparation (`scripts/`, `prepared_logos/`)

`scripts/prepare_image.py` and `scripts/postprocess_logos.py` generate optimized PNGs for the LED matrix. Pre-generated logos are stored in `prepared_logos/`. The app auto-selects `peloton_64x64_auto.png` or `peloton_64x32_auto.png` based on matrix row count unless `display.logo_path` is set.

### Models (`models/`)

Typed workout data models for each discipline: `cycling.py`, `running.py`, `rowing.py`, `strength.py`, all extending `models/core.py`. Used by `peloton/summaries.py` to normalize raw API payloads into structured workout summaries.
