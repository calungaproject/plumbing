#!/usr/bin/env python3
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_import import (
    check_import,
    classify_wheel,
    detect_import_names,
    inspect_wheel,
    main,
    parse_dist_info,
)


def _make_wheel(name, version, files, top_level_txt=None, dir_entries=None):
    """Create a minimal .whl file (zip) with the given structure."""
    dist_info = f"{name}-{version}.dist-info"
    fd, path = tempfile.mkstemp(suffix='.whl')
    os.close(fd)
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr(f"{dist_info}/METADATA", f"Name: {name}\nVersion: {version}\n")
        zf.writestr(f"{dist_info}/RECORD", "")
        if top_level_txt is not None:
            zf.writestr(f"{dist_info}/top_level.txt", top_level_txt)
        for f_path, content in files.items():
            zf.writestr(f_path, content)
        for d in (dir_entries or []):
            zf.mkdir(d)
    return path


class TestInspectWheel(unittest.TestCase):
    def _wheel(self, *args, **kwargs):
        path = _make_wheel(*args, **kwargs)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        return path

    def test_basic_package(self):
        path = self._wheel('foo', '1.0', {'foo/__init__.py': '', 'foo/core.py': 'x=1'})
        result = inspect_wheel(path)
        self.assertEqual(result['dist_info_dir'], 'foo-1.0.dist-info')
        self.assertTrue(result['has_source'])
        self.assertIn('foo/__init__.py', result['content_entries'])
        self.assertIn('foo/core.py', result['content_entries'])

    def test_top_level_txt(self):
        path = self._wheel('bar', '2.0', {'bar/__init__.py': ''}, top_level_txt='bar\n')
        result = inspect_wheel(path)
        self.assertEqual(result['top_level_txt'], 'bar\n')

    def test_no_top_level_txt(self):
        path = self._wheel('baz', '1.0', {'baz/__init__.py': ''})
        result = inspect_wheel(path)
        self.assertIsNone(result['top_level_txt'])

    def test_data_only(self):
        path = self._wheel('data_pkg', '1.0', {'data_pkg/data.txt': 'hello'})
        result = inspect_wheel(path)
        self.assertFalse(result['has_source'])

    def test_empty_wheel(self):
        path = self._wheel('empty', '1.0', {})
        result = inspect_wheel(path)
        self.assertEqual(result['content_entries'], [])
        self.assertFalse(result['has_source'])

    def test_filters_dist_info_and_data(self):
        path = self._wheel('pkg', '1.0', {
            'pkg/__init__.py': '',
            'pkg-1.0.data/scripts/run.sh': '#!/bin/bash',
        })
        result = inspect_wheel(path)
        content_names = result['content_entries']
        self.assertIn('pkg/__init__.py', content_names)
        self.assertNotIn('pkg-1.0.data/scripts/run.sh', content_names)

    def test_extension_module(self):
        path = self._wheel('ext', '1.0', {
            'ext/__init__.py': '',
            'ext/_fast.cpython-312-x86_64-linux-gnu.so': b'\x00',
        })
        result = inspect_wheel(path)
        self.assertTrue(result['has_source'])

    def test_directory_entries_filtered(self):
        path = self._wheel('pkg', '1.0', {'pkg/__init__.py': ''},
                           dir_entries=['pkg/'])
        result = inspect_wheel(path)
        self.assertNotIn('pkg/', result['content_entries'])
        self.assertIn('pkg/__init__.py', result['content_entries'])


class TestParseDistInfo(unittest.TestCase):
    def test_normal(self):
        name, version = parse_dist_info('click-8.1.0.dist-info')
        self.assertEqual(name, 'click')
        self.assertEqual(version, '8.1.0')

    def test_underscore_name(self):
        name, version = parse_dist_info('pydantic_ai_slim-2.10.0.dist-info')
        self.assertEqual(name, 'pydantic-ai-slim')
        self.assertEqual(version, '2.10.0')

    def test_no_version(self):
        name, version = parse_dist_info('weird.dist-info')
        self.assertEqual(name, 'weird')
        self.assertEqual(version, 'unknown')


class TestClassifyWheel(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(classify_wheel({'content_entries': [], 'has_source': False}), 'empty')

    def test_data_only(self):
        self.assertEqual(classify_wheel({
            'content_entries': ['pkg/data.txt'],
            'has_source': False,
        }), 'data-only')

    def test_importable(self):
        self.assertEqual(classify_wheel({
            'content_entries': ['pkg/__init__.py'],
            'has_source': True,
        }), 'importable')


class TestDetectImportNames(unittest.TestCase):
    def _wheel(self, *args, **kwargs):
        path = _make_wheel(*args, **kwargs)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        return path

    def test_regular_package(self):
        path = self._wheel('mypkg', '1.0', {
            'mypkg/__init__.py': '',
            'mypkg/core.py': '',
        })
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertEqual(names, {'mypkg'})

    def test_top_level_module(self):
        path = self._wheel('single', '1.0', {'mymod.py': 'x=1'})
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('mymod', names)

    def test_extension_module(self):
        path = self._wheel('ext', '1.0', {
            'fastmod.cpython-312-x86_64-linux-gnu.so': b'\x00',
        })
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('fastmod', names)

    def test_pyd_extension(self):
        path = self._wheel('ext', '1.0', {'winmod.pyd': b'\x00'})
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('winmod', names)

    def test_filters_underscore_prefixed(self):
        path = self._wheel('pkg', '1.0', {
            'pkg/__init__.py': '',
            '_internal/__init__.py': '',
        })
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('pkg', names)
        self.assertNotIn('_internal', names)

    def test_filters_tests(self):
        path = self._wheel('pkg', '1.0', {
            'pkg/__init__.py': '',
            'tests/__init__.py': '',
        })
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('pkg', names)
        self.assertNotIn('tests', names)

    def test_filters_libs(self):
        path = self._wheel('pkg', '1.0', {
            'pkg/__init__.py': '',
            'pkg.libs/libfoo.so': b'\x00',
        })
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('pkg', names)
        self.assertNotIn('pkg.libs', names)

    def test_filters_pytest_prefix(self):
        """pytest_ imports are filtered when a non-pytest import exists."""
        path = self._wheel('pytest_cov', '1.0', {
            'pytest_cov/__init__.py': '',
            'pytest_cov/plugin.py': '',
            'covmod/__init__.py': '',
        })
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('covmod', names)
        self.assertNotIn('pytest_cov', names)

    def test_pytest_prefix_only_package(self):
        """When only pytest_ imports exist, they're kept after fallback filtering."""
        path = self._wheel('pytest_mock', '1.0', {
            'pytest_mock/__init__.py': '',
        })
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertEqual(names, {'pytest_mock'})

    def test_top_level_txt_adds_valid_name(self):
        path = self._wheel('pkg', '1.0', {
            'mypkg/__init__.py': '',
            'extra/__init__.py': '',
        }, top_level_txt='mypkg\nextra\n')
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('mypkg', names)
        self.assertIn('extra', names)

    def test_top_level_txt_ignores_unknown(self):
        path = self._wheel('pkg', '1.0', {
            'real/__init__.py': '',
        }, top_level_txt='real\nphantom\n')
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('real', names)
        self.assertNotIn('phantom', names)

    def test_top_level_txt_ignores_path_separators(self):
        path = self._wheel('pkg', '1.0', {
            'real/__init__.py': '',
        }, top_level_txt='real\nbad/path\nback\\slash\n')
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('real', names)
        self.assertNotIn('bad/path', names)
        self.assertNotIn('back\\slash', names)

    def test_top_level_txt_ignores_tests(self):
        path = self._wheel('pkg', '1.0', {
            'real/__init__.py': '',
            'tests/__init__.py': '',
        }, top_level_txt='real\ntests\n')
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('real', names)
        self.assertNotIn('tests', names)

    def test_top_level_txt_skips_underscore_when_imports_exist(self):
        path = self._wheel('pkg', '1.0', {
            'real/__init__.py': '',
            '_private/__init__.py': '',
        }, top_level_txt='real\n_private\n')
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('real', names)
        self.assertNotIn('_private', names)

    def test_namespace_package(self):
        path = self._wheel('ns_pkg', '1.0', {
            'ns/sub/__init__.py': '',
            'ns/sub/mod.py': '',
        })
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('ns.sub', names)

    def test_multiple_packages(self):
        path = self._wheel('multi', '1.0', {
            'alpha/__init__.py': '',
            'beta/__init__.py': '',
        })
        inspection = inspect_wheel(path)
        names = detect_import_names(inspection)
        self.assertIn('alpha', names)
        self.assertIn('beta', names)


class TestCheckImport(unittest.TestCase):
    def test_stdlib_module(self):
        success, msg = check_import('json')
        self.assertTrue(success)
        self.assertIn('json', msg)

    def test_nonexistent_module(self):
        success, msg = check_import('nonexistent_module_xyz_12345')
        self.assertFalse(success)
        self.assertIn('ImportError', msg)

    def test_non_import_error(self):
        with patch('verify_import.importlib.import_module', side_effect=RuntimeError('boom')):
            success, msg = check_import('anything')
            self.assertFalse(success)
            self.assertIn('RuntimeError', msg)
            self.assertIn('boom', msg)


class TestMain(unittest.TestCase):
    def _wheel(self, *args, **kwargs):
        path = _make_wheel(*args, **kwargs)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        return path

    def _run_main(self, *args):
        """Run main() in-process, capturing stdout and SystemExit."""
        with patch('sys.argv', ['verify_import.py'] + list(args)):
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                try:
                    main()
                    return 0, mock_out.getvalue()
                except SystemExit as e:
                    return e.code, mock_out.getvalue()

    def test_classify_only_importable(self):
        path = self._wheel('clstest', '1.0', {'clstest/__init__.py': ''})
        rc, _ = self._run_main('--classify-only', path)
        self.assertEqual(rc, 10)

    def test_classify_only_empty(self):
        path = self._wheel('emptytest', '1.0', {})
        rc, out = self._run_main('--classify-only', path)
        self.assertEqual(rc, 0)
        d = json.loads(out)
        self.assertEqual(d['status'], 'SKIP')
        self.assertIn('empty', d['reason'])

    def test_classify_only_data_only(self):
        path = self._wheel('datatest', '1.0', {'datatest/data.csv': 'a,b,c'})
        rc, out = self._run_main('--classify-only', path)
        self.assertEqual(rc, 0)
        d = json.loads(out)
        self.assertEqual(d['status'], 'SKIP')
        self.assertIn('data-only', d['reason'])

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = self._run_main(os.path.join(td, 'nonexistent.whl'))
        self.assertEqual(rc, 2)
        d = json.loads(out)
        self.assertEqual(d['status'], 'ERROR')

    def test_no_args(self):
        rc, out = self._run_main()
        self.assertEqual(rc, 2)

    def test_import_pass(self):
        path = self._wheel('jsonwrap', '1.0', {'json_wrap/__init__.py': ''})
        rc, out = self._run_main(path)
        d = json.loads(out)
        self.assertEqual(d['wheel'], os.path.basename(path))
        self.assertIn('dist_name', d)
        self.assertIn('version', d)
        self.assertIn('imports_tested', d)

    def test_import_fail(self):
        path = self._wheel('xyznonexist', '1.0', {
            'xyznonexist_pkg/__init__.py': 'import nonexistent_module_abc_999',
        })
        rc, out = self._run_main(path)
        d = json.loads(out)
        self.assertEqual(d['status'], 'FAIL')
        self.assertEqual(rc, 1)
        self.assertTrue(any(not t['success'] for t in d['imports_tested']))

    def test_private_only_imports(self):
        path = self._wheel('odd', '1.0', {'_only_private/__init__.py': ''})
        rc, out = self._run_main(path)
        d = json.loads(out)
        self.assertIn('imports_tested', d)

    def test_no_dist_info(self):
        fd, path = tempfile.mkstemp(suffix='.whl')
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        with zipfile.ZipFile(path, 'w') as zf:
            zf.writestr('pkg/__init__.py', '')
        rc, out = self._run_main(path)
        d = json.loads(out)
        self.assertEqual(d['dist_name'], 'unknown')


if __name__ == '__main__':
    unittest.main()
