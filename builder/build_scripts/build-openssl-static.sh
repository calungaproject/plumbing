#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# A second, static-only OpenSSL for packages that embed OpenSSL directly in
# their extension module instead of linking it dynamically. cryptography is the
# case that matters: its official PyPI wheels are built this way, shipping one
# self-contained _rust.abi3.so with no libcrypto/libssl beside it.
#
# Dynamically linked against the shared build, auditwheel bundles libcrypto and
# libssl into the wheel but cannot see ossl-modules/legacy.so, because OpenSSL
# dlopens it and auditwheel only follows DT_NEEDED. The bundled libcrypto also
# carries a MODULESDIR compiled to this image's paths, which do not exist
# wherever the wheel is installed. OSSL_PROVIDER_load(NULL, "legacy") then fails
# and Blowfish, CAST5, IDEA, SEED, ARC4 and RC2 become unusable.
#
# Configure notes:
#   no-module  builds the providers, "legacy" included, into libcrypto.a.
#              Without it they are only ever separate .so modules, which a
#              statically linked wheel has no way to reach. no-shared does NOT
#              imply this.
#   -fPIC      these archives get linked into a shared object.
#
# This prefix is deliberately named so it does NOT match the /opt/_internal/
# openssl* globs the final stage uses to publish the shared build into
# /usr/local/{include,lib,lib/pkgconfig} -- it must stay off PKG_CONFIG_PATH and
# out of ldconfig so nothing links it by accident. A package opts in explicitly
# by setting OPENSSL_DIR and OPENSSL_STATIC.

check_var "${OPENSSL_ROOT}"
check_var "${OPENSSL_HASH}"
check_var "${OPENSSL_DOWNLOAD_URL}"

OPENSSL_VERSION=${OPENSSL_ROOT#*-}

if [ "${OS_ID_LIKE}" = "rhel" ];then
	manylinux_pkg_install perl-core
fi

PREFIX=/opt/_internal/static-openssl-${OPENSSL_VERSION%.*}

PARALLEL_BUILDS=
if [ "$(nproc)" -ge 2 ]; then
	PARALLEL_BUILDS=-j2
fi

LIBATOMIC=
if [ "${AUDITWHEEL_ARCH}" == "i686" ]; then
	LIBATOMIC=-latomic
fi

fetch_source "${OPENSSL_ROOT}.tar.gz" "${OPENSSL_DOWNLOAD_URL}"
check_sha256sum "${OPENSSL_ROOT}.tar.gz" "${OPENSSL_HASH}"
tar -xzf "${OPENSSL_ROOT}.tar.gz"
pushd "${OPENSSL_ROOT}"
./Configure "--prefix=${PREFIX}" "--openssldir=${PREFIX}" --libdir=lib no-afalgeng no-shared no-module -fPIC CPPFLAGS="${MANYLINUX_CPPFLAGS}" CFLAGS="${MANYLINUX_CFLAGS}" CXXFLAGS="${MANYLINUX_CXXFLAGS}" LDFLAGS="${MANYLINUX_LDFLAGS} ${LIBATOMIC}" > /dev/null
make ${PARALLEL_BUILDS} > /dev/null
make install_sw > /dev/null
popd
rm -rf "${OPENSSL_ROOT}" "${OPENSSL_ROOT}.tar.gz"

# Only the archives and the headers are consumed here. install_sw also lays down
# a 7.8 MB statically linked openssl CLI that nothing can reach -- this prefix is
# off PATH by design -- and that image scanners would inventory as a second
# OpenSSL. openssl-sys reads the version out of the headers, not by running the
# binary, so dropping it does not change the wheel.
rm -rf "${PREFIX}/bin"

# Version-independent path, so consumers do not have to track the OpenSSL
# version across repositories.
ln -sfn "${PREFIX}" /opt/_internal/static-openssl

# The archives must keep their symbol tables to be linkable, so this is not
# passed through strip_.

# The providers have to be inside libcrypto.a, or a statically linked wheel
# silently loses the legacy algorithms. Fail the build here rather than ship it.
# grep -c rather than grep -q: -q closes the pipe on the first match and kills
# nm with SIGPIPE, which pipefail would turn into a build failure on success.
LEGACY_SYMS=$(nm "${PREFIX}/lib/libcrypto.a" | grep -c ossl_legacy_provider_init || true)
if [ "${LEGACY_SYMS}" -eq 0 ]; then
	echo "ERROR: no ossl_legacy_provider_init in ${PREFIX}/lib/libcrypto.a." >&2
	echo "The legacy provider was not built in; a wheel linking this would" >&2
	echo "silently lose Blowfish, CAST5, IDEA, SEED, ARC4 and RC2." >&2
	exit 1
fi
