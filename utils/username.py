"""Utilities for resolving the display username used by the LED screens.

This isolates the logic from peloton_led.py so it can be tested and reused.
"""
from typing import Dict, Optional
import logging


def resolve_display_username(cmd_username: Optional[str], me: Optional[Dict[str, object]], display_config: Dict[str, object]) -> str:
    """Return a display username chosen from, in order:

    1. The explicitly-provided command line username (cmd_username)
    2. The Peloton /api/me response (me["username"] or me["id"]) with a log
    3. The display config's "username" value
    4. A sensible default string "Peloton Member"
    """
    logger = logging.getLogger("peloton-led")

    username = cmd_username
    if not username and me:
        username = me.get("username") or me.get("id")
        if username:
            logger.info("Using Peloton username %s from /api/me", username)

    if not username:
        username = display_config.get("username") or "Peloton Member"

    return username
