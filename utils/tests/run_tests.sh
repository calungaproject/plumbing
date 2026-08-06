#!/usr/bin/env bash
# Unit tests for plumbing-utils npm release scripts.
# Run from repo:  ./utils/tests/run_tests.sh
# Or via Containerfile test stage.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
SCRIPTS="${ROOT}/scripts"
export PATH="${SCRIPTS}:${PATH}"

# shellcheck disable=SC1091
source "${SCRIPTS}/npm-common.sh"

PASS=0
FAIL=0

assert_eq() {
  local got="$1" want="$2" msg="$3"
  if [[ "${got}" == "${want}" ]]; then
    echo "PASS: ${msg}"
    PASS=$((PASS + 1))
  else
    echo "FAIL: ${msg} (got='${got}' want='${want}')" >&2
    FAIL=$((FAIL + 1))
  fi
}

assert_ok() {
  local msg="$1"
  shift
  if "$@"; then
    echo "PASS: ${msg}"
    PASS=$((PASS + 1))
  else
    echo "FAIL: ${msg}" >&2
    FAIL=$((FAIL + 1))
  fi
}

assert_fail() {
  local msg="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "FAIL: ${msg} (expected failure)" >&2
    FAIL=$((FAIL + 1))
  else
    echo "PASS: ${msg}"
    PASS=$((PASS + 1))
  fi
}

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

# --- assert_tar_member_size ---
pkgdir="${tmpdir}/pkg"
mkdir -p "${pkgdir}/package"
echo '{"name":"x","version":"1.0.0"}' > "${pkgdir}/package/package.json"
tgz="${tmpdir}/x-1.0.0.tgz"
tar -czf "${tgz}" -C "${pkgdir}" package
assert_ok "assert_tar_member_size accepts package.json" \
  assert_tar_member_size "${tgz}" "package/package.json" 1048576
assert_fail "assert_tar_member_size rejects missing member" \
  assert_tar_member_size "${tgz}" "package/missing.json" 1048576

# --- write_status_error / fail_with_status ---
status="${tmpdir}/status"
STATUS_PATH="${status}" write_status_error "boom"
assert_eq "$(cat "${status}")" "ERROR: boom" "write_status_error writes STATUS_PATH"

# --- npm-populate-release-notes empty fails ---
empty_files="${tmpdir}/empty-files"
mkdir -p "${empty_files}"
data="${tmpdir}/data.json"
echo '{"releaseNotes":{"content":{}}}' > "${data}"
assert_fail "npm-populate-release-notes fails with no .tgz" \
  env FILES_DIR="${empty_files}" DATA_FILE="${data}" npm-populate-release-notes

# --- npm-pulp-upload empty fails ---
assert_fail "npm-pulp-upload fails with no .tgz" \
  env FILES_DIR="${empty_files}" \
      PULP_BASE_URL="https://example.invalid" \
      PULP_DOMAIN="d" \
      PULP_REPOSITORY="r" \
      npm-pulp-upload

# --- npm-release-upload missing secret fails ---
sec="${tmpdir}/secret-empty"
mkdir -p "${sec}"
: > "${sec}/username"
: > "${sec}/password"
status2="${tmpdir}/status2"
assert_fail "npm-release-upload fails on empty credentials" \
  env SECRET_DIR="${sec}" STATUS_PATH="${status2}" \
      FILES_DIR="${empty_files}" \
      PULP_BASE_URL="https://example.invalid" \
      PULP_DOMAIN="d" \
      PULP_REPOSITORY="r" \
      npm-release-upload
[[ -f "${status2}" ]] && assert_eq "$(head -n1 "${status2}")" "ERROR: Pulp credential missing or empty: ${sec}/username" \
  "npm-release-upload writes STATUS_PATH on credential failure" \
  || { echo "FAIL: missing STATUS_PATH after credential failure"; FAIL=$((FAIL + 1)); }

# --- npm-release-extract orchestration with PATH stubs ---
stub_bin="${tmpdir}/stubs"
mkdir -p "${stub_bin}"
log="${tmpdir}/calls.log"
: > "${log}"
for cmd in npm-extract-artifacts npm-populate-release-notes npm-fetch-chains-provenance; do
  cat > "${stub_bin}/${cmd}" <<EOF
#!/usr/bin/env bash
echo "${cmd}" >> "${log}"
EOF
  chmod +x "${stub_bin}/${cmd}"
done

workdir="${tmpdir}/workdir"
mkdir -p "${workdir}"
cat > "${workdir}/snapshot.json" <<'EOF'
{
  "components": [
    {"containerImage": "quay.example/repo@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
    {"name": "skip-me"},
    {"containerImage": "quay.example/repo2@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}
  ]
}
EOF
images_txt="${workdir}/images.txt"
data2="${workdir}/data.json"
echo '{}' > "${data2}"
files_dir="${workdir}/files"
mkdir -p "${files_dir}"

assert_ok "npm-release-extract runs with stubbed children" \
  env PATH="${stub_bin}:${SCRIPTS}:${PATH}" \
      TRUSTED_ARTIFACTS_EXTRACT_DIR="${workdir}" \
      SNAPSHOT_PATH="snapshot.json" \
      IMAGES_TXT="${images_txt}" \
      FILES_DIR="${files_dir}" \
      DATA_FILE="${data2}" \
      npm-release-extract

assert_eq "$(wc -l < "${images_txt}" | tr -d ' ')" "2" "extract writes two image refs"
assert_eq "$(tr '\n' ' ' < "${log}" | tr -s ' ')" \
  "npm-extract-artifacts npm-populate-release-notes npm-fetch-chains-provenance " \
  "extract calls children in order"

# missing snapshot fails
assert_fail "npm-release-extract fails without snapshot" \
  env PATH="${stub_bin}:${SCRIPTS}:${PATH}" \
      TRUSTED_ARTIFACTS_EXTRACT_DIR="${workdir}" \
      SNAPSHOT_PATH="missing.json" \
      IMAGES_TXT="${images_txt}" \
      FILES_DIR="${files_dir}" \
      DATA_FILE="${data2}" \
      npm-release-extract

# --- npm-pulp-upload digest match (skip) and digest conflict (fail) ---
pulp_files="${tmpdir}/pulp-files"
mkdir -p "${pulp_files}"
cp "${tgz}" "${pulp_files}/lodash-4.17.21.tgz"
# Rename package.json inside is already name x; rewrite tarball as lodash for upload
pulp_pkg="${tmpdir}/lodash-pkg"
mkdir -p "${pulp_pkg}/package"
jq -nc '{name:"lodash",version:"4.17.21"}' > "${pulp_pkg}/package/package.json"
lodash_tgz="${pulp_files}/lodash-4.17.21.tgz"
tar -czf "${lodash_tgz}" -C "${pulp_pkg}" package
local_sha="$(sha256sum "${lodash_tgz}" | awk '{print $1}')"

# Shared mock curl for digest scenarios (state via MOCK_MODE env)
mock_curl_bin="${tmpdir}/mock-curl"
mkdir -p "${mock_curl_bin}"
cat > "${mock_curl_bin}/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
joined="$*"
# Repo list
if [[ "${joined}" == *"/repositories/npm/npm/"* && "${joined}" != *"/content/"* ]]; then
  echo '{"results":[{"name":"npm-registry","pulp_href":"/api/pulp/d/api/v3/repositories/npm/npm/r/","latest_version_href":"/api/pulp/d/api/v3/repositories/npm/npm/r/versions/1/"}]}'
  exit 0
fi
# Content list
if [[ "${joined}" == *"/content/npm/packages/"* && "${joined}" == *"--data-urlencode"* ]]; then
  echo "{\"count\":1,\"results\":[{\"name\":\"lodash\",\"version\":\"4.17.21\",\"pulp_href\":\"/api/pulp/d/api/v3/content/npm/packages/x/\",\"artifact\":\"/api/pulp/d/api/v3/artifacts/${MOCK_REMOTE_SHA}/\",\"pulp_labels\":{}}]}"
  exit 0
fi
# Artifact GET
if [[ "${joined}" == *"/artifacts/"* ]]; then
  echo "{\"sha256\":\"${MOCK_REMOTE_SHA}\"}"
  exit 0
fi
# Label set (digest-match path still applies labels)
if [[ "${joined}" == *"set_label/"* ]]; then
  echo '{}'
  exit 0
fi
# Upload should not be reached on match; allow on conflict path failures
if [[ "${joined}" == *"/content/npm/packages/upload/"* ]]; then
  echo "mock curl: unexpected upload" >&2
  exit 22
fi
echo "mock curl: unhandled: ${joined}" >&2
exit 22
EOF
chmod +x "${mock_curl_bin}/curl"

sec_ok="${tmpdir}/secret-ok"
mkdir -p "${sec_ok}"
echo user > "${sec_ok}/username"
echo pass > "${sec_ok}/password"

assert_ok "npm-pulp-upload skips when remote sha256 matches" \
  env PATH="${mock_curl_bin}:${PATH}" \
      FILES_DIR="${pulp_files}" \
      SECRET_DIR="${sec_ok}" \
      PULP_BASE_URL="https://example.invalid" \
      PULP_API_ROOT="/api/" \
      PULP_DOMAIN="d" \
      PULP_REPOSITORY="npm-registry" \
      MOCK_REMOTE_SHA="${local_sha}" \
      npm-pulp-upload

assert_fail "npm-pulp-upload fails when remote sha256 conflicts" \
  env PATH="${mock_curl_bin}:${PATH}" \
      FILES_DIR="${pulp_files}" \
      SECRET_DIR="${sec_ok}" \
      PULP_BASE_URL="https://example.invalid" \
      PULP_API_ROOT="/api/" \
      PULP_DOMAIN="d" \
      PULP_REPOSITORY="npm-registry" \
      MOCK_REMOTE_SHA="0000000000000000000000000000000000000000000000000000000000000000" \
      npm-pulp-upload

echo
echo "Results: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
