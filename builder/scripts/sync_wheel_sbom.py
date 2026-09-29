#!/usr/bin/env python3
"""Synchronize the built-wheel package identity in its Red Hat SPDX SBOM."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import sys
import tempfile
import zipfile
from io import StringIO
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

WHEEL_ID = "SPDXRef-wheel"
UPSTREAM_ID = "SPDXRef-upstream"
SBOM_SUFFIX = ".dist-info/sboms/redhat.spdx.json"
RECORD_SUFFIX = ".dist-info/RECORD"


class SyncWheelSbomError(ValueError):
    """Raised when the wheel's Red Hat SPDX metadata is not safe to update."""


def _single(names, suffix, label):
    matches = [name for name in names if name.endswith(suffix)]
    if len(matches) != 1:
        raise SyncWheelSbomError(f"expected exactly one {label}, found {len(matches)}")
    return matches[0]


def _update_purl(purl, computed_version, wheel_filename):
    parts = urlsplit(purl)
    if (
        parts.scheme != "pkg"
        or not parts.path.startswith("pypi/")
        or "@" not in parts.path
    ):
        raise SyncWheelSbomError(f"invalid PyPI PURL: {purl}")
    name, _version = parts.path.rsplit("@", 1)
    qualifiers, file_name_added = [], False
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "download_url":
            continue
        if key == "file_name":
            if not file_name_added:
                qualifiers.append((key, wheel_filename))
                file_name_added = True
            continue
        qualifiers.append((key, value))
    if not file_name_added:
        qualifiers.append(("file_name", wheel_filename))
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            f"{name}@{quote(computed_version, safe='')}",
            urlencode(qualifiers, quote_via=quote, safe=""),
            parts.fragment,
        )
    )


def _sync_spdx(data, version, filename):
    try:
        doc = json.loads(data)
    except json.JSONDecodeError as exc:
        raise SyncWheelSbomError(f"invalid SPDX JSON: {exc}") from exc
    packages = doc.get("packages") if isinstance(doc, dict) else None
    if not isinstance(packages, list):
        raise SyncWheelSbomError("SPDX document has no packages list")
    ids = {p.get("SPDXID"): p for p in packages if isinstance(p, dict)}
    wheel, upstream = ids.get(WHEEL_ID), ids.get(UPSTREAM_ID)
    if wheel is None or upstream is None:
        raise SyncWheelSbomError(
            "SPDX document must contain SPDXRef-wheel and SPDXRef-upstream"
        )
    refs = [
        r
        for r in wheel.get("externalRefs", [])
        if isinstance(r, dict)
        and r.get("referenceType") == "purl"
        and str(r.get("referenceLocator", "")).startswith("pkg:pypi/")
    ]
    if len(refs) != 1:
        raise SyncWheelSbomError(f"expected one wheel PyPI PURL, found {len(refs)}")
    wheel["versionInfo"] = version
    refs[0]["referenceLocator"] = _update_purl(
        refs[0]["referenceLocator"], version, filename
    )
    return (json.dumps(doc, indent=2) + "\n").encode()


def _record(record, member, content):
    try:
        rows = list(csv.reader(StringIO(record.decode(), newline="")))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise SyncWheelSbomError(f"invalid wheel RECORD: {exc}") from exc
    digest = (
        base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
    )
    for row in rows:
        if len(row) != 3:
            raise SyncWheelSbomError("wheel RECORD row has incorrect field count")
        if row[0] == member:
            row[1], row[2] = "sha256=" + digest, str(len(content))
            break
    else:
        raise SyncWheelSbomError(f"RECORD is missing entry for {member}")
    out = StringIO(newline="")
    csv.writer(out, lineterminator="\n").writerows(rows)
    return out.getvalue().encode()


def sync_wheel_sbom(path, version):
    with zipfile.ZipFile(path) as src:
        names = [i.filename for i in src.infolist()]
        sbom = _single(names, SBOM_SUFFIX, "Red Hat SPDX SBOM")
        rec = _single(names, RECORD_SUFFIX, "RECORD")
        sig = [
            n
            for n in names
            if n.endswith((".dist-info/RECORD.jws", ".dist-info/RECORD.p7s"))
        ]
        if sig:
            raise SyncWheelSbomError(
                "cannot update signed wheel RECORD: " + ", ".join(sig)
            )
        changed = _sync_spdx(src.read(sbom), version, path.name)
        changed_record = _record(src.read(rec), sbom, changed)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with zipfile.ZipFile(tmp_path, "w") as dst:
                for info in src.infolist():
                    dst.writestr(
                        info,
                        changed
                        if info.filename == sbom
                        else changed_record
                        if info.filename == rec
                        else src.read(info.filename),
                    )
            tmp_path.replace(path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("wheel", type=Path)
    p.add_argument("version")
    a = p.parse_args(argv)
    try:
        sync_wheel_sbom(a.wheel, a.version)
    except (OSError, zipfile.BadZipFile, SyncWheelSbomError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
