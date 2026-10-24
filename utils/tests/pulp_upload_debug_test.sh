#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
SCRIPT="${ROOT}/scripts/pulp-upload"

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

make_files() {
  local dest="$1"
  mkdir -p "${dest}"
  printf 'wheel' > "${dest}/pkg-1.0.0-py3-none-any.whl"
  printf 'att' > "${dest}/pkg-1.0.0-py3-none-any.whl.attestation"
}

mockbin="${tmpdir}/bin"
mkdir -p "${mockbin}"

cat > "${mockbin}/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
outfile=""
url=""
for ((i=1;i<=$#;i++)); do
  a="${!i}"
  if [[ "$a" == "-o" ]]; then
    j=$((i+1)); outfile="${!j}"
  elif [[ "$a" == http* ]]; then
    url="$a"
  fi
done

if [[ "$url" == *"repositories/python/python/"* ]]; then
  printf '%s' '{"results":[{"name":"repo","latest_version_href":"/v/1/"}]}' > "$outfile"
  printf '200'
  exit 0
fi

if [[ "$url" == *"content/python/packages/"* ]]; then
  case "${CURL_MODE:-http404_exit0}" in
    http404_exit0)
      printf '%s' '{"results":[],"authorization":"Bearer abc","password":"secret","token":"abc"}' > "$outfile"
      printf '404'
      exit 0
      ;;
    transport_fail)
      printf '%s' '{"results":[],"credentials":"user:pass","api_key":"abcdef"}' > "$outfile"
      printf '000'
      exit 7
      ;;
    oversized_body)
      pad=$(printf 'x%.0s' {1..600})
      printf '%s' "{\"results\":[],\"authorization\":\"Bearer abc\",\"padding\":\"${pad}\"}" > "$outfile"
      printf '404'
      exit 0
      ;;
    twine_upload)
      printf '%s' '{"results":[]}' > "$outfile"
      printf '200'
      exit 0
      ;;
    *)
      printf '%s' '{"error":"unexpected mode"}' > "$outfile"
      printf '500'
      exit 22
      ;;
  esac
fi

printf '%s' '{"error":"unexpected"}' > "$outfile"
printf '500'
exit 22
EOF
chmod +x "${mockbin}/curl"

cat > "${mockbin}/twine" <<'EOF'
#!/usr/bin/env bash
for arg in "$@"; do
  printf 'twine-arg:%s\n' "$arg" >&2
done
exit 1
EOF
chmod +x "${mockbin}/twine"

files_dir="${tmpdir}/files"
make_files "${files_dir}"

run_pulp_upload() {
  local mode="$1"
  local debug_enabled="$2"
  local max_body_chars="$3"
  local tag="$4"

  local stdout_file="${tmpdir}/${tag}-stdout.log"
  local stderr_file="${tmpdir}/${tag}-stderr.log"

  set +e
  (
    export PATH="${mockbin}:$PATH"
    export FILES_DIR="${files_dir}"
    export PULP_BASE_URL="https://user:password@example.invalid"
    export PULP_API_ROOT="/api/"
    export PULP_DOMAIN="d"
    export PULP_REPOSITORY="repo"
    export TWINE_USERNAME="user"
    export TWINE_PASSWORD="password"
    export PULP_UPLOAD_DEBUG="${debug_enabled}"
    if [[ -n "${max_body_chars}" ]]; then
      export PULP_UPLOAD_DEBUG_MAX_BODY_CHARS="${max_body_chars}"
    else
      unset PULP_UPLOAD_DEBUG_MAX_BODY_CHARS
    fi
    export CURL_MODE="${mode}"
    bash "${SCRIPT}"
  ) >"${stdout_file}" 2>"${stderr_file}"
  local rc=$?
  set -e

  LAST_RC=$rc
  LAST_STDOUT="${stdout_file}"
  LAST_STDERR="${stderr_file}"
}

# Test 1: http404_exit0 with secrets redaction, proper stderr routing
run_pulp_upload "http404_exit0" "true" "512" "case_http404"
[[ $LAST_RC -ne 0 ]]
# Debug diagnostics must NEVER appear in stdout (keeps JSON pipeline clean)
if grep -Fq 'DEBUG pulp-upload' "${LAST_STDOUT}"; then
  echo "FAIL: DEBUG logs found in stdout" >&2
  exit 1
fi
# Debug diagnostics MUST appear in stderr
grep -Fq 'DEBUG pulp-upload op=repository_list_lookup' "${LAST_STDERR}"
grep -Fq 'DEBUG pulp-upload op=package_existence_lookup:pkg-1.0.0-py3-none-any.whl' "${LAST_STDERR}"
grep -Fq 'status=404' "${LAST_STDERR}"
grep -Fq 'https://***:***@example.invalid' "${LAST_STDERR}"
! grep -Fq 'user:password@example.invalid' "${LAST_STDERR}"
! grep -Fq 'Bearer abc' "${LAST_STDERR}"
! grep -Fq '"password":"secret"' "${LAST_STDERR}"
! grep -Fq '"token":"abc"' "${LAST_STDERR}"
grep -Fq '\"authorization\":\"\*\*\*\"' "${LAST_STDERR}"
grep -Fq '\"password\":\"\*\*\*\"' "${LAST_STDERR}"
grep -Fq '\"token\":\"\*\*\*\"' "${LAST_STDERR}"
# Short body within 512 char limit must not be truncated
! grep -Fq '…\<truncated\>' "${LAST_STDERR}"

# Test 2: transport_fail with curl transport code and credential redaction
run_pulp_upload "transport_fail" "true" "512" "case_transport"
[[ $LAST_RC -ne 0 ]]
! grep -Fq 'DEBUG pulp-upload' "${LAST_STDOUT}"
grep -Fq 'status=curl_exit_7/http_000' "${LAST_STDERR}"
! grep -Fq '"credentials":"user:pass"' "${LAST_STDERR}"
! grep -Fq '"api_key":"abcdef"' "${LAST_STDERR}"
grep -Fq '\"credentials\":\"\*\*\*\"' "${LAST_STDERR}"
grep -Fq '\"api_key\":\"\*\*\*\"' "${LAST_STDERR}"

# Test 3: Twine upload execution, quoted arguments, and twine diagnostic logging
run_pulp_upload "twine_upload" "true" "512" "case_twine"
[[ $LAST_RC -ne 0 ]]
! grep -Fq 'DEBUG pulp-upload' "${LAST_STDOUT}"
grep -Fq 'DEBUG pulp-upload op=twine_upload_attempt:pkg-1.0.0-py3-none-any.whl' "${LAST_STDERR}"
grep -Fq 'DEBUG pulp-upload op=twine_upload_result:pkg-1.0.0-py3-none-any.whl method=POST' "${LAST_STDERR}"
grep -Fq 'twine-arg:pkg-1.0.0-py3-none-any.whl' "${LAST_STDERR}"
grep -Fq 'twine-arg:pkg-1.0.0-py3-none-any.whl.attestation' "${LAST_STDERR}"

# Test 4: Truncation with explicit small limit
run_pulp_upload "http404_exit0" "true" "25" "case_truncate_small"
[[ $LAST_RC -ne 0 ]]
! grep -Fq 'DEBUG pulp-upload' "${LAST_STDOUT}"
grep -Fq '…\<truncated\>' "${LAST_STDERR}"

# Test 5: Invalid limit falls back to 512 default:
# a) Short body (<512) is NOT truncated even with invalid setting
run_pulp_upload "http404_exit0" "true" "not-a-number" "case_fallback_short"
[[ $LAST_RC -ne 0 ]]
! grep -Fq 'DEBUG pulp-upload' "${LAST_STDOUT}"
! grep -Fq '…\<truncated\>' "${LAST_STDERR}"

# b) Oversized body (>512) IS truncated under fallback
run_pulp_upload "oversized_body" "true" "not-a-number" "case_fallback_oversized"
[[ $LAST_RC -ne 0 ]]
! grep -Fq 'DEBUG pulp-upload' "${LAST_STDOUT}"
grep -Fq '…\<truncated\>' "${LAST_STDERR}"

# Test 6: Disabled by default (PULP_UPLOAD_DEBUG not true)
run_pulp_upload "http404_exit0" "false" "512" "case_disabled"
[[ $LAST_RC -ne 0 ]]
! grep -Fq 'DEBUG pulp-upload' "${LAST_STDOUT}"
! grep -Fq 'DEBUG pulp-upload' "${LAST_STDERR}"

echo "PASS: pulp-upload debug logging redacts secrets, routes to stderr only, bounds body, validates fallback, and covers HTTP/transport failures"
