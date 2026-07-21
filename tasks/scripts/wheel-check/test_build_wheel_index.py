#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_wheel_index import main


class TestBuildWheelIndex(unittest.TestCase):
    def _run_in_dir(self, wheel_files):
        """Create a temp dir with fake wheel files and call main() directly."""
        tmpdir = tempfile.mkdtemp()
        output_path = os.path.join(tmpdir, 'wheel-index.json')
        for name in wheel_files:
            open(os.path.join(tmpdir, name), 'w').close()
        index = main(wheels_dir=tmpdir, output_path=output_path)
        written = json.load(open(output_path))
        for name in wheel_files:
            os.unlink(os.path.join(tmpdir, name))
        os.unlink(output_path)
        os.rmdir(tmpdir)
        return index, written

    def test_single_wheel(self):
        index, written = self._run_in_dir(['click-8.1.0-py3-none-any.whl'])
        self.assertIn('click-8.1.0', index)
        self.assertEqual(index['click-8.1.0'], 'click-8.1.0-py3-none-any.whl')
        self.assertEqual(index, written)

    def test_multiple_wheels(self):
        index, _ = self._run_in_dir([
            'click-8.1.0-py3-none-any.whl',
            'flask-3.0.0-py3-none-any.whl',
        ])
        self.assertEqual(len(index), 2)
        self.assertIn('click-8.1.0', index)
        self.assertIn('flask-3.0.0', index)

    def test_normalizes_name(self):
        index, _ = self._run_in_dir([
            'Pydantic_AI_Slim-2.10.0-py3-none-any.whl',
        ])
        self.assertIn('pydantic_ai_slim-2.10.0', index)

    def test_ignores_non_wheel_files(self):
        index, _ = self._run_in_dir([
            'click-8.1.0-py3-none-any.whl',
            'click-8.1.0.tar.gz',
            'README.md',
        ])
        self.assertEqual(len(index), 1)

    def test_empty_dir(self):
        index, _ = self._run_in_dir([])
        self.assertEqual(len(index), 0)

    def test_build_number_wheel(self):
        index, _ = self._run_in_dir([
            'presidio_analyzer-2.2.359-0-py3-none-any.whl',
        ])
        self.assertIn('presidio_analyzer-2.2.359', index)
        self.assertEqual(
            index['presidio_analyzer-2.2.359'],
            'presidio_analyzer-2.2.359-0-py3-none-any.whl',
        )

    def test_writes_to_output_path(self):
        tmpdir = tempfile.mkdtemp()
        output_path = os.path.join(tmpdir, 'custom-index.json')
        open(os.path.join(tmpdir, 'a-1.0-py3-none-any.whl'), 'w').close()
        main(wheels_dir=tmpdir, output_path=output_path)
        self.assertTrue(os.path.exists(output_path))
        written = json.load(open(output_path))
        self.assertIn('a-1.0', written)
        os.unlink(os.path.join(tmpdir, 'a-1.0-py3-none-any.whl'))
        os.unlink(output_path)
        os.rmdir(tmpdir)


if __name__ == '__main__':
    unittest.main()
