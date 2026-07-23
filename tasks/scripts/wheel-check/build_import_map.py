#!/usr/bin/env python3
"""Build a mapping from top-level import names to wheel filenames."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wheel_helpers import normalize
from verify_import import inspect_wheel, detect_import_names


def main(wheels_dir=None, output_path='/tmp/import-to-wheel.json'):
    if wheels_dir is None:
        wheels_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    import_to_wheel = {}
    for f in sorted(os.listdir(wheels_dir)):
        if not f.endswith('.whl'):
            continue
        whl_path = os.path.join(wheels_dir, f)
        try:
            inspection = inspect_wheel(whl_path)
            names = detect_import_names(inspection)
            for n in names:
                import_to_wheel.setdefault(normalize(n), []).append(f)
        except Exception as exc:
            print(f'WARNING: skipping {f}: {exc}', file=sys.stderr)
    with open(output_path, 'w') as f:
        json.dump(import_to_wheel, f)
    print(f'Mapped {len(import_to_wheel)} import name(s) to wheels')
    return import_to_wheel


if __name__ == '__main__':
    main()
