#!/usr/bin/env bash
set -Eeuo pipefail

APP_USER="peloton-led"
APP_DIR="/opt/peloton-led"
CONFIG_DIR="/etc/peloton-led"
STATE_DIR="/var/lib/peloton-led"
UNIT_DIR="/etc/systemd/system"
BIN_DIR="/usr/local/bin"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DRIVER_REF="master"
AUTO_TOKEN=false
NO_BROWSER=false
# none, browser or no-browser; empty until resolve_token_mode: a flag, the
# board's saved mode, or the hardware's.
TOKEN_MODE=""
TOKEN_MODE_SOURCE=""
# flag when a token flag chose the mode, on this run or an earlier one.
TOKEN_MODE_ORIGIN=auto
TOKEN_MODE_FILE="$CONFIG_DIR/token-mode"
DISPLAY_WAS_RUNNING=false
# The live config's matrix.gpio_mapping (check_gpio_mapping), and whether the
# onboard audio stays loaded until a reboot (check_pwm_audio).
GPIO_MAPPING=""
AUDIO_REBOOT=false
SKIP_MATRIX=false
SKIP_PACKAGES=false
SKIP_REQUIREMENTS=false
NO_START=false
# Empty until resolve_start_mode: --manual / --start-at-boot, or the default.
MANUAL=""
KEPT_BOOT_START=false
RECONFIGURE=false
# true or false; empty until resolve_settings_page: a flag, or the board's.
SETTINGS_PAGE=""
SETTINGS_PORT=8080

usage() {
    cat <<'USAGE'
Usage: sudo ./peloton-install.sh [options]

Install or upgrade Peloton LED as managed Raspberry Pi services. Existing
configuration, token, login environment, cache, and PR state are preserved.

On first install (no /etc/peloton-led/config.json yet), you'll be prompted
to add one rider for a single-user board, or two or more for a shared board.

Token renewal is picked automatically: a board that already renews tokens
keeps its mode; otherwise a 32-bit or under-768 MB board gets --no-browser
and any other board --auto-token. The flags below override that and are
remembered; renewal stays off only after --no-auto-token.

Options:
  --auto-token          Verify hourly; renew within 12 hours of expiry or after
                         401, logging in with Chromium when a refresh token fails
  --no-browser          With --auto-token (implied): renew only with refresh
                         tokens seeded from another computer; skip Chromium and
                         Playwright (32-bit or under-768 MB boards)
  --no-auto-token       No scheduled renewal; replace tokens by hand
  --reconfigure         Re-prompt for riders, replacing the existing config and
                         auth.env (e.g. to switch between single- and dual-user)
  --skip-matrix         Skip the native rpi-rgb-led-matrix build
  --skip-packages       Skip apt package installation
  --skip-requirements   Skip pip installing requirements*.txt (the updater's, when
                         neither changed)
  --driver REF          Matrix driver branch, tag, or commit (default: master)
  --no-start            With --start-at-boot: enable units without starting now
                         (an upgrade still restarts a display that is running)
  --manual              The default: don't start at boot or now; run on demand
                         with systemctl start/stop peloton-led (automatic token
                         renewal only runs while the display does).
                         Upgrades of a board that already starts at boot keep
                         doing so unless --manual is given.
  --start-at-boot       Start the display at boot and now (a dedicated board)
  --no-settings-page    Turn off the settings page (http://<board>.local:8080),
                         which is on by default; remembered on upgrades
  --settings-page       Turn it back on
  -h, --help            Show this help
USAGE
}

# The settings page (peloton-settings.service) is on unless a flag says otherwise, or an earlier
# --no-settings-page left it installed but disabled.
resolve_settings_page() {
    if [[ -z "$SETTINGS_PAGE" ]]; then
        SETTINGS_PAGE=true
        if [[ -f "$UNIT_DIR/peloton-settings.service" ]] \
            && ! systemctl is-enabled --quiet peloton-settings.service 2>/dev/null; then
            SETTINGS_PAGE=false
        fi
    fi
}

# Started at boot whatever the display's mode (it drives no panel), and restarted for an
# upgrade's new code; or stopped and disabled.
start_settings_page() {
    if [[ "$SETTINGS_PAGE" == true ]]; then
        systemctl enable peloton-settings.service
        systemctl restart peloton-settings.service
    else
        systemctl disable --now peloton-settings.service 2>/dev/null || true
    fi
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

# Too small for Chromium: a 32-bit userland (Playwright ships no wheels for
# it) or under 768 MB of RAM.
low_spec_board() {
    local mem_kb
    [[ "$(getconf LONG_BIT 2>/dev/null)" == 32 ]] && return 0
    mem_kb="$(awk '/^MemTotal:/ {print $2}' "${MEMINFO:-/proc/meminfo}" 2>/dev/null || true)"
    [[ -n "$mem_kb" && "$mem_kb" -lt 786432 ]]
}

# A flag wins. Otherwise a board that already renews tokens keeps its mode
# (saved by this installer, or read off an older install's units and venv),
# and everything else goes by the hardware. Renewal stays off only when
# --no-auto-token said so: before that flag existed, "off" just meant an
# upgrade had been run without --auto-token.
resolve_token_mode() {
    local saved_mode="" saved_origin=""
    if [[ -n "$TOKEN_MODE" ]]; then
        TOKEN_MODE_SOURCE=flag
        TOKEN_MODE_ORIGIN=flag
        if [[ "$TOKEN_MODE" == browser ]] && low_spec_board; then
            echo "Warning: this board looks too small for Chromium (32-bit or under 768 MB); --no-browser suits it better." >&2
        fi
    else
        if [[ -f "$TOKEN_MODE_FILE" ]]; then
            read -r saved_mode saved_origin < "$TOKEN_MODE_FILE" || true
        elif [[ -f "$UNIT_DIR/peloton-led.service" ]] \
            && { systemctl is-enabled --quiet peloton-token-refresh.timer 2>/dev/null \
                 || [[ -f "$UNIT_DIR/peloton-led.service.d/manual.conf" ]]; }; then
            if [[ -x "$APP_DIR/venv/bin/python" ]] \
                && "$APP_DIR/venv/bin/python" -c 'import playwright' 2>/dev/null; then
                saved_mode=browser
            else
                saved_mode=no-browser
            fi
        fi
        if [[ -n "$saved_mode" && ( "$saved_mode" != none || "$saved_origin" == flag ) ]]; then
            TOKEN_MODE="$saved_mode"
            TOKEN_MODE_SOURCE=kept
            if [[ "$saved_origin" == flag ]]; then
                TOKEN_MODE_ORIGIN=flag
            fi
        elif low_spec_board; then
            TOKEN_MODE=no-browser
            TOKEN_MODE_SOURCE=detected
        else
            TOKEN_MODE=browser
            TOKEN_MODE_SOURCE=detected
        fi
    fi
    case "$TOKEN_MODE" in
        none) AUTO_TOKEN=false; NO_BROWSER=false ;;
        browser) AUTO_TOKEN=true; NO_BROWSER=false ;;
        no-browser) AUTO_TOKEN=true; NO_BROWSER=true ;;
        *) echo "Unknown token mode '$TOKEN_MODE' in $TOKEN_MODE_FILE; pass --auto-token, --no-browser or --no-auto-token." >&2
           exit 2 ;;
    esac
}

save_token_mode() {
    printf '%s %s\n' "$TOKEN_MODE" "$TOKEN_MODE_ORIGIN" > "$TOKEN_MODE_FILE"
    chmod 0644 "$TOKEN_MODE_FILE"
}

# The display service passes no --led-gpio-mapping (it used to force
# adafruit-hat), so the panel wiring comes from the config the service reads.
# Stop before touching a board whose config doesn't say, rather than let its
# panel fall back to the "regular" mapping and go dark.
check_gpio_mapping() {
    local config="$CONFIG_DIR/config.json" status=0
    if [[ -f "$SOURCE_DIR/config.json" ]]; then
        config="$SOURCE_DIR/config.json"
    elif [[ "$RECONFIGURE" == true || ! -f "$config" ]]; then
        return 0    # rewritten from packaging/config.pi.json, which sets it
    fi
    GPIO_MAPPING="$(python3 - "$config" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding='utf-8') as handle:
        matrix = json.load(handle).get('matrix') or {}
    mapping = matrix.get('gpio_mapping')
except (OSError, ValueError, AttributeError) as exc:
    sys.exit(f'Could not read {sys.argv[1]}: {exc}')
if not mapping:
    sys.exit(3)
print(mapping)
PY
)" || status=$?
    if ((status == 3)); then
        cat >&2 <<EOF
$config has no matrix.gpio_mapping. The display service no longer sets it,
so add it to the "matrix" section before upgrading (nothing has changed yet):

    "matrix": {"gpio_mapping": "adafruit-hat"}

Use "adafruit-hat-pwm" if the HAT has the GPIO4-GPIO18 jumper, or "regular"
for a panel wired straight to the GPIO header.
EOF
        exit 1
    elif ((status != 0)); then
        exit 1
    fi
}

is_interactive() {
    [[ -t 0 ]]
}

# adafruit-hat-pwm drives the panel with the PWM hardware the onboard audio
# also uses; with snd_bcm2835 loaded the driver exits at start. Turning the
# audio off edits the boot config, so ask first: no answer, no change.
check_pwm_audio() {
    [[ "$GPIO_MAPPING" == adafruit-hat-pwm ]] || return 0
    grep -q '^snd_bcm2835 ' "${PROC_MODULES:-/proc/modules}" 2>/dev/null || return 0
    local boot_config="${BOOT_CONFIG:-}" answer updated
    if [[ -z "$boot_config" ]]; then
        boot_config=/boot/firmware/config.txt
        [[ -f "$boot_config" ]] || boot_config=/boot/config.txt
    fi
    cat <<EOF

The config uses "adafruit-hat-pwm", but the Pi's onboard audio (snd_bcm2835)
is loaded. It shares the PWM hardware the jumper uses, so the display would
exit at start. Turning it off sets dtparam=audio=off in $boot_config
(backed up first) and blacklists snd_bcm2835; the Pi's 3.5 mm and HDMI
sound stop working. The panel doesn't use either.
EOF
    if ! is_interactive; then
        echo "Run this in an interactive terminal to answer, or set \"gpio_mapping\": \"adafruit-hat\". Nothing has changed." >&2
        exit 1
    fi
    read -r -p "Turn the onboard audio off? [y/N] " answer || answer=""
    case "$answer" in
        [yY]|[yY][eE][sS]) ;;
        *) echo "Nothing has changed. Answer y to use the jumper, or set \"gpio_mapping\": \"adafruit-hat\" to run without it." >&2
           exit 1 ;;
    esac
    # Plain cp: the boot partition is FAT, where -p's ownership fails as root.
    cp "$boot_config" "$boot_config.peloton-led.bak"
    updated="$(awk '/^dtparam=audio=/ {print "dtparam=audio=off"; done = 1; next} {print}
                    END {if (!done) print "dtparam=audio=off"}' "$boot_config")"
    printf '%s\n' "$updated" > "$boot_config"
    printf 'blacklist snd_bcm2835\n' > "${MODPROBE_DIR:-/etc/modprobe.d}/blacklist-rgb-matrix.conf"
    if modprobe -r snd_bcm2835 2>/dev/null; then
        echo "Onboard audio is off."
    else
        AUDIO_REBOOT=true
        echo "Onboard audio turns off at the next reboot; the display can't start until then." >&2
    fi
}

# The updater's backstops (self_update), run from this checkout with the app's venv:
# peloton-update (status, check, update, rollback), peloton-rollback, and a boot oneshot that
# rolls back an update a power cut stopped (enabled after daemon-reload). A oneshot, not ordered
# before the display: rolling back restarts the display and waits for it. No time limit: a
# rollback that reinstalls pip packages takes ages on a Pi Zero.
setup_updater() {
    local python="$APP_DIR/venv/bin/python"
    cat > "$UNIT_DIR/peloton-update-recover.service" <<UNIT
[Unit]
Description=Peloton LED: roll back an update that stopped midway
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$SOURCE_DIR
ExecStart=$python -m self_update recover
TimeoutStartSec=infinity

[Install]
WantedBy=multi-user.target
UNIT
    chmod 0644 "$UNIT_DIR/peloton-update-recover.service"
    cat > "$BIN_DIR/peloton-update" <<COMMAND
#!/bin/sh
# Peloton LED's updater, from the checkout it installs from (peloton-install.sh's):
# peloton-update check [--channel beta], sudo peloton-update update [--channel beta], --help
cd "$SOURCE_DIR" && exec "$python" -m self_update "\$@"
COMMAND
    cat > "$BIN_DIR/peloton-rollback" <<COMMAND
#!/bin/sh
# Undo Peloton LED's last update, config.json included: sudo peloton-rollback (peloton-install.sh's)
cd "$SOURCE_DIR" && exec "$python" -m self_update rollback "\$@"
COMMAND
    chmod 0755 "$BIN_DIR/peloton-update" "$BIN_DIR/peloton-rollback"
}

# Starts the display unless manual mode or --no-start says not to. Either way
# a display that was running when the install began is restarted, so it never
# keeps running the old code.
start_or_restart_display() {
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
    elif [[ "$DISPLAY_WAS_RUNNING" == true ]]; then
        echo "Restarting the running display on the new version"
        systemctl restart peloton-led.service
    fi
}

while (($#)); do
    case "$1" in
        --auto-token) TOKEN_MODE=browser; shift ;;
        --no-browser) TOKEN_MODE=no-browser; shift ;;
        --no-auto-token) TOKEN_MODE=none; shift ;;
        --reconfigure) RECONFIGURE=true; shift ;;
        --skip-matrix) SKIP_MATRIX=true; shift ;;
        --skip-packages) SKIP_PACKAGES=true; shift ;;
        --skip-requirements) SKIP_REQUIREMENTS=true; shift ;;
        --driver)
            [[ $# -ge 2 ]] || { echo "--driver requires a value" >&2; exit 2; }
            DRIVER_REF="$2"; shift 2 ;;
        --no-start) NO_START=true; shift ;;
        --manual) MANUAL=true; shift ;;
        --start-at-boot) MANUAL=false; shift ;;
        --settings-page) SETTINGS_PAGE=true; shift ;;
        --no-settings-page) SETTINGS_PAGE=false; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ "$(uname -s)" == "Linux" ]] || { echo "This installer must run on Linux." >&2; exit 1; }
[[ $EUID -eq 0 ]] || { echo "Run this installer with sudo." >&2; exit 1; }
[[ -f "$SOURCE_DIR/peloton_led.py" ]] || { echo "Run the installer from the project checkout." >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd is required." >&2; exit 1; }
resolve_start_mode
resolve_token_mode
resolve_settings_page
check_gpio_mapping
check_pwm_audio
# Before anything changes, so a display that crashes mid-upgrade still counts.
if systemctl is-active --quiet peloton-led.service 2>/dev/null; then
    DISPLAY_WAS_RUNNING=true
fi

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
# Saved now, so a re-run after a failure further down keeps this mode.
save_token_mode
install -d -m 0750 -o "$APP_USER" -g "$APP_USER" "$STATE_DIR"
# The display opens its log while still root (see peloton-led.service); owning
# the folder lets it rotate the log after dropping to $APP_USER.
install -d -m 0755 -o "$APP_USER" -g "$APP_USER" "$STATE_DIR/logs"

# self_update and version.py: the settings page's Updates card (the updater itself runs from the checkout).
for directory in assets display driver models peloton prepared_logos scripts self_update settings_page utils packaging; do
    rm -rf "$APP_DIR/$directory"
    cp -a "$SOURCE_DIR/$directory" "$APP_DIR/$directory"
done
# Folders earlier versions installed that the app no longer has.
rm -rf "$APP_DIR/api"
for file in peloton_led.py version.py requirements.txt requirements-auth.txt README.md config.json-example config.dual-users-example.json emulator_config.json; do
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
if [[ "$SKIP_REQUIREMENTS" == false ]]; then
    "$APP_DIR/venv/bin/python" -m pip install --upgrade pip
    "$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"
fi

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
    if [[ "$SKIP_REQUIREMENTS" == false ]]; then
        "$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/requirements-auth.txt"
    fi
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
install -m 0644 -o root -g root "$SOURCE_DIR/packaging/systemd/peloton-settings.service" "$UNIT_DIR/peloton-settings.service"
setup_updater

# The checkout's config.json, when present, is the live config: the services
# see it at $CONFIG_DIR/config.json through a read-only bind mount (below).
LIVE_CONFIG="$CONFIG_DIR/config.json"
if [[ -f "$SOURCE_DIR/config.json" ]]; then
    LIVE_CONFIG="$SOURCE_DIR/config.json"
fi
(cd "$APP_DIR" && "$APP_DIR/venv/bin/python" -c \
    "import sys; from peloton.config import load_config; load_config(sys.argv[1])" "$LIVE_CONFIG")
systemd-analyze verify "$UNIT_DIR/peloton-led.service" \
    "$UNIT_DIR/peloton-token-refresh.service" "$UNIT_DIR/peloton-token-refresh.timer" \
    "$UNIT_DIR/peloton-settings.service" "$UNIT_DIR/peloton-update-recover.service"
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
# The settings page writes the live config itself (no bind: a read-only bind can't be saved to),
# so it gets the checkout's path and that folder, for the atomic write and its .bak. Its Updates
# card updates this checkout (PELOTON_CHECKOUT): a check fetches into its .git.
install -d -m 0755 "$UNIT_DIR/peloton-settings.service.d"
{
    printf '[Service]\nEnvironment=PELOTON_CHECKOUT=%s\nReadWritePaths=%s\n' "$SOURCE_DIR" "$SOURCE_DIR/.git"
    if [[ "$LIVE_CONFIG" == "$SOURCE_DIR/config.json" ]]; then
        printf 'Environment=PELOTON_CONFIG=%s\nReadWritePaths=%s\n' "$LIVE_CONFIG" "$SOURCE_DIR"
    fi
} > "$UNIT_DIR/peloton-settings.service.d/project-config.conf"
if [[ "$MANUAL" == true && "$AUTO_TOKEN" == true ]]; then
    install -d -m 0755 "$UNIT_DIR/peloton-led.service.d" "$UNIT_DIR/peloton-token-refresh.timer.d"
    printf '[Unit]\nWants=peloton-token-refresh.service peloton-token-refresh.timer\n' \
        > "$UNIT_DIR/peloton-led.service.d/manual.conf"
    printf '[Unit]\nPartOf=peloton-led.service\n' \
        > "$UNIT_DIR/peloton-token-refresh.timer.d/manual.conf"
fi

systemctl daemon-reload
systemctl enable peloton-update-recover.service  # runs at each boot; nothing to do now
if [[ "$MANUAL" == true ]]; then
    # Undo boot-time enablement from an earlier non-manual install.
    systemctl disable peloton-led.service peloton-token-refresh.timer 2>/dev/null || true
else
    systemctl enable peloton-led.service
    if [[ "$AUTO_TOKEN" == true ]]; then
        systemctl enable peloton-token-refresh.timer
    fi
fi
# Switching renewal off: stop the timer too. In manual mode nothing else
# would, since the PartOf= drop-in that tied it to the display is gone.
if [[ "$AUTO_TOKEN" == false ]]; then
    systemctl disable --now peloton-token-refresh.timer 2>/dev/null || true
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
start_or_restart_display
start_settings_page

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
  Tokens:   $TOKEN_MODE ($TOKEN_MODE_SOURCE; override with --auto-token,
            --no-browser or --no-auto-token)
  Updates:  peloton-update check, then sudo peloton-update update
            (add --channel beta for develop-beta; sudo peloton-rollback undoes one)
EOF
if [[ "$SETTINGS_PAGE" == true ]]; then
    cat <<EOF
  Settings: http://$(hostname).local:$SETTINGS_PORT   (a PIN shows on the panel to sign in;
            --no-settings-page turns it off)
EOF
fi
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
if [[ "$AUDIO_REBOOT" == true ]]; then
    cat <<EOF

  REBOOT: the onboard audio couldn't be unloaded now; the display (using
  adafruit-hat-pwm) won't start until you run   sudo reboot
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
