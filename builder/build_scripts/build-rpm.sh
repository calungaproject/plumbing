#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install rpm (librpm + librpmio), what createrepo_c links. rpm-devel is not
# available in UBI8 repos, so build from source.
#
# Configured lean: the image's source-built OpenSSL instead of libgcrypt,
# sqlite + ndb rpmdb backends, and none of selinux/dbus/audit/cap/acl/libelf/
# plugins/python/sequoia. Everything librpmio links is either source-built in
# this image (openssl, sqlite3, zstd, bzip2, liblzma) or source-built alongside
# (lua, popt), so auditwheel repair bundles only current, source-built libs.
#
# Note: the 4.20.1 release tarball ships no rpmio/rpmpgp_legacy and we build
# without sequoia, so this build has no OpenPGP backend. That is fine for
# createrepo_c, which reads packages with _RPMVSF_NOSIGNATURES |
# _RPMVSF_NODIGESTS | RPMVSF_NOHDRCHK.
#
# The rpm binaries are installed under ${PREFIX}/bin, which is not on PATH:
# they must not shadow /usr/bin/rpm*, because dnf's package-signature check
# shells out to `rpmkeys` (found via PATH) and ours has no OpenPGP support.
check_var "${RPM_VERSION}"
check_var "${RPM_HASH}"
check_var "${RPM_DOWNLOAD_URL}"
RPM_ROOT="rpm-${RPM_VERSION}"

PREFIX=/opt/_internal/rpm-${RPM_VERSION%.*}

# CMake's FindLua does not search /opt/_internal, so point it at our
# source-built lua explicitly.
LUA_PREFIX="$(echo /opt/_internal/lua-*)"
[ -d "${LUA_PREFIX}" ]
LUA_LIBRARY="$(find "${LUA_PREFIX}/lib" -maxdepth 1 -name 'liblua-*.so' | sort | head -1)"
check_var "${LUA_LIBRARY}"

# Likewise for the configure-time-only dependencies (libmagic via
# find_library/find_path) and for CMake's FindZLIB/FindBZip2, which do not use
# pkg-config. In build stages there are no /usr/local symlinks, so every
# find_* module needs the /opt/_internal prefixes hinted explicitly.
# libarchive, popt, sqlite3, xz and zstd are found through pkg-config.
DEP_PREFIX="$(printf '%s;' /opt/_internal/file-* /opt/_internal/libarchive-* \
    /opt/_internal/zlib-* /opt/_internal/bzip2-*)"

fetch_source "${RPM_ROOT}.tar.bz2" "${RPM_DOWNLOAD_URL}"
check_sha256sum "${RPM_ROOT}.tar.bz2" "${RPM_HASH}"
tar xjf "${RPM_ROOT}.tar.bz2"
pushd "${RPM_ROOT}"

# rpm's CMakeLists probes -fno-strict-overflow, -fno-delete-null-pointer-checks
# and -fhardened with check_c_compiler_flag(), all writing to the same result
# variable ("found") and only unsetting the normal variable -- the INTERNAL
# cache entry survives, so every flag after the first inherits its result and
# -fhardened gets added even on compilers that do not support it (the static
# clang used for image builds rejects it with "unknown argument"). Drop it:
# the hardening it would enable is already provided by MANYLINUX_CFLAGS
# (-fstack-protector-strong, -D_FORTIFY_SOURCE=2 via CPPFLAGS).
sed -i "s/ -fhardened)/)/" CMakeLists.txt

mkdir -p _build
cd _build
cmake .. \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="${MANYLINUX_CFLAGS}" \
    -DCMAKE_PREFIX_PATH="${DEP_PREFIX}" \
    -DLUA_INCLUDE_DIR="${LUA_PREFIX}/include" \
    -DLUA_LIBRARY="${LUA_LIBRARY}" \
    -DENABLE_NLS=OFF \
    -DENABLE_OPENMP=OFF \
    -DENABLE_PYTHON=OFF \
    -DENABLE_PLUGINS=OFF \
    -DENABLE_SQLITE=ON \
    -DENABLE_NDB=ON \
    -DENABLE_BDB_RO=OFF \
    -DWITH_CAP=OFF \
    -DWITH_ACL=OFF \
    -DWITH_SELINUX=OFF \
    -DWITH_DBUS=OFF \
    -DWITH_AUDIT=OFF \
    -DWITH_FAPOLICYD=OFF \
    -DWITH_FSVERITY=OFF \
    -DWITH_IMAEVM=OFF \
    -DWITH_SEQUOIA=OFF \
    -DWITH_OPENSSL=ON \
    -DWITH_READLINE=OFF \
    -DWITH_LIBELF=OFF \
    -DWITH_LIBDW=OFF \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${RPM_ROOT}" "${RPM_ROOT}.tar.bz2"

# Add rpath to pkgconfig
if [ -f /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/rpm.pc ]; then
    sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" \
        /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/rpm.pc
fi

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlink for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
if [ -f /manylinux-buildfs"${PREFIX}"/lib/pkgconfig/rpm.pc ]; then
    ln -s "${PREFIX}/lib/pkgconfig/rpm.pc" \
        /manylinux-buildfs/usr/local/lib/pkgconfig/rpm.pc
fi

# Clean-up for runtime: keep lib/rpm (macros, rpmrc, platform) and the
# ${PREFIX}/bin tools -- they are off PATH and needed by nothing at runtime,
# but dropping them would diverge from the trees the other build scripts ship.
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig \
       /manylinux-rootfs"${PREFIX}"/include \
       /manylinux-rootfs"${PREFIX}"/share
