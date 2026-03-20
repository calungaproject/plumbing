#!/bin/bash
# Top-level build script called from Dockerfile

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Install a more recent Rust
check_var "${RUST_VERSION}"
check_var "${RUST_HASH}"
check_var "${RUST_DOWNLOAD_URL}"

PREFIX=/opt/_internal/rust-${RUST_VERSION}

# Download and verify rustup-init
RUSTUP_INIT="rustup-init"
if [ "${AUDITWHEEL_ARCH}" == "x86_64" ]; then
    RUSTUP_ARCH="x86_64-unknown-linux-gnu"
elif [ "${AUDITWHEEL_ARCH}" == "aarch64" ]; then
    RUSTUP_ARCH="aarch64-unknown-linux-gnu"
elif [ "${AUDITWHEEL_ARCH}" == "i686" ]; then
    RUSTUP_ARCH="i686-unknown-linux-gnu"
elif [ "${AUDITWHEEL_ARCH}" == "armv7l" ]; then
    RUSTUP_ARCH="armv7-unknown-linux-gnueabihf"
else
    echo "Unsupported architecture: ${AUDITWHEEL_ARCH}"
    exit 1
fi

fetch_source "${RUSTUP_INIT}" "${RUST_DOWNLOAD_URL}/${RUSTUP_ARCH}"
check_sha256sum "${RUSTUP_INIT}" "${RUST_HASH}"
chmod +x "${RUSTUP_INIT}"

# Install Rust using rustup to PREFIX
RUSTUP_HOME="${PREFIX}/rustup"
CARGO_HOME="${PREFIX}/cargo"
export RUSTUP_HOME CARGO_HOME

./"${RUSTUP_INIT}" -y --default-toolchain "${RUST_VERSION}" --profile minimal --no-modify-path

# Create symlinks for runtime
mkdir -p /manylinux-rootfs"${PREFIX}"
cp -r "${CARGO_HOME}" /manylinux-rootfs"${PREFIX}"/
cp -r "${RUSTUP_HOME}" /manylinux-rootfs"${PREFIX}"/

# Create wrapper scripts that set environment variables
mkdir -p /manylinux-rootfs/usr/local/bin
cat > /manylinux-rootfs/usr/local/bin/rustc <<EOF
#!/bin/bash
export RUSTUP_HOME="${PREFIX}/rustup"
export CARGO_HOME="${PREFIX}/cargo"
exec "${PREFIX}/cargo/bin/rustc" "\$@"
EOF
chmod +x /manylinux-rootfs/usr/local/bin/rustc

cat > /manylinux-rootfs/usr/local/bin/cargo <<EOF
#!/bin/bash
export RUSTUP_HOME="${PREFIX}/rustup"
export CARGO_HOME="${PREFIX}/cargo"
exec "${PREFIX}/cargo/bin/cargo" "\$@"
EOF
chmod +x /manylinux-rootfs/usr/local/bin/cargo

cat > /manylinux-rootfs/usr/local/bin/rustup <<EOF
#!/bin/bash
export RUSTUP_HOME="${PREFIX}/rustup"
export CARGO_HOME="${PREFIX}/cargo"
exec "${PREFIX}/cargo/bin/rustup" "\$@"
EOF
chmod +x /manylinux-rootfs/usr/local/bin/rustup

# Clean up
rm -f "${RUSTUP_INIT}"

# Strip what we can (be careful with Rust binaries, some stripping can break them)
# strip_ /manylinux-rootfs  # Commented out to avoid breaking Rust binaries

# Install for build
mkdir /manylinux-buildfs
cp -rlf /manylinux-rootfs/* /manylinux-buildfs/

# Verify installation
export RUSTUP_HOME="${PREFIX}/rustup"
export CARGO_HOME="${PREFIX}/cargo"
"${PREFIX}/cargo/bin/rustc" --version
"${PREFIX}/cargo/bin/cargo" --version
