#!/usr/bin/env python3
"""Peloton LED main entrypoint."""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set, Tuple

from driver import RGBMatrix, __version__
from display.discipline_totals import render_discipline_page
from display.display import initialize_fonts
from display.user_name import render_username
from peloton.api import PelotonClient, make_session
from utils import debug
from utils.utils import args, led_matrix_options

logger = logging.getLogger("peloton-led")

RANGE_KEYS = [
    "discipline_totals",
    "workouts",
    "workouts_per_discipline",
    "workout_counts",
    "workout_counts_by_discipline",
    "discipline_counts",
]


def load_config(path: str = "config") -> Dict[str, Any]:
    config_path = Path(path)
    if config_path.suffix != ".json":
        config_path = config_path.with_suffix(".json")
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found at {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def configure_logging(config: Dict[str, Any]) -> None:
    level = logging.DEBUG if config.get("debug") else logging.INFO
    logger.setLevel(level)
    debug.logger.setLevel(level)


def build_peloton_context(
    cookies_file: str,
) -> Tuple[Optional[PelotonClient], Optional[Dict[str, Any]]]:
    path = Path(cookies_file)
    if not path.exists():
        logger.debug("Peloton cookies file %s missing; skipping API calls", path)
        return None, None
    try:
        session = make_session(path)
        client = PelotonClient(session)
        me = client.get_me()
        return client, me
    except Exception as exc:  # pragma: no cover - external call
        logger.warning("Could not build Peloton client: %s", exc)
    return None, None


def extract_discipline_totals(overview: Dict[str, Any]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    seen: Set[str] = set()

    def add_entry(display_label: str, count_value: Any) -> None:
        """Normalize and add a discipline/count pair to totals.

        display_label: the human-facing label for the discipline (may contain
        whitespace/case that will be preserved in the totals keys).
        count_value: the raw count value from the overview which may be a string
        or number and needs to be converted to int.
        """
        if not display_label or count_value is None:
            return
        try:
            count_int = int(float(count_value))
        except (ValueError, TypeError):
            return
        normalized_label = display_label.strip().lower()
        if not normalized_label or normalized_label in seen:
            return
        seen.add(normalized_label)
        totals[display_label.strip()] = count_int

    def handle_entry(entry: Dict[str, Any]) -> None:
        label = (
            entry.get("discipline_display_name")
            or entry.get("discipline_name")
            or entry.get("name")
            or entry.get("title")
            or entry.get("discipline")
        )
        count = (
            entry.get("workout_count")
            or entry.get("total_workouts")
            or entry.get("count")
            or entry.get("workouts")
        )
        add_entry(label or "", count)

    def handle_mapping(mapping: Dict[str, Any]) -> None:
        for key, value in mapping.items():
            display_name = key.replace("_", " ").title()
            if isinstance(value, dict):
                count = (
                    value.get("count")
                    or value.get("workout_count")
                    or value.get("total_workouts")
                )
                add_entry(display_name, count)
                for nested in _iterate_entries(value):
                    handle_entry(nested)
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict):
                        handle_entry(entry)
            else:
                add_entry(display_name, value)

    def _iterate_entries(container: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        for field in ("workouts", "items", "disciplines", "workout_counts"):
            nested = container.get(field)
            if isinstance(nested, list):
                yield from nested

    for key in RANGE_KEYS:
        data = overview.get(key)
        if isinstance(data, dict):
            handle_mapping(data)
        elif isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    handle_entry(entry)

    return totals


def render_username_card(matrix, username: str, font_key: str, color_key: str) -> None:
    render_username(matrix, username, font_key=font_key, color_key=color_key)


def cycle_discipline_totals(
    matrix,
    discipline_totals: Dict[str, int],
    color_key: str,
    overview_duration: int,
) -> None:
    if not discipline_totals:
        return
    logger.info("Cycling through disciplines (%d entries)", len(discipline_totals))
    for discipline, count in discipline_totals.items():
        logger.info("Rendering discipline '%s' (%d workouts)", discipline, count)
        render_discipline_page(matrix, discipline, count, color_key=color_key)
        if overview_duration > 0:
            time.sleep(overview_duration)


def main() -> None:
    command_line_args = args()
    config = load_config(command_line_args.config)
    configure_logging(config)

    logger.info("Starting Peloton LED display (driver version %s)", __version__)

    display_config = config.get("display", {})
    client, me = build_peloton_context(command_line_args.cookies)

    matrix_options = led_matrix_options(command_line_args)
    matrix = RGBMatrix(options=matrix_options)
    initialize_fonts(matrix.height)

    username = command_line_args.username
    if not username and me:
        username = me.get("username") or me.get("id")
        if username:
            logger.info("Using Peloton username %s from /api/me", username)
    if not username:
        username = display_config.get("username") or "Peloton Member"

    font_key = display_config.get("font", "ride")
    color_key = display_config.get("color", "white")
    duration = (
        command_line_args.display_duration
        if command_line_args.display_duration is not None
        else display_config.get("duration", 4)
    )
    overview_duration = display_config.get("overview_duration", 4)

    try:
        overview = client.get_overview(me["id"]) or {}
        while True:
            render_username_card(matrix, username, font_key, color_key)
            if duration > 0:
                time.sleep(duration)

            discipline_totals: Dict[str, int] = {}
            if client and me and me.get("id"):
                try:
                    discipline_totals = extract_discipline_totals(overview)
                    if not discipline_totals:
                        logger.info("No discipline totals found in overview response")
                except Exception as exc:  # pragma: no cover - external call
                    logger.warning("Could not fetch overview: %s", exc)
            else:
                logger.debug("Skipping overview fetch; client or user data missing")

            if discipline_totals:
                cycle_discipline_totals(
                    matrix, discipline_totals, color_key, overview_duration
                )
            elif overview_duration > 0:
                time.sleep(overview_duration)
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down Peloton LED display")


if __name__ == "__main__":
    main()
