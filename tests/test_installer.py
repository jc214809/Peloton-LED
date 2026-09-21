import json
import subprocess
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
    assert 'EnvironmentFile=/etc/peloton-led/auth.env' in refresh
    assert 'PELOTON_CHROMIUM_EXECUTABLE=/usr/bin/chromium' in refresh
    assert ' --ensure ' in refresh
    assert ' --all-users ' in refresh
    assert 'OnBootSec=5min' in timer
    assert 'OnUnitActiveSec=1h' in timer
    assert 'Persistent=true' in timer
