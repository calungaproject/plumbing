#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_import_map import main


def _make_wheel(dir_path, name, version, files, top_level_txt=None):
    """Create a minimal .whl in the given directory."""
    dist_info = f"{name}-{version}.dist-info"
    whl_name = f"{name}-{version}-py3-none-any.whl"
    whl_path = os.path.join(dir_path, whl_name)
    with zipfile.ZipFile(whl_path, 'w') as zf:
        zf.writestr(f"{dist_info}/METADATA", f"Name: {name}\nVersion: {version}\n")
        zf.writestr(f"{dist_info}/RECORD", "")
        if top_level_txt is not None:
            zf.writestr(f"{dist_info}/top_level.txt", top_level_txt)
        for f_path, content in files.items():
            zf.writestr(f_path, content)
    return whl_name


class TestBuildImportMap(unittest.TestCase):
    def _run_in_dir(self, wheels):
        """Create wheels in a temp dir and call main() directly."""
        tmpdir = tempfile.mkdtemp()
        output_path = os.path.join(tmpdir, 'import-to-wheel.json')
        whl_names = []
        for w in wheels:
            whl_names.append(_make_wheel(tmpdir, **w))
        imap = main(wheels_dir=tmpdir, output_path=output_path)
        written = json.load(open(output_path))
        for f in os.listdir(tmpdir):
            os.unlink(os.path.join(tmpdir, f))
        os.rmdir(tmpdir)
        return imap, written, whl_names

    def test_single_package(self):
        imap, written, names = self._run_in_dir([{
            'name': 'click', 'version': '8.1.0',
            'files': {'click/__init__.py': '', 'click/core.py': ''},
        }])
        self.assertIn('click', imap)
        self.assertEqual(imap['click'], [names[0]])
        self.assertEqual(imap, written)

    def test_multiple_packages(self):
        imap, _, names = self._run_in_dir([
            {
                'name': 'click', 'version': '8.1.0',
                'files': {'click/__init__.py': ''},
            },
            {
                'name': 'flask', 'version': '3.0.0',
                'files': {'flask/__init__.py': ''},
            },
        ])
        self.assertIn('click', imap)
        self.assertIn('flask', imap)

    def test_different_import_name(self):
        imap, _, names = self._run_in_dir([{
            'name': 'beautifulsoup4', 'version': '4.12.0',
            'files': {'bs4/__init__.py': '', 'bs4/element.py': ''},
            'top_level_txt': 'bs4\n',
        }])
        self.assertIn('bs4', imap)
        self.assertEqual(imap['bs4'], [names[0]])

    def test_normalizes_import_name(self):
        imap, _, names = self._run_in_dir([{
            'name': 'My_Package', 'version': '1.0',
            'files': {'My_Package/__init__.py': ''},
            'top_level_txt': 'My_Package\n',
        }])
        self.assertIn('my_package', imap)

    def test_empty_dir(self):
        imap, _, _ = self._run_in_dir([])
        self.assertEqual(len(imap), 0)

    def test_data_only_wheel_skipped(self):
        imap, _, _ = self._run_in_dir([{
            'name': 'data_pkg', 'version': '1.0',
            'files': {'data_pkg/data.csv': 'a,b'},
        }])
        self.assertEqual(len(imap), 0)

    def test_multiple_imports_from_one_wheel(self):
        imap, _, names = self._run_in_dir([{
            'name': 'multi', 'version': '1.0',
            'files': {
                'alpha/__init__.py': '',
                'beta/__init__.py': '',
            },
        }])
        self.assertIn('alpha', imap)
        self.assertIn('beta', imap)
        self.assertEqual(imap['alpha'], [names[0]])
        self.assertEqual(imap['beta'], [names[0]])

    def test_writes_to_output_path(self):
        tmpdir = tempfile.mkdtemp()
        output_path = os.path.join(tmpdir, 'custom-map.json')
        _make_wheel(tmpdir, 'pkg', '1.0', {'pkg/__init__.py': ''})
        main(wheels_dir=tmpdir, output_path=output_path)
        self.assertTrue(os.path.exists(output_path))
        written = json.load(open(output_path))
        self.assertIn('pkg', written)
        for f in os.listdir(tmpdir):
            os.unlink(os.path.join(tmpdir, f))
        os.rmdir(tmpdir)


if __name__ == '__main__':
    unittest.main()
