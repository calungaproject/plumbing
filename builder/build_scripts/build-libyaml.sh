#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent libyaml
check_var "${LIBYAML_VERSION}"
check_var "${LIBYAML_HASH}"
check_var "${LIBYAML_DOWNLOAD_URL}"
LIBYAML_ROOT="yaml-${LIBYAML_VERSION}"

PREFIX=/opt/_internal/libyaml-${LIBYAML_VERSION%.*}

fetch_source "${LIBYAML_ROOT}.tar.gz" "${LIBYAML_DOWNLOAD_URL}"
check_sha256sum "${LIBYAML_ROOT}.tar.gz" "${LIBYAML_HASH}"
tar xfz "${LIBYAML_ROOT}.tar.gz"
pushd "${LIBYAML_ROOT}"

# Add rpath to pkgconfig
sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" yaml-0.1.pc.in

DESTDIR=/manylinux-rootfs do_standard_install --prefix="${PREFIX}"
popd
rm -rf "${LIBYAML_ROOT}" "${LIBYAML_ROOT}.tar.gz"

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlink for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
ln -s "${PREFIX}/lib/pkgconfig/yaml-0.1.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/yaml-0.1.pc

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig /manylinux-rootfs"${PREFIX}"/include
