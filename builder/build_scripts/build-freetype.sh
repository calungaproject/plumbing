#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent FreeType
check_var "${FREETYPE_VERSION}"
check_var "${FREETYPE_HASH}"
check_var "${FREETYPE_DOWNLOAD_URL}"
FREETYPE_ROOT="freetype-${FREETYPE_VERSION}"

PREFIX=/opt/_internal/freetype-${FREETYPE_VERSION%.*}

fetch_source "${FREETYPE_ROOT}.tar.xz" "${FREETYPE_DOWNLOAD_URL}"
check_sha256sum "${FREETYPE_ROOT}.tar.xz" "${FREETYPE_HASH}"
tar xf "${FREETYPE_ROOT}.tar.xz"
pushd "${FREETYPE_ROOT}"

# Point CMake's module-mode find_package at our source-built deps (headers live
# under /opt/_internal/<pkg>/, not on the system include path).
DEP_PREFIX="$(printf '%s;' /opt/_internal/libpng-* /opt/_internal/brotli-*)"

# Build with CMake
mkdir -p _build
cd _build
# FT_REQUIRE_* force these optional deps on: if discovery ever breaks the build
# fails loudly instead of silently shipping a FreeType without PNG (embedded
# color bitmap / emoji fonts) or Brotli (WOFF2 font loading) support.
#
# HarfBuzz is deliberately DISABLED here (matches PyPI's Pillow wheel build,
# which configures FreeType with --with-harfbuzz=no). FreeType only uses
# HarfBuzz to improve the auto-hinter for complex scripts; enabling it would
# create a FreeType<->HarfBuzz build cycle (HarfBuzz needs FreeType for hb-ft).
# Complex-script shaping is instead provided at the Pillow layer via vendored
# raqm linking HarfBuzz. HarfBuzz is built AFTER FreeType with freetype support.
cmake .. \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="${MANYLINUX_CFLAGS}" \
    -DCMAKE_CXX_FLAGS="${MANYLINUX_CXXFLAGS}" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DBUILD_SHARED_LIBS=ON \
    -DCMAKE_PREFIX_PATH="${DEP_PREFIX}" \
    -DFT_REQUIRE_PNG=ON \
    -DFT_DISABLE_HARFBUZZ=ON \
    -DFT_REQUIRE_BROTLI=ON \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${FREETYPE_ROOT}" "${FREETYPE_ROOT}.tar.xz"

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
