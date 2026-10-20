#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install file (libmagic). rpm's CMakeLists unconditionally requires the
# libmagic library and magic.h at configure time (find_library + find_path),
# and rpmbuild links it -- but librpm/librpmio, the libraries createrepo_c
# links, do not. So this only needs to be present in the rpm build stage; it
# never reaches the final image and never lands in wheels.
check_var "${FILE_VERSION}"
check_var "${FILE_HASH}"
check_var "${FILE_DOWNLOAD_URL}"
FILE_ROOT="file-${FILE_VERSION}"

PREFIX=/opt/_internal/file-${FILE_VERSION}

fetch_source "${FILE_ROOT}.tar.gz" "${FILE_DOWNLOAD_URL}"
check_sha256sum "${FILE_ROOT}.tar.gz" "${FILE_HASH}"
tar xfz "${FILE_ROOT}.tar.gz"
pushd "${FILE_ROOT}"

./configure --prefix="${PREFIX}" \
    --disable-static \
    CPPFLAGS="${MANYLINUX_CPPFLAGS}" \
    CFLAGS="${MANYLINUX_CFLAGS}" \
    LDFLAGS="${MANYLINUX_LDFLAGS}" \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${FILE_ROOT}" "${FILE_ROOT}.tar.gz"

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
        ln -s "${PREFIX}/lib/pkgconfig/$(basename "$pc")" \
            /manylinux-buildfs/usr/local/lib/pkgconfig/$(basename "$pc")
    fi
done

# Clean-up for runtime (rootfs is unused for file, but keep the tree tidy)
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig \
       /manylinux-rootfs"${PREFIX}"/include \
       /manylinux-rootfs"${PREFIX}"/share
