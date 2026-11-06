import json
import subprocess

import pytest
from pathlib import Path

from peloton.config import load_config


ROOT = Path(__file__).resolve().parents[1]


def test_installer_shell_syntax_and_upgrade_preservation_contract():
    installer = ROOT / 'peloton-install.sh'
    subprocess.run(['bash', '-n', str(installer)], check=True)
    text = installer.read_text()
    assert 'if [[ ! -f "$CONFIG_DIR/config.json" || "$RECONFIGURE" == true ]]' in text
    assert 'if [[ ! -f "$STATE_DIR/cookies.txt"' in text
    assert 'rm -rf "$APP_DIR/$directory"' in text
    assert 'rm -rf "$CONFIG_DIR' not in text
    assert 'rm -rf "$STATE_DIR' not in text
    # Upstream rpi-rgb-led-matrix dropped its old make-based Python bindings
    # build in favor of a scikit-build-core/cmake pip install from the repo
    # root; guard against regressing back to the removed make targets.
    assert 'make -C "$driver_dir"' not in text
    assert 'pip install "$driver_dir"' in text


def test_installer_keeps_private_umask_away_from_the_venv():
    text = (ROOT / 'peloton-install.sh').read_text()
    # A bare `umask 077` leaked into venv creation, so the service account got
    # "Permission denied" executing venv/bin/python (status=203/EXEC).
    assert '\n    umask 077\n' not in text
    assert '(umask 077 && python3 "$SOURCE_DIR/scripts/setup_config.py"' in text
    assert text.index('chmod -R a+rX "$APP_DIR"') > text.index('pip install "$driver_dir"')
    assert text.index('chmod -R a+rX "$APP_DIR"') < text.index('systemctl daemon-reload')


def test_installer_uses_interactive_setup_script_not_silent_migration():
    text = (ROOT / 'peloton-install.sh').read_text()
    # Config creation/rider setup must be one interactive step (config.json +
    # auth.env together), not the old silent migrate_pi_config.py call that
    # left auth.env creation as a separate, easy-to-miss --auto-token path.
    assert 'scripts/setup_config.py' in text
    assert 'scripts/migrate_pi_config.py' not in text
    assert '--reconfigure' in text
    assert '[[ -t 0 ]]' in text


def test_pi_config_uses_writable_state_cache():
    path = ROOT / 'packaging' / 'config.pi.json'
    parsed = load_config(path)
    assert parsed['display']['cache_path'] == '/var/lib/peloton-led/dashboard-cache.json'
    assert json.loads(path.read_text())['debug'] is False
    # Fresh installs get the HAT wiring from the config, not the service.
    assert parsed['matrix']['gpio_mapping'] == 'adafruit-hat'


def test_systemd_units_have_managed_runtime_and_token_safety():
    unit_dir = ROOT / 'packaging' / 'systemd'
    display = (unit_dir / 'peloton-led.service').read_text()
    refresh = (unit_dir / 'peloton-token-refresh.service').read_text()
    timer = (unit_dir / 'peloton-token-refresh.timer').read_text()
    # Starts as root only to map the panel's hardware registers, then the
    # driver drops to peloton-led (PELOTON_MATRIX_USER) before any token or
    # cache is touched; every extra right goes with root.
    assert 'User=root' in display and 'Group=peloton-led' in display
    assert 'Environment=PELOTON_MATRIX_USER=peloton-led' in display
    assert 'AmbientCapabilities' not in display
    bounding = display.split('CapabilityBoundingSet=', 1)[1].split('\n', 1)[0].split()
    assert sorted(bounding) == sorted(['CAP_SYS_RAWIO', 'CAP_SYS_NICE', 'CAP_IPC_LOCK',
                                       'CAP_SETUID', 'CAP_SETGID', 'CAP_DAC_OVERRIDE'])
    assert 'NoNewPrivileges=true' in display and 'ProtectSystem=strict' in display
    assert 'ProtectHome=true' in display
    assert 'Restart=on-failure' in display
    assert '--cookies /var/lib/peloton-led/cookies.txt' in display
    # A command-line flag beats config.json, so the service must not set the
    # wiring: each board's config chooses adafruit-hat or adafruit-hat-pwm.
    assert '--led-' not in display
    assert 'ReadWritePaths=/var/lib/peloton-led' in display
    # ProtectSystem=strict makes /opt/peloton-led read-only, so utils/debug.py's
    # default log location (next to the code) must be redirected somewhere
    # writable, or the app crashes on startup trying to create it.
    assert 'PELOTON_LOG_DIR=/var/lib/peloton-led/logs' in display
    # Optional: refresh-token renewal needs no credentials.
    assert 'EnvironmentFile=-/etc/peloton-led/auth.env' in refresh
    assert 'PELOTON_CHROMIUM_EXECUTABLE=/usr/bin/chromium' in refresh
    # Progress ("Opening ...") reaches the journal live, not only at exit.
    assert 'Environment=PYTHONUNBUFFERED=1' in refresh
    assert ' --ensure ' in refresh
    assert ' --all-users ' in refresh
    assert 'OnBootSec=5min' in timer
    assert 'OnUnitActiveSec=1h' in timer
    assert 'Persistent=true' in timer


def test_installer_manual_mode_never_enables_at_boot():
    text = (ROOT / 'peloton-install.sh').read_text()
    assert '--manual) MANUAL=true; shift ;;' in text
    assert '--start-at-boot) MANUAL=false; shift ;;' in text
    # Decided after argument parsing, before any unit is installed or enabled.
    assert text.index('resolve_start_mode\n') < text.index('systemctl daemon-reload')
    enable_block = text.split('if [[ "$MANUAL" == true ]]; then\n    # Undo boot-time', 1)[1]
    manual_branch, default_branch = enable_block.split('else', 1)
    assert 'systemctl disable peloton-led.service peloton-token-refresh.timer' in manual_branch
    assert 'systemctl enable' not in manual_branch
    assert 'systemctl enable peloton-led.service' in default_branch
    # Token renewal follows the display: started with it, stopped with it,
    # and the drop-ins are removed again on a later non-manual install.
    assert 'Wants=peloton-token-refresh.service peloton-token-refresh.timer' in text
    assert 'PartOf=peloton-led.service' in text
    assert 'rm -f "$UNIT_DIR/peloton-led.service.d/manual.conf"' in text



def test_installer_binds_the_checkout_config_into_both_services():
    text = (ROOT / 'peloton-install.sh').read_text()
    # ProtectHome hides the checkout, so the services see its config.json via
    # a read-only bind; "-" keeps the /etc file when the checkout has none.
    assert "printf '[Service]\\nBindReadOnlyPaths=-%s:%s\\n' \"$SOURCE_DIR/config.json\" \"$CONFIG_DIR/config.json\"" in text
    assert 'for unit in peloton-led.service peloton-token-refresh.service; do' in text
    assert 'project-config.conf' in text
    # The installer validates and reads whichever config the services will see.
    assert 'LIVE_CONFIG="$SOURCE_DIR/config.json"' in text
    assert 'load_config(sys.argv[1])" "$LIVE_CONFIG"' in text
    assert 'sync_config' not in text


def test_installer_builds_the_driver_against_matching_pillow_headers():
    text = (ROOT / 'peloton-install.sh').read_text()
    # Upstream's binding includes Pillow's private Imaging.h; pip's Pillow ships
    # none, and a distro python3-pil may not match the installed struct layout.
    fetch = '"$APP_DIR/scripts/fetch_pillow_headers.py" "$pillow_headers"'
    build = 'CFLAGS="-I$pillow_headers ${CFLAGS:-}" "$APP_DIR/venv/bin/python" -m pip install "$driver_dir"'
    assert fetch in text and build in text
    assert text.index('pip install -r "$APP_DIR/requirements.txt"') < text.index(fetch) < text.index(build)
    assert 'python3-pil' not in text


def test_installer_no_browser_mode_skips_chromium_and_playwright():
    text = (ROOT / 'peloton-install.sh').read_text()
    assert 'if [[ "$AUTO_TOKEN" == true && "$NO_BROWSER" == false ]]; then\n        packages+=(chromium)' in text
    no_browser, rest = text.split('if [[ "$NO_BROWSER" == true ]]; then\n    # Renewal', 1)[1].split('elif', 1)
    assert 'pip uninstall -y playwright' in no_browser
    assert 'requirements-auth.txt' not in no_browser
    assert 'requirements-auth.txt' in rest.split('fi', 1)[0]


def test_installer_copies_seeded_refresh_tokens_without_overwriting():
    text = (ROOT / 'peloton-install.sh').read_text()
    assert 'for source_token in "$SOURCE_DIR"/cookies-*.txt "$SOURCE_DIR"/cookies*.refresh.json; do' in text
    loop = text.split('"$SOURCE_DIR"/cookies*.refresh.json; do', 1)[1].split('done', 1)[0]
    assert 'if [[ ! -f "$target_token" ]]' in loop
    assert 'install -m 0600 -o "$APP_USER"' in loop


def test_refresh_token_files_are_gitignored():
    assert '*.refresh.json' in (ROOT / '.gitignore').read_text().splitlines()


def _run_install_ending(tmp_path, tokens, no_browser, sudo_user='admin'):
    """Run the installer's closing seeding hint with stand-in variables."""
    import os
    text = (ROOT / 'peloton-install.sh').read_text()
    ending = text[text.index('# Checked last:'):]
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / 'hostname').write_text('#!/bin/sh\necho PelotonPi\n')
    (bin_dir / 'hostname').chmod(0o755)
    setup = (f'set -Eeuo pipefail\nNO_BROWSER={str(no_browser).lower()}\n'
             f'configured_tokens=({" ".join(str(t) for t in tokens)})\n')
    env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}'}
    env.pop('SUDO_USER', None)
    if sudo_user:
        env['SUDO_USER'] = sudo_user
    result = subprocess.run(['bash', '-c', setup + ending], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_installer_ends_with_the_seed_command_when_a_rider_has_no_token(tmp_path):
    joel, jen = tmp_path / 'cookies-joel.txt', tmp_path / 'cookies-jen.txt'
    joel.write_text('token')
    for no_browser in (True, False):
        out = _run_install_ending(tmp_path, [joel, jen], no_browser)
        assert 'NEXT STEP' in out and str(jen) in out and str(joel) not in out
        assert 'scripts/seed_board.sh admin@PelotonPi.local' in out


def test_installer_only_reminds_no_browser_boards_once_tokens_exist(tmp_path):
    joel = tmp_path / 'cookies-joel.txt'
    joel.write_text('token')
    out = _run_install_ending(tmp_path, [joel], no_browser=True, sudo_user=None)
    assert 'NEXT STEP' not in out
    assert 'scripts/seed_board.sh <user>@PelotonPi.local' in out
    assert _run_install_ending(tmp_path, [joel], no_browser=False) == ''


def test_installer_lists_token_paths_even_with_no_start():
    text = (ROOT / 'peloton-install.sh').read_text()
    # The closing hint needs the token list whether or not services start.
    assert text.index('mapfile -t configured_tokens') < text.index('\nstart_or_restart_display\n')


def _start_mode(tmp_path, flag_value, enabled_now):
    """Run resolve_start_mode with a fake systemctl; return MANUAL, NO_START, KEPT_BOOT_START."""
    import os
    text = (ROOT / 'peloton-install.sh').read_text()
    start = text.index('resolve_start_mode() {')
    function = text[start:text.index('\n}\n', start) + 3]
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / 'systemctl').write_text(f'#!/bin/sh\nexit {0 if enabled_now else 1}\n')
    (bin_dir / 'systemctl').chmod(0o755)
    script = (f'set -Eeuo pipefail\nMANUAL="{flag_value}"\nNO_START=false\nKEPT_BOOT_START=false\n'
              f'{function}resolve_start_mode\necho "$MANUAL $NO_START $KEPT_BOOT_START"\n')
    env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}'}
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


@pytest.mark.parametrize('flag,enabled_now,expected', [
    ('', False, ['true', 'true', 'false']),    # fresh install or a manual board: manual
    ('', True, ['false', 'false', 'true']),    # upgrade of a boot-start board: keep it
    ('true', True, ['true', 'true', 'false']),   # --manual switches a boot-start board
    ('false', False, ['false', 'false', 'false']),  # --start-at-boot
    ('false', True, ['false', 'false', 'false']),
])
def test_manual_is_the_default_but_upgrades_keep_boot_start(tmp_path, flag, enabled_now, expected):
    assert _start_mode(tmp_path, flag, enabled_now) == expected


def test_installer_summary_explains_a_kept_boot_start():
    text = (ROOT / 'peloton-install.sh').read_text()
    assert 'elif [[ "$KEPT_BOOT_START" == true ]]; then' in text
    assert 're-run with --manual to switch this board' in text
    assert 'For a dedicated board, re-run with --start-at-boot.' in text


def test_every_path_the_installer_copies_exists():
    # A folder deleted from the repo but still listed here stops the install
    # halfway (set -e on a failed cp), as api/ once did.
    import re
    text = (ROOT / 'peloton-install.sh').read_text()
    directories = re.search(r'^for directory in (.+); do$', text, re.M).group(1).split()
    files = re.search(r'^for file in (.+); do$', text, re.M).group(1).split()
    assert directories and files
    # Check what git tracks, not the disk: a deleted folder's leftover
    # __pycache__ would otherwise hide the problem on a developer's machine.
    tracked = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.splitlines()
    for name in directories:
        assert any(path.startswith(f'{name}/') for path in tracked), \
            f'installer copies folder {name}/, which the repo no longer has'
    for name in files:
        assert name in tracked, f'installer copies {name}, which the repo no longer has'


def _installer_snippets():
    """The installer's inline Python blocks that read riders from the live config."""
    import re
    text = (ROOT / 'peloton-install.sh').read_text()
    return re.findall(r'"\$APP_DIR" "\$CONFIG_DIR" <<\'PY\'\n(.*?)\nPY\n', text, re.S)


def test_installer_rider_snippets_resolve_default_token_paths_like_the_app(tmp_path):
    # A rider without token_path crashed both snippets with KeyError on upgrade.
    import sys
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'users': [
        {'name': 'Joel'}, {'name': 'Jen', 'token_path': '/var/lib/peloton-led/cookies-jen.txt'}]}))
    tokens, summary = _installer_snippets()
    run = lambda code: subprocess.run([sys.executable, '-', str(config), str(ROOT), '/etc/peloton-led'],
                                      input=code, text=True, capture_output=True, check=True).stdout
    assert run(tokens).split() == ['/etc/peloton-led/cookies-joel.txt', '/var/lib/peloton-led/cookies-jen.txt']
    assert run(summary).strip() == ('2 riders: Joel (/etc/peloton-led/cookies-joel.txt), '
                                    'Jen (/var/lib/peloton-led/cookies-jen.txt)')
    config.write_text('{}')
    assert run(tokens).strip() == '/var/lib/peloton-led/cookies.txt'


def _installer_function(name):
    text = (ROOT / 'peloton-install.sh').read_text()
    start = text.index(f'{name}() {{')
    return text[start:text.index('\n}\n', start) + 3]


def _fake_bin(tmp_path, **scripts):
    import os
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir(exist_ok=True)
    for name, body in scripts.items():
        (bin_dir / name).write_text(f'#!/bin/sh\n{body}\n')
        (bin_dir / name).chmod(0o755)
    return {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}'}


def _token_mode(tmp_path, flag='', saved=None, installed=False, venv_only=False, timer_enabled=False,
                manual_conf=False, playwright=False, long_bit=64, mem_kb=3884000):
    """Run resolve_token_mode then save_token_mode against a fake board.

    Returns (stdout fields, stderr, exit code); the saved file is left at
    tmp_path/etc/token-mode for a second run to read."""
    app_dir, unit_dir, config_dir = tmp_path / 'opt', tmp_path / 'units', tmp_path / 'etc'
    for directory in (app_dir, unit_dir, config_dir):
        directory.mkdir(exist_ok=True)
    if saved is not None:
        (config_dir / 'token-mode').write_text(saved + '\n' if saved else '')
    if installed:
        (unit_dir / 'peloton-led.service').write_text('[Service]\n')
    if (installed or venv_only) and not (app_dir / 'venv').exists():
        (app_dir / 'venv' / 'bin').mkdir(parents=True)
        python = app_dir / 'venv' / 'bin' / 'python'
        python.write_text(f'#!/bin/sh\nexit {0 if playwright else 1}\n')
        python.chmod(0o755)
    if manual_conf:
        (unit_dir / 'peloton-led.service.d').mkdir(exist_ok=True)
        (unit_dir / 'peloton-led.service.d' / 'manual.conf').write_text('[Unit]\n')
    meminfo = tmp_path / 'meminfo'
    meminfo.write_text(f'MemTotal:       {mem_kb} kB\nMemFree:          100000 kB\n')
    env = _fake_bin(tmp_path,
                    systemctl=f'[ "$3" = peloton-token-refresh.timer ] && exit {0 if timer_enabled else 1}; exit 1',
                    getconf=f'echo {long_bit}')
    env['MEMINFO'] = str(meminfo)
    script = (f'set -Eeuo pipefail\nAPP_DIR="{app_dir}"\nUNIT_DIR="{unit_dir}"\n'
              f'TOKEN_MODE_FILE="{config_dir}/token-mode"\nTOKEN_MODE="{flag}"\nTOKEN_MODE_SOURCE=""\n'
              f'TOKEN_MODE_ORIGIN=auto\nAUTO_TOKEN=unset\nNO_BROWSER=unset\n'
              f'{_installer_function("low_spec_board")}{_installer_function("resolve_token_mode")}'
              f'{_installer_function("save_token_mode")}'
              'resolve_token_mode\nsave_token_mode\necho "$TOKEN_MODE $TOKEN_MODE_SOURCE $AUTO_TOKEN $NO_BROWSER"\n')
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True, env=env)
    return result.stdout.split(), result.stderr, result.returncode


@pytest.mark.parametrize('board,expected', [
    ({}, 'browser detected true false'),                          # 64-bit, 4 GB
    ({'long_bit': 32}, 'no-browser detected true true'),          # 32-bit userland
    ({'mem_kb': 443000}, 'no-browser detected true true'),        # 512 MB board
    ({'mem_kb': 786431}, 'no-browser detected true true'),
    ({'mem_kb': 908000}, 'browser detected true false'),          # 1 GB board
])
def test_fresh_install_picks_token_mode_from_the_hardware(tmp_path, board, expected):
    out, err, code = _token_mode(tmp_path, **board)
    assert code == 0, err
    assert ' '.join(out) == expected


def test_unreadable_meminfo_on_a_64_bit_board_means_browser(tmp_path):
    script = _installer_function('low_spec_board') + 'low_spec_board && echo low || echo ok\n'
    env = _fake_bin(tmp_path, getconf='exit 1')
    env['MEMINFO'] = str(tmp_path / 'missing')
    result = subprocess.run(['bash', '-c', 'set -Eeuo pipefail\n' + script],
                            capture_output=True, text=True, env=env)
    assert result.stdout.strip() == 'ok', result.stderr


@pytest.mark.parametrize('board,expected', [
    # Saved by this installer: a renewing mode is kept even on hardware that
    # would pick otherwise.
    ({'saved': 'browser auto', 'installed': True, 'long_bit': 32}, 'browser kept true false'),
    ({'saved': 'no-browser auto', 'installed': True}, 'no-browser kept true true'),
    ({'saved': 'no-browser', 'installed': True}, 'no-browser kept true true'),   # first version: no origin
    # Renewal off is kept only when --no-auto-token chose it.
    ({'saved': 'none flag', 'installed': True}, 'none kept false false'),
    ({'saved': 'none auto', 'installed': True}, 'browser detected true false'),
    # First version, inferred from a board an upgrade had left without renewal
    # (Disneypi): turned on from the hardware.
    ({'saved': 'none', 'installed': True}, 'browser detected true false'),
    ({'saved': 'none', 'installed': True, 'mem_kb': 443000}, 'no-browser detected true true'),
    ({'saved': '', 'installed': True}, 'browser detected true false'),
    # Installed by an older installer that saved no mode: renewal it had is kept.
    ({'installed': True, 'timer_enabled': True, 'playwright': True}, 'browser kept true false'),
    ({'installed': True, 'timer_enabled': True}, 'no-browser kept true true'),
    ({'installed': True, 'manual_conf': True, 'playwright': True}, 'browser kept true false'),
    ({'installed': True, 'manual_conf': True}, 'no-browser kept true true'),
    # ...and renewal it lacked (no flag could choose that then) is turned on.
    ({'installed': True, 'playwright': True}, 'browser detected true false'),
    ({'installed': True, 'mem_kb': 443000}, 'no-browser detected true true'),
    # A first install that died after building the venv (say, in the driver
    # build) never wrote its units: still a fresh install.
    ({'venv_only': True}, 'browser detected true false'),
    ({'venv_only': True, 'long_bit': 32}, 'no-browser detected true true'),
])
def test_upgrade_without_flags_keeps_the_boards_token_mode(tmp_path, board, expected):
    out, err, code = _token_mode(tmp_path, **board)
    assert code == 0, err
    assert ' '.join(out) == expected


@pytest.mark.parametrize('flag,expected', [
    ('browser', 'browser flag true false'),
    ('no-browser', 'no-browser flag true true'),
    ('none', 'none flag false false'),
])
def test_token_mode_flags_override_the_saved_mode(tmp_path, flag, expected):
    out, err, code = _token_mode(tmp_path, flag=flag, saved='no-browser' if flag != 'no-browser' else 'browser',
                                 installed=True, timer_enabled=True)
    assert code == 0, err
    assert ' '.join(out) == expected
    assert 'Warning' not in err


@pytest.mark.parametrize('first,saved,second', [
    ({'flag': 'none'}, 'none flag', 'none kept false false'),
    ({'flag': 'no-browser'}, 'no-browser flag', 'no-browser kept true true'),
    ({}, 'browser auto', 'browser kept true false'),
    ({'mem_kb': 443000}, 'no-browser auto', 'no-browser kept true true'),
    ({'saved': 'none flag'}, 'none flag', 'none kept false false'),   # stays a flag choice
])
def test_saved_mode_round_trips_with_its_origin(tmp_path, first, saved, second):
    _, err, code = _token_mode(tmp_path, installed=True, **first)
    assert code == 0, err
    assert (tmp_path / 'etc' / 'token-mode').read_text() == saved + '\n'
    out, err, code = _token_mode(tmp_path, installed=True, mem_kb=first.get('mem_kb', 3884000))
    assert code == 0, err
    assert ' '.join(out) == second
    assert (tmp_path / 'etc' / 'token-mode').read_text() == saved + '\n'


def test_auto_token_on_a_small_board_warns_but_obeys(tmp_path):
    out, err, code = _token_mode(tmp_path, flag='browser', mem_kb=443000)
    assert code == 0
    assert ' '.join(out) == 'browser flag true false'
    assert 'too small for Chromium' in err


def test_unknown_saved_token_mode_stops_the_install(tmp_path):
    out, err, code = _token_mode(tmp_path, saved='chromium', installed=True)
    assert code == 2
    assert "Unknown token mode 'chromium'" in err


@pytest.mark.parametrize('args,expected', [
    ([], ''),
    (['--auto-token'], 'browser'),
    (['--no-browser'], 'no-browser'),
    (['--no-auto-token'], 'none'),
    (['--no-browser', '--auto-token'], 'browser'),   # last one wins
])
def test_token_flags_set_the_mode(args, expected):
    text = (ROOT / 'peloton-install.sh').read_text()
    start = text.index('while (($#)); do')
    loop = text[start:text.index('\ndone\n', start) + 6]
    script = ('set -Eeuo pipefail\nusage() { :; }\nTOKEN_MODE=""\nRECONFIGURE=false\nSKIP_MATRIX=false\n'
              'SKIP_PACKAGES=false\nNO_START=false\nMANUAL=""\n' + loop + 'echo "$TOKEN_MODE"\n')
    result = subprocess.run(['bash', '-c', script, 'installer', *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_installer_resolves_and_saves_the_token_mode_in_order():
    text = (ROOT / 'peloton-install.sh').read_text()
    resolve = text.index('\nresolve_token_mode\n')
    running = text.index('if systemctl is-active --quiet peloton-led.service')
    # Packages (Chromium) depend on the mode; whether the display ran is noted
    # before the install touches it.
    assert text.index('resolve_start_mode\n') < resolve < running < text.index('apt-get update')
    assert running < text.index('rm -rf "$APP_DIR/$directory"')
    # Saved as soon as its directory exists, before the steps that tend to
    # fail (venv, driver build), so a re-run keeps the mode instead of
    # mistaking the half-built install for something else.
    save = text.index('\nsave_token_mode\n')
    assert text.count('\nsave_token_mode\n') == 1
    assert text.index('install -d -m 0755 -o root -g root "$APP_DIR" "$CONFIG_DIR"') < save
    assert save < text.index('python3 -m venv "$APP_DIR/venv"') < text.index('pip install "$driver_dir"')
    assert 'TOKEN_MODE_FILE="$CONFIG_DIR/token-mode"' in text
    assert 'Tokens:   $TOKEN_MODE ($TOKEN_MODE_SOURCE' in text


def _enable_units(tmp_path, manual, auto_token):
    """Run the installer's enable/disable block with a logging systemctl."""
    text = (ROOT / 'peloton-install.sh').read_text()
    block = text.split('systemctl daemon-reload\n', 1)[1].split('\n# Token paths as', 1)[0]
    log = tmp_path / 'calls.log'
    env = _fake_bin(tmp_path, systemctl=f'echo "systemctl $*" >> "{log}"')
    script = (f'set -Eeuo pipefail\nMANUAL={str(manual).lower()}\nAUTO_TOKEN={str(auto_token).lower()}\n'
              + block + '\n')
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    return log.read_text().splitlines() if log.exists() else []


@pytest.mark.parametrize('manual,auto_token,expected', [
    (True, True, ['systemctl disable peloton-led.service peloton-token-refresh.timer']),
    # Renewal off in manual mode: the PartOf= drop-in is gone, so nothing else
    # would ever stop a timer the display had started.
    (True, False, ['systemctl disable peloton-led.service peloton-token-refresh.timer',
                   'systemctl disable --now peloton-token-refresh.timer']),
    (False, True, ['systemctl enable peloton-led.service',
                   'systemctl enable peloton-token-refresh.timer']),
    (False, False, ['systemctl enable peloton-led.service',
                    'systemctl disable --now peloton-token-refresh.timer']),
])
def test_installer_enables_units_and_stops_renewal_when_switched_off(tmp_path, manual, auto_token, expected):
    # The updater's boot-time recovery is on in every mode: a manual board loses power mid-update too.
    assert _enable_units(tmp_path, manual, auto_token) == ['systemctl enable peloton-update-recover.service'] + expected


def _start_or_restart(tmp_path, no_start, was_running, auto_token=False, tokens=()):
    """Run start_or_restart_display with logging fakes; return the logged commands."""
    log = tmp_path / 'calls.log'
    env = _fake_bin(tmp_path,
                    systemctl=f'echo "systemctl $*" >> "{log}"',
                    runuser=f'echo "runuser $*" >> "{log}"')
    script = (f'set -Eeuo pipefail\nAPP_USER=peloton-led\nAPP_DIR=/opt/peloton-led\nCONFIG_DIR=/etc/peloton-led\n'
              f'NO_START={str(no_start).lower()}\nDISPLAY_WAS_RUNNING={str(was_running).lower()}\n'
              f'AUTO_TOKEN={str(auto_token).lower()}\n'
              f'configured_tokens=({" ".join(str(t) for t in tokens)})\n'
              f'{_installer_function("start_or_restart_display")}start_or_restart_display\n')
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    return log.read_text().splitlines() if log.exists() else [], result.stdout


@pytest.mark.parametrize('was_running', [True, False])
def test_manual_upgrade_restarts_only_a_running_display(tmp_path, was_running):
    calls, out = _start_or_restart(tmp_path, no_start=True, was_running=was_running, auto_token=True,
                                   tokens=[tmp_path / 'cookies.txt'])
    if was_running:
        assert calls == ['systemctl restart peloton-led.service']
        assert 'Restarting the running display' in out
    else:
        assert calls == []


def test_starting_install_verifies_tokens_then_starts_display_and_renewal(tmp_path):
    token = tmp_path / 'cookies-joel.txt'
    token.write_text('token')
    calls, _ = _start_or_restart(tmp_path, no_start=False, was_running=True, auto_token=True,
                                 tokens=[token, tmp_path / 'cookies-jen.txt'])
    assert len(calls) == 4
    assert calls[0].startswith('runuser -u peloton-led -- /opt/peloton-led/venv/bin/python')
    assert f'--verify-only --cookies {token}' in calls[0]
    assert calls[1:] == ['systemctl restart peloton-led.service',
                         'systemctl start peloton-token-refresh.timer',
                         'systemctl start peloton-token-refresh.service']


def test_starting_install_without_auto_token_starts_only_the_display(tmp_path):
    token = tmp_path / 'cookies.txt'
    token.write_text('token')
    calls, _ = _start_or_restart(tmp_path, no_start=False, was_running=False, tokens=[token])
    assert calls[1:] == ['systemctl restart peloton-led.service']


def _check_gpio_mapping(tmp_path, checkout=None, etc=None, reconfigure=False):
    """Run check_gpio_mapping with optional checkout and /etc configs; return the result."""
    source_dir, config_dir = tmp_path / 'checkout', tmp_path / 'etc'
    source_dir.mkdir(exist_ok=True)
    config_dir.mkdir(exist_ok=True)
    for directory, content in ((source_dir, checkout), (config_dir, etc)):
        if content is not None:
            (directory / 'config.json').write_text(content if isinstance(content, str) else json.dumps(content))
    script = (f'set -Eeuo pipefail\nSOURCE_DIR="{source_dir}"\nCONFIG_DIR="{config_dir}"\n'
              f'RECONFIGURE={str(reconfigure).lower()}\n'
              f'{_installer_function("check_gpio_mapping")}check_gpio_mapping\necho checked\n')
    return subprocess.run(['bash', '-c', script], capture_output=True, text=True)


@pytest.mark.parametrize('kwargs', [
    {'checkout': {'matrix': {'gpio_mapping': 'adafruit-hat'}}},
    {'checkout': {'matrix': {'gpio_mapping': 'adafruit-hat-pwm'}}, 'etc': {}},
    {'etc': {'matrix': {'gpio_mapping': 'regular'}}},
    {},                                    # fresh install: written from the template
    {'etc': {}, 'reconfigure': True},      # /etc config rewritten from the template
])
def test_gpio_mapping_check_passes_when_the_live_config_sets_it(tmp_path, kwargs):
    result = _check_gpio_mapping(tmp_path, **kwargs)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'checked'


@pytest.mark.parametrize('kwargs', [
    {'checkout': {'matrix': {'rows': 64}}},
    {'checkout': {'matrix': {'gpio_mapping': None}}},
    {'checkout': {}, 'etc': {'matrix': {'gpio_mapping': 'adafruit-hat'}}},   # the checkout's is live
    {'etc': {'display': {}}},
    {'checkout': {}, 'reconfigure': True},  # --reconfigure leaves the checkout's config alone
])
def test_gpio_mapping_check_stops_a_board_that_would_lose_its_wiring(tmp_path, kwargs):
    result = _check_gpio_mapping(tmp_path, **kwargs)
    assert result.returncode == 1
    assert 'checked' not in result.stdout
    assert 'has no matrix.gpio_mapping' in result.stderr
    assert '"matrix": {"gpio_mapping": "adafruit-hat"}' in result.stderr


def test_gpio_mapping_check_reports_an_unreadable_config(tmp_path):
    result = _check_gpio_mapping(tmp_path, checkout='{not json')
    assert result.returncode == 1
    assert 'Could not read' in result.stderr
    assert 'has no matrix.gpio_mapping' not in result.stderr


def test_gpio_mapping_is_checked_before_the_install_changes_anything():
    text = (ROOT / 'peloton-install.sh').read_text()
    check = text.index('\ncheck_gpio_mapping\n')
    assert text.index('[[ $EUID -eq 0 ]]') < check < text.index('apt-get update')
    assert check < text.index('rm -rf "$APP_DIR/$directory"') < text.index('install -m 0644 -o root -g root "$SOURCE_DIR/packaging/systemd/peloton-led.service"')


def test_installer_gives_the_display_its_log_folder():
    # The display opens its log while still root; peloton-led must own the
    # folder to rotate that log after the drop.
    text = (ROOT / 'peloton-install.sh').read_text()
    logs = 'install -d -m 0755 -o "$APP_USER" -g "$APP_USER" "$STATE_DIR/logs"'
    assert logs in text
    assert text.index('install -d -m 0750 -o "$APP_USER" -g "$APP_USER" "$STATE_DIR"') < text.index(logs)
    assert text.index(logs) < text.index('\nstart_or_restart_display\n')


def _pwm_audio(tmp_path, mapping='adafruit-hat-pwm', loaded=True, interactive=True, answer='y\n',
               boot='# Enable audio (loads snd_bcm2835)\ndtparam=audio=on\n', unload_ok=True):
    """Run check_pwm_audio on a fake board; return (result, boot config path, modprobe dir)."""
    modules = tmp_path / 'modules'
    modules.write_text(('snd_bcm2835 24576 0 - Live 0x0\n' if loaded else '') + 'vc4 300000 4 - Live 0x0\n')
    boot_config = tmp_path / 'config.txt'
    boot_config.write_text(boot)
    modprobe_dir = tmp_path / 'modprobe.d'
    modprobe_dir.mkdir(exist_ok=True)
    log = tmp_path / 'modprobe.log'
    env = _fake_bin(tmp_path, modprobe=f'echo "$*" >> "{log}"; exit {0 if unload_ok else 1}')
    env.update(PROC_MODULES=str(modules), BOOT_CONFIG=str(boot_config), MODPROBE_DIR=str(modprobe_dir))
    script = (f'set -Eeuo pipefail\nGPIO_MAPPING="{mapping}"\nAUDIO_REBOOT=false\n'
              f'is_interactive() {{ {"true" if interactive else "false"}; }}\n'
              f'{_installer_function("check_pwm_audio")}check_pwm_audio\necho "reboot=$AUDIO_REBOOT"\n')
    result = subprocess.run(['bash', '-c', script], input=answer, capture_output=True, text=True, env=env)
    return result, boot_config, modprobe_dir


@pytest.mark.parametrize('kwargs', [
    {'mapping': 'adafruit-hat'},     # no PWM pulse, no conflict
    {'mapping': ''},
    {'loaded': False},               # already off
])
def test_pwm_audio_check_asks_nothing_without_a_conflict(tmp_path, kwargs):
    result, boot_config, modprobe_dir = _pwm_audio(tmp_path, answer='', **kwargs)
    assert result.returncode == 0, result.stderr
    assert 'Turn the onboard audio off' not in result.stdout + result.stderr
    assert 'dtparam=audio=on' in boot_config.read_text()
    assert not list(modprobe_dir.iterdir())


@pytest.mark.parametrize('kwargs', [
    {'answer': 'n\n'},
    {'answer': '\n'},                # the default is no
    {'answer': ''},                  # end of input
    {'interactive': False},          # nobody to ask
])
def test_pwm_audio_is_only_turned_off_when_the_user_accepts(tmp_path, kwargs):
    result, boot_config, modprobe_dir = _pwm_audio(tmp_path, **kwargs)
    assert result.returncode == 1
    assert 'reboot=' not in result.stdout
    assert 'Nothing has changed' in result.stderr
    assert '"gpio_mapping": "adafruit-hat"' in result.stderr
    assert boot_config.read_text() == '# Enable audio (loads snd_bcm2835)\ndtparam=audio=on\n'
    assert not (tmp_path / 'config.txt.peloton-led.bak').exists()
    assert not list(modprobe_dir.iterdir())


@pytest.mark.parametrize('answer', ['y\n', 'Y\n', 'yes\n', 'YES\n'])
def test_accepting_turns_the_audio_off_and_unloads_it(tmp_path, answer):
    result, boot_config, modprobe_dir = _pwm_audio(tmp_path, answer=answer)
    assert result.returncode == 0, result.stderr
    assert 'shares the PWM hardware' in result.stdout
    assert boot_config.read_text() == '# Enable audio (loads snd_bcm2835)\ndtparam=audio=off\n'
    assert (tmp_path / 'config.txt.peloton-led.bak').read_text() == \
        '# Enable audio (loads snd_bcm2835)\ndtparam=audio=on\n'
    assert (modprobe_dir / 'blacklist-rgb-matrix.conf').read_text() == 'blacklist snd_bcm2835\n'
    assert (tmp_path / 'modprobe.log').read_text() == '-r snd_bcm2835\n'
    assert 'Onboard audio is off.' in result.stdout
    assert result.stdout.strip().endswith('reboot=false')


def test_accepting_adds_the_audio_line_when_the_boot_config_has_none(tmp_path):
    result, boot_config, _ = _pwm_audio(tmp_path, boot='[all]\narm_boost=1\n')
    assert result.returncode == 0, result.stderr
    assert boot_config.read_text() == '[all]\narm_boost=1\ndtparam=audio=off\n'


def test_audio_that_cannot_be_unloaded_asks_for_a_reboot(tmp_path):
    result, boot_config, _ = _pwm_audio(tmp_path, unload_ok=False)
    assert result.returncode == 0, result.stderr
    assert 'dtparam=audio=off' in boot_config.read_text()
    assert result.stdout.strip().endswith('reboot=true')
    assert 'turns off at the next reboot' in result.stderr


def test_installer_ends_with_a_reboot_step_when_the_audio_is_still_loaded():
    text = (ROOT / 'peloton-install.sh').read_text()
    block = text[text.index('if [[ "$AUDIO_REBOOT" == true ]]; then'):text.index('# Checked last:')]
    for reboot, shown in ((True, True), (False, False)):
        out = subprocess.run(['bash', '-c', f'set -Eeuo pipefail\nAUDIO_REBOOT={str(reboot).lower()}\n' + block],
                             capture_output=True, text=True, check=True).stdout
        assert ('sudo reboot' in out) == shown


def test_gpio_mapping_check_records_the_mapping_for_the_audio_check(tmp_path):
    source_dir, config_dir = tmp_path / 'checkout', tmp_path / 'etc'
    source_dir.mkdir()
    config_dir.mkdir()
    (source_dir / 'config.json').write_text(json.dumps({'matrix': {'gpio_mapping': 'adafruit-hat-pwm'}}))
    script = (f'set -Eeuo pipefail\nSOURCE_DIR="{source_dir}"\nCONFIG_DIR="{config_dir}"\nRECONFIGURE=false\n'
              f'GPIO_MAPPING=""\n{_installer_function("check_gpio_mapping")}check_gpio_mapping\necho "$GPIO_MAPPING"\n')
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'adafruit-hat-pwm'
    text = (ROOT / 'peloton-install.sh').read_text()
    # Asked right after the mapping is known, before the install changes anything.
    assert text.index('\ncheck_gpio_mapping\n') < text.index('\ncheck_pwm_audio\n') < text.index('apt-get update')


def test_settings_page_unit_runs_its_own_writable_service():
    unit = (ROOT / 'packaging' / 'systemd' / 'peloton-settings.service').read_text()
    # Root to save the live config whoever owns it and to restart the display; group
    # peloton-led so the PIN in its runtime folder is readable by the display.
    assert 'User=root' in unit and 'Group=peloton-led' in unit
    assert ('-m settings_page.server --config ${PELOTON_CONFIG} --auth-env /etc/peloton-led/auth.env '
            '--token-base /etc/peloton-led --cookies /var/lib/peloton-led/cookies.txt') in unit
    assert 'Environment=PELOTON_CONFIG=/etc/peloton-led/config.json' in unit
    assert 'RuntimeDirectory=peloton-led-settings' in unit and 'RuntimeDirectoryMode=0750' in unit
    assert 'ProtectSystem=strict' in unit and 'ProtectHome=read-only' in unit
    assert 'ReadWritePaths=/etc/peloton-led' in unit and 'NoNewPrivileges=true' in unit
    # The logins are never loaded into its environment: it reads auth.env itself, in-process.
    assert '\nEnvironmentFile=' not in unit
    assert 'WantedBy=multi-user.target' in unit
    from settings_page.pins import PIN_FILE
    assert PIN_FILE == '/run/peloton-led-settings/pin'


def test_installer_installs_verifies_and_points_the_settings_page_at_the_live_config():
    text = (ROOT / 'peloton-install.sh').read_text()
    assert 'packaging/systemd/peloton-settings.service" "$UNIT_DIR/peloton-settings.service"' in text
    assert '"$UNIT_DIR/peloton-settings.service"' in text.split('systemd-analyze verify', 1)[1].split('\n#', 1)[0]
    assert text.index('resolve_settings_page\n') < text.index('apt-get update')
    assert text.index('\nstart_or_restart_display\nstart_settings_page\n') > text.index('systemctl daemon-reload')
    assert '--settings-page) SETTINGS_PAGE=true' in text and '--no-settings-page) SETTINGS_PAGE=false' in text


def _settings_page_mode(tmp_path, flag, installed, enabled):
    unit_dir = tmp_path / 'units'
    unit_dir.mkdir(exist_ok=True)
    if installed:
        (unit_dir / 'peloton-settings.service').write_text('')
    env = _fake_bin(tmp_path, systemctl=f'exit {0 if enabled else 1}')
    script = (f'set -Eeuo pipefail\nUNIT_DIR="{unit_dir}"\nSETTINGS_PAGE="{flag}"\n'
              f'{_installer_function("resolve_settings_page")}resolve_settings_page\necho "$SETTINGS_PAGE"\n')
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.mark.parametrize('flag,installed,enabled,expected', [
    ('', False, False, 'true'),   # fresh install: on
    ('', True, True, 'true'),     # upgrade of a board with it on
    ('', True, False, 'false'),   # an earlier --no-settings-page is kept
    ('true', True, False, 'true'),
    ('false', True, True, 'false'),
])
def test_settings_page_is_on_unless_turned_off(tmp_path, flag, installed, enabled, expected):
    assert _settings_page_mode(tmp_path, flag, installed, enabled) == expected


@pytest.mark.parametrize('on,expected', [
    (True, ['systemctl enable peloton-settings.service', 'systemctl restart peloton-settings.service']),
    (False, ['systemctl disable --now peloton-settings.service']),
])
def test_start_settings_page(tmp_path, on, expected):
    log = tmp_path / 'calls.log'
    env = _fake_bin(tmp_path, systemctl=f'echo "systemctl $*" >> "{log}"')
    script = (f'set -Eeuo pipefail\nSETTINGS_PAGE={str(on).lower()}\n'
              f'{_installer_function("start_settings_page")}start_settings_page\n')
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == expected


def test_setup_updater_runs_the_updater_from_the_checkout_with_the_apps_venv(tmp_path):
    units, bin_dir = tmp_path / 'units', tmp_path / 'local-bin'
    units.mkdir()
    bin_dir.mkdir()
    script = (f'set -Eeuo pipefail\nAPP_DIR=/opt/peloton-led\nSOURCE_DIR=/home/pi/Peloton-LED\n'
              f'UNIT_DIR={units}\nBIN_DIR={bin_dir}\n'
              f'{_installer_function("setup_updater")}setup_updater\n')
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    unit = (units / 'peloton-update-recover.service').read_text()
    assert 'WorkingDirectory=/home/pi/Peloton-LED\n' in unit
    assert 'ExecStart=/opt/peloton-led/venv/bin/python -m self_update recover\n' in unit
    assert 'Type=oneshot' in unit and 'WantedBy=multi-user.target' in unit
    for name, command in (('peloton-update', ''), ('peloton-rollback', ' rollback')):
        text = (bin_dir / name).read_text()
        assert text.startswith('#!/bin/sh\n') and (bin_dir / name).stat().st_mode & 0o777 == 0o755
        assert (f'cd "/home/pi/Peloton-LED" && exec "/opt/peloton-led/venv/bin/python" -m self_update{command} "$@"\n'
                in text), 'arguments pass through, not expanded by the installer'


def test_the_updater_can_skip_pip_and_its_backstops_are_installed_and_enabled():
    text = (ROOT / 'peloton-install.sh').read_text()
    subprocess.run(['bash', '-n', str(ROOT / 'peloton-install.sh')], check=True)
    # --skip-requirements (the updater's, when neither requirements file changed) skips every pip
    # install of them, the pip upgrade too: an update with nothing new to install needs no network.
    for line in ('"$APP_DIR/venv/bin/python" -m pip install --upgrade pip',
                 '"$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"',
                 '"$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/requirements-auth.txt"'):
        guard = text.rindex('if [[ "$SKIP_REQUIREMENTS" == false ]]; then', 0, text.index(line))
        assert 'fi\n' not in text[guard:text.index(line)], line
    assert text.index('\nsetup_updater\n') < text.index('systemd-analyze verify')
    assert '"$UNIT_DIR/peloton-update-recover.service"' in text[text.index('systemd-analyze verify'):]
    assert (text.index('systemctl enable peloton-update-recover.service')
            > text.index('\nsystemctl daemon-reload\n'))


def test_the_display_unit_gives_the_heartbeat_a_folder_it_can_write_after_dropping_root():
    display = (ROOT / 'packaging' / 'systemd' / 'peloton-led.service').read_text()
    assert 'RuntimeDirectory=peloton-led\n' in display and 'RuntimeDirectoryMode=0770\n' in display
    assert 'Group=peloton-led' in display  # the folder's group: the user the display drops to
    assert "HEARTBEAT_FILE = '/run/peloton-led/health'\n" in (ROOT / 'utils' / 'heartbeat.py').read_text()


def _settings_drop_in(tmp_path, live_config):
    """Run the installer's settings-page drop-in block; return the drop-in it writes."""
    text = (ROOT / 'peloton-install.sh').read_text()
    start = text.index('install -d -m 0755 "$UNIT_DIR/peloton-settings.service.d"')
    block = text[start:text.index('if [[ "$MANUAL" == true && "$AUTO_TOKEN" == true ]]', start)]
    units = tmp_path / 'units'
    units.mkdir(exist_ok=True)
    script = (f'set -Eeuo pipefail\nUNIT_DIR={units}\nSOURCE_DIR=/home/pi/Peloton-LED\n'
              f'LIVE_CONFIG={live_config}\n{block}')
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return (units / 'peloton-settings.service.d' / 'project-config.conf').read_text()


def test_the_settings_page_gets_the_checkout_to_update_and_the_live_config(tmp_path):
    # The Updates card updates the checkout: its path, and its .git writable for a check's fetch.
    assert _settings_drop_in(tmp_path, '/etc/peloton-led/config.json') == (
        '[Service]\nEnvironment=PELOTON_CHECKOUT=/home/pi/Peloton-LED\n'
        'ReadWritePaths=/home/pi/Peloton-LED/.git\n')
    # The checkout's config.json is the live one: the page saves it there, with its .bak beside it.
    assert _settings_drop_in(tmp_path, '/home/pi/Peloton-LED/config.json') == (
        '[Service]\nEnvironment=PELOTON_CHECKOUT=/home/pi/Peloton-LED\n'
        'ReadWritePaths=/home/pi/Peloton-LED/.git\n'
        'Environment=PELOTON_CONFIG=/home/pi/Peloton-LED/config.json\nReadWritePaths=/home/pi/Peloton-LED\n')


def test_opt_gets_what_the_updates_card_imports():
    import re
    text = (ROOT / 'peloton-install.sh').read_text()
    assert 'self_update' in re.search(r'^for directory in (.+); do$', text, re.M).group(1).split()
    assert 'version.py' in re.search(r'^for file in (.+); do$', text, re.M).group(1).split()
