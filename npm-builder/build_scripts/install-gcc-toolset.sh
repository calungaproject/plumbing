#!/usr/bin/env bash
# Install gcc-toolset for node-gyp / Tier C native builds (C++20 on UBI 8).
# Keeps UBI 8 glibc for published .node runtime; only the compiler is newer.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${GCC_TOOLSET_LOCK:-}" ]]; then
    LOCK_FILE="${GCC_TOOLSET_LOCK}"
elif [[ -f "${SCRIPT_DIR}/gcc-toolset.lock" ]]; then
    LOCK_FILE="${SCRIPT_DIR}/gcc-toolset.lock"
else
    LOCK_FILE="${SCRIPT_DIR}/../gcc-toolset.lock"
fi

if [[ -f "${LOCK_FILE}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${LOCK_FILE}"
    set +a
fi

GCC_TOOLSET="${GCC_TOOLSET:-14}"
GCC_TOOLSET_ROOT="/opt/rh/gcc-toolset-${GCC_TOOLSET}/root"
GXX="${GCC_TOOLSET_ROOT}/usr/bin/g++"
GCC="${GCC_TOOLSET_ROOT}/usr/bin/gcc"

dnf -y install dnf-plugins-core
dnf config-manager --set-enabled ubi-8-codeready-builder-rpms 2>/dev/null || \
    dnf config-manager --set-enabled codeready-builder-for-rhel-8-*-rpms 2>/dev/null || \
    dnf config-manager --set-enabled powertools 2>/dev/null || true

dnf -y install \
    --setopt install_weak_deps=0 \
    "gcc-toolset-${GCC_TOOLSET}-binutils" \
    "gcc-toolset-${GCC_TOOLSET}-gcc" \
    "gcc-toolset-${GCC_TOOLSET}-gcc-c++" \
    "gcc-toolset-${GCC_TOOLSET}-libatomic-devel"

[[ -x "${GXX}" ]] || {
    echo "Missing ${GXX}" >&2
    exit 1
}

# Verify C++20 (required by better-sqlite3 >= 11.2 and similar node-gyp addons).
cat >/tmp/npm-builder-cxx20-test.cpp <<'EOF'
#include <version>
int main() { return __cplusplus >= 202002L ? 0 : 1; }
EOF
"${GXX}" -std=c++20 -o /tmp/npm-builder-cxx20-test /tmp/npm-builder-cxx20-test.cpp
/tmp/npm-builder-cxx20-test
rm -f /tmp/npm-builder-cxx20-test /tmp/npm-builder-cxx20-test.cpp

echo "Installed gcc-toolset-${GCC_TOOLSET} for npm-builder (C++20 OK)"
"${GCC}" --version | head -1
"${GXX}" --version | head -1
