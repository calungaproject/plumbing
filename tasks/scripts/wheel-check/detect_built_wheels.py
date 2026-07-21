#!/usr/bin/env python3
import json
import os
import re
import sys


def normalize(name):
    return re.sub(r'[-_.]+', '_', name).lower()


directory = sys.argv[1] if len(sys.argv) > 1 else '.'

sdist_pkgs = set()
for f in os.listdir(directory):
    if not f.endswith('.tar.gz'):
        continue
    base = f[:-len('.tar.gz')]
    name_part, _, version_part = base.rpartition('-')
    if name_part:
        sdist_pkgs.add(normalize(name_part))

wheel_index = json.load(open('/tmp/wheel-index.json'))
built = set()
for key, whl in wheel_index.items():
    pkg_name = normalize(key.rsplit('-', 1)[0])
    if pkg_name in sdist_pkgs:
        built.add(whl)

if sdist_pkgs and built:
    status = 'has_built'
    print(f'Found {len(sdist_pkgs)} sdist(s), matched {len(built)} wheel(s) built from source')
elif len(wheel_index) > 0 and not sdist_pkgs:
    status = 'all_cached'
    print(f'All {len(wheel_index)} wheel(s) pulled from cache — no sdists found')
else:
    status = 'no_sdists'
    print('No sdists found — will test all wheels')

json.dump({'status': status, 'wheels': sorted(built)}, open('/tmp/built-wheels.json', 'w'))
