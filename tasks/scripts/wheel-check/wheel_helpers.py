#!/usr/bin/env python3
"""CLI subcommands for wheel-check: result parsing, wheel index lookups, and sdist filtering."""
import json
import os
import re
import sys


def normalize(name):
    return re.sub(r'[-_.]+', '_', name).lower()


def read_result_status(path):
    try:
        with open(path) as f:
            return json.load(f).get('status', 'FAIL')
    except Exception:
        return 'FAIL'


def read_field(path, field):
    try:
        with open(path) as f:
            return json.load(f).get(field, '')
    except Exception:
        return ''


def print_failed_imports(path, prefix='  '):
    try:
        with open(path) as f:
            d = json.load(f)
        for t in d.get('imports_tested', []):
            if not isinstance(t, dict) or t.get('success'):
                continue
            name = t.get('name', '<unknown>')
            message = t.get('message', '')
            print(f'{prefix}{name}: {message}')
    except Exception:
        pass


def format_summary_row(path):
    try:
        with open(path) as f:
            d = json.load(f)
        w = d.get('wheel', '?')
        s = d.get('status', 'ERROR')
        r = d.get('reason', '')
        dep = d.get('undeclared_dep', '')
        if dep:
            r = f'undeclared dep: {dep}' if not r else f'{r} (undeclared dep: {dep})'
    except Exception:
        w = os.path.splitext(os.path.basename(path))[0]
        s, r = 'FAIL', 'verify_import failed without output'
    print(f'{s}\t{w}\t{r}')


def annotate_dep(path, dep_string):
    with open(path) as f:
        d = json.load(f)
    d['undeclared_dep'] = dep_string
    with open(path, 'w') as f:
        json.dump(d, f)


def match_installed_wheels(wheel_index_path):
    with open(wheel_index_path) as f:
        wheel_index = json.load(f)
    installed = json.load(sys.stdin)
    for pkg in installed:
        key = normalize(pkg['name']) + '-' + pkg['version']
        whl = wheel_index.get(key)
        if whl:
            print(whl)


def lookup_wheel(wheel_index_path, name, version):
    with open(wheel_index_path) as f:
        wheel_index = json.load(f)
    key = normalize(name) + '-' + version
    print(wheel_index.get(key, ''))


def extract_missing_module(path):
    try:
        with open(path) as f:
            d = json.load(f)
        for t in d.get('imports_tested', []):
            if isinstance(t, dict) and not t.get('success', True):
                msg = t.get('message', '')
                if 'No module named' in msg:
                    mod = msg.split("'")[1] if "'" in msg else ''
                    if mod:
                        print(mod.split('.')[0])
                        return
    except Exception:
        pass


def find_missing_wheel(module, tried_csv, import_map_path):
    target = normalize(module)
    tried = set(tried_csv.split(',')) if tried_csv else set()
    try:
        with open(import_map_path) as f:
            import_map = json.load(f)
        for whl in import_map.get(target, []):
            if whl not in tried:
                print(whl)
                return
    except Exception:
        pass
    for fname in sorted(os.listdir('.')):
        if (fname.endswith('.whl')
                and normalize(fname.split('-')[0]) == target
                and fname not in tried):
            print(fname)
            return


def write_failure_result(wheel_name, reason):
    print(json.dumps({
        'wheel': wheel_name,
        'status': 'FAIL',
        'reason': reason,
        'imports_tested': [],
    }))


def write_skip_result(wheel_name, reason):
    print(json.dumps({
        'wheel': wheel_name,
        'status': 'SKIP',
        'reason': reason,
        'imports_tested': [],
    }))


def read_built_status(path='/tmp/built-wheels.json'):
    try:
        with open(path) as f:
            return json.load(f)['status']
    except Exception:
        return 'no_sdists'


def read_built_wheels(path='/tmp/built-wheels.json'):
    try:
        with open(path) as f:
            return ','.join(json.load(f)['wheels'])
    except Exception:
        return ''


def group_has_built(summary_path, built_wheels_csv, wheel_index_path='/tmp/wheel-index.json'):
    built = set(built_wheels_csv.split(',')) if built_wheels_csv else set()
    try:
        with open(summary_path) as f:
            entries = json.load(f)
        with open(wheel_index_path) as f:
            wheel_index = json.load(f)
        for e in entries:
            if not isinstance(e, dict):
                continue
            key = normalize(e.get('name', '')) + '-' + str(e.get('version', ''))
            whl = wheel_index.get(key, '')
            if whl in built:
                print('yes')
                return
    except Exception as exc:
        print(f'WARNING: {exc}', file=sys.stderr)
    print('no')


def lookup_primary(label_raw, summary_path, wheel_index_path):
    if '__' not in label_raw:
        return
    label_name = normalize(label_raw.split('__', 1)[0])
    with open(wheel_index_path) as f:
        wheel_index = json.load(f)
    with open(summary_path) as f:
        entries = json.load(f)
    for entry in entries:
        norm = normalize(entry['name'])
        if label_name == norm:
            name = entry['name']
            version = entry['version']
            key = norm + '-' + version
            wheel = wheel_index.get(key, '')
            print(f'{name}\n{version}\n{wheel}')
            return


COMMANDS = {
    'read-status': lambda args: print(read_result_status(args[0])),
    'read-field': lambda args: print(read_field(args[0], args[1])),
    'print-failures': lambda args: print_failed_imports(
        args[0],
        prefix=args[args.index('--prefix') + 1] if '--prefix' in args else '  ',
    ),
    'format-row': lambda args: format_summary_row(args[0]),
    'annotate-dep': lambda args: annotate_dep(args[0], args[1]),
    'match-installed': lambda args: match_installed_wheels(args[0]),
    'lookup-wheel': lambda args: lookup_wheel(args[0], args[1], args[2]),
    'extract-missing': lambda args: extract_missing_module(args[0]),
    'find-missing': lambda args: find_missing_wheel(args[0], args[1], args[2]),
    'write-failure': lambda args: write_failure_result(args[0], args[1]),
    'write-skip': lambda args: write_skip_result(args[0], args[1]),
    'read-built-status': lambda _: print(read_built_status()),
    'read-built-wheels': lambda _: print(read_built_wheels()),
    'group-has-built': lambda args: group_has_built(args[0], args[1]),
    'lookup-primary': lambda args: lookup_primary(args[0], args[1], args[2]),
}

if __name__ == '__main__':
    cmd = sys.argv[1]
    COMMANDS[cmd](sys.argv[2:])
