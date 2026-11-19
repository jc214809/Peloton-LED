"""Pins `Updater._update`, step by step, ahead of splitting it up (code health 2f-H): every path through
it, recording each call it makes on the board, the state file, GitHub and the notifier, plus the log
lines, the outcome and the files left behind. The split must leave every one of these unchanged."""
import logging

import pytest

from self_update import state as states
from self_update.update import RELEASES
from tests.test_updater import APP, NEW, OLD, SETTINGS, make_env


@pytest.fixture
def env(tmp_path):
    return make_env(tmp_path)


class Recorder:
    """Wraps an object, logging every method called on it into one shared, ordered list."""
    def __init__(self, target, name, events):
        self._target, self._name, self._events = target, name, events

    def __getattr__(self, attr):
        value = getattr(self._target, attr)
        if not callable(value):
            return value

        def call(*args, **kwargs):
            self._events.append((self._name, attr, args, tuple(sorted(kwargs.items()))))
            return value(*args, **kwargs)
        return call


def run(env, caplog, dry_run=False, channel=RELEASES):
    """Run the update, returning (the outcome, the ordered events, the log lines)."""
    events = []
    env.updater.board = Recorder(env.board, "board", events)
    env.updater.state = Recorder(env.state, "state", events)
    env.updater.gh = Recorder(env.gh, "gh", events)
    env.updater.notify = lambda title, message: events.append(("notify", title, message))
    with caplog.at_level(logging.INFO, logger="peloton-led.update"):
        outcome = env.updater.update(channel, dry_run=dry_run)
    lines = [(r.levelname, r.getMessage()) for r in caplog.records if r.name == "peloton-led.update"]
    return outcome, events, lines


def names(events, who=None):
    """The (who, method) pairs, in order."""
    return [e[:2] for e in events if who is None or e[0] == who]


def phases(events):
    return [e[2][1] for e in events if e[:2] == ("state", "set_phase")]


def summary(outcome):
    return outcome.result, outcome.message, outcome.ok, outcome.target


PREFLIGHT = [("board", "free_bytes"), ("board", "throttled"), ("board", "changes")]


def test_an_unfinished_update_returns_before_touching_the_board(env, caplog):
    env.state.set_phase(env.state.load(), states.SWITCHED, **{"from": {"sha": OLD}})
    outcome, events, lines = run(env, caplog)
    assert summary(outcome) == ("blocked", "an earlier update didn't finish (it stopped at switched): "
                                           "roll it back first (sudo peloton-rollback)", False, None)
    assert names(events) == [("state", "lock"), ("state", "load")]
    assert lines == []


def test_preflight_problems_return_before_resolving(env, caplog):
    env.board.free = 100 * 2**20
    env.board.flags = 0x5
    outcome, events, lines = run(env, caplog)
    assert summary(outcome) == ("blocked", "only 100 MB free; an update needs 300 MB; the Pi is under-voltage or "
                                           "throttled right now (0x5): fix its power or cooling first", False, None)
    assert names(events) == [("state", "lock"), ("state", "load"), *PREFLIGHT, ("gh", "releases")]
    assert env.board.calls == []
    assert lines == []


def test_a_github_error_joins_the_preflight_problems(env, caplog):
    env.board.free = 100 * 2**20
    env.gh.error = "can't reach GitHub (timed out)"
    outcome, events, lines = run(env, caplog)
    assert summary(outcome) == ("blocked", "only 100 MB free; an update needs 300 MB; can't reach GitHub (timed out)",
                                False, None)
    assert names(events, "board") == PREFLIGHT
    assert env.board.calls == []
    assert lines == []


def test_nothing_newer_returns_the_plans_outcome(env, caplog):
    env.gh.tags = ["v2.0.0"]
    outcome, events, lines = run(env, caplog)
    assert summary(outcome) == ("current", "no release newer than 2.0.0", True, None)
    assert names(events, "board") == PREFLIGHT
    assert env.board.calls == []
    assert lines == []


def test_a_resolve_that_fails_blocks_after_the_fetch(env, caplog):
    env.board.fail = {"fetch": lambda board: True}
    outcome, events, lines = run(env, caplog)
    assert summary(outcome) == ("blocked", "fetch failed", False, None)
    assert env.board.calls == [("fetch",)]
    assert phases(events) == []
    assert lines == []


@pytest.mark.parametrize("setup, expected", [
    (lambda b: b.refs.pop("refs/tags/v2.2.0"), ("blocked", "v2.2.0 isn't in the fetched checkout")),
    (lambda b: setattr(b, "head_sha", NEW), ("current", f"already on v2.2.0 ({NEW[:7]})")),
    (lambda b: b.without_updater.add(NEW), ("blocked", f"v2.2.0 ({NEW[:7]}) predates the updater: it couldn't "
                                                       "update or roll back again")),
])
def test_a_resolve_that_stops_returns_its_outcome(env, caplog, setup, expected):
    setup(env.board)
    outcome, events, lines = run(env, caplog)
    assert (outcome.result, outcome.message, outcome.target) == (*expected, None)
    assert env.board.calls == [("fetch",)]
    assert phases(events) == []
    assert lines == []


def test_a_dry_run_stops_after_resolving_with_no_lock_and_no_state_written(env, caplog):
    outcome, events, lines = run(env, caplog, dry_run=True)
    assert (outcome.result, outcome.message, outcome.ok) == ("would_update", f"would update to v2.2.0 ({NEW[:7]})",
                                                             True)
    assert (outcome.target.channel, outcome.target.ref, outcome.target.sha) == (RELEASES, "v2.2.0", NEW)
    assert names(events) == [("state", "load"), *PREFLIGHT, ("gh", "releases"), ("board", "fetch"),
                             ("board", "commit_of"), ("board", "head"), ("board", "file_at")]
    assert env.board.calls == [("fetch",)]
    assert lines == []


def test_a_failed_rollback_point_blocks_with_nothing_changed(env, caplog):
    fails = "pip_freeze"
    env.board.fail = {fails: lambda board: True}
    outcome, events, lines = run(env, caplog)
    assert summary(outcome) == ("blocked", f"couldn't take a rollback point, so nothing changed: {fails} failed",
                                False, None)
    assert not any(c[0] in ("checkout", "install", "restart") for c in env.board.calls)
    assert phases(events) == []
    assert lines == []


def test_a_rollback_point_that_cant_be_written_blocks_on_an_oserror(env, caplog, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr("self_update.update.shutil.copy2", boom)
    outcome, events, lines = run(env, caplog)
    assert summary(outcome) == ("blocked", "couldn't take a rollback point, so nothing changed: disk full",
                                False, None)
    assert phases(events) == []
    assert lines == []


def test_a_successful_update_in_full(env, caplog):
    outcome, events, lines = run(env, caplog)
    assert summary(outcome) == ("updated", f"updated to v2.2.0 ({NEW[:7]})", True, None)
    assert phases(events) == ["ready", "switched", "installed", "checking", "updated"]
    assert [e[:3] for e in events if e[0] == "board"] == [
        ("board", "free_bytes", ()), ("board", "throttled", ()), ("board", "changes", ()),
        ("board", "fetch", ()), ("board", "commit_of", ("refs/tags/v2.2.0",)), ("board", "head", ()),
        ("board", "file_at", (NEW, "self_update/__init__.py")),
        ("board", "head", ()), ("board", "pip_freeze", ()), ("board", "branch", ()), ("board", "tags_at", (OLD,)),
        ("board", "changed", (OLD, NEW, "requirements.txt")),
        ("board", "changed", (OLD, NEW, "requirements-auth.txt")), ("board", "active", (APP,)),
        ("board", "checkout", (NEW,)), ("board", "install", ()), ("board", "enabled", (SETTINGS,)),
        ("board", "restart", (APP,)), ("board", "restart", (SETTINGS,)), ("board", "restarts", (APP,)),
        ("board", "restarts", (APP,)), ("board", "active", (APP,)), ("board", "port_answers", (8080,))]
    assert env.board.calls == [("fetch",), ("pip_freeze",), ("tags_at", OLD), ("checkout", NEW, True),
                               ("install", NEW, True), ("restart", APP), ("restart", SETTINGS)]
    assert lines == [("INFO", f"Updating from {OLD[:7]} to v2.2.0 ({NEW[:7]})."),
                     ("INFO", f"Updated to v2.2.0 ({NEW[:7]}); it passed its health check.")]
    record = env.state.load()
    assert record["phase"] == "updated" and record["good"] == [NEW] and record["reason"] is None
    assert [e for e in events if e[0] == "notify"] == []


def test_a_requirements_change_installs_with_pip(env, caplog):
    env.board.requirements_changed = True
    outcome, events, lines = run(env, caplog)
    assert outcome.result == "updated"
    assert ("install", NEW, False) in env.board.calls


def test_a_failed_checkout_rolls_back_and_says_why(env, caplog):
    env.board.fail = {"checkout": lambda board, ref, detach: ref == NEW}
    outcome, events, lines = run(env, caplog)
    assert summary(outcome) == ("rolled_back", f"rolled back to Beta {OLD[:7]}: checkout failed", False, None)
    assert phases(events) == ["ready", "rolling_back", "rolled_back"]
    assert env.board.calls[3:5] == [("checkout", NEW, True), ("checkout", "develop-beta", False)]
    assert lines[0] == ("INFO", f"Updating from {OLD[:7]} to v2.2.0 ({NEW[:7]}).")
    assert lines[1] == ("ERROR", f"The update to v2.2.0 ({NEW[:7]}) failed: checkout failed. Rolling back.")
    assert [e[1] for e in events if e[0] == "notify"] == ["Update rolled back"]


def test_a_failed_install_stops_after_switching_then_rolls_back(env, caplog):
    env.board.fail = {"install": lambda board, sha, skip: sha == NEW}
    outcome, events, lines = run(env, caplog)
    assert outcome.result == "rolled_back" and not outcome.ok and "install failed" in outcome.message
    assert phases(events) == ["ready", "switched", "rolling_back", "rolled_back"]
    assert ("install", NEW, True) in env.board.calls and ("restart", APP) in env.board.calls


def test_an_unexpected_error_is_logged_with_its_traceback_and_rolls_back(env, caplog, monkeypatch):
    monkeypatch.setattr(env.board, "install", lambda skip_requirements: 1 / 0)
    outcome, events, lines = run(env, caplog)
    assert summary(outcome) == ("rollback_failed", f"rolling back to Beta {OLD[:7]} failed: the rollback failed "
                                                   "unexpectedly: division by zero (the update failed: the update "
                                                   "failed unexpectedly: division by zero)", False, None)
    assert lines[1] == ("ERROR", "The update failed unexpectedly.")
    assert lines[2] == ("ERROR", f"The update to v2.2.0 ({NEW[:7]}) failed: the update failed unexpectedly: "
                                 "division by zero. Rolling back.")
    assert [r.exc_info is not None for r in caplog.records if r.getMessage() == "The update failed unexpectedly."] \
        == [True]
    assert phases(events)[:2] == ["ready", "switched"]


def test_a_display_that_never_draws_fails_the_health_check_and_rolls_back(env, caplog):
    env.board.healthy = False
    outcome, events, lines = run(env, caplog)
    assert outcome.result == "rolled_back" and not outcome.ok
    assert "hasn't finished a screen" in outcome.message
    assert phases(events) == ["ready", "switched", "installed", "checking", "rolling_back", "rolled_back"]
    assert lines[1][0] == "ERROR" and lines[1][1].endswith("the display hasn't finished a screen since it restarted. "
                                                            "Rolling back.")
    assert env.state.load()["good"] == []


def test_a_rollback_that_fails_too_is_reported_as_failed(env, caplog):
    env.board.fail = {"install": lambda board, sha, skip: True}
    outcome, events, lines = run(env, caplog)
    assert outcome.result == "rollback_failed" and not outcome.ok
    assert phases(events) == ["ready", "switched", "rolling_back", "rollback_failed"]
    assert [e[1] for e in events if e[0] == "notify"] == ["Update rollback FAILED"]


def test_a_held_lock_blocks_without_running_a_step(env, caplog):
    with env.state.lock():
        outcome, events, lines = run(env, caplog)
    assert outcome.result == "blocked" and "already running" in outcome.message
    assert env.board.calls == [] and names(events) == [("state", "lock")]


def test_unreadable_tags_only_warn_while_taking_the_rollback_point(env, caplog):
    env.board.fail = {"tags_at": lambda board, sha: True}
    outcome, events, lines = run(env, caplog)
    assert outcome.result == "updated"
    assert lines[0] == ("WARNING", "Can't read the checkout's tags: tags_at failed")
