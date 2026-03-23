#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent libxslt
check_var "${LIBXSLT_VERSION}"
check_var "${LIBXSLT_HASH}"
check_var "${LIBXSLT_DOWNLOAD_URL}"
LIBXSLT_MAJOR_MINOR=$(echo "${LIBXSLT_VERSION}" | cut -d. -f1-2)
LIBXSLT_ROOT="libxslt-${LIBXSLT_VERSION}"

PREFIX=/opt/_internal/libxslt-${LIBXSLT_MAJOR_MINOR}

fetch_source "${LIBXSLT_ROOT}.tar.xz" "${LIBXSLT_DOWNLOAD_URL}/${LIBXSLT_MAJOR_MINOR}"
check_sha256sum "${LIBXSLT_ROOT}.tar.xz" "${LIBXSLT_HASH}"
tar xf "${LIBXSLT_ROOT}.tar.xz"
pushd "${LIBXSLT_ROOT}"

# Add rpath to pkgconfig files
sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" libxslt.pc.in
sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" libexslt.pc.in

# Ensure dynamic linker can find libxml2
ldconfig

# Find libxml2 location
LIBXML2_PREFIX=$(find /opt/_internal -maxdepth 1 -type d -name 'libxml2-*' | head -1)
if [ -z "${LIBXML2_PREFIX}" ]; then
    echo "ERROR: Could not find libxml2 installation"
    exit 1
fi

# Configure with explicit libxml2 location
DESTDIR=/manylinux-rootfs ./configure \
    --prefix="${PREFIX}" \
    --without-python \
    --with-libxml-prefix="${LIBXML2_PREFIX}" \
    CPPFLAGS="${MANYLINUX_CPPFLAGS}" \
    CFLAGS="${MANYLINUX_CFLAGS}" \
    CXXFLAGS="${MANYLINUX_CXXFLAGS}" \
    LDFLAGS="${MANYLINUX_LDFLAGS}"

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${LIBXSLT_ROOT}" "${LIBXSLT_ROOT}.tar.xz"

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlinks for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
ln -s "${PREFIX}/lib/pkgconfig/libxslt.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/libxslt.pc
ln -s "${PREFIX}/lib/pkgconfig/libexslt.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/libexslt.pc

# Clean-up for runtime - keep bin/xsltproc for potential debugging
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig /manylinux-rootfs"${PREFIX}"/include
rm -rf /manylinux-rootfs"${PREFIX}"/share/man /manylinux-rootfs"${PREFIX}"/share/doc
