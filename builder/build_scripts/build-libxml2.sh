#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent libxml2
check_var "${LIBXML2_VERSION}"
check_var "${LIBXML2_HASH}"
check_var "${LIBXML2_DOWNLOAD_URL}"
LIBXML2_MAJOR_MINOR=$(echo "${LIBXML2_VERSION}" | cut -d. -f1-2)
LIBXML2_ROOT="libxml2-${LIBXML2_VERSION}"

PREFIX=/opt/_internal/libxml2-${LIBXML2_MAJOR_MINOR}

fetch_source "${LIBXML2_ROOT}.tar.xz" "${LIBXML2_DOWNLOAD_URL}/${LIBXML2_MAJOR_MINOR}"
check_sha256sum "${LIBXML2_ROOT}.tar.xz" "${LIBXML2_HASH}"
tar xf "${LIBXML2_ROOT}.tar.xz"
pushd "${LIBXML2_ROOT}"

# Add rpath to pkgconfig
sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" libxml-2.0.pc.in

DESTDIR=/manylinux-rootfs do_standard_install \
    --prefix="${PREFIX}" \
    --without-python \
    --without-lzma \
    --with-zlib
popd
rm -rf "${LIBXML2_ROOT}" "${LIBXML2_ROOT}.tar.xz"

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlink for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
ln -s "${PREFIX}/lib/pkgconfig/libxml-2.0.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/libxml-2.0.pc

# Clean-up for runtime - keep bin/xmllint for potential debugging
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig /manylinux-rootfs"${PREFIX}"/include
rm -rf /manylinux-rootfs"${PREFIX}"/share/man /manylinux-rootfs"${PREFIX}"/share/doc
