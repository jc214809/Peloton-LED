#!/usr/bin/env python3
"""Extract Pillow's C headers (Imaging.h and friends) for the installed Pillow.

rpi-rgb-led-matrix's Python binding reads Pillow's internal image struct, so
it must compile against headers from the exact Pillow version it runs with.
Pip's Pillow wheels ship no headers, and a distro's python3-pil is usually a
different version whose struct layout may not match (Pillow 12 changed it).

Usage: python fetch_pillow_headers.py DEST_DIR
Prints DEST_DIR on success; exits non-zero with a message otherwise.
"""
import io
import json
import sys
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

PYPI_JSON = 'https://pypi.org/pypi/pillow/{version}/json'
HEADER_DIR = 'src/libImaging'


def sdist_url(version, fetch):
    try:
        release = json.loads(fetch(PYPI_JSON.format(version=version)))
    except ValueError as exc:
        raise RuntimeError(f'PyPI returned unreadable metadata for Pillow {version}') from exc
    for item in release.get('urls') or []:
        if isinstance(item, dict) and item.get('packagetype') == 'sdist' and item.get('url'):
            return item['url']
    raise RuntimeError(f'PyPI lists no source release for Pillow {version}')


def extract_headers(archive_bytes, dest):
    """Copy <sdist>/src/libImaging/*.h into dest; return how many were written."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if (member.isfile() and path.suffix == '.h' and len(path.parts) == 4
                    and '/'.join(path.parts[1:3]) == HEADER_DIR):
                (dest / path.name).write_bytes(archive.extractfile(member).read())
                count += 1
    if not (dest / 'Imaging.h').is_file():
        raise RuntimeError('Pillow source release has no src/libImaging/Imaging.h')
    return count


def _fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'peloton-led-installer'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main(argv=None, fetch=_fetch, version=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        sys.exit(__doc__)
    if version is None:
        import PIL
        version = PIL.__version__
    try:
        count = extract_headers(fetch(sdist_url(version, fetch)), argv[0])
    except (OSError, RuntimeError, tarfile.TarError) as exc:
        sys.exit(f'Could not get Pillow {version} headers: {exc}')
    print(f'Pillow {version}: {count} headers in {argv[0]}', file=sys.stderr)
    print(argv[0])
    return 0


if __name__ == '__main__':
    sys.exit(main())
