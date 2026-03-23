#!/bin/bash
# Update system packages

# Stop at any error, show all commands
set -exuo pipefail

# Get script directory
MY_DIR=$(dirname "${BASH_SOURCE[0]}")

# Get build utilities
# shellcheck source-path=SCRIPTDIR
source "${MY_DIR}/build_utils.sh"

dnf -y upgrade
manylinux_pkg_clean

# do we want to update locales ?
LOCALE_ARCHIVE=/usr/lib/locale/locale-archive
TIMESTAMP_FILE=${LOCALE_ARCHIVE}.ml.timestamp
if [ ! -f "${TIMESTAMP_FILE}" ] || [ "${LOCALE_ARCHIVE}" -nt "${TIMESTAMP_FILE}" ]; then
	# upgrading glibc-common can end with removal on en_US.UTF-8 locale
	localedef -i en_US -f UTF-8 en_US.UTF-8

	# if we updated glibc, we need to strip locales again...
	if localedef --list-archive | grep -sq -v -i ^en_US.utf8; then
		localedef --list-archive | grep -v -i ^en_US.utf8 | xargs localedef --delete-from-archive
	fi
	touch ${TIMESTAMP_FILE}
fi

if [ -d /usr/share/locale ]; then
	find /usr/share/locale -mindepth 1 -maxdepth 1 -not \( -name 'en*' -or -name 'locale.alias' \) -print0 | xargs -0 rm -rf
fi
if [ -d /usr/local/share/locale ]; then
	find /usr/local/share/locale -mindepth 1 -maxdepth 1 -not \( -name 'en*' -or -name 'locale.alias' \) -print0 | xargs -0 rm -rf
fi

if [ "${DEVTOOLSET_ROOTPATH:-}" != "" ]; then
	# remove useless things that have been installed/updated by devtoolset
	if [ -d "${DEVTOOLSET_ROOTPATH}/usr/share/man" ]; then
		rm -rf "${DEVTOOLSET_ROOTPATH}/usr/share/man"
	fi
	if [ -d "${DEVTOOLSET_ROOTPATH}/usr/share/locale" ]; then
		find "${DEVTOOLSET_ROOTPATH}/usr/share/locale" -mindepth 1 -maxdepth 1 -not \( -name 'en*' -or -name 'locale.alias' \) -print0 | xargs -0 rm -rf
	fi
fi

if [ -d /usr/share/backgrounds ]; then
	rm -rf /usr/share/backgrounds
fi

if [ -d /usr/local/share/man ]; then
	# https://github.com/pypa/manylinux/issues/1060
	# wrong /usr/local/man symlink
	# only delete the content
	rm -rf /usr/local/share/man/*
fi

if [ -f /usr/local/lib/libcrypt.so.1 ]; then
	# Remove libcrypt to only use installed libxcrypt instead
	find /lib* /usr/lib* \( -name 'libcrypt.a' -o -name 'libcrypt.so' -o -name 'libcrypt.so.*' -o -name 'libcrypt-2.*.so' \) -delete
fi

ldconfig
