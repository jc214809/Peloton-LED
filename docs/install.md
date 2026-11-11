# Installation Guide

This guide covers every supported way to install and run Peloton LED: a local
desktop emulator for development, and a managed Raspberry Pi installation for
a physical panel. See the [main README](../README.md) for how the dashboard
behaves once it's running; this document is only about getting it installed.

## Contents

- [Requirements](#requirements)
- [Desktop / emulator install](#desktop--emulator-install)
- [Getting a Peloton token](#getting-a-peloton-token)
- [Raspberry Pi managed install](#raspberry-pi-managed-install)
- [Installer options reference](#installer-options-reference)
- [Settings page](#settings-page)
- [Upgrading](#upgrading)
  - [Updating with `peloton-update`](#updating-with-peloton-update)
- [Uninstalling](#uninstalling)
- [Two users on one board](#two-users-on-one-board)
- [Troubleshooting](#troubleshooting)

## Requirements

- Python 3.10+ (development and clean-install checks currently use Python
  3.14 on macOS).
- For a physical panel: a Raspberry Pi running Linux with `systemd`, and an
  RGB LED matrix wired per the
  [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix)
  documentation.
- No panel is required for local development — the browser-based emulator
  runs on any desktop OS.

`RGBMatrixEmulator` is pinned to the verified `0.15.2` release. `0.19.0`
failed canvas initialization during clean-install testing, so don't bump it
without re-verifying.

## Desktop / emulator install

```bash
git clone https://github.com/jc214809/Peloton-LED.git
cd Peloton-LED
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp config.json-example config.json
# Runs in the foreground at http://localhost:8888 — Ctrl+C to stop
python peloton_led.py --emulated
```

This starts a browser-based emulator at `http://localhost:8888` showing a
64×64 panel with no Peloton data (the dashboard will show a login-needed
state until you add a token — see below). Emulator-only settings, such as
window size and pixel style, live in `emulator_config.json`, not
`config.json`.

To try the dashboard without any Peloton account at all, use demo mode
(synthetic data, no network calls):

```bash
python peloton_led.py --emulated --demo --cycles 1
```

### Every `peloton_led.py` command-line flag

Flags override the matching `config.json` value for that run only; they
don't change the file. Everything under `display` in `config.json` is
documented in the [main README's configuration table](../README.md#configuration).

| Flag | Default | Meaning |
|---|---|---|
| `--config PATH` | `config` | Config file base name/path (e.g. `config/rockies.config`) |
| `--emulated` | off | Force the browser emulator instead of the native/hardware matrix |
| `--cookies PATH` | `cookies.txt` | Path to the Peloton bearer-token file |
| `--username NAME` | none | Override the displayed username for this run |
| `--display-duration SECONDS` | `display.duration` | Seconds per username screen |
| `--refresh-interval SECONDS` | `display.refresh_interval` (300) | Background data refresh interval |
| `--demo` | off | Use synthetic data; no network calls or credentials required |
| `--demo-login-needed` | off | Preview the login-needed indicator (requires `--demo`) |
| `--cycles N` | `0` | Stop after N full screen rotations; `0` runs continuously |
| `--drop-privileges` | off | Force the matrix driver to drop root privileges after GPIO setup |

Matrix hardware settings (passed straight through to `rpi-rgb-led-matrix` /
`RGBMatrixEmulator`). Set them once in the top-level `"matrix"` section of
`config.json`, using the key in the second column; a flag overrides the
config value for that run. The panel can't report its own size, so a 64×32
board needs `"rows": 32`.

On a Pi installed with `peloton-install.sh`, `gpio_mapping` must be set in
`config.json`: the service passes no `--led-*` flags, and the installer stops
before changing anything if the config the service reads leaves it out. Use
`"adafruit-hat"` for an Adafruit HAT or Bonnet, or `"adafruit-hat-pwm"` if
you've soldered the GPIO4–GPIO18 jumper (the PWM mod), which reduces
flicker. Fresh installs start with `"adafruit-hat"`.

`adafruit-hat-pwm` drives the panel with the Pi's PWM hardware, which the
onboard audio also uses, so the audio has to be off or the display exits
with a `snd_bcm2835` message. When the config says `adafruit-hat-pwm` and the
audio is loaded, the installer explains this and asks before turning it off
(it backs up the boot config to `config.txt.peloton-led.bak`, sets
`dtparam=audio=off`, blacklists `snd_bcm2835`, and unloads it, or tells you
to reboot if it can't). Answer no, or run it without a terminal, and it
stops with nothing changed. `lsmod | grep snd_bcm2835` printing nothing means
the audio is off.

```json
"matrix": {"rows": 32, "cols": 64, "gpio_mapping": "adafruit-hat", "slowdown_gpio": 2}
```

| Flag | `matrix` key | Default | Meaning |
|---|---|---|---|
| `--led-rows N` | `rows` | `64` | Panel height in pixels: `32` or `64` |
| `--led-cols N` | `cols` | `64` | Panel width in pixels |
| `--led-chain N` | `chain` | `1` | Number of daisy-chained boards |
| `--led-parallel N` | `parallel` | `1` | Parallel chains (Plus-models/RPi2 only), `1`-`3` |
| `--led-pwm-bits N` | `pwm_bits` | `11` | Bits used for PWM, `1`-`11` |
| `--led-brightness N` | `brightness` | `100` | Brightness, `1`-`100` |
| `--led-gpio-mapping NAME` | `gpio_mapping` | `null` | `regular`, `adafruit-hat`, or `adafruit-hat-pwm` |
| `--led-scan-mode N` | `scan_mode` | `1` | `0` progressive, `1` interlaced |
| `--led-pwm-lsb-nanoseconds N` | `pwm_lsb_nanoseconds` | `130` | Base on-time unit for the lowest PWM bit |
| `--led-show-refresh` | `show_refresh` | `false` | Print the panel's live refresh rate |
| `--led-slowdown-gpio N` | `slowdown_gpio` | `null` (driver default) | Slow down GPIO writes, `0`-`4` |
| `--led-no-hardware-pulse` | `no_hardware_pulse` | `false` | Disable hardware pin-pulse generation |
| `--led-rgb-sequence STR` | `rgb_sequence` | `RGB` | Reorder color channels if wired differently |
| `--led-pixel-mapper STR` | `pixel_mapper` | `""` | e.g. `"Rotate:90"` |
| `--led-row-addr-type N` | `row_addr_type` | `0` | `0` default, `1` AB-addressed, `2` direct row select, `3` ABC-addressed |
| `--led-multiplexing N` | `multiplexing` | `0` | `0`-`8`; see `--help` for the full mapping |
| `--led-limit-refresh HZ` | `limit_refresh` | `0` | Cap refresh rate; `0` = no limit |
| `--led-pwm-dither-bits N` | `pwm_dither_bits` | `0` | Time-dither the lower PWM bits |

Run `python peloton_led.py --help` at any time for the authoritative list —
this table mirrors it but the `--help` output wins if they ever diverge.

## Getting a Peloton token

Despite its name, `cookies.txt` holds a bearer access token, not a cookie
export. There is no username/password login at runtime — only this token
file. You have two ways to produce it:

**Option A — automated (recommended for local dev):** install the login
helper once, then run it whenever the token needs refreshing:

```bash
python -m pip install -r requirements-auth.txt
python -m playwright install chromium
python scripts/refresh_cookies.py --no-headless
```

The helper reads `PELOTON_EMAIL` / `PELOTON_PASSWORD` from the environment
(or `.env` — copy `.env.example` to `.env` and fill in real values; it's
gitignored), then falls back to `auth.email` / `auth.password` in
`config.json`, then prompts interactively. It verifies the new token against
the Peloton API before atomically replacing the existing file, sets
owner-only file permissions, and never prints the token. Drop `--no-headless`
for a background login once you've confirmed it works.

The login also saves Peloton's refresh token beside the access token, as
`<token stem>.refresh.json` (e.g. `cookies-joel.refresh.json`, owner-only,
gitignored). `--ensure` uses it to get a new access token over plain HTTPS,
with no browser. Refresh tokens rotate on every use and the old one stops
working, so **a refresh file belongs to one machine**: copying it to a
second machine breaks renewal on both.

To just check whether the current token is still valid without logging in
again:

```bash
python scripts/refresh_cookies.py --verify-only
```

Full `refresh_cookies.py` flags:

| Flag | Default | Meaning |
|---|---|---|
| `--cookies PATH` | `cookies.txt` | Output token file path |
| `--config PATH` | `config.json` | Config file to read `auth.*` fallback credentials from |
| `--verify-only` | off | Skip login; just verify the existing token |
| `--ensure` | off | Only log in if the token is missing/near expiry/rejected (used by the Pi renewal timer) |
| `--renew-before-hours N` | `12` | With `--ensure`, renew when fewer than N hours remain before expiry |
| `--all-users` | off | Refresh every user listed in a dual-user `config.json` instead of one `--cookies` path |
| `--seed-dir DIR` | off | Log in every rider in `--config` and write a fresh token + refresh-token pair per rider into `DIR`, named for the board, then print the commands to install them (see [Seeding a board](#seeding-a-board-from-another-computer---no-browser)) |
| `--status` | off | Show each token's expiry and whether it has a refresh token, without network calls |
| `--no-headless` | off | Show the browser window during login (useful for first-time setup or debugging) |

**Option B — manual:** log in to onepeloton.com in your browser, extract the
bearer token from a request's `Authorization` header using your browser's
network inspector, and paste it into `cookies.txt` yourself. This is only
worth doing if you can't run a local Chromium (Playwright) for some reason —
Option A is easier and is what the Pi installer automates.

An **amber padlock in the bottom-right corner** of the dashboard means the
token is missing, empty, unreadable, or was rejected with HTTP 401. Replace
the token file and the running display picks it up automatically — it polls
for file changes roughly once per second.

## Raspberry Pi managed install

For a permanent installation driving a physical panel, clone the repo on
the Pi itself and run the installer from the checkout:

```bash
git clone https://github.com/jc214809/Peloton-LED.git
cd Peloton-LED
sudo ./peloton-install.sh                    # manual: you start/stop the display
sudo ./peloton-install.sh --start-at-boot    # dedicated board: runs at boot
```

By default the display is **not** started at boot or during install; start it
with `sudo systemctl start peloton-led` (see [Manual mode](#manual-mode-the-default)).
Pass `--start-at-boot` if the Pi drives nothing else and should show Peloton
whenever it's on.

The installer also picks how tokens are renewed, so most boards need no
token flag. A 64-bit board with 768 MB or more of RAM gets
[automatic renewal with Chromium](#automatic-token-renewal---auto-token); a
32-bit board, or one with under 768 MB (a Pi Zero 2 W, say), gets
[`--no-browser`](#seeding-a-board-from-another-computer---no-browser). That
covers fresh installs and upgrades of boards that had no renewal. A board
that already renews tokens keeps its mode (saved in
`/etc/peloton-led/token-mode`, or read off an older install's timer,
drop-ins, and venv). Renewal stays off only if you pass `--no-auto-token`,
which is remembered like the other token flags. The installer's summary
prints the mode and where it came from (`detected`, `kept`, or `flag`).

This is safe to re-run — it's also how you [upgrade](#upgrading) later.

**On first install**, since there's no `/etc/peloton-led/config.json` yet,
the installer stops and asks you interactively who's using the board:

```
Let's set up who's using this board.
Rider name (leave blank to finish, at least one required): Joel
  Peloton email for Joel: joel@example.com
  Peloton password for Joel: ********
Rider name (leave blank to finish): Jen
  Peloton email for Jen: jen@example.com
  Peloton password for Jen: ********
Rider name (leave blank to finish):
Configured 2 rider(s): Joel, Jen
```

Answer with just one rider for a single-user board, or two or more for
riders sharing one panel — there's no separate "dual-user mode" to opt into,
it's simply how many names you give it. This single prompt writes both
`/etc/peloton-led/config.json` (with a `users` array only if you added more
than one rider) and `/etc/peloton-led/auth.env` (the credentials, used for
[automatic token renewal](#automatic-token-renewal---auto-token)), so
there's nothing left to configure by hand afterward. This step needs a real
terminal (SSH is fine; a non-interactive script is not) — the installer
exits with an error rather than hanging if it can't prompt you.

What the full run does, in order:

1. Installs required `apt` packages (`python3`, build tools, `cmake`,
   `libopenjp2-7`, and `chromium` when renewal uses a browser (`--auto-token`,
   not `--no-browser`). Skippable with
   `--skip-packages` if you manage packages yourself.
2. Creates a dedicated, unprivileged `peloton-led` system account (home
   `/var/lib/peloton-led`, shell `/usr/sbin/nologin`), and adds it to the
   `gpio` and `video` groups if they exist. The display service starts as
   root only long enough for the matrix driver to map the panel's hardware
   registers (`/dev/mem`), then switches to `peloton-led` before it reads
   any token or cache; it refuses to run if that switch fails. The token
   renewal service runs as `peloton-led` throughout.
3. Copies the application into `/opt/peloton-led`, owned by `root` so the
   service account can't modify its own code.
4. Prompts for riders and writes `/etc/peloton-led/config.json` +
   `/etc/peloton-led/auth.env` as described above — **only if neither file
   exists yet, or `--reconfigure` was passed**. Otherwise both are left
   untouched, so re-running the installer after a `git pull` won't clobber
   your settings.
5. Copies any existing local `cookies.txt` / `cookies-*.txt` token files
   and `cookies*.refresh.json` refresh tokens into `/var/lib/peloton-led/`,
   but never overwrites one that's already there.
6. Creates a Python virtualenv under `/opt/peloton-led/venv` and installs
   `requirements.txt` into it.
7. Builds and installs the native `rpi-rgb-led-matrix` Python bindings from
   source (unless `--skip-matrix`), cloning
   `github.com/hzeller/rpi-rgb-led-matrix` into
   `/opt/peloton-led/vendor/rpi-rgb-led-matrix` at the ref given by
   `--driver` (default: `master`).
8. Installs `peloton-led.service` (and, with automatic renewal,
   `peloton-token-refresh.timer` / `.service`). With `--start-at-boot` it
   enables and starts them, unless `--no-start` is given. In manual mode it
   starts nothing, but a display that was running when the install began is
   restarted, so it picks up the new code.

### Changing riders later (`--reconfigure`)

```bash
sudo ./peloton-install.sh --reconfigure
```

Re-runs the interactive rider prompt from scratch and overwrites both
`/etc/peloton-led/config.json` and `/etc/peloton-led/auth.env` with your new
answers — for example, to add a second rider to a single-user board, remove
a rider, or fix a mistyped password. Everything else (tokens already on
disk, cached history, PR/milestone state) is untouched, though a renamed or
removed rider's old token/cache files are simply orphaned on disk rather
than deleted — safe to remove by hand from `/var/lib/peloton-led/` if you
want to reclaim the space.

### Directory layout

| Purpose | Path |
|---|---|
| Application code | `/opt/peloton-led` |
| Configuration | `config.json` in your checkout (e.g. `~/Peloton-LED/config.json`), seen by the services as `/etc/peloton-led/config.json`; without one, the `/etc` file itself |
| Login environment (credentials) | `/etc/peloton-led/auth.env` |
| Access token(s) | `/var/lib/peloton-led/cookies*.txt` |
| Refresh token(s) | `/var/lib/peloton-led/cookies*.refresh.json` |
| Persistent snapshot/cache | `/var/lib/peloton-led/dashboard-cache*.json` |
| Workout log (one per rider, about 1 MB; safe to delete, it re-downloads) | `/var/lib/peloton-led/dashboard-cache*.workouts.json` |

The display runs as `peloton-led.service`: it starts when you start it (or
at boot with `--start-at-boot`), restarts on failure, and is granted only the GPIO-related capabilities the matrix driver
needs — it does not run as root. The installer validates configuration and
the systemd units before enabling the service, so a bad config fails the
install rather than producing a crash-looping service.

### Automatic token renewal (`--auto-token`)

```bash
sudo ./peloton-install.sh --auto-token
```

The default on a 64-bit board with 768 MB or more of RAM that doesn't
already renew tokens some other way.
It keeps your Peloton token fresh without you re-running the login helper.
Pass the flag to switch an existing board to it, or
`--no-auto-token` to turn renewal off. It:

- Installs the Pi distribution's Chromium build, for logins when a rider has
  no refresh token yet (skip it with `--no-browser`, below).
- Uses the credentials already written to `/etc/peloton-led/auth.env`
  (root-readable, mode `0600`) during the rider setup prompt above. If that
  file is somehow missing, the installer warns and tells you to re-run with
  `--reconfigure` rather than silently doing nothing.
- Enables `peloton-token-refresh.timer`, which runs roughly hourly with a
  randomized delay and invokes `refresh_cookies.py --ensure`, which:
  1. Verifies the existing token against `/api/me`.
  2. Reads the token's real JWT expiry and does nothing if more than 12
     hours remain — no browser is opened on the common case.
  3. Renews only within the final 12 hours of expiry, or immediately after
     an HTTP 401. With a saved refresh token it asks Peloton's token
     endpoint for a new one and saves the rotated refresh token first;
     without one it starts a headless Chromium login, which saves a refresh
     token for next time.
  4. Never opens a browser for DNS failures, timeouts, rate limits, or
     Peloton server errors — those are treated as transient and retried
     next hour instead.
  5. When Peloton rejects a saved refresh token (`invalid_grant`), tries
     one headless browser login if this board has Chromium and the rider's
     credentials, then waits a day before trying again, so a board too slow
     for Chromium doesn't fail that login every hour. A `--no-browser` board
     never tries; the log says to seed it again (below).
  6. Verifies the replacement token before atomically swapping it in.
  7. Exits nonzero on failure, leaving the previous token untouched.
- Optionally sends a Pushover alert when renewal keeps failing: add
  `PUSHOVER_APP_TOKEN` and `PUSHOVER_USER_KEY` to `/etc/peloton-led/auth.env`
  (see the README's token section for when alerts fire).

The running dashboard notices the token file change on its own (no service
restart needed). If Peloton ever introduces CAPTCHA, MFA, or another
interactive step, the renewal fails safely, keeps the old token, and the
dashboard's amber padlock signals that a manual login is needed. The padlock appears as soon as the renewal job knows a fresh login is needed (for example `invalid_grant`), while the old token still works and data keeps updating, and it clears when renewal succeeds or the board is re-seeded.

### Seeding a board from another computer (`--no-browser`)

Chromium isn't available for 32-bit Raspberry Pi OS and is too slow on 512 MB
boards like the Pi Zero 2 W. The installer picks this mode itself on a fresh
install when it finds a 32-bit userland or under 768 MB of RAM. To pick it
yourself, for example to move an existing board to it:

```bash
sudo ./peloton-install.sh --no-browser   # implies --auto-token
```

That skips Chromium and Playwright (and uninstalls Playwright on an upgrade)
and renews only with refresh tokens. Give the board its own login from a
computer that can run the login helper, using a `config.json` with the
board's riders. One command does it all:

```bash
scripts/seed_board.sh admin@pelotonpi.local          # --config PATH for another config
```

It logs each rider in on this computer, copies each token + refresh-token
pair to the board, installs them into `/var/lib/peloton-led/` (asking for
the board's sudo password if it needs one), prints `--status`, and deletes
every other copy on both machines, even when a step fails. The display picks
up the new tokens within seconds. Seed each board separately. When a rider
still has no token at the end of an install (always the case on a first
`--no-browser` install), the installer ends with a **NEXT STEP** showing
this command with the board's user and hostname filled in.

To do it by hand instead, `python scripts/refresh_cookies.py --seed-dir
~/peloton-seed-pelotonpi` writes the files and prints the `scp` and `sudo
install` commands; delete the seed folder afterward. Repeat this if the renewal log reports
`invalid_grant` (for example after a Peloton password change). Check which
riders have refresh tokens with:

```bash
sudo -u peloton-led /opt/peloton-led/venv/bin/python /opt/peloton-led/scripts/refresh_cookies.py \
    --status --all-users --config /etc/peloton-led/config.json --cookies /var/lib/peloton-led/cookies.txt
```

### Manual mode (the default)

Unless you pass `--start-at-boot`, nothing is enabled at boot and nothing is
started during install. This suits a Pi that already runs another display
(say, a baseball scoreboard) that should stay the boot default:

```bash
sudo ./peloton-install.sh
```

Only one program can drive the matrix at a time, so swap them by hand:

```bash
sudo systemctl stop <other-display>.service && sudo systemctl start peloton-led
sudo systemctl stop peloton-led && sudo systemctl start <other-display>.service
```

With automatic renewal, token renewal follows the display instead of running
all the time: starting `peloton-led` runs one token check (logging in if the
token expired while it was off) and starts the hourly timer, and stopping
`peloton-led` stops the timer.

On an **upgrade**, a board that already starts at boot keeps doing so when
you pass neither flag (so it doesn't go dark on its next reboot), and the
installer says so. Pass `--manual` to switch such a board to manual, or
`--start-at-boot` to switch a manual board to starting at boot. If the display
is running when you upgrade, the installer restarts it on the new code. If it's
stopped, the installer leaves it stopped.

## Installer options reference

```
sudo ./peloton-install.sh [options]
```

| Option | Effect |
|---|---|
| `--auto-token` | Install Chromium and enable hourly token verification/renewal (see above). Picked automatically on a fresh 64-bit board with 768 MB+ |
| `--no-browser` | Renew only with seeded refresh tokens; no Chromium or Playwright. Implies `--auto-token` (see [above](#seeding-a-board-from-another-computer---no-browser)). Picked automatically on a fresh 32-bit or under-768 MB board |
| `--no-auto-token` | No scheduled token renewal; disables the timer on a board that had it. The only way renewal stays off: without it the installer turns renewal on |
| `--reconfigure` | Re-run the interactive rider setup, overwriting `config.json` and `auth.env` (see [above](#changing-riders-later---reconfigure)) |
| `--skip-matrix` | Skip building/installing the native `rpi-rgb-led-matrix` bindings — use when they're already installed, or when preparing a Pi with no panel attached yet |
| `--skip-packages` | Skip the `apt-get install` step — use when you manage system packages yourself or they're already present |
| `--skip-requirements` | Skip `pip install` of `requirements.txt` and `requirements-auth.txt` — what the [updater](#updating-with-peloton-update) passes when neither changed |
| `--driver REF` | Git branch, tag, or commit of `rpi-rgb-led-matrix` to build (default: `master`) |
| `--manual` | The default: never start at boot or during install; you start/stop the display yourself (see [above](#manual-mode-the-default)). Needed on upgrade only to switch a board that currently starts at boot |
| `--start-at-boot` | Enable the display at boot and start it now — for a Pi that drives nothing else |
| `--no-settings-page` | Turn off the [settings page](#settings-page) (on by default). Remembered: upgrades keep it off until `--settings-page` |
| `--settings-page` | Turn the settings page back on |
| `--no-start` | With `--start-at-boot`: enable the units but don't start them yet — useful when staging a config before going live. A display that is already running is still restarted on the new code |
| `-h`, `--help` | Print usage and exit |

### Editing the config

Edit `config.json` in the checkout you ran the installer from, then restart:

```bash
nano ~/Peloton-LED/config.json
sudo systemctl restart peloton-led
```

The services run sandboxed and can't see home directories, so the installer
maps that file read-only onto `/etc/peloton-led/config.json` inside both
services (`BindReadOnlyPaths=` in `project-config.conf` under
`/etc/systemd/system/peloton-led.service.d/` and
`peloton-token-refresh.service.d/`). There's no copy to keep in sync; the
file in your checkout is the one that runs.

- The file must be readable by everyone (`chmod 644 ~/Peloton-LED/config.json`,
  the default for a new file). It only names environment variables, never
  passwords.
- Use the Pi's paths: each rider's `token_path` and `cache_path`, and
  `display.cache_path`, under `/var/lib/peloton-led/`. Relative paths would
  point inside `/etc/peloton-led`, where the service can't write.
- Each rider's `email_env`/`password_env` must match the names in
  `/etc/peloton-led/auth.env` (`sudo cut -d= -f1 /etc/peloton-led/auth.env`
  lists them), or automatic token renewal can't log in.
- An invalid file stops the service from starting; the reason is in
  `journalctl -u peloton-led.service -n 50`. Fix the file and restart.
- With no `config.json` in the checkout, the services use
  `/etc/peloton-led/config.json` as before.

`config.json` isn't tracked by git, so `git pull` never overwrites it. Start
from `config.json-example`. Re-run the installer after moving the checkout,
since the mapping records its path.

Most settings can also be changed from a browser on the
[settings page](#settings-page).

## Settings page

The installer runs a small web page on every board, `peloton-settings.service`,
at **http://&lt;board&gt;.local:8080** (the installer prints the address). It edits
the live `config.json` from a phone or laptop:

- **General**: text colour, and compact workout pages (64x32 only)
- **Rotation**: which screens show, in what order, and each one's seconds
- **Workout insights**: the switch for the comparisons after your latest
  workout (off by default), and how many earlier workouts each rider has on
  the board to compare with. That history is copied from the Mac once with
  `scripts/push_workout_rows.sh user@board`; until then the card says "Not
  copied yet" and that rider gets no insights
- **Timing**: default page time, workout stat time, logo, how often to check Peloton
- **Goals**: everyone's weekly goals, each rider's name and own goals, and
  the streak reminder day
- **Milestones**: the total workouts to celebrate (a list, then every N), the
  Next milestone countdown (how close, how many pages), and each rider's own
  list; each discipline's (25, 50, 100, then every 100) needs no setting
- **Schedules**: time zone, day and night brightness, quiet hours
- **Panel**: size, brightness, GPIO mapping, rotation, slowdown, PWM timing;
  the rest of the driver settings under **Advanced**, with debug logging and
  the fallback name

- **Updates** (top of the page): what's installed, a check for a newer
  Release or Beta with what's in it, **Update now**, and **Roll back** (see
  [Updating with `peloton-update`](#updating-with-peloton-update), which it
  runs for you)
- **Logins**: token renewal's status, each rider's login health, renewal on
  demand, and write-only credentials (below)
- **Pushover alerts**: whether alerts are on, a test alert, and the write-only
  Pushover keys

Riders' names, token and cache paths, login variable names and the journey
route aren't on the page and are kept as they are.

**Logins.** At the top, renewal's status as labelled rows:

- **Renewal**: running now, or whether the last run worked. A run that's going
  updates there by itself until it finishes.
- **Last run**, and **Interval**: every hour (on a manual board, only while the
  display is on). Each check renews a token only once it's within 12 hours of
  expiring; otherwise it does nothing.
- **Next check**, and **Next renewal**: when the soonest rider's token will
  actually be renewed, at the first check within 12 hours of it expiring.
  Times are approximate, since a check can start up to 10 minutes late.
- **Failures** in a row, if any, and the board's renewal **Mode**.

Then a card per rider. It stays closed to one line (name, when their token
renews, and a green *Working* pill) while their login works. It opens by
itself when it needs you: *No working token*, *Expired* or *Needs login*, with
the reason renewal gave. On a board without a browser, it also shows the
`scripts/seed_board.sh user@board.local` command to run from your computer.
Open, it lists the token's expiry, when it renews, the refresh chain's age and
renewals, the last browser-login try, and whether an email and password are
saved (never what they are).

- *Renew now* starts `peloton-token-refresh.service` straight away (the same
  run the hourly timer does, with its once-a-day limit on browser logins);
  the status above follows it.
- Each rider has a card: closed to one line (name, when their token renews,
  and a pill saying Working) while their login works, and open by itself when
  it needs you. Click a rider's *Email & password* row (*Change*) to set their
  Peloton email or password; *Save* writes just that rider's to
  `/etc/peloton-led/auth.env`, and *Cancel* clears and closes it. The
  Pushover keys are set the same way from their own card, where *Send a test
  alert* sends a Pushover message, at most once a minute. Fields are always empty; blank keeps
  what's saved; nothing saved is ever sent back to a browser or written to a
  log (the log names only what changed). The file stays root-only (600) and
  every other line in it is kept; no backup copy is made. Renewal uses the new
  values from its next run. Passwords only matter on a board with a browser
  (`--auto-token`); a `--no-browser` board renews from seeded tokens.
- Changing logins always takes the PIN, even on the Wi-Fi setup hotspot.
- The page is plain HTTP: anything typed crosses your network unencrypted, so
  only change logins on your own Wi-Fi.

**Signing in.** Press *Show a PIN on the board*: a four-digit PIN appears on
the panel for two minutes; type it in and that browser stays signed in for an
hour. A PIN allows five guesses, and a new one comes only after the last runs
out. With `PUSHOVER_APP_TOKEN` and `PUSHOVER_USER_KEY` in `auth.env`, *Send the
PIN to my phone* sends it by Pushover too (at most once a minute). In manual
mode the display may not be running, so the PIN can't show on the panel; the
page says so (use Pushover, or `sudo systemctl start peloton-led`).

**Saving** checks the whole config with the display's own rules, keeps the old
file as `config.json.bak` beside it, writes the new one in one step with the
old owner and mode, and restarts the display if it's running. A manual-mode
board that's off uses the new settings the next time it starts. Because the
settings page is its own service, a config that stops the display can still
be fixed here.

**Wi-Fi setup.** On a board set up with LightningLane-Live-LED's
`board-setup.sh`, comitup opens an open `<board>-setup` hotspot when no known
Wi-Fi is in range. While it's up, the display shows *Wi-Fi setup / Join
<board>-setup*, then *Settings / Browse to 10.41.0.1:8080*, until the board is
back on a network; comitup's own page (http://10.41.0.1) picks the network.
Anyone on the hotspot gets the settings page with no PIN (they're in the room).

Which file it edits: the checkout's `config.json` when the installer found one
(a `project-config.conf` drop-in under
`/etc/systemd/system/peloton-settings.service.d/` gives its path and makes that
folder writable to this service only), else `/etc/peloton-led/config.json`.
It runs as root, so it can write the file whoever owns it, edit `auth.env`, read the tokens in
`/var/lib/peloton-led` and restart `peloton-led.service` and start token renewal; the PIN goes in `/run/peloton-led-settings/pin`
(group `peloton-led`, gone when the service stops). Logs:
`journalctl -u peloton-settings.service`. Turn it off with
`--no-settings-page`.

## Upgrading

Pull the latest code into your checkout, then re-run the installer. You
don't need any flags: it keeps the board's token mode (turning renewal on
for a board that had none), keeps its boot or manual setting, and restarts
the display if it's running:

```bash
git pull
sudo ./peloton-install.sh
```

Boards installed before the display service stopped passing
`--led-gpio-mapping adafruit-hat` need `"gpio_mapping"` in their config's
`"matrix"` section first ([above](#every-peloton_ledpy-command-line-flag)); the installer
says so and stops, with nothing changed, if it's missing.

This upgrades the application code in `/opt/peloton-led` while preserving
configuration, tokens, credentials, cached display data, and PR/milestone
state — none of that lives in `/opt/peloton-led`, so it's never touched.

### Updating with `peloton-update`

Once a board has a version with the updater (the first release, v0.1.0, or
any Beta after it), it can update itself and undo a bad update. The installer
puts `peloton-update` and `peloton-rollback` in `/usr/local/bin`; both run the
updater from the checkout you installed from.

```bash
peloton-update check                        # what an update would install; changes nothing
sudo peloton-update update                  # the newest release
sudo peloton-update update --channel beta   # develop-beta's tip, once its CI has passed
sudo peloton-update status                  # what's installed and how the last update went
sudo peloton-rollback                       # undo the last update, config.json included
```

There are two channels. **Releases** (the default) are the `vX.Y.0` tags made
when `develop-beta` merges into `main`; the updater never installs an older
one than you have. **Beta** is `develop-beta`'s newest commit, installed only
once its CI has passed; every pull request merged into `develop-beta` is
tagged `vX.Y.N-beta`.

An update checks first: at least 300 MB free, no under-voltage or throttling
right now, no edits in the checkout (`git status` clean, untracked files like
`config.json` don't count), and GitHub reachable. It then saves a rollback
point in `/var/lib/peloton-update` (the commit, `pip freeze`, a copy of the
live `config.json`), checks out the new version, and re-runs its installer with
`--skip-packages --skip-matrix` (and `--skip-requirements` unless a
requirements file changed). Your board's mode flags are kept, as in a manual
upgrade.

Within 5 minutes the new version must be healthy: a display that was running
before the update must finish a screen (it writes
`/run/peloton-led/health` after each one) without systemd restarting it, and
the settings page, if it's on, must answer. A manual-mode board whose display
was off stays off; only the settings page is checked. If the check fails, or any
step errors, the updater rolls back to the saved commit, packages and
`config.json`, and sends a Pushover alert if `auth.env` has the keys. If the
power goes out mid-update, `peloton-update-recover.service` rolls it back at
the next boot.

The settings page's **Updates** card does the same from a browser. When the
page loads it checks the channel you're on (at most once every 10 minutes:
GitHub allows 60 unauthenticated calls an hour). It lists the pull requests
an update brings with their release notes, or a Beta's tests while they run.
**Update now** and **Roll back** run as their own `peloton-update` unit
(`journalctl -u peloton-update` shows how it went), and the card follows each
step. Saving settings waits until the update is done, because a rollback puts
`config.json` back as it was.

After an update the checkout is on a detached commit; `git switch main`
(or `develop-beta`) before pulling by hand again.

## Uninstalling

There's no automated uninstaller. To remove a Pi installation by hand:

```bash
sudo systemctl disable --now peloton-led.service peloton-token-refresh.timer peloton-token-refresh.service \
    peloton-settings.service peloton-update-recover.service
sudo rm -rf /opt/peloton-led /etc/peloton-led /var/lib/peloton-led /var/lib/peloton-update
sudo rm -rf /etc/systemd/system/peloton-led.service /etc/systemd/system/peloton-token-refresh.{service,timer} \
    /etc/systemd/system/peloton-settings.service /etc/systemd/system/peloton-update-recover.service \
    /etc/systemd/system/peloton-*.d
sudo rm -f /usr/local/bin/peloton-update /usr/local/bin/peloton-rollback
sudo systemctl daemon-reload
sudo userdel peloton-led   # optional: removes the dedicated service account
```

Back up `/etc/peloton-led/config.json` and `/var/lib/peloton-led/` first if
you might reinstall later — that's your settings, tokens, and history cache.

## Two users on one board

Two Peloton accounts (e.g. two riders sharing one panel) are supported. **On
the Pi**, just answer the installer's rider prompt with more than one name
(see above) — that's the entire setup. **For local desktop development**,
see the [dual-user setup and operations guide](dual-users.md): copy
`config.dual-users-example.json`, list each rider with a unique token path,
and create each rider's token with
`python scripts/refresh_cookies.py --cookies cookies-<name>.txt`.

## Troubleshooting

- **`This installer must run on Linux.` / `Run this installer with sudo.`**
  — the installer intentionally refuses to run anywhere but a Linux host as
  root; it's meant for the Pi itself, not macOS/dev machines.
- **`Run the installer from the project checkout.`** — run
  `./peloton-install.sh` from inside the cloned repository, not from a copy
  of just the script.
- **Amber padlock after install** — the token is missing or was rejected;
  see [Getting a Peloton token](#getting-a-peloton-token). Check
  `journalctl -u peloton-token-refresh.service -n 100` if `--auto-token` is
  enabled.
- **Service won't start** — `sudo systemctl status peloton-led.service` and
  `journalctl -u peloton-led.service -n 100` for the actual error;
  configuration is validated at startup, so a bad `config.json` value will
  show up there before the display initializes.
- **Panel blank with `adafruit-hat-pwm`, service restarting** — the PWM
  jumper mapping needs two things, and each has its own error in
  `journalctl -u peloton-led.service -n 30`:
  - `Need root. You are configured to use the hardware pulse generator` —
    the driver couldn't open `/dev/mem`. The managed service starts as root
    for this and then drops to `peloton-led`; re-run
    `sudo ./peloton-install.sh` if the board's `peloton-led.service` predates
    that (`systemctl cat peloton-led` shows `User=root` once it's current).
    Don't work around it with `--led-no-hardware-pulse`: that turns off the
    very pulse the jumper is for.
  - `snd_bcm2835: found that the Pi sound module is loaded` — the onboard
    audio shares the PWM hardware. Re-running `sudo ./peloton-install.sh`
    offers to turn it off; to do it by hand, set `dtparam=audio=off` in
    `/boot/firmware/config.txt`, add `blacklist snd_bcm2835` to
    `/etc/modprobe.d/blacklist-rgb-matrix.conf`, and reboot;
    `lsmod | grep snd_bcm2835` should then print nothing.

  The jumper itself is rarely the problem: these errors appear before the
  panel is driven at all. Set `"gpio_mapping": "adafruit-hat"` to get the
  panel back while you fix them.
- **Wrong number of riders / stuck on an old config** — if your checkout has a
  `config.json`, that's the one the services run (see
  [Editing the config](#editing-the-config)); remember to restart after
  editing it. `systemctl cat peloton-led` shows the `BindReadOnlyPaths=` line
  with the exact path. Without one, `/etc/peloton-led/config.json` and
  `auth.env` are only written on first install; `sudo ./peloton-install.sh
  --reconfigure` redoes the rider prompt (with a checkout `config.json`,
  that file still wins for settings, so `--reconfigure` then only matters
  for `auth.env`).
- **`git pull` doesn't fix a bug you just pulled** — the systemd services run
  code copied into `/opt/peloton-led`, not your `~/Peloton-LED` checkout.
  `git pull` only updates the checkout; re-run `sudo ./peloton-install.sh`
  (no flags needed; it keeps the board's modes) to sync the fix into the
  deployed copy the services actually execute.
- **A specific rider's login times out waiting for the login form** — if
  `journalctl` shows `Could not reach or fill in the login form` or `No
  access token found after login`, `refresh_cookies.py` saves a screenshot
  and the page's HTML next to that rider's token file (e.g.
  `/var/lib/peloton-led/cookies-joel-login-failure.png` and `.html`) so you
  can see what the headless browser was actually looking at — a cookie
  banner, a CAPTCHA, a bot-detection challenge, or Peloton having changed
  the login page. Check that file rather than guessing from the log alone.
- **Diagnostic commands:**
  ```bash
  sudo systemctl status peloton-led.service
  journalctl -u peloton-led.service -n 100
  systemctl list-timers peloton-token-refresh.timer
  sudo systemctl start peloton-token-refresh.service
  sudo systemctl status peloton-token-refresh.service
  journalctl -u peloton-token-refresh.service -n 100
  ```
