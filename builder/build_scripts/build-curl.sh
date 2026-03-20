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
CURL_DEVEL_AVAILABLE=false
if [ "${PACKAGE_MANAGER}" = "dnf" ] || [ "${PACKAGE_MANAGER}" = "yum" ]; then
	if dnf list available curl-devel &>/dev/null || yum list available curl-devel &>/dev/null; then
		CURL_DEVEL_AVAILABLE=true
	fi
elif [ "${PACKAGE_MANAGER}" = "apk" ]; then
	if apk list curl-dev 2>/dev/null | grep -q curl-dev; then
		CURL_DEVEL_AVAILABLE=true
	fi
fi

# Skip building curl if system curl-devel is available and we're not on manylinux2014
# (manylinux2014 always needs custom curl for compatibility)
if [ "${AUDITWHEEL_POLICY}" != "manylinux2014" ] && [ "${CURL_DEVEL_AVAILABLE}" = "true" ]; then
	echo "skipping installation of ${CURL_ROOT} - using system curl-devel"
	exit 0
fi

# Remove system curl-devel if present (we're building from source)
if which yum &>/dev/null; then
	yum erase -y curl-devel 2>/dev/null || true
elif which dnf &>/dev/null; then
	dnf erase -y curl-devel 2>/dev/null || true
elif which apk &>/dev/null; then
	apk del curl-dev 2>/dev/null || true
fi

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
