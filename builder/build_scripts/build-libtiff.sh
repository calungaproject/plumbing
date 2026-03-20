#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent libtiff
check_var "${LIBTIFF_VERSION}"
check_var "${LIBTIFF_HASH}"
check_var "${LIBTIFF_DOWNLOAD_URL}"
LIBTIFF_ROOT="tiff-${LIBTIFF_VERSION}"

PREFIX=/opt/_internal/libtiff-${LIBTIFF_VERSION%.*}

fetch_source "${LIBTIFF_ROOT}.tar.xz" "${LIBTIFF_DOWNLOAD_URL}"
check_sha256sum "${LIBTIFF_ROOT}.tar.xz" "${LIBTIFF_HASH}"
tar xf "${LIBTIFF_ROOT}.tar.xz"
pushd "${LIBTIFF_ROOT}"

# Build with CMake
mkdir build
cd build
cmake .. \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="${MANYLINUX_CFLAGS}" \
    -DCMAKE_CXX_FLAGS="${MANYLINUX_CXXFLAGS}" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -Dtiff-tools=OFF \
    -Dtiff-tests=OFF \
    -Dtiff-contrib=OFF \
    -Dtiff-docs=OFF \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${LIBTIFF_ROOT}" "${LIBTIFF_ROOT}.tar.xz"

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
for pc in "${PREFIX}"/lib/pkgconfig/*.pc; do
    if [ -f "/manylinux-buildfs${pc}" ]; then
        ln -s "${pc}" /manylinux-buildfs/usr/local/lib/pkgconfig/$(basename "$pc")
    fi
done

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig /manylinux-rootfs"${PREFIX}"/include
