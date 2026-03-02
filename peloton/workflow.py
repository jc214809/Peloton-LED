"""High-level workflow helpers that build enriched workout models."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from models import GeneralWorkout, get_model_for_discipline
from peloton.api import PelotonClient
from peloton.summaries import summarize_workout


def build_workouts(
    client: PelotonClient,
    rows: Iterable[Dict[str, Any]],
    dump_dir: Optional[Path] = None,
) -> List[GeneralWorkout]:
    dump_path = Path(dump_dir) if dump_dir else None
    workouts: List[GeneralWorkout] = []
    sorted_rows = sorted(rows, key=lambda r: r.get("start_time", 0), reverse=True)

    for row in sorted_rows:
        workout_id = row.get("id")
        perf = client.get_perf_graph(workout_id) if workout_id else None
        if dump_path and perf is not None:
            dump_path.mkdir(parents=True, exist_ok=True)
            dump_path.joinpath(f"performance_graph_{workout_id}.json").write_text(
                json.dumps(perf, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        summary = summarize_workout(row, perf)
        model_cls = get_model_for_discipline(summary.get("discipline"))
        workouts.append(model_cls.from_row(summary))

    return workouts
