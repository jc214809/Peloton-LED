"""The version, from git's tags: `git describe` gives "0.2.0" on a release, "0.2.3-beta" on a Beta
(.github/workflows/auto-tag.yml tags every merge), "0.2.3-beta-3-g1a2b3c4" three commits past one.
SCRIPT_VERSION is only the fallback for a copy without git (a zip download, or /opt/peloton-led,
the installer's copy). Locally, tags arrive with git fetch (git fetch --tags if they're stale).
"""
import functools
import os
import subprocess

SCRIPT_NAME = "Peloton-LED"
SCRIPT_VERSION = "0.0.1"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DESCRIBE_TIMEOUT_S = 10


@functools.lru_cache(maxsize=None)
def version(app_dir=APP_DIR, run=subprocess.run):
    """This checkout's version from its tags, without the "v", else SCRIPT_VERSION. The updater runs
    as root in a checkout that isn't root's, so git is told it's safe."""
    try:
        done = run(["git", "-c", f"safe.directory={app_dir}", "describe", "--tags", "--match", "v[0-9]*"],
                   cwd=app_dir, capture_output=True, text=True, timeout=DESCRIBE_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return SCRIPT_VERSION
    found = done.stdout.strip() if done.returncode == 0 else ""
    return found.removeprefix("v") or SCRIPT_VERSION


if __name__ == "__main__":
    print(f"{SCRIPT_NAME} v{version()}")
