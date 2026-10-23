#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install lua as a shared library, a hard requirement of rpm.
# Not in UBI8 repos, so build from source.
check_var "${LUA_VERSION}"
check_var "${LUA_HASH}"
check_var "${LUA_DOWNLOAD_URL}"
LUA_ROOT="lua-${LUA_VERSION}"

PREFIX=/opt/_internal/lua-${LUA_VERSION%.*}
LUA_SOVERSION=${LUA_VERSION%.*}

fetch_source "${LUA_ROOT}.tar.gz" "${LUA_DOWNLOAD_URL}"
check_sha256sum "${LUA_ROOT}.tar.gz" "${LUA_HASH}"
tar xfz "${LUA_ROOT}.tar.gz"
pushd "${LUA_ROOT}"

# The upstream tarball has no liblua.so target and ships no pkg-config file
# (and its "make install" only installs the static library), so build the
# objects with -fPIC and assemble the shared library and .pc by hand.
make -C src linux-noreadline \
    MYCFLAGS="${MANYLINUX_CFLAGS} -fPIC" \
    > /dev/null
gcc -shared -Wl,-soname,liblua-${LUA_SOVERSION}.so \
    ${MANYLINUX_LDFLAGS} \
    -o "src/liblua-${LUA_SOVERSION}.so" \
    -Wl,--whole-archive src/liblua.a -Wl,--no-whole-archive \
    -lm -ldl

mkdir -p /manylinux-rootfs"${PREFIX}"/include \
         /manylinux-rootfs"${PREFIX}"/lib/pkgconfig
install -m 0755 "src/liblua-${LUA_SOVERSION}.so" \
    /manylinux-rootfs"${PREFIX}"/lib/
# unversioned development symlink
ln -s "liblua-${LUA_SOVERSION}.so" /manylinux-rootfs"${PREFIX}"/lib/liblua.so
install -m 0644 src/lua.h src/luaconf.h src/lualib.h src/lauxlib.h \
    /manylinux-rootfs"${PREFIX}"/include/

cat > /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/lua.pc <<EOF
prefix=${PREFIX}
exec_prefix=\${prefix}
libdir=\${exec_prefix}/lib
includedir=\${prefix}/include

Name: Lua
Description: An Extensible Extension Language
Version: ${LUA_VERSION}
Cflags: -I\${includedir}
Libs: -L\${libdir} -llua
EOF
popd
rm -rf "${LUA_ROOT}" "${LUA_ROOT}.tar.gz"

# Add rpath to pkgconfig
if [ -f /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/lua.pc ]; then
    sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" \
        /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/lua.pc
fi

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlink for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
if [ -f /manylinux-buildfs"${PREFIX}"/lib/pkgconfig/lua.pc ]; then
    ln -s "${PREFIX}/lib/pkgconfig/lua.pc" \
        /manylinux-buildfs/usr/local/lib/pkgconfig/lua.pc
fi

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig \
       /manylinux-rootfs"${PREFIX}"/include
