#!/usr/bin/env python3
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wheel_helpers import (
    annotate_dep,
    extract_missing_module,
    find_missing_wheel,
    format_summary_row,
    group_has_built,
    lookup_primary,
    lookup_wheel,
    match_installed_wheels,
    normalize,
    print_failed_imports,
    read_built_status,
    read_built_wheels,
    read_field,
    read_result_status,
    write_failure_result,
    write_skip_result,
)


class TestNormalize(unittest.TestCase):
    def test_hyphen(self):
        self.assertEqual(normalize("my-package"), "my_package")

    def test_dot(self):
        self.assertEqual(normalize("my.package"), "my_package")

    def test_underscore(self):
        self.assertEqual(normalize("my_package"), "my_package")

    def test_mixed(self):
        self.assertEqual(normalize("My-Package.Name"), "my_package_name")

    def test_consecutive_separators(self):
        self.assertEqual(normalize("foo--bar"), "foo_bar")

    def test_case(self):
        self.assertEqual(normalize("MyPackage"), "mypackage")

    def test_pep503_equivalence(self):
        self.assertEqual(normalize("Foo-Bar"), normalize("foo_bar"))
        self.assertEqual(normalize("foo.bar"), normalize("foo-bar"))


class TestReadResultStatus(unittest.TestCase):
    def test_pass(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'status': 'PASS'}, f)
            f.flush()
        try:
            self.assertEqual(read_result_status(f.name), 'PASS')
        finally:
            os.unlink(f.name)

    def test_fail(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'status': 'FAIL'}, f)
            f.flush()
        try:
            self.assertEqual(read_result_status(f.name), 'FAIL')
        finally:
            os.unlink(f.name)

    def test_missing_status(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()
        try:
            self.assertEqual(read_result_status(f.name), 'FAIL')
        finally:
            os.unlink(f.name)

    def test_missing_file(self):
        self.assertEqual(read_result_status('/tmp/nonexistent-file-12345.json'), 'FAIL')

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not json')
            f.flush()
        try:
            self.assertEqual(read_result_status(f.name), 'FAIL')
        finally:
            os.unlink(f.name)


class TestReadField(unittest.TestCase):
    def test_existing_field(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'wheel': 'foo-1.0.whl', 'status': 'PASS'}, f)
            f.flush()
        try:
            self.assertEqual(read_field(f.name, 'wheel'), 'foo-1.0.whl')
        finally:
            os.unlink(f.name)

    def test_missing_field(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'status': 'PASS'}, f)
            f.flush()
        try:
            self.assertEqual(read_field(f.name, 'undeclared_dep'), '')
        finally:
            os.unlink(f.name)

    def test_missing_file(self):
        self.assertEqual(read_field('/tmp/nonexistent-file-12345.json', 'status'), '')


class TestPrintFailedImports(unittest.TestCase):
    def test_prints_failures(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'imports_tested': [
                    {'name': 'foo', 'success': True, 'message': 'OK'},
                    {'name': 'bar', 'success': False, 'message': 'ImportError: No module named bar'},
                ]
            }, f)
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                print_failed_imports(f.name, prefix='  -> ')
                output = mock_out.getvalue()
            self.assertIn('bar', output)
            self.assertIn('  -> ', output)
            self.assertNotIn('foo', output)
        finally:
            os.unlink(f.name)

    def test_no_failures(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'imports_tested': [{'name': 'foo', 'success': True}]}, f)
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                print_failed_imports(f.name)
                self.assertEqual(mock_out.getvalue(), '')
        finally:
            os.unlink(f.name)

    def test_corrupt_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not json')
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                print_failed_imports(f.name)
                self.assertEqual(mock_out.getvalue(), '')
        finally:
            os.unlink(f.name)


class TestFormatSummaryRow(unittest.TestCase):
    def test_pass(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'wheel': 'foo-1.0.whl', 'status': 'PASS', 'reason': ''}, f)
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                format_summary_row(f.name)
                self.assertIn('PASS', mock_out.getvalue())
                self.assertIn('foo-1.0.whl', mock_out.getvalue())
        finally:
            os.unlink(f.name)

    def test_with_undeclared_dep(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'wheel': 'foo-1.0.whl', 'status': 'PASS', 'reason': '', 'undeclared_dep': 'bar'}, f)
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                format_summary_row(f.name)
                self.assertIn('undeclared dep: bar', mock_out.getvalue())
        finally:
            os.unlink(f.name)

    def test_invalid_file(self):
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            format_summary_row('/tmp/nonexistent-12345.json')
            output = mock_out.getvalue()
            self.assertIn('FAIL', output)
            self.assertIn('nonexistent-12345', output)
            self.assertIn('verify_import failed without output', output)


class TestAnnotateDep(unittest.TestCase):
    def test_adds_dep(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'status': 'PASS'}, f)
            f.flush()
        try:
            annotate_dep(f.name, 'click')
            with open(f.name) as rf:
                d = json.load(rf)
            self.assertEqual(d['undeclared_dep'], 'click')
        finally:
            os.unlink(f.name)


class TestLookupWheel(unittest.TestCase):
    def test_found(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'click-8.1.0': 'click-8.1.0-py3-none-any.whl'}, f)
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                lookup_wheel(f.name, 'click', '8.1.0')
                self.assertEqual(mock_out.getvalue().strip(), 'click-8.1.0-py3-none-any.whl')
        finally:
            os.unlink(f.name)

    def test_not_found(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                lookup_wheel(f.name, 'nonexistent', '1.0')
                self.assertEqual(mock_out.getvalue().strip(), '')
        finally:
            os.unlink(f.name)


class TestExtractMissingModule(unittest.TestCase):
    def test_extracts_module(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'imports_tested': [
                    {'name': 'foo', 'success': False, 'message': "ImportError: No module named 'click'"},
                ]
            }, f)
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                extract_missing_module(f.name)
                self.assertEqual(mock_out.getvalue().strip(), 'click')
        finally:
            os.unlink(f.name)

    def test_dotted_module(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'imports_tested': [
                    {'name': 'foo', 'success': False, 'message': "ImportError: No module named 'pkg.sub'"},
                ]
            }, f)
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                extract_missing_module(f.name)
                self.assertEqual(mock_out.getvalue().strip(), 'pkg')
        finally:
            os.unlink(f.name)

    def test_no_missing(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'imports_tested': [{'name': 'foo', 'success': True}]}, f)
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                extract_missing_module(f.name)
                self.assertEqual(mock_out.getvalue().strip(), '')
        finally:
            os.unlink(f.name)

    def test_corrupt_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not json')
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                extract_missing_module(f.name)
                self.assertEqual(mock_out.getvalue().strip(), '')
        finally:
            os.unlink(f.name)


class TestWriteFailureResult(unittest.TestCase):
    def test_output(self):
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            write_failure_result('foo-1.0.whl', 'pip install failed')
            d = json.loads(mock_out.getvalue())
            self.assertEqual(d['wheel'], 'foo-1.0.whl')
            self.assertEqual(d['status'], 'FAIL')
            self.assertEqual(d['reason'], 'pip install failed')


class TestLookupPrimary(unittest.TestCase):
    def _make_files(self, summary_entries, wheel_index):
        sf = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(summary_entries, sf)
        sf.flush()
        sf.close()
        wf = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(wheel_index, wf)
        wf.flush()
        wf.close()
        self.addCleanup(lambda: os.unlink(sf.name) if os.path.exists(sf.name) else None)
        self.addCleanup(lambda: os.unlink(wf.name) if os.path.exists(wf.name) else None)
        return sf.name, wf.name

    def test_normal_label(self):
        summary_path, index_path = self._make_files(
            [{'name': 'click', 'version': '8.1.0'}],
            {'click-8.1.0': 'click-8.1.0-0-py3-none-any.whl'},
        )
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            lookup_primary('click__8.1.0', summary_path, index_path)
            lines = mock_out.getvalue().strip().split('\n')
            self.assertEqual(lines[0], 'click')
            self.assertEqual(lines[1], '8.1.0')
            self.assertEqual(lines[2], 'click-8.1.0-0-py3-none-any.whl')

    def test_git_sourced_label(self):
        summary_path, index_path = self._make_files(
            [
                {'name': 'presidio-analyzer', 'version': '2.2.359'},
                {'name': 'spacy', 'version': '3.8.13'},
            ],
            {'presidio_analyzer-2.2.359': 'presidio_analyzer-2.2.359-0-py3-none-any.whl'},
        )
        label = 'presidio_analyzer___git_https___github.com_microsoft_presidio.git_2.2.359'
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            lookup_primary(label, summary_path, index_path)
            lines = mock_out.getvalue().strip().split('\n')
            self.assertEqual(lines[0], 'presidio-analyzer')
            self.assertEqual(lines[1], '2.2.359')
            self.assertEqual(lines[2], 'presidio_analyzer-2.2.359-0-py3-none-any.whl')

    def test_hyphenated_name(self):
        summary_path, index_path = self._make_files(
            [{'name': 'pydantic-ai-slim', 'version': '2.10.0'}],
            {'pydantic_ai_slim-2.10.0': 'pydantic_ai_slim-2.10.0-0-py3-none-any.whl'},
        )
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            lookup_primary('pydantic-ai-slim__2.10.0', summary_path, index_path)
            lines = mock_out.getvalue().strip().split('\n')
            self.assertEqual(lines[0], 'pydantic-ai-slim')
            self.assertEqual(lines[1], '2.10.0')

    def test_no_match(self):
        summary_path, index_path = self._make_files(
            [{'name': 'other-pkg', 'version': '1.0'}],
            {},
        )
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            lookup_primary('click__8.1.0', summary_path, index_path)
            self.assertEqual(mock_out.getvalue().strip(), '')

    def test_empty_summary(self):
        summary_path, index_path = self._make_files([], {})
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            lookup_primary('click__8.1.0', summary_path, index_path)
            self.assertEqual(mock_out.getvalue().strip(), '')

    def test_no_prefix_collision(self):
        summary_path, index_path = self._make_files(
            [
                {'name': 'foo', 'version': '1.0'},
                {'name': 'foobar', 'version': '2.0'},
            ],
            {'foobar-2.0': 'foobar-2.0-0-py3-none-any.whl'},
        )
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            lookup_primary('foobar__2.0', summary_path, index_path)
            lines = mock_out.getvalue().strip().split('\n')
            self.assertEqual(lines[0], 'foobar')
            self.assertEqual(lines[1], '2.0')


class TestFindMissingWheel(unittest.TestCase):
    def test_from_import_map(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'click': ['click-8.1.0-py3-none-any.whl']}, f)
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                find_missing_wheel('click', '', f.name)
                self.assertEqual(mock_out.getvalue().strip(), 'click-8.1.0-py3-none-any.whl')
        finally:
            os.unlink(f.name)

    def test_skips_tried(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'click': ['click-8.1.0-py3-none-any.whl']}, f)
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                find_missing_wheel('click', 'click-8.1.0-py3-none-any.whl', f.name)
                self.assertEqual(mock_out.getvalue().strip(), '')
        finally:
            os.unlink(f.name)

    def test_corrupt_import_map(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not json')
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                find_missing_wheel('click', '', f.name)
                self.assertEqual(mock_out.getvalue().strip(), '')
        finally:
            os.unlink(f.name)


class TestCLIDispatch(unittest.TestCase):
    def test_read_status_cli(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'status': 'PASS'}, f)
            f.flush()
        try:
            script = str(Path(__file__).resolve().parent / 'wheel_helpers.py')
            result = subprocess.run(
                [sys.executable, script, 'read-status', f.name],
                capture_output=True, text=True,
            )
            self.assertEqual(result.stdout.strip(), 'PASS')
        finally:
            os.unlink(f.name)

    def test_write_failure_cli(self):
        script = str(Path(__file__).resolve().parent / 'wheel_helpers.py')
        result = subprocess.run(
            [sys.executable, script, 'write-failure', 'test.whl', 'broken'],
            capture_output=True, text=True,
        )
        d = json.loads(result.stdout)
        self.assertEqual(d['status'], 'FAIL')
        self.assertEqual(d['wheel'], 'test.whl')

    def test_write_skip_cli(self):
        script = str(Path(__file__).resolve().parent / 'wheel_helpers.py')
        result = subprocess.run(
            [sys.executable, script, 'write-skip', 'cached.whl', 'no sdist'],
            capture_output=True, text=True,
        )
        d = json.loads(result.stdout)
        self.assertEqual(d['status'], 'SKIP')
        self.assertEqual(d['wheel'], 'cached.whl')
        self.assertEqual(d['reason'], 'no sdist')


class TestWriteSkipResult(unittest.TestCase):
    def test_output(self):
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            write_skip_result('cached.whl', 'no matching sdist')
            d = json.loads(mock_out.getvalue())
            self.assertEqual(d['status'], 'SKIP')
            self.assertEqual(d['wheel'], 'cached.whl')
            self.assertEqual(d['reason'], 'no matching sdist')
            self.assertEqual(d['imports_tested'], [])


class TestReadBuiltStatus(unittest.TestCase):
    def test_reads_status(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'status': 'has_built', 'wheels': ['a.whl']}, f)
            f.flush()
        try:
            self.assertEqual(read_built_status(f.name), 'has_built')
        finally:
            os.unlink(f.name)

    def test_missing_file(self):
        self.assertEqual(read_built_status('/tmp/nonexistent-built-12345.json'), 'no_sdists')


class TestReadBuiltWheels(unittest.TestCase):
    def test_reads_wheels(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'status': 'has_built', 'wheels': ['a.whl', 'b.whl']}, f)
            f.flush()
        try:
            result = read_built_wheels(f.name)
            self.assertIn('a.whl', result)
            self.assertIn('b.whl', result)
        finally:
            os.unlink(f.name)

    def test_missing_file(self):
        self.assertEqual(read_built_wheels('/tmp/nonexistent-built-12345.json'), '')


class TestGroupHasBuilt(unittest.TestCase):
    def _setup(self, summary_entries, wheel_index, built_csv):
        sf = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(summary_entries, sf)
        sf.flush()
        sf.close()
        wf = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(wheel_index, wf)
        wf.flush()
        wf.close()
        self.addCleanup(lambda: os.unlink(sf.name) if os.path.exists(sf.name) else None)
        self.addCleanup(lambda: os.unlink(wf.name) if os.path.exists(wf.name) else None)
        return sf.name, wf.name

    def test_has_built_wheel(self):
        summary_path, index_path = self._setup(
            [{'name': 'click', 'version': '8.1.0'}],
            {'click-8.1.0': 'click-8.1.0-py3-none-any.whl'},
            'click-8.1.0-py3-none-any.whl',
        )
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            group_has_built(summary_path, 'click-8.1.0-py3-none-any.whl',
                            wheel_index_path=index_path)
            self.assertEqual(mock_out.getvalue().strip(), 'yes')

    def test_no_built_wheel(self):
        summary_path, index_path = self._setup(
            [{'name': 'click', 'version': '8.1.0'}],
            {'click-8.1.0': 'click-8.1.0-py3-none-any.whl'},
            'other.whl',
        )
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            group_has_built(summary_path, 'other.whl',
                            wheel_index_path=index_path)
            self.assertEqual(mock_out.getvalue().strip(), 'no')

    def test_empty_summary(self):
        summary_path, index_path = self._setup([], {}, '')
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            group_has_built(summary_path, 'any.whl',
                            wheel_index_path=index_path)
            self.assertEqual(mock_out.getvalue().strip(), 'no')

    def test_corrupt_json_warns(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not json')
            f.flush()
        try:
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out, \
                 patch('sys.stderr', new_callable=io.StringIO) as mock_err:
                group_has_built(f.name, 'any.whl')
                self.assertEqual(mock_out.getvalue().strip(), 'no')
                self.assertIn('WARNING', mock_err.getvalue())
        finally:
            os.unlink(f.name)

    def test_empty_csv_no_false_positive(self):
        summary_path, index_path = self._setup(
            [{'name': 'click', 'version': '8.1.0'}],
            {'click-8.1.0': 'click-8.1.0-py3-none-any.whl'},
            '',
        )
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            group_has_built(summary_path, '',
                            wheel_index_path=index_path)
            self.assertEqual(mock_out.getvalue().strip(), 'no')


class TestMatchInstalledWheels(unittest.TestCase):
    def test_matches_installed(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'click-8.1.0': 'click-8.1.0-py3-none-any.whl',
                'flask-3.0.0': 'flask-3.0.0-py3-none-any.whl',
            }, f)
            f.flush()
        try:
            stdin_data = json.dumps([
                {'name': 'click', 'version': '8.1.0'},
                {'name': 'requests', 'version': '2.31.0'},
            ])
            with patch('sys.stdin', io.StringIO(stdin_data)), \
                 patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                match_installed_wheels(f.name)
                self.assertEqual(mock_out.getvalue().strip(), 'click-8.1.0-py3-none-any.whl')
        finally:
            os.unlink(f.name)

    def test_no_matches(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'click-8.1.0': 'click-8.1.0-py3-none-any.whl'}, f)
            f.flush()
        try:
            stdin_data = json.dumps([{'name': 'requests', 'version': '2.31.0'}])
            with patch('sys.stdin', io.StringIO(stdin_data)), \
                 patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                match_installed_wheels(f.name)
                self.assertEqual(mock_out.getvalue().strip(), '')
        finally:
            os.unlink(f.name)


class TestFindMissingWheelFallback(unittest.TestCase):
    def test_cwd_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, 'click-8.1.0-py3-none-any.whl')).touch()
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump({}, f)
                f.flush()
            try:
                with patch('sys.stdout', new_callable=io.StringIO) as mock_out, \
                     patch('wheel_helpers.os.listdir', return_value=os.listdir(tmpdir)):
                    find_missing_wheel('click', '', f.name)
                    self.assertEqual(mock_out.getvalue().strip(),
                                     'click-8.1.0-py3-none-any.whl')
            finally:
                os.unlink(f.name)

    def test_cwd_fallback_skips_tried(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, 'click-8.1.0-py3-none-any.whl')).touch()
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump({}, f)
                f.flush()
            try:
                with patch('sys.stdout', new_callable=io.StringIO) as mock_out, \
                     patch('wheel_helpers.os.listdir', return_value=os.listdir(tmpdir)):
                    find_missing_wheel('click', 'click-8.1.0-py3-none-any.whl', f.name)
                    self.assertEqual(mock_out.getvalue().strip(), '')
            finally:
                os.unlink(f.name)


if __name__ == '__main__':
    unittest.main()
