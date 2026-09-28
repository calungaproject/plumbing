#!/usr/bin/env python3
"""Install a wheel via pip and verify its top-level imports succeed."""
import importlib
import json
import signal
import sys
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath

ALARM_AVAILABLE = hasattr(signal, 'SIGALRM')


def inspect_wheel(wheel_path):
    """Open a .whl as a zip and extract metadata for classification and import detection."""
    with zipfile.ZipFile(wheel_path) as zf:
        entries = zf.namelist()

        dist_info_dir = None
        for entry in entries:
            parts = PurePosixPath(entry).parts
            if parts and parts[0].endswith('.dist-info'):
                dist_info_dir = parts[0]
                break

        top_level_txt = None
        if dist_info_dir:
            tl_path = f"{dist_info_dir}/top_level.txt"
            if tl_path in entries:
                top_level_txt = zf.read(tl_path).decode('utf-8', errors='replace')

        content_entries = []
        for entry in entries:
            parts = PurePosixPath(entry).parts
            if not parts:
                continue
            if parts[0].endswith(('.dist-info', '.data')):
                continue
            if entry.endswith('/'):
                continue
            content_entries.append(entry)

        source_exts = {'.py', '.so', '.pyd'}
        has_source = any(
            PurePosixPath(e).suffix in source_exts or '.cpython-' in PurePosixPath(e).name
            for e in content_entries
        )

    return {
        'dist_info_dir': dist_info_dir,
        'content_entries': content_entries,
        'top_level_txt': top_level_txt,
        'has_source': has_source,
    }


def parse_dist_info(dist_info_dir):
    """Extract (dist_name, version) from a .dist-info directory name."""
    base = dist_info_dir.removesuffix('.dist-info')
    parts = base.split('-', 1)
    if len(parts) == 2:
        return parts[0].replace('_', '-').lower(), parts[1]
    return base.replace('_', '-').lower(), 'unknown'


def classify_wheel(inspection):
    """Return 'empty', 'data-only', or 'importable' based on wheel contents."""
    if not inspection['content_entries']:
        return 'empty'
    if not inspection['has_source']:
        return 'data-only'
    return 'importable'


def detect_import_names(inspection):
    """Determine importable module names from wheel zip entries.

    Scans for regular packages (__init__.py), namespace packages,
    top-level modules, and extension modules. Uses top_level.txt as
    a supplementary hint only, validated against actual wheel contents.
    """
    content_entries = inspection['content_entries']

    top_level_dirs = defaultdict(list)
    top_level_files = []

    for entry in content_entries:
        parts = PurePosixPath(entry).parts
        if not parts:
            continue
        if len(parts) == 1:
            top_level_files.append(parts[0])
        else:
            top_level_dirs[parts[0]].append(entry)

    import_names = set()
    namespace_imports = set()

    for dir_name, files in top_level_dirs.items():
        has_init = any(
            PurePosixPath(f).parts == (dir_name, '__init__.py')
            for f in files
        )
        if has_init:
            import_names.add(dir_name)

    for dir_name, files in top_level_dirs.items():
        if dir_name in import_names:
            continue
        has_py = any(
            PurePosixPath(f).suffix in ('.py', '.so', '.pyd')
            or '.cpython-' in PurePosixPath(f).name
            for f in files
        )
        if has_py:
            for f in files:
                fp = PurePosixPath(f)
                if fp.name == '__init__.py' and len(fp.parts) >= 2:
                    dotted = '.'.join(fp.parts[:-1])
                    namespace_imports.add(dotted)
            if not any(ni.startswith(dir_name + '.') for ni in namespace_imports):
                import_names.add(dir_name)

    filtered_ns = set()
    for ni in sorted(namespace_imports, key=lambda x: x.count('.')):
        parts = ni.split('.')
        if not any('.'.join(parts[:i]) in filtered_ns for i in range(1, len(parts))):
            filtered_ns.add(ni)
    namespace_imports = filtered_ns

    for f in top_level_files:
        if f.endswith('.py'):
            import_names.add(Path(f).stem)

    for f in top_level_files:
        if f.endswith('.so') or f.endswith('.pyd') or '.cpython-' in f:
            import_names.add(f.split('.')[0])

    import_names.update(namespace_imports)

    non_underscore = {
        name for name in import_names
        if not any(part.startswith('_') for part in name.split('.'))
        and name != 'tests'
        and not name.endswith('.libs')
        and not name.startswith('pytest_')
    }
    if non_underscore:
        import_names = non_underscore
    else:
        import_names = {
            name for name in import_names
            if name != 'tests'
            and not name.endswith('.libs')
        }

    if inspection['top_level_txt']:
        all_top_dirs = set(top_level_dirs.keys())
        all_top_files = {Path(f).stem for f in top_level_files if f.endswith('.py')}
        all_top_files.update(
            f.split('.')[0] for f in top_level_files
            if f.endswith('.so') or f.endswith('.pyd') or '.cpython-' in f
        )
        known_names = all_top_dirs | all_top_files

        for line in inspection['top_level_txt'].splitlines():
            tl_name = line.strip()
            if not tl_name:
                continue
            if '/' in tl_name or '\\' in tl_name:
                continue
            if tl_name == 'tests':
                continue
            if tl_name.startswith('_') and import_names:
                continue
            if tl_name in known_names and tl_name not in import_names:
                import_names.add(tl_name)

    return import_names


class ImportTimeout(Exception):
    """Raised by the SIGALRM handler when one import overruns its budget."""


def _raise_import_timeout(signum, frame):
    raise ImportTimeout()


def check_import(name, timeout=0):
    """Try to import a module by name; return (success, message, timed_out).

    A positive timeout (seconds) bounds the import with SIGALRM. Some import
    pathologies are not defects in the wheel but in the interpreter — namespace
    package resolution is exponential in nesting depth before Python 3.14 — and
    without a bound one such import consumes the whole pipeline budget. The
    alarm only interrupts Python-level work, so a hang inside a C extension's
    module init still needs the caller's subprocess timeout.
    """
    armed = timeout > 0 and ALARM_AVAILABLE
    if armed:
        previous_handler = signal.signal(signal.SIGALRM, _raise_import_timeout)
        signal.alarm(timeout)
    try:
        importlib.import_module(name)
        return True, f"Successfully imported {name}", False
    except ImportTimeout:
        return False, f"Timeout: import exceeded {timeout}s", True
    except ImportError as e:
        return False, f"ImportError: {e}", False
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", False
    finally:
        if armed:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_handler)


def parse_args(argv):
    """Parse argv; return (wheel, classify_only, import_timeout), or None if unusable."""
    classify_only = False
    import_timeout = 0
    positional = []

    remaining = list(argv)
    while remaining:
        arg = remaining.pop(0)
        if arg == '--classify-only':
            classify_only = True
        elif arg == '--import-timeout' or arg.startswith('--import-timeout='):
            if arg.startswith('--import-timeout='):
                value = arg.split('=', 1)[1]
            elif remaining:
                value = remaining.pop(0)
            else:
                return None
            try:
                import_timeout = int(value)
            except ValueError:
                return None
            if import_timeout < 0:
                return None
        else:
            positional.append(arg)

    if len(positional) != 1:
        return None
    return positional[0], classify_only, import_timeout


def main():
    """Classify a wheel and verify its imports; output a single JSON result line."""
    parsed = parse_args(sys.argv[1:])

    if parsed is None:
        print(json.dumps({
            "status": "ERROR",
            "reason": "Usage: verify_import.py [--classify-only] "
                      "[--import-timeout SECONDS] <wheel>",
        }))
        sys.exit(2)

    wheel, classify_only, import_timeout = parsed
    wheel_path = Path(wheel)
    if not wheel_path.exists():
        print(json.dumps({"wheel": wheel_path.name, "status": "ERROR",
                          "reason": f"File not found: {wheel_path}"}))
        sys.exit(2)

    inspection = inspect_wheel(wheel_path)

    dist_name, version = 'unknown', 'unknown'
    if inspection['dist_info_dir']:
        dist_name, version = parse_dist_info(inspection['dist_info_dir'])

    category = classify_wheel(inspection)

    if category == 'empty':
        print(json.dumps({"wheel": wheel_path.name, "dist_name": dist_name,
                          "version": version, "status": "SKIP",
                          "reason": "empty wheel (only dist-info, no source files)",
                          "imports_tested": []}))
        sys.exit(0)

    if category == 'data-only':
        print(json.dumps({"wheel": wheel_path.name, "dist_name": dist_name,
                          "version": version, "status": "SKIP",
                          "reason": "data-only package (no importable Python code)",
                          "imports_tested": []}))
        sys.exit(0)

    if classify_only:
        sys.exit(10)

    import_names = detect_import_names(inspection)

    if not import_names:
        print(json.dumps({"wheel": wheel_path.name, "dist_name": dist_name,
                          "version": version, "status": "FAIL",
                          "reason": "has source files but could not determine import names",
                          "imports_tested": []}))
        sys.exit(1)

    results = []
    any_failed = False
    timed_out_on = None
    for name in sorted(import_names):
        success, message, timed_out = check_import(name, import_timeout)
        results.append({"name": name, "success": success, "message": message})
        if not success:
            any_failed = True
        if timed_out:
            # Stop here. Whatever made this import overrun almost always applies
            # to its siblings too, and a wheel like ansible 14.3.0 offers 200 of
            # them — running the rest would multiply the budget, not spend it.
            timed_out_on = name
            break

    if timed_out_on:
        status = "TIMEOUT"
        reason = f"import of {timed_out_on} exceeded {import_timeout}s"
    elif any_failed:
        status, reason = "FAIL", "import failures"
    else:
        status, reason = "PASS", ""

    print(json.dumps({"wheel": wheel_path.name, "dist_name": dist_name,
                      "version": version, "status": status,
                      "reason": reason, "imports_tested": results}))
    sys.exit(1 if any_failed else 0)


if __name__ == '__main__':
    main()
