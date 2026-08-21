"""Quay OCI push via oras (snapshot .tgz + compliance sidecar)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .env import ProbeEnv, require_commands
from .runner import run


def _oras_push(image_ref: str, artifact_type: str, src_dir: Path, *files: str) -> None:
    cmd = ["oras", "push", image_ref, "--artifact-type", artifact_type, *files]
    retry = shutil.which("retry")
    if retry:
        cmd = [retry, *cmd]
    run(cmd, cwd=src_dir, check=True)


def _oras_resolve(image_ref: str) -> str:
    proc = subprocess.run(
        ["oras", "resolve", image_ref],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def push_oci_artifacts(
    probe_env: ProbeEnv,
    name: str,
    version: str,
    tgz: Path,
    sidecar: Path,
    workdir: Path,
    *,
    snapshot_image: str | None = None,
    compliance_image: str | None = None,
) -> None:
    require_commands("oras")
    probe_env.require_compliance_prefix()
    snapshot_ref = snapshot_image or probe_env.snapshot_image_for(name, version)
    compliance_ref = compliance_image or probe_env.compliance_image_for(name, version)

    snapshot_name = tgz.name
    compliance_name = sidecar.name

    print()
    print("=== Step 3a: Quay OCI snapshot (package .tgz only) ===")
    snapshot_dir = workdir / "oci-snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tgz, snapshot_dir / snapshot_name)
    _oras_push(snapshot_ref, probe_env.snapshot_artifact_type, snapshot_dir, snapshot_name)
    print(f"Snapshot: {_oras_resolve(snapshot_ref)}")

    print()
    print("=== Step 3b: Quay OCI compliance artifact (*.tl-compliance.json) ===")
    print(f"  ref: {compliance_ref}")
    compliance_dir = workdir / "oci-compliance"
    compliance_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sidecar, compliance_dir / compliance_name)
    _oras_push(
        compliance_ref,
        probe_env.compliance_artifact_type,
        compliance_dir,
        compliance_name,
    )
    print(f"Compliance: {_oras_resolve(compliance_ref)}")
