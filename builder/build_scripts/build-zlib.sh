#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent zlib
check_var "${ZLIB_VERSION}"
check_var "${ZLIB_HASH}"
check_var "${ZLIB_DOWNLOAD_URL}"
ZLIB_ROOT="zlib-${ZLIB_VERSION}"

PREFIX=/opt/_internal/zlib-${ZLIB_VERSION%.*}

fetch_source "${ZLIB_ROOT}.tar.gz" "${ZLIB_DOWNLOAD_URL}"
check_sha256sum "${ZLIB_ROOT}.tar.gz" "${ZLIB_HASH}"
tar xfz "${ZLIB_ROOT}.tar.gz"
pushd "${ZLIB_ROOT}"

# Configure and build
CFLAGS="${MANYLINUX_CFLAGS}" \
LDFLAGS="${MANYLINUX_LDFLAGS}" \
./configure --prefix="${PREFIX}" > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${ZLIB_ROOT}" "${ZLIB_ROOT}.tar.gz"

# Add rpath to pkgconfig
if [ -f /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/zlib.pc ]; then
    sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/zlib.pc
fi

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlink for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
if [ -f "${PREFIX}/lib/pkgconfig/zlib.pc" ]; then
    ln -s "${PREFIX}/lib/pkgconfig/zlib.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/zlib.pc
fi

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig /manylinux-rootfs"${PREFIX}"/include
rm -rf /manylinux-rootfs"${PREFIX}"/share/man
