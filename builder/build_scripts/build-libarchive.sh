#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install libarchive. rpm's CMakeLists unconditionally requires the
# libarchive pkg-config module at configure time, and rpm's tools
# (rpm2archive, rpmuncompress) link it -- but librpm/librpmio, the libraries
# createrepo_c links, do not. So this only needs to be present in the rpm
# build stage; it never reaches the final image and never lands in wheels.
check_var "${LIBARCHIVE_VERSION}"
check_var "${LIBARCHIVE_HASH}"
check_var "${LIBARCHIVE_DOWNLOAD_URL}"
LIBARCHIVE_ROOT="libarchive-${LIBARCHIVE_VERSION}"

PREFIX=/opt/_internal/libarchive-${LIBARCHIVE_VERSION%.*}

fetch_source "${LIBARCHIVE_ROOT}.tar.gz" "${LIBARCHIVE_DOWNLOAD_URL}/v${LIBARCHIVE_VERSION}"
check_sha256sum "${LIBARCHIVE_ROOT}.tar.gz" "${LIBARCHIVE_HASH}"
tar xfz "${LIBARCHIVE_ROOT}.tar.gz"
pushd "${LIBARCHIVE_ROOT}"

./configure --prefix="${PREFIX}" \
    --disable-static \
    --without-xml2 \
    --without-expat \
    --without-lz4 \
    CPPFLAGS="${MANYLINUX_CPPFLAGS}" \
    CFLAGS="${MANYLINUX_CFLAGS}" \
    LDFLAGS="${MANYLINUX_LDFLAGS}" \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${LIBARCHIVE_ROOT}" "${LIBARCHIVE_ROOT}.tar.gz"

# Add rpath to pkgconfig
for pc in /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/*.pc; do
    if [ -f "$pc" ]; then
        sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" "$pc"
    fi
done

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlinks for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
for pc in /manylinux-buildfs"${PREFIX}"/lib/pkgconfig/*.pc; do
    if [ -f "$pc" ]; then
        ln -s "${PREFIX}/lib/pkgconfig/$(basename "$pc")" \
            /manylinux-buildfs/usr/local/lib/pkgconfig/$(basename "$pc")
    fi
done

# Clean-up for runtime (rootfs is unused for libarchive, but keep the tree tidy)
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig \
       /manylinux-rootfs"${PREFIX}"/include \
       /manylinux-rootfs"${PREFIX}"/share
