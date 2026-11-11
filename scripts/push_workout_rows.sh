#!/usr/bin/env bash
# scripts/push_workout_rows.sh
# Put each rider's workout-compare row store on a board: build it here from this computer's rows and
# saved responses (scripts/build_board_rows.py: in-scope workouts of the last 760 days), copy it
# over, and install it beside the board's cache in
# /var/lib/peloton-led as <cache stem>.workout-rows.json (peloton-led, 0600).
# Re-run after a ROW_VERSION bump: the board ignores rows of an older version.
#
# The board's file names come from the board's config (--board-config, default config.json, the Pi's
# copy); the rows are built from this computer's (--config, default config.local.json).
#
# Usage: scripts/push_workout_rows.sh user@board [--config config.local.json] [--board-config config.json]
set -Eeuo pipefail

usage() {
    echo "Usage: $0 user@board [--config config.local.json] [--board-config config.json]" >&2
    exit 2
}

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BOARD=""
CONFIG="$REPO_DIR/config.local.json"
BOARD_CONFIG="$REPO_DIR/config.json"
while (($#)); do
    case "$1" in
        --config)
            [[ $# -ge 2 ]] || usage
            CONFIG="$2"; shift 2 ;;
        --board-config)
            [[ $# -ge 2 ]] || usage
            BOARD_CONFIG="$2"; shift 2 ;;
        -h|--help) usage ;;
        -*) echo "Unknown option: $1" >&2; usage ;;
        *) [[ -z "$BOARD" ]] || usage; BOARD="$1"; shift ;;
    esac
done
[[ -n "$BOARD" ]] || usage
[[ -f "$CONFIG" ]] || { echo "No config at $CONFIG (pass --config)." >&2; exit 1; }
[[ -f "$BOARD_CONFIG" ]] || { echo "No board config at $BOARD_CONFIG (pass --board-config)." >&2; exit 1; }

PYTHON="${PELOTON_PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
    PYTHON="$REPO_DIR/venv/bin/python"
    [[ -x "$PYTHON" ]] || PYTHON="python3"
fi

OUT_DIR="$(mktemp -d)"
CONTROL_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$OUT_DIR"
    ssh -o ControlPath="$CONTROL_DIR/ssh" -O exit "$BOARD" >/dev/null 2>&1 || true
    rm -rf "$CONTROL_DIR"
}
trap cleanup EXIT
SSH_OPTS=(-o ControlMaster=auto -o ControlPath="$CONTROL_DIR/ssh" -o ControlPersist=120)

echo "==> Building each rider's board store on this computer"
riders="$("$PYTHON" "$REPO_DIR/scripts/build_board_rows.py" --config "$CONFIG" --board-config "$BOARD_CONFIG" --list)"
[[ -n "$riders" ]] || { echo "The config lists no riders." >&2; exit 1; }
names=()
while IFS=$'\t' read -r rider name; do
    [[ -n "$rider" ]] || continue
    "$PYTHON" "$REPO_DIR/scripts/build_board_rows.py" --rider "$rider" --config "$CONFIG" --out "$OUT_DIR/$name"
    [[ -s "$OUT_DIR/$name" ]] || { echo "No store built for $rider." >&2; exit 1; }
    names+=("$name")
done <<< "$riders"

echo "==> Copying to $BOARD"
REMOTE_DIR="$(ssh "${SSH_OPTS[@]}" "$BOARD" 'mktemp -d')"
scp -q "${SSH_OPTS[@]}" "${names[@]/#/$OUT_DIR/}" "$BOARD:$REMOTE_DIR/"

echo "==> Installing into /var/lib/peloton-led and restarting the display (sudo on the board)"
# Each file goes in under a .new name, then moves into place, so the display never reads half a file.
# The temporary copies go even on failure. try-restart leaves a board whose display is off (manual
# mode) off. -t so sudo can prompt.
install_cmds=""
for name in "${names[@]}"; do
    install_cmds+=" && sudo install -m 0600 -o peloton-led -g peloton-led '$REMOTE_DIR/$name' '/var/lib/peloton-led/$name.new' && sudo mv -f '/var/lib/peloton-led/$name.new' '/var/lib/peloton-led/$name'"
done
ssh -t "${SSH_OPTS[@]}" "$BOARD" "
    status=0
    {
        true$install_cmds && sudo systemctl try-restart peloton-led.service
    } || status=\$?
    rm -rf '$REMOTE_DIR'
    exit \$status
"
echo "==> Done: ${names[*]}"
