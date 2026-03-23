#!/bin/bash
# Install packages that will be needed at runtime

# Stop at any error, show all commands
set -exuo pipefail

# Set build environment variables
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

# Libraries that are allowed as part of the manylinux2014 profile
# Extract from PEP: https://www.python.org/dev/peps/pep-0599/#the-manylinux2014-policy
# On RPM-based systems, they are provided by these packages:
# Package:    Libraries
# glib2:      libglib-2.0.so.0, libgthread-2.0.so.0, libgobject-2.0.so.0
# glibc:      libresolv.so.2, libutil.so.1, libnsl.so.1, librt.so.1, libpthread.so.0, libdl.so.2, libm.so.6, libc.so.6
# libICE:     libICE.so.6
# libX11:     libX11.so.6
# libXext:    libXext.so.6
# libXrender: libXrender.so.1
# libgcc:     libgcc_s.so.1
# libstdc++:  libstdc++.so.6
# mesa:       libGL.so.1
#
# PEP is missing the package for libSM.so.6 for RPM based system
#
# With PEP600, more packages are allowed by auditwheel policies
# - libz.so.1
# - libexpat.so.1


# MANYLINUX_DEPS: Install development packages (except for libgcc which is provided by gcc install)
# Note: UBI images have a limited package set. Some X11 libraries may not be available.
MANYLINUX_DEPS=(glibc-devel libstdc++-devel glib2-devel zlib-devel expat-devel)
# Try to install X11 libraries if available (not in UBI minimal images)
for pkg in libX11-devel libXext-devel libXrender-devel mesa-libGL-devel libICE-devel libSM-devel; do
	if dnf list available "$pkg" &>/dev/null; then
		MANYLINUX_DEPS+=("$pkg")
	fi
done

# RUNTIME_DEPS: Runtime dependencies. c.f. install-build-packages.sh
RUNTIME_DEPS=(zlib bzip2 expat ncurses readline gdbm xz openssl libcurl uuid libffi tk)

BASE_TOOLS=(autoconf automake bzip2 ca-certificates curl diffutils file make patch unzip)
# Add bison if available (not in UBI minimal images)
if dnf list available bison &>/dev/null; then
	BASE_TOOLS+=(bison)
fi
BASE_TOOLS+=(glibc-locale-source glibc-langpack-en gnupg2 gzip hardlink hostname libcurl libxcrypt which)
# libnsl not available in UBI8, add if present
if dnf list available libnsl &>/dev/null; then
	BASE_TOOLS+=(libnsl)
fi
echo "tsflags=nodocs" >> /etc/dnf/dnf.conf
dnf -y upgrade
EPEL=
if dnf list available epel-release &>/dev/null; then
	EPEL=epel-release
fi
dnf -y install dnf-plugins-core ${EPEL}
# UBI8 already has ubi-8-codeready-builder-rpms enabled by default
dnf config-manager --set-enabled ubi-8-codeready-builder-rpms 2>/dev/null || \
	dnf config-manager --set-enabled codeready-builder-for-rhel-8-*-rpms 2>/dev/null || \
	dnf config-manager --set-enabled powertools 2>/dev/null || true
TOOLCHAIN_DEPS=(gcc-toolset-14-binutils gcc-toolset-14-gcc gcc-toolset-14-gcc-c++ gcc-toolset-14-gcc-gfortran gcc-toolset-14-libatomic-devel)
if [ "${AUDITWHEEL_ARCH}" == "x86_64" ]; then
	# yasm not available in UBI8, add if present (we can build without it if needed)
	if dnf list available yasm &>/dev/null; then
		TOOLCHAIN_DEPS+=(yasm)
	fi
fi

manylinux_pkg_install "${BASE_TOOLS[@]}" "${TOOLCHAIN_DEPS[@]}" "${MANYLINUX_DEPS[@]}" "${RUNTIME_DEPS[@]}"

# update system packages, we already updated them but
# the following script takes care of cleaning-up some things
# and since it's also needed in the finalize step, everything's
# centralized in this script to avoid code duplication
LC_ALL=C "${MY_DIR}/update-system-packages.sh"

# we'll be removing libcrypt.so.1 later on
# this is needed to ensure the new one will be found
# as LD_LIBRARY_PATH does not seem enough.
# c.f. https://github.com/pypa/manylinux/issues/1022
echo "/usr/local/lib" > /etc/ld.so.conf.d/00-manylinux.conf
ldconfig

if [ "${OS_ID_LIKE}-${AUDITWHEEL_ARCH}" == "rhel-i686" ] && [ -f /usr/bin/i686-redhat-linux-gnu-pkg-config ] && [ ! -f /usr/bin/i386-redhat-linux-gnu-pkg-config ]; then
	ln -s i686-redhat-linux-gnu-pkg-config /usr/bin/i386-redhat-linux-gnu-pkg-config
fi
