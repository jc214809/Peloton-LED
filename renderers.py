"""Markdown rendering utilities shared by the README builders."""
from collections import defaultdict
from typing import DefaultDict, List, Tuple

from models import GeneralWorkout, get_model_for_discipline


def _align_cells(columns: List[Tuple[str, str]]) -> List[str]:
    align_left = {"date_time", "tz", "discipline", "title", "instructor"}
    return [" --- " if key in align_left else " ---: " for key, _ in columns]


def render_grouped_markdown(workouts: List[GeneralWorkout]) -> str:
    header = "# Recent Peloton Workouts (by Discipline)"
    if not workouts:
        return f"{header}\n\n_No workouts found._\n"

    groups: DefaultDict[str, List[GeneralWorkout]] = defaultdict(list)
    for workout in workouts:
        label = workout.discipline or "Other"
        groups[label].append(workout)

    lines: List[str] = [header, ""]
    preferred_order = ["Running", "Rowing", "Cycling", "Strength"]
    remaining = sorted([key for key in groups.keys() if key not in preferred_order])
    for disc in preferred_order + remaining:
        items = groups.get(disc)
        if not items:
            continue
        model_cls = get_model_for_discipline(disc)
        columns = model_cls.columns()
        header_cells = [label for (_key, label) in columns]
        align_cells = _align_cells(columns)

        lines.append(f"## {disc}")
        lines.append("")
        lines.append("| " + " | ".join(header_cells) + " |")
        lines.append("| " + " | ".join(align_cells) + " |")
        for workout in items:
            cells = workout.to_markdown_row(columns)
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    return "\n".join(lines)
