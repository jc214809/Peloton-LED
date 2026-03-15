import logging
from utils.username import resolve_display_username


def test_cmd_username_takes_precedence():
    username = resolve_display_username("cli_user", {"username": "api_user", "id": "api_id"}, {"username": "config_user"})
    assert username == "cli_user"


def test_me_username_used_when_no_cmd():
    username = resolve_display_username(None, {"username": "api_user", "id": "api_id"}, {"username": "config_user"})
    assert username == "api_user"


def test_me_id_used_if_username_missing():
    username = resolve_display_username(None, {"id": "api_id"}, {"username": "config_user"})
    assert username == "api_id"


def test_config_used_if_no_cmd_or_me():
    username = resolve_display_username(None, None, {"username": "config_user"})
    assert username == "config_user"


def test_default_used_if_nothing_provided():
    username = resolve_display_username(None, None, {})
    assert username == "Peloton Member"


def test_logs_when_using_api_me(caplog):
    caplog.set_level(logging.INFO)
    username = resolve_display_username(None, {"username": "api_user", "id": "api_id"}, {})
    assert username == "api_user"
    # Verify a log record was emitted mentioning the username
    assert any("Using Peloton username api_user from /api/me" in rec.getMessage() for rec in caplog.records)
