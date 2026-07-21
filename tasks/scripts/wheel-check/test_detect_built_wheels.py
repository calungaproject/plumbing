#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = str(Path(__file__).resolve().parent / 'detect_built_wheels.py')


class TestDetectBuiltWheels(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.wheel_index_path = '/tmp/wheel-index.json'

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)
        for f in [self.wheel_index_path, '/tmp/built-wheels.json']:
            if os.path.exists(f):
                os.unlink(f)

    def _write_wheel_index(self, index):
        with open(self.wheel_index_path, 'w') as f:
            json.dump(index, f)

    def _create_file(self, name):
        open(os.path.join(self.tmpdir, name), 'w').close()

    def _run(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, self.tmpdir],
            capture_output=True, text=True,
        )
        with open('/tmp/built-wheels.json') as f:
            return json.load(f), result.stdout

    def test_has_built(self):
        self._write_wheel_index({
            'click-8.1.0': 'click-8.1.0-py3-none-any.whl',
            'requests-2.31.0': 'requests-2.31.0-py3-none-any.whl',
        })
        self._create_file('click-8.1.0.tar.gz')
        self._create_file('click-8.1.0-py3-none-any.whl')
        self._create_file('requests-2.31.0-py3-none-any.whl')

        data, stdout = self._run()
        self.assertEqual(data['status'], 'has_built')
        self.assertIn('click-8.1.0-py3-none-any.whl', data['wheels'])
        self.assertNotIn('requests-2.31.0-py3-none-any.whl', data['wheels'])
        self.assertIn('1 sdist', stdout)

    def test_all_cached(self):
        self._write_wheel_index({
            'click-8.1.0': 'click-8.1.0-py3-none-any.whl',
        })
        self._create_file('click-8.1.0-py3-none-any.whl')

        data, stdout = self._run()
        self.assertEqual(data['status'], 'all_cached')
        self.assertEqual(data['wheels'], [])
        self.assertIn('cache', stdout)

    def test_no_sdists_empty_dir(self):
        self._write_wheel_index({})

        data, stdout = self._run()
        self.assertEqual(data['status'], 'no_sdists')

    def test_multi_segment_name(self):
        self._write_wheel_index({
            'azure_mgmt_resource-1.0.0': 'azure_mgmt_resource-1.0.0-py3-none-any.whl',
        })
        self._create_file('azure-mgmt-resource-1.0.0.tar.gz')
        self._create_file('azure_mgmt_resource-1.0.0-py3-none-any.whl')

        data, _ = self._run()
        self.assertEqual(data['status'], 'has_built')
        self.assertIn('azure_mgmt_resource-1.0.0-py3-none-any.whl', data['wheels'])

    def test_multiple_sdists(self):
        self._write_wheel_index({
            'click-8.1.0': 'click-8.1.0-py3-none-any.whl',
            'flask-2.3.0': 'flask-2.3.0-py3-none-any.whl',
            'requests-2.31.0': 'requests-2.31.0-py3-none-any.whl',
        })
        self._create_file('click-8.1.0.tar.gz')
        self._create_file('flask-2.3.0.tar.gz')

        data, stdout = self._run()
        self.assertEqual(data['status'], 'has_built')
        self.assertEqual(len(data['wheels']), 2)
        self.assertIn('2 sdist', stdout)


if __name__ == '__main__':
    unittest.main()
