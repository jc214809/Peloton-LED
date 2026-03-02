#!/usr/bin/env python3
import json
import logging
import time
from pathlib import Path
from typing import Optional

from driver import RGBMatrix, __version__
from display.castle import render_castle
from display.display import initialize_fonts
from display.startup import render_mickey_logo
from display.user_name import render_username
from peloton.api import make_session, PelotonClient
from utils import debug
from utils.utils import args, led_matrix_options

logger = logging.getLogger("peloton-led")


def load_config(path="config.json"):
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found at {config_path}")
    with config_path.open() as handle:
        return json.load(handle)


def configure_logging(config):
    level = logging.DEBUG if config.get("debug") else logging.INFO
    logger.setLevel(level)
    debug.logger.setLevel(level)


def fetch_peloton_username(cookies_file: str) -> Optional[str]:  # pragma: no cover - external call
    path = Path(cookies_file)
    if not path.exists():
        logger.debug("Cookies file %s missing; skipping username lookup", cookies_file)
        return None
    try:
        session = make_session(path)
        client = PelotonClient(session)
        me = client.get_me()
        username = me.get("location") or me.get("id")
        if username:
            logger.info("Fetched Peloton username %s from API", username)
        return username
    except Exception as exc:  # pragma: no cover - external call
        logger.warning("Could not fetch username via Peloton API: %s", exc)
    return None


def main():
    config = load_config()
    configure_logging(config)

    command_line_args = args()
    matrix_options = led_matrix_options(command_line_args)
    matrix = RGBMatrix(options=matrix_options)
    initialize_fonts(matrix.height)

    logger.info("Starting Peloton LED display (driver version %s)", __version__)

    display_config = config.get("display", {})
    username = command_line_args.username
    if not username:
        username = fetch_peloton_username(command_line_args.cookies)
    if not username:
        username = display_config.get("username") or "Peloton Member"

    font_key = display_config.get("font", "ride")
    color_key = display_config.get("color", "white")
    duration = (
        command_line_args.display_duration
        if command_line_args.display_duration is not None
        else display_config.get("duration", 30)
    )

    render_username(
        matrix,
        username,
        font_key=font_key,
        color_key=color_key,
    )

    if duration and duration > 0:
        time.sleep(duration)


if __name__ == "__main__":
    main()
