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

Two layers:
- `peloton/api.py` — `PelotonClient`: raw HTTP calls to `api.onepeloton.com`. Requires a `requests.Session` initialized from `cookies.txt` (Netscape/semicolon-delimited cookie format).
- `api/peloton_api.py` — `PelotonAPI`: thin safety wrapper around `PelotonClient` that handles `None` client (when cookies are missing) and catches exceptions, returning safe defaults.

Authentication is cookie-based — no username/password login. Extract cookies from a browser session after logging in at onepeloton.com.

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
