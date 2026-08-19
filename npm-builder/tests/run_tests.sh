#!/usr/bin/env bash
# Unit tests for npm-builder compliance helpers.
# Run from repo:  ./npm-builder/tests/run_tests.sh
# Or via Containerfile test stage.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# assess-npm-compliance needs bash 4+ (mapfile) and GNU sha256sum.
for b in /opt/homebrew/bin/bash /usr/local/bin/bash; do
    if [[ -x "${b}" ]]; then
        export PATH="$(dirname "${b}"):${PATH}"
        break
    fi
done
for p in /opt/homebrew/opt/coreutils/libexec/gnubin /usr/local/opt/coreutils/libexec/gnubin; do
    if [[ -x "${p}/sha256sum" ]]; then
        export PATH="${p}:${PATH}"
        break
    fi
done

python3 "${ROOT}/test_lookup_npm_tl_compliance.py" -v
bash "${ROOT}/test_assess_npm_compliance.sh"
