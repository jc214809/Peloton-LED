import json
import subprocess
from pathlib import Path

from peloton.config import load_config
from scripts.migrate_pi_config import migrate_config


ROOT = Path(__file__).resolve().parents[1]


def test_installer_shell_syntax_and_upgrade_preservation_contract():
    installer = ROOT / 'peloton-install.sh'
    subprocess.run(['bash', '-n', str(installer)], check=True)
    text = installer.read_text()
    assert 'if [[ ! -f "$CONFIG_DIR/config.json" ]]' in text
    assert 'if [[ ! -f "$STATE_DIR/cookies.txt"' in text
    assert 'if [[ ! -f "$CONFIG_DIR/auth.env" ]]' in text
    assert 'rm -rf "$APP_DIR/$directory"' in text
    assert 'rm -rf "$CONFIG_DIR' not in text
    assert 'rm -rf "$STATE_DIR' not in text
    # Upstream rpi-rgb-led-matrix dropped its old make-based Python bindings
    # build in favor of a scikit-build-core/cmake pip install from the repo
    # root; guard against regressing back to the removed make targets.
    assert 'make -C "$driver_dir"' not in text
    assert 'pip install "$driver_dir"' in text


def test_pi_config_uses_writable_state_cache():
    path = ROOT / 'packaging' / 'config.pi.json'
    parsed = load_config(path)
    assert parsed['display']['cache_path'] == '/var/lib/peloton-led/dashboard-cache.json'
    assert json.loads(path.read_text())['debug'] is False


def test_first_install_migrates_display_settings_without_credentials(tmp_path):
    source = tmp_path / 'config.json'
    source.write_text(json.dumps({
        'debug': True,
        'auth': {'email': 'private@example.com', 'password': 'secret'},
        'display': {'color': 'gold', 'duration': 9},
    }))
    destination = tmp_path / 'etc' / 'config.json'
    migrate_config(source, ROOT / 'packaging' / 'config.pi.json', destination)
    migrated = json.loads(destination.read_text())
    assert 'auth' not in migrated
    assert migrated['debug'] is True
    assert migrated['display']['color'] == 'gold'
    assert migrated['display']['duration'] == 9
    assert migrated['display']['cache_path'] == '/var/lib/peloton-led/dashboard-cache.json'


def test_pi_migration_preserves_users_with_isolated_state_paths(tmp_path):
    source = tmp_path / 'config.json'
    source.write_text(json.dumps({'users': [
        {'name': 'One', 'token_path': 'cookies-one.txt', 'cache_path': 'one-cache.json',
         'email_env': 'ONE_EMAIL', 'password_env': 'ONE_PASSWORD'},
        {'name': 'Two', 'token_path': 'cookies-two.txt'},
    ], 'display': {}}))
    destination = tmp_path / 'etc' / 'config.json'
    migrate_config(source, ROOT / 'packaging' / 'config.pi.json', destination)
    users = json.loads(destination.read_text())['users']
    assert users[0]['token_path'] == '/var/lib/peloton-led/cookies-one.txt'
    assert users[0]['cache_path'] == '/var/lib/peloton-led/one-cache.json'
    assert users[1]['token_path'] == '/var/lib/peloton-led/cookies-two.txt'
    assert users[1]['cache_path'] == '/var/lib/peloton-led/dashboard-cache-user-2.json'


def test_pi_migration_derives_token_path_from_name_when_omitted(tmp_path):
    source = tmp_path / 'config.json'
    source.write_text(json.dumps({'users': [
        {'name': 'Joel'}, {'name': 'Jen'},
    ], 'display': {}}))
    destination = tmp_path / 'etc' / 'config.json'
    migrate_config(source, ROOT / 'packaging' / 'config.pi.json', destination)
    users = json.loads(destination.read_text())['users']
    assert users[0]['token_path'] == '/var/lib/peloton-led/cookies-joel.txt'
    assert users[1]['token_path'] == '/var/lib/peloton-led/cookies-jen.txt'


def test_systemd_units_have_managed_runtime_and_token_safety():
    unit_dir = ROOT / 'packaging' / 'systemd'
    display = (unit_dir / 'peloton-led.service').read_text()
    refresh = (unit_dir / 'peloton-token-refresh.service').read_text()
    timer = (unit_dir / 'peloton-token-refresh.timer').read_text()
    assert 'User=peloton-led' in display
    assert 'Restart=on-failure' in display
    assert '--cookies /var/lib/peloton-led/cookies.txt' in display
    assert 'ReadWritePaths=/var/lib/peloton-led' in display
    assert 'EnvironmentFile=/etc/peloton-led/auth.env' in refresh
    assert 'PELOTON_CHROMIUM_EXECUTABLE=/usr/bin/chromium' in refresh
    assert ' --ensure ' in refresh
    assert ' --all-users ' in refresh
    assert 'OnBootSec=5min' in timer
    assert 'OnUnitActiveSec=1h' in timer
    assert 'Persistent=true' in timer
