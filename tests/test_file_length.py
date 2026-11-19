"""Source files stay at most MAX_LINES long; today's oversized ones are capped where they are.

The allowlist is a ratchet (docs/CODE-HEALTH-PLAN.md): a listed file may shrink but not grow, and once it
shrinks its cap must come down with it, so the list only gets shorter. Tests are exempt.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_LINES = 600

# path: current maximum. Remove an entry once the file is at most MAX_LINES.
ALLOWED_OVER = {
    'settings_page/server.py': 660,
}


def source_files():
    """Every tracked .py file outside tests/, as repo-relative posix paths."""
    tracked = subprocess.run(['git', 'ls-files', '*.py'], cwd=ROOT, check=True, capture_output=True,
                             text=True).stdout.split()
    return sorted(p for p in tracked if not p.startswith('tests/'))


def length_problems(lengths, allowed=None, max_lines=MAX_LINES):
    """Messages for every file that breaks the rule; lengths is {path: line count}."""
    allowed = ALLOWED_OVER if allowed is None else allowed
    problems = []
    for path, count in sorted(lengths.items()):
        cap = allowed.get(path)
        if cap is None and count > max_lines:
            problems.append(f'{path} is {count} lines (limit {max_lines}): split it')
        elif cap is not None and count > cap:
            problems.append(f'{path} is {count} lines, over its cap of {cap}: split it, do not grow it')
        elif cap is not None and count < cap:
            fix = 'remove it from ALLOWED_OVER' if count <= max_lines else f'lower the cap to {count}'
            problems.append(f'{path} is now {count} lines but its cap is {cap}: {fix}')
    problems += [f'{path} is in ALLOWED_OVER but is not a tracked source file: remove it'
                 for path in sorted(allowed) if path not in lengths]
    return problems


def test_source_files_stay_within_the_length_limit():
    lengths = {p: len((ROOT / p).read_text().splitlines()) for p in source_files()}
    assert length_problems(lengths) == []


def test_length_problems_names_each_way_to_break_the_rule():
    allowed = {'big.py': 900, 'shrunk.py': 900, 'small.py': 900, 'gone.py': 700}
    lengths = {'big.py': 901, 'shrunk.py': 800, 'small.py': 500, 'new.py': 601, 'fine.py': 600, 'ok.py': 10}
    assert length_problems(lengths, allowed) == [
        'big.py is 901 lines, over its cap of 900: split it, do not grow it',
        'new.py is 601 lines (limit 600): split it',
        'shrunk.py is now 800 lines but its cap is 900: lower the cap to 800',
        'small.py is now 500 lines but its cap is 900: remove it from ALLOWED_OVER',
        'gone.py is in ALLOWED_OVER but is not a tracked source file: remove it',
    ]
