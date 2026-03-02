"""Workout summarization helpers."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, Tuple

from models import get_model_for_discipline

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None


def ts_to_local_str(ts: Any, tzname: Optional[str] = None, fmt: str = "%b %d, %Y %I:%M %p %Z") -> str:
    if ts is None:
        return ""
    t = float(ts)
    if t > 1e12:
        t = t / 1000.0
    dt_utc = datetime.fromtimestamp(t, tz=timezone.utc)
    if tzname and ZoneInfo:
        try:
            return dt_utc.astimezone(ZoneInfo(tzname)).strftime(fmt)
        except Exception:
            pass
    return dt_utc.astimezone().strftime(fmt)


def extract_summary_from_perf(perf: Dict[str, Any], allowed_slugs: Set[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    def _set_value(slug: str, value: Any, unit: Optional[str] = None) -> None:
        if slug not in allowed_slugs:
            return
        out[slug] = value
        if unit is not None:
            out[f"{slug}__unit"] = unit

    summary_map: Dict[str, Tuple[Any, Optional[str]]] = {}
    for arr_name in ("average_summaries", "summaries"):
        for entry in (perf.get(arr_name) or []):
            slug = entry.get("slug")
            if slug and slug in allowed_slugs:
                summary_map[slug] = (entry.get("value"), entry.get("display_unit"))

    for slug, (value, unit) in summary_map.items():
        _set_value(slug, value, unit)

    metrics_map: Dict[str, Dict[str, Any]] = {}
    for metric in (perf.get("metrics") or []):
        slug = (metric.get("slug") or "").strip().lower()
        if not slug:
            continue
        metrics_map[slug] = {
            "average": metric.get("average_value"),
            "max": metric.get("max_value"),
            "unit": metric.get("display_unit"),
        }

    if "heart_rate" in metrics_map:
        hr = metrics_map["heart_rate"]
        _set_value("hr_avg", hr.get("average"))
        _set_value("hr_max", hr.get("max"))

    if "cadence" in metrics_map:
        cadence = metrics_map["cadence"]
        _set_value("avg_cadence", cadence.get("average"), cadence.get("unit") or "rpm")

    if "resistance" in metrics_map:
        resistance = metrics_map["resistance"]
        _set_value("avg_resistance", resistance.get("average"), resistance.get("unit") or "%")

    if "incline" in metrics_map:
        incline = metrics_map["incline"]
        if isinstance(incline.get("average"), (int, float)):
            _set_value("avg_incline", incline.get("average"), incline.get("unit") or "%")
        if isinstance(incline.get("max"), (int, float)):
            _set_value("max_incline", incline.get("max"), incline.get("unit") or "%")

    if "speed" in metrics_map:
        speed = metrics_map["speed"]
        if speed.get("average") is not None:
            _set_value("avg_speed", speed.get("average"), speed.get("unit") or out.get("avg_speed__unit"))
        if isinstance(speed.get("max"), (int, float)):
            _set_value("max_speed", speed.get("max"), out.get("avg_speed__unit") or speed.get("unit") or "mph")

    if "stroke_rate" in metrics_map:
        stroke = metrics_map["stroke_rate"]
        _set_value("avg_stroke_rate", stroke.get("average"), stroke.get("unit") or "spm")

    if "elevation" in metrics_map:
        elevation = metrics_map["elevation"]
        if isinstance(elevation.get("average"), (int, float)):
            _set_value("elevation", elevation.get("average"), elevation.get("unit") or "ft")

    return out


def _display_discipline(workout: Dict[str, Any], ride: Dict[str, Any]) -> str:
    for src in (ride, workout):
        display = (src or {}).get("fitness_discipline_display_name")
        if isinstance(display, str) and display.strip():
            return display.strip()
    slug = (ride.get("fitness_discipline") or workout.get("fitness_discipline") or "").strip().lower()
    mapping = {
        "cycling": "Cycling",
        "bike_bootcamp": "Bike Bootcamp",
        "tread_bootcamp": "Tread Bootcamp",
        "bootcamp": "Bootcamp",
        "running": "Running",
        "walking": "Walking",
        "walking_outdoor": "Outdoor Walk",
        "running_outdoor": "Outdoor Run",
        "strength": "Strength",
        "cardio": "Cardio",
        "yoga": "Yoga",
        "meditation": "Meditation",
        "stretching": "Stretching",
        "pilates": "Pilates",
        "barre": "Barre",
        "rowing": "Rowing",
        "caesar": "Rowing",
    }
    if slug in mapping:
        return mapping[slug]
    return slug.capitalize() if slug else ""


def summarize_workout(workout: Dict[str, Any], perf: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ride = workout.get("ride") or {}
    tz = workout.get("timezone") or ""
    title = ride.get("title") or workout.get("title") or workout.get("name") or "<no title>"
    instructor = (ride.get("instructor") or {}).get("name") or (ride.get("instructor") or {}).get("display_name") or ""
    discipline = _display_discipline(workout, ride)
    model_cls = get_model_for_discipline(discipline)
    start_str = ts_to_local_str(workout.get("start_time"), tz)
    duration = ride.get("duration")
    duration_min = int(round(duration / 60)) if isinstance(duration, (int, float)) else None

    metrics = extract_summary_from_perf(perf or {}, model_cls.perf_slugs()) if perf else {}
    duration_sec = float(duration) if isinstance(duration, (int, float)) and duration > 0 else None
    if duration_sec is None and perf and isinstance(perf.get("duration"), (int, float)):
        duration_sec = float(perf.get("duration"))

    dist_val = metrics.get("distance")
    dist_unit = metrics.get("distance__unit")
    dist_m = None
    if isinstance(dist_val, (int, float)) and dist_val > 0:
        if dist_unit in ("m", "meter", "meters"):
            dist_m = float(dist_val)
        elif dist_unit in ("km", "kilometer", "kilometers"):
            dist_m = float(dist_val) * 1000.0
        elif dist_unit in ("mi", "mile", "miles"):
            dist_m = float(dist_val) * 1609.344

    avg_speed = metrics.get("avg_speed")
    avg_speed_unit = metrics.get("avg_speed__unit")
    avg_pace = metrics.get("avg_pace")
    avg_pace_unit = metrics.get("avg_pace__unit")
    row_split_sec = None

    if duration_sec and dist_m and (avg_speed is None or avg_pace is None):
        miles = dist_m / 1609.344
        if miles > 0:
            if avg_speed is None:
                avg_speed = miles / (duration_sec / 3600.0)
                avg_speed_unit = "mph"
            if avg_pace is None:
                avg_pace = (duration_sec / 60.0) / miles
                avg_pace_unit = "min/mi"
        if dist_m > 0:
            row_split_sec = duration_sec / (dist_m / 500.0)

    total_work = workout.get("total_work")
    total_kj = int(round(float(total_work) / 1000.0)) if isinstance(total_work, (int, float)) else None

    achievement_pr = any(
        (
            (template.get("slug") or "").strip().lower() == "output_pr"
            for template in workout.get("achievement_templates") or []
        )
    )
    is_pr = (
        # achievement_pr or
        bool(workout.get("is_total_work_personal_record"))
        # or bool(workout.get("is_splits_personal_record"))
    )

    return {
        "workout_id": workout.get("id"),
        "date_time": start_str,
        "tz": tz,
        "discipline": discipline,
        "title": title,
        "instructor": instructor,
        "duration_min": duration_min,
        "distance": metrics.get("distance"),
        "distance_unit": metrics.get("distance__unit"),
        "avg_speed": avg_speed,
        "avg_speed_unit": avg_speed_unit,
        "max_speed": metrics.get("max_speed"),
        "max_speed_unit": metrics.get("max_speed__unit"),
        "avg_pace": avg_pace,
        "avg_pace_unit": avg_pace_unit,
        "row_split_sec_per_500m": row_split_sec,
        "calories": metrics.get("calories"),
        "calories_unit": metrics.get("calories__unit"),
        "total_output_kj": metrics.get("total_output"),
        "avg_output_w": metrics.get("avg_output"),
        "avg_incline": metrics.get("avg_incline"),
        "avg_incline_unit": metrics.get("avg_incline__unit"),
        "max_incline": metrics.get("max_incline"),
        "max_incline_unit": metrics.get("max_incline__unit"),
        "is_pr": is_pr,
        "elevation": metrics.get("elevation"),
        "elevation_unit": metrics.get("elevation__unit"),
        "avg_cadence": metrics.get("avg_cadence"),
        "avg_cadence_unit": metrics.get("avg_cadence__unit"),
        "avg_resistance": metrics.get("avg_resistance"),
        "avg_resistance_unit": metrics.get("avg_resistance__unit"),
        "avg_stroke_rate": metrics.get("avg_stroke_rate"),
        "avg_stroke_rate_unit": metrics.get("avg_stroke_rate__unit"),
        "hr_avg": metrics.get("hr_avg"),
        "hr_max": metrics.get("hr_max"),
    }
