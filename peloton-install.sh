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
SKIP_MATRIX=false
SKIP_PACKAGES=false
NO_START=false

usage() {
    cat <<'USAGE'
Usage: sudo ./peloton-install.sh [options]

Install or upgrade Peloton LED as managed Raspberry Pi services. Existing
configuration, token, login environment, cache, and PR state are preserved.

Options:
  --auto-token          Verify hourly; renew within 12 hours of expiry or after 401
  --skip-matrix         Skip the native rpi-rgb-led-matrix build
  --skip-packages       Skip apt package installation
  --driver REF          Matrix driver branch, tag, or commit (default: master)
  --no-start            Install and enable units without starting them now
  -h, --help            Show this help
USAGE
}

while (($#)); do
    case "$1" in
        --auto-token) AUTO_TOKEN=true; shift ;;
        --skip-matrix) SKIP_MATRIX=true; shift ;;
        --skip-packages) SKIP_PACKAGES=true; shift ;;
        --driver)
            [[ $# -ge 2 ]] || { echo "--driver requires a value" >&2; exit 2; }
            DRIVER_REF="$2"; shift 2 ;;
        --no-start) NO_START=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ "$(uname -s)" == "Linux" ]] || { echo "This installer must run on Linux." >&2; exit 1; }
[[ $EUID -eq 0 ]] || { echo "Run this installer with sudo." >&2; exit 1; }
[[ -f "$SOURCE_DIR/peloton_led.py" ]] || { echo "Run the installer from the project checkout." >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd is required." >&2; exit 1; }

echo "Installing Peloton LED from $SOURCE_DIR"

if [[ "$SKIP_PACKAGES" == false ]]; then
    apt-get update
    packages=(python3 python3-dev python3-pip python3-venv cython3 git make gcc g++ cmake libopenjp2-7)
    if [[ "$AUTO_TOKEN" == true ]]; then
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

for directory in api assets display driver models peloton prepared_logos scripts utils packaging; do
    rm -rf "$APP_DIR/$directory"
    cp -a "$SOURCE_DIR/$directory" "$APP_DIR/$directory"
done
for file in peloton_led.py requirements.txt requirements-auth.txt README.md config.json-example config.dual-users-example.json emulator_config.json; do
    install -m 0644 -o root -g root "$SOURCE_DIR/$file" "$APP_DIR/$file"
done
chmod 0755 "$APP_DIR/peloton_led.py" "$APP_DIR/scripts/refresh_cookies.py"
chown -R root:root "$APP_DIR"

if [[ ! -f "$CONFIG_DIR/config.json" ]]; then
    python3 "$SOURCE_DIR/scripts/migrate_pi_config.py" \
        "$SOURCE_DIR/config.json" "$SOURCE_DIR/packaging/config.pi.json" "$CONFIG_DIR/config.json"
    chown root:"$APP_USER" "$CONFIG_DIR/config.json"
    chmod 0640 "$CONFIG_DIR/config.json"
else
    echo "Preserving existing $CONFIG_DIR/config.json"
fi
if [[ ! -f "$STATE_DIR/cookies.txt" && -f "$SOURCE_DIR/cookies.txt" ]]; then
    install -m 0600 -o "$APP_USER" -g "$APP_USER" "$SOURCE_DIR/cookies.txt" "$STATE_DIR/cookies.txt"
fi
for source_token in "$SOURCE_DIR"/cookies-*.txt; do
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
    "$APP_DIR/venv/bin/python" -m pip install "$driver_dir"
fi

write_auth_environment() {
    local profile email_var password_var email password escaped_email escaped_password
    local -a auth_profiles
    mapfile -t auth_profiles < <("$APP_DIR/venv/bin/python" - "$CONFIG_DIR/config.json" <<'PY'
import json, re, sys
config = json.load(open(sys.argv[1], encoding='utf-8'))
users = config.get('users') or []
if not users:
    print('default\tPELOTON_EMAIL\tPELOTON_PASSWORD')
for user in users:
    suffix = re.sub(r'[^A-Z0-9]+', '_', user['name'].upper()).strip('_') or 'USER'
    print('\t'.join((user['name'], user.get('email_env', f'PELOTON_EMAIL_{suffix}'),
                    user.get('password_env', f'PELOTON_PASSWORD_{suffix}'))))
PY
)
    umask 077
    : > "$CONFIG_DIR/auth.env"
    for row in "${auth_profiles[@]}"; do
        IFS=$'\t' read -r profile email_var password_var <<< "$row"
        email="${!email_var:-}"; password="${!password_var:-}"
        if [[ -z "$email" ]]; then
            [[ -t 0 ]] || { echo "$email_var is required for --auto-token." >&2; return 1; }
            read -r -p "Peloton email for $profile: " email
        fi
        if [[ -z "$password" ]]; then
            [[ -t 0 ]] || { echo "$password_var is required for --auto-token." >&2; return 1; }
            read -r -s -p "Peloton password for $profile: " password
            echo
        fi
        escaped_email="${email//\\/\\\\}"; escaped_email="${escaped_email//\"/\\\"}"
        escaped_password="${password//\\/\\\\}"; escaped_password="${escaped_password//\"/\\\"}"
        printf '%s="%s"\n' "$email_var" "$escaped_email" >> "$CONFIG_DIR/auth.env"
        printf '%s="%s"\n' "$password_var" "$escaped_password" >> "$CONFIG_DIR/auth.env"
    done
    chown root:root "$CONFIG_DIR/auth.env"
    chmod 0600 "$CONFIG_DIR/auth.env"
}

if [[ "$AUTO_TOKEN" == true ]]; then
    "$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/requirements-auth.txt"
    if [[ ! -f "$CONFIG_DIR/auth.env" ]]; then
        write_auth_environment
    else
        echo "Preserving existing $CONFIG_DIR/auth.env"
    fi
fi

install -m 0644 -o root -g root "$SOURCE_DIR/packaging/systemd/peloton-led.service" "$UNIT_DIR/peloton-led.service"
install -m 0644 -o root -g root "$SOURCE_DIR/packaging/systemd/peloton-token-refresh.service" "$UNIT_DIR/peloton-token-refresh.service"
install -m 0644 -o root -g root "$SOURCE_DIR/packaging/systemd/peloton-token-refresh.timer" "$UNIT_DIR/peloton-token-refresh.timer"

(cd "$APP_DIR" && "$APP_DIR/venv/bin/python" -c \
    "from peloton.config import load_config; load_config('$CONFIG_DIR/config.json')")
systemd-analyze verify "$UNIT_DIR/peloton-led.service" \
    "$UNIT_DIR/peloton-token-refresh.service" "$UNIT_DIR/peloton-token-refresh.timer"
systemctl daemon-reload
systemctl enable peloton-led.service

if [[ "$AUTO_TOKEN" == true ]]; then
    systemctl enable peloton-token-refresh.timer
fi

if [[ "$NO_START" == false ]]; then
    mapfile -t configured_tokens < <("$APP_DIR/venv/bin/python" - "$CONFIG_DIR/config.json" <<'PY'
import json, sys
config=json.load(open(sys.argv[1], encoding='utf-8'))
users=config.get('users') or []
print('\n'.join(user['token_path'] for user in users) if users else '/var/lib/peloton-led/cookies.txt')
PY
)
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

cat <<EOF

Peloton LED installation complete.

  Display:  systemctl status peloton-led.service
  Logs:     journalctl -u peloton-led.service -n 100
  Config:   $CONFIG_DIR/config.json
  Token:    $STATE_DIR/cookies.txt
EOF
if [[ "$AUTO_TOKEN" == true ]]; then
    cat <<EOF
  Timer:    systemctl list-timers peloton-token-refresh.timer
  Refresh:  systemctl start peloton-token-refresh.service
  Auth log: journalctl -u peloton-token-refresh.service -n 100
EOF
fi
