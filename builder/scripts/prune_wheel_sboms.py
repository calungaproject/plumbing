#!/usr/bin/env python3
"""Keep only the curated Red Hat SPDX file in a wheel's SBOM directory."""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
import zipfile
from io import StringIO
from pathlib import Path

SBOM_MARKER = ".dist-info/sboms/"
RECORD_SUFFIX = ".dist-info/RECORD"


class PruneWheelSbomError(ValueError):
    """Raised when a wheel cannot be safely pruned."""


def prune_wheel_sboms(path):
    if not path.is_file():
        raise PruneWheelSbomError(f"wheel does not exist: {path}")
    with zipfile.ZipFile(path) as src:
        infos = src.infolist()
        names = [i.filename for i in infos]
        sboms = [n for n in names if SBOM_MARKER in n and not n.endswith("/")]
        allowed_suffix = SBOM_MARKER + "redhat.spdx.json"
        remove = {n for n in sboms if not n.endswith(allowed_suffix)}
        if not remove:
            return []
        records = [n for n in names if n.endswith(RECORD_SUFFIX)]
        if len(records) != 1:
            raise PruneWheelSbomError(
                f"expected one wheel RECORD, found {len(records)}"
            )
        sig = [
            n
            for n in names
            if n.endswith((".dist-info/RECORD.jws", ".dist-info/RECORD.p7s"))
        ]
        if sig:
            raise PruneWheelSbomError(
                "cannot update signed wheel RECORD: " + ", ".join(sig)
            )
        try:
            rows = list(csv.reader(StringIO(src.read(records[0]).decode(), newline="")))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise PruneWheelSbomError(f"invalid wheel RECORD: {exc}") from exc
        found = set()
        kept = []
        for row in rows:
            if len(row) != 3:
                raise PruneWheelSbomError("wheel RECORD row has incorrect field count")
            if row[0] in remove:
                found.add(row[0])
            else:
                kept.append(row)
        missing = remove - found
        if missing:
            raise PruneWheelSbomError(
                "RECORD missing removed SBOM entries: " + ", ".join(sorted(missing))
            )
        out = StringIO(newline="")
        csv.writer(out, lineterminator="\n").writerows(kept)
        record = out.getvalue().encode()
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with zipfile.ZipFile(tmp_path, "w") as dst:
                for info in infos:
                    if info.filename not in remove:
                        dst.writestr(
                            info,
                            record
                            if info.filename == records[0]
                            else src.read(info.filename),
                        )
            tmp_path.replace(path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
    return sorted(remove)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("wheel", type=Path)
    a = p.parse_args(argv)
    try:
        removed = prune_wheel_sboms(a.wheel)
    except (OSError, zipfile.BadZipFile, PruneWheelSbomError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for member in removed:
        print(f"Removed non-Red-Hat SBOM: {member}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
