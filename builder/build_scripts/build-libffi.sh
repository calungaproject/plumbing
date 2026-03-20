#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent libffi
check_var "${LIBFFI_VERSION}"
check_var "${LIBFFI_HASH}"
check_var "${LIBFFI_DOWNLOAD_URL}"
LIBFFI_ROOT="libffi-${LIBFFI_VERSION}"

PREFIX=/opt/_internal/libffi-${LIBFFI_VERSION%.*.*}

fetch_source "${LIBFFI_ROOT}.tar.gz" "${LIBFFI_DOWNLOAD_URL}/v${LIBFFI_VERSION}"
check_sha256sum "${LIBFFI_ROOT}.tar.gz" "${LIBFFI_HASH}"
tar xfz "${LIBFFI_ROOT}.tar.gz"
pushd "${LIBFFI_ROOT}"

# Add rpath to pkgconfig
sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" libffi.pc.in

DESTDIR=/manylinux-rootfs do_standard_install --prefix="${PREFIX}"
popd
rm -rf "${LIBFFI_ROOT}" "${LIBFFI_ROOT}.tar.gz"

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlink for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
ln -s "${PREFIX}/lib/pkgconfig/libffi.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/libffi.pc

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig /manylinux-rootfs"${PREFIX}"/include
rm -rf /manylinux-rootfs"${PREFIX}"/share/man /manylinux-rootfs"${PREFIX}"/share/info
