#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Build FFmpeg shared libraries (libavcodec/libavformat/libavutil/libswscale/
# libswresample) so OpenCV's VideoCapture/VideoWriter (Video I/O) works, matching
# the PyPI opencv-python wheel which bundles FFmpeg. FFmpeg is built LGPL (no
# --enable-gpl / --enable-nonfree), so it is redistributable.
check_var "${FFMPEG_VERSION}"
check_var "${FFMPEG_HASH}"
check_var "${FFMPEG_DOWNLOAD_URL}"
FFMPEG_ROOT="ffmpeg-${FFMPEG_VERSION}"

PREFIX=/opt/_internal/ffmpeg-${FFMPEG_VERSION%.*}

fetch_source "${FFMPEG_ROOT}.tar.xz" "${FFMPEG_DOWNLOAD_URL}"
check_sha256sum "${FFMPEG_ROOT}.tar.xz" "${FFMPEG_HASH}"
tar xf "${FFMPEG_ROOT}.tar.xz"
pushd "${FFMPEG_ROOT}"

# zlib is source-built and staged into the build fs; find its paths via pkg-config
# (the manylinux flags do not put /usr/local on the search path).
ZLIB_INCDIR=$(pkg-config --variable=includedir zlib)
ZLIB_LIBDIR=$(pkg-config --variable=libdir zlib)

# --disable-x86asm: the UBI8 builder base ships no assembler (nasm/yasm); aom is
#   built the same way (ENABLE_NASM=OFF). Functionally complete, just no hand-
#   tuned x86 assembly.
# --disable-autodetect: never silently link a system library. Only zlib is
#   explicitly re-enabled, so the wheels stay self-contained and gate-clean
#   (libz.so.1 is manylinux-allowlisted).
./configure \
    --prefix="${PREFIX}" \
    --enable-shared \
    --disable-static \
    --enable-pic \
    --disable-x86asm \
    --disable-autodetect \
    --enable-zlib \
    --disable-programs \
    --disable-doc \
    --disable-debug \
    --enable-rpath \
    --extra-cflags="${MANYLINUX_CPPFLAGS} ${MANYLINUX_CFLAGS} -I${ZLIB_INCDIR}" \
    --extra-ldflags="${MANYLINUX_LDFLAGS} -L${ZLIB_LIBDIR} -Wl,-rpath,${ZLIB_LIBDIR}" \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${FFMPEG_ROOT}" "${FFMPEG_ROOT}.tar.xz"

# Add rpath to pkgconfig so pkg-config consumers (OpenCV) get the rpath
# automatically and auditwheel can bundle the libs.
for pc in /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/*.pc; do
    if [ -f "$pc" ]; then
        sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" "$pc"
    fi
done

# Strip what we can
strip_ /manylinux-rootfs

# share/ holds only ffmpeg CLI presets + examples (we --disable-programs); it is
# needed by neither building nor runtime. Drop it before the buildfs copy so it
# does not get carried into the builder image via merged_buildfs.
rm -rf /manylinux-rootfs"${PREFIX}"/share

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlinks for pkgconfig so consumers find libav*.pc on the standard path
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
for pc in /manylinux-buildfs"${PREFIX}"/lib/pkgconfig/*.pc; do
    if [ -f "$pc" ]; then
        ln -s "${PREFIX}/lib/pkgconfig/$(basename "$pc")" /manylinux-buildfs/usr/local/lib/pkgconfig/$(basename "$pc")
    fi
done

# Clean-up for runtime (keep libs, drop headers + pkgconfig)
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig /manylinux-rootfs"${PREFIX}"/include
