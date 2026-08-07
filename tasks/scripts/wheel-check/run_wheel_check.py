#!/usr/bin/env python3
"""Orchestrate wheel-check: Phase 1 individual testing, Phase 2 group fallback."""
import argparse
import glob
import json
import locale
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_import_map
import build_wheel_index
import detect_built_wheels
from verify_import import classify_wheel, inspect_wheel
from wheel_helpers import (
    annotate_dep,
    extract_missing_module,
    find_missing_wheel,
    format_summary_row,
    group_has_built,
    lookup_primary,
    match_installed_wheels,
    print_failed_imports,
    read_built_status,
    read_built_wheels,
    read_field,
    read_result_status,
)

WHEEL_INDEX_PATH = '/tmp/wheel-index.json'
BUILT_WHEELS_PATH = '/tmp/built-wheels.json'
IMPORT_MAP_PATH = '/tmp/import-to-wheel.json'
RESULTS_DIR = '/tmp/wheel-test-results'
COMBINED_RESULTS_DIR = '/tmp/wheel-test-results-combined'
VENV_PATH = '/tmp/test-venv'
VENV_GROUP_PATH = '/tmp/test-venv-group'
SEPARATOR = '=' * 50
RC_SCRIPT_ERROR = 2
PYTHON_PATTERN = re.compile(r'^python\d+\.\d+$')


def create_venv(python, path):
    shutil.rmtree(path, ignore_errors=True)
    try:
        subprocess.run([python, '-m', 'venv', path], check=True,  # nosemgrep
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print(f'ERROR: Python interpreter {python!r} not found',
              file=sys.stderr)
        sys.exit(RC_SCRIPT_ERROR)
    except subprocess.CalledProcessError as exc:
        print(f'ERROR: Failed to create venv at {path!r} '
              f'using {python!r} (exit code {exc.returncode})',
              file=sys.stderr)
        sys.exit(RC_SCRIPT_ERROR)
    return path


def pip_install(venv, *packages):
    cmd = [os.path.join(venv, 'bin', 'pip'), 'install',
           '--no-index', '--find-links', '.'] + list(packages)
    result = subprocess.run(cmd, capture_output=True, text=True)  # nosemgrep
    if result.stdout:
        print(result.stdout, end='')
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, end='', file=sys.stderr)
        return False
    return True


def pip_list_json(venv):
    result = subprocess.run(  # nosemgrep
        [os.path.join(venv, 'bin', 'pip'), 'list', '--format=json'],
        capture_output=True, text=True)
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f'WARNING: Failed to parse pip list JSON: {exc}',
              file=sys.stderr)
        return []


def verify_in_venv(venv, script_dir, wheel, result_file):
    result = subprocess.run(  # nosemgrep
        [os.path.join(venv, 'bin', 'python'),
         os.path.join(script_dir, 'verify_import.py'), wheel],
        capture_output=True, text=True)
    if result.stdout.strip():
        with open(result_file, 'w') as f:
            f.write(result.stdout)
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)
    return result.returncode


def write_result(path, data):
    with open(path, 'w') as f:
        json.dump(data, f)


def _fail_no_output(wheel):
    return {'wheel': wheel, 'status': 'FAIL',
            'reason': 'verify_import failed without output', 'imports_tested': []}


def result_path(results_dir, wheel):
    return os.path.join(results_dir, wheel.replace('/', '_') + '.json')


def run_phase1(wheels, built_set, results_dir, python, files_dir, script_dir):
    had_failures = False

    for wheel in wheels:
        rpath = result_path(results_dir, wheel)

        if built_set is not None and wheel not in built_set:
            print(SEPARATOR)
            print(f'SKIP (no sdist, cached): {wheel}')
            write_result(rpath, {
                'wheel': wheel, 'status': 'SKIP',
                'reason': 'no matching sdist (not built from source)',
                'imports_tested': [],
            })
            continue

        print(SEPARATOR)
        print(f'Testing {wheel}...')

        wheel_path = os.path.join(files_dir, wheel)
        try:
            inspection = inspect_wheel(wheel_path)
            category = classify_wheel(inspection)
        except Exception as exc:
            print(f'WARNING: Could not inspect {wheel}: {exc}', file=sys.stderr)
            category = None
        if category in ('empty', 'data-only'):
            reason = ('empty wheel (only dist-info, no source files)' if category == 'empty'
                      else 'data-only package (no importable Python code)')
            write_result(rpath, {
                'wheel': wheel, 'status': 'SKIP',
                'reason': reason, 'imports_tested': [],
            })
            print(f'SKIP: {wheel}')
            continue

        print('Setting up virtual environment...')
        create_venv(python, VENV_PATH)

        print('Installing wheel...')
        if not pip_install(VENV_PATH, wheel):
            print(f'FAIL: Installation failed for {wheel}')
            write_result(rpath, {
                'wheel': wheel, 'status': 'FAIL',
                'reason': 'pip install failed', 'imports_tested': [],
            })
            had_failures = True
            continue

        print('Verifying import...')
        rc = verify_in_venv(VENV_PATH, script_dir, wheel, rpath)
        if rc == 0:
            print(f'PASS: {wheel}')
        elif rc == RC_SCRIPT_ERROR:
            print(f'ERROR: Script error for {wheel}')
            if not os.path.exists(rpath):
                write_result(rpath, _fail_no_output(wheel))
            had_failures = True
        else:
            if not os.path.exists(rpath):
                write_result(rpath, _fail_no_output(wheel))
            status = read_result_status(rpath)
            if status == 'SKIP':
                print(f'SKIP: {wheel}')
            else:
                print(f'FAIL: {wheel}')
                had_failures = True
                print_failed_imports(rpath, prefix='  ')

    return had_failures


def print_summary(results_dir, title='              SUMMARY REPORT'):
    print()
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)
    print()

    pass_count = 0
    fail_count = 0
    skip_count = 0

    print(f'{"WHEEL":<60s} {"STATUS":<8s} {"DETAILS"}')
    print(f'{"-----":<60s} {"------":<8s} {"-------"}')

    result_files = sorted(glob.glob(os.path.join(results_dir, '*.json')),
                          key=locale.strxfrm)
    for rfile in result_files:
        status, wheel, reason = format_summary_row(rfile)
        print(f'{wheel:<60s} {status:<8s} {reason}')

        if status == 'FAIL':
            print_failed_imports(rfile, prefix='  -> ')

        if status == 'PASS':
            pass_count += 1
        elif status == 'SKIP':
            skip_count += 1
        else:
            fail_count += 1

    total = pass_count + fail_count + skip_count
    print()
    print(f'Total: {total}  |  PASS: {pass_count}  |  FAIL: {fail_count}  |  SKIP: {skip_count}')
    print()

    return pass_count, fail_count, skip_count


def run_phase2(summary_files, built_set, results_dir, combined_dir, python, files_dir, script_dir):
    print()
    print(SEPARATOR)
    print('Individual wheel testing had failures.')
    print('Retrying using build-sequence-summary groups...')
    print(SEPARATOR)

    if not summary_files:
        print('No build-sequence-summary files found — cannot run group tests.')
        return

    print(f'Found {len(summary_files)} build-sequence-summary file(s)')

    build_import_map.main(files_dir, IMPORT_MAP_PATH)

    shutil.rmtree(combined_dir, ignore_errors=True)
    os.makedirs(combined_dir)
    for rfile in glob.glob(os.path.join(results_dir, '*.json')):
        shutil.copy2(rfile, combined_dir)

    for group_idx, summary_file in enumerate(summary_files, 1):
        label = os.path.basename(summary_file).removesuffix('.json').removeprefix('build-sequence-summary-')

        print()
        print(SEPARATOR)
        print(f'Group {group_idx}: {label}')
        print(SEPARATOR)

        try:
            primary = lookup_primary(label, summary_file, WHEEL_INDEX_PATH)
        except Exception as exc:
            print(f'  WARNING: Could not read summary for {label}: {exc}',
                  file=sys.stderr)
            continue
        if primary is None or not primary[2]:
            print(f'  WARNING: No matching wheel for {label}, skipping')
            continue

        primary_name, primary_version, primary_wheel = primary

        if built_set is not None:
            if not group_has_built(summary_file, built_set, WHEEL_INDEX_PATH):
                print('  SKIP group (no wheels with sdist match)')
                continue

        print(f'  Installing {primary_name}=={primary_version}...')
        create_venv(python, VENV_GROUP_PATH)
        if not pip_install(VENV_GROUP_PATH, f'{primary_name}=={primary_version}'):
            print(f'  WARNING: Group install failed for {label}, skipping')
            continue

        pip_json = pip_list_json(VENV_GROUP_PATH)
        installed_wheels = match_installed_wheels(WHEEL_INDEX_PATH, pip_json=pip_json)

        group_failed = False
        tested_in_group = set()
        wheel_idx = 0

        while wheel_idx < len(installed_wheels):
            wheel = installed_wheels[wheel_idx]
            wheel_idx += 1
            rpath = result_path(combined_dir, wheel)

            if built_set is not None and wheel not in built_set:
                continue

            if os.path.exists(rpath):
                prev_status = read_result_status(rpath)
                if prev_status == 'SKIP':
                    continue

            wheel_path = os.path.join(files_dir, wheel)
            if os.path.exists(wheel_path):
                try:
                    inspection = inspect_wheel(wheel_path)
                    if classify_wheel(inspection) in ('empty', 'data-only'):
                        continue
                except Exception as exc:
                    print(f'  WARNING: Could not inspect {wheel}: {exc}',
                          file=sys.stderr)

            if wheel in tested_in_group:
                continue

            print(f'  Testing import (group {group_idx}): {wheel}...')

            prev_undeclared = read_field(rpath, 'undeclared_dep') if os.path.exists(rpath) else ''

            rc = verify_in_venv(VENV_GROUP_PATH, script_dir, wheel, rpath)
            if rc == 0:
                print(f'  PASS: {wheel}')
                tested_in_group.add(wheel)
                if prev_undeclared:
                    annotate_dep(rpath, prev_undeclared)
                continue

            if not os.path.exists(rpath):
                write_result(rpath, _fail_no_output(wheel))

            if rc == RC_SCRIPT_ERROR:
                print(f'  ERROR: Script error for {wheel}')
                group_failed = True
                continue

            status = read_result_status(rpath)
            if status == 'SKIP':
                print(f'  SKIP: {wheel}')
                continue

            saved_wheel_idx = wheel_idx
            saved_installed = list(installed_wheels)
            undeclared_deps = []
            tried_wheels = set()
            found_deps = []
            fallback_resolved = False

            while True:
                missing_module = extract_missing_module(rpath)
                if not missing_module:
                    break

                missing_wheel = find_missing_wheel(missing_module, tried_wheels, IMPORT_MAP_PATH)
                if not missing_wheel:
                    break

                tried_wheels.add(missing_wheel)
                found_deps.append(missing_wheel)
                undeclared_deps.append(missing_module)

                print(f'  Retrying with undeclared dep(s): {" ".join(found_deps)}')
                create_venv(python, VENV_GROUP_PATH)
                install_args = [f'{primary_name}=={primary_version}'] + found_deps
                if not pip_install(VENV_GROUP_PATH, *install_args):
                    print(f'  WARNING: Install failed with deps: {" ".join(found_deps)}')
                    continue

                pip_json = pip_list_json(VENV_GROUP_PATH)
                installed_wheels = match_installed_wheels(WHEEL_INDEX_PATH, pip_json=pip_json)
                wheel_idx = 0

                rc = verify_in_venv(VENV_GROUP_PATH, script_dir, wheel, rpath)
                if rc == 0:
                    dep_str = ','.join(undeclared_deps)
                    print(f'  PASS: {wheel} (with undeclared deps: {dep_str})')
                    annotate_dep(rpath, dep_str)
                    tested_in_group.add(wheel)
                    fallback_resolved = True
                    break

            if fallback_resolved:
                continue

            wheel_idx = saved_wheel_idx
            installed_wheels = saved_installed

            create_venv(python, VENV_GROUP_PATH)
            if not pip_install(VENV_GROUP_PATH, f'{primary_name}=={primary_version}'):
                print(f'  WARNING: Could not restore group venv for {label}, skipping remaining wheels')
                break

            print(f'  FAIL: {wheel}')
            group_failed = True
            print_failed_imports(rpath, prefix='    -> ')

        if group_failed:
            print(f'  Group {group_idx} had failures')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Wheel-check orchestrator')
    parser.add_argument('--python', default='python3.12')
    parser.add_argument('--files-dir', default=None)
    parser.add_argument('--script-dir', default=None)
    args = parser.parse_args(argv)

    files_dir = args.files_dir or os.getcwd()
    script_dir = args.script_dir or str(Path(__file__).resolve().parent)
    python = args.python

    if not PYTHON_PATTERN.match(python):
        print(f'ERROR: Invalid python interpreter: {python!r}', file=sys.stderr)
        return 1

    os.chdir(files_dir)
    try:
        locale.setlocale(locale.LC_COLLATE, '')
    except locale.Error:
        print('WARNING: locale not available, using default sort order',
              file=sys.stderr)
    wheels = sorted((f for f in os.listdir(files_dir) if f.endswith('.whl')),
                    key=locale.strxfrm)
    if not wheels:
        print(f'ERROR: No .whl files found in {files_dir}')
        return 1

    os.makedirs(RESULTS_DIR, exist_ok=True)

    build_wheel_index.main(files_dir, WHEEL_INDEX_PATH)
    detect_built_wheels.main(files_dir, WHEEL_INDEX_PATH, BUILT_WHEELS_PATH)

    built_status = read_built_status(BUILT_WHEELS_PATH)

    if built_status == 'all_cached':
        print()
        print('All wheels were pulled from cache — no sdists found, nothing built from source.')
        print('Skipping all import tests.')
        print()
        print('RESULT: PASSED')
        return 0

    built_set = None
    if built_status == 'has_built':
        built_csv = read_built_wheels(BUILT_WHEELS_PATH)
        built_set = set(built_csv.split(',')) if built_csv else set()

    had_failures = run_phase1(wheels, built_set, RESULTS_DIR, python, files_dir, script_dir)

    print_summary(RESULTS_DIR)

    if not had_failures:
        print('RESULT: PASSED')
        return 0

    summary_files = sorted(glob.glob(os.path.join(files_dir, 'build-sequence-summary-*.json')),
                           key=locale.strxfrm)
    if not summary_files:
        print('No build-sequence-summary files found — cannot run group tests.')
        print('RESULT: FAILED')
        return 1

    run_phase2(summary_files, built_set, RESULTS_DIR, COMBINED_RESULTS_DIR,
               python, files_dir, script_dir)

    pass_count, fail_count, skip_count = print_summary(
        COMBINED_RESULTS_DIR, title='         BUILD GROUP SUMMARY REPORT')

    total = pass_count + fail_count + skip_count
    if total == 0:
        print('RESULT: NO TESTS RUN')
        return 1

    if fail_count > 0:
        print('RESULT: FAILED')
        return 1

    print('RESULT: PASSED (via build-group fallback)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
