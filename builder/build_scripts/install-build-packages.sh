#!/bin/bash
# Install packages that will be needed at runtime

# Stop at any error, show all commands
set -exuo pipefail

# Set build environment variables
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# if a devel package is added to COMPILE_DEPS,
# make sure the corresponding library is added to RUNTIME_DEPS if applicable

# Base dependencies that should be available in all RHEL-like distributions
# cmake is needed for libjpeg-turbo, libtiff, and other CMake-based builds
COMPILE_DEPS=(bzip2-devel ncurses-devel gdbm-devel xz-devel openssl openssl-devel libffi-devel kernel-headers perl-IPC-Cmd cmake)

# Optional dependencies (not available in minimal UBI images)
# We build curl and Tcl/Tk from source, so curl-devel and tk-devel are optional
for optional_pkg in readline-devel curl-devel uuid-devel tk-devel; do
	if dnf list available "$optional_pkg" &>/dev/null; then
		COMPILE_DEPS+=("$optional_pkg")
	fi
done

manylinux_pkg_install "${COMPILE_DEPS[@]}"
manylinux_pkg_clean
