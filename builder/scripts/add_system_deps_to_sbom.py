#!/usr/bin/env python3
"""Inject system library dependencies discovered by auditwheel into Fromager SPDX SBOMs.

Runs `auditwheel show` on a manylinux wheel to discover which system-provided shared
libraries it links against, then adds those as SPDX Package entries with DEPENDS_ON
relationships in the wheel's fromager.spdx.json.

Designed to run *after* auditwheel repair (so the wheel already has its final manylinux
tag and only external system deps remain) and *before* patch-sbom-purl (which renames
the SBOM to redhat.spdx.json and appends PURL qualifiers).
"""
import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Add system library deps from auditwheel show to SPDX SBOMs inside a wheel"
    )
    parser.add_argument("wheel", type=Path, help="Path to the manylinux wheel file")
    return parser.parse_args()


def run_auditwheel_show(wheel_path):
    """Run auditwheel show and return stdout, or None on failure."""
    result = subprocess.run(
        ["auditwheel", "show", str(wheel_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def parse_system_libs(output):
    """Parse auditwheel show output for system library references.

    Returns dict mapping library soname to a sorted list of version symbols,
    e.g. {"libc.so.6": ["GLIBC_2.14", "GLIBC_2.2.5", ...]}
    """
    # Collapse wrapped lines into a single string for regex matching
    text = " ".join(output.split())

    match = re.search(
        r"system-provided shared libraries:\s*(.+?)(?:This constrains|$)",
        text,
    )
    if not match:
        return {}

    libs_text = match.group(1)
    libs = {}
    for m in re.finditer(
        r"(\S+\.so\S*)\s+with\s+versions\s+\{([^}]+)\}", libs_text
    ):
        lib_name = m.group(1)
        versions = sorted(
            v.strip().strip("'\"") for v in m.group(2).split(",")
        )
        libs[lib_name] = versions

    return libs


def sanitize_spdx_id(name):
    """Convert a library soname to a valid SPDX idstring component.

    SPDX 2.3 restricts idstrings to [a-zA-Z0-9.-], so characters like
    underscores and plus signs must be replaced. The result is only used
    for the SPDXID field; the original soname is preserved in the package
    "name" field (e.g. name="libstdc++.so.6" even though the SPDXID uses
    "libstdc--.so.6").
    """
    return re.sub(r"[^a-zA-Z0-9.-]", "-", name)


def find_root_package_id(sbom):
    """Find the SPDXID of the root package described by this SBOM document."""
    for rel in sbom.get("relationships", []):
        if (
            rel.get("relationshipType") == "DESCRIBES"
            and rel.get("spdxElementId") == "SPDXRef-DOCUMENT"
        ):
            return rel.get("relatedSpdxElement")

    describes = sbom.get("documentDescribes", [])
    if describes:
        return describes[0]

    packages = sbom.get("packages", [])
    if packages:
        return packages[0].get("SPDXID")
    return None


def add_system_deps(sbom_data, system_libs):
    """Add SPDX Package entries and DEPENDS_ON relationships for system libraries."""
    sbom = json.loads(sbom_data)

    root_id = find_root_package_id(sbom)
    if not root_id:
        return sbom_data

    # Track existing IDs to guard against duplicates, both from re-running
    # on an already-patched wheel (idempotency) and from the case where two
    # different sonames sanitize to the same SPDX ID.
    existing_ids = {pkg.get("SPDXID") for pkg in sbom.get("packages", [])}
    added = False

    for lib_name, versions in sorted(system_libs.items()):
        spdx_id = f"SPDXRef-SystemLib-{sanitize_spdx_id(lib_name)}"
        if spdx_id in existing_ids:
            continue

        existing_ids.add(spdx_id)
        added = True
        pkg = {
            "SPDXID": spdx_id,
            "name": lib_name,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "primaryPackagePurpose": "LIBRARY",
            "supplier": "NOASSERTION",
        }
        if versions:
            pkg["comment"] = (
                f"System-provided shared library detected by auditwheel. "
                f"Referenced versioned symbols: {', '.join(versions)}"
            )

        sbom.setdefault("packages", []).append(pkg)
        sbom.setdefault("relationships", []).append(
            {
                "spdxElementId": root_id,
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": spdx_id,
            }
        )

    if not added:
        return sbom_data

    return json.dumps(sbom, indent=2).encode()


def update_record(record_data, filename, new_data):
    """Recalculate the RECORD hash for a modified file entry."""
    digest = base64.urlsafe_b64encode(
        hashlib.sha256(new_data).digest()
    ).rstrip(b"=").decode()
    new_entry = f"{filename},sha256={digest},{len(new_data)}"

    lines = record_data.decode().splitlines()
    new_lines = []
    found = False
    for line in lines:
        if line.startswith(filename + ","):
            new_lines.append(new_entry)
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(new_entry)

    return ("\n".join(new_lines) + "\n").encode()


def main():
    args = parse_args()
    whl_path = args.wheel

    with zipfile.ZipFile(whl_path) as zf:
        all_names = zf.namelist()
        sbom_entries = {
            n
            for n in all_names
            if n.endswith(".dist-info/sboms/fromager.spdx.json")
        }
        record_entry = next(
            (n for n in all_names if n.endswith(".dist-info/RECORD")), None
        )

    if not sbom_entries:
        print(f"  No Fromager SBOM found in {whl_path.name}, skipping system deps")
        return

    output = run_auditwheel_show(whl_path)
    if output is None:
        print(f"  auditwheel show failed for {whl_path.name}, skipping system deps")
        return

    system_libs = parse_system_libs(output)
    if not system_libs:
        print(f"  No system library references found in {whl_path.name}")
        return

    lib_names = ", ".join(sorted(system_libs))
    print(f"  Found {len(system_libs)} system libraries in {whl_path.name}: {lib_names}")

    tmp = whl_path.with_suffix(".tmp")
    modified_sboms = {}

    with (
        zipfile.ZipFile(whl_path) as zf_in,
        zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf_out,
    ):
        record_info = None
        for item in zf_in.infolist():
            if item.filename == record_entry:
                record_info = item
                continue

            data = zf_in.read(item.filename)
            if item.filename in sbom_entries:
                data = add_system_deps(data, system_libs)
                modified_sboms[item.filename] = data

            zf_out.writestr(item, data)

        if record_info:
            record_data = zf_in.read(record_info.filename)
            for sbom_name, sbom_data in modified_sboms.items():
                record_data = update_record(record_data, sbom_name, sbom_data)
            zf_out.writestr(record_info, record_data)

    tmp.replace(whl_path)
    print(f"  Added system library dependencies to SBOM in {whl_path.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"  ERROR adding system deps: {e}", file=sys.stderr)
        sys.exit(1)
