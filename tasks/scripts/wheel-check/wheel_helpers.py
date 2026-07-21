#!/usr/bin/env python3
import json
import os
import re
import sys


def normalize(name):
    return re.sub(r'[-_.]+', '_', name).lower()


def read_result_status(path):
    try:
        return json.load(open(path)).get('status', 'FAIL')
    except Exception:
        return 'FAIL'


def read_field(path, field):
    try:
        return json.load(open(path)).get(field, '')
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
        d = json.load(open(path))
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
    wheel_index = json.load(open(wheel_index_path))
    installed = json.load(sys.stdin)
    for pkg in installed:
        key = normalize(pkg['name']) + '-' + pkg['version']
        whl = wheel_index.get(key)
        if whl:
            print(whl)


def lookup_wheel(wheel_index_path, name, version):
    wheel_index = json.load(open(wheel_index_path))
    key = normalize(name) + '-' + version
    print(wheel_index.get(key, ''))


def extract_missing_module(path):
    try:
        d = json.load(open(path))
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
        import_map = json.load(open(import_map_path))
        for whl in import_map.get(target, []):
            if whl not in tried:
                print(whl)
                return
    except Exception:
        pass
    for f in sorted(os.listdir('.')):
        if f.endswith('.whl') and normalize(f.split('-')[0]) == target and f not in tried:
            print(f)
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


def read_built_status():
    try:
        return json.load(open('/tmp/built-wheels.json'))['status']
    except Exception:
        return 'no_sdists'


def read_built_wheels():
    try:
        return ','.join(json.load(open('/tmp/built-wheels.json'))['wheels'])
    except Exception:
        return ''


def group_has_built(summary_path, built_wheels_csv):
    built = set(built_wheels_csv.split(','))
    try:
        entries = json.load(open(summary_path))
        wheel_index = json.load(open('/tmp/wheel-index.json'))
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
    label = re.sub(r'[-.]', '_', label_raw).lower()
    wheel_index = json.load(open(wheel_index_path))
    for entry in json.load(open(summary_path)):
        norm = normalize(entry['name'])
        if label.startswith(norm + '__'):
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
