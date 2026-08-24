"""Closure publish/update via production utils scripts."""

from __future__ import annotations

import sys
from pathlib import Path

from .env import ProbeEnv
from .runner import run, run_pipeline_script


def seed_catalog(probe_env: ProbeEnv, *, init_index: bool = False) -> None:
    probe_env.require_pulp_creds()
    probe_env.require_compliance_prefix()
    probe_env.assert_npm_repository()
    script = probe_env.script_path("utils", "scripts", "update-npm-closure")
    args = ["seed"]
    if init_index:
        args.append("--init-index")
    print(
        f"Pulp scope: domain={probe_env.pulp_domain} "
        f"repository={probe_env.pulp_repository}"
    )
    print(f"Compliance prefix: {probe_env.compliance_image_prefix}")
    print(f"Closure index:     {probe_env.closure_index_image}")
    run_pipeline_script(probe_env, script, *args)


def rebalance_index(probe_env: ProbeEnv, *, index_only: bool = False) -> None:
    probe_env.require_pulp_creds()
    probe_env.require_compliance_prefix()
    script = probe_env.script_path("utils", "scripts", "update-npm-closure")
    args = ["rebalance"]
    if index_only:
        args.append("--index-only")
    run_pipeline_script(probe_env, script, *args)


def     publish_closure_update(
    probe_env: ProbeEnv,
    sidecar: Path,
    pulp_href: str,
) -> None:
    """Release-path closure update (npm-release-closure-update → update-npm-closure update)."""
    probe_env.require_pulp_creds()
    probe_env.require_compliance_prefix()
    release_script = probe_env.script_path(
        "utils", "scripts", "npm-release-closure-update"
    )
    update_script = probe_env.script_path("utils", "scripts", "update-npm-closure")
    if release_script.is_file():
        extra_env = {"SIDECAR_PATH": str(sidecar)}
        if pulp_href:
            extra_env["PULP_CONTENT_HREF"] = pulp_href
        print()
        print("=== Step 4: publish (npm-release-closure-update) ===")
        run_pipeline_script(probe_env, release_script, extra_env=extra_env)
        return
    if not update_script.is_file():
        sys.exit("ERROR: update-npm-closure not found in utils/scripts")
    print()
    print("=== Step 4: publish (update-npm-closure update) ===")
    args = ["update", "--sidecar", str(sidecar)]
    if pulp_href:
        args.extend(["--pulp-href", pulp_href])
    run_pipeline_script(probe_env, update_script, *args)
