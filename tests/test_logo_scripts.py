"""Offline logo tools: prepare_image, generate_logo_variants, postprocess_logos."""
import argparse
import runpy
import sys
from pathlib import Path

import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def _source(path, size=(200, 100)):
    image = Image.new('RGBA', size, (0, 0, 0, 0))
    w, h = size
    for x in range(w // 5, w * 4 // 5):
        for y in range(h // 5, h * 4 // 5):
            image.putpixel((x, y), (220, 30, 40, 255))
    image.save(path)
    return path


def _run(script, monkeypatch, *argv):
    monkeypatch.setattr(sys, 'argv', [script, *map(str, argv)])
    runpy.run_path(str(SCRIPTS / script), run_name='__main__')


def test_prepare_image_fits_and_centers_on_the_background(tmp_path, monkeypatch, capsys):
    source, out = _source(tmp_path / 'wide.png'), tmp_path / 'out.png'
    _run('prepare_image.py', monkeypatch, source, out, 64, 64, '--bg', '#102030')
    image = Image.open(out)
    assert image.mode == 'RGB' and image.size == (64, 64)
    # 2:1 source letterboxed into a square: background above and below.
    assert image.getpixel((32, 2)) == (16, 32, 48)
    assert image.getpixel((32, 32))[0] > 150
    assert '(64x64)' in capsys.readouterr().out


def test_prepare_image_defaults_to_black(tmp_path, monkeypatch):
    source, out = _source(tmp_path / 'wide.png'), tmp_path / 'out.png'
    _run('prepare_image.py', monkeypatch, source, out, 64, 32, '--bg')
    assert Image.open(out).getpixel((0, 0)) == (0, 0, 0)


def test_prepare_image_usage(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exit_info:
        _run('prepare_image.py', monkeypatch, 'only-one-arg')
    assert exit_info.value.code == 1
    assert 'Usage' in capsys.readouterr().out


def test_generate_logo_variants_writes_every_variant(tmp_path, monkeypatch):
    source, out_dir = _source(tmp_path / 'logo.png'), tmp_path / 'variants'
    _run('generate_logo_variants.py', monkeypatch, source, '--out-dir', out_dir,
         '--sizes', '64x32, 64x64,', '--colors', '8')
    names = sorted(p.name for p in out_dir.iterdir())
    for w, h in ((64, 32), (64, 64)):
        for suffix in ('nearest', 'lanczos_sharp', 'lanczos_unsharp', 'quant8', 'posterize6', 'mono_dither'):
            name = f'prepared_{w}x{h}_{suffix}.png'
            assert name in names
            assert Image.open(out_dir / name).size == (w, h)
    assert len(names) == 12


def test_generate_logo_variants_rejects_a_bad_size():
    from scripts.generate_logo_variants import parse_size
    assert parse_size('64X32') == (64, 32)
    with pytest.raises(argparse.ArgumentTypeError, match='expected WIDTHxHEIGHT'):
        parse_size('sixty-four')


def test_postprocess_logos_writes_variants_for_both_sizes(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'prepared_logos').mkdir()
    _source(tmp_path / 'prepared_logos' / 'peloton_64x64.png', (64, 64))
    _source(tmp_path / 'prepared_logos' / 'peloton_64x32.png', (64, 32))
    _run('postprocess_logos.py', monkeypatch)
    names = {p.name for p in (tmp_path / 'prepared_logos').iterdir()}
    assert {'peloton_64x64_nearest.png', 'peloton_64x64_sharp.png', 'peloton_64x64_quant12.png',
            'peloton_64x32_nearest.png', 'peloton_64x32_sharp.png',
            'peloton_64x32_posterize6.png'} <= names
    assert 'Postprocessing complete' in capsys.readouterr().out


def test_postprocess_logos_explains_missing_sources(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _run('postprocess_logos.py', monkeypatch)
    out = capsys.readouterr().out
    assert out.count('run scripts/rasterize_svg.sh first') == 2
