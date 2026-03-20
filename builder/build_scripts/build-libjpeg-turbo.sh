#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent libjpeg-turbo
check_var "${LIBJPEG_TURBO_VERSION}"
check_var "${LIBJPEG_TURBO_HASH}"
check_var "${LIBJPEG_TURBO_DOWNLOAD_URL}"
LIBJPEG_TURBO_ROOT="libjpeg-turbo-${LIBJPEG_TURBO_VERSION}"

PREFIX=/opt/_internal/libjpeg-turbo-${LIBJPEG_TURBO_VERSION%.*}

fetch_source "${LIBJPEG_TURBO_ROOT}.tar.gz" "${LIBJPEG_TURBO_DOWNLOAD_URL}/${LIBJPEG_TURBO_VERSION}"
check_sha256sum "${LIBJPEG_TURBO_ROOT}.tar.gz" "${LIBJPEG_TURBO_HASH}"
tar xfz "${LIBJPEG_TURBO_ROOT}.tar.gz"
pushd "${LIBJPEG_TURBO_ROOT}"

# Build with CMake
mkdir build
cd build
cmake .. \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="${MANYLINUX_CFLAGS}" \
    -DCMAKE_CXX_FLAGS="${MANYLINUX_CXXFLAGS}" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DENABLE_SHARED=ON \
    -DENABLE_STATIC=OFF \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${LIBJPEG_TURBO_ROOT}" "${LIBJPEG_TURBO_ROOT}.tar.gz"

# Add rpath to pkgconfig files
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
ln -s "${PREFIX}/lib/pkgconfig/libjpeg.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/libjpeg.pc
ln -s "${PREFIX}/lib/pkgconfig/libturbojpeg.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/libturbojpeg.pc

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig /manylinux-rootfs"${PREFIX}"/include
