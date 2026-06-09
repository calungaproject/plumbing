#!/usr/bin/env bash
# Refresh rust-toolset.lock from UBI AppStream (linux/amd64).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="${ROOT_DIR}/rust-toolset.lock"
BASEIMAGE_LOCK="${ROOT_DIR}/baseimage.lock"
PLATFORM="${PLATFORM:-linux/amd64}"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-docker}"

if [[ -f "${BASEIMAGE_LOCK}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${BASEIMAGE_LOCK}"
    set +a
fi
BASEIMAGE="${BASEIMAGE:?BASEIMAGE required — set in baseimage.lock or env}"

read -r RUST_VERSION RUST_VR < <(
    "${CONTAINER_RUNTIME}" run --rm --platform "${PLATFORM}" "${BASEIMAGE}" bash -c '
        set -euo pipefail
        dnf -y -q module install rust-toolset
        # UBI rust-toolset RPMs use epoch (none); version-release is sufficient for dnf.
        echo "$(rpm -q --qf "%\{VERSION\}" rust) $(rpm -q --qf "%\{VERSION\}-%\{RELEASE\}" rust)"
    '
)

cat > "${LOCK_FILE}" <<EOF
# Single source of truth for pinned rust-toolset RPMs (UBI AppStream only).
# Base image digest: see baseimage.lock (must match Containerfile ARG BASEIMAGE).
#
# To upgrade Rust:
#   1. Ensure baseimage.lock matches Containerfile, then run:
#        hack/update-rust-toolset-lock.sh
#   2. Rebuild the npm-builder image.
RUST_VERSION=${RUST_VERSION}
RUST_VR=${RUST_VR}
EOF

echo "Using BASEIMAGE=${BASEIMAGE} (${CONTAINER_RUNTIME})"
echo "Updated ${LOCK_FILE}:"
grep -E '^RUST_' "${LOCK_FILE}"
