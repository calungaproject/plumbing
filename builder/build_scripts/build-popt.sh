#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install popt (command-line option parsing), a hard requirement of rpm.
# Not in UBI8 repos, so build from source.
check_var "${POPT_VERSION}"
check_var "${POPT_HASH}"
check_var "${POPT_DOWNLOAD_URL}"
POPT_ROOT="popt-${POPT_VERSION}"

PREFIX=/opt/_internal/popt-${POPT_VERSION}

fetch_source "${POPT_ROOT}.tar.gz" "${POPT_DOWNLOAD_URL}"
check_sha256sum "${POPT_ROOT}.tar.gz" "${POPT_HASH}"
tar xfz "${POPT_ROOT}.tar.gz"
pushd "${POPT_ROOT}"

./configure --prefix="${PREFIX}" \
    --disable-static \
    CPPFLAGS="${MANYLINUX_CPPFLAGS}" \
    CFLAGS="${MANYLINUX_CFLAGS}" \
    LDFLAGS="${MANYLINUX_LDFLAGS}" \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${POPT_ROOT}" "${POPT_ROOT}.tar.gz"

# Add rpath to pkgconfig
if [ -f /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/popt.pc ]; then
    sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" \
        /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/popt.pc
fi

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlink for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
if [ -f /manylinux-buildfs"${PREFIX}"/lib/pkgconfig/popt.pc ]; then
    ln -s "${PREFIX}/lib/pkgconfig/popt.pc" \
        /manylinux-buildfs/usr/local/lib/pkgconfig/popt.pc
fi

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig \
       /manylinux-rootfs"${PREFIX}"/include \
       /manylinux-rootfs"${PREFIX}"/share
