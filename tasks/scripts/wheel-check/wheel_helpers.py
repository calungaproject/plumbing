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
    return (s, w, r)


def annotate_dep(path, dep_string):
    with open(path) as f:
        d = json.load(f)
    d['undeclared_dep'] = dep_string
    with open(path, 'w') as f:
        json.dump(d, f)


def match_installed_wheels(wheel_index_path, pip_json=None):
    with open(wheel_index_path) as f:
        wheel_index = json.load(f)
    if pip_json is None:
        pip_json = json.load(sys.stdin)
    matched = []
    for pkg in pip_json:
        key = normalize(pkg['name']) + '-' + pkg['version']
        whl = wheel_index.get(key)
        if whl:
            matched.append(whl)
    return matched


def lookup_wheel(wheel_index_path, name, version):
    with open(wheel_index_path) as f:
        wheel_index = json.load(f)
    key = normalize(name) + '-' + version
    return wheel_index.get(key, '')


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
                        return mod.split('.')[0]
    except Exception:
        pass
    return None


def find_missing_wheel(module, tried, import_map_path):
    target = normalize(module)
    if isinstance(tried, str):
        tried = set(tried.split(',')) if tried else set()
    try:
        with open(import_map_path) as f:
            import_map = json.load(f)
        for whl in import_map.get(target, []):
            if whl not in tried:
                return whl
    except Exception:
        pass
    for fname in sorted(os.listdir('.')):
        if (fname.endswith('.whl')
                and normalize(fname.split('-')[0]) == target
                and fname not in tried):
            return fname
    return None


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


def group_has_built(summary_path, built_wheels, wheel_index_path='/tmp/wheel-index.json'):
    if isinstance(built_wheels, str):
        built_wheels = set(built_wheels.split(',')) if built_wheels else set()
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
            if whl in built_wheels:
                return True
    except Exception as exc:
        print(f'WARNING: {exc}', file=sys.stderr)
    return False


def lookup_primary(label_raw, summary_path, wheel_index_path):
    if '__' not in label_raw:
        return None
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
            return (name, version, wheel)
    return None


def _cli_format_row(args):
    s, w, r = format_summary_row(args[0])
    print(f'{s}\t{w}\t{r}')


def _cli_match_installed(args):
    for whl in match_installed_wheels(args[0]):
        print(whl)


def _cli_extract_missing(args):
    result = extract_missing_module(args[0])
    if result:
        print(result)


def _cli_find_missing(args):
    result = find_missing_wheel(args[0], args[1], args[2])
    if result:
        print(result)


def _cli_group_has_built(args):
    print('yes' if group_has_built(args[0], args[1]) else 'no')


def _cli_lookup_primary(args):
    result = lookup_primary(args[0], args[1], args[2])
    if result:
        print(f'{result[0]}\n{result[1]}\n{result[2]}')


COMMANDS = {
    'read-status': lambda args: print(read_result_status(args[0])),
    'read-field': lambda args: print(read_field(args[0], args[1])),
    'print-failures': lambda args: print_failed_imports(
        args[0],
        prefix=args[args.index('--prefix') + 1] if '--prefix' in args else '  ',
    ),
    'format-row': lambda args: _cli_format_row(args),
    'annotate-dep': lambda args: annotate_dep(args[0], args[1]),
    'match-installed': lambda args: _cli_match_installed(args),
    'lookup-wheel': lambda args: print(lookup_wheel(args[0], args[1], args[2])),
    'extract-missing': lambda args: _cli_extract_missing(args),
    'find-missing': lambda args: _cli_find_missing(args),
    'write-failure': lambda args: write_failure_result(args[0], args[1]),
    'write-skip': lambda args: write_skip_result(args[0], args[1]),
    'read-built-status': lambda _: print(read_built_status()),
    'read-built-wheels': lambda _: print(read_built_wheels()),
    'group-has-built': lambda args: _cli_group_has_built(args),
    'lookup-primary': lambda args: _cli_lookup_primary(args),
}

if __name__ == '__main__':
    cmd = sys.argv[1]
    COMMANDS[cmd](sys.argv[2:])
