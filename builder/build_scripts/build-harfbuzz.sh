#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent HarfBuzz (complex-script text shaping/hinting for FreeType)
check_var "${HARFBUZZ_VERSION}"
check_var "${HARFBUZZ_HASH}"
check_var "${HARFBUZZ_DOWNLOAD_URL}"
HARFBUZZ_ROOT="harfbuzz-${HARFBUZZ_VERSION}"

PREFIX=/opt/_internal/harfbuzz-${HARFBUZZ_VERSION%.*}

fetch_source "${HARFBUZZ_ROOT}.tar.xz" "${HARFBUZZ_DOWNLOAD_URL}"
check_sha256sum "${HARFBUZZ_ROOT}.tar.xz" "${HARFBUZZ_HASH}"
tar xf "${HARFBUZZ_ROOT}.tar.xz"
pushd "${HARFBUZZ_ROOT}"

# Point CMake's module-mode find_package at our source-built FreeType (headers
# live under /opt/_internal/<pkg>/, not on the system include path).
DEP_PREFIX="$(printf '%s;' /opt/_internal/freetype-* /opt/_internal/libpng-* /opt/_internal/brotli-*)"

# Build with CMake. HarfBuzz's preferred build system is meson, but that needs
# Python, which is not present in this base build stage (CPython is built later).
# The CMake build produces the same libharfbuzz.
#
# HB_HAVE_FREETYPE=ON is REQUIRED: it compiles hb-ft (the FreeType integration)
# and installs hb-ft.h, both of which Pillow's vendored raqm needs (raqm.c does
# #include <hb-ft.h> and calls hb_ft_font_create). This is why HarfBuzz is built
# AFTER FreeType -- it links against the already-built libfreetype. FreeType
# itself is built without HarfBuzz (see build-freetype.sh) so there is no cycle.
# Other optional integrations are off to keep the lib minimal, matching PyPI's
# Pillow build (meson -Dfreetype=enabled -Dglib=disabled).
mkdir -p _build
cd _build
cmake .. \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="${MANYLINUX_CFLAGS}" \
    -DCMAKE_CXX_FLAGS="${MANYLINUX_CXXFLAGS}" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DCMAKE_PREFIX_PATH="${DEP_PREFIX}" \
    -DBUILD_SHARED_LIBS=ON \
    -DHB_HAVE_FREETYPE=ON \
    -DHB_HAVE_GLIB=OFF \
    -DHB_HAVE_GOBJECT=OFF \
    -DHB_HAVE_ICU=OFF \
    -DHB_BUILD_UTILS=OFF \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${HARFBUZZ_ROOT}" "${HARFBUZZ_ROOT}.tar.xz"

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
