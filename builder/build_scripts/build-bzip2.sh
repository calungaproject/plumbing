#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent bzip2
check_var "${BZIP2_VERSION}"
check_var "${BZIP2_HASH}"
check_var "${BZIP2_DOWNLOAD_URL}"
BZIP2_ROOT="bzip2-${BZIP2_VERSION}"

PREFIX=/opt/_internal/bzip2-${BZIP2_VERSION%.*}

fetch_source "${BZIP2_ROOT}.tar.gz" "${BZIP2_DOWNLOAD_URL}"
check_sha256sum "${BZIP2_ROOT}.tar.gz" "${BZIP2_HASH}"
tar xfz "${BZIP2_ROOT}.tar.gz"
pushd "${BZIP2_ROOT}"

# bzip2 doesn't have a configure script, use make directly
make -f Makefile-libbz2_so \
    CC="${CC:-gcc}" \
    CFLAGS="${MANYLINUX_CFLAGS} -fPIC -D_FILE_OFFSET_BITS=64" \
    > /dev/null

# Install shared library
mkdir -p /manylinux-rootfs"${PREFIX}"/lib
mkdir -p /manylinux-rootfs"${PREFIX}"/include
mkdir -p /manylinux-rootfs"${PREFIX}"/bin

cp -a libbz2.so* /manylinux-rootfs"${PREFIX}"/lib/
cp bzlib.h /manylinux-rootfs"${PREFIX}"/include/

# Build and install utilities
make clean > /dev/null
make CC="${CC:-gcc}" CFLAGS="${MANYLINUX_CFLAGS}" > /dev/null
cp bzip2 bunzip2 bzcat /manylinux-rootfs"${PREFIX}"/bin/

popd
rm -rf "${BZIP2_ROOT}" "${BZIP2_ROOT}.tar.gz"

# Create pkgconfig file
mkdir -p /manylinux-rootfs"${PREFIX}"/lib/pkgconfig
cat > /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/bzip2.pc <<EOF
prefix=${PREFIX}
exec_prefix=\${prefix}
libdir=\${prefix}/lib
includedir=\${prefix}/include

Name: bzip2
Description: A file compression library
Version: ${BZIP2_VERSION}
Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} -L\${libdir} -lbz2
Cflags: -I\${includedir}
EOF

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlink for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
ln -s "${PREFIX}/lib/pkgconfig/bzip2.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/bzip2.pc

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig /manylinux-rootfs"${PREFIX}"/include
