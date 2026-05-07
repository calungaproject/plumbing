#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Build libomp (LLVM OpenMP runtime)
check_var "${LIBOMP_VERSION}"
check_var "${LIBOMP_HASH}"
check_var "${LIBOMP_CMAKE_HASH}"
check_var "${LIBOMP_DOWNLOAD_URL}"
LIBOMP_ROOT="openmp-${LIBOMP_VERSION}.src"
LLVM_CMAKE_ROOT="cmake-${LIBOMP_VERSION}.src"

PREFIX=/opt/_internal/libomp-${LIBOMP_VERSION%%.*}

# Python3 is required by libomp's cmake build to generate string tables
manylinux_pkg_install python3

fetch_source "${LIBOMP_ROOT}.tar.xz" "${LIBOMP_DOWNLOAD_URL}/llvmorg-${LIBOMP_VERSION}"
check_sha256sum "${LIBOMP_ROOT}.tar.xz" "${LIBOMP_HASH}"
fetch_source "${LLVM_CMAKE_ROOT}.tar.xz" "${LIBOMP_DOWNLOAD_URL}/llvmorg-${LIBOMP_VERSION}"
check_sha256sum "${LLVM_CMAKE_ROOT}.tar.xz" "${LIBOMP_CMAKE_HASH}"
tar xf "${LIBOMP_ROOT}.tar.xz"
tar xf "${LLVM_CMAKE_ROOT}.tar.xz"
pushd "${LIBOMP_ROOT}"

# Build with CMake (standalone build requires LLVM cmake modules)
mkdir build
cd build
cmake .. \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="${MANYLINUX_CFLAGS}" \
    -DCMAKE_CXX_FLAGS="${MANYLINUX_CXXFLAGS}" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DOPENMP_STANDALONE_BUILD=ON \
    -DLIBOMP_INSTALL_ALIASES=ON \
    -DLIBOMP_OMPD_GDB_SUPPORT=OFF \
    -DOPENMP_ENABLE_LIBOMPTARGET=OFF \
    -DCMAKE_MODULE_PATH="$(pwd)/../../${LLVM_CMAKE_ROOT}/Modules" \
    > /dev/null

make -j"$(nproc)" > /dev/null
make install DESTDIR=/manylinux-rootfs > /dev/null
popd
rm -rf "${LIBOMP_ROOT}" "${LIBOMP_ROOT}.tar.xz" "${LLVM_CMAKE_ROOT}" "${LLVM_CMAKE_ROOT}.tar.xz"

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Clean-up for runtime (keep libs and omp.h, remove cmake config)
rm -rf /manylinux-rootfs"${PREFIX}"/lib/cmake
