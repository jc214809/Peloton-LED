# Phase 5 implementation status

Phase 5 packages the dashboard for unattended Raspberry Pi operation under systemd.

## Implemented

- `peloton-install.sh` installs or upgrades the application in `/opt/peloton-led` and creates a dedicated `peloton-led` system account.
- Configuration, authentication, and runtime state live outside the application tree under `/etc/peloton-led` and `/var/lib/peloton-led`.
- Existing configuration, token, login environment, cache, and PR acknowledgement state are preserved on upgrades. A first managed install migrates legacy display settings but removes the legacy `auth` block from the service-readable configuration.
- `peloton-led.service` starts at boot, restarts after failures, stops with enough time for an in-flight API request, and grants the limited capabilities needed by the matrix driver.
- The installer builds `rpi-rgb-led-matrix` into the application virtual environment unless `--skip-matrix` is selected.
- `--auto-token` installs authentication dependencies and the Pi distribution’s Chromium package, writes root-only credentials, and enables a persistent hourly timer with randomized delay.
- `scripts/refresh_cookies.py --ensure` verifies hourly and opens a headless browser when a valid JWT has 12 hours or less remaining, or immediately after HTTP 401. Network, timeout, rate-limit, and server failures leave the token untouched.
- The installer validates application configuration and all systemd units before enabling services, verifies an existing token, and prints service and journal commands.

## Automated evidence

- Shell syntax is checked with `bash -n`.
- Tests verify the upgrade-preservation contract, production cache path, managed-service restart policy, protected state paths, timer persistence, Chromium selection, and expiry-aware renewal.
- Token tests confirm that a token with 13 hours remaining is kept, one with 11 hours remaining is renewed, network failures never launch the browser, rejected tokens require unattended credentials, and replacements remain atomic and private.
- A real headless login on the development host obtained a different token, verified it with `/api/me`, saved it with `0600` permissions, and triggered a live dashboard reload without restarting the emulator.

## On-device acceptance checklist

Run this once on the target Raspberry Pi before considering hardware deployment accepted:

1. Install with `sudo ./peloton-install.sh --auto-token`.
2. Confirm `systemctl status peloton-led.service` is active and the physical panel rotates screens.
3. Reboot and confirm the service and display return without an interactive login.
4. Run `sudo systemctl start peloton-token-refresh.service` and inspect its journal.
5. Temporarily disconnect networking, restart the display, and confirm cached screens appear immediately and the blue stale-data clock appears after the third failed refresh.
6. Restore networking and confirm the stale clock clears after a successful refresh.
7. Run the installer again and confirm local configuration, token, cache, and authentication files retain their checksums.
