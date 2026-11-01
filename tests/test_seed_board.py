import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'seed_board.sh'

FAKE_SSH = '''#!/usr/bin/env bash
# Stand-in for ssh: "mktemp -d" makes the board's temp dir, -O exit closes the
# shared connection, anything else is logged as the remote command.
echo "ssh $*" >> "$FAKE_LOG"
for arg in "$@"; do last="$arg"; done
case "$*" in
    *" -O exit "*) exit 0 ;;
esac
if [[ "$last" == "mktemp -d" ]]; then
    mkdir -p "$FAKE_REMOTE/seed" && echo "$FAKE_REMOTE/seed"
    exit 0
fi
printf '%s\\n' "$last" > "$FAKE_REMOTE/command"
exit "${FAKE_SSH_STATUS:-0}"
'''

FAKE_SCP = '''#!/usr/bin/env bash
# Stand-in for scp: copy the local files into the "remote" path after host:.
echo "scp $*" >> "$FAKE_LOG"
args=(); for arg in "$@"; do args+=("$arg"); done
target="${args[${#args[@]}-1]}"; target="${target#*:}"
for arg in "${args[@]}"; do [[ -f "$arg" ]] && cp "$arg" "$target"; done
exit 0
'''

FAKE_PYTHON = '''#!/usr/bin/env bash
# Stand-in for refresh_cookies.py --seed-dir DIR: write two riders' pairs.
echo "python $*" >> "$FAKE_LOG"
[[ -n "${FAKE_SEED_FAIL:-}" ]] && { echo "Seeding failed: login" >&2; exit 1; }
while (($#)); do [[ "$1" == "--seed-dir" ]] && dir="$2"; shift; done
for rider in joel jen; do
    echo token > "$dir/cookies-$rider.txt"
    echo '{"refresh_token": "r"}' > "$dir/cookies-$rider.refresh.json"
done
'''


def _run(tmp_path, **env):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir(exist_ok=True)
    for name, body in (('ssh', FAKE_SSH), ('scp', FAKE_SCP), ('fake-python', FAKE_PYTHON)):
        path = bin_dir / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    local_tmp = tmp_path / 'local-tmp'
    remote = tmp_path / 'remote'
    local_tmp.mkdir(exist_ok=True)
    remote.mkdir(exist_ok=True)
    config = tmp_path / 'config.json'
    config.write_text('{}')
    result = subprocess.run(
        ['bash', str(SCRIPT), 'admin@board.local', '--config', str(config)],
        capture_output=True, text=True,
        env={**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}', 'TMPDIR': str(local_tmp),
             'PELOTON_PYTHON': str(bin_dir / 'fake-python'), 'FAKE_LOG': str(tmp_path / 'log'),
             'FAKE_REMOTE': str(remote), **env})
    return result, local_tmp, remote, (tmp_path / 'log').read_text() if (tmp_path / 'log').exists() else ''


def test_seed_board_copies_installs_and_cleans_up_both_sides(tmp_path):
    result, local_tmp, remote, log = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    names = ['cookies-jen.txt', 'cookies-joel.txt', 'cookies-jen.refresh.json', 'cookies-joel.refresh.json']
    assert sorted(p.name for p in (remote / 'seed').iterdir()) == sorted(names)
    assert '--no-install-hint' in log and '--seed-dir' in log
    command = (remote / 'command').read_text()
    assert 'sudo install -m 0600 -o peloton-led -g peloton-led' in command
    assert all(name in command for name in names) and '/var/lib/peloton-led/' in command
    # The board's copies go whether or not install worked, before the status check.
    assert command.index(f"rm -rf '{remote / 'seed'}'") < command.index('--status --all-users')
    # The status check runs as peloton-led, which can't read admin's temp dir.
    assert command.index("cd /") < command.index('sudo -u peloton-led')
    assert ' -t ' in log  # sudo on the board can prompt for a password.
    # One shared connection, closed at the end; no local copies left behind.
    assert all('ControlPath=' in line for line in log.splitlines() if line.startswith(('ssh', 'scp')))
    assert ' -O exit ' in log
    assert list(local_tmp.iterdir()) == []


def test_seed_board_stops_before_copying_when_login_fails(tmp_path):
    result, local_tmp, remote, log = _run(tmp_path, FAKE_SEED_FAIL='1')
    assert result.returncode != 0
    assert 'Seeding failed' in result.stderr
    assert 'scp ' not in log and not (remote / 'command').exists()
    assert list(local_tmp.iterdir()) == []


def test_seed_board_reports_a_failed_install(tmp_path):
    result, local_tmp, _, _ = _run(tmp_path, FAKE_SSH_STATUS='1')
    assert result.returncode != 0
    assert list(local_tmp.iterdir()) == []


def test_seed_board_requires_a_board(tmp_path):
    result = subprocess.run(['bash', str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 2 and 'Usage' in result.stderr
