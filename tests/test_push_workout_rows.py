import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'push_workout_rows.sh'

FAKE_SSH = '''#!/usr/bin/env bash
echo "ssh $*" >> "$FAKE_LOG"
for arg in "$@"; do last="$arg"; done
case "$*" in
    *" -O exit "*) exit 0 ;;
esac
if [[ "$last" == "mktemp -d" ]]; then
    mkdir -p "$FAKE_REMOTE/push" && echo "$FAKE_REMOTE/push"
    exit 0
fi
printf '%s\\n' "$last" > "$FAKE_REMOTE/command"
exit "${FAKE_SSH_STATUS:-0}"
'''

FAKE_SCP = '''#!/usr/bin/env bash
echo "scp $*" >> "$FAKE_LOG"
args=(); for arg in "$@"; do args+=("$arg"); done
target="${args[${#args[@]}-1]}"; target="${target#*:}"
for arg in "${args[@]}"; do [[ -f "$arg" ]] && cp "$arg" "$target"; done
exit 0
'''

FAKE_PYTHON = '''#!/usr/bin/env bash
# Stand-in for scripts/build_board_rows.py: --list names two riders, --out writes a file.
echo "python $*" >> "$FAKE_LOG"
[[ -n "${FAKE_BUILD_FAIL:-}" ]] && { echo "Build failed" >&2; exit 1; }
out=""; list=""
while (($#)); do
    [[ "$1" == "--out" ]] && out="$2"
    [[ "$1" == "--list" ]] && list=1
    shift
done
if [[ -n "$list" ]]; then
    printf 'joel\\tdashboard-cache-joel.workout-rows.json\\n'
    printf 'jen\\tdashboard-cache-jen.workout-rows.json\\n'
else
    echo '{"version": 1, "rows": {}}' > "$out"
fi
'''


def _run(tmp_path, args=None, **env):
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
    board_config = tmp_path / 'board-config.json'
    board_config.write_text('{}')
    default = ['admin@board.local', '--config', str(config), '--board-config', str(board_config)]
    result = subprocess.run(
        ['bash', str(SCRIPT), *(args if args is not None else default)],
        capture_output=True, text=True,
        env={**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}', 'TMPDIR': str(local_tmp),
             'PELOTON_PYTHON': str(bin_dir / 'fake-python'), 'FAKE_LOG': str(tmp_path / 'log'),
             'FAKE_REMOTE': str(remote), **env})
    log = (tmp_path / 'log').read_text() if (tmp_path / 'log').exists() else ''
    return result, local_tmp, remote, log


def test_push_builds_copies_installs_and_restarts(tmp_path):
    result, local_tmp, remote, log = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert f"--board-config {tmp_path / 'board-config.json'} --list" in log
    names = ['dashboard-cache-jen.workout-rows.json', 'dashboard-cache-joel.workout-rows.json']
    assert sorted(p.name for p in (remote / 'push').iterdir()) == names
    assert '--rider joel' in log and '--rider jen' in log and '--out' in log
    command = (remote / 'command').read_text()
    for name in names:
        path = f'/var/lib/peloton-led/{name}'
        assert f"sudo install -m 0600 -o peloton-led -g peloton-led '{remote / 'push' / name}' '{path}.new'" in command
        assert f"sudo mv -f '{path}.new' '{path}'" in command
    assert command.index('sudo mv -f') < command.index('sudo systemctl try-restart peloton-led.service')
    assert command.index('try-restart') < command.index(f"rm -rf '{remote / 'push'}'")
    assert ' -t ' in log
    assert all('ControlPath=' in line for line in log.splitlines() if line.startswith(('ssh', 'scp')))
    assert ' -O exit ' in log
    assert list(local_tmp.iterdir()) == []


def test_push_stops_before_copying_when_the_build_fails(tmp_path):
    result, local_tmp, remote, log = _run(tmp_path, FAKE_BUILD_FAIL='1')
    assert result.returncode != 0 and 'Build failed' in result.stderr
    assert 'scp ' not in log and not (remote / 'command').exists()
    assert list(local_tmp.iterdir()) == []


def test_push_reports_a_failed_install(tmp_path):
    result, local_tmp, _, _ = _run(tmp_path, FAKE_SSH_STATUS='1')
    assert result.returncode != 0
    assert list(local_tmp.iterdir()) == []


def test_push_usage_and_missing_config(tmp_path):
    result = subprocess.run(['bash', str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 2 and 'Usage' in result.stderr
    result, *_ = _run(tmp_path, args=['admin@board.local', '--config', str(tmp_path / 'nope.json')])
    assert result.returncode == 1 and 'No config' in result.stderr
    config = tmp_path / 'config.json'
    result, *_ = _run(tmp_path, args=['admin@board.local', '--config', str(config),
                                      '--board-config', str(tmp_path / 'nope.json')])
    assert result.returncode == 1 and 'No board config' in result.stderr
