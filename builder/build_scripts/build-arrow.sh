#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Build Apache Arrow C++ library (required by pyarrow)
check_var "${ARROW_VERSION}"
check_var "${ARROW_HASH}"
check_var "${ARROW_DOWNLOAD_URL}"
ARROW_ROOT="apache-arrow-${ARROW_VERSION}"

PREFIX=/usr/local

fetch_source "${ARROW_ROOT}.tar.gz" "${ARROW_DOWNLOAD_URL}"
check_sha256sum "${ARROW_ROOT}.tar.gz" "${ARROW_HASH}"
tar xfz "${ARROW_ROOT}.tar.gz"
pushd "${ARROW_ROOT}/cpp"

cmake -S . -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DARROW_BUILD_STATIC=OFF \
    -DARROW_BUILD_SHARED=ON \
    -DARROW_COMPUTE=ON \
    -DARROW_CSV=ON \
    -DARROW_DATASET=ON \
    -DARROW_HDFS=ON \
    -DARROW_JSON=ON \
    -DARROW_PARQUET=ON \
    -DARROW_WITH_SNAPPY=ON \
    -DARROW_WITH_LZ4=ON \
    -DARROW_WITH_ZSTD=ON \
    -DARROW_WITH_ZLIB=ON \
    -DARROW_WITH_BZ2=ON \
    -DARROW_WITH_BROTLI=ON \
    -DARROW_WITH_RE2=ON \
    -DARROW_WITH_UTF8PROC=ON \
    -DARROW_DEPENDENCY_SOURCE=BUNDLED \
    -DCMAKE_C_FLAGS="${MANYLINUX_CFLAGS}" \
    -DCMAKE_CXX_FLAGS="${MANYLINUX_CXXFLAGS}" > /dev/null

cmake --build build --parallel "$(nproc)" > /dev/null
DESTDIR=/manylinux-rootfs cmake --install build > /dev/null
popd
rm -rf "${ARROW_ROOT}" "${ARROW_ROOT}.tar.gz"

# Add rpath to pkgconfig so pkg-config consumers get the rpath automatically
for pc in /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/{arrow,parquet}*.pc; do
    if [ -f "$pc" ]; then
        sed -i "s|^Libs:|Libs: -Wl,--enable-new-dtags,-rpath=\${libdir} |g" "$pc"
    fi
done

# Strip what we can
strip_ /manylinux-rootfs

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Clean-up for runtime (keep libs, drop headers, pkgconfig, cmake config and debug/doc files)
rm -rf /manylinux-rootfs"${PREFIX}"/include/arrow
rm -rf /manylinux-rootfs"${PREFIX}"/include/parquet
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/arrow*.pc
rm -rf /manylinux-rootfs"${PREFIX}"/lib/pkgconfig/parquet*.pc
rm -rf /manylinux-rootfs"${PREFIX}"/lib/cmake/Arrow
rm -rf /manylinux-rootfs"${PREFIX}"/lib/cmake/ArrowAcero
rm -rf /manylinux-rootfs"${PREFIX}"/lib/cmake/ArrowCompute
rm -rf /manylinux-rootfs"${PREFIX}"/lib/cmake/ArrowDataset
rm -rf /manylinux-rootfs"${PREFIX}"/lib/cmake/Parquet
rm -rf /manylinux-rootfs"${PREFIX}"/share/arrow
rm -rf /manylinux-rootfs"${PREFIX}"/share/doc/arrow
