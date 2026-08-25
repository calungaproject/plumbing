#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent Little CMS 2
check_var "${LCMS2_VERSION}"
check_var "${LCMS2_HASH}"
check_var "${LCMS2_DOWNLOAD_URL}"
LCMS2_ROOT="lcms2-${LCMS2_VERSION}"

PREFIX=/opt/_internal/lcms2-${LCMS2_VERSION%.*}

fetch_source "${LCMS2_ROOT}.tar.gz" "${LCMS2_DOWNLOAD_URL}"
check_sha256sum "${LCMS2_ROOT}.tar.gz" "${LCMS2_HASH}"
tar xf "${LCMS2_ROOT}.tar.gz"
pushd "${LCMS2_ROOT}"

DESTDIR=/manylinux-rootfs do_standard_install --prefix="${PREFIX}" --disable-static
popd
rm -rf "${LCMS2_ROOT}" "${LCMS2_ROOT}.tar.gz"

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
