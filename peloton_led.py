#!/usr/bin/env python3
"""Peloton LED main entrypoint."""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set, Tuple

from driver import RGBMatrix, __version__
from display.ui.discipline_page import DisciplinePageScreen
from display.display import initialize_fonts
from display.ui.manager import ScreenManager

from display.ui.username import UsernameScreen
from display.ui.pr_star import PrStarScreen
from display.ui.logo_screen import LogoScreen
from peloton.api import PelotonClient, make_session
from api.peloton_api import PelotonAPI
from api.pr import pr_from_last_day_workouts
from utils import debug
from utils.utils import args, led_matrix_options
from utils.username import resolve_display_username
from api.get_last_active_days_workouts import get_last_active_days_workouts

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


def build_peloton_client(
    cookies_file: str,
) -> Optional[PelotonClient]:
    path = Path(cookies_file)
    if not path.exists():
        logger.debug("Peloton cookies file %s missing; skipping API calls", path)
        return None
    try:
        session = make_session(path)
        client = PelotonClient(session)
        return client
    except Exception as exc:  # pragma: no cover - external call
        logger.warning("Could not build Peloton client: %s", exc)
    return None


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

def show_and_wait(manager: ScreenManager, name: str, state: Optional[Any], duration: float, tick_interval: float = 0.05) -> None:
    """Switch to a screen via manager.show and render it.

    By default this performs a single render (one manager.tick) then sleeps
    for `duration` seconds. If you need continuous animation/update during the
    duration, set up a dedicated tick loop elsewhere or call manager.tick
    repeatedly with an appropriate interval.
    """
    manager.show(name, state)
    # Render once immediately so the screen is drawn.
    try:
        manager.tick(state)
    except Exception:
        # manager.tick will log exceptions
        pass

    if duration > 0:
        # Keep the image on-screen for the requested duration without
        # repeatedly re-rendering (avoids repeated log spam from render()).
        time.sleep(duration)


def render_last_day_workouts(
    manager: ScreenManager,
    workouts: Iterable[Dict[str, Any]],
    color_key: str,
    per_workout_duration: int = 4,
    peloton_api: Optional[PelotonAPI] = None,
) -> None:
    """Render each workout from the last-day workouts using the ScreenManager.

    For each workout this function determines a human-friendly discipline label
    (using PelotonAPI.get_workout_discipline_label when available) and shows the
    discipline page for that workout. The most recent workout is shown first.
    """
    if not workouts:
        return

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

        # Prefer using the convenience helper on PelotonAPI when available so
        # the discipline extraction logic lives next to other Peloton-related
        # helpers and can be tested/maintained there.
        if peloton_api:
            try:
                disc_label = peloton_api.get_workout_discipline_label(w)
            except Exception:
                disc_label = None
        else:
            try:
                # summarize_workout contains the discipline logic used elsewhere in the
                # project; import lazily to avoid circular imports at module import time.
                from peloton.summaries import summarize_workout
            except Exception:
                summarize_workout = None

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
            show_and_wait(manager, "discipline", {"discipline": disc_label, "count": 1, "color_key": color_key}, per_workout_duration)
        except Exception as exc:  # pragma: no cover - drawing errors depend on hardware
            logger.warning("Failed to render workout discipline page for %s: %s", disc_label, exc)


def cycle_discipline_totals(
    manager: ScreenManager,
    discipline_totals: Dict[str, int],
    color_key: str,
    overview_duration: int,
) -> None:
    if not discipline_totals:
        return
    logger.info("Cycling through disciplines (%d entries)", len(discipline_totals))
    for discipline, count in discipline_totals.items():
        logger.info("Rendering discipline '%s' (%d workouts)", discipline, count)
        try:
            show_and_wait(manager, "discipline", {"discipline": discipline, "count": count, "color_key": color_key}, overview_duration)
        except Exception as exc:
            logger.warning("Failed to render discipline page for %s: %s", discipline, exc)



def run_display_loop(
    manager: ScreenManager,
    client: Optional[PelotonClient],
    api: Optional[PelotonAPI],
    me: Optional[Dict[str, Any]],
    overview: Dict[str, Any],
    last_day_workouts: Iterable[Dict[str, Any]],
    username: str,
    duration: float,
    overview_duration: int,
    per_workout_duration: int,
    color_key: str,
    pr_shown: bool,
) -> None:
    """Main display loop extracted for clarity.

    This computes discipline totals once from the provided overview and then
    cycles through the usual screens. The loop is intentionally free of
    network I/O; refreshes should be done outside and a new loop invocation
    used if live updates are added later.
    """
    # Compute once from the (prefetched) overview
    discipline_totals = extract_discipline_totals(overview)

    try:
        while True:
            if pr_shown:
                show_and_wait(manager, "pr", None, overview_duration)
                # pr_shown = False

            show_and_wait(manager, "username", username, duration)

            if client and me and me.get("id") and last_day_workouts:
                render_last_day_workouts(manager, last_day_workouts, color_key, per_workout_duration=per_workout_duration, peloton_api=api)

            if discipline_totals:
                cycle_discipline_totals(manager, discipline_totals, color_key, overview_duration)
            elif overview_duration > 0:
                time.sleep(overview_duration)
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down Peloton LED display")


def main() -> None:
    command_line_args = args()
    config = load_config(command_line_args.config)
    configure_logging(config)

    logger.info("Starting Peloton LED display (driver version %s)", __version__)

    display_config = config.get("display", {})
    font_key = display_config.get("font", "ride")
    color_key = display_config.get("color", "white")
    overview_duration = display_config.get("overview_duration", 4)
    per_workout_duration = display_config.get("per_workout_duration", 4)

    client = build_peloton_client(command_line_args.cookies)
    api = PelotonAPI(client)

    # Fetch /api/me once (separate from building the client) so callers can
    # choose whether they need the user object. This avoids duplicate network
    # calls if another part of the program already requested the user.
    me: Optional[Dict[str, Any]] = None
    if client:
        try:
            me = client.get_me()
        except Exception as exc:  # pragma: no cover - external call
            logger.warning("Could not fetch /api/me: %s", exc)

    matrix_options = led_matrix_options(command_line_args)
    matrix = RGBMatrix(options=matrix_options)
    initialize_fonts(matrix.height)

    # Resolve a display username early and log when obtained from the API
    username = resolve_display_username(command_line_args.username, me, display_config)

    duration = (
        command_line_args.display_duration
        if command_line_args.display_duration is not None
        else display_config.get("duration", 4)
    )

    # Instantiate screens and manager
    manager = ScreenManager(matrix, initial="logo")
    # Logo screen (optional) - path and duration come from display config
    logo_path = display_config.get("logo_path", "prepared_logos/prepared_64x64_posterize6.png")
    logo_duration = display_config.get("logo_duration", 3)
    manager.register("username", UsernameScreen(font_key=font_key, color_key=color_key))
    manager.register("pr", PrStarScreen(color_key=color_key))
    manager.register("discipline", DisciplinePageScreen())
    # Register logo screen last so it can be shown before the username screen
    try:
        manager.register("logo", LogoScreen(image_path=logo_path))
    except Exception:
        logger.warning("Could not register LogoScreen; continuing without it")

    # Show the optional logo screen once at startup (if present), then the username
    try:
        if Path(logo_path).exists():
            show_and_wait(manager, "logo", None, logo_duration)
        else:
            logger.debug("Logo image %s not found; skipping logo screen", logo_path)
    except Exception as exc:
        logger.warning("Failed to display logo screen: %s", exc)

    # Now show the initial username screen
    manager.show("username", username)

    # Prefetch data once before entering the display loop
    overview: Dict[str, Any] = {}
    last_day_workouts = []
    pr_shown = False
    if client and me and me.get("id"):
        overview = api.get_overview(me.get("id"))
        try:
            last_day_workouts = get_last_active_days_workouts(client, me["id"], limit=50, days=30)
        except Exception as exc:  # pragma: no cover - external call
            logger.warning("Could not fetch recent workouts for PR check: %s", exc)
        if last_day_workouts:
             pr_shown = pr_from_last_day_workouts(last_day_workouts)
    else:
        logger.debug("Skipping initial API fetch; client or user data missing")

    # Run the extracted loop
    run_display_loop(
        manager=manager,
        client=client,
        api=api,
        me=me,
        overview=overview,
        last_day_workouts=last_day_workouts,
        username=username,
        duration=duration,
        overview_duration=overview_duration,
        per_workout_duration=per_workout_duration,
        color_key=color_key,
        pr_shown=pr_shown,
    )



if __name__ == "__main__":
    main()

