# Screens, driver, fonts and logo

<!-- Moved from CLAUDE.md on 2026-11-12 so it loads only when needed. Keep it current with the code it describes. -->

Read before adding a screen or changing `driver/`, `display/display.py`, `display/ui/manager.py`, `logo_art.py` or `models/`.

## Screen system (`display/ui/`)

All screens implement the `Screen` ABC (`display/ui/screen.py`):
- `on_enter(matrix, state)` — called when screen becomes active
- `render(matrix, state)` — draws to the matrix
- `update(dt)` — optional animation tick
- `on_exit(matrix)` — clears the matrix by default

`ScreenManager` (`display/ui/manager.py`) holds a registry of named screens, manages transitions (calling `on_exit`/`on_enter`), and drives `tick()` calls. Screens are registered with `manager.register(name, ScreenInstance)` and shown with `manager.show(name, state)`.

`show_and_wait(manager, name, state, duration)` in `peloton_led.py` is the standard way to display a screen for a fixed duration.

## Driver (`driver/`)

`driver/__init__.py` replaces the `driver` module in `sys.modules` with a `DriverWrapper` instance. When `--emulated` is passed (or tests are running), it imports `RGBMatrixEmulator`; otherwise it tries to import `rgbmatrix` (the native Raspberry Pi library) and falls back to the emulator. All code imports `from driver import RGBMatrix, graphics, ...` transparently.

## Fonts and colours (`display/display.py`)

`initialize_fonts(matrix_height)` loads `.bdf` fonts from `assets/fonts/patched/` into a global `loaded_fonts` dict, keyed by font name. Font selection is board-height-aware (32 vs 64 rows). Colors are defined as `graphics.Color` instances in `colors()`.

## Logo (`display/ui/logo_art.py`)

The startup logo (`LogoMaskScreen`) is drawn, not decoded: the red mark (`logo_art.MARK`, cropped from the 32-row art), PELOTON and L E D in the loaded fonts, and a zone bar in `ZONE_COLORS` (also the workout pages' `HR_ZONE_COLORS`). 64 rows stack them; fewer put the mark on the left. `display.logo_path` swaps in an image file (`LogoScreen`). `settings_page/logo.py` draws the settings page's icons from the same art (inline SVG for the header and favicon, `/apple-touch-icon.png` served without a PIN), so `logo_art` must stay import-free. `scripts/render_logo.py` regenerates `docs/logo.png` and the README's startup screenshot. `prepared_logos/` and the `prepare_image`/`postprocess_logos` scripts are only for `logo_path` images.

## Models (`models/`)

Typed workout data models for each discipline: `cycling.py`, `running.py`, `rowing.py`, `strength.py`, all extending `models/core.py`. Used by `peloton/summaries.py` to normalize raw API payloads into structured workout summaries.

## Emulator

For Sixel output in the emulator (optional): `brew install libsixel` on macOS.

## Display keys that touch screens

The README's Configuration table is the full list; these notes cover legacy behaviour.

Key display settings under `display`:
- `username` — fallback display name
- `font` — no longer used (`UsernameScreen` picks the largest font that fits); still validated (`discipline`, `info`, `titles`, `stats`, `countdown`; legacy `ride`/`park` map to `discipline`) so old configs load, and kept on save though the settings page doesn't show it
- `color` — `white`, `gold`, `red`, `disney_blue`, `down` (the settings page's General card offers the first four as *Text colour*, plus `down` when a config already has it)
- `duration` — username screen duration (seconds)
- `overview_duration` — per-discipline page duration (seconds)
- `per_workout_duration` — per-recent-workout page duration (seconds)
- `logo_path` — optional override for startup logo image
- `logo_duration` — startup logo display duration (seconds); `show_logo` false hides it
