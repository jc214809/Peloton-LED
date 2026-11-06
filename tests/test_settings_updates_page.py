"""The settings page's Updates card (page.updates_card), from updates.Updates.view()-shaped dicts."""
import re

from settings_page.page import check_result, settings_page

UPDATES = {"version": "2.1.0", "sha": "a" * 40, "branch": "develop-beta", "running": False, "phase": "idle",
           "status": None, "step": None, "from": None, "outcome": None, "check": None, "channel": "releases",
           "auto_check": False}


def _updates(started=None, **changes):
    return settings_page({}, updates={**UPDATES, **changes}, started=started)


def test_the_updates_card_is_after_logins_outside_the_settings_form_with_its_own_forms():
    html = _updates()
    assert html.index('id="updates"') < html.index('id="settings"'), "not part of Save"
    assert html.index('href="#logins"') < html.index('href="#updates"') < html.index('href="#rotation"')
    assert "<strong>2.1.0</strong>" in html and "aaaaaaa" in html and "on develop-beta" in html
    assert re.search(r'<form method="post" action="/update/check"[^>]*><select id="channel" name="channel">'
                     r'<option value="releases" selected>Releases</option><option value="beta">Beta</option>', html)
    assert "/update/start" not in html and "/update/rollback" not in html, "nothing found, nothing to undo"
    html = settings_page({})
    assert 'id="updates"' not in html and 'href="#updates"' not in html, "no checkout: no card, no link"


def test_a_check_that_found_one_offers_update_now_on_its_channel():
    found = {"channel": "beta", "result": "would_update", "message": "would update to develop-beta (bbbbbbb)",
             "ok": True, "at": 0}
    html = _updates(check={**found, "ref": "develop-beta", "sha": "b" * 40}, channel="beta")
    assert '<div class="notice new" role="status">' in html
    assert '<strong>Update available on Beta: Beta <span class="mono">bbbbbbb</span></strong>' in html, "its commit"
    html = _updates(check={**found, "ref": "v9", "sha": "b" * 40, "channel": "releases"})
    assert "<strong>Update available on Releases: v9 bbbbbbb</strong>" in html, "no version: ref and commit"
    html = _updates(check={**found, "ref": "develop-beta", "sha": "b" * 40}, channel="beta")
    assert re.search(r'action="/update/start"[^>]*><input type="hidden" name="channel" value="beta">', html)
    assert 'class="changes"' not in html, "the check couldn't list them: no list"
    html = _updates(check={**found, "result": "current", "message": "no release newer than 2.1.0"})
    assert '<div class="notice good" role="status">' in html and "this is the newest on Beta" in html
    assert "No release newer than 2.1.0." in html and "/update/start" not in html


def test_a_check_says_up_to_date_waiting_or_blocked_apart():
    check = {"channel": "beta", "ok": True, "at": 0}
    html = _updates(check={**check, "result": "waiting", "message": "3333333's CI is still running (test)"})
    assert "Up to date for now" in html and "isn't ready yet" in html and "CI is still running" in html
    assert '<div class="notice info"' in html and "/update/start" not in html
    assert "3333333&#x27;s CI is still running (test)." in html, "a sha isn't capitalised"
    html = _updates(check={**check, "result": "blocked", "ok": False, "message": "the checkout has changes: M a"})
    assert '<div class="notice warn"' in html and "Can't update right now:</strong> The checkout has changes: M a." in html
    assert "Up to date" not in html


def test_a_beta_waiting_on_its_tests_lists_each_run():
    check = {"channel": "beta", "result": "waiting", "ok": True, "at": 0, "message": "3333333's CI is still running"}
    html = _updates(check={**check, "runs": [["pytest (3.13)", "passed"], ["pytest (3.11)", "running"]]})
    assert "<strong>A newer Beta is being tested.</strong>" in html and "Up to date for now" not in html
    assert ('<ol class="steps" aria-label="Tests"><li class="now">Tests on Python 3.11: running</li>'
            '<li class="done">Tests on Python 3.13: passed</li></ol>') in html, "in name order, step styles"
    assert "It can be installed once both pass." in html and "/update/start" not in html
    html = _updates(check={**check, "runs": [["test (3.11)", "passed"], ["lint", "failed"]]})
    assert "<strong>A newer Beta didn't pass its tests.</strong>" in html
    assert '<li class="failed">lint: failed</li>' in html and "the next Beta that passes can be" in html
    html = _updates(check={**check, "runs": []})
    assert "<strong>A newer Beta hasn't been tested yet.</strong>" in html and 'aria-label="Tests"' not in html
    html = _updates(check={**check, "runs": [["a", "running"], ["b", "running"], ["c", "passed"]]})
    assert "once they all pass" in html


def test_with_no_check_the_page_checks_the_installed_channel_by_itself():
    html = _updates(auto_check=True, channel="beta")
    assert '<div id="update-check" data-auto="beta">' in html and "Checking Beta for a newer version" in html
    assert "fetch('/update/check'" in html
    assert 'id="update-check"' not in _updates(), "nothing to check, nothing said"
    assert check_result({**UPDATES, "auto_check": True})
    assert check_result(UPDATES) == ""


def test_after_an_update_the_card_offers_a_rollback_that_warns_about_config_json():
    html = _updates(phase="updated", branch=None, **{"from": {"version": "2.0.9", "sha": "c" * 40}},
                    outcome={"command": "update", "result": "updated", "message": "updated to v2.2.0 (ddddddd)",
                             "ok": True, "at": 0})
    assert "as installed by an update" in html
    assert '<div class="notice good" role="status">' in html and "Last update" in html
    assert re.search(r'action="/update/rollback"[^>]*data-confirm="[^"]*undoing settings saved since', html)
    assert "Back to 2.0.9 (ccccccc)" in html
    html = _updates(phase="updated", **{"from": {"version": "2.0.9", "sha": "c" * 40, "branch": "develop-beta"}})
    assert "Back to Beta ccccccc on develop-beta, as before the last update" in html, "its commit, not a channel"
    html = _updates(phase="updated", **{"from": {"version": "2.0.9", "sha": "c" * 40, "channel": "beta"}})
    assert "Back to Beta ccccccc, as before the last update" in html, "a detached Beta (an earlier update's)"
    html = _updates(phase="updated", **{"from": {"version": "2.0.9", "sha": "c" * 40, "branch": "main"}})
    assert "Back to 2.0.9 (ccccccc) on main, as before the last update" in html
    assert "/update/rollback" not in _updates(phase="rolled_back", **{"from": {"version": "2.0.9", "sha": "c"}})


def test_a_failed_update_and_a_failed_rollback_say_so():
    html = _updates(phase="rolled_back", outcome={"command": "update", "result": "rolled_back", "ok": False,
                                                  "message": "rolled back to 2.1.0: the display crashed", "at": 0})
    assert '<div class="notice bad" role="alert">' in html and "Rolled back to 2.1.0: the display crashed." in html
    html = _updates(phase="rollback_failed", **{"from": {"version": "2.0.9", "sha": "c" * 40}})
    assert "The last rollback failed" in html and "sudo peloton-rollback" in html and "/update/rollback" in html
    assert "stopped midway" in _updates(phase="checking", **{"from": {"version": "2.0.9", "sha": "c" * 40}})


def test_while_one_runs_the_card_follows_it_with_the_buttons_off():
    html = _updates(running=True, phase="switched", status="Installing the new version", step=2,
                    **{"from": {"version": "2.0.9", "sha": "c" * 40}},
                    outcome={"command": "update", "result": "updated", "message": "old news", "ok": True, "at": 0})
    assert 'id="update-running"' in html and "Installing the new version" in html
    assert ('<ol class="steps" id="update-steps" aria-label="Steps"><li class="done">Checking it can update</li>'
            '<li class="done">Saving a rollback point</li><li class="now" aria-current="step">Installing the new '
            'version</li><li>Restarting and checking it works</li></ol>') in html
    assert "Old news" not in html and "stopped midway" not in html
    assert re.search(r'action="/update/rollback".*?<button type="submit" class="secondary" disabled>', html)
    assert "fetch('/update/status'" in html
    html = _updates(running=True, phase="rolling_back", status="Rolling back", step=None, auto_check=True,
                    check={"channel": "beta", "result": "current", "ok": True, "at": 0, "message": "x"})
    assert 'id="update-steps" aria-label="Steps" hidden>' in html, "a rollback has no steps"
    assert 'id="update-check"' not in html, "no check while it runs"


def test_starting_says_how_it_went():
    assert "Couldn't start it" in _updates(started="failed")
    assert "already running" in _updates(started="busy")
    assert "<strong>Started.</strong>" in _updates(started="started")
    assert "<strong>Started.</strong>" not in _updates(started="started", running=True, status="Saving a rollback point")


def test_an_update_found_lists_whats_in_it_linked_to_github():
    changes = [[200 + n, f"Change {n}"] for n in range(14, 0, -1)]
    found = {"channel": "releases", "result": "would_update", "message": "would update to v2.2.0 (2222222)",
             "ok": True, "at": 0, "ref": "v2.2.0", "sha": "2" * 40, "version": "2.2.0", "changes": changes,
             "packages": True}
    html = _updates(check=found)
    assert "Update available on Releases: 2.2.0" in html and "<strong>2.1.0 \u2192 2.2.0</strong>" in html
    assert ('<li><a href="https://github.com/jc214809/Peloton-LED/pull/214" target="_blank" '
            'rel="noopener">#214</a><span>Change 14</span></li>') in html
    assert "Change 3<" in html and "Change 2<" not in html and "and 2 more" in html
    assert "up to hours on a Pi Zero" in html
    html = _updates(check={**found, "changes": [[None, "Fix <a> typo"]], "packages": False})
    assert "<span>Fix &lt;a&gt; typo</span>" in html and "up to hours" not in html


def test_while_it_runs_the_card_says_what_its_installing():
    html = _updates(running=True, phase="checking", status="Checking the new version works",
                    to={"ref": "develop-beta", "sha": "9" * 40, "version": "2.2.0", "changes": [[201, "Updates card"]]})
    assert 'Updating to Beta <span class="mono">9999999</span>' in html and "Updates card" in html
    html = _updates(running=True, phase="checking", status="x", to={"ref": "v2.2.0", "sha": "9" * 40, "version": "2.2.0"})
    assert "Updating to 2.2.0" in html


def test_a_beta_build_shows_as_beta_not_as_the_release_it_grew_from():
    html = _updates(installed_channel="beta", version="2.0.0")
    assert '<strong>Beta <span class="mono">aaaaaaa</span></strong>' in html
    assert "A Beta (test) version on develop-beta, newer than release 2.0.0" in html
    assert "<strong>2.0.0</strong>" not in html
    html = _updates(installed_channel="releases", branch="main", version="2.1.0")
    assert '<strong>2.1.0</strong> <span class="mono">aaaaaaa</span>' in html and "Beta (test)" not in html
    found = {"channel": "beta", "result": "would_update", "message": "m", "ok": True, "at": 0,
             "ref": "develop-beta", "sha": "b" * 40, "version": "2.0.0", "changes": []}
    html = _updates(installed_channel="beta", check=found, channel="beta")
    assert '<strong>Beta <span class="mono">aaaaaaa</span> \u2192 Beta <span class="mono">bbbbbbb</span></strong>' in html
    html = _updates(installed_channel="beta", channel="releases",
                    check={**found, "channel": "releases", "ref": "v2.1.0", "version": "2.1.0"})
    assert '<strong>Beta <span class="mono">aaaaaaa</span> \u2192 2.1.0</strong>' in html


def test_a_tagged_beta_shows_by_its_number():
    html = _updates(installed_channel="beta", version="2.1.5-beta")
    assert "<strong>Beta 2.1.5</strong>" in html and "newer than release 2.1.0" in html
    html = _updates(installed_channel="beta", version="2.1.5-beta-2-gaaaaaaa")
    assert '<strong>Beta <span class="mono">aaaaaaa</span></strong>' in html, "past a Beta: by its commit"
    found = {"channel": "beta", "result": "would_update", "message": "m", "ok": True, "at": 0,
             "ref": "develop-beta", "sha": "b" * 40, "version": "2.1.6-beta", "changes": []}
    html = _updates(installed_channel="beta", version="2.1.5-beta", check=found, channel="beta")
    assert "<strong>Beta 2.1.5 \u2192 Beta 2.1.6</strong>" in html


def test_each_pull_request_shows_its_notes_under_its_title_and_the_behind_the_scenes_ones_together():
    found = {"channel": "beta", "result": "would_update", "message": "m", "ok": True, "at": 0,
             "ref": "develop-beta", "sha": "b" * 40, "changes": [
                 [206, "Sparkle", ["The castle sparkles.", "So do <the> rides."]],
                 [205, "Faster CI", []], [204, "Tidy tests", []],
                 [203, "Updates card polish", None]]}
    html = _updates(check=found, channel="beta")
    assert ('#206</a><span>Sparkle<span class="hint note">The castle sparkles.</span>'
            '<span class="hint note">So do &lt;the&gt; rides.</span></span></li>') in html, "notes under the title"
    assert '#203</a><span>Updates card polish</span></li>' in html, "from before release notes: the title alone"
    assert re.search(r"Behind the scenes, nothing you'd notice: <a [^>]*>#205</a>, <a [^>]*>#204</a></span>", html)
    assert "Faster CI" not in html
    html = _updates(check={**found, "changes": [[None, "Fix a typo", None]]}, channel="beta")
    assert "<span>Fix a typo</span>" in html and "Behind the scenes" not in html


def test_outcome_and_check_times_are_in_the_boards_zone():
    outcome = {"command": "update", "result": "updated", "message": "updated", "ok": True, "at": 0}
    html = settings_page({"display": {"timezone": "America/New_York"}}, updates={**UPDATES, "outcome": outcome})
    assert "Last update</strong> (Wed Dec 31, 7:00 PM)" in html
    html = settings_page({"display": {"timezone": "UTC"}}, updates={**UPDATES, "check": {
        "channel": "releases", "result": "current", "ok": True, "at": 0, "message": "no release newer than 2.1.0"}})
    assert "checked Thu Jan 1, 12:00 AM" in html
