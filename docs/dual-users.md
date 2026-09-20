# Dual-user operation

Dual-user mode runs two independent Peloton dashboards on one matrix. Both accounts refresh in parallel. The display shows every configured section for the first rider, then every section for the second rider, and repeats in that order.

## Configuration

Start with `config.dual-users-example.json`. Each entry under `users` requires:

- `name`: local profile label used in logs and credential setup.
- `token_path` (optional): that rider's bearer-token file. Defaults to `cookies-<name>.txt` (name lowercased, slugified) beside the config file.
- `cache_path` (optional): that rider's persisted snapshot, PR acknowledgements, and milestone state. Defaults to `<token file stem>-dashboard-cache.json` beside the token file.
- `email_env` and `password_env`: environment-variable names used only for unattended token renewal.
- `username` (optional): board name override. When omitted, the account's Peloton username is shown.
- `weekly_goals` (optional): per-rider weekly workout/minute targets. Falls back to `display.weekly_goals` when omitted.
- `milestones` (optional): per-rider lifetime-workout milestone thresholds. Falls back to `display.milestones` when omitted.

User order in the JSON array is display order. Token and cache paths must be unique. Relative paths resolve beside the configuration file.

## Initial tokens

Create each token through a separate interactive login. If you didn't set `token_path` explicitly, use the derived default (`cookies-<name>.txt`) so `refresh_cookies.py` and the display app agree on the file:

```bash
python scripts/refresh_cookies.py --cookies cookies-joel.txt
python scripts/refresh_cookies.py --cookies cookies-jen.txt
```

The script verifies the account before replacing a token. Token files and dashboard caches are ignored by Git and should remain owner-readable only.

## Local development

For unattended/scripted token renewal on a dev machine (`refresh_cookies.py --ensure`), `email_env`/`password_env` only *name* which environment variables to read — nothing sets them for you outside the Pi install. Locally, put them in a `.env` file:

```bash
cp .env.example .env
# then edit .env with real credentials
```

`.env` is gitignored and loaded automatically by `peloton_led.py` and `scripts/refresh_cookies.py` at startup (a real, already-exported env var always takes precedence over `.env`). For a single-user setup, `.env.example` also documents the plain `PELOTON_EMAIL` / `PELOTON_PASSWORD` fallback used when no `users` array is configured.

This `.env` loading is a local-dev convenience only — it isn't used on the Raspberry Pi install, which reads credentials from `/etc/peloton-led/auth.env` instead (see below).

## Display and failure isolation

Each rider has an independent background refresh worker, cache, login-required state, three-failure stale indicator, PR history, milestone history, weekly progress, latest active day, and lifetime totals. A failure for one rider does not stop the other rider's data refresh or erase either cache. Login and stale indicators follow the rider currently displayed.

## Raspberry Pi installation

On first installation, the migration script rewrites each token and cache location under `/var/lib/peloton-led/`. The installer copies matching `cookies-*.txt` files without replacing existing state. With `--auto-token`, it prompts for every rider's login and writes the configured variables to root-owned `/etc/peloton-led/auth.env` with mode `0600`.

The hourly `peloton-token-refresh.timer` calls `refresh_cookies.py --ensure --all-users`. It verifies all tokens, opens headless Chromium only for rejected or soon-expiring tokens, and renews them independently. It attempts later riders even if an earlier rider fails, then reports a failed service run so the problem remains visible in systemd.

## Backward compatibility

When `users` is absent, `--cookies`, the legacy cache path, the display service, and token renewal continue to operate as a single-user installation.
