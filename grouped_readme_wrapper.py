#!/usr/bin/env python3
"""Generate a discipline-grouped README via the same data helpers."""
import argparse
from pathlib import Path
from typing import Optional

from peloton.api import make_session, PelotonClient
from peloton.workflow import build_workouts
from renderers import render_grouped_markdown


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Group Peloton workouts by discipline.")
    ap.add_argument("--days", type=int, default=30, help="How many days of workouts to include.")
    ap.add_argument("--limit", type=int, default=200, help="Maximum workouts to request from the API.")
    ap.add_argument("--out", default="README.md", help="Output markdown path.")
    ap.add_argument("--cookies", default="cookies.txt", help="Path to Cookie header file (one line).")
    ap.add_argument("--dump-perf-dir", default=None, help="If set, write raw performance_graph JSON per workout.")
    return ap.parse_args()


def main():
    args = parse_args()
    cookie_path = Path(args.cookies)
    if not cookie_path.exists():
        raise SystemExit("cookies.txt not found; create it with your Cookie header string (one line).")

    session = make_session(cookie_path)
    client = PelotonClient(session)
    me = client.get_me()
    uid = me.get("id")
    if not uid:
        raise SystemExit("Could not determine user id from /api/me")

    recent = client.get_recent_workouts(uid, limit=args.limit, days=args.days)
    dump_path: Optional[Path] = Path(args.dump_perf_dir) if args.dump_perf_dir else None
    workouts = build_workouts(client, recent, dump_path)

    md = render_grouped_markdown(workouts)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"Wrote {args.out} with {len(workouts)} workout(s) and metrics.")


if __name__ == "__main__":
    main()
