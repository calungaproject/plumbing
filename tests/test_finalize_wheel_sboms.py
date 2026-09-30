#!/usr/bin/env python3
"""Focused tests for generic package-wheel SPDX finalization."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.machinery
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "builder/scripts"))
_finalize_path = (
    Path(__file__).resolve().parents[1] / "builder/scripts/finalize-wheel-sboms"
)
_finalize_spec = importlib.util.spec_from_file_location(
    "finalize_wheel_sboms",
    _finalize_path,
    loader=importlib.machinery.SourceFileLoader(
        "finalize_wheel_sboms", str(_finalize_path)
    ),
)
_finalize_module = importlib.util.module_from_spec(_finalize_spec)
sys.modules[_finalize_spec.name] = _finalize_module
_finalize_spec.loader.exec_module(_finalize_module)
FinalizeWheelSbomsError = _finalize_module.FinalizeWheelSbomsError
finalize_wheels = _finalize_module.finalize_wheels


def _digest(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(
        hashlib.sha256(data).digest()
    ).decode().rstrip("=")


def _record(rows: list[list[str]]) -> bytes:
    output = StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    return output.getvalue().encode()


def _write_wheel(
    path: Path,
    package: str,
    version: str,
    extra_sbom: str | None = None,
    extra_metadata: tuple[str, bytes] | None = None,
) -> tuple[str, str]:
    dist_info = f"{package}-{version}.dist-info"
    metadata_path = f"{dist_info}/METADATA"
    module_path = f"{package.replace('-', '_')}/__init__.py"
    sbom_path = f"{dist_info}/sboms/redhat.spdx.json"
    record_path = f"{dist_info}/RECORD"
    upstream_version = version.split("+", 1)[0]
    members = {
        metadata_path: f"Metadata-Version: 2.1\nName: {package}\nVersion: {version}\n".encode(),
        module_path: b"VALUE = 1\n",
        sbom_path: json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "packages": [
                    {
                        "SPDXID": "SPDXRef-wheel",
                        "name": package,
                        "versionInfo": upstream_version,
                        "externalRefs": [
                            {
                                "referenceCategory": "PACKAGE-MANAGER",
                                "referenceType": "purl",
                                "referenceLocator": f"pkg:pypi/{package}@{upstream_version}?file_name={package}-{upstream_version}.whl&download_url=https%3A%2F%2Fsource.example%2Fwheel.whl",
                            }
                        ],
                    },
                    {
                        "SPDXID": "SPDXRef-upstream",
                        "name": package,
                        "versionInfo": upstream_version,
                        "externalRefs": [
                            {
                                "referenceCategory": "PACKAGE-MANAGER",
                                "referenceType": "purl",
                                "referenceLocator": f"pkg:pypi/{package}@{upstream_version}",
                            }
                        ],
                    },
                ],
            }
        ).encode(),
    }
    if extra_sbom:
        members[f"{dist_info}/sboms/{extra_sbom}"] = b'{"bomFormat":"CycloneDX"}'
    if extra_metadata:
        members[extra_metadata[0]] = extra_metadata[1]
    rows = [[name, _digest(data), str(len(data))] for name, data in members.items()]
    rows.append([record_path, "", ""])
    members[record_path] = _record(rows)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return sbom_path, record_path


class WheelSbomTests(unittest.TestCase):
    def test_version_sync_applies_to_all_primary_tags_only(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            primary = []
            for tag in ("py3-none-any", "cp312-cp312-manylinux_x86_64"):
                wheel = directory / f"demo_pkg-1.0+vendor.1-{tag}.whl"
                sbom, record = _write_wheel(
                    wheel, "demo-pkg", "1.0+vendor.1", "virtualenv.cdx.json"
                )
                wheel.chmod(0o440)
                primary.append((wheel, sbom, record))
            finalized = finalize_wheels("demo-pkg", "1.0+vendor.1", directory)

            self.assertEqual(
                set(finalized), {wheel for wheel, _sbom, _record in primary}
            )
            for wheel, sbom_path, record_path in primary:
                with zipfile.ZipFile(wheel) as archive:
                    names = archive.namelist()
                    self.assertIn(sbom_path, names)
                    doc = json.loads(archive.read(sbom_path))
                    rows = list(
                        csv.reader(StringIO(archive.read(record_path).decode()))
                    )
                    sbom_bytes = archive.read(sbom_path)
                packages = {pkg["SPDXID"]: pkg for pkg in doc["packages"]}
                self.assertEqual(
                    packages["SPDXRef-wheel"]["versionInfo"], "1.0+vendor.1"
                )
                purl = packages["SPDXRef-wheel"]["externalRefs"][0]["referenceLocator"]
                from urllib.parse import quote

                self.assertIn(
                    "@1.0%2Bvendor.1?file_name=" + quote(wheel.name, safe=""), purl
                )
                self.assertNotIn("download_url=", purl)
                self.assertEqual(wheel.stat().st_mode & 0o777, 0o440)
                self.assertEqual(packages["SPDXRef-upstream"]["versionInfo"], "1.0")
                self.assertFalse(
                    any("virtualenv.cdx.json" in name for name in archive.namelist())
                )
                record = {row[0]: row for row in rows}
                self.assertEqual(
                    record[sbom_path][1:], [_digest(sbom_bytes), str(len(sbom_bytes))]
                )

    def test_dependency_wheel_with_multiple_metadata_files_is_not_inspected(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            primary = directory / "demo_pkg-1.0+vendor.1-py3-none-any.whl"
            _write_wheel(primary, "demo-pkg", "1.0+vendor.1")

            dependency = directory / "flit_core-3.12.0-0-py3-none-any.whl"
            _write_wheel(
                dependency,
                "flit_core",
                "3.12.0",
                extra_metadata=(
                    "legacy.dist-info/METADATA",
                    b"Metadata-Version: 2.1\nName: legacy\nVersion: 1.0\n",
                ),
            )
            dependency_before = dependency.read_bytes()

            self.assertEqual(
                finalize_wheels("demo-pkg", "1.0+vendor.1", directory),
                (primary,),
            )
            self.assertEqual(dependency.read_bytes(), dependency_before)

    def test_missing_or_ambiguous_primary_wheel_fails(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            _write_wheel(directory / "demo-pkg-1.0-py3-none-any.whl", "demo-pkg", "1.0")
            with self.assertRaises(FinalizeWheelSbomsError):
                finalize_wheels("demo-pkg", "1.0+vendor.1", directory)
            _write_wheel(
                directory / "demo_pkg-1.0+vendor.1-py3-none-any.whl",
                "demo-pkg",
                "1.0+vendor.1",
            )
            _write_wheel(
                directory / "demo_pkg-1.0+vendor.1-cp312-cp312-manylinux_x86_64.whl",
                "demo-pkg",
                "1.0+vendor.1",
            )
            self.assertEqual(
                len(finalize_wheels("demo-pkg", "1.0+vendor.1", directory)), 2
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
