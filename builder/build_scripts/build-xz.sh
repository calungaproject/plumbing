#!/bin/bash
set -exuo pipefail
MY_DIR=$(dirname "${BASH_SOURCE[0]}")
source "${MY_DIR}/build_utils.sh"

check_var "${XZ_VERSION}"
check_var "${XZ_HASH}"
check_var "${XZ_DOWNLOAD_URL}"
XZ_ROOT="xz-${XZ_VERSION}"

PREFIX=/opt/_internal/xz-${XZ_VERSION%.*}

fetch_source "${XZ_ROOT}.tar.gz" "${XZ_DOWNLOAD_URL}/v${XZ_VERSION}"
check_sha256sum "${XZ_ROOT}.tar.gz" "${XZ_HASH}"
tar xfz "${XZ_ROOT}.tar.gz"
pushd "${XZ_ROOT}"

./configure --prefix="${PREFIX}" \
    --disable-static \
    --disable-xz \
    --disable-xzdec \
    --disable-lzmadec \
    --disable-lzmainfo \
    --disable-scripts \
    --disable-doc \
    CPPFLAGS="${MANYLINUX_CPPFLAGS}" \
    CFLAGS="${MANYLINUX_CFLAGS}" \
    LDFLAGS="${MANYLINUX_LDFLAGS}" \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${XZ_ROOT}" "${XZ_ROOT}.tar.gz"

# Add rpath to pkgconfig
if [ -f /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/liblzma.pc ]; then
    sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" \
        /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/liblzma.pc
fi

strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlink for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
if [ -f /manylinux-buildfs"${PREFIX}"/lib/pkgconfig/liblzma.pc ]; then
    ln -s "${PREFIX}/lib/pkgconfig/liblzma.pc" \
        /manylinux-buildfs/usr/local/lib/pkgconfig/liblzma.pc
fi

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig \
       /manylinux-rootfs"${PREFIX}"/include \
       /manylinux-rootfs"${PREFIX}"/share
