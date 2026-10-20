#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install libmodulemd, a hard requirement of createrepo_c (its
# WITH_LIBMODULEMD option is ON by default, matching upstream PyPI wheels).
# Links the image's glib (manylinux-whitelisted, stays external), the image's
# source-built libyaml, and our librpmio (decompression). Requires meson and
# ninja on PATH, and the popt/lua/rpm build trees under /opt/_internal.
#
# libmodulemd's meson.build hardcodes -Werror=format=2, which gcc 14 escalates
# into errors on two spots (format-overflow, format-truncation); the c_args
# below disable just those two escalations.
check_var "${MODULEMD_VERSION}"
check_var "${MODULEMD_HASH}"
check_var "${MODULEMD_DOWNLOAD_URL}"
MODULEMD_ROOT="modulemd-${MODULEMD_VERSION}"

PREFIX=/opt/_internal/modulemd-${MODULEMD_VERSION%.*}

fetch_source "${MODULEMD_ROOT}.tar.xz" "${MODULEMD_DOWNLOAD_URL}/${MODULEMD_VERSION}"
check_sha256sum "${MODULEMD_ROOT}.tar.xz" "${MODULEMD_HASH}"
tar xJf "${MODULEMD_ROOT}.tar.xz"
pushd "${MODULEMD_ROOT}"

meson setup _build \
    --prefix="${PREFIX}" \
    --libdir=lib \
    --buildtype=release \
    "-Dc_args=['-Wno-error=format-overflow','-Wno-error=format-truncation']" \
    -Dskip_introspection=true \
    -Dwith_py3=false \
    -Dwith_py2=false \
    -Dwith_docs=false \
    -Dwith_manpages=disabled \
    > /dev/null

meson compile -C _build > /dev/null
meson install -C _build --destdir /manylinux-rootfs > /dev/null
popd
rm -rf "${MODULEMD_ROOT}" "${MODULEMD_ROOT}.tar.xz"

# Nothing needs the modulemd tools (modulemd-validator); drop them so they do
# not end up as dead weight in the final image.
rm -rf /manylinux-rootfs"${PREFIX}"/bin

# Add rpath to pkgconfig
if [ -f /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/modulemd-2.0.pc ]; then
    sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" \
        /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/modulemd-2.0.pc
fi

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlink for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
if [ -f /manylinux-buildfs"${PREFIX}"/lib/pkgconfig/modulemd-2.0.pc ]; then
    ln -s "${PREFIX}/lib/pkgconfig/modulemd-2.0.pc" \
        /manylinux-buildfs/usr/local/lib/pkgconfig/modulemd-2.0.pc
fi

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig \
       /manylinux-rootfs"${PREFIX}"/include \
       /manylinux-rootfs"${PREFIX}"/share
