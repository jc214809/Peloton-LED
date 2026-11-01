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


def test_systemd_units_have_managed_runtime_and_token_safety():
    unit_dir = ROOT / 'packaging' / 'systemd'
    display = (unit_dir / 'peloton-led.service').read_text()
    refresh = (unit_dir / 'peloton-token-refresh.service').read_text()
    timer = (unit_dir / 'peloton-token-refresh.timer').read_text()
    assert 'User=peloton-led' in display
    assert 'Restart=on-failure' in display
    assert '--cookies /var/lib/peloton-led/cookies.txt' in display
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
    assert '--no-browser) AUTO_TOKEN=true; NO_BROWSER=true; shift ;;' in text
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
    assert text.index('mapfile -t configured_tokens') < text.index('if [[ "$NO_START" == false ]]; then\n    for token_file')


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
