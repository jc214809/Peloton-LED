# Peloton LED Dashboard

A Python dashboard for a Raspberry Pi RGB LED matrix, with a desktop browser emulator. Shows every completed workout from your latest active day, one-time personal-record celebrations, username, and lifetime workout counts by discipline.

## Setup

Quick start for local development:

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

Run commands from the project directory. The default panel is 64×64. The browser emulator is available at http://localhost:8888 while running; its settings are in `emulator_config.json`.

For every install option — the full `peloton_led.py` flag reference, getting a Peloton access token, the Raspberry Pi managed installation (`peloton-install.sh` and its flags, directory layout, automatic token renewal), upgrading, uninstalling, and troubleshooting — see the **[Installation Guide](docs/install.md)**.

## Authentication

Despite its name, `cookies.txt` contains a bearer access token, not a cookie export. See the [Installation Guide](docs/install.md#getting-a-peloton-token) for how to generate one.

An **amber padlock in the bottom-right** means the token is missing, empty, unreadable, or rejected with HTTP 401. Refresh the token file and the running display automatically reloads it. It checks for file changes approximately once per second between requests. Network errors alone do not trigger the padlock.

## Refresh behavior

- Profile, overview totals, and recent history refresh in the background every **300 seconds** by default, measured after the previous successful refresh finishes.
- New data becomes visible on the next screen rotation. Authentication indicator changes can repaint the current screen.
- Performance data is held in a bounded in-memory LRU cache keyed by workout ID. Workouts less than one hour old are fetched each refresh to allow metrics to settle; changed workout metadata and missing performance data also cause a refetch.
- Rendering does not make API calls. Slow requests do not pause screen rotation.
- Each atomic snapshot includes connection state, refresh progress, last attempt/success times, refresh duration, next scheduled attempt, a sanitized error type, and a generation counter.
- Network failures preserve the previous successful snapshot in memory and retry after 15, 30, 60 seconds, etc., up to the configured interval. Rate-limit `Retry-After` values can extend that delay.
- A rejected token pauses further requests until the token file changes.
- The last successful display snapshot is saved atomically in `dashboard-cache.json` beside the token by default, with owner-only permissions. It is loaded before the first network request after a restart.
- A **blue clock in the bottom-left** appears after three consecutive refresh failures and means the board is showing saved data. The first two failures remain quiet, and any successful refresh resets the counter and clears the clock. Corrupt, incomplete, and unsupported cache files are ignored safely.

Override the interval:

```bash
python peloton_led.py --emulated --refresh-interval 300
```

## Display rotation logic

The startup logo is shown once when the application starts. After that, the dashboard repeats this rotation:

1. One workout screen for every completed workout on the most recent active calendar day, newest first.
2. A PR star immediately after a personal-record workout, the first time that PR is displayed.
3. Username screen.
4. A dedicated full-size Total Workouts page, followed on 64×64 panels by compact lifetime pages with four separate disciplines per page. Each has its own pixel icon and exact count; Bootcamp disciplines remain separate. 64×32 panels show the same icon tiles two per page.

“Most recent active day” means the newest local calendar date containing at least one completed workout. If the member worked out today, today’s completed workouts are shown. If their last activity was a week ago, every completed workout from that date is shown. The search is bounded by `history_days`, `history_limit`, and the pagination safety settings. In-progress workouts are excluded. If no workout summary is available, the first position is replaced by a short `Loading`, `Login needed`, `Offline`, or `No workouts` status screen.

The duration of each position comes from the display configuration:

| Position | Setting |
|---|---|
| Each latest-active-day workout | `last_workout_duration` |
| PR screen | `overview_duration` |
| Username | `duration` |
| Total Workouts and each lifetime overview page | One shared `overview_duration` |
| Status screen | The smaller of `overview_duration` and two seconds |

Lifetime tiles are composed offscreen and published in one frame, so every label, icon, and count appears at the same time. Rowing uses a minimal indoor exercise-rower icon with a slim rail, supports, and filled flywheel housing. Bootcamp animations share one page clock: they show the activity icon on arrival, switch together on the first 0.2-second update, then alternate with a strength dumbbell every 0.8 seconds. Total Workouts and every lifetime discipline page use the same display time. When any Bootcamp is present and durations are nonzero, that shared time is at least 3.2 seconds so every page advances at the same pace.

The worker publishes refreshed data in the background, but a rotation uses one consistent snapshot from beginning to end. Newly fetched workouts and totals appear at the start of the next rotation. Authentication-state changes are the exception: the amber login padlock can appear or disappear while the current screen is still displayed.

The username screen keeps the complete rider name fixed while its lower panel rotates through Total Workouts, this week's workout/minute progress, and the leading lifetime discipline. It automatically selects the largest font that fits the username. Detail values use up to two short lines so counts, minutes, and discipline names remain complete. A blue underline and each detail animate as soon as the screen appears. When the configured username duration is nonzero, it is automatically extended to three seconds per available detail so every detail appears once.

The former `last_workout_discipline` filter is no longer used: the rotation always includes every discipline completed on the most recent active day. `display.rotation` controls screen order and inclusion using `latest_workouts`, `username`, `total_workouts`, `lifetime`, `milestones`, and `goals`. `screen_durations` can override section timing; `lifetime` controls both Total Workouts and lifetime pages so their timing stays synchronized. `per_workout_duration` remains accepted for compatibility but is not used. Displayed PR workout IDs and lifetime milestones are saved with the dashboard cache, so celebrations do not replay after restart.

## Phase 6 customization

Weekly goals are optional. Set `weekly_goals.workouts` and/or `weekly_goals.minutes` to a positive number to add progress screens; zero disables that goal. Progress counts completed workouts from Monday at midnight in the configured/profile timezone. Set `milestones` to lifetime Total Workouts thresholds such as `[100, 250, 500, 1000]`. Each reached threshold celebrates once.

Set `brightness_schedule` to `null` to retain command-line brightness, or use a day/night schedule:

```json
"brightness_schedule": {
  "day": 80,
  "night": 15,
  "day_start": "07:00",
  "night_start": "22:00"
}
```

Times use the configured/profile timezone and brightness ranges from 1 through 100. On 32-row panels, `compact_workout_pages: true` switches back to the older two-page compact workout layout in place of the rotating one.

## Offline demo and checks

Demo mode uses five synthetic API-shaped workouts, including a PR, long title, metric/imperial distances, and missing metrics. It does not read credentials or call Peloton. If no config exists, defaults are used.

```bash
python peloton_led.py --emulated --demo --cycles 1
python peloton_led.py --emulated --demo --demo-login-needed --cycles 1
python scripts/render_demo.py /tmp/peloton-demo.png
python -m pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

`--cycles 1` stops after one full rotation. Omit it to run continuously. Durations come from configuration; `--display-duration` overrides only the username screen. The PNG preview uses the same emulator text drawing and screen code, without starting a browser server.

## Configuration

Settings live under `display` in `config.json`. Invalid values produce a startup error before hardware or network initialization. Every setting below is optional — an absent key falls back to its default, so a minimal `{"display": {}}` (or even `{}`) is a valid config.

| Setting | Default | Meaning |
|---|---|---|
| `username` | Peloton Member | Fallback if profile is unavailable; `--username` takes precedence |
| `font` | stats | Username font: discipline, info, titles, stats, countdown |
| `color` | white | white, red, gold, disney_blue, down |
| `duration` | 4 | Username screen seconds |
| `overview_duration` | 4 | Per-discipline and PR screen seconds |
| `last_workout_duration` | 30 | Workout screen seconds on 32-row panels; 64-row pages are timed by `last_workout_detail_interval` (see below) |
| `last_workout_detail_interval` | 4 | Seconds each stat (and the intro) holds for during the workout screen's rotation |
| `logo_duration` | 3 | Startup logo seconds |
| `logo_path` | Auto-selected | Optional logo file; missing logos are skipped |
| `timezone` | Profile, then system local | Calendar-day grouping; explicit config must be a valid IANA zone |
| `refresh_interval` | 300 | Positive integer seconds |
| `history_days` | 90 | History lookback |
| `history_limit` | 200 | Maximum recent workouts returned |
| `history_page_size` | 50 | Workouts requested per API page |
| `history_max_pages` | 10 | Page safety limit |
| `instructor_tally_max_pages` | 200 | Page safety limit for the one-time full-history instructor tally |
| `performance_cache_size` | 32 | Maximum in-memory performance records |
| `cache_path` | Beside token | Optional persistent snapshot and PR-state file |
| `rotation` | See below | Screen sections to show, and their order |
| `screen_durations` | `{}` | Per-section seconds, overriding the individual duration settings above |
| `weekly_goals` | `{"workouts": 0, "minutes": 0}` | Weekly workout/minute targets; `0` disables that goal. See [Phase 6 customization](#phase-6-customization) |
| `milestones` | `[]` | Lifetime Total Workouts thresholds that celebrate once each, e.g. `[100, 250, 500]` |
| `brightness_schedule` | `null` | Optional day/night brightness schedule. See [Phase 6 customization](#phase-6-customization) |
| `compact_workout_pages` | `false` | On 32-row panels, use the older two-page compact workout layout instead of the rotating one |

`rotation` accepts any subset of `latest_workouts`, `username`, `total_workouts`, `lifetime`, `milestones`, `goals`, each at most once. `screen_durations` keys are `latest_workouts`, `username`, `lifetime`, `milestones`, `goals` — `lifetime` controls both Total Workouts and lifetime discipline pages so their timing stays synchronized.

Each full-board workout screen shows a discipline/duration/title intro, then shows each of that discipline's stats once, one at a time, each held for `last_workout_detail_interval` seconds. The page lasts exactly `last_workout_detail_interval * (1 + stat count)` seconds, so every stat gets one full turn with no cut-offs and no repeats. A workout with no stats shows its intro for one interval. `last_workout_duration` (or `screen_durations.latest_workouts`) only sets the page length on 32-row panels, where pages are static; `0` still disables the section.

Legacy `ride` and `park` font names map to `discipline`. `per_workout_duration` is accepted for older configs but is not used in the current rotation.

History fetches stop on the date cutoff, end of results, repeated pages, or configured limits. A warning is logged when a limit prevents a complete search. Explicit incomplete workouts are excluded; older payloads without a status remain usable. If no workout matches the selected discipline, the latest completed workout is shown and the fallback is logged.

Timestamps accept Unix seconds/milliseconds and ISO dates with offsets. Date-only values can be grouped into days but never establish which workout occurred last. Explicit API metrics take precedence over derived averages, including rowing split values supplied in minutes per 500 m. Missing metrics remain blank; zero is preserved. Output PRs and splits PRs share a badge, but only output PRs receive the output star.

Each refresh saves Peloton's output personal-records table (one record per discipline and class length) in the dashboard cache, at no extra API cost since it arrives with the profile overview. Peloton only reports the current record, so when a record's workout ID changes, the saved value is kept as the record it replaced, and the PR screen shows the gain (e.g. `+14 KJ`). A PR set before the app first saw the old record, such as on a fresh install, shows the class length instead.

### Full example: every option set explicitly

[`config.json-example`](config.json-example) and [`config.dual-users-example.json`](config.dual-users-example.json) are intentionally minimal — anything left out just uses its default. The example below sets every `display` option and every per-user option at once, purely as a reference for what exists; it isn't meant to be used verbatim or copied as a starting point.

```json
{
  "debug": false,
  "users": [
    {
      "name": "Joel",
      "email_env": "PELOTON_EMAIL_RIDER_ONE",
      "password_env": "PELOTON_PASSWORD_RIDER_ONE",
      "token_path": "cookies-joel.txt",
      "cache_path": "dashboard-cache-joel.json",
      "username": "Joel",
      "weekly_goals": { "workouts": 5, "minutes": 0 },
      "milestones": [100, 250, 500]
    }
  ],
  "display": {
    "font": "stats",
    "color": "white",
    "duration": 9,
    "overview_duration": 4,
    "last_workout_duration": 15,
    "last_workout_detail_interval": 4,
    "logo_duration": 3,
    "logo_path": null,
    "timezone": "America/New_York",
    "refresh_interval": 300,
    "history_days": 90,
    "history_limit": 200,
    "history_page_size": 50,
    "history_max_pages": 10,
    "instructor_tally_max_pages": 200,
    "performance_cache_size": 32,
    "rotation": ["username", "latest_workouts", "total_workouts", "lifetime", "milestones", "goals"],
    "screen_durations": { "latest_workouts": 15, "username": 9, "lifetime": 5, "milestones": 4, "goals": 4 },
    "brightness_schedule": null,
    "compact_workout_pages": false
  }
}
```

Top-level and per-user fields, and whether each is required:

| Field | Required? | Notes |
|---|---|---|
| `debug` | No (default `false`) | Verbose logging |
| `users` | No | Omit entirely for single-user mode (`config.json-example`); see [dual-user guide](docs/dual-users.md) |
| `users[].name` | **Yes**, once `users` is present | Must be unique (case-insensitive) across all users |
| `users[].token_path` | No | Defaults to `cookies-<slug of name>.txt` beside the config file |
| `users[].cache_path` | No | Defaults to `<token file stem>-dashboard-cache.json` |
| `users[].username` | No | Defaults to the account's real Peloton username |
| `users[].email_env` | No | Only used for unattended token renewal (`refresh_cookies.py --ensure`) |
| `users[].password_env` | No | Only used for unattended token renewal |
| `users[].weekly_goals` | No | Falls back to `display.weekly_goals` when omitted |
| `users[].milestones` | No | Falls back to `display.milestones` when omitted |
| `display` | No | Omit entirely to use every default in the table above |
| every `display.*` key | No | See the configuration table above for each default |

## Display support and remaining work

Both **64×64** and **64×32** panels are supported; for 64×32 use `--led-rows 32 --led-cols 64`. On 64×32 the workout screen uses the same intro-then-rotating-stats layout as 64×64, adapted to fit: the instructor is the first rotating stat, and the heart-rate/calories bar shows during the stats. See [docs/64x32-NOTES.md](docs/64x32-NOTES.md) for every difference. Preview either size with `python scripts/render_rotation.py --height 32 --demo`.

Live mode cycles through every completed workout on the latest active day. Every discipline uses a safe common layout; cycling/bike bootcamp, running/walking/tread, and rowing/row bootcamp add discipline-specific statistics when Peloton supplies them. Unknown future disciplines still show discipline, title, duration, heart rate, calories, and compatible common metrics. Lifetime totals preserve every discipline and its exact count in separate pixel-icon tiles, four per page on 64×64 and two per page on 64×32. No disciplines are combined. Goals, milestones, scheduled brightness, configurable rotation, and optional two-page 32-row workout details are implemented in Phase 6.

## Code map

- `peloton_led.py`: startup and screen rotation
- `peloton/dashboard.py`, `peloton/cache.py`: background refresh, token reload, snapshots, and recovery
- `peloton/api.py`: authenticated requests and bounded history pagination
- `peloton/timestamps.py`, `selection.py`, `records.py`, `totals.py`: shared data and lifetime pagination rules
- `peloton/summaries.py`: metric normalization for screens and reports
- `display/ui/`: screens and login indicator
- `driver/`: hardware/emulator selection
- `scripts/refresh_cookies.py`: browser login and verified token saving
- `scripts/render_demo.py`: reproducible screen preview

## Phase 3 validation

See [Phase 3 implementation status and evidence](docs/phase-3-status.md).

## Phase 4 validation

See [Phase 4 recovery and durable-event status](docs/phase-4-status.md).

## Phase 1–2 validation

See [implementation status and validation evidence](docs/phase-1-2-status.md).

## Raspberry Pi managed installation

`sudo ./peloton-install.sh` installs Peloton LED as a managed systemd service under a dedicated, unprivileged account, and is also how you upgrade an existing install. See the **[Installation Guide](docs/install.md#raspberry-pi-managed-install)** for the full walkthrough: directory layout, every installer flag, automatic token renewal (`--auto-token`), upgrading, uninstalling, and diagnostic commands.

## Two users on one board

See the complete [dual-user setup and operations guide](docs/dual-users.md).

Copy `config.dual-users-example.json` to a private configuration file and list riders in the desired display order. Each rider requires a unique `token_path` and `cache_path`. The board completes the first rider's full rotation before starting the second rider's rotation. Profile data, latest workouts, totals, weekly goals, milestones, PR acknowledgements, login state, stale state, and disk cache remain isolated per rider.

Relative token and cache paths resolve beside the configuration file. For a local setup, create each token separately:

```bash
python scripts/refresh_cookies.py --cookies cookies-rider-one.txt
python scripts/refresh_cookies.py --cookies cookies-rider-two.txt
```

Each command prompts for that rider's Peloton email and password without placing the password in shell history.

Token files contain bearer credentials and must stay out of Git. The included `cookies*.txt` ignore rule covers the recommended names.

For unattended Pi renewal, each user entry names its email/password environment variables. The resulting root-owned `/etc/peloton-led/auth.env` looks like this:

```bash
PELOTON_EMAIL_RIDER_ONE="first@example.com"
PELOTON_PASSWORD_RIDER_ONE="first password"
PELOTON_EMAIL_RIDER_TWO="second@example.com"
PELOTON_PASSWORD_RIDER_TWO="second password"
```

`peloton-token-refresh.timer` checks every configured token hourly and renews each one headlessly when fewer than 12 hours remain. One user's failed login does not mix or overwrite another user's token. The installer stores each token and cache under `/var/lib/peloton-led/` with restricted permissions.

## Phase 5 validation

See [Phase 5 managed-installation status](docs/phase-5-status.md). Native matrix access, Pi Chromium login, and boot/restart behavior still require one on-device acceptance run because the development host is macOS.

## Phase 6 validation

See [Phase 6 customization status](docs/phase-6-status.md).
