#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent libaom (AV1 codec, used by libavif for AVIF support)
check_var "${AOM_VERSION}"
check_var "${AOM_HASH}"
check_var "${AOM_DOWNLOAD_URL}"
AOM_ROOT="libaom-${AOM_VERSION}"

PREFIX=/opt/_internal/aom-${AOM_VERSION%.*}

fetch_source "${AOM_ROOT}.tar.gz" "${AOM_DOWNLOAD_URL}"
check_sha256sum "${AOM_ROOT}.tar.gz" "${AOM_HASH}"
tar xf "${AOM_ROOT}.tar.gz"
pushd "${AOM_ROOT}"

# Build with CMake.
# AOM_TARGET_CPU=generic: the UBI8 builder base has no assembler (nasm/yasm are
# not in its repos), and aom's cmake requires one for its hand-written SIMD asm.
# generic disables that asm and builds a pure-C library that is portable and
# correct; AVIF encode/decode is slower but functionally complete. SIMD can be
# restored later by adding a source-built nasm stage.
mkdir -p _build
cd _build
cmake .. \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="${MANYLINUX_CFLAGS}" \
    -DCMAKE_CXX_FLAGS="${MANYLINUX_CXXFLAGS}" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DBUILD_SHARED_LIBS=ON \
    -DAOM_TARGET_CPU=generic \
    -DENABLE_NASM=OFF \
    -DENABLE_DOCS=OFF \
    -DENABLE_EXAMPLES=OFF \
    -DENABLE_TESTS=OFF \
    -DENABLE_TESTDATA=OFF \
    -DENABLE_TOOLS=OFF \
    -DCONFIG_AV1_DECODER=1 \
    -DCONFIG_AV1_ENCODER=1 \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${AOM_ROOT}" "${AOM_ROOT}.tar.gz"

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
