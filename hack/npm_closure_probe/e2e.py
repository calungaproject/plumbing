"""Parent + level propagation E2E scenario."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .add import add_package
from .env import ProbeEnv, require_commands


SEND_NAME = "send"
SEND_VERSION = "0.19.0"
FINAL_NAME = "finalhandler"
FINAL_VERSION = "1.3.1"
DEBUG_NAME = "debug"
DEBUG_VERSION = "2.6.9"
MS_SEND_VERSION = "2.1.3"

SHARED_DEP_PROBES = [
    ("ee-first", "1.1.1"),
    ("ms", "2.0.0"),
    ("statuses", "2.0.1"),
    ("escape-html", "1.0.3"),
    ("on-finished", "2.4.1"),
    ("debug", "2.6.9"),
]
FINAL_ONLY_PROBES = [
    ("parseurl", "1.3.3"),
    ("unpipe", "1.0.0"),
    ("encodeurl", "2.0.0"),
]


@dataclass
class E2EResults:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    seed_first: bool = False

    def ok(self, msg: str) -> None:
        print(f"PASS: {msg}")
        self.passed += 1

    def bad(self, msg: str) -> None:
        print(f"FAIL: {msg}", file=sys.stderr)
        self.failed += 1

    def skip(self, msg: str) -> None:
        print(f"SKIP: {msg}")
        self.skipped += 1


def _pull_oci_json(image_ref: str, pattern: str) -> dict | None:
    tmp = Path(tempfile.mkdtemp(prefix="npm-probe-pull."))
    try:
        subprocess.run(
            ["oras", "pull", image_ref, "-o", str(tmp)],
            check=False,
            capture_output=True,
        )
        matches = list(tmp.glob(pattern))
        if not matches:
            return None
        return json.loads(matches[0].read_text())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pull_compliance(probe_env: ProbeEnv, name: str, version: str) -> dict | None:
    ref = probe_env.compliance_image_for(name, version)
    return _pull_oci_json(ref, "*.tl-compliance.json")


def pull_index(probe_env: ProbeEnv) -> dict | None:
    return _pull_oci_json(probe_env.closure_index_image, "npm-closure-index.json")


def show_compliance(probe_env: ProbeEnv, name: str, version: str, label: str) -> None:
    print()
    print(f"=== {label}: {name}@{version} ===")
    print(f"  OCI: {probe_env.compliance_image_for(name, version)}")
    doc = pull_compliance(probe_env, name, version)
    if doc is None:
        print("  (compliance OCI not found yet)")
        return
    summary = {
        "level": doc.get("compliance_level"),
        "missing": doc.get("missing_gaps") or [],
        "pending": doc.get("pending_l3_gaps") or [],
        "deps": [
            {"name": d.get("name"), "requested": d.get("requested")}
            for d in doc.get("direct_dependencies") or []
        ],
    }
    print(json.dumps(summary, indent=2))


def run_probe(
    probe_env: ProbeEnv,
    results: E2EResults,
    name: str,
    version: str,
) -> None:
    seed = results.seed_first
    if seed:
        results.seed_first = False
    add_package(
        probe_env,
        name,
        version,
        seed_first=seed,
    )


class E2ERunner:
    def __init__(self, probe_env: ProbeEnv, mode: str = "all", seed_first: bool = False):
        self.env = probe_env
        self.mode = mode
        self.results = E2EResults(seed_first=seed_first)

    def should_run(self, phase: str) -> bool:
        return self.mode in ("all", phase)

    def assert_level(self, name: str, version: str, want: str, ctx: str) -> None:
        doc = pull_compliance(self.env, name, version)
        if doc is None:
            self.results.bad(f"{ctx}: no compliance OCI for {name}@{version}")
            return
        got = doc.get("compliance_level") or ""
        if got == want:
            self.results.ok(f"{ctx}: {name}@{version} level={want}")
        else:
            self.results.bad(f"{ctx}: {name}@{version} level want={want} got={got or '<empty>'}")

    def assert_level_one_of(
        self, name: str, version: str, ctx: str, *wants: str
    ) -> None:
        doc = pull_compliance(self.env, name, version)
        if doc is None:
            self.results.bad(f"{ctx}: no compliance OCI for {name}@{version}")
            return
        got = doc.get("compliance_level") or ""
        if got in wants:
            self.results.ok(f"{ctx}: {name}@{version} level={got}")
        else:
            self.results.bad(
                f"{ctx}: {name}@{version} level want one of [{', '.join(wants)}] "
                f"got={got or '<empty>'}"
            )

    def assert_oci_exists(self, name: str, version: str, ctx: str) -> None:
        if pull_compliance(self.env, name, version) is not None:
            self.results.ok(f"{ctx}: compliance OCI exists for {name}@{version}")
        else:
            self.results.bad(f"{ctx}: missing compliance OCI for {name}@{version}")

    def assert_index_includes_parent(
        self, blocker_key: str, parent_key: str, ctx: str
    ) -> None:
        index = pull_index(self.env)
        if index is None:
            self.results.bad(
                f"{ctx}: closure index OCI not found ({self.env.closure_index_image})"
            )
            return
        parents = (index.get("entries") or {}).get(blocker_key, {}).get("parents") or []
        if parent_key in parents:
            self.results.ok(f"{ctx}: index[{blocker_key}] includes {parent_key}")
        else:
            self.results.bad(
                f"{ctx}: index[{blocker_key}] missing {parent_key} (parents={parents!r})"
            )

    def assert_send_registered_on_index(self, ctx: str) -> None:
        send_key = f"{SEND_NAME}@{SEND_VERSION}"
        doc = pull_compliance(self.env, SEND_NAME, SEND_VERSION)
        if doc is None:
            self.results.bad(f"{ctx}: no compliance OCI for {send_key}")
            return
        gaps = (doc.get("missing_gaps") or []) + (doc.get("pending_l3_gaps") or [])
        if not gaps:
            self.results.skip(f"{ctx}: {send_key} has no gap keys on index (already L3?)")
            return
        for blocker in gaps:
            self.assert_index_includes_parent(blocker, send_key, ctx)

    def phase_shared(self) -> None:
        print()
        print(">>> Phase shared: land dependency chain on TL (idempotent reuse)")
        for name, version in SHARED_DEP_PROBES:
            print(f"--- probe {name}@{version} ---")
            run_probe(self.env, self.results, name, version)
            show_compliance(self.env, name, version, f"After {name} probe")
        print()
        print(f"--- refresh debug@{DEBUG_VERSION} (ms@2.0.0 now on TL) ---")
        run_probe(self.env, self.results, DEBUG_NAME, DEBUG_VERSION)
        show_compliance(self.env, DEBUG_NAME, DEBUG_VERSION, "debug refreshed")
        self.assert_level(DEBUG_NAME, DEBUG_VERSION, "L3", "shared/debug")

    def phase_parents(self) -> None:
        print()
        print(">>> Phase parents: probe/re-probe consumers + assert closure index links")
        if self.mode != "verify":
            run_probe(self.env, self.results, SEND_NAME, SEND_VERSION)
            show_compliance(self.env, SEND_NAME, SEND_VERSION, "send")
            self.assert_oci_exists(SEND_NAME, SEND_VERSION, "parents/send-oci")
            self.assert_level_one_of(
                SEND_NAME, SEND_VERSION, "parents/send-level", "L1", "L2"
            )
            self.assert_send_registered_on_index("parents/send-index")

            print(
                f"--- land ms@{MS_SEND_VERSION} "
                "(send dep; after send registers index waiters) ---"
            )
            run_probe(self.env, self.results, "ms", MS_SEND_VERSION)
            show_compliance(self.env, "ms", MS_SEND_VERSION, "ms for send")

            run_probe(self.env, self.results, FINAL_NAME, FINAL_VERSION)
            show_compliance(self.env, FINAL_NAME, FINAL_VERSION, "finalhandler")
            self.assert_oci_exists(FINAL_NAME, FINAL_VERSION, "parents/final-oci")
            self.assert_level_one_of(
                FINAL_NAME,
                FINAL_VERSION,
                "parents/final-level",
                "L1",
                "L2",
                "L3",
            )
        else:
            self.results.skip("parents probes (--mode verify)")

        show_compliance(self.env, "statuses", "2.0.1", "Shared dep statuses")
        show_compliance(self.env, DEBUG_NAME, DEBUG_VERSION, "Shared dep debug")
        if self.mode == "verify":
            self.assert_send_registered_on_index("parents")

    def phase_levels(self) -> None:
        print()
        print(">>> Phase levels: finalhandler-only deps + L3 assertion")
        if self.mode != "verify":
            for name, version in FINAL_ONLY_PROBES:
                print(f"--- probe {name}@{version} ---")
                run_probe(self.env, self.results, name, version)
            print(f"--- refresh debug@{DEBUG_VERSION} ---")
            run_probe(self.env, self.results, DEBUG_NAME, DEBUG_VERSION)
            self.assert_level(DEBUG_NAME, DEBUG_VERSION, "L3", "levels/debug")
            print(f"--- refresh finalhandler@{FINAL_VERSION} ---")
            run_probe(self.env, self.results, FINAL_NAME, FINAL_VERSION)
        else:
            self.results.skip("levels probes (--mode verify)")

        show_compliance(
            self.env, FINAL_NAME, FINAL_VERSION, "finalhandler final"
        )
        self.assert_level(FINAL_NAME, FINAL_VERSION, "L3", "levels/finalhandler")
        self.assert_level_one_of(
            SEND_NAME, SEND_VERSION, "levels/send", "L1", "L2"
        )

    def run(self) -> int:
        require_commands("jq", "oras")
        if self.mode != "verify":
            self.env.require_quay_env()
            self.env.require_pulp_creds()
        else:
            self.env.require_compliance_prefix()

        send_key = f"{SEND_NAME}@{SEND_VERSION}"
        final_key = f"{FINAL_NAME}@{FINAL_VERSION}"
        print(f"Parent + level propagation E2E (mode={self.mode})")
        print(f"  Parents:  {send_key}  +  {final_key}")
        print(
            "  Shared:   debug@2.6.9 escape-html@1.0.3 on-finished@2.4.1 "
            "statuses@2.0.1 ms@2.0.0"
        )
        print(f"            ms@{MS_SEND_VERSION} probed after send in parents phase")
        print()

        if self.should_run("shared"):
            if self.mode == "verify":
                self.results.skip("shared probes (--mode verify)")
            else:
                self.phase_shared()

        if self.should_run("parents") or self.mode == "verify":
            self.phase_parents()

        if self.should_run("levels") or self.mode == "verify":
            self.phase_levels()

        r = self.results
        print()
        print(f"=== Results: {r.passed} passed, {r.failed} failed, {r.skipped} skipped ===")
        if r.failed:
            print("Some assertions failed — see FAIL lines above.", file=sys.stderr)
            return 1
        return 0


def run_e2e(probe_env: ProbeEnv, *, mode: str = "all", seed_first: bool = False) -> int:
    valid = {"all", "shared", "parents", "levels", "verify"}
    if mode not in valid:
        sys.exit(f"ERROR: invalid mode {mode!r}; expected one of {sorted(valid)}")
    return E2ERunner(probe_env, mode=mode, seed_first=seed_first).run()
