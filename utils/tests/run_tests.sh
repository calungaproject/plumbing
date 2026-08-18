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

# Shared mock curl for digest scenarios (state via MOCK_REMOTE_SHA env)
mock_curl_bin="${tmpdir}/mock-curl"
mkdir -p "${mock_curl_bin}"
cat > "${mock_curl_bin}/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
joined="$*"
# Repo list (modify/ also contains this path)
if [[ "${joined}" == *"/repositories/npm/npm/"* \
   && "${joined}" != *"/content/"* \
   && "${joined}" != *"modify/"* ]]; then
  echo '{"results":[{"name":"npm-registry","pulp_href":"/api/pulp/d/api/v3/repositories/npm/npm/r/","latest_version_href":"/api/pulp/d/api/v3/repositories/npm/npm/r/versions/1/"}]}'
  exit 0
fi
# Content list — RH Pulp rejects the version filter
if [[ "${joined}" == *"/content/npm/packages/"* && "${joined}" == *"--data-urlencode"* ]]; then
  if [[ "${joined}" == *"--data-urlencode version="* ]]; then
    echo '{"errors":["Invalid Filter: '"'"'version'"'"'"]}'
    exit 22
  fi
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

# --- npm-pulp-upload RH API dry-run: list without version, upload without
# repository, then repository modify + task poll ---
rh_mock_bin="${tmpdir}/rh-mock-curl"
mkdir -p "${rh_mock_bin}"
rh_call_log="${tmpdir}/rh-api-calls.log"
: > "${rh_call_log}"
cat > "${rh_mock_bin}/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
joined="$*"
printf '%s\n' "${joined}" >> "${RH_CALL_LOG}"

# RH list rejects version= (exact production error)
if [[ "${joined}" == *"/content/npm/packages/"* \
   && "${joined}" != *"/upload/"* \
   && "${joined}" == *"--data-urlencode version="* ]]; then
  echo '{"errors":["Invalid Filter: '"'"'version'"'"'"]}'
  exit 22
fi

# Sync upload rejects repository= (exact production error)
if [[ "${joined}" == *"/content/npm/packages/upload/"* ]]; then
  if [[ "${joined}" == *"--form-string repository="* \
     || "${joined}" == *"-F repository="* ]]; then
    echo '{"repository":["Unexpected field"]}'
    exit 22
  fi
  echo '{"pulp_href":"/api/pulp/d/api/v3/content/npm/packages/new/","name":"lodash","version":"4.17.21"}'
  exit 0
fi

if [[ "${joined}" == *"modify/"* ]]; then
  if [[ "${joined}" != *add_content_units* ]]; then
    echo '{"add_content_units":["This field is required."]}'
    exit 22
  fi
  echo '{"task":"/api/pulp/d/api/v3/tasks/t1/"}'
  exit 0
fi

if [[ "${joined}" == *"/tasks/"* ]]; then
  echo '{"state":"completed"}'
  exit 0
fi

if [[ "${joined}" == *"/repositories/npm/npm/"* && "${joined}" != *"/content/"* ]]; then
  echo '{"results":[{"name":"npm-registry","pulp_href":"/api/pulp/d/api/v3/repositories/npm/npm/r/","latest_version_href":"/api/pulp/d/api/v3/repositories/npm/npm/r/versions/1/"}]}'
  exit 0
fi

# Other versions of the same name must not look like "already exists"
if [[ "${joined}" == *"/content/npm/packages/"* && "${joined}" == *"--data-urlencode"* ]]; then
  echo '{"count":1,"next":null,"results":[{"name":"lodash","version":"4.17.20","pulp_href":"/api/pulp/d/api/v3/content/npm/packages/old/","artifact":"/api/pulp/d/api/v3/artifacts/old/","pulp_labels":{}}]}'
  exit 0
fi

echo "mock curl: unhandled: ${joined}" >&2
exit 22
EOF
chmod +x "${rh_mock_bin}/curl"

assert_ok "npm-pulp-upload RH API dry-run (upload + modify)" \
  env PATH="${rh_mock_bin}:${PATH}" \
      FILES_DIR="${pulp_files}" \
      SECRET_DIR="${sec_ok}" \
      PULP_BASE_URL="https://example.invalid" \
      PULP_API_ROOT="/api/" \
      PULP_DOMAIN="d" \
      PULP_REPOSITORY="npm-registry" \
      PULP_TASK_POLL_SECONDS=0 \
      PULP_TASK_TIMEOUT_SECONDS=30 \
      RH_CALL_LOG="${rh_call_log}" \
      npm-pulp-upload

if grep -q -- '--data-urlencode version=' "${rh_call_log}"; then
  echo "FAIL: list query still sent version= filter" >&2
  FAIL=$((FAIL + 1))
else
  echo "PASS: list query did not send version= filter"
  PASS=$((PASS + 1))
fi
if grep -q -- '--form-string repository=' "${rh_call_log}"; then
  echo "FAIL: sync upload still sent repository=" >&2
  FAIL=$((FAIL + 1))
else
  echo "PASS: sync upload did not send repository="
  PASS=$((PASS + 1))
fi
if grep -q 'packages/upload/' "${rh_call_log}" \
   && grep -q 'modify/' "${rh_call_log}" \
   && grep -q '/tasks/' "${rh_call_log}"; then
  echo "PASS: dry-run issued upload, modify, and task poll"
  PASS=$((PASS + 1))
else
  echo "FAIL: dry-run missing upload/modify/task calls" >&2
  cat "${rh_call_log}" >&2
  FAIL=$((FAIL + 1))
fi

# --- npm-fetch-chains-provenance: SLSA v0.2 (cluster) and v1 ---
HEX="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
IMG="quay.example/npm@sha256:${HEX}"
prov_root="${tmpdir}/prov"
mkdir -p "${prov_root}"
images_prov="${prov_root}/images.txt"
printf '%s\n' "${IMG}" > "${images_prov}"
files_prov="${prov_root}/files"
mkdir -p "${files_prov}"

envelope_from_statement() {
  local statement="$1"
  local payload
  payload="$(printf '%s' "${statement}" | base64 | tr -d '\n')"
  jq -nc --arg payload "${payload}" '{
    payloadType: "application/vnd.in-toto+json",
    payload: $payload,
    signatures: [{keyid: "", sig: "mock"}]
  }'
}

v02_statement() {
  local runtime="$1" ns="$2" hex="$3"
  jq -nc --arg runtime "${runtime}" --arg ns "${ns}" --arg hex "${hex}" '{
    "_type": "https://in-toto.io/Statement/v0.1",
    "predicateType": "https://slsa.dev/provenance/v0.2",
    "subject": [{"name": "quay.example/npm", "digest": {"sha256": $hex}}],
    "predicate": {
      "builder": {"id": "https://tekton.dev/chains/v2"},
      "buildType": "tekton.dev/v1/PipelineRun",
      "invocation": {
        "configSource": {},
        "parameters": {},
        "environment": {
          "labels": {"pipelines.openshift.io/runtime": $runtime},
          "annotations": {
            "pipelinesascode.tekton.dev/log-url":
              ("https://konflux-ui.example/ns/" + $ns + "/pipelinerun/x")
          }
        }
      },
      "buildConfig": {"tasks": []},
      "metadata": {"buildStartedOn": "2026-08-13T15:53:47Z"}
    }
  }'
}

v1_statement() {
  local pname="$1" invoc="$2" hex="$3"
  jq -nc --arg pname "${pname}" --arg invoc "${invoc}" --arg hex "${hex}" '{
    "_type": "https://in-toto.io/Statement/v0.1",
    "predicateType": "https://slsa.dev/provenance/v1",
    "subject": [{"name": "quay.example/npm", "digest": {"sha256": $hex}}],
    "predicate": {
      "buildDefinition": {
        "buildType": "https://tekton.dev/chains/v2/slsa",
        "externalParameters": {
          "runSpec": {"pipelineRef": {"name": $pname}, "params": []}
        }
      },
      "runDetails": {
        "builder": {"id": "https://konflux-ci.dev/chains/v2"},
        "metadata": {"invocationId": $invoc}
      }
    }
  }'
}

fetch_stubs="${tmpdir}/fetch-stubs"
mkdir -p "${fetch_stubs}"
cat > "${fetch_stubs}/select-oci-auth" <<'EOF'
#!/usr/bin/env bash
echo '{"auths":{}}'
EOF
cat > "${fetch_stubs}/cosign" <<'EOF'
#!/usr/bin/env bash
if [[ "${1}" == "verify-attestation" ]]; then
  cat "${COSIGN_ENVELOPE_FILE}"
  exit 0
fi
exit 0
EOF
chmod +x "${fetch_stubs}/select-oci-auth" "${fetch_stubs}/cosign"

run_fetch() {
  env PATH="${fetch_stubs}:${PATH}" \
      FILES_DIR="${files_prov}" \
      IMAGES_TXT="${images_prov}" \
      TRUSTED_PROVENANCE_NAMESPACES="calunga-tenant" \
      COSIGN_ENVELOPE_FILE="${1}" \
      npm-fetch-chains-provenance
}

env_v02="${tmpdir}/env-v02.json"
envelope_from_statement "$(v02_statement promote-npm calunga-tenant "${HEX}")" > "${env_v02}"
rm -rf "${files_prov}/chains-provenance"
assert_ok "npm-fetch-chains-provenance accepts SLSA v0.2 promote-npm" \
  run_fetch "${env_v02}"
assert_ok "v0.2 provenance file has tekton Chains builder" \
  jq -e '.predicate.builder.id == "https://tekton.dev/chains/v2"' \
    "${files_prov}/chains-provenance/sha256_${HEX}.json" >/dev/null

env_v1="${tmpdir}/env-v1.json"
envelope_from_statement "$(v1_statement promote-npm "calunga-tenant/pr-1" "${HEX}")" > "${env_v1}"
rm -rf "${files_prov}/chains-provenance"
assert_ok "npm-fetch-chains-provenance accepts SLSA v1 promote-npm" \
  run_fetch "${env_v1}"
assert_ok "v1 provenance file has buildDefinition" \
  jq -e '.predicate.buildDefinition.buildType == "https://tekton.dev/chains/v2/slsa"' \
    "${files_prov}/chains-provenance/sha256_${HEX}.json" >/dev/null

env_bad_rt="${tmpdir}/env-bad-rt.json"
envelope_from_statement "$(v02_statement docker-build calunga-tenant "${HEX}")" > "${env_bad_rt}"
rm -rf "${files_prov}/chains-provenance"
assert_fail "npm-fetch-chains-provenance rejects non-npm pipeline runtime" \
  run_fetch "${env_bad_rt}"

env_bad_ns="${tmpdir}/env-bad-ns.json"
envelope_from_statement "$(v02_statement promote-npm other-tenant "${HEX}")" > "${env_bad_ns}"
rm -rf "${files_prov}/chains-provenance"
assert_fail "npm-fetch-chains-provenance rejects other tenant namespace" \
  run_fetch "${env_bad_ns}"

env_bad_hex="${tmpdir}/env-bad-hex.json"
envelope_from_statement "$(v02_statement promote-npm calunga-tenant \
  "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")" > "${env_bad_hex}"
rm -rf "${files_prov}/chains-provenance"
assert_fail "npm-fetch-chains-provenance rejects subject digest mismatch" \
  run_fetch "${env_bad_hex}"

echo
echo "Results: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
