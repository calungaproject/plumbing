#!/usr/bin/env python3
"""Unit tests for lookup-npm-tl-compliance (semver + mocked registry)."""
from __future__ import print_function

import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import unittest
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "lookup-npm-tl-compliance")

_loader = importlib.machinery.SourceFileLoader("lookup_npm_tl_compliance", SCRIPT)
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
lookup = importlib.util.module_from_spec(_spec)
sys.dont_write_bytecode = True
_loader.exec_module(lookup)


class FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, url, code):
        hdrs = {}
        fp = io.BytesIO()
        urllib.error.HTTPError.__init__(self, url, code, "err", hdrs, fp)


class SemverTests(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(lookup.satisfies("1.5.0", "1.5.0"))
        self.assertFalse(lookup.satisfies("1.5.1", "1.5.0"))

    def test_caret(self):
        self.assertTrue(lookup.satisfies("1.5.0", "^1.5.0"))
        self.assertTrue(lookup.satisfies("1.9.9", "^1.5.0"))
        self.assertFalse(lookup.satisfies("2.0.0", "^1.5.0"))
        self.assertTrue(lookup.satisfies("0.2.5", "^0.2.3"))
        self.assertFalse(lookup.satisfies("0.3.0", "^0.2.3"))
        self.assertTrue(lookup.satisfies("0.0.3", "^0.0.3"))
        self.assertFalse(lookup.satisfies("0.0.4", "^0.0.3"))

    def test_tilde(self):
        self.assertTrue(lookup.satisfies("1.2.3", "~1.2.3"))
        self.assertTrue(lookup.satisfies("1.2.9", "~1.2.3"))
        self.assertFalse(lookup.satisfies("1.3.0", "~1.2.3"))
        self.assertTrue(lookup.satisfies("1.2.0", "~1.2"))
        self.assertFalse(lookup.satisfies("1.3.0", "~1.2"))

    def test_star_and_x(self):
        self.assertTrue(lookup.satisfies("1.2.3", "*"))
        self.assertTrue(lookup.satisfies("1.2.3", "1.x"))
        self.assertFalse(lookup.satisfies("2.0.0", "1.x"))
        self.assertTrue(lookup.satisfies("1.2.9", "1.2.x"))
        self.assertFalse(lookup.satisfies("1.3.0", "1.2.x"))

    def test_comparators_and_or(self):
        self.assertTrue(lookup.satisfies("1.5.0", ">=1.0.0 <2.0.0"))
        self.assertFalse(lookup.satisfies("2.0.0", ">=1.0.0 <2.0.0"))
        self.assertTrue(lookup.satisfies("2.1.0", "^1.0.0 || ^2.0.0"))

    def test_prerelease_skipped_by_default(self):
        self.assertFalse(lookup.satisfies("1.5.0-beta.1", "^1.5.0"))
        self.assertTrue(lookup.satisfies("1.5.0-beta.1", "^1.5.0-beta.1"))

    def test_max_satisfying_picks_highest(self):
        self.assertEqual(
            lookup.max_satisfying(["1.4.0", "1.5.2", "1.5.0", "2.0.0"], "^1.5.0"),
            "1.5.2",
        )
        self.assertIsNone(lookup.max_satisfying(["2.0.0"], "^1.5.0"))

    def test_registry_spec(self):
        self.assertTrue(lookup.is_registry_spec("^1.5.0"))
        self.assertFalse(lookup.is_registry_spec("git+https://example.com/repo.git"))
        self.assertFalse(lookup.is_registry_spec("https://example.com/foo.tgz"))


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.orig = lookup.get_json
        self.urls = []

    def tearDown(self):
        lookup.get_json = self.orig

    def _install(self, handler):
        def wrapped(url):
            self.urls.append(url)
            return handler(url)

        lookup.get_json = wrapped

    def test_exact_hit_with_sidecar(self):
        def handler(url):
            if url.endswith("/bindings"):
                return {"versions": {"1.5.0": {}, "1.5.5": {}}}
            if url.endswith("bindings-1.5.0.tl-compliance.json"):
                return {"compliance_level": "L2"}
            raise FakeHTTPError(url, 404)

        self._install(handler)
        rc, payload = lookup.lookup("https://example.test/javascript", "bindings", "1.5.0")
        self.assertEqual(rc, 0)
        self.assertEqual(payload["version"], "1.5.0")
        self.assertEqual(payload["compliance_level"], "L2")

    def test_range_picks_highest_and_bootstraps_l3(self):
        def handler(url):
            if url.endswith("/bindings"):
                return {"versions": {"1.5.0": {}, "1.5.5": {}, "2.0.0": {}}}
            raise FakeHTTPError(url, 404)

        self._install(handler)
        rc, payload = lookup.lookup("https://example.test/javascript", "bindings", "^1.5.0")
        self.assertEqual(rc, 0)
        self.assertEqual(payload["version"], "1.5.5")
        self.assertEqual(payload["compliance_level"], "L3")
        self.assertEqual(payload["requested"], "^1.5.0")

    def test_missing_package(self):
        def handler(url):
            raise FakeHTTPError(url, 404)

        self._install(handler)
        rc, payload = lookup.lookup("https://example.test/javascript", "missing", "^1.0.0")
        self.assertEqual(rc, 1)
        self.assertIsNone(payload)

    def test_range_unsatisfied(self):
        def handler(url):
            if url.endswith("/bindings"):
                return {"versions": {"2.0.0": {}}}
            raise FakeHTTPError(url, 404)

        self._install(handler)
        rc, payload = lookup.lookup("https://example.test/javascript", "bindings", "^1.5.0")
        self.assertEqual(rc, 1)
        self.assertIsNone(payload)

    def test_git_spec_is_a_miss(self):
        rc, payload = lookup.lookup(
            "https://example.test/javascript",
            "foo",
            "git+https://github.com/x/y.git",
        )
        self.assertEqual(rc, 1)
        self.assertIsNone(payload)

    def test_scoped_packument_path(self):
        self.assertIn("%2F", lookup.pkg_path("@calunga/esbuild-linux-x64"))

    def test_main_max_satisfying_cli(self):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc = lookup.main(
                ["lookup-npm-tl-compliance", "--max-satisfying", "^1.5.0", "1.4.0", "1.5.1"]
            )
        finally:
            sys.stdout = old
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().strip(), "1.5.1")

    def test_main_json_stdout(self):
        def handler(url):
            if url.endswith("/bindings"):
                return {"versions": {"1.5.0": {}}}
            raise FakeHTTPError(url, 404)

        self._install(handler)
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc = lookup.main(
                [
                    "lookup-npm-tl-compliance",
                    "https://example.test/javascript",
                    "bindings",
                    "^1.5.0",
                ]
            )
        finally:
            sys.stdout = old
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["version"], "1.5.0")
        self.assertEqual(payload["compliance_level"], "L3")


class SkipSidecarTests(unittest.TestCase):
    def test_skip_sidecar_returns_l3_without_fetch(self):
        old = os.environ.get("TL_SKIP_COMPLIANCE_SIDECAR")
        try:
            os.environ["TL_SKIP_COMPLIANCE_SIDECAR"] = "1"
            rc, level = lookup.compliance_for_version(
                "https://example.test/javascript",
                "ms",
                "2.1.3",
            )
        finally:
            if old is None:
                os.environ.pop("TL_SKIP_COMPLIANCE_SIDECAR", None)
            else:
                os.environ["TL_SKIP_COMPLIANCE_SIDECAR"] = old
        self.assertEqual(rc, 0)
        self.assertEqual(level, "L3")


class TmpSidecar(unittest.TestCase):
    """Sanity: script file is executable-shaped (shebang)."""

    def test_shebang(self):
        with open(SCRIPT) as fh:
            self.assertTrue(fh.readline().startswith("#!"))


if __name__ == "__main__":
    unittest.main()
