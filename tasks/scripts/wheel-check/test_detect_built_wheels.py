#!/usr/bin/env python3
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from detect_built_wheels import main


class TestDetectBuiltWheels(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir)
        self.wheel_index_path = os.path.join(self.tmpdir, 'wheel-index.json')
        self.built_wheels_path = os.path.join(self.tmpdir, 'built-wheels.json')

    def _write_wheel_index(self, index):
        with open(self.wheel_index_path, 'w') as f:
            json.dump(index, f)

    def _create_file(self, name):
        Path(os.path.join(self.tmpdir, name)).touch()

    def _run(self):
        main(directory=self.tmpdir,
             wheel_index_path=self.wheel_index_path,
             output_path=self.built_wheels_path)
        with open(self.built_wheels_path) as f:
            return json.load(f)

    def test_has_built(self):
        self._write_wheel_index({
            'click-8.1.0': 'click-8.1.0-py3-none-any.whl',
            'requests-2.31.0': 'requests-2.31.0-py3-none-any.whl',
        })
        self._create_file('click-8.1.0.tar.gz')
        self._create_file('click-8.1.0-py3-none-any.whl')
        self._create_file('requests-2.31.0-py3-none-any.whl')

        data = self._run()
        self.assertEqual(data['status'], 'has_built')
        self.assertIn('click-8.1.0-py3-none-any.whl', data['wheels'])
        self.assertNotIn('requests-2.31.0-py3-none-any.whl', data['wheels'])

    def test_all_cached(self):
        self._write_wheel_index({
            'click-8.1.0': 'click-8.1.0-py3-none-any.whl',
        })
        self._create_file('click-8.1.0-py3-none-any.whl')

        data = self._run()
        self.assertEqual(data['status'], 'all_cached')
        self.assertEqual(data['wheels'], [])

    def test_no_sdists_empty_dir(self):
        self._write_wheel_index({})

        data = self._run()
        self.assertEqual(data['status'], 'no_sdists')

    def test_multi_segment_name(self):
        self._write_wheel_index({
            'azure_mgmt_resource-1.0.0': 'azure_mgmt_resource-1.0.0-py3-none-any.whl',
        })
        self._create_file('azure-mgmt-resource-1.0.0.tar.gz')
        self._create_file('azure_mgmt_resource-1.0.0-py3-none-any.whl')

        data = self._run()
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

        data = self._run()
        self.assertEqual(data['status'], 'has_built')
        self.assertEqual(len(data['wheels']), 2)

    def test_no_match(self):
        self._write_wheel_index({
            'other-1.0.0': 'other-1.0.0-py3-none-any.whl',
        })
        self._create_file('unrelated-2.0.0.tar.gz')

        data = self._run()
        self.assertEqual(data['status'], 'no_match')
        self.assertEqual(data['wheels'], [])


if __name__ == '__main__':
    unittest.main()
