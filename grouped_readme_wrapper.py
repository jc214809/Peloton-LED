#!/usr/bin/env python3
"""
Wrapper that uses generate_readme_with_metrics.py helpers to produce a single
README grouped by discipline with discipline-specific columns.

Usage:
  python3 grouped_readme_wrapper.py --days 30 --limit 200 --out README.md --dump-perf-dir perf_graphs

This avoids editing the main script; it imports summarize_row and get_perf_graph
from generate_readme_with_metrics.py and performs grouping/rendering here.
"""
import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

from generate_readme_with_metrics import (
    make_session,
    get_me,
    get_workouts_page,
    get_perf_graph,
    summarize_row,
)

from models import get_model_for_discipline
from renderers import render_grouped_markdown


def render_grouped(rows: List[Dict[str, Any]]) -> str:
    workouts = [
        get_model_for_discipline(row.get("discipline")).from_row(row)
        for row in rows
    ]
    return render_grouped_markdown(workouts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", default="README.md")
    ap.add_argument("--cookies", default="cookies.txt")
    ap.add_argument("--dump-perf-dir", default=None)
    args = ap.parse_args()

    cookie_path = Path(args.cookies)
    if not cookie_path.exists():
        raise SystemExit("cookies.txt not found; create it with your Cookie header string (one line).")

    s = make_session(cookie_path)
    me = get_me(s)
    uid = me.get("id")
    if not uid:
        raise SystemExit("Could not determine user id from /api/me")

    page = get_workouts_page(s, uid, limit=args.limit, page=0)
    items = page.get("data", [])

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

    workouts: List[Dict[str, Any]] = []
    dump_dir = Path(args.dump_perf_dir) if args.dump_perf_dir else None
    for w in sorted(recent, key=lambda x: x.get("start_time", 0), reverse=True):
        wid = w.get("id")
        perf = get_perf_graph(s, wid) if wid else None
        if dump_dir and perf is not None:
            dump_dir.mkdir(parents=True, exist_ok=True)
            (dump_dir / f"performance_graph_{wid}.json").write_text(json.dumps(perf, ensure_ascii=False, indent=2), encoding="utf-8")
        workouts.append(summarize_row(w, perf))

    md = render_grouped(workouts)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"Wrote {args.out} with {len(workouts)} workout(s) and metrics.")


if __name__ == "__main__":
    main()
