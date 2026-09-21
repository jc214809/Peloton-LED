import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _import_debug_in_subprocess(env):
    return subprocess.run(
        [sys.executable, '-c', 'from utils import debug; debug.info("hi"); print("IMPORT_OK")'],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
    )


def test_peloton_log_dir_overrides_default_location(tmp_path):
    log_dir = tmp_path / 'logs'
    result = _import_debug_in_subprocess({**os.environ, 'PELOTON_LOG_DIR': str(log_dir)})
    assert result.returncode == 0, result.stderr
    assert 'IMPORT_OK' in result.stdout
    assert (log_dir / 'app.log').exists()


def test_unwritable_log_dir_does_not_crash_the_import(tmp_path):
    unwritable_parent = tmp_path / 'readonly-parent'
    unwritable_parent.mkdir()
    unwritable_parent.chmod(0o500)  # no write permission
    try:
        result = _import_debug_in_subprocess(
            {**os.environ, 'PELOTON_LOG_DIR': str(unwritable_parent / 'logs')})
        assert result.returncode == 0, result.stderr
        assert 'IMPORT_OK' in result.stdout
        assert 'Could not set up file logging' in result.stderr
    finally:
        unwritable_parent.chmod(0o700)
