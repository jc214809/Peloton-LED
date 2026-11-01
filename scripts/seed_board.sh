#!/usr/bin/env bash
# scripts/seed_board.sh
# Give a board its own Peloton login from this computer: log every rider in
# (refresh_cookies.py --seed-dir), copy the token + refresh-token pairs to the
# board, install them for the peloton-led service, show their status, and
# delete every copy outside /var/lib/peloton-led.
#
# Usage: scripts/seed_board.sh admin@pelotonpi.local [--config path/to/config.json]
#
# The config must list the board's riders (names and token file names).
# Refresh tokens are single-use, so each run starts a new login for that board
# only; never point two boards at the same seed.
set -Eeuo pipefail

usage() {
    echo "Usage: $0 user@board [--config path/to/config.json]" >&2
    exit 2
}

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BOARD=""
CONFIG="$REPO_DIR/config.json"
while (($#)); do
    case "$1" in
        --config)
            [[ $# -ge 2 ]] || usage
            CONFIG="$2"; shift 2 ;;
        -h|--help) usage ;;
        -*) echo "Unknown option: $1" >&2; usage ;;
        *) [[ -z "$BOARD" ]] || usage; BOARD="$1"; shift ;;
    esac
done
[[ -n "$BOARD" ]] || usage
[[ -f "$CONFIG" ]] || { echo "No config at $CONFIG (pass --config)." >&2; exit 1; }

PYTHON="${PELOTON_PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
    PYTHON="$REPO_DIR/venv/bin/python"
    [[ -x "$PYTHON" ]] || PYTHON="python3"
fi

SEED_DIR="$(mktemp -d)"
CONTROL_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$SEED_DIR"
    ssh -o ControlPath="$CONTROL_DIR/ssh" -O exit "$BOARD" >/dev/null 2>&1 || true
    rm -rf "$CONTROL_DIR"
}
trap cleanup EXIT

# One SSH connection for every step, so a password is asked for once.
SSH_OPTS=(-o ControlMaster=auto -o ControlPath="$CONTROL_DIR/ssh" -o ControlPersist=120)

echo "==> Logging riders in on this computer"
"$PYTHON" "$REPO_DIR/scripts/refresh_cookies.py" --seed-dir "$SEED_DIR" --config "$CONFIG" --no-install-hint
files=()
for file in "$SEED_DIR"/cookies*.txt "$SEED_DIR"/cookies*.refresh.json; do
    [[ -f "$file" ]] && files+=("$(basename "$file")")
done
((${#files[@]})) || { echo "Seeding wrote no token files." >&2; exit 1; }
echo "    ${files[*]}"

echo "==> Copying to $BOARD"
REMOTE_DIR="$(ssh "${SSH_OPTS[@]}" "$BOARD" 'mktemp -d')"
scp -q "${SSH_OPTS[@]}" "${files[@]/#/$SEED_DIR/}" "$BOARD:$REMOTE_DIR/"

echo "==> Installing into /var/lib/peloton-led (sudo on the board)"
# -t so sudo can prompt; the copies in $REMOTE_DIR are removed even on failure.
ssh -t "${SSH_OPTS[@]}" "$BOARD" "
    cd '$REMOTE_DIR' &&
    sudo install -m 0600 -o peloton-led -g peloton-led ${files[*]} /var/lib/peloton-led/;
    installed=\$?
    rm -rf '$REMOTE_DIR'
    [ \$installed -eq 0 ] || exit \$installed
    cd /  # The service account can't read admin's (now deleted) temp dir.
    sudo -u peloton-led /opt/peloton-led/venv/bin/python /opt/peloton-led/scripts/refresh_cookies.py \
        --status --all-users --config /etc/peloton-led/config.json --cookies /var/lib/peloton-led/cookies.txt
"

echo "==> Done. The display picks up the new tokens by itself within a few seconds."
