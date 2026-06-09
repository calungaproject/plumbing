#!/usr/bin/env bash
# Install pinned rust-toolset RPMs from UBI AppStream (no rust-lang.org).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_FILE="${RUST_TOOLSET_LOCK:-${SCRIPT_DIR}/../rust-toolset.lock}"

if [[ -f "${LOCK_FILE}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${LOCK_FILE}"
    set +a
fi

RUST_VERSION="${RUST_VERSION:?RUST_VERSION required (set in ${LOCK_FILE})}"
RUST_VR="${RUST_VR:?RUST_VR required (set in ${LOCK_FILE})}"

# rust-toolset is a rolling AppStream module (not nodejs:20-style version streams).
# Pin by exact RPM version-release (epoch is always none on UBI rust-toolset).
dnf -y module enable rust-toolset

dnf -y install \
    --setopt install_weak_deps=0 \
    "rust-toolset-${RUST_VR}" \
    "rust-${RUST_VR}" \
    "cargo-${RUST_VR}" \
    "rust-std-static-${RUST_VR}"

if ! rustc --version | grep -Fq "${RUST_VERSION}"; then
    echo "rustc version mismatch: expected ${RUST_VERSION}" >&2
    rustc --version >&2 || true
    exit 1
fi

# Prevent accidental upgrades when the rolling module moves (e.g. 1.84 → 1.88).
dnf -y install dnf-plugin-versionlock
dnf versionlock add \
    "rust-toolset-${RUST_VR}" \
    "rust-${RUST_VR}" \
    "cargo-${RUST_VR}" \
    "rust-std-static-${RUST_VR}"

echo "Installed and locked rust-toolset ${RUST_VERSION} (${RUST_VR})"
rustc --version
cargo --version
