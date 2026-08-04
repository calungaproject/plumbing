#!/usr/bin/env python3
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_wheel_check


def make_wheel(directory, name, version, has_source=True):
    """Create a minimal .whl file for testing."""
    whl_name = f'{name}-{version}-0-py3-none-any.whl'
    whl_path = os.path.join(directory, whl_name)
    dist_info = f'{name}-{version}.dist-info'
    with zipfile.ZipFile(whl_path, 'w') as zf:
        zf.writestr(f'{dist_info}/METADATA', f'Name: {name}\nVersion: {version}\n')
        zf.writestr(f'{dist_info}/RECORD', '')
        if has_source:
            zf.writestr(f'{name}/__init__.py', '')
    return whl_name


def make_data_wheel(directory, name, version):
    """Create a data-only .whl (no .py files)."""
    whl_name = f'{name}-{version}-0-py3-none-any.whl'
    whl_path = os.path.join(directory, whl_name)
    dist_info = f'{name}-{version}.dist-info'
    with zipfile.ZipFile(whl_path, 'w') as zf:
        zf.writestr(f'{dist_info}/METADATA', f'Name: {name}\nVersion: {version}\n')
        zf.writestr(f'{dist_info}/RECORD', '')
        zf.writestr('data/config.yaml', 'key: value')
    return whl_name


def make_sdist(directory, name, version):
    """Create a minimal sdist tarball (just touch the file)."""
    sdist_name = f'{name}-{version}.tar.gz'
    Path(os.path.join(directory, sdist_name)).touch()
    return sdist_name


def make_summary(directory, label, entries):
    """Create a build-sequence-summary JSON file."""
    fname = f'build-sequence-summary-{label}.json'
    with open(os.path.join(directory, fname), 'w') as f:
        json.dump(entries, f)
    return fname


class TestCreateVenv(unittest.TestCase):
    @patch('run_wheel_check.subprocess.run')
    @patch('run_wheel_check.shutil.rmtree')
    def test_creates_venv(self, mock_rmtree, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = run_wheel_check.create_venv('python3.12', '/tmp/test-venv')
        mock_rmtree.assert_called_once_with('/tmp/test-venv', ignore_errors=True)
        mock_run.assert_called_once()
        self.assertEqual(result, '/tmp/test-venv')


class TestPipInstall(unittest.TestCase):
    @patch('run_wheel_check.subprocess.run')
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='Installed', stderr='')
        result = run_wheel_check.pip_install('/tmp/venv', 'click==8.0')
        self.assertTrue(result)

    @patch('run_wheel_check.subprocess.run')
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='ERROR')
        result = run_wheel_check.pip_install('/tmp/venv', 'bad-pkg')
        self.assertFalse(result)


class TestPipListJson(unittest.TestCase):
    @patch('run_wheel_check.subprocess.run')
    def test_returns_list(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"name":"click","version":"8.1.0"}]')
        result = run_wheel_check.pip_list_json('/tmp/venv')
        self.assertEqual(result, [{'name': 'click', 'version': '8.1.0'}])

    @patch('run_wheel_check.subprocess.run')
    def test_failure_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='err')
        result = run_wheel_check.pip_list_json('/tmp/venv')
        self.assertEqual(result, [])


class TestWriteResult(unittest.TestCase):
    def test_writes_json(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name
        try:
            run_wheel_check.write_result(path, {'status': 'PASS', 'wheel': 'foo.whl'})
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data['status'], 'PASS')
        finally:
            os.unlink(path)


class TestResultPath(unittest.TestCase):
    def test_basic(self):
        result = run_wheel_check.result_path('/tmp/results', 'click-8.0-py3-none-any.whl')
        self.assertEqual(result, '/tmp/results/click-8.0-py3-none-any.whl.json')


class TestRunPhase1(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.results_dir = os.path.join(self.tmpdir, 'results')
        os.makedirs(self.results_dir)
        self.script_dir = str(Path(__file__).resolve().parent)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_all_cached_skip(self):
        whl = make_wheel(self.tmpdir, 'click', '8.1.0')
        built_set = set()
        result = run_wheel_check.run_phase1(
            [whl], built_set, self.results_dir, 'python3.12', self.tmpdir, self.script_dir)
        self.assertFalse(result)
        rpath = run_wheel_check.result_path(self.results_dir, whl)
        with open(rpath) as f:
            data = json.load(f)
        self.assertEqual(data['status'], 'SKIP')

    def test_data_only_skip(self):
        whl = make_data_wheel(self.tmpdir, 'mydata', '1.0')
        result = run_wheel_check.run_phase1(
            [whl], None, self.results_dir, 'python3.12', self.tmpdir, self.script_dir)
        self.assertFalse(result)
        rpath = run_wheel_check.result_path(self.results_dir, whl)
        with open(rpath) as f:
            data = json.load(f)
        self.assertEqual(data['status'], 'SKIP')
        self.assertIn('data-only', data['reason'])

    @patch('run_wheel_check.verify_in_venv', return_value=0)
    @patch('run_wheel_check.pip_install', return_value=True)
    @patch('run_wheel_check.create_venv', return_value='/tmp/test-venv')
    def test_importable_pass(self, mock_venv, mock_pip, mock_verify):
        whl = make_wheel(self.tmpdir, 'click', '8.1.0')
        rpath = run_wheel_check.result_path(self.results_dir, whl)
        run_wheel_check.write_result(rpath, {
            'wheel': whl, 'status': 'PASS', 'reason': '', 'imports_tested': []})

        def write_pass_result(venv, sd, wheel, rf):
            run_wheel_check.write_result(rf, {
                'wheel': wheel, 'status': 'PASS', 'reason': '', 'imports_tested': []})
            return 0
        mock_verify.side_effect = write_pass_result

        result = run_wheel_check.run_phase1(
            [whl], None, self.results_dir, 'python3.12', self.tmpdir, self.script_dir)
        self.assertFalse(result)

    @patch('run_wheel_check.verify_in_venv', return_value=1)
    @patch('run_wheel_check.pip_install', return_value=True)
    @patch('run_wheel_check.create_venv', return_value='/tmp/test-venv')
    def test_import_failure(self, mock_venv, mock_pip, mock_verify):
        whl = make_wheel(self.tmpdir, 'badpkg', '1.0')
        rpath = run_wheel_check.result_path(self.results_dir, whl)

        def write_fail_result(venv, sd, wheel, rf):
            run_wheel_check.write_result(rf, {
                'wheel': wheel, 'status': 'FAIL', 'reason': 'import failures',
                'imports_tested': [{'name': 'badpkg', 'success': False,
                                    'message': 'ImportError: bad'}]})
            return 1
        mock_verify.side_effect = write_fail_result

        result = run_wheel_check.run_phase1(
            [whl], None, self.results_dir, 'python3.12', self.tmpdir, self.script_dir)
        self.assertTrue(result)

    @patch('run_wheel_check.create_venv', return_value='/tmp/test-venv')
    @patch('run_wheel_check.pip_install', return_value=False)
    def test_pip_install_failure(self, mock_pip, mock_venv):
        whl = make_wheel(self.tmpdir, 'broken', '1.0')
        result = run_wheel_check.run_phase1(
            [whl], None, self.results_dir, 'python3.12', self.tmpdir, self.script_dir)
        self.assertTrue(result)
        rpath = run_wheel_check.result_path(self.results_dir, whl)
        with open(rpath) as f:
            data = json.load(f)
        self.assertEqual(data['status'], 'FAIL')
        self.assertIn('pip install', data['reason'])

    @patch('run_wheel_check.verify_in_venv', return_value=2)
    @patch('run_wheel_check.pip_install', return_value=True)
    @patch('run_wheel_check.create_venv', return_value='/tmp/test-venv')
    def test_script_error(self, mock_venv, mock_pip, mock_verify):
        whl = make_wheel(self.tmpdir, 'crash', '1.0')
        result = run_wheel_check.run_phase1(
            [whl], None, self.results_dir, 'python3.12', self.tmpdir, self.script_dir)
        self.assertTrue(result)

    def test_built_set_filters(self):
        whl1 = make_wheel(self.tmpdir, 'click', '8.1.0')
        whl2 = make_wheel(self.tmpdir, 'flask', '3.0.0')
        built_set = {whl1}

        with patch('run_wheel_check.create_venv') as mock_venv, \
             patch('run_wheel_check.pip_install', return_value=True), \
             patch('run_wheel_check.verify_in_venv') as mock_verify:
            mock_venv.return_value = '/tmp/test-venv'

            def write_pass(venv, sd, wheel, rf):
                run_wheel_check.write_result(rf, {
                    'wheel': wheel, 'status': 'PASS', 'reason': '', 'imports_tested': []})
                return 0
            mock_verify.side_effect = write_pass

            result = run_wheel_check.run_phase1(
                [whl1, whl2], built_set, self.results_dir, 'python3.12',
                self.tmpdir, self.script_dir)

        self.assertFalse(result)
        rpath2 = run_wheel_check.result_path(self.results_dir, whl2)
        with open(rpath2) as f:
            data = json.load(f)
        self.assertEqual(data['status'], 'SKIP')

    def test_mixed_results(self):
        whl_data = make_data_wheel(self.tmpdir, 'mydata', '1.0')
        whl_good = make_wheel(self.tmpdir, 'click', '8.1.0')

        with patch('run_wheel_check.create_venv', return_value='/tmp/test-venv'), \
             patch('run_wheel_check.pip_install', return_value=True), \
             patch('run_wheel_check.verify_in_venv') as mock_verify:

            def write_pass(venv, sd, wheel, rf):
                run_wheel_check.write_result(rf, {
                    'wheel': wheel, 'status': 'PASS', 'reason': '', 'imports_tested': []})
                return 0
            mock_verify.side_effect = write_pass

            result = run_wheel_check.run_phase1(
                [whl_data, whl_good], None, self.results_dir, 'python3.12',
                self.tmpdir, self.script_dir)

        self.assertFalse(result)


class TestPrintSummary(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_counts(self):
        run_wheel_check.write_result(
            os.path.join(self.tmpdir, 'a.json'),
            {'wheel': 'a.whl', 'status': 'PASS', 'reason': '', 'imports_tested': []})
        run_wheel_check.write_result(
            os.path.join(self.tmpdir, 'b.json'),
            {'wheel': 'b.whl', 'status': 'FAIL', 'reason': 'import failures',
             'imports_tested': [{'name': 'b', 'success': False, 'message': 'err'}]})
        run_wheel_check.write_result(
            os.path.join(self.tmpdir, 'c.json'),
            {'wheel': 'c.whl', 'status': 'SKIP', 'reason': 'cached', 'imports_tested': []})

        p, f, s = run_wheel_check.print_summary(self.tmpdir)
        self.assertEqual(p, 1)
        self.assertEqual(f, 1)
        self.assertEqual(s, 1)

    def test_empty_dir(self):
        p, f, s = run_wheel_check.print_summary(self.tmpdir)
        self.assertEqual(p, 0)
        self.assertEqual(f, 0)
        self.assertEqual(s, 0)


class TestRunPhase2(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.files_dir = os.path.join(self.tmpdir, 'files')
        self.results_dir = os.path.join(self.tmpdir, 'results')
        self.combined_dir = os.path.join(self.tmpdir, 'combined')
        os.makedirs(self.files_dir)
        os.makedirs(self.results_dir)
        self.script_dir = str(Path(__file__).resolve().parent)

        self.whl_primary = make_wheel(self.files_dir, 'mypkg', '1.0')
        self.whl_dep = make_wheel(self.files_dir, 'mydep', '2.0')
        make_sdist(self.files_dir, 'mypkg', '1.0')

        self.summary = make_summary(self.files_dir, 'mypkg__1.0', [
            {'name': 'mypkg', 'version': '1.0'},
            {'name': 'mydep', 'version': '2.0'},
        ])

        run_wheel_check.WHEEL_INDEX_PATH = os.path.join(self.tmpdir, 'wheel-index.json')
        run_wheel_check.IMPORT_MAP_PATH = os.path.join(self.tmpdir, 'import-map.json')

        from wheel_helpers import normalize
        wheel_index = {}
        for f in os.listdir(self.files_dir):
            if f.endswith('.whl'):
                parts = f.split('-')
                key = normalize(parts[0]) + '-' + parts[1]
                wheel_index[key] = f
        with open(run_wheel_check.WHEEL_INDEX_PATH, 'w') as f:
            json.dump(wheel_index, f)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        run_wheel_check.WHEEL_INDEX_PATH = '/tmp/wheel-index.json'
        run_wheel_check.IMPORT_MAP_PATH = '/tmp/import-to-wheel.json'

    @patch('run_wheel_check.pip_list_json')
    @patch('run_wheel_check.verify_in_venv')
    @patch('run_wheel_check.pip_install', return_value=True)
    @patch('run_wheel_check.create_venv', return_value='/tmp/test-venv-group')
    def test_group_pass(self, mock_venv, mock_pip, mock_verify, mock_pip_list):
        mock_pip_list.return_value = [
            {'name': 'mypkg', 'version': '1.0'},
            {'name': 'mydep', 'version': '2.0'},
        ]

        def verify_pass(venv, sd, wheel, rf):
            run_wheel_check.write_result(rf, {
                'wheel': wheel, 'status': 'PASS', 'reason': '', 'imports_tested': []})
            return 0
        mock_verify.side_effect = verify_pass

        run_wheel_check.write_result(
            os.path.join(self.results_dir, f'{self.whl_primary}.json'),
            {'wheel': self.whl_primary, 'status': 'FAIL', 'reason': 'import failures',
             'imports_tested': [{'name': 'mypkg', 'success': False, 'message': 'err'}]})

        summary_files = [os.path.join(self.files_dir, self.summary)]
        run_wheel_check.run_phase2(
            summary_files, None, self.results_dir, self.combined_dir,
            'python3.12', self.files_dir, self.script_dir)

        rpath = run_wheel_check.result_path(self.combined_dir, self.whl_primary)
        self.assertTrue(os.path.exists(rpath))
        with open(rpath) as f:
            data = json.load(f)
        self.assertEqual(data['status'], 'PASS')

    def test_no_summary_files(self):
        run_wheel_check.run_phase2(
            [], None, self.results_dir, self.combined_dir,
            'python3.12', self.files_dir, self.script_dir)
        self.assertFalse(os.path.exists(self.combined_dir))

    @patch('run_wheel_check.pip_list_json')
    @patch('run_wheel_check.verify_in_venv')
    @patch('run_wheel_check.pip_install', return_value=True)
    @patch('run_wheel_check.create_venv', return_value='/tmp/test-venv-group')
    def test_skips_non_built(self, mock_venv, mock_pip, mock_verify, mock_pip_list):
        mock_pip_list.return_value = [
            {'name': 'mypkg', 'version': '1.0'},
        ]
        built_set = {self.whl_primary}

        def verify_pass(venv, sd, wheel, rf):
            run_wheel_check.write_result(rf, {
                'wheel': wheel, 'status': 'PASS', 'reason': '', 'imports_tested': []})
            return 0
        mock_verify.side_effect = verify_pass

        run_wheel_check.write_result(
            os.path.join(self.results_dir, f'{self.whl_primary}.json'),
            {'wheel': self.whl_primary, 'status': 'FAIL', 'reason': 'import failures',
             'imports_tested': []})

        summary_files = [os.path.join(self.files_dir, self.summary)]
        run_wheel_check.run_phase2(
            summary_files, built_set, self.results_dir, self.combined_dir,
            'python3.12', self.files_dir, self.script_dir)

        mock_verify.assert_called()

    @patch('run_wheel_check.pip_list_json')
    @patch('run_wheel_check.verify_in_venv')
    @patch('run_wheel_check.pip_install', return_value=True)
    @patch('run_wheel_check.create_venv', return_value='/tmp/test-venv-group')
    def test_skip_group_no_built_wheels(self, mock_venv, mock_pip, mock_verify, mock_pip_list):
        built_set = set()

        summary_files = [os.path.join(self.files_dir, self.summary)]
        run_wheel_check.run_phase2(
            summary_files, built_set, self.results_dir, self.combined_dir,
            'python3.12', self.files_dir, self.script_dir)

        mock_verify.assert_not_called()


class TestUndeclaredDepResolution(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.files_dir = os.path.join(self.tmpdir, 'files')
        self.results_dir = os.path.join(self.tmpdir, 'results')
        self.combined_dir = os.path.join(self.tmpdir, 'combined')
        os.makedirs(self.files_dir)
        os.makedirs(self.results_dir)
        self.script_dir = str(Path(__file__).resolve().parent)

        self.whl_primary = make_wheel(self.files_dir, 'mypkg', '1.0')
        self.whl_dep = make_wheel(self.files_dir, 'undeclared', '1.0')
        make_sdist(self.files_dir, 'mypkg', '1.0')

        make_summary(self.files_dir, 'mypkg__1.0', [
            {'name': 'mypkg', 'version': '1.0'},
        ])

        run_wheel_check.WHEEL_INDEX_PATH = os.path.join(self.tmpdir, 'wheel-index.json')
        run_wheel_check.IMPORT_MAP_PATH = os.path.join(self.tmpdir, 'import-map.json')

        from wheel_helpers import normalize
        wheel_index = {}
        for f in os.listdir(self.files_dir):
            if f.endswith('.whl'):
                parts = f.split('-')
                key = normalize(parts[0]) + '-' + parts[1]
                wheel_index[key] = f
        with open(run_wheel_check.WHEEL_INDEX_PATH, 'w') as f:
            json.dump(wheel_index, f)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        run_wheel_check.WHEEL_INDEX_PATH = '/tmp/wheel-index.json'
        run_wheel_check.IMPORT_MAP_PATH = '/tmp/import-to-wheel.json'

    @patch('run_wheel_check.pip_list_json')
    @patch('run_wheel_check.verify_in_venv')
    @patch('run_wheel_check.pip_install', return_value=True)
    @patch('run_wheel_check.create_venv', return_value='/tmp/test-venv-group')
    def test_resolves_undeclared_dep(self, mock_venv, mock_pip, mock_verify, mock_pip_list):
        mock_pip_list.return_value = [
            {'name': 'mypkg', 'version': '1.0'},
        ]

        call_count = [0]

        def verify_side_effect(venv, sd, wheel, rf):
            call_count[0] += 1
            if call_count[0] == 1:
                run_wheel_check.write_result(rf, {
                    'wheel': wheel, 'status': 'FAIL', 'reason': 'import failures',
                    'imports_tested': [{'name': 'mypkg', 'success': False,
                                        'message': "ImportError: No module named 'undeclared'"}]})
                return 1
            else:
                run_wheel_check.write_result(rf, {
                    'wheel': wheel, 'status': 'PASS', 'reason': '', 'imports_tested': []})
                return 0
        mock_verify.side_effect = verify_side_effect

        run_wheel_check.write_result(
            os.path.join(self.results_dir, f'{self.whl_primary}.json'),
            {'wheel': self.whl_primary, 'status': 'FAIL', 'reason': 'import failures',
             'imports_tested': [{'name': 'mypkg', 'success': False,
                                 'message': "ImportError: No module named 'undeclared'"}]})

        summary_files = sorted(
            os.path.join(self.files_dir, f) for f in os.listdir(self.files_dir)
            if f.startswith('build-sequence-summary-'))

        run_wheel_check.run_phase2(
            summary_files, None, self.results_dir, self.combined_dir,
            'python3.12', self.files_dir, self.script_dir)

        rpath = run_wheel_check.result_path(self.combined_dir, self.whl_primary)
        with open(rpath) as f:
            data = json.load(f)
        self.assertEqual(data['status'], 'PASS')
        self.assertIn('undeclared_dep', data)


class TestMainFunction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_results = run_wheel_check.RESULTS_DIR
        self.orig_combined = run_wheel_check.COMBINED_RESULTS_DIR
        self.orig_wheel_index = run_wheel_check.WHEEL_INDEX_PATH
        self.orig_built_wheels = run_wheel_check.BUILT_WHEELS_PATH
        self.orig_import_map = run_wheel_check.IMPORT_MAP_PATH

        run_wheel_check.RESULTS_DIR = os.path.join(self.tmpdir, 'results')
        run_wheel_check.COMBINED_RESULTS_DIR = os.path.join(self.tmpdir, 'combined')
        run_wheel_check.WHEEL_INDEX_PATH = os.path.join(self.tmpdir, 'wheel-index.json')
        run_wheel_check.BUILT_WHEELS_PATH = os.path.join(self.tmpdir, 'built-wheels.json')
        run_wheel_check.IMPORT_MAP_PATH = os.path.join(self.tmpdir, 'import-map.json')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        run_wheel_check.RESULTS_DIR = self.orig_results
        run_wheel_check.COMBINED_RESULTS_DIR = self.orig_combined
        run_wheel_check.WHEEL_INDEX_PATH = self.orig_wheel_index
        run_wheel_check.BUILT_WHEELS_PATH = self.orig_built_wheels
        run_wheel_check.IMPORT_MAP_PATH = self.orig_import_map

    def test_no_wheels(self):
        files_dir = os.path.join(self.tmpdir, 'empty')
        os.makedirs(files_dir)
        rc = run_wheel_check.main(['--files-dir', files_dir])
        self.assertEqual(rc, 1)

    def test_all_cached_early_exit(self):
        files_dir = os.path.join(self.tmpdir, 'files')
        os.makedirs(files_dir)
        make_wheel(files_dir, 'click', '8.1.0')
        rc = run_wheel_check.main(['--files-dir', files_dir])
        self.assertEqual(rc, 0)

    def test_all_skip_passes(self):
        files_dir = os.path.join(self.tmpdir, 'files')
        os.makedirs(files_dir)
        make_data_wheel(files_dir, 'mydata', '1.0')
        make_sdist(files_dir, 'mydata', '1.0')
        rc = run_wheel_check.main(['--files-dir', files_dir])
        self.assertEqual(rc, 0)

    @patch('run_wheel_check.verify_in_venv', return_value=0)
    @patch('run_wheel_check.pip_install', return_value=True)
    @patch('run_wheel_check.create_venv', return_value='/tmp/test-venv')
    def test_pass_with_sdist(self, mock_venv, mock_pip, mock_verify):
        files_dir = os.path.join(self.tmpdir, 'files')
        os.makedirs(files_dir)
        whl = make_wheel(files_dir, 'click', '8.1.0')
        make_sdist(files_dir, 'click', '8.1.0')

        def write_pass(venv, sd, wheel, rf):
            run_wheel_check.write_result(rf, {
                'wheel': wheel, 'status': 'PASS', 'reason': '', 'imports_tested': []})
            return 0
        mock_verify.side_effect = write_pass

        rc = run_wheel_check.main(['--files-dir', files_dir])
        self.assertEqual(rc, 0)

    @patch('run_wheel_check.verify_in_venv', return_value=1)
    @patch('run_wheel_check.pip_install', return_value=True)
    @patch('run_wheel_check.create_venv', return_value='/tmp/test-venv')
    def test_fail_no_summary(self, mock_venv, mock_pip, mock_verify):
        files_dir = os.path.join(self.tmpdir, 'files')
        os.makedirs(files_dir)
        whl = make_wheel(files_dir, 'badpkg', '1.0')
        make_sdist(files_dir, 'badpkg', '1.0')

        def write_fail(venv, sd, wheel, rf):
            run_wheel_check.write_result(rf, {
                'wheel': wheel, 'status': 'FAIL', 'reason': 'import failures',
                'imports_tested': [{'name': 'badpkg', 'success': False, 'message': 'err'}]})
            return 1
        mock_verify.side_effect = write_fail

        rc = run_wheel_check.main(['--files-dir', files_dir])
        self.assertEqual(rc, 1)


class TestPhase2CarryForward(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.results_dir = os.path.join(self.tmpdir, 'results')
        self.combined_dir = os.path.join(self.tmpdir, 'combined')
        self.files_dir = os.path.join(self.tmpdir, 'files')
        os.makedirs(self.results_dir)
        os.makedirs(self.files_dir)
        self.script_dir = str(Path(__file__).resolve().parent)

        run_wheel_check.WHEEL_INDEX_PATH = os.path.join(self.tmpdir, 'wheel-index.json')
        run_wheel_check.IMPORT_MAP_PATH = os.path.join(self.tmpdir, 'import-map.json')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        run_wheel_check.WHEEL_INDEX_PATH = '/tmp/wheel-index.json'
        run_wheel_check.IMPORT_MAP_PATH = '/tmp/import-to-wheel.json'

    @patch('run_wheel_check.pip_list_json', return_value=[])
    @patch('run_wheel_check.pip_install', return_value=True)
    @patch('run_wheel_check.create_venv', return_value='/tmp/test-venv-group')
    def test_phase1_results_copied(self, mock_venv, mock_pip, mock_pip_list):
        whl = make_wheel(self.files_dir, 'cached', '1.0')
        make_summary(self.files_dir, 'mypkg__1.0', [{'name': 'mypkg', 'version': '1.0'}])

        run_wheel_check.write_result(
            os.path.join(self.results_dir, f'{whl}.json'),
            {'wheel': whl, 'status': 'SKIP', 'reason': 'cached', 'imports_tested': []})

        from wheel_helpers import normalize
        wheel_index = {}
        for f in os.listdir(self.files_dir):
            if f.endswith('.whl'):
                parts = f.split('-')
                key = normalize(parts[0]) + '-' + parts[1]
                wheel_index[key] = f
        with open(run_wheel_check.WHEEL_INDEX_PATH, 'w') as f:
            json.dump(wheel_index, f)

        summary_files = sorted(
            os.path.join(self.files_dir, f) for f in os.listdir(self.files_dir)
            if f.startswith('build-sequence-summary-'))
        run_wheel_check.run_phase2(
            summary_files, None, self.results_dir, self.combined_dir,
            'python3.12', self.files_dir, self.script_dir)

        combined_file = os.path.join(self.combined_dir, f'{whl}.json')
        self.assertTrue(os.path.exists(combined_file))
        with open(combined_file) as f:
            data = json.load(f)
        self.assertEqual(data['status'], 'SKIP')


if __name__ == '__main__':
    unittest.main()
