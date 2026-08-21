#!/usr/bin/env python3
"""Unit tests for update-npm-closure (pure logic; no live Pulp/Quay)."""
from __future__ import print_function

import importlib.machinery
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "update-npm-closure")

_loader = importlib.machinery.SourceFileLoader("update_npm_closure", SCRIPT)
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
closure = importlib.util.module_from_spec(_spec)
sys.dont_write_bytecode = True
_loader.exec_module(closure)


class LevelTests(unittest.TestCase):
    def test_leaf_l3(self):
        doc = {"missing_gaps": [], "pending_l3_gaps": []}
        self.assertEqual(closure.compute_level(doc), "L3")

    def test_missing_l1(self):
        doc = {"missing_gaps": ["dep@1.0.0"], "pending_l3_gaps": []}
        self.assertEqual(closure.compute_level(doc), "L1")

    def test_pending_l2(self):
        doc = {"missing_gaps": [], "pending_l3_gaps": ["dep@1.0.0"]}
        self.assertEqual(closure.compute_level(doc), "L2")

    def test_missing_beats_pending(self):
        doc = {"missing_gaps": ["a@1.0.0"], "pending_l3_gaps": ["b@2.0.0"]}
        self.assertEqual(closure.compute_level(doc), "L1")


class GapRefreshTests(unittest.TestCase):
    def test_missing_to_pending_when_blocker_l2(self):
        doc = {
            "name": "parent",
            "version": "1.0.0",
            "compliance_revision": 1,
            "direct_dependencies": [{"name": "dep", "requested": "^1.0.0"}],
            "missing_gaps": ["dep@1.0.0"],
            "pending_l3_gaps": [],
            "compliance_level": "L1",
        }
        updated = closure.refresh_parent_doc(doc, "dep@1.0.0", "L2")
        self.assertEqual(updated["missing_gaps"], [])
        self.assertEqual(updated["pending_l3_gaps"], ["dep@1.0.0"])
        self.assertEqual(updated["compliance_level"], "L2")
        self.assertEqual(updated["direct_dependencies"], doc["direct_dependencies"])

    def test_pending_removed_when_blocker_l3(self):
        doc = {
            "name": "parent",
            "version": "1.0.0",
            "compliance_revision": 2,
            "direct_dependencies": [{"name": "dep", "requested": "1.0.0"}],
            "missing_gaps": [],
            "pending_l3_gaps": ["dep@1.0.0"],
            "compliance_level": "L2",
        }
        updated = closure.refresh_parent_doc(doc, "dep@1.0.0", "L3")
        self.assertEqual(updated["pending_l3_gaps"], [])
        self.assertEqual(updated["compliance_level"], "L3")

    def test_missing_cleared_to_l3_when_blocker_l3_and_no_pending(self):
        doc = {
            "name": "parent",
            "version": "1.0.0",
            "compliance_revision": 1,
            "direct_dependencies": [{"name": "dep", "requested": "1.0.0"}],
            "missing_gaps": ["dep@1.0.0"],
            "pending_l3_gaps": [],
            "compliance_level": "L1",
        }
        updated = closure.refresh_parent_doc(doc, "dep@1.0.0", "L3")
        self.assertEqual(updated["missing_gaps"], [])
        self.assertEqual(updated["pending_l3_gaps"], [])
        self.assertEqual(updated["compliance_level"], "L3")


class IndexTests(unittest.TestCase):
    def test_rebuild_index_from_docs(self):
        docs = {
            "send@0.19.0": {
                "missing_gaps": ["depd@1.2.0"],
                "pending_l3_gaps": ["ms@2.1.3"],
            },
            "express@4.21.0": {
                "missing_gaps": [],
                "pending_l3_gaps": ["send@0.19.0"],
            },
        }
        index = closure.rebuild_index_from_docs(docs)
        self.assertEqual(
            index["entries"]["depd@1.2.0"]["parents"],
            ["send@0.19.0"],
        )
        self.assertEqual(
            index["entries"]["send@0.19.0"]["parents"],
            ["express@4.21.0"],
        )

    def test_apply_index_release_drops_l3_blocker(self):
        index = closure.empty_index()
        index["entries"]["send@0.19.0"] = {"parents": ["express@4.21.0"]}
        doc = {
            "missing_gaps": [],
            "pending_l3_gaps": [],
            "compliance_level": "L3",
        }
        closure.apply_index_release(index, "send@0.19.0", doc, "L3")
        self.assertNotIn("send@0.19.0", index["entries"])

    def test_apply_index_release_drops_range_blocker_key(self):
        index = closure.empty_index()
        index["entries"]["on-headers@~1.0.2"] = {"parents": ["morgan@1.10.0"]}
        doc = {
            "missing_gaps": [],
            "pending_l3_gaps": [],
            "compliance_level": "L3",
        }
        closure.apply_index_release(index, "on-headers@1.0.2", doc, "L3")
        self.assertNotIn("on-headers@~1.0.2", index["entries"])

    def test_find_index_blocker_keys_for_release_tilde(self):
        index = {
            "entries": {
                "on-headers@~1.0.2": {"parents": ["morgan@1.10.0"]},
                "basic-auth@~2.0.1": {"parents": ["morgan@1.10.0"]},
            }
        }
        keys = closure.find_index_blocker_keys_for_release(
            index, "on-headers", "1.0.2"
        )
        self.assertEqual(keys, ["on-headers@~1.0.2"])

    def test_register_adds_gap_parents(self):
        index = closure.empty_index()
        doc = {
            "missing_gaps": ["depd@1.0.0"],
            "pending_l3_gaps": ["ms@2.0.0"],
        }
        closure.register_package_on_index(index, "send@0.19.0", doc)
        self.assertEqual(index["entries"]["depd@1.0.0"]["parents"], ["send@0.19.0"])
        self.assertEqual(index["entries"]["ms@2.0.0"]["parents"], ["send@0.19.0"])


class NormalizeTests(unittest.TestCase):
    def test_normalize_v3_doc(self):
        doc = closure.normalize_doc(
            {
                "schema_version": 3,
                "name": "leaf",
                "version": "1.0.0",
                "compliance_level": "L3",
                "direct_dependencies": [{"name": "a", "requested": "^1.0.0"}],
                "missing_gaps": [],
                "pending_l3_gaps": [],
            }
        )
        self.assertEqual(doc["schema_version"], 3)
        self.assertEqual(doc["direct_dependencies"][0]["requested"], "^1.0.0")
        self.assertNotIn("version", doc["direct_dependencies"][0])

    def test_normalize_legacy_closure_gaps(self):
        doc = closure.normalize_doc(
            {
                "name": "x",
                "version": "1.0.0",
                "closure_gaps": [{"name": "missing", "requested": "1.0.0"}],
                "direct_dependencies": [{"name": "missing", "requested": "1.0.0"}],
            }
        )
        self.assertIn("missing@1.0.0", doc["missing_gaps"])


class ComplianceRefTests(unittest.TestCase):
    def test_compliance_oci_tag_unscoped(self):
        self.assertEqual(closure.compliance_oci_tag("debug", "4.4.3"), "debug-4.4.3")

    def test_compliance_oci_tag_scoped(self):
        self.assertEqual(
            closure.compliance_oci_tag("@babel/core", "7.0.0"),
            "babel-core-7.0.0",
        )

    def test_doc_to_compliance_json(self):
        old = os.environ.get("COMPLIANCE_IMAGE_PREFIX")
        try:
            os.environ["COMPLIANCE_IMAGE_PREFIX"] = "quay.example/npm-compliance"
            doc = closure.doc_to_compliance_json(
                {
                    "name": "leaf",
                    "version": "1.0.0",
                    "compliance_level": "L3",
                    "direct_dependencies": [{"name": "a", "requested": "1.0.0"}],
                    "missing_gaps": [],
                    "pending_l3_gaps": [],
                    "compliance_revision": 1,
                    "pulp_href": "/api/pulp/.../npm/packages/x/",
                }
            )
        finally:
            if old is None:
                os.environ.pop("COMPLIANCE_IMAGE_PREFIX", None)
            else:
                os.environ["COMPLIANCE_IMAGE_PREFIX"] = old
        self.assertEqual(doc["schema_version"], 3)
        self.assertEqual(doc["compliance_level"], "L3")
        self.assertNotIn("parents", doc)
        self.assertEqual(doc["compliance_oci"], "quay.example/npm-compliance:leaf-1.0.0")

    def test_closure_index_image_default(self):
        old = os.environ.get("COMPLIANCE_IMAGE_PREFIX")
        try:
            os.environ["COMPLIANCE_IMAGE_PREFIX"] = "quay.example/org/npm-compliance"
            self.assertEqual(
                closure.closure_index_image_ref(),
                "quay.example/org/npm-compliance/npm-closure-index:latest",
            )
        finally:
            if old is None:
                os.environ.pop("COMPLIANCE_IMAGE_PREFIX", None)
            else:
                os.environ["COMPLIANCE_IMAGE_PREFIX"] = old


class SafetyTests(unittest.TestCase):
    def test_refuses_python_main_repository_name(self):
        old = os.environ.get("PULP_REPOSITORY")
        try:
            os.environ["PULP_REPOSITORY"] = "main"
            with self.assertRaises(SystemExit):
                closure.npm_repository_name()
        finally:
            if old is None:
                os.environ.pop("PULP_REPOSITORY", None)
            else:
                os.environ["PULP_REPOSITORY"] = old

    def test_gap_must_be_direct_dependency(self):
        with self.assertRaises(SystemExit):
            closure.validate_gap_subset(
                {
                    "name": "p",
                    "version": "1.0.0",
                    "direct_dependencies": [{"name": "a", "requested": "1.0.0"}],
                    "missing_gaps": ["b@1.0.0"],
                    "pending_l3_gaps": [],
                }
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
