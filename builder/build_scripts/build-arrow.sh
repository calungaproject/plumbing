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

cmake_extra_args=()
target_arch="${AUDITWHEEL_ARCH:?AUDITWHEEL_ARCH must be set}"
if [[ "$target_arch" == "x86_64" ]]; then
    cmake_extra_args+=( -DBOOST_UUID_LINK_LIBATOMIC=OFF )
fi

# Arrow's bundled cloud SDKs (S3/GCS/Azure) link libcurl, so libarrow carries a
# NEEDED on libcurl.so.4. That soname also exists in /lib64 -- UBI8's curl
# 7.61.1 -- and the image deliberately does NOT put our curl prefix on the
# default library search path, because our build omits HTTP/2 and UBI's curl
# binary would start failing https fetches with CURLE_NOT_BUILT_IN. Carry an
# rpath instead, the same way this script does for arrow's own .pc files below,
# so the loader and auditwheel both reach the 8.17.0 we compile against rather
# than resolving to the older /lib64 copy. Without it the wheel bundles 7.61.1
# and dies on import with "undefined symbol: curl_multi_poll".
CURL_PREFIX=$(find /opt/_internal -maxdepth 1 -name 'curl-*')
if [ -n "${CURL_PREFIX}" ]; then
    cmake_extra_args+=(
        "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,--enable-new-dtags,-rpath=${CURL_PREFIX}/lib"
    )
fi

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
    -DPARQUET_REQUIRE_ENCRYPTION=ON \
    -DARROW_ORC=ON \
    -DARROW_SUBSTRAIT=ON \
    -DARROW_FLIGHT=ON \
    -DARROW_S3=ON \
    -DARROW_GCS=ON \
    -DARROW_AZURE=ON \
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
    -DCMAKE_CXX_FLAGS="${MANYLINUX_CXXFLAGS}" \
    "${cmake_extra_args[@]}" > /dev/null

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
