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
python scripts/render_rotation.py --height 32 --cache cookies-joel-dashboard-cache.json --config config.json --out /tmp/joel-32.png
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

Token renewal (`scripts/refresh_cookies.py --ensure`) prefers the Auth0 refresh token saved beside each token file (`cookies-x.refresh.json`). Auth0 rotates it on every use and rejects reuse with `invalid_grant`, so persist the new one before anything else, never share one file between machines, and never retry Chromium hourly after `invalid_grant` (slow boards would fail every time): a board with Playwright/Chromium and credentials tries one browser login per day (`<stem>.browser-attempt` records the last try, written before starting); `--no-browser` boards never do. Each refresh file also records `chain_started_at` and `renewals`, carried through every rotation (a new login starts a new chain). `--status` and the `invalid_grant` error report the chain's age, which is how we learn Auth0's real chain lifetime. `--ensure` reports each run to `peloton/notify.py`, which sends Pushover alerts (`PUSHOVER_APP_TOKEN`/`PUSHOVER_USER_KEY` in auth.env) rate-limited by `token-alert-state.json` beside the tokens: second failure in a row or `invalid_grant`, then daily, plus one recovery notice. When renewal raises `LoginRequired` (incl. `RefreshTokenRejected`) it writes `<stem>.renewal-failed`; `Dashboard.login_indicator_required` shows the padlock from it (checked every 30 s, ignored once the token file is newer), but the refresh loop keeps using `login_required` so data keeps updating on the still-valid token. `scripts/seed_board.sh user@board` seeds, copies and installs a per-board pair from the Mac (via `--seed-dir`); `peloton-install.sh --no-browser` skips Chromium/Playwright. The installer defaults to manual mode (not started at boot or during install; `--start-at-boot` opts in), except that an upgrade with neither flag keeps a board already enabled at boot (`resolve_start_mode`). It also picks the token mode (`resolve_token_mode`): a flag wins (`--auto-token`/`--no-browser`/`--no-auto-token`), else a renewing mode the board already has — saved in `/etc/peloton-led/token-mode` as `<mode> <flag|auto>` (written by `save_token_mode` as soon as `/etc/peloton-led` exists, so a failed install keeps it), or, if `peloton-led.service` is installed without that file, inferred from the timer/`manual.conf` and whether the venv imports Playwright — else the hardware (32-bit `getconf LONG_BIT` or under 768 MB → `no-browser`, otherwise `browser`). Renewal stays off only with origin `flag` (`--no-auto-token`): before that flag existed, "off" just meant an upgrade ran without `--auto-token`, so a bare saved `none` (the first version's format) or an older board without renewal gets the hardware's mode. `peloton-led.service` passes no `--led-*` flags (a flag beats config, so the old `--led-gpio-mapping adafruit-hat` hid the config's value); `matrix.gpio_mapping` comes from config (`packaging/config.pi.json` sets `adafruit-hat`), and `check_gpio_mapping` stops the installer before any change if the live config lacks it. `peloton-led.service` starts as `User=root`/`Group=peloton-led` so the driver can map `/dev/mem` (the PWM pulse `adafruit-hat-pwm` needs, and the 1 MHz timer); as an unprivileged user the driver falls back to `/dev/gpiomem` and `-pwm` exits with "Need root". `PELOTON_MATRIX_USER=peloton-led` makes `led_matrix_options` set `drop_priv_user/group`, so the driver drops right after creating the matrix (before `configured_profiles` touches tokens/cache), and `ensure_privileges_dropped` exits if it's still root (the driver ignores a failed drop). Anything moved ahead of the `RGBMatrix(...)` call in `main()` runs as root. `adafruit-hat-pwm` also needs the onboard audio off (`dtparam=audio=off` + `blacklist snd_bcm2835`): the driver exits with a `snd_bcm2835` message otherwise. `check_pwm_audio` (after `check_gpio_mapping`, which records `GPIO_MAPPING`) asks before doing that and exits unchanged on no or without a tty; tests stub `is_interactive` and override `PROC_MODULES`/`BOOT_CONFIG`/`MODPROBE_DIR`. The boot partition is FAT, so no `cp -p` there. Blank-panel debugging on PelotonPi (2026-11-01) hit "Need root" first, then would have hit the audio; the jumper was fine. Troubleshooting entry in `docs/install.md`. `start_or_restart_display` restarts a display that was running when the install began even in manual/`--no-start` mode.

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

On a multi-rider board, `configured_profiles` gives each profile its own `display` (the shared section with the rider's `weekly_goals`, `milestones` and `journey` over it), and `run_multi_user_loop` must pass that, not the shared one, to each rider's `run_display_loop`: until 2026-11-04 it passed the shared one, so per-rider goal pages never showed. `render_rotation.py` hard-codes its own goals, so it can't catch this; `test_each_rider_rotation_uses_their_own_goals_milestones_and_journey` does.

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
- `peloton/dashboard.py` — `Dashboard`: background refresh thread, cache, failure counting and the stale/login flags the display reads. Each refresh: overview + the newest `recent_fetch_size` workouts (profile once a day), merged into the workout log; a `peloton-history` thread does the first full download (resumable, `history_batch_size` per batch) and count-mismatch re-walks.
- `peloton/workout_log.py` — `WorkoutLog`: every workout as a slim row keyed by workout ID (`<cache>.workouts.json`). Instructor counts, journey miles and weekly progress are derived from it on each refresh by feeding `as_workout()` rows to the existing `merge_instructor_counts` / `merge_distance_totals` / `weekly_progress`, so a counting fix never needs a re-download. Instructor and distance figures stay empty until the backfill is complete. To add a field: extend `trim()` and bump `LOG_VERSION` (one re-download per board). Design and measurements: `docs/WORKOUT-LOG-PLAN.md`.
- `peloton/activity.py` — per-day figures from the log: `streak_week_workouts` (streak-eligible workouts since Monday, for the weekend `streak_risk` page that replaces `streak`) and `daily_minutes` (12 weeks, for the `heatmap` page). Both arrive in the snapshot via `WorkoutLog.derived`.

### Settings page (`settings_page/`)

`python -m settings_page.server` (`peloton-settings.service`, port 8080, root, its own service so a config that stops the display can be fixed; ported from LightningLane-Live-LED's). `form.py` is config ⇄ form (only shown keys change; requires the hidden `settings_form` field since unticked switches post nothing; every check is `peloton.config.validate_config` on a copy, so `load_config` and the page agree), `page.py` the HTML (inline CSS/JS, works without JS; rotation rows drag by a grip with pointer events (mouse and touch; arrow keys on the grip), a switched-off screen drops to the bottom and a switched-on one joins the end of the numbered ones; `tests/test_settings_form.py` parses it like a browser, and saving an unchanged page must load the same), `pins.py` the PIN gate, `server.py` stdlib HTTP. Riders are matched by index plus a hidden name check; names, token/cache paths, `*_env` and the journey are never on the page. Logins card (`logins.py`, no HTTP/HTML): health from renewal's own files via `scripts/refresh_cookies.py` helpers (`token_status`, `load_refresh_chain`/`describe_chain`, the `.renewal-failed` marker honoured only while newer than the token, `.browser-attempt`, `token-alert-state.json`, `/etc/peloton-led/token-mode`), unit state from `systemctl show`; *Renew now* is `systemctl start --no-block peloton-token-refresh.service`; credentials are write-only: `update_auth_env` rewrites only the changed lines (setup_config.py's quoting, 600, no .bak), the page only ever gets set/not-set, the log only names what changed, and `/credentials` needs a PIN session even on the hotspot. Relative token paths start from `--token-base` (/etc/peloton-led, as the display sees its config), not the checkout. PIN-page states live at `/signin`. The PIN goes to `/run/peloton-led-settings/pin` (`RuntimeDirectory`, group peloton-led, 0640) and `display/ui/settings_pin.py` draws it in `ScreenManager.tick`; `show_and_wait` repaints when it appears/goes, like the padlock. Wi-Fi: `utils/wifi_setup.py` reads comitup's `/run/comitup-state` (written by LLL's `board-setup.sh`); while `HOTSPOT`, a browser in 10.41.0.0/16 needs no PIN and `run_multi_user_loop` holds the `wifi_setup` screen each cycle. Save: validate, `.bak`, atomic write keeping owner/mode, then `restart_app`: `not_running` (manual board off) / `restarted` / `failed` / `saved` (no systemd). The display's config is a read-only bind of the checkout file, so the settings service gets the real path and its folder via its own `project-config.conf` drop-in; the atomic replace is picked up when the display restarts. Installer: `resolve_settings_page` (flag, else on unless installed-and-disabled), `start_settings_page` after `start_or_restart_display`.

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
