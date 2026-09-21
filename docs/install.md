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
- [Upgrading](#upgrading)
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

Matrix hardware flags (passed straight through to `rpi-rgb-led-matrix` /
`RGBMatrixEmulator`; only relevant when driving real hardware or when you
need to emulate a non-default panel shape):

| Flag | Default | Meaning |
|---|---|---|
| `--led-rows N` | `64` | Panel height in pixels: `32` or `64` |
| `--led-cols N` | `64` | Panel width in pixels |
| `--led-chain N` | `1` | Number of daisy-chained boards |
| `--led-parallel N` | `1` | Parallel chains (Plus-models/RPi2 only), `1`-`3` |
| `--led-pwm-bits N` | `11` | Bits used for PWM, `1`-`11` |
| `--led-brightness N` | `100` | Brightness, `1`-`100` |
| `--led-gpio-mapping NAME` | none | `regular`, `adafruit-hat`, or `adafruit-hat-pwm` |
| `--led-scan-mode N` | `1` | `0` progressive, `1` interlaced |
| `--led-pwm-lsb-nanoseconds N` | `130` | Base on-time unit for the lowest PWM bit |
| `--led-show-refresh` | off | Print the panel's live refresh rate |
| `--led-slowdown-gpio N` | `1` | Slow down GPIO writes, `0`-`4` |
| `--led-no-hardware-pulse` | off | Disable hardware pin-pulse generation |
| `--led-rgb-sequence STR` | `RGB` | Reorder color channels if wired differently |
| `--led-pixel-mapper STR` | `""` | e.g. `"Rotate:90"` |
| `--led-row-addr-type N` | `0` | `0` default, `1` AB-addressed, `2` direct row select, `3` ABC-addressed |
| `--led-multiplexing N` | `0` | `0`-`8`; see `--help` for the full mapping |
| `--led-limit-refresh HZ` | `0` | Cap refresh rate; `0` = no limit |
| `--led-pwm-dither-bits N` | `0` | Time-dither the lower PWM bits |

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
sudo ./peloton-install.sh
```

This is safe to re-run — it's also how you [upgrade](#upgrading) later.

What it does, in order:

1. Installs required `apt` packages (`python3`, build tools, `libopenjp2-7`,
   and `chromium` if `--auto-token` is set). Skippable with `--skip-packages`
   if you manage packages yourself.
2. Creates a dedicated, unprivileged `peloton-led` system account (home
   `/var/lib/peloton-led`, shell `/usr/sbin/nologin`), and adds it to the
   `gpio` and `video` groups if they exist.
3. Copies the application into `/opt/peloton-led`, owned by `root` so the
   service account can't modify its own code.
4. Migrates or creates `/etc/peloton-led/config.json` from your local
   `config.json` — **an existing file at that path is never overwritten**,
   so re-running the installer after a `git pull` won't clobber your
   settings.
5. Copies any existing local `cookies.txt` / `cookies-*.txt` token files
   into `/var/lib/peloton-led/`, but again, never overwrites a token that's
   already there.
6. Creates a Python virtualenv under `/opt/peloton-led/venv` and installs
   `requirements.txt` into it.
7. Builds and installs the native `rpi-rgb-led-matrix` Python bindings from
   source (unless `--skip-matrix`), cloning
   `github.com/hzeller/rpi-rgb-led-matrix` into
   `/opt/peloton-led/vendor/rpi-rgb-led-matrix` at the ref given by
   `--driver` (default: `master`).
8. Installs and enables `peloton-led.service` (and, with `--auto-token`,
   `peloton-token-refresh.timer` / `.service`), starting them immediately
   unless `--no-start` is given.

### Directory layout

| Purpose | Path |
|---|---|
| Application code | `/opt/peloton-led` |
| Configuration | `/etc/peloton-led/config.json` |
| Login environment (credentials) | `/etc/peloton-led/auth.env` |
| Access token(s) | `/var/lib/peloton-led/cookies*.txt` |
| Persistent snapshot/cache | `/var/lib/peloton-led/dashboard-cache*.json` |

The display runs as `peloton-led.service`: it starts at boot, restarts on
failure, and is granted only the GPIO-related capabilities the matrix driver
needs — it does not run as root. The installer validates configuration and
the systemd units before enabling the service, so a bad config fails the
install rather than producing a crash-looping service.

### Automatic token renewal (`--auto-token`)

```bash
sudo ./peloton-install.sh --auto-token
```

Add this if you want the Pi to keep your Peloton token fresh without you
manually re-running the login helper. It:

- Installs the Pi distribution's Chromium build (needed for headless login).
- Prompts for Peloton credentials the *first* time it creates
  `/etc/peloton-led/auth.env` (root-readable, mode `0600`); it's left alone
  on subsequent runs.
- Enables `peloton-token-refresh.timer`, which runs roughly hourly with a
  randomized delay and invokes `refresh_cookies.py --ensure`, which:
  1. Verifies the existing token against `/api/me`.
  2. Reads the token's real JWT expiry and does nothing if more than 12
     hours remain — no browser is opened on the common case.
  3. Starts a headless Chromium login only within the final 12 hours of
     expiry, or immediately after an HTTP 401.
  4. Never opens a browser for DNS failures, timeouts, rate limits, or
     Peloton server errors — those are treated as transient and retried
     next hour instead.
  5. Verifies the replacement token before atomically swapping it in.
  6. Exits nonzero on failure, leaving the previous token untouched.

The running dashboard notices the token file change on its own (no service
restart needed). If Peloton ever introduces CAPTCHA, MFA, or another
interactive step, the renewal fails safely, keeps the old token, and the
dashboard's amber padlock signals that a manual login is needed.

## Installer options reference

```
sudo ./peloton-install.sh [options]
```

| Option | Effect |
|---|---|
| `--auto-token` | Install Chromium and enable hourly headless token verification/renewal (see above) |
| `--skip-matrix` | Skip building/installing the native `rpi-rgb-led-matrix` bindings — use when they're already installed, or when preparing a Pi with no panel attached yet |
| `--skip-packages` | Skip the `apt-get install` step — use when you manage system packages yourself or they're already present |
| `--driver REF` | Git branch, tag, or commit of `rpi-rgb-led-matrix` to build (default: `master`) |
| `--no-start` | Install and enable the systemd units but don't start them yet — useful when staging a config before going live |
| `-h`, `--help` | Print usage and exit |

## Upgrading

Pull the latest code into your checkout, then re-run the same installer
command you used originally (with or without `--auto-token`, matching your
setup):

```bash
git pull
sudo ./peloton-install.sh --auto-token   # match your original flags
```

This upgrades the application code in `/opt/peloton-led` while preserving
configuration, tokens, credentials, cached display data, and PR/milestone
state — none of that lives in `/opt/peloton-led`, so it's never touched.

## Uninstalling

There's no automated uninstaller. To remove a Pi installation by hand:

```bash
sudo systemctl disable --now peloton-led.service peloton-token-refresh.timer peloton-token-refresh.service
sudo rm -rf /opt/peloton-led /etc/peloton-led /var/lib/peloton-led
sudo rm -f /etc/systemd/system/peloton-led.service /etc/systemd/system/peloton-token-refresh.{service,timer}
sudo systemctl daemon-reload
sudo userdel peloton-led   # optional: removes the dedicated service account
```

Back up `/etc/peloton-led/config.json` and `/var/lib/peloton-led/` first if
you might reinstall later — that's your settings, tokens, and history cache.

## Two users on one board

Two Peloton accounts (e.g. two riders sharing one panel) are supported and
documented separately in the
[dual-user setup and operations guide](dual-users.md). The short version:
copy `config.dual-users-example.json`, list each rider with a unique token
path, and create each rider's token with
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
- **Diagnostic commands:**
  ```bash
  sudo systemctl status peloton-led.service
  journalctl -u peloton-led.service -n 100
  systemctl list-timers peloton-token-refresh.timer
  sudo systemctl start peloton-token-refresh.service
  sudo systemctl status peloton-token-refresh.service
  journalctl -u peloton-token-refresh.service -n 100
  ```
