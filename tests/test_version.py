import subprocess

from version import SCRIPT_VERSION, version


def _run(code=0, out="", error=None):
    def run(args, **kwargs):
        if error:
            raise error
        assert args[:2] == ["git", "-c"] and "describe" in args, "git describe, told the checkout is safe"
        return subprocess.CompletedProcess(args, code, out, "")
    return run


def test_the_version_is_git_describe_without_the_v():
    assert version("/a", run=_run(out="v0.2.3-beta-3-g1a2b3c4\n")) == "0.2.3-beta-3-g1a2b3c4"


def test_without_tags_or_git_its_the_fallback():
    assert version("/b", run=_run(code=128)) == SCRIPT_VERSION
    assert version("/c", run=_run(error=OSError("no git"))) == SCRIPT_VERSION
    assert version("/d", run=_run(error=subprocess.TimeoutExpired("git", 10))) == SCRIPT_VERSION
