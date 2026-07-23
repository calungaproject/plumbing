#!/usr/bin/env python3
"""Build a name-version to filename index from wheel files in a directory."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wheel_helpers import normalize


def main(wheels_dir=None, output_path='/tmp/wheel-index.json'):
    if wheels_dir is None:
        wheels_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    wheel_index = {}
    for f in os.listdir(wheels_dir):
        if not f.endswith('.whl'):
            continue
        parts = f.split('-')
        if len(parts) >= 2:
            key = normalize(parts[0]) + '-' + parts[1]
            wheel_index[key] = f
    with open(output_path, 'w') as f:
        json.dump(wheel_index, f)
    print(f'Indexed {len(wheel_index)} wheel(s)')
    return wheel_index


if __name__ == '__main__':
    main()
