"""Workout compare on real rows: the expectations of spec section 9.

The rows are private, so the fixture is gitignored and these tests skip without it (as in CI).
Make it on a machine with training-data/:  python scripts/export_compare_fixtures.py
The exporter itself is tested on hand-made raw files below, so it runs in CI too.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from peloton.workout_insights import insights

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests' / 'fixtures' / 'workout_compare' / 'real-rows.json'


def _exporter():
    spec = importlib.util.spec_from_file_location('export_compare_fixtures',
                                                  ROOT / 'scripts' / 'export_compare_fixtures.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cases():
    if not FIXTURE.exists():
        return [pytest.param(None, marks=pytest.mark.skip(reason=f'{FIXTURE.name} not exported (private rows)'))]
    payload = json.loads(FIXTURE.read_text(encoding='utf-8'))
    return [pytest.param((payload['rows'][c['rider']], c), id=f"{c['rider']}-{c['target'][:8]}")
            for c in payload['cases']]


@pytest.mark.parametrize('case', _cases())
def test_real_workout_expectations(case):
    rows, expected = case
    target = rows[expected['target']]
    assert [code for code, _ in insights(target, list(rows.values()))] == expected['expected']


def _detail(workout_id, start, disc='strength'):
    return {'id': workout_id, 'start_time': start, 'end_time': start + 1200, 'status': 'COMPLETE',
            'fitness_discipline': disc, 'workout_type': 'class', 'timezone': 'UTC',
            'ride': {'id': f'r-{workout_id}', 'duration': 1200}}


def test_exporter_keeps_the_target_and_two_years_of_its_discipline(tmp_path):
    exporter = _exporter()
    folder = tmp_path / 'joel'
    folder.mkdir()
    day = exporter.DAY
    now = 1_800_000_000
    details = [_detail('aaaa0001', now), _detail('bbbb0002', now - 10 * day),
               _detail('cccc0003', now - 800 * day), _detail('dddd0004', now - 5 * day, disc='cycling'),
               _detail('eeee0005', now + day)]
    for detail in details:
        (folder / f"{detail['id']}.workout.json").write_text(json.dumps(detail), encoding='utf-8')
    payload = exporter.export(tmp_path, expected=(('joel', 'aaaa', ['no_tracker']),))
    assert payload['cases'] == [{'rider': 'joel', 'target': 'aaaa0001', 'expected': ['no_tracker']}]
    assert sorted(payload['rows']['joel']) == ['aaaa0001', 'bbbb0002']
    with pytest.raises(SystemExit):
        exporter.export(tmp_path, expected=(('joel', 'ffff', []),))


def test_exporter_main_writes_the_file(tmp_path, capsys):
    exporter = _exporter()
    (tmp_path / 'joel').mkdir()
    detail = _detail('aaaa0001', 1_800_000_000)
    (tmp_path / 'joel' / 'aaaa0001.workout.json').write_text(json.dumps(detail), encoding='utf-8')
    exporter.EXPECTED = (('joel', 'aaaa', ['no_tracker']),)  # a fresh module per test, so no clean-up
    out = tmp_path / 'out' / 'rows.json'
    assert exporter.main(['--raw-dir', str(tmp_path), '--out', str(out)]) == 0
    assert json.loads(out.read_text(encoding='utf-8'))['cases'][0]['target'] == 'aaaa0001'
    assert '1 cases, 1 rows' in capsys.readouterr().out
