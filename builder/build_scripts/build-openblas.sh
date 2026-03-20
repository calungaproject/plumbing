#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent OpenBLAS
check_var "${OPENBLAS_VERSION}"
check_var "${OPENBLAS_HASH}"
check_var "${OPENBLAS_DOWNLOAD_URL}"
OPENBLAS_ROOT="OpenBLAS-${OPENBLAS_VERSION}"

PREFIX=/opt/_internal/openblas-${OPENBLAS_VERSION%.*.*}

fetch_source "${OPENBLAS_ROOT}.tar.gz" "${OPENBLAS_DOWNLOAD_URL}/v${OPENBLAS_VERSION}"
check_sha256sum "${OPENBLAS_ROOT}.tar.gz" "${OPENBLAS_HASH}"
tar xfz "${OPENBLAS_ROOT}.tar.gz"
pushd "${OPENBLAS_ROOT}"

# Determine target architecture for optimization
TARGET=
if [ "${AUDITWHEEL_ARCH}" == "x86_64" ]; then
    TARGET="HASWELL"  # Generic x86_64 with AVX2 support
elif [ "${AUDITWHEEL_ARCH}" == "aarch64" ]; then
    TARGET="ARMV8"
elif [ "${AUDITWHEEL_ARCH}" == "i686" ]; then
    TARGET="PRESCOTT"
fi

# Build OpenBLAS
# Note: OpenBLAS build requires system GCC for OpenMP support
# The USE_OPENMP=1 flag enables multi-threaded BLAS operations
make -j"$(nproc)" \
    PREFIX="${PREFIX}" \
    DYNAMIC_ARCH=1 \
    USE_OPENMP=1 \
    NO_STATIC=1 \
    ${TARGET:+TARGET=${TARGET}} \
    CC=gcc \
    FC=gfortran \
    CFLAGS="${MANYLINUX_CFLAGS}" \
    FFLAGS="${MANYLINUX_CFLAGS}" \
    > /dev/null

make install PREFIX="${PREFIX}" DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${OPENBLAS_ROOT}" "${OPENBLAS_ROOT}.tar.gz"

# Add rpath to pkgconfig
if [ -f /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/openblas.pc ]; then
    sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/openblas.pc
fi

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Create symlinks for pkgconfig
mkdir -p /manylinux-buildfs/usr/local/lib/pkgconfig/
ln -s "${PREFIX}/lib/pkgconfig/openblas.pc" /manylinux-buildfs/usr/local/lib/pkgconfig/openblas.pc

# Clean-up for runtime
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig /manylinux-rootfs"${PREFIX}"/include
