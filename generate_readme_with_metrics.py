#!/usr/bin/env python3
"""
Fetch recent Peloton workouts (using browser session cookie in cookies.txt),
collect per-workout performance metrics (distance, pace, speed, calories, etc.),
and generate a README.md with a rich table and details.

Usage:
  1) Put your Cookie header string (one line: "name=value; name2=value2; ...") into cookies.txt
  2) pip install requests (in a venv recommended)
  3) Run:
       python3 generate_readme_with_metrics.py --days 3 --limit 50 --out README.md

Notes:
- This uses the unofficial Peloton endpoints and a browser session cookie.
- Keep cookies.txt private. Do not share it.
"""
import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from models import get_model_for_discipline
from renderers import render_grouped_markdown


def _format_split_sec(sec: Optional[float]) -> str:
    if not isinstance(sec, (int, float)) or sec <= 0:
        return ""
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d} s/500m"

import requests

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None

BASE = "https://api.onepeloton.com"


def load_cookie_dict(path: Path) -> Dict[str, str]:
    txt = path.read_text(encoding="utf-8").strip()
    parts = [p.strip() for p in txt.split(";") if p.strip()]
    d = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            d[k] = v
    return d


def make_session(cookie_path: Path) -> requests.Session:
    cookies = load_cookie_dict(cookie_path)
    s = requests.Session()
    s.headers.update({"User-Agent": "peloton-led/1.0", "peloton-platform": "web"})
    s.cookies.update(cookies)
    return s


def get_me(s: requests.Session) -> Dict[str, Any]:
    r = s.get(f"{BASE}/api/me", timeout=15)
    r.raise_for_status()
    return r.json()


def get_workouts_page(s: requests.Session, user_id: str, limit: int, page: int = 0) -> Dict[str, Any]:
    params = {"joins": "ride,ride.instructor", "limit": limit, "page": page}
    r = s.get(f"{BASE}/api/user/{user_id}/workouts", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def get_perf_graph(s: requests.Session, workout_id: str) -> Optional[Dict[str, Any]]:
    r = s.get(f"{BASE}/api/workout/{workout_id}/performance_graph", params={"every_n": 5}, timeout=30)
    if not r.ok:
        return None
    # Some responses are arrays or dicts; we expect dict with summaries/metrics
    try:
        return r.json()
    except Exception:
        return None


def ts_to_local_str(ts: Any, tzname: Optional[str] = None, fmt: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
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


def extract_summary_from_perf(perf: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # average_summaries and summaries are lists of {display_name, display_unit, value, slug}
    for arr_name in ("average_summaries", "summaries"):
        for e in (perf.get(arr_name) or []):
            slug = e.get("slug")
            out[slug] = e.get("value")
            out[f"{slug}__unit"] = e.get("display_unit")
    # metrics array may include multiple time-series with average/max
    # Capture heart_rate plus other discipline-specific aggregates commonly useful
    for m in (perf.get("metrics") or []):
        slug = (m.get("slug") or "").strip().lower()
        avg_v = m.get("average_value")
        max_v = m.get("max_value")
        if slug == "heart_rate":
            out["hr_avg"] = avg_v
            out["hr_max"] = max_v
        elif slug == "cadence":
            out["avg_cadence"] = avg_v
            out["avg_cadence__unit"] = out.get("avg_cadence__unit") or "rpm"
        elif slug == "resistance":
            out["avg_resistance"] = avg_v
            out["avg_resistance__unit"] = out.get("avg_resistance__unit") or "%"
        elif slug == "incline":
            # Prefer average_summaries avg_incline, but record from timeseries if present
            if out.get("avg_incline") is None and isinstance(avg_v, (int, float)):
                out["avg_incline"] = avg_v
                out["avg_incline__unit"] = out.get("avg_incline__unit") or "%"
        elif slug == "speed":
            # Keep avg_speed from summaries if available; record max_speed when present
            if isinstance(max_v, (int, float)) and out.get("max_speed") is None:
                out["max_speed"] = max_v
                out["max_speed__unit"] = out.get("avg_speed__unit") or out.get("speed__unit") or "mph"
        elif slug == "stroke_rate":
            out["avg_stroke_rate"] = avg_v
            out["avg_stroke_rate__unit"] = out.get("avg_stroke_rate__unit") or "spm"
        elif slug == "elevation":
            # Some graphs include elevation as a series; summary usually provides total elevation
            if out.get("elevation") is None and isinstance(avg_v, (int, float)):
                out["elevation"] = avg_v
                out["elevation__unit"] = out.get("elevation__unit") or "ft"
    return out


def _display_discipline(w: Dict[str, Any], ride: Dict[str, Any]) -> str:
    """Return a friendly discipline name.

    Preference order:
    - ride.fitness_discipline_display_name (if present)
    - w.fitness_discipline_display_name (if present)
    - Map slug from ride.fitness_discipline or w.fitness_discipline to a friendly label
    - Fallback to capitalized slug
    """
    # Prefer explicit display names when provided
    for src in (ride, w):
        val = (src or {}).get("fitness_discipline_display_name")
        if isinstance(val, str) and val.strip():
            return val.strip()

    # Fallback to slug mapping
    slug = (ride.get("fitness_discipline") or w.get("fitness_discipline") or "").strip().lower()
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
        "caesar": "Rowing",  # Peloton internal code for rowing
    }
    if slug in mapping:
        return mapping[slug]
    return slug.capitalize() if slug else ""


def summarize_row(w: Dict[str, Any], perf: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ride = w.get("ride") or {}
    tz = w.get("timezone") or ""
    title = ride.get("title") or w.get("title") or w.get("name") or "<no title>"
    instr = (ride.get("instructor") or {}).get("name") or (ride.get("instructor") or {}).get("display_name") or ""
    disc = _display_discipline(w, ride)
    start_str = ts_to_local_str(w.get("start_time"), tz)
    dur_s = ride.get("duration")
    dur_m = int(round(dur_s / 60)) if isinstance(dur_s, (int, float)) else None

    # totals from page json
    total_work_j = w.get("total_work")
    total_kj = int(round(float(total_work_j) / 1000.0)) if isinstance(total_work_j, (int, float)) else None

    metrics = extract_summary_from_perf(perf or {}) if perf else {}

    # Derive missing pace/speed for workouts (e.g., rowing/"caesar") if summaries omit them
    duration_sec = None
    if isinstance(dur_s, (int, float)) and dur_s > 0:
        duration_sec = float(dur_s)
    elif perf and isinstance(perf.get("duration"), (int, float)):
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
                avg_speed = miles / (duration_sec / 3600.0)  # mph
                avg_speed_unit = "mph"
            if avg_pace is None:
                avg_pace = (duration_sec / 60.0) / miles     # min/mi
                avg_pace_unit = "min/mi"
        # Rowing split (sec/500m)
        if dist_m > 0:
            row_split_sec = duration_sec / (dist_m / 500.0)

    return {
        "workout_id": w.get("id"),
        "date_time": start_str,
        "tz": tz,
        "discipline": disc,
        "title": title,
        "instructor": instr,
        "duration_min": dur_m,
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
        "total_output_kj": metrics.get("total_output"),  # already in kJ per API sample
        "avg_output_w": metrics.get("avg_output"),
        "avg_incline": metrics.get("avg_incline"),
        "avg_incline_unit": metrics.get("avg_incline__unit"),
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--out", default="README.md")
    ap.add_argument("--cookies", default="cookies.txt", help="Path to Cookie header file (one-line)")
    ap.add_argument("--dump-perf-dir", default=None, help="If set, write raw performance_graph JSON per workout to this directory")
    args = ap.parse_args()

    cookie_path = Path(args.cookies)
    if not cookie_path.exists():
        raise SystemExit("cookies.txt not found. Create it with your Cookie header string (one line).")

    s = make_session(cookie_path)
    me = get_me(s)
    uid = me.get("id")
    if not uid:
        raise SystemExit("Could not determine user id from /api/me")

    page = get_workouts_page(s, uid, limit=args.limit, page=0)
    items = page.get("data", [])

    # filter last N days
    now_utc = datetime.now(timezone.utc)
    thr_ts = (now_utc - timedelta(days=args.days)).timestamp()
    recent = []
    for w in items:
        st = w.get("start_time")
        if st is None:
            continue
        t = float(st)
        if t > 1e12:
            t /= 1000.0
        if t >= thr_ts:
            recent.append(w)

    # build workouts enriched with perf metrics
    workouts: List[GeneralWorkout] = []
    dump_dir = Path(args["dump-perf-dir"]) if isinstance(args, dict) and args.get("dump-perf-dir") else (Path(args.dump_perf_dir) if getattr(args, "dump_perf_dir", None) else None)

    for w in sorted(recent, key=lambda x: x.get("start_time", 0), reverse=True):
        wid = w.get("id")
        perf = get_perf_graph(s, wid) if wid else None
        if dump_dir and perf is not None:
            dump_dir.mkdir(parents=True, exist_ok=True)
            (dump_dir / f"performance_graph_{wid}.json").write_text(json.dumps(perf, ensure_ascii=False, indent=2), encoding="utf-8")
        row = summarize_row(w, perf)
        model_cls = get_model_for_discipline(row.get("discipline"))
        workouts.append(model_cls.from_row(row))

    md = render_grouped_markdown(workouts)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"Wrote {args.out} with {len(workouts)} workout(s) and metrics.")


if __name__ == "__main__":
    main()
