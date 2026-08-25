#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent libwebp
check_var "${LIBWEBP_VERSION}"
check_var "${LIBWEBP_HASH}"
check_var "${LIBWEBP_DOWNLOAD_URL}"
LIBWEBP_ROOT="libwebp-${LIBWEBP_VERSION}"

PREFIX=/opt/_internal/libwebp-${LIBWEBP_VERSION%.*}

fetch_source "${LIBWEBP_ROOT}.tar.gz" "${LIBWEBP_DOWNLOAD_URL}"
check_sha256sum "${LIBWEBP_ROOT}.tar.gz" "${LIBWEBP_HASH}"
tar xf "${LIBWEBP_ROOT}.tar.gz"
pushd "${LIBWEBP_ROOT}"

# Build with CMake
mkdir -p _build
cd _build
cmake .. \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="${MANYLINUX_CFLAGS}" \
    -DCMAKE_CXX_FLAGS="${MANYLINUX_CXXFLAGS}" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DBUILD_SHARED_LIBS=ON \
    -DWEBP_BUILD_ANIM_UTILS=OFF \
    -DWEBP_BUILD_CWEBP=OFF \
    -DWEBP_BUILD_DWEBP=OFF \
    -DWEBP_BUILD_GIF2WEBP=OFF \
    -DWEBP_BUILD_IMG2WEBP=OFF \
    -DWEBP_BUILD_VWEBP=OFF \
    -DWEBP_BUILD_WEBPINFO=OFF \
    -DWEBP_BUILD_WEBPMUX=OFF \
    -DWEBP_BUILD_EXTRAS=OFF \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${LIBWEBP_ROOT}" "${LIBWEBP_ROOT}.tar.gz"

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
        ln -s "${PREFIX}/lib/pkgconfig/$(basename "$pc")" /manylinux-buildfs/usr/local/lib/pkgconfig/$(basename "$pc")
    fi
done

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig /manylinux-rootfs"${PREFIX}"/include
