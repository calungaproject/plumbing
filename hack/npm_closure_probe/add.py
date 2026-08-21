"""Add one package: assess → Pulp → OCI → closure publish."""

from __future__ import annotations

import os
from pathlib import Path

from .assess import assess_package
from .env import ProbeEnv, require_commands
from .oci import push_oci_artifacts
from .publish import publish_closure_update, seed_catalog
from .pulp import upload_to_pulp


def add_package(
    probe_env: ProbeEnv,
    name: str,
    version: str,
    *,
    skip_pulp: bool = False,
    skip_oci: bool = False,
    skip_closure: bool = False,
    seed_first: bool = False,
    workdir: Path | None = None,
    snapshot_image: str | None = None,
    compliance_image: str | None = None,
) -> None:
    require_commands("jq", "oras")
    probe_env.assert_npm_repository()
    print(
        f"Pulp scope: domain={probe_env.pulp_domain} "
        f"repository={probe_env.pulp_repository}"
    )

    if not skip_pulp:
        probe_env.require_pulp_creds()
    if seed_first or not skip_closure:
        probe_env.require_compliance_prefix()
    if not skip_oci:
        probe_env.require_compliance_prefix()
        if not snapshot_image:
            probe_env.require_snapshot_prefix()

    result = assess_package(probe_env, name, version, workdir=workdir)

    pulp_href = ""
    if not skip_pulp:
        pulp_href = upload_to_pulp(probe_env, result.tgz, result.sidecar, result.level)

    if not skip_oci:
        push_oci_artifacts(
            probe_env,
            result.name,
            result.version,
            result.tgz,
            result.sidecar,
            result.workdir,
            snapshot_image=snapshot_image,
            compliance_image=compliance_image,
        )

    if not skip_closure:
        if seed_first:
            print()
            print("=== Step 4a: seed compliance OCI + init closure index ===")
            seed_catalog(probe_env, init_index=True)
        publish_closure_update(probe_env, result.sidecar, pulp_href)

    print()
    print("=== done ===")
    if os.environ.get("KEEP_WORKDIR") == "1":
        print(f"WORKDIR={result.workdir}")
