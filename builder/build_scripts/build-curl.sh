#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent curl
check_var "${CURL_ROOT}"
check_var "${CURL_HASH}"
check_var "${CURL_DOWNLOAD_URL}"

# Check if curl-devel is available from packages
# On UBI images, curl-devel is not available, so we need to build from source
if dnf list available curl-devel &>/dev/null; then
	echo "skipping installation of ${CURL_ROOT} - using system curl-devel"
	# Ensure the buildfs dir always exists so `COPY --from=build_curl
	# /manylinux-buildfs /` succeeds even when we skip the source build
	# (system curl-devel already provides headers/pkgconfig to consumers).
	mkdir -p /manylinux-buildfs
	exit 0
fi

# Remove system curl-devel if present (we're building from source)
dnf erase -y curl-devel 2>/dev/null || true

SO_COMPAT=4
PREFIX=/opt/_internal/curl-${SO_COMPAT}

fetch_source "${CURL_ROOT}.tar.gz" "${CURL_DOWNLOAD_URL}"
check_sha256sum "${CURL_ROOT}.tar.gz" "${CURL_HASH}"
tar -xzf "${CURL_ROOT}.tar.gz"
pushd "${CURL_ROOT}"
./configure --prefix=${PREFIX} --disable-static --without-libpsl --with-openssl CPPFLAGS="${MANYLINUX_CPPFLAGS}" CFLAGS="${MANYLINUX_CFLAGS}" CXXFLAGS="${MANYLINUX_CXXFLAGS}" LDFLAGS="${MANYLINUX_LDFLAGS} -Wl,-rpath=\$(LIBRPATH)" > /dev/null
make > /dev/null
make install > /dev/null
popd
rm -rf "${CURL_ROOT}" "${CURL_ROOT}.tar.gz" ${PREFIX}/share/man

if [ ! -f ${PREFIX}/lib/libcurl.so.${SO_COMPAT} ]; then
	echo "please update SO_COMPAT"
	ls -al ${PREFIX}/lib
	exit 1
fi

strip_ ${PREFIX}

${PREFIX}/bin/curl --version
${PREFIX}/bin/curl-config --features

mkdir -p /manylinux-rootfs/${PREFIX}/lib
cp -f ${PREFIX}/lib/libcurl.so.${SO_COMPAT} /manylinux-rootfs/${PREFIX}/lib/

# Stage the full dev tree (headers, linkable .so symlink, pkgconfig) for
# build-time consumers such as Arrow's bundled S3/GCS/Azure cloud SDKs, which
# link libcurl. Mirrors the buildfs pattern in build-libxml2.sh/build-zlib.sh.
mkdir -p /manylinux-buildfs${PREFIX}
cp -rlf ${PREFIX}/. /manylinux-buildfs${PREFIX}/
# Expose libcurl.pc on the standard pkg-config search path so CMake's
# FindCURL (and pkg-config consumers) can discover it.
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
if [ -f ${PREFIX}/lib/pkgconfig/libcurl.pc ]; then
	ln -s "${PREFIX}/lib/pkgconfig/libcurl.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/libcurl.pc
fi
