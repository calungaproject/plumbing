#!/usr/bin/env bash
# Shared helpers for npm pulp release scripts. Source from other scripts:
#   # shellcheck source=npm-common.sh
#   source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/npm-common.sh"

# Fail if the named tar member is missing, empty, or larger than max_bytes.
# Probes with head -c so we never buffer more than max+1 bytes.
assert_tar_member_size() {
  local archive="${1}"
  local member="${2}"
  local max_bytes="${3}"
  local tmp size
  tmp="$(mktemp)"
  # Process substitution avoids a pipefail-sensitive tar|head pipeline:
  # head closes early on truncate; tar's SIGPIPE stays in the subshell.
  head -c "$((max_bytes + 1))" \
    < <(tar -xOf "${archive}" "${member}" 2>/dev/null) \
    > "${tmp}" || true
  size="$(wc -c < "${tmp}" | tr -d ' ')"
  rm -f "${tmp}"
  if [[ -z "${size}" || "${size}" -eq 0 ]]; then
    return 1
  fi
  if [[ "${size}" -gt "${max_bytes}" ]]; then
    echo "ERROR: ${member} in $(basename "${archive}") exceeds" \
      "${max_bytes} bytes" >&2
    return 1
  fi
  return 0
}
