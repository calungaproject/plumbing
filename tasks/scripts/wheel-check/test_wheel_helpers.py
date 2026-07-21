#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wheel_helpers import (
    annotate_dep,
    extract_missing_module,
    find_missing_wheel,
    format_summary_row,
    group_has_built,
    lookup_primary,
    lookup_wheel,
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
            self.assertEqual(read_result_status(f.name), 'PASS')
        os.unlink(f.name)

    def test_fail(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'status': 'FAIL'}, f)
            f.flush()
            self.assertEqual(read_result_status(f.name), 'FAIL')
        os.unlink(f.name)

    def test_missing_status(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()
            self.assertEqual(read_result_status(f.name), 'FAIL')
        os.unlink(f.name)

    def test_missing_file(self):
        self.assertEqual(read_result_status('/tmp/nonexistent-file-12345.json'), 'FAIL')

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not json')
            f.flush()
            self.assertEqual(read_result_status(f.name), 'FAIL')
        os.unlink(f.name)


class TestReadField(unittest.TestCase):
    def test_existing_field(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'wheel': 'foo-1.0.whl', 'status': 'PASS'}, f)
            f.flush()
            self.assertEqual(read_field(f.name, 'wheel'), 'foo-1.0.whl')
        os.unlink(f.name)

    def test_missing_field(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'status': 'PASS'}, f)
            f.flush()
            self.assertEqual(read_field(f.name, 'undeclared_dep'), '')
        os.unlink(f.name)

    def test_missing_file(self):
        self.assertEqual(read_field('/tmp/nonexistent-file-12345.json', 'status'), '')


class TestPrintFailedImports(unittest.TestCase):
    def test_prints_failures(self, ):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'imports_tested': [
                    {'name': 'foo', 'success': True, 'message': 'OK'},
                    {'name': 'bar', 'success': False, 'message': 'ImportError: No module named bar'},
                ]
            }, f)
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                print_failed_imports(f.name, prefix='  -> ')
                output = mock_out.getvalue()
            self.assertIn('bar', output)
            self.assertIn('  -> ', output)
            self.assertNotIn('foo', output)
        os.unlink(f.name)

    def test_no_failures(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'imports_tested': [{'name': 'foo', 'success': True}]}, f)
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                print_failed_imports(f.name)
                self.assertEqual(mock_out.getvalue(), '')
        os.unlink(f.name)

    def test_corrupt_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not json')
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                print_failed_imports(f.name)
                self.assertEqual(mock_out.getvalue(), '')
        os.unlink(f.name)


class TestFormatSummaryRow(unittest.TestCase):
    def test_pass(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'wheel': 'foo-1.0.whl', 'status': 'PASS', 'reason': ''}, f)
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                format_summary_row(f.name)
                self.assertIn('PASS', mock_out.getvalue())
                self.assertIn('foo-1.0.whl', mock_out.getvalue())
        os.unlink(f.name)

    def test_with_undeclared_dep(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'wheel': 'foo-1.0.whl', 'status': 'PASS', 'reason': '', 'undeclared_dep': 'bar'}, f)
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                format_summary_row(f.name)
                self.assertIn('undeclared dep: bar', mock_out.getvalue())
        os.unlink(f.name)

    def test_invalid_file(self):
        import io
        from unittest.mock import patch
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
            annotate_dep(f.name, 'click')
            with open(f.name) as rf:
                d = json.load(rf)
            self.assertEqual(d['undeclared_dep'], 'click')
        os.unlink(f.name)


class TestLookupWheel(unittest.TestCase):
    def test_found(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'click-8.1.0': 'click-8.1.0-py3-none-any.whl'}, f)
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                lookup_wheel(f.name, 'click', '8.1.0')
                self.assertEqual(mock_out.getvalue().strip(), 'click-8.1.0-py3-none-any.whl')
        os.unlink(f.name)

    def test_not_found(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                lookup_wheel(f.name, 'nonexistent', '1.0')
                self.assertEqual(mock_out.getvalue().strip(), '')
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
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                extract_missing_module(f.name)
                self.assertEqual(mock_out.getvalue().strip(), 'click')
        os.unlink(f.name)

    def test_dotted_module(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'imports_tested': [
                    {'name': 'foo', 'success': False, 'message': "ImportError: No module named 'pkg.sub'"},
                ]
            }, f)
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                extract_missing_module(f.name)
                self.assertEqual(mock_out.getvalue().strip(), 'pkg')
        os.unlink(f.name)

    def test_no_missing(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'imports_tested': [{'name': 'foo', 'success': True}]}, f)
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                extract_missing_module(f.name)
                self.assertEqual(mock_out.getvalue().strip(), '')
        os.unlink(f.name)

    def test_corrupt_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not json')
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                extract_missing_module(f.name)
                self.assertEqual(mock_out.getvalue().strip(), '')
        os.unlink(f.name)


class TestWriteFailureResult(unittest.TestCase):
    def test_output(self):
        import io
        from unittest.mock import patch
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            write_failure_result('foo-1.0.whl', 'pip install failed')
            d = json.loads(mock_out.getvalue())
            self.assertEqual(d['wheel'], 'foo-1.0.whl')
            self.assertEqual(d['status'], 'FAIL')
            self.assertEqual(d['reason'], 'pip install failed')


class TestLookupPrimary(unittest.TestCase):
    def _make_files(self, summary_entries, wheel_index):
        summary_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(summary_entries, summary_file)
        summary_file.flush()
        index_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(wheel_index, index_file)
        index_file.flush()
        return summary_file.name, index_file.name

    def test_normal_label(self):
        summary_path, index_path = self._make_files(
            [{'name': 'click', 'version': '8.1.0'}],
            {'click-8.1.0': 'click-8.1.0-0-py3-none-any.whl'},
        )
        import io
        from unittest.mock import patch
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            lookup_primary('click__8.1.0', summary_path, index_path)
            lines = mock_out.getvalue().strip().split('\n')
            self.assertEqual(lines[0], 'click')
            self.assertEqual(lines[1], '8.1.0')
            self.assertEqual(lines[2], 'click-8.1.0-0-py3-none-any.whl')
        os.unlink(summary_path)
        os.unlink(index_path)

    def test_git_sourced_label(self):
        summary_path, index_path = self._make_files(
            [
                {'name': 'presidio-analyzer', 'version': '2.2.359'},
                {'name': 'spacy', 'version': '3.8.13'},
            ],
            {'presidio_analyzer-2.2.359': 'presidio_analyzer-2.2.359-0-py3-none-any.whl'},
        )
        import io
        from unittest.mock import patch
        label = 'presidio_analyzer___git_https___github.com_microsoft_presidio.git_2.2.359'
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            lookup_primary(label, summary_path, index_path)
            lines = mock_out.getvalue().strip().split('\n')
            self.assertEqual(lines[0], 'presidio-analyzer')
            self.assertEqual(lines[1], '2.2.359')
            self.assertEqual(lines[2], 'presidio_analyzer-2.2.359-0-py3-none-any.whl')
        os.unlink(summary_path)
        os.unlink(index_path)

    def test_hyphenated_name(self):
        summary_path, index_path = self._make_files(
            [{'name': 'pydantic-ai-slim', 'version': '2.10.0'}],
            {'pydantic_ai_slim-2.10.0': 'pydantic_ai_slim-2.10.0-0-py3-none-any.whl'},
        )
        import io
        from unittest.mock import patch
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            lookup_primary('pydantic-ai-slim__2.10.0', summary_path, index_path)
            lines = mock_out.getvalue().strip().split('\n')
            self.assertEqual(lines[0], 'pydantic-ai-slim')
            self.assertEqual(lines[1], '2.10.0')
        os.unlink(summary_path)
        os.unlink(index_path)

    def test_no_match(self):
        summary_path, index_path = self._make_files(
            [{'name': 'other-pkg', 'version': '1.0'}],
            {},
        )
        import io
        from unittest.mock import patch
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            lookup_primary('click__8.1.0', summary_path, index_path)
            self.assertEqual(mock_out.getvalue().strip(), '')
        os.unlink(summary_path)
        os.unlink(index_path)

    def test_empty_summary(self):
        summary_path, index_path = self._make_files([], {})
        import io
        from unittest.mock import patch
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            lookup_primary('click__8.1.0', summary_path, index_path)
            self.assertEqual(mock_out.getvalue().strip(), '')
        os.unlink(summary_path)
        os.unlink(index_path)

    def test_no_prefix_collision(self):
        summary_path, index_path = self._make_files(
            [
                {'name': 'foo', 'version': '1.0'},
                {'name': 'foobar', 'version': '2.0'},
            ],
            {'foobar-2.0': 'foobar-2.0-0-py3-none-any.whl'},
        )
        import io
        from unittest.mock import patch
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            lookup_primary('foobar__2.0', summary_path, index_path)
            lines = mock_out.getvalue().strip().split('\n')
            self.assertEqual(lines[0], 'foobar')
            self.assertEqual(lines[1], '2.0')
        os.unlink(summary_path)
        os.unlink(index_path)


class TestFindMissingWheel(unittest.TestCase):
    def test_from_import_map(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'click': ['click-8.1.0-py3-none-any.whl']}, f)
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                find_missing_wheel('click', '', f.name)
                self.assertEqual(mock_out.getvalue().strip(), 'click-8.1.0-py3-none-any.whl')
        os.unlink(f.name)

    def test_skips_tried(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'click': ['click-8.1.0-py3-none-any.whl']}, f)
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                find_missing_wheel('click', 'click-8.1.0-py3-none-any.whl', f.name)
                self.assertEqual(mock_out.getvalue().strip(), '')
        os.unlink(f.name)

    def test_corrupt_import_map(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not json')
            f.flush()
            import io
            from unittest.mock import patch
            with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
                find_missing_wheel('click', '', f.name)
                self.assertEqual(mock_out.getvalue().strip(), '')
        os.unlink(f.name)


class TestCLIDispatch(unittest.TestCase):
    def test_read_status_cli(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'status': 'PASS'}, f)
            f.flush()
            script = str(Path(__file__).resolve().parent / 'wheel_helpers.py')
            result = subprocess.run(
                [sys.executable, script, 'read-status', f.name],
                capture_output=True, text=True,
            )
            self.assertEqual(result.stdout.strip(), 'PASS')
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
        import io
        from unittest.mock import patch
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            write_skip_result('cached.whl', 'no matching sdist')
            d = json.loads(mock_out.getvalue())
            self.assertEqual(d['status'], 'SKIP')
            self.assertEqual(d['wheel'], 'cached.whl')
            self.assertEqual(d['reason'], 'no matching sdist')
            self.assertEqual(d['imports_tested'], [])


class TestReadBuiltStatus(unittest.TestCase):
    def test_reads_status(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False,
                                          dir='/tmp', prefix='built-wheels') as f:
            json.dump({'status': 'has_built', 'wheels': ['a.whl']}, f)
            f.flush()
        saved = '/tmp/built-wheels.json'
        import shutil
        shutil.copy(f.name, saved)
        os.unlink(f.name)
        try:
            self.assertEqual(read_built_status(), 'has_built')
        finally:
            os.unlink(saved)

    def test_missing_file(self):
        saved = '/tmp/built-wheels.json'
        if os.path.exists(saved):
            os.unlink(saved)
        self.assertEqual(read_built_status(), 'no_sdists')


class TestReadBuiltWheels(unittest.TestCase):
    def test_reads_wheels(self):
        saved = '/tmp/built-wheels.json'
        with open(saved, 'w') as f:
            json.dump({'status': 'has_built', 'wheels': ['a.whl', 'b.whl']}, f)
        try:
            result = read_built_wheels()
            self.assertIn('a.whl', result)
            self.assertIn('b.whl', result)
        finally:
            os.unlink(saved)

    def test_missing_file(self):
        saved = '/tmp/built-wheels.json'
        if os.path.exists(saved):
            os.unlink(saved)
        self.assertEqual(read_built_wheels(), '')


class TestGroupHasBuilt(unittest.TestCase):
    def _setup(self, summary_entries, wheel_index, built_csv):
        summary_path = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(summary_entries, summary_path)
        summary_path.flush()
        with open('/tmp/wheel-index.json', 'w') as f:
            json.dump(wheel_index, f)
        return summary_path.name

    def test_has_built_wheel(self):
        summary_path = self._setup(
            [{'name': 'click', 'version': '8.1.0'}],
            {'click-8.1.0': 'click-8.1.0-py3-none-any.whl'},
            'click-8.1.0-py3-none-any.whl',
        )
        import io
        from unittest.mock import patch
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            group_has_built(summary_path, 'click-8.1.0-py3-none-any.whl')
            self.assertEqual(mock_out.getvalue().strip(), 'yes')
        os.unlink(summary_path)

    def test_no_built_wheel(self):
        summary_path = self._setup(
            [{'name': 'click', 'version': '8.1.0'}],
            {'click-8.1.0': 'click-8.1.0-py3-none-any.whl'},
            'other.whl',
        )
        import io
        from unittest.mock import patch
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            group_has_built(summary_path, 'other.whl')
            self.assertEqual(mock_out.getvalue().strip(), 'no')
        os.unlink(summary_path)

    def test_empty_summary(self):
        summary_path = self._setup([], {}, '')
        import io
        from unittest.mock import patch
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out:
            group_has_built(summary_path, 'any.whl')
            self.assertEqual(mock_out.getvalue().strip(), 'no')
        os.unlink(summary_path)

    def test_corrupt_json_warns(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not json')
            f.flush()
        import io
        from unittest.mock import patch
        with patch('sys.stdout', new_callable=io.StringIO) as mock_out, \
             patch('sys.stderr', new_callable=io.StringIO) as mock_err:
            group_has_built(f.name, 'any.whl')
            self.assertEqual(mock_out.getvalue().strip(), 'no')
            self.assertIn('WARNING', mock_err.getvalue())
        os.unlink(f.name)


if __name__ == '__main__':
    unittest.main()
