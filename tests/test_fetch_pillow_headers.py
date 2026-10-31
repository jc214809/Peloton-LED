"""Fetching Pillow's C headers for the LED driver build (PyPI mocked)."""
import io
import json
import tarfile

import pytest

from scripts.fetch_pillow_headers import extract_headers, main, sdist_url

SDIST = 'https://files.example/pillow-13.0.0.tar.gz'


def tarball(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


GOOD = tarball({'pillow-13.0.0/src/libImaging/Imaging.h': b'/* imaging */',
                'pillow-13.0.0/src/libImaging/ImPlatform.h': b'/* platform */',
                'pillow-13.0.0/src/libImaging/Storage.c': b'int x;',
                'pillow-13.0.0/src/libImaging/sub/Deep.h': b'/* nested, skipped */',
                'pillow-13.0.0/src/other/Other.h': b'/* elsewhere, skipped */',
                '../../evil/src/libImaging/Evil.h': b'/* outside, skipped */'})


def fake_pypi(release=None, archive=GOOD):
    release = release if release is not None else json.dumps({'urls': [
        {'packagetype': 'bdist_wheel', 'url': 'https://files.example/pillow.whl'},
        {'packagetype': 'sdist', 'url': SDIST}]})

    def fetch(url):
        if url == SDIST:
            return archive
        assert url == 'https://pypi.org/pypi/pillow/13.0.0/json'
        return release
    return fetch


def test_extracts_only_top_level_libimaging_headers(tmp_path, capsys):
    assert main([str(tmp_path / 'inc')], fetch=fake_pypi(), version='13.0.0') == 0
    assert sorted(p.name for p in (tmp_path / 'inc').iterdir()) == ['ImPlatform.h', 'Imaging.h']
    assert capsys.readouterr().out.strip() == str(tmp_path / 'inc')
    assert not (tmp_path / 'evil').exists()


@pytest.mark.parametrize('release, archive, message', [
    ('not json', GOOD, 'unreadable metadata'),
    (json.dumps({'urls': [{'packagetype': 'bdist_wheel', 'url': 'x'}]}), GOOD, 'no source release'),
    (json.dumps({}), GOOD, 'no source release'),
    (None, tarball({'pillow-13.0.0/src/libImaging/ImPlatform.h': b''}), 'has no src/libImaging/Imaging.h'),
    (None, b'not a tarball', 'Could not get Pillow 13.0.0 headers'),
])
def test_bad_responses_fail_with_a_clear_message(tmp_path, release, archive, message):
    with pytest.raises(SystemExit, match=message):
        main([str(tmp_path / 'inc')], fetch=fake_pypi(release, archive), version='13.0.0')


def test_network_failure_fails_with_a_clear_message(tmp_path):
    def offline(url):
        raise OSError('no route to host')
    with pytest.raises(SystemExit, match='Could not get Pillow 13.0.0 headers: no route to host'):
        main([str(tmp_path / 'inc')], fetch=offline, version='13.0.0')


def test_sdist_url_and_extract_helpers(tmp_path):
    assert sdist_url('13.0.0', fake_pypi()) == SDIST
    assert extract_headers(GOOD, tmp_path) == 2
