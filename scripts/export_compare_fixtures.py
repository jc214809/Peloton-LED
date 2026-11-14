"""Export the real-row fixtures for the workout-compare expectations (spec section 9). No API calls.

    python scripts/export_compare_fixtures.py                     # training-data/ -> the default file

Writes tests/fixtures/workout_compare/real-rows.json, which is gitignored (the repo is public and the
rows hold heart rate, weights and class titles). tests/test_workout_compare_real.py skips when the
file is missing. For each target: its row plus the same rider's same-discipline rows from the two
years before it (for strength that is every tracked strength class in the window, which the weight
history needs). Rows are built from the saved raw files by the current code, so re-export after a
ROW_VERSION bump.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from peloton.workout_rows import RawFiles, RowStore, import_raw  # noqa: E402

DEFAULT_OUT = ROOT / 'tests' / 'fixtures' / 'workout_compare' / 'real-rows.json'
WINDOW_DAYS = 730
DAY = 86400
# (rider, workout ID prefix, expected insight codes in order): spec section 9.
EXPECTED = (
    ('joel', 'c1fcbc0c', ['go_up_lighter', 'go_up_lighter', 'effort_high']),
    ('joel', 'f44c128b', ['go_up_lighter', 'go_up_streak']),
    ('joel', '12208fe6', ['went_heavier']),
    ('jen', '28797884', ['nothing']),
    ('joel', 'e0d2d0f3', ['too_few']),
    ('joel', 'eb281dcd', ['too_few']),
    ('joel', 'e6ea7ca1', ['output_down']),
    ('joel', '7611a8ea', ['output_down']),
    # output_down until 2026-11-13: rated 6.7 against a usual 5.7, the tough class now takes its place.
    ('joel', '26beff7c', ['tough_class']),
    # Tough against the rider's usual with no output insight behind it (too_few / nothing before 2026-11-13).
    ('joel', '4d00ee5e', ['tough_class']),
    ('jen', 'a0e7650f', ['tough_class']),
    ('jen', '4a0027bc', ['tough_class']),
    # Tough, and the effort insight now stays after it.
    ('joel', 'a9ad33b7', ['tough_class', 'effort_high']),
    ('joel', 'e9a1055b', ['in_line']),
    ('jen', 'f4c69f0d', ['in_line', 'effort_high']),
    ('jen', '96bf6669', ['in_line', 'resistance_low', 'effort_low']),
    # resistance_low until 2026-11-13: 25% under counted the break before the floor block; 24% in the riding.
    ('jen', '823e0327', ['output_down']),
    ('jen', '587c1988', ['in_line']),
    ('joel', '0f931cbb', ['freestyle']),
)


def window_rows(target, rows):
    """The target and every same-discipline row from the WINDOW_DAYS before it."""
    since = target['start'] - WINDOW_DAYS * DAY
    return [r for r in rows if r['disc'] == target['disc'] and since <= r['start'] <= target['start']]


def export(raw_dir, expected=EXPECTED):
    """{'cases': [{rider, target, expected}], 'rows': {rider: {id: row}}} from the saved raw files."""
    stores = {}
    cases, out = [], {}
    for rider, prefix, codes in expected:
        if rider not in stores:
            stores[rider] = RowStore(Path('unused'))
            import_raw(stores[rider], RawFiles(raw_dir, rider))
        rows = list(stores[rider].rows.values())
        matches = [r for r in rows if r['id'].startswith(prefix)]
        if len(matches) != 1:
            raise SystemExit(f'{rider} {prefix}: {len(matches)} stored workouts match')
        target = matches[0]
        out.setdefault(rider, {}).update({r['id']: r for r in window_rows(target, rows)})
        cases.append({'rider': rider, 'target': target['id'], 'expected': list(codes)})
    return {'cases': cases, 'rows': out}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--raw-dir', default=str(ROOT / 'training-data'))
    parser.add_argument('--out', default=str(DEFAULT_OUT))
    options = parser.parse_args(argv)
    payload = export(options.raw_dir, EXPECTED)
    out = Path(options.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
    count = sum(len(rows) for rows in payload['rows'].values())
    print(f"{len(payload['cases'])} cases, {count} rows, {out.stat().st_size // 1024} KB -> {out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
