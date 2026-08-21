"""CLI for local npm closure probes."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .add import add_package
from .assess import assess_package
from .e2e import run_e2e
from .env import ProbeEnv
from .publish import rebalance_index, seed_catalog
from .verify import verify_compliance, verify_index, verify_index_all

ENV_HELP = """
Environment (required prefixes are never defaulted):

  export PULP_USERNAME='...'
  export PULP_PASSWORD='...'
  export COMPLIANCE_IMAGE_PREFIX='quay.io/<org>/npm-compliance'
  export SNAPSHOT_IMAGE_PREFIX='quay.io/<org>/npm-snapshot'   # add / e2e OCI steps

Optional:
  CLOSURE_INDEX_IMAGE   default: ${COMPLIANCE_IMAGE_PREFIX}/npm-closure-index:latest
  NPM_PROBE_BASH        optional explicit bash 4+ (e.g. /opt/homebrew/bin/bash)
  TL_REGISTRY_TIMEOUT   registry HTTP timeout seconds (default 60)
  TL_REGISTRY_RETRIES   retries on 5xx/timeout (default 5)
  PULP_* / TL_NPM_REGISTRY_URL / UPSTREAM_REGISTRY

macOS: brew install bash coreutils (assess + npm-pulp-upload need bash 4+ / GNU readlink)

Pipeline scripts invoked:
  assess   → npm-builder/scripts/assess-npm-compliance
  publish  → utils/scripts/npm-pulp-upload, oras, npm-release-closure-update
  rebalance → utils/scripts/update-npm-closure rebalance
  seed     → utils/scripts/update-npm-closure seed
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="npm-closure-probe",
        description="Local npm TL closure probe (assess → Pulp → Quay → closure update).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=ENV_HELP.strip(),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser(
        "add",
        help="Add one package from upstream npm (assess → publish → closure update)",
    )
    add_p.add_argument("name", help="Package name")
    add_p.add_argument("version", help="Exact version")
    add_p.add_argument("--skip-pulp", action="store_true")
    add_p.add_argument("--skip-oci", action="store_true")
    add_p.add_argument("--skip-closure", action="store_true")
    add_p.add_argument("--seed-first", action="store_true")
    add_p.add_argument("--snapshot-image", default="")
    add_p.add_argument("--compliance-image", default="")

    seed_p = sub.add_parser(
        "seed",
        help="Bootstrap missing compliance OCI from Pulp catalog",
    )
    seed_p.add_argument("--init-index", action="store_true")

    reb_p = sub.add_parser(
        "rebalance",
        help="Rebuild closure index and/or gap lists (update-npm-closure rebalance)",
    )
    reb_p.add_argument("--index-only", action="store_true")

    e2e_p = sub.add_parser(
        "e2e",
        help="Parent + level propagation E2E scenario",
    )
    e2e_p.add_argument(
        "--mode",
        default="all",
        choices=["all", "shared", "parents", "levels", "verify"],
    )
    e2e_p.add_argument("--seed-first", action="store_true")

    assess_p = sub.add_parser(
        "assess",
        help="Assess only (assess-npm-compliance; no Quay prefixes required)",
    )
    assess_p.add_argument("name")
    assess_p.add_argument("version")

    verify_p = sub.add_parser(
        "verify",
        help="Inspect compliance OCI or closure index after manual add steps",
    )
    verify_sub = verify_p.add_subparsers(dest="verify_command", required=True)

    vc_p = verify_sub.add_parser("compliance", help="Pull and show *.tl-compliance.json")
    vc_p.add_argument("name")
    vc_p.add_argument("version")

    vi_p = verify_sub.add_parser("index", help="Show index entry for a blocker key")
    vi_p.add_argument(
        "blocker_key",
        help="Gap key, e.g. escape-html@~1.0.3",
    )
    vi_p.add_argument(
        "--expect-parent",
        action="append",
        default=[],
        metavar="PKG@VER",
        help="Assert parent appears in index (repeatable)",
    )

    via_p = verify_sub.add_parser("index-all", help="List all index entries")
    via_p.add_argument(
        "--parent",
        default="",
        help="Only show entries listing this parent key",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    probe_env = ProbeEnv.from_environ()

    if args.command == "add":
        add_package(
            probe_env,
            args.name,
            args.version,
            skip_pulp=args.skip_pulp,
            skip_oci=args.skip_oci,
            skip_closure=args.skip_closure,
            seed_first=args.seed_first,
            snapshot_image=args.snapshot_image or None,
            compliance_image=args.compliance_image or None,
        )
        return 0

    if args.command == "seed":
        seed_catalog(probe_env, init_index=args.init_index)
        return 0

    if args.command == "rebalance":
        rebalance_index(probe_env, index_only=args.index_only)
        return 0

    if args.command == "e2e":
        return run_e2e(probe_env, mode=args.mode, seed_first=args.seed_first)

    if args.command == "assess":
        assess_package(probe_env, args.name, args.version)
        return 0

    if args.command == "verify":
        if args.verify_command == "compliance":
            return verify_compliance(probe_env, args.name, args.version)
        if args.verify_command == "index":
            expected = args.expect_parent or None
            return verify_index(probe_env, args.blocker_key, expected)
        if args.verify_command == "index-all":
            return verify_index_all(probe_env, parent_filter=args.parent)
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
