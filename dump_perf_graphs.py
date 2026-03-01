#!/usr/bin/env python3
"""
Fetch performance_graph for recent workouts and save raw JSON per workout.

Usage examples:
  python3 dump_perf_graphs.py --days 7 --limit 50 --outdir perf_graphs
  python3 dump_perf_graphs.py --days 3 --limit 20 --print-one

Requires: cookies.txt (one-line Cookie header) alongside this script by default.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

import requests

BASE = "https://api.onepeloton.com"


def load_cookie_dict(path: Path) -> Dict[str, str]:
    txt = path.read_text(encoding="utf-8").strip()
    parts = [p.strip() for p in txt.split(";") if p.strip()]
    d: Dict[str, str] = {}
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


def get_perf_graph(s: requests.Session, workout_id: str):
    r = s.get(f"{BASE}/api/workout/{workout_id}/performance_graph", params={"every_n": 5}, timeout=30)
    if not r.ok:
        return None
    try:
        return r.json()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="How many days back to include")
    ap.add_argument("--limit", type=int, default=50, help="Max workouts to fetch from page 0")
    ap.add_argument("--cookies", default="cookies.txt", help="Path to Cookie header file (one-line)")
    ap.add_argument("--outdir", default="perf_graphs", help="Directory to write JSON files")
    ap.add_argument("--print-all", action="store_true", help="Also print all JSONs to stdout")
    ap.add_argument("--print-one", action="store_true", help="Also print the most recent JSON to stdout")
    args = ap.parse_args()

    cookie_path = Path(args.cookies)
    if not cookie_path.exists():
        raise SystemExit("cookies.txt not found. Create it with your Cookie header string (one line).")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    s = make_session(cookie_path)
    me = get_me(s)
    uid = me.get("id")
    if not uid:
        raise SystemExit("Could not determine user id from /api/me")

    page = get_workouts_page(s, uid, limit=args.limit, page=0)
    items: List[Dict[str, Any]] = page.get("data", [])

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

    # Sort newest first
    recent.sort(key=lambda x: x.get("start_time", 0), reverse=True)

    saved_files: List[Path] = []
    printed = False

    for w in recent:
        wid = w.get("id")
        if not wid:
            continue
        perf = get_perf_graph(s, wid)
        if perf is None:
            continue
        out_path = outdir / f"performance_graph_{wid}.json"
        out_path.write_text(json.dumps(perf, ensure_ascii=False, indent=2), encoding="utf-8")
        saved_files.append(out_path)

        if args.print_all:
            print(f"\n===== performance_graph for workout {wid} =====")
            print(json.dumps(perf, ensure_ascii=False, indent=2))
            printed = True

    # Optionally print the most recent only
    if args.print_one and not args.print_all and saved_files:
        most_recent = saved_files[0]
        print(f"\n===== Most recent performance_graph: {most_recent.name} =====")
        print(most_recent.read_text(encoding="utf-8"))
        printed = True

    print(f"Saved {len(saved_files)} performance_graph JSON file(s) to {outdir}/")
    if saved_files:
        print("First few files:")
        for p in saved_files[:5]:
            print(f" - {p}")
    if not printed:
        print("(Pass --print-one or --print-all to print JSON to stdout)")


if __name__ == "__main__":
    main()
