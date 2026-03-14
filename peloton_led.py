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
from display.ui.username import UsernameScreen
from display.ui.pr_star import PrStarScreen
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
        def _label_from_key(key: str) -> str:
            return key.replace("_", " ").title()

        def _extract_count_from_dict(d: Dict[str, Any]) -> Any:
            return d.get("count") or d.get("workout_count") or d.get("total_workouts")

        for key, value in mapping.items():
            display_name = _label_from_key(key)
            if isinstance(value, dict):
                count = _extract_count_from_dict(value)
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


def is_pr_workout(workout: Dict[str, Any]) -> bool:
    """Return True if the given workout appears to be a personal record.

    Checks common fields returned by the Peloton API: explicit PR flags and
    achievement templates with the 'output_pr' slug.
    """
    if not workout:
        return False
    if bool(workout.get("is_total_work_personal_record")):
        return True
    if bool(workout.get("is_splits_personal_record")):
        return True
    for template in (workout.get("achievement_templates") or []):
        if (template.get("slug") or "").strip().lower() == "output_pr":
            return True
    return False


def get_last_day_workouts(client: PelotonClient, user_id: str, limit: int = 50, days: int = 30):
    """Return the workouts that occurred on the user's most recent workout date.

    This fetches a batch of recent workouts and groups them by date (YYYY-MM-DD
    taken from ISO-style timestamps). The workouts for the latest date are
    returned. The function is defensive about missing timestamp fields.
    """
    try:
        recent = client.get_recent_workouts(user_id, limit=limit, days=days) or []
    except Exception as exc:  # pragma: no cover - external call
        logger.warning("Could not fetch recent workouts for last-day lookup: %s", exc)
        return []

    if not recent:
        return []

    def _timestamp_str(w: Dict[str, Any]) -> str:
        # Try common timestamp fields in order of likelihood.
        for key in (
            "created_at",
            "start_time",
            "start_date",
            "start_time_iso8601",
            "start_date_local",
        ):
            val = w.get(key)
            if isinstance(val, str) and val:
                return val
        return ""

    def _date_part(ts: str) -> str:
        if not ts:
            return ""
        if "T" in ts:
            return ts.split("T", 1)[0]
        if " " in ts:
            return ts.split(" ", 1)[0]
        return ts

    workouts_by_date = {}
    for w in recent:
        ts = _timestamp_str(w)
        d = _date_part(ts)
        if not d:
            continue
        workouts_by_date.setdefault(d, []).append(w)

    if not workouts_by_date:
        return []

    last_date = max(workouts_by_date.keys())
    logger.info("Found last workout date %s with %d workouts", last_date, len(workouts_by_date[last_date]))
    return workouts_by_date[last_date]




def render_last_day_workouts(
    matrix,
    workouts: Iterable[Dict[str, Any]],
    color_key: str,
    per_workout_duration: int = 4,
) -> None:
    """Render each workout from the last-day workouts on the matrix.

    For each workout this function determines a human-friendly discipline label
    (using peloton.summaries.summarize_workout when available) and shows the
    discipline page for that workout. The most recent workout is shown first.
    """
    if not workouts:
        return

    try:
        # summarize_workout contains the discipline logic used elsewhere in the
        # project; import lazily to avoid circular imports at module import time.
        from peloton.summaries import summarize_workout
    except Exception:
        summarize_workout = None

    def _ts_key(w: Dict[str, Any]) -> str:
        for k in (
            "created_at",
            "start_time",
            "start_date",
            "start_time_iso8601",
            "start_date_local",
        ):
            v = w.get(k)
            if isinstance(v, str) and v:
                return v
        return ""

    # Sort newest first so the latest workouts are displayed earlier.
    items = sorted(workouts, key=_ts_key, reverse=True)
    logger.info("Rendering %d workouts from last day", len(items))

    for w in items:
        disc_label = None
        if summarize_workout:
            try:
                disc_label = summarize_workout(w, None).get("discipline")
            except Exception:
                disc_label = None

        if not disc_label:
            # Fallback extraction from common fields if summarizer isn't available
            ride = w.get("ride") or {}
            disc_label = (
                (ride.get("fitness_discipline_display_name") or w.get("fitness_discipline_display_name"))
                or (ride.get("fitness_discipline") or w.get("fitness_discipline"))
                or w.get("discipline")
                or ride.get("title")
            )
            if isinstance(disc_label, dict):
                disc_label = disc_label.get("name") or disc_label.get("display_name") or ""

        disc_label = (disc_label or "Workout").strip()
        logger.info("Rendering workout of discipline '%s'", disc_label)
        # Use count 1 for per-workout discipline page
        try:
            render_discipline_page(matrix, disc_label, 1, color_key=color_key)
        except Exception as exc:  # pragma: no cover - drawing errors depend on hardware
            logger.warning("Failed to render workout discipline page for %s: %s", disc_label, exc)

        if per_workout_duration > 0:
            time.sleep(per_workout_duration)


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
    per_workout_duration = display_config.get("per_workout_duration", 4)

    # instantiate UsernameScreen to render the username card
    username_screen = UsernameScreen(font_key=font_key, color_key=color_key)
    # instantiate PR star screen
    pr_screen = PrStarScreen(color_key=color_key)

    last_day_workouts = []
    try:
        # Make a single set of API calls before entering the main loop. The
        # runtime loop should not perform network I/O — updates will be
        # handled asynchronously in the future.
        overview: Dict[str, Any] = {}
        pr_shown = False
        if client and me and me.get("id"):
            try:
                overview = client.get_overview(me["id"]) or {}
            except Exception as exc:  # pragma: no cover - external call
                logger.warning("Could not fetch overview: %s", exc)
            try:
                # Fetch all workouts that occurred on the user's most recent workout day.
                last_day_workouts = get_last_day_workouts(client, me["id"], limit=50, days=30)
                if last_day_workouts:
                    # Pick the most recent workout from that day (by available timestamp)
                    def _ts_key(w: Dict[str, Any]) -> str:
                        for k in ("created_at", "start_time", "start_date", "start_time_iso8601", "start_date_local"):
                            v = w.get(k)
                            if isinstance(v, str) and v:
                                return v
                        return ""

                    latest = max(last_day_workouts, key=_ts_key)
                    pr_shown = is_pr_workout(latest)
            except Exception as exc:  # pragma: no cover - external call
                logger.warning("Could not fetch recent workouts for PR check: %s", exc)
        else:
            logger.debug("Skipping initial API fetch; client or user data missing")

        while True:



            # If a recent PR was detected at startup, show the PR star once.
            if pr_shown:
                pr_screen.render(matrix)
                if overview_duration > 0:
                    time.sleep(overview_duration)

            # Then render the username card as usual
            username_screen.render(matrix, state=username)
            if duration > 0:
                time.sleep(duration)

            # Show each workout from the user's last workout day (prefetched at startup)
            if client and me and me.get("id") and last_day_workouts:
                render_last_day_workouts(matrix, last_day_workouts, color_key, per_workout_duration=per_workout_duration)

            # Use the pre-fetched overview data to show discipline totals.
            discipline_totals: Dict[str, int] = extract_discipline_totals(overview)

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
