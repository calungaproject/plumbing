#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent libpng
check_var "${LIBPNG_VERSION}"
check_var "${LIBPNG_HASH}"
check_var "${LIBPNG_DOWNLOAD_URL}"
LIBPNG_ROOT="libpng-${LIBPNG_VERSION}"

PREFIX=/opt/_internal/libpng-${LIBPNG_VERSION%.*.*}

fetch_source "${LIBPNG_ROOT}.tar.xz" "${LIBPNG_DOWNLOAD_URL}"
check_sha256sum "${LIBPNG_ROOT}.tar.xz" "${LIBPNG_HASH}"
tar xf "${LIBPNG_ROOT}.tar.xz"
pushd "${LIBPNG_ROOT}"

# Add rpath to pkgconfig
sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" libpng.pc.in

DESTDIR=/manylinux-rootfs do_standard_install --prefix="${PREFIX}"
popd
rm -rf "${LIBPNG_ROOT}" "${LIBPNG_ROOT}.tar.xz"

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlink for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
ln -s "${PREFIX}/lib/pkgconfig/libpng16.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/libpng16.pc
ln -s "${PREFIX}/lib/pkgconfig/libpng.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/libpng.pc

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig /manylinux-rootfs"${PREFIX}"/include
rm -rf /manylinux-rootfs"${PREFIX}"/share/man /manylinux-rootfs"${PREFIX}"/bin/libpng*-config
