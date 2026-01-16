#!/usr/bin/env python3
"""Convert DSSE attestation to PEP 740 format for Pulp compatibility."""

import json
import sys


def convert_dsse_to_pep740(dsse_file: str, output_file: str) -> None:
    """Convert a DSSE attestation file to PEP 740 format.

    Args:
        dsse_file: Path to the input DSSE attestation file.
        output_file: Path to write the PEP 740 formatted output.
    """
    with open(dsse_file) as f:
        dsse = json.load(f)

    # Wrap DSSE in PEP 740 format
    pep740 = {
        "version": 1,
        "verification_material": None,  # None since we use private key signing
        "envelope": {
            "statement": dsse.get("payload", ""),
            "signature": dsse.get("signatures", [{}])[0].get("sig", ""),
        },
    }

    with open(output_file, "w") as f:
        json.dump(pep740, f)

    print(f"Created PEP 740 attestation: {output_file}")


def main() -> int:
    """Main entry point."""

    dsse_file = sys.argv[1]
    output_file = sys.argv[2]

    try:
        convert_dsse_to_pep740(dsse_file, output_file)
        return 0
    except Exception as e:
        print(f"ERROR: Failed to convert attestation: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

