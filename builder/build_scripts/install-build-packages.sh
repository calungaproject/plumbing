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

if [ "${OS_ID_LIKE}" = "rhel" ]; then
	# Base dependencies that should be available in all RHEL-like distributions
	# cmake is needed for libjpeg-turbo, libtiff, and other CMake-based builds
	COMPILE_DEPS=(bzip2-devel ncurses-devel gdbm-devel xz-devel openssl openssl-devel libffi-devel kernel-headers perl-IPC-Cmd cmake)

	# Optional dependencies (not available in minimal UBI images)
	# We build curl and Tcl/Tk from source, so curl-devel and tk-devel are optional
	for optional_pkg in readline-devel curl-devel uuid-devel; do
		if dnf list available "$optional_pkg" &>/dev/null; then
			COMPILE_DEPS+=("$optional_pkg")
		fi
	done

	if [ "${AUDITWHEEL_POLICY}" == "manylinux2014" ]; then
		COMPILE_DEPS+=(libXft-devel)
		# Optional for manylinux2014 - we rebuild curl
		for optional_pkg in keyutils-libs-devel krb5-devel libcom_err-devel libidn-devel; do
			if dnf list available "$optional_pkg" &>/dev/null; then
				COMPILE_DEPS+=("$optional_pkg")
			fi
		done
	elif [ "${AUDITWHEEL_POLICY}" == "manylinux_2_28" ]; then
		# tk-devel optional - we build Tcl/Tk from source
		if dnf list available tk-devel &>/dev/null; then
			COMPILE_DEPS+=(tk-devel)
		fi
	else
		# tk-devel optional - we build Tcl/Tk from source
		if dnf list available tk-devel &>/dev/null; then
			COMPILE_DEPS+=(tk-devel)
		fi
	fi
elif [ "${OS_ID_LIKE}" == "debian" ]; then
	COMPILE_DEPS=(libbz2-dev libncurses-dev libreadline-dev tk-dev libgdbm-dev libdb-dev liblzma-dev openssl libssl-dev libcurl4-openssl-dev uuid-dev libffi-dev linux-headers-generic)
elif [ "${OS_ID_LIKE}" == "alpine" ]; then
	COMPILE_DEPS=(bzip2-dev ncurses-dev readline-dev tk-dev gdbm-dev xz-dev openssl openssl-dev curl-dev util-linux-dev libffi-dev linux-headers)
else
	echo "Unsupported policy: '${AUDITWHEEL_POLICY}'"
	exit 1
fi

manylinux_pkg_install "${COMPILE_DEPS[@]}"
manylinux_pkg_clean
