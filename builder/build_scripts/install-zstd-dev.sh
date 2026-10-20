#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Reconstruct the zstd development files the published image is missing.
#
# The builder image source-builds zstd (build-zstd.sh) and ships its runtime
# library under /opt/_internal/zstd-1, but the published image contains only
# the /manylinux-rootfs trees: the headers and pkg-config file were cleaned
# from the runtime and the /manylinux-buildfs tree never reaches the wheel
# build environment. Packages like createrepo_c need pkg-config(libzstd) at
# build time.
#
# This script rebuilds the dev half (headers + .pc pointing at the existing
# runtime library) as a /manylinux-buildfs tree, i.e. exactly what
# `COPY --from=build_zstd /manylinux-buildfs /` in merged_buildfs would give.
# When that Containerfile fix lands, this script becomes unnecessary.
check_var "${ZSTD_VERSION}"
check_var "${ZSTD_HASH}"
check_var "${ZSTD_DOWNLOAD_URL}"
ZSTD_ROOT="zstd-${ZSTD_VERSION}"

# Keep the prefix in sync with build-zstd.sh: /opt/_internal/zstd-<major>
PREFIX=/opt/_internal/zstd-${ZSTD_VERSION%%.*}

fetch_source "${ZSTD_ROOT}.tar.gz" "${ZSTD_DOWNLOAD_URL}/v${ZSTD_VERSION}"
check_sha256sum "${ZSTD_ROOT}.tar.gz" "${ZSTD_HASH}"
tar xfz "${ZSTD_ROOT}.tar.gz"

# The runtime library is already in the image; only take the headers from the
# matching source tarball.
mkdir -p "/manylinux-buildfs${PREFIX}/include" \
         "/manylinux-buildfs${PREFIX}/lib/pkgconfig" \
         /manylinux-buildfs/usr/local/lib/pkgconfig
install -m 0644 "${ZSTD_ROOT}/lib/zstd.h" "${ZSTD_ROOT}/lib/zstd_errors.h" \
    "${ZSTD_ROOT}/lib/zdict.h" "/manylinux-buildfs${PREFIX}/include/"

# libzstd.pc as build-zstd.sh would have installed it (including the rpath it
# adds to Libs)
cat > "/manylinux-buildfs${PREFIX}/lib/pkgconfig/libzstd.pc" <<EOF
prefix=${PREFIX}
libdir=\${prefix}/lib
includedir=\${prefix}/include

Name: zstd
Description: Zstandard compression library
Version: ${ZSTD_VERSION}
Cflags: -I\${includedir}
Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} -L\${libdir} -lzstd
EOF

ln -s "${PREFIX}/lib/pkgconfig/libzstd.pc" \
    /manylinux-buildfs/usr/local/lib/pkgconfig/libzstd.pc

rm -rf "${ZSTD_ROOT}" "${ZSTD_ROOT}.tar.gz"
