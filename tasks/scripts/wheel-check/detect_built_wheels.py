#!/usr/bin/env python3
"""Detect which wheels were built from source by matching sdist archives to the wheel index."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wheel_helpers import normalize


def main(directory=None, wheel_index_path='/tmp/wheel-index.json',
         output_path='/tmp/built-wheels.json'):
    if directory is None:
        directory = sys.argv[1] if len(sys.argv) > 1 else '.'

    sdist_pkgs = set()
    for f in os.listdir(directory):
        if not f.endswith('.tar.gz'):
            continue
        base = f[:-len('.tar.gz')]
        name_part, _, version_part = base.rpartition('-')
        if name_part:
            sdist_pkgs.add(normalize(name_part))

    with open(wheel_index_path) as fh:
        wheel_index = json.load(fh)

    built = set()
    for key, whl in wheel_index.items():
        pkg_name = normalize(key.rsplit('-', 1)[0])
        if pkg_name in sdist_pkgs:
            built.add(whl)

    if sdist_pkgs and built:
        status = 'has_built'
        print(f'Found {len(sdist_pkgs)} sdist(s), matched {len(built)} wheel(s) built from source')
    elif sdist_pkgs and not built:
        status = 'no_match'
        print(f'Found {len(sdist_pkgs)} sdist(s) but none matched the wheel index')
    elif wheel_index and not sdist_pkgs:
        status = 'all_cached'
        print(f'All {len(wheel_index)} wheel(s) pulled from cache — no sdists found')
    else:
        status = 'no_sdists'
        print('No sdists found — will test all wheels')

    with open(output_path, 'w') as fh:
        json.dump({'status': status, 'wheels': sorted(built)}, fh)


if __name__ == '__main__':
    main()
