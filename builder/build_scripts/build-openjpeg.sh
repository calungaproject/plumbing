#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent OpenJPEG (JPEG2000 codec)
check_var "${OPENJPEG_VERSION}"
check_var "${OPENJPEG_HASH}"
check_var "${OPENJPEG_DOWNLOAD_URL}"
OPENJPEG_ROOT="openjpeg-${OPENJPEG_VERSION}"

PREFIX=/opt/_internal/openjpeg-${OPENJPEG_VERSION%.*}

# GitHub auto-generated archive is named v<version>.tar.gz; it extracts to ${OPENJPEG_ROOT}/
fetch_source "v${OPENJPEG_VERSION}.tar.gz" "${OPENJPEG_DOWNLOAD_URL}"
check_sha256sum "v${OPENJPEG_VERSION}.tar.gz" "${OPENJPEG_HASH}"
tar xf "v${OPENJPEG_VERSION}.tar.gz"
pushd "${OPENJPEG_ROOT}"

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
    -DBUILD_STATIC_LIBS=OFF \
    -DBUILD_CODEC=OFF \
    -DBUILD_PKGCONFIG_FILES=ON \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${OPENJPEG_ROOT}" "v${OPENJPEG_VERSION}.tar.gz"

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
