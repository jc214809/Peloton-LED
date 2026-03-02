#!/usr/bin/env python3
"""Orchestrates fetching Peloton workouts and writing the grouped README."""
import argparse
from pathlib import Path
from typing import Optional

from peloton.api import make_session, PelotonClient
from peloton.workflow import build_workouts
from renderers import render_grouped_markdown


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Generate a Peloton workout README.")
    ap.add_argument("--days", type=int, default=3, help="How many days of workouts to include.")
    ap.add_argument("--limit", type=int, default=50, help="Maximum workouts to request from the API.")
    ap.add_argument("--out", default="README.md", help="Output markdown path.")
    ap.add_argument("--cookies", default="cookies.txt", help="Path to Cookie header file (one-line)")
    ap.add_argument("--dump-perf-dir", default=None, help="If set, write raw performance_graph JSON per workout.")
    return ap.parse_args()


def main():
    args = parse_args()
    print(f"Starting README build with args={args}")
    cookie_path = Path(args.cookies)
    if not cookie_path.exists():
        raise SystemExit("cookies.txt not found. Create it with your Cookie header string (one line).")
    print(f"Using cookies from {cookie_path}")

    session = make_session(cookie_path)
    print("Session Created")
    # print("Session cookies:", session.cookies.get_dict())
    # print("Session headers:", session.headers)
    client = PelotonClient(session)
    me = client.get_me()
    print(f"Authenticated as {me.get('username') or me.get('id')}")
    uid = me.get("id")
    if not uid:
        raise SystemExit("Could not determine user id from /api/me")

    recent = client.get_recent_workouts(uid, limit=args.limit, days=args.days)
    print(f"Fetched {len(recent)} recent workouts (limit {args.limit}, days {args.days})")
    dump_path: Optional[Path] = Path(args.dump_perf_dir) if args.dump_perf_dir else None
    workouts = build_workouts(client, recent, dump_path)
    print(f"Built {len(workouts)} formatted workouts (dump_dir={dump_path})")

    md = render_grouped_markdown(workouts)
    print("Rendered markdown output")
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"Wrote {args.out} with {len(workouts)} workout(s) and metrics.")


if __name__ == "__main__":
    main()
