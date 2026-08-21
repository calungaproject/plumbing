"""Pull and print compliance OCI + closure index state."""

from __future__ import annotations

import json
import sys

from .e2e import pull_compliance, pull_index, show_compliance
from .env import ProbeEnv, require_commands


def verify_compliance(probe_env: ProbeEnv, name: str, version: str) -> int:
    require_commands("oras")
    probe_env.require_compliance_prefix()
    show_compliance(probe_env, name, version, "compliance")
    if pull_compliance(probe_env, name, version) is None:
        print("ERROR: compliance OCI not found", file=sys.stderr)
        return 1
    return 0


def verify_index(
    probe_env: ProbeEnv,
    blocker_key: str,
    expected_parents: list[str] | None = None,
) -> int:
    require_commands("oras")
    probe_env.require_compliance_prefix()
    index = pull_index(probe_env)
    if index is None:
        print(
            f"ERROR: closure index not found ({probe_env.closure_index_image})",
            file=sys.stderr,
        )
        return 1
    entry = (index.get("entries") or {}).get(blocker_key)
    if entry is None:
        print(f"blocker: {blocker_key}")
        print("  (no index entry — dependency may already be on TL as L3)")
        if expected_parents:
            print(
                f"ERROR: expected parents {expected_parents!r} but entry is absent",
                file=sys.stderr,
            )
            return 1
        return 0
    parents = entry.get("parents") or []
    print(f"blocker: {blocker_key}")
    print(f"  parents ({len(parents)}): {json.dumps(parents, indent=2)}")
    print(f"  index_revision: {index.get('revision')}")
    if expected_parents is not None:
        missing = sorted(set(expected_parents) - set(parents))
        extra = sorted(set(parents) - set(expected_parents))
        if missing or extra:
            if missing:
                print(f"ERROR: missing expected parents: {missing!r}", file=sys.stderr)
            if extra:
                print(f"ERROR: unexpected parents: {extra!r}", file=sys.stderr)
            return 1
        print(f"PASS: parents match expected {expected_parents!r}")
    return 0


def verify_index_all(probe_env: ProbeEnv, *, parent_filter: str = "") -> int:
    require_commands("oras")
    probe_env.require_compliance_prefix()
    index = pull_index(probe_env)
    if index is None:
        print(
            f"ERROR: closure index not found ({probe_env.closure_index_image})",
            file=sys.stderr,
        )
        return 1
    entries = index.get("entries") or {}
    print(f"index: {probe_env.closure_index_image}")
    print(f"revision: {index.get('revision')}")
    print(f"entries: {len(entries)}")
    for key in sorted(entries):
        parents = entries[key].get("parents") or []
        if parent_filter and parent_filter not in parents:
            continue
        print(f"  {key}: {parents}")
    return 0
