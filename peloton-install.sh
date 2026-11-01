#!/usr/bin/env bash
set -Eeuo pipefail

APP_USER="peloton-led"
APP_DIR="/opt/peloton-led"
CONFIG_DIR="/etc/peloton-led"
STATE_DIR="/var/lib/peloton-led"
UNIT_DIR="/etc/systemd/system"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DRIVER_REF="master"
AUTO_TOKEN=false
NO_BROWSER=false
SKIP_MATRIX=false
SKIP_PACKAGES=false
NO_START=false
# Empty until resolve_start_mode: --manual / --start-at-boot, or the default.
MANUAL=""
KEPT_BOOT_START=false
RECONFIGURE=false

usage() {
    cat <<'USAGE'
Usage: sudo ./peloton-install.sh [options]

Install or upgrade Peloton LED as managed Raspberry Pi services. Existing
configuration, token, login environment, cache, and PR state are preserved.

On first install (no /etc/peloton-led/config.json yet), you'll be prompted
to add one rider for a single-user board, or two or more for a shared board.

Options:
  --auto-token          Verify hourly; renew within 12 hours of expiry or after 401
  --no-browser          With --auto-token (implied): renew only with refresh
                         tokens seeded from another computer; skip Chromium and
                         Playwright (32-bit or 512 MB boards)
  --reconfigure         Re-prompt for riders, replacing the existing config and
                         auth.env (e.g. to switch between single- and dual-user)
  --skip-matrix         Skip the native rpi-rgb-led-matrix build
  --skip-packages       Skip apt package installation
  --driver REF          Matrix driver branch, tag, or commit (default: master)
  --no-start            With --start-at-boot: enable units without starting now
  --manual              The default: don't start at boot or now; run on demand
                         with systemctl start/stop peloton-led (token renewal,
                         with --auto-token, only runs while the display does).
                         Upgrades of a board that already starts at boot keep
                         doing so unless --manual is given.
  --start-at-boot       Start the display at boot and now (a dedicated board)
  -h, --help            Show this help
USAGE
}

# Manual (start on demand) is the default. An upgrade with no mode flag keeps a
# board that already starts at boot that way, so it doesn't go dark on its
# next reboot.
resolve_start_mode() {
    if [[ -z "$MANUAL" ]]; then
        if systemctl is-enabled --quiet peloton-led.service 2>/dev/null; then
            MANUAL=false
            KEPT_BOOT_START=true
        else
            MANUAL=true
        fi
    fi
    if [[ "$MANUAL" == true ]]; then
        NO_START=true
    fi
}

while (($#)); do
    case "$1" in
        --auto-token) AUTO_TOKEN=true; shift ;;
        --no-browser) AUTO_TOKEN=true; NO_BROWSER=true; shift ;;
        --reconfigure) RECONFIGURE=true; shift ;;
        --skip-matrix) SKIP_MATRIX=true; shift ;;
        --skip-packages) SKIP_PACKAGES=true; shift ;;
        --driver)
            [[ $# -ge 2 ]] || { echo "--driver requires a value" >&2; exit 2; }
            DRIVER_REF="$2"; shift 2 ;;
        --no-start) NO_START=true; shift ;;
        --manual) MANUAL=true; shift ;;
        --start-at-boot) MANUAL=false; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ "$(uname -s)" == "Linux" ]] || { echo "This installer must run on Linux." >&2; exit 1; }
[[ $EUID -eq 0 ]] || { echo "Run this installer with sudo." >&2; exit 1; }
[[ -f "$SOURCE_DIR/peloton_led.py" ]] || { echo "Run the installer from the project checkout." >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd is required." >&2; exit 1; }
resolve_start_mode

echo "Installing Peloton LED from $SOURCE_DIR"

if [[ "$SKIP_PACKAGES" == false ]]; then
    apt-get update
    packages=(python3 python3-dev python3-pip python3-venv cython3 git make gcc g++ cmake libopenjp2-7)
    if [[ "$AUTO_TOKEN" == true && "$NO_BROWSER" == false ]]; then
        packages+=(chromium)
    fi
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
for group in gpio video; do
    if getent group "$group" >/dev/null; then
        usermod -a -G "$group" "$APP_USER"
    fi
done

install -d -m 0755 -o root -g root "$APP_DIR" "$CONFIG_DIR"
install -d -m 0750 -o "$APP_USER" -g "$APP_USER" "$STATE_DIR"

for directory in assets display driver models peloton prepared_logos scripts utils packaging; do
    rm -rf "$APP_DIR/$directory"
    cp -a "$SOURCE_DIR/$directory" "$APP_DIR/$directory"
done
# Folders earlier versions installed that the app no longer has.
rm -rf "$APP_DIR/api"
for file in peloton_led.py requirements.txt requirements-auth.txt README.md config.json-example config.dual-users-example.json emulator_config.json; do
    install -m 0644 -o root -g root "$SOURCE_DIR/$file" "$APP_DIR/$file"
done
chmod 0755 "$APP_DIR/peloton_led.py" "$APP_DIR/scripts/refresh_cookies.py"
chown -R root:root "$APP_DIR"

if [[ ! -f "$CONFIG_DIR/config.json" || "$RECONFIGURE" == true ]]; then
    [[ -t 0 ]] || { echo "Run this in an interactive terminal to set up riders (or copy an existing config.json + auth.env into place manually)." >&2; exit 1; }
    # Subshell keeps the private umask to the secrets; leaking it would make
    # the venv below unreadable to the service account.
    (umask 077 && python3 "$SOURCE_DIR/scripts/setup_config.py" \
        "$SOURCE_DIR/packaging/config.pi.json" "$CONFIG_DIR/config.json" "$CONFIG_DIR/auth.env")
    chown root:"$APP_USER" "$CONFIG_DIR/config.json"
    chmod 0640 "$CONFIG_DIR/config.json"
    chown root:root "$CONFIG_DIR/auth.env"
    chmod 0600 "$CONFIG_DIR/auth.env"
else
    echo "Preserving existing $CONFIG_DIR/config.json and $CONFIG_DIR/auth.env"
    echo "(pass --reconfigure to change riders, e.g. switching single- vs. multi-user)"
fi
if [[ ! -f "$STATE_DIR/cookies.txt" && -f "$SOURCE_DIR/cookies.txt" ]]; then
    install -m 0600 -o "$APP_USER" -g "$APP_USER" "$SOURCE_DIR/cookies.txt" "$STATE_DIR/cookies.txt"
fi
# Seeded refresh tokens (refresh_cookies.py --seed-dir) ride along the same way.
for source_token in "$SOURCE_DIR"/cookies-*.txt "$SOURCE_DIR"/cookies*.refresh.json; do
    [[ -f "$source_token" ]] || continue
    target_token="$STATE_DIR/$(basename "$source_token")"
    if [[ ! -f "$target_token" ]]; then
        install -m 0600 -o "$APP_USER" -g "$APP_USER" "$source_token" "$target_token"
    fi
done

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

if [[ "$SKIP_MATRIX" == false ]]; then
    driver_dir="$APP_DIR/vendor/rpi-rgb-led-matrix"
    if [[ ! -d "$driver_dir/.git" ]]; then
        install -d -m 0755 -o root -g root "$(dirname "$driver_dir")"
        git clone https://github.com/hzeller/rpi-rgb-led-matrix.git "$driver_dir"
    fi
    git -C "$driver_dir" fetch --tags origin
    git -C "$driver_dir" checkout "$DRIVER_REF"
    # Upstream builds the Python bindings via scikit-build-core/cmake now
    # (pyproject.toml at the repo root); the old make-based targets for this
    # no longer exist on current master.
    # The binding compiles against Pillow's private Imaging.h, which pip's
    # Pillow doesn't ship; use headers from the exact installed version.
    pillow_headers="$(mktemp -d)"
    "$APP_DIR/venv/bin/python" "$APP_DIR/scripts/fetch_pillow_headers.py" "$pillow_headers" >/dev/null
    CFLAGS="-I$pillow_headers ${CFLAGS:-}" "$APP_DIR/venv/bin/python" -m pip install "$driver_dir"
    rm -rf "$pillow_headers"
fi

if [[ "$NO_BROWSER" == true ]]; then
    # Renewal falls back to a browser login only when Playwright is importable;
    # remove it so an upgraded board never starts Chromium.
    "$APP_DIR/venv/bin/python" -m pip uninstall -y playwright >/dev/null 2>&1 || true
elif [[ "$AUTO_TOKEN" == true ]]; then
    "$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/requirements-auth.txt"
    if [[ ! -f "$CONFIG_DIR/auth.env" ]]; then
        echo "Warning: $CONFIG_DIR/auth.env is missing; unattended token renewal needs it." >&2
        echo "Re-run with --reconfigure to set up rider credentials." >&2
    fi
fi

# The service runs as $APP_USER, so the code and venv must be world-readable.
# This also repairs installs whose venv was built under a leaked umask 077.
chmod -R a+rX "$APP_DIR"

install -m 0644 -o root -g root "$SOURCE_DIR/packaging/systemd/peloton-led.service" "$UNIT_DIR/peloton-led.service"
install -m 0644 -o root -g root "$SOURCE_DIR/packaging/systemd/peloton-token-refresh.service" "$UNIT_DIR/peloton-token-refresh.service"
install -m 0644 -o root -g root "$SOURCE_DIR/packaging/systemd/peloton-token-refresh.timer" "$UNIT_DIR/peloton-token-refresh.timer"

# The checkout's config.json, when present, is the live config: the services
# see it at $CONFIG_DIR/config.json through a read-only bind mount (below).
LIVE_CONFIG="$CONFIG_DIR/config.json"
if [[ -f "$SOURCE_DIR/config.json" ]]; then
    LIVE_CONFIG="$SOURCE_DIR/config.json"
fi
(cd "$APP_DIR" && "$APP_DIR/venv/bin/python" -c \
    "import sys; from peloton.config import load_config; load_config(sys.argv[1])" "$LIVE_CONFIG")
systemd-analyze verify "$UNIT_DIR/peloton-led.service" \
    "$UNIT_DIR/peloton-token-refresh.service" "$UNIT_DIR/peloton-token-refresh.timer"
# Manual mode: tie token renewal to the display's lifetime instead of boot.
# Starting the display runs one token check and starts the hourly timer;
# stopping the display stops the timer.
rm -f "$UNIT_DIR/peloton-led.service.d/manual.conf" "$UNIT_DIR/peloton-token-refresh.timer.d/manual.conf"
# ProtectHome hides the checkout from the services, so bind its config.json
# read-only over $CONFIG_DIR/config.json. "-" falls back to the /etc file
# when the checkout has none.
for unit in peloton-led.service peloton-token-refresh.service; do
    install -d -m 0755 "$UNIT_DIR/$unit.d"
    printf '[Service]\nBindReadOnlyPaths=-%s:%s\n' "$SOURCE_DIR/config.json" "$CONFIG_DIR/config.json" \
        > "$UNIT_DIR/$unit.d/project-config.conf"
done
if [[ "$MANUAL" == true && "$AUTO_TOKEN" == true ]]; then
    install -d -m 0755 "$UNIT_DIR/peloton-led.service.d" "$UNIT_DIR/peloton-token-refresh.timer.d"
    printf '[Unit]\nWants=peloton-token-refresh.service peloton-token-refresh.timer\n' \
        > "$UNIT_DIR/peloton-led.service.d/manual.conf"
    printf '[Unit]\nPartOf=peloton-led.service\n' \
        > "$UNIT_DIR/peloton-token-refresh.timer.d/manual.conf"
fi

systemctl daemon-reload
if [[ "$MANUAL" == true ]]; then
    # Undo boot-time enablement from an earlier non-manual install.
    systemctl disable peloton-led.service peloton-token-refresh.timer 2>/dev/null || true
else
    systemctl enable peloton-led.service
    if [[ "$AUTO_TOKEN" == true ]]; then
        systemctl enable peloton-token-refresh.timer
    fi
fi

# Token paths as the service resolves them: a rider without token_path uses
# cookies-<name>.txt beside the config the service reads ($CONFIG_DIR).
mapfile -t configured_tokens < <("$APP_DIR/venv/bin/python" - "$LIVE_CONFIG" "$APP_DIR" "$CONFIG_DIR" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[2])
from peloton.config import user_token_path
config=json.load(open(sys.argv[1], encoding='utf-8'))
users=config.get('users') or []
print('\n'.join(str(user_token_path(user, sys.argv[3])) for user in users) if users else '/var/lib/peloton-led/cookies.txt')
PY
)
if [[ "$NO_START" == false ]]; then
    for token_file in "${configured_tokens[@]}"; do
        if [[ -f "$token_file" ]]; then
            if ! runuser -u "$APP_USER" -- "$APP_DIR/venv/bin/python" \
                "$APP_DIR/scripts/refresh_cookies.py" --verify-only \
                --cookies "$token_file" --config "$CONFIG_DIR/config.json"; then
                echo "Warning: $token_file could not be verified." >&2
            fi
        else
            echo "No token installed at $token_file; that user will show a login indicator." >&2
        fi
    done
    systemctl restart peloton-led.service
    if [[ "$AUTO_TOKEN" == true ]]; then
        systemctl start peloton-token-refresh.timer
        systemctl start peloton-token-refresh.service || true
    fi
fi

rider_summary="$("$APP_DIR/venv/bin/python" - "$LIVE_CONFIG" "$APP_DIR" "$CONFIG_DIR" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[2])
from peloton.config import user_token_path
config = json.load(open(sys.argv[1], encoding='utf-8'))
users = config.get('users') or []
if not users:
    print('single-user (/var/lib/peloton-led/cookies.txt)')
else:
    names = ', '.join(f"{u['name']} ({user_token_path(u, sys.argv[3])})" for u in users)
    print(f'{len(users)} riders: {names}')
PY
)"

cat <<EOF

Peloton LED installation complete.

  Display:  systemctl status peloton-led.service
  Logs:     journalctl -u peloton-led.service -n 100
  Config:   $LIVE_CONFIG (edit, then restart peloton-led)
  Riders:   $rider_summary
EOF
if [[ "$MANUAL" == true ]]; then
    cat <<EOF
  Manual:   not started at boot; stop whatever else drives the panel, then
            sudo systemctl start peloton-led   (and stop peloton-led when done)
            For a dedicated board, re-run with --start-at-boot.
EOF
elif [[ "$KEPT_BOOT_START" == true ]]; then
    cat <<EOF
  Boot:     starts at boot, as before (manual is now the default for new
            installs; re-run with --manual to switch this board)
EOF
fi
if [[ "$AUTO_TOKEN" == true ]]; then
    cat <<EOF
  Timer:    systemctl list-timers peloton-token-refresh.timer
  Refresh:  systemctl start peloton-token-refresh.service
  Auth log: journalctl -u peloton-token-refresh.service -n 100
EOF
fi
# Checked last: on a board with Chromium, the renewal run above has already
# tried to log riders in. Whoever is still missing needs seeding from a computer.
missing_tokens=()
for token_file in "${configured_tokens[@]}"; do
    [[ -f "$token_file" ]] || missing_tokens+=("$token_file")
done
seed_command="scripts/seed_board.sh ${SUDO_USER:-<user>}@$(hostname).local"
if ((${#missing_tokens[@]})); then
    cat <<EOF

  NEXT STEP: no Peloton login yet for ${missing_tokens[*]}
  The display shows a padlock until you run this from the Peloton-LED
  checkout on your computer (it logs the riders in there and installs
  their tokens here):

      $seed_command

EOF
elif [[ "$NO_BROWSER" == true ]]; then
    cat <<EOF
  Seeding:  no browser here; to log in again, run from your computer's checkout
            $seed_command   (one seed per board)
EOF
fi
