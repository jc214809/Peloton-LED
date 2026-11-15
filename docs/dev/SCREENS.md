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

`initialize_fonts(matrix_height)` loads `.bdf` fonts from `assets/fonts/patched/` into a global `loaded_fonts` dict, keyed by font name. Font selection is board-height-aware (32 vs 64 rows). Colors are defined as `graphics.Color` instances in `colors()`. The 5-row small fonts (`tom-thumb`, `4x6-legacy`) have accented capitals, but an accent on a flattened letter doesn't read (their `Ó` looks like `6`: `ROBIN ARZ6N`), so `plain_letters` takes accents off before drawing; the name page's highlights use it (Joel, 2026-11-12). The workout page's insight frames don't yet.

## Logo (`display/ui/logo_art.py`)

The startup logo (`LogoMaskScreen`) is drawn, not decoded: the red mark (`logo_art.MARK`, cropped from the 32-row art), PELOTON and L E D in the loaded fonts, and a zone bar in `ZONE_COLORS` (also the workout pages' `HR_ZONE_COLORS`). 64 rows stack them; fewer put the mark on the left. `display.logo_path` swaps in an image file (`LogoScreen`). `settings_page/logo.py` draws the settings page's icons from the same art (inline SVG for the header and favicon, `/apple-touch-icon.png` served without a PIN), so `logo_art` must stay import-free. `scripts/render_logo.py` regenerates `docs/logo.png` and the README's startup screenshot. `prepared_logos/` and the `prepare_image`/`postprocess_logos` scripts are only for `logo_path` images.

## Streak flame (`display/ui/streak_screen.py`)

Other animated screens follow the journey page's pattern: `animated = True`, `atomic_frames = True` (drawn on a frame canvas and swapped in, so no flicker), `frame_seconds = 0.05`, `elapsed` zeroed in `on_enter` and advanced by `update(dt)`, an `INTRO_SECONDS` after which the frame is the static page (previews and screenshots draw it there). The challenges page does this for its ring / bar fill and number count-up (`docs/dev/ROTATION.md`).

The streak page and the streak reminder share the 12x16 flame through the `FlickeringFlame` mixin (`animated`, `atomic_frames`, 20 fps via `frame_seconds`). It is drawn, not stored: `flame_pixels(t)` unions three teardrop tongues (`FLAME_LOBES`: the middle one and two at the shoulders), each with its own tip height and lean from smooth value noise, eats into their edges with turbulence that rises over time, and colours each pixel by heat on `FLAME_RAMP` (deep-red rim to a pale-yellow core low in the middle). Sometimes a spark rises beside the tongues (`SPARK_SECONDS`). The bulb stays put, so it burns without wobbling, and every pixel stays in the 12x16 box, so the layouts' fit checks hold. It's a pure function of time: the same `t` always draws the same flame, which the tests and screenshots rely on. About 0.5 ms a frame on a Mac, so roughly 10 ms on a Pi Zero 2 W.

History (2026-11-14, Joel): four hand-drawn frames swapped at 8 fps came first (#112); on the board they read as jumps, not flicker, so they were replaced by this. `scripts/render_streaks.py` draws the README's `streaks.png` and `streak-risk.png` at `FLAME_SECONDS` (a moment with all three tongues up; `render_rotation.frame_times` uses it too); until then they were drawn by hand. Redraw them after any change to the flame or either page.

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
