#!/bin/bash
# Helper utilities for build


# use all flags used by ubuntu 20.04 for hardening builds, dpkg-buildflags --export
# other flags mentioned in https://wiki.ubuntu.com/ToolChain/CompilerFlags can't be
# used because the distros used here are too old
MANYLINUX_CPPFLAGS="-Wdate-time -D_FORTIFY_SOURCE=2"
MANYLINUX_CFLAGS="-g -O2 -Wall -fdebug-prefix-map=/=. -fstack-protector-strong -Wformat -Werror=format-security"
MANYLINUX_CXXFLAGS="-g -O2 -Wall -fdebug-prefix-map=/=. -fstack-protector-strong -Wformat -Werror=format-security"
MANYLINUX_LDFLAGS="-Wl,-Bsymbolic-functions -Wl,-z,relro -Wl,-z,now"

export BASE_POLICY=manylinux
PACKAGE_MANAGER=dnf
OS_ID_LIKE=rhel

function check_var {
	if [ -z "$1" ]; then
		echo "required variable not defined"
		exit 1
	fi
}


function fetch_source {
	# This is called both inside and outside the build context (e.g. in Travis) to prefetch
	# source tarballs, where curl exists (and works).
	# Optional third argument: fallback URL tried after all preferred-source attempts are exhausted.
	# Without a fallback the original single-URL behaviour (--retry 10) is preserved.
	local file=$1
	check_var "${file}"
	local url=$2
	check_var "${url}"
	local fallback_url=${3:-}

	if [ -f "${file}" ]; then
		echo "${file} exists, skipping fetch"
		return 0
	fi

	if [ -z "${fallback_url}" ]; then
		curl -fsSL --retry 10 -o "${file}" "${url}/${file}"
		return
	fi

	local preferred_attempts=3
	local fallback_attempts=3
	local attempt rc

	for ((attempt = 1; attempt <= preferred_attempts; attempt++)); do
		echo "Fetching ${file} from ${url} (attempt ${attempt}/${preferred_attempts})"
		if curl -fsSL -o "${file}" "${url}/${file}"; then
			return 0
		else
			rc=$?
		fi
		echo "Attempt ${attempt}/${preferred_attempts} failed (curl exit code: ${rc})" >&2
		rm -f "${file}"
	done

	echo "Preferred source ${url} unavailable after ${preferred_attempts} attempts; falling back to ${fallback_url}" >&2

	for ((attempt = 1; attempt <= fallback_attempts; attempt++)); do
		echo "Fetching ${file} from ${fallback_url} (attempt ${attempt}/${fallback_attempts})"
		if curl -fsSL -o "${file}" "${fallback_url}/${file}"; then
			return 0
		else
			rc=$?
		fi
		echo "Fallback attempt ${attempt}/${fallback_attempts} failed (curl exit code: ${rc})" >&2
		rm -f "${file}"
	done

	echo "Both preferred and fallback sources failed" >&2
	return "${rc}"
}


function check_sha256sum {
	local fname=$1
	check_var "${fname}"
	local sha256=$2
	check_var "${sha256}"

	echo "${sha256}  ${fname}" > "${fname}.sha256"
	sha256sum -c "${fname}.sha256"
	rm -f "${fname}.sha256"
}

# shellcheck disable=SC2120 # optional arguments
function do_standard_install {
	./configure "$@" CPPFLAGS="${MANYLINUX_CPPFLAGS}" CFLAGS="${MANYLINUX_CFLAGS}" "CXXFLAGS=${MANYLINUX_CXXFLAGS}" LDFLAGS="${MANYLINUX_LDFLAGS}" > /dev/null
	make > /dev/null
	make install > /dev/null
}

function strip_ {
	# Strip what we can -- and ignore errors, because this just attempts to strip
	# *everything*, including non-ELF files:
	find "$1" -type f -print0 | xargs -0 -n1 strip --strip-unneeded 2>/dev/null || true
}

function clean_pyc {
	find "$1" -type f -a \( -name '*.pyc' -o -name '*.pyo' \) -delete
}

function manylinux_pkg_install {
	dnf -y install --setopt install_weak_deps=0 --allowerasing "$@"
}

function manylinux_pkg_remove {
	dnf erase -y "$@"
}

function manylinux_pkg_clean {
	dnf clean all
	rm -rf /var/cache/dnf
}
