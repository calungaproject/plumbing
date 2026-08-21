"""Assess step: npm pack + assess-npm-compliance (npm-builder image script)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .env import (
    ProbeEnv,
    ensure_modern_bash,
    require_commands,
    validate_npm_name,
    validate_npm_version,
)
from .runner import run_pipeline_script


@dataclass
class AssessResult:
    workdir: Path
    tgz: Path
    sidecar: Path
    name: str
    version: str
    level: str


def assess_package(
    probe_env: ProbeEnv,
    name: str,
    version: str,
    *,
    workdir: Path | None = None,
    tgz: Path | None = None,
) -> AssessResult:
    require_commands("jq", "tar", "npm")
    ensure_modern_bash(probe_env)
    assess_script = probe_env.script_path("npm-builder", "scripts", "assess-npm-compliance")
    if not assess_script.is_file():
        sys.exit(f"ERROR: assess script not found: {assess_script}")

    cleanup = workdir is None
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="npm-closure-probe."))
    artifact_dir = workdir / "artifact"
    source_dir = workdir / "source"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "packages").mkdir(parents=True, exist_ok=True)

    if tgz is None:
        safe_name = validate_npm_name(name)
        safe_version = validate_npm_version(version)
        print(f"Downloading {safe_name}@{safe_version} from {probe_env.upstream_registry}...")
        subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use
            [
                "npm",
                "pack",
                f"{safe_name}@{safe_version}",
                "--registry",
                probe_env.upstream_registry,
            ],
            cwd=artifact_dir,
            check=True,
        )
        matches = list(artifact_dir.glob("*.tgz"))
        if len(matches) != 1:
            sys.exit(f"ERROR: expected one .tgz in {artifact_dir}, got {len(matches)}")
        tgz = matches[0]
    else:
        tgz = Path(tgz)
        if not tgz.is_file():
            sys.exit(f"ERROR: tarball not found: {tgz}")
        shutil.copy2(tgz, artifact_dir / tgz.name)
        tgz = artifact_dir / tgz.name

    with tarfile.open(tgz, "r:gz") as tf:
        pkg_json = json.loads(tf.extractfile("package/package.json").read().decode())
    pkg_name = pkg_json.get("name") or ""
    pkg_version = pkg_json.get("version") or ""
    if not pkg_name or not pkg_version:
        sys.exit("ERROR: tarball missing name/version")

    manifest_dir = source_dir / "packages" / pkg_name / pkg_version
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": pkg_name,
        "version": pkg_version,
        "source": {"url": probe_env.upstream_registry + "/", "ref": "probe-upstream"},
        "outputs": [{"type": "npm-package", "pulp_name": pkg_name}],
    }
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    pkg_rel = f"packages/{pkg_name}/{pkg_version}"
    env = probe_env.as_subprocess_env()
    print("=== Step 1: assess (assess-npm-compliance) ===")
    run_pipeline_script(
        probe_env,
        assess_script,
        str(artifact_dir),
        str(source_dir),
        pkg_rel,
    )

    sidecar = Path(str(tgz).replace(".tgz", ".tl-compliance.json"))
    if not sidecar.is_file():
        sys.exit(f"ERROR: assess did not write {sidecar}")

    doc = json.loads(sidecar.read_text())
    level = doc.get("compliance_level") or ""
    print(f"Package: {pkg_name}@{pkg_version} assessed → {level}")
    print(f"  tgz:     {tgz}")
    print(f"  sidecar: {sidecar}")
    if cleanup:
        print(f"WORKDIR={workdir}  (set KEEP_WORKDIR=1 to preserve)")
    return AssessResult(workdir, tgz, sidecar, pkg_name, pkg_version, level)
