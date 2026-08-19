#!/usr/bin/env bash
# Drive the production npm-pulp-upload REST path against a live Pulp.
#
# Same API + labels as plumbing utils/scripts/npm-pulp-upload (what RSC
# upload-npm-pulp runs after the plumbing-utils image pin):
#   GET  .../repositories/npm/npm/?name=<repo>
#   GET  .../content/npm/packages/?name=&repository_version=  (no version=)
#   POST .../content/npm/packages/upload/   file, name, version, pulp_labels
#                                          (no repository)
#   POST {repo_href}modify/                 {"add_content_units":[href]}
#   GET  {task} until state=completed
# Label key: tl.compliance_level  (from adjacent *.tl-compliance.json)
#
# Defaults match the merged calunga-push-npm-to-pulp-prod RPA.
#
# Example:
#   export PULP_USERNAME='...'
#   export PULP_PASSWORD='...'
#   ./hack/npm-pulp-api-probe.sh --package /path/to/express-4.22.0.tgz
#
# macOS: npm-pulp-upload uses GNU `readlink -f`. Install coreutils and this
# probe will prepend it to PATH:
#   brew install coreutils
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPLOAD_SCRIPT="${SCRIPT_DIR}/../utils/scripts/npm-pulp-upload"

# npm-pulp-upload uses GNU `readlink -f`; this probe also needs `sha256sum`.
# On macOS, Homebrew coreutils puts those on PATH under libexec/gnubin.
ensure_gnu_coreutils_path() {
  if readlink -f / >/dev/null 2>&1 && command -v sha256sum >/dev/null 2>&1; then
    return 0
  fi
  local prefixes=()
  local p
  prefixes+=(
    /opt/homebrew/opt/coreutils/libexec/gnubin
    /usr/local/opt/coreutils/libexec/gnubin
  )
  if command -v brew >/dev/null 2>&1; then
    p="$(brew --prefix coreutils 2>/dev/null || true)"
    if [[ -n "${p}" ]]; then
      prefixes+=("${p}/libexec/gnubin")
    fi
  fi
  for p in "${prefixes[@]}"; do
    if [[ -x "${p}/readlink" ]]; then
      export PATH="${p}:${PATH}"
      if readlink -f / >/dev/null 2>&1; then
        echo "Using GNU coreutils from ${p}"
        return 0
      fi
    fi
  done
  cat >&2 <<'EOF'
ERROR: GNU coreutils are required (readlink -f, sha256sum).
macOS ships BSD readlink, which has no -f.

Install and retry:

  brew install coreutils

This probe prepends $(brew --prefix coreutils)/libexec/gnubin to PATH when that
directory exists. You can also add it to your shell profile.
EOF
  exit 1
}

# Merged RPA: config/.../ReleasePlanAdmission/calunga/calunga-push-npm-to-pulp-prod.yaml
PULP_BASE_URL="${PULP_BASE_URL:-https://packages.redhat.com}"
PULP_API_ROOT="${PULP_API_ROOT:-/api/}"
PULP_DOMAIN="${PULP_DOMAIN:-public-trusted-libraries}"
PULP_REPOSITORY="${PULP_REPOSITORY:-npm-registry}"
# Production pipeline omits fileRepository (labels only).
PULP_FILE_REPOSITORY="${PULP_FILE_REPOSITORY:-}"

PACKAGE=""
COMPLIANCE_LEVEL="L1"
USERNAME="${PULP_USERNAME:-}"
PASSWORD="${PULP_PASSWORD:-}"
PASSWORD_FILE=""
SECRET_DIR_IN=""
VERIFY_ONLY=false

usage() {
  cat <<EOF
Usage: $(basename "$0") --package FILE [options]

Upload one npm .tgz through the same Pulp REST sequence RSC/plumbing use.

Required:
  --package, -f FILE         Path to a .tgz (e.g. express-4.22.0.tgz)

Credentials (first match wins):
  --secret-dir DIR           Tekton-style dir with username and password files
  --username, -u NAME        Or env PULP_USERNAME
  --password-file FILE       File containing the password (preferred over -p)
  --password, -p PASS        Or env PULP_PASSWORD (visible in ps / shell history)

Options:
  --compliance-level LEVEL   L1, L2, or L3 (default: L1). Writes the same
                             *.tl-compliance.json sidecar npm-pulp-upload reads
                             and sets pulp_labels tl.compliance_level.
  --no-label                 Do not send a compliance label (no sidecar).
  --verify-only              Skip upload; only list name@version in the repo.
  --base-url URL             default: ${PULP_BASE_URL}
  --api-root PATH            default: ${PULP_API_ROOT}
  --domain NAME              default: ${PULP_DOMAIN}
  --repository NAME          default: ${PULP_REPOSITORY}
  -h, --help

PULP_FILE_REPOSITORY is left empty unless you export it, matching production.

macOS: brew install coreutils
  (GNU readlink -f; this script prepends coreutils to PATH when needed)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --package|-f)
      [[ $# -lt 2 ]] && { echo "ERROR: $1 requires a value" >&2; exit 1; }
      PACKAGE="$2"; shift 2 ;;
    --compliance-level)
      [[ $# -lt 2 ]] && { echo "ERROR: $1 requires a value" >&2; exit 1; }
      COMPLIANCE_LEVEL="$2"; shift 2 ;;
    --no-label) COMPLIANCE_LEVEL=""; shift ;;
    --verify-only) VERIFY_ONLY=true; shift ;;
    --username|-u)
      [[ $# -lt 2 ]] && { echo "ERROR: $1 requires a value" >&2; exit 1; }
      USERNAME="$2"; shift 2 ;;
    --password|-p)
      [[ $# -lt 2 ]] && { echo "ERROR: $1 requires a value" >&2; exit 1; }
      PASSWORD="$2"; shift 2 ;;
    --password-file)
      [[ $# -lt 2 ]] && { echo "ERROR: $1 requires a value" >&2; exit 1; }
      PASSWORD_FILE="$2"; shift 2 ;;
    --secret-dir)
      [[ $# -lt 2 ]] && { echo "ERROR: $1 requires a value" >&2; exit 1; }
      SECRET_DIR_IN="$2"; shift 2 ;;
    --base-url)
      [[ $# -lt 2 ]] && { echo "ERROR: $1 requires a value" >&2; exit 1; }
      PULP_BASE_URL="$2"; shift 2 ;;
    --api-root)
      [[ $# -lt 2 ]] && { echo "ERROR: $1 requires a value" >&2; exit 1; }
      PULP_API_ROOT="$2"; shift 2 ;;
    --domain)
      [[ $# -lt 2 ]] && { echo "ERROR: $1 requires a value" >&2; exit 1; }
      PULP_DOMAIN="$2"; shift 2 ;;
    --repository)
      [[ $# -lt 2 ]] && { echo "ERROR: $1 requires a value" >&2; exit 1; }
      PULP_REPOSITORY="$2"; shift 2 ;;
    --)
      shift; break ;;
    -*)
      echo "ERROR: unknown option $1" >&2
      usage >&2
      exit 1 ;;
    *)
      if [[ -n "${PACKAGE}" ]]; then
        echo "ERROR: unexpected argument '$1'" >&2
        exit 1
      fi
      PACKAGE="$1"
      shift ;;
  esac
done

if [[ -z "${PACKAGE}" ]]; then
  echo "ERROR: --package is required" >&2
  usage >&2
  exit 1
fi
if [[ ! -f "${PACKAGE}" ]]; then
  echo "ERROR: package not found: ${PACKAGE}" >&2
  exit 1
fi
if [[ "${PACKAGE}" != *.tgz ]]; then
  echo "ERROR: package must be a .tgz: ${PACKAGE}" >&2
  exit 1
fi
if [[ -n "${COMPLIANCE_LEVEL}" && ! "${COMPLIANCE_LEVEL}" =~ ^L[123]$ ]]; then
  echo "ERROR: --compliance-level must be L1, L2, or L3 (got '${COMPLIANCE_LEVEL}')" >&2
  exit 1
fi
if [[ ! -f "${UPLOAD_SCRIPT}" ]]; then
  echo "ERROR: production uploader not found: ${UPLOAD_SCRIPT}" >&2
  exit 1
fi

ensure_gnu_coreutils_path

for cmd in jq curl tar sha256sum; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${cmd}" >&2
    exit 1
  fi
done

if ! pkg_json="$(tar -xOf "${PACKAGE}" package/package.json 2>/dev/null)"; then
  echo "ERROR: ${PACKAGE} has no package/package.json" >&2
  exit 1
fi
PKG_NAME="$(jq -r '.name // empty' <<<"${pkg_json}")"
PKG_VERSION="$(jq -r '.version // empty' <<<"${pkg_json}")"
if [[ -z "${PKG_NAME}" || -z "${PKG_VERSION}" ]]; then
  echo "ERROR: package.json missing name/version" >&2
  exit 1
fi
LOCAL_SHA="$(sha256sum "${PACKAGE}" | awk '{print $1}')"

if [[ -n "${PASSWORD_FILE}" ]]; then
  PASSWORD="$(< "${PASSWORD_FILE}")"
fi

workdir="$(mktemp -d "${TMPDIR:-/tmp}/npm-pulp-api-probe.XXXXXX")"
cleanup() { rm -rf "${workdir}"; }
trap cleanup EXIT
umask 077

if [[ -n "${SECRET_DIR_IN}" ]]; then
  SECRET_DIR="${SECRET_DIR_IN}"
else
  if [[ -z "${USERNAME}" || -z "${PASSWORD}" ]]; then
    echo "ERROR: provide --secret-dir, or username + password" >&2
    echo "       (--username/--password-file, or PULP_USERNAME/PULP_PASSWORD)" >&2
    exit 1
  fi
  SECRET_DIR="${workdir}/secret"
  mkdir -p "${SECRET_DIR}"
  printf '%s' "${USERNAME}" > "${SECRET_DIR}/username"
  printf '%s' "${PASSWORD}" > "${SECRET_DIR}/password"
fi

files_dir="${workdir}/files"
mkdir -p "${files_dir}"
base="$(basename "${PACKAGE}")"
cp "${PACKAGE}" "${files_dir}/${base}"
if [[ -n "${COMPLIANCE_LEVEL}" ]]; then
  sidecar="${files_dir}/${base%.tgz}.tl-compliance.json"
  jq -nc --arg lvl "${COMPLIANCE_LEVEL}" '{compliance_level: $lvl}' > "${sidecar}"
fi

api_root_norm="${PULP_API_ROOT%/}/"
query_base="${PULP_BASE_URL}${api_root_norm}pulp/${PULP_DOMAIN}/api/v3/"

echo "Destination (RPA defaults unless overridden)"
echo "  base URL:    ${PULP_BASE_URL}"
echo "  domain:      ${PULP_DOMAIN}"
echo "  repository:  ${PULP_REPOSITORY}"
echo "  file repo:   ${PULP_FILE_REPOSITORY:-<unset, labels only>}"
echo "Package"
echo "  file:        ${PACKAGE}"
echo "  name:        ${PKG_NAME}@${PKG_VERSION}"
echo "  sha256:      ${LOCAL_SHA}"
echo "  label:       ${COMPLIANCE_LEVEL:-<none>}"
echo "API sequence"
echo "  GET  ${query_base}repositories/npm/npm/?name=${PULP_REPOSITORY}"
echo "  GET  ${query_base}content/npm/packages/?name=${PKG_NAME}&repository_version=..."
echo "  POST ${query_base}content/npm/packages/upload/  (file,name,version[,pulp_labels]; no repository)"
echo "  POST {repo_href}modify/  {\"add_content_units\":[content_href]}"
echo "  GET  {task} until completed"
echo

verify_in_repo() {
  local user pass auth repo_json repo_href repo_ver list_json match
  user="$(< "${SECRET_DIR}/username")"
  pass="$(< "${SECRET_DIR}/password")"
  auth=(-u "${user}:${pass}")

  repo_json="$(curl --fail-with-body --silent --retry 3 --max-time 30 \
    -G "${auth[@]}" \
    "${query_base}repositories/npm/npm/" \
    --data-urlencode "name=${PULP_REPOSITORY}")"
  repo_href="$(jq -r '.results[0].pulp_href // empty' <<<"${repo_json}")"
  repo_ver="$(jq -r '.results[0].latest_version_href // empty' <<<"${repo_json}")"
  if [[ -z "${repo_href}" || -z "${repo_ver}" ]]; then
    echo "ERROR: repository ${PULP_REPOSITORY} not found" >&2
    echo "${repo_json}" >&2
    return 1
  fi
  echo "Repository ${repo_href}"
  echo "Version    ${repo_ver}"

  list_json="$(curl --fail-with-body --silent --retry 3 --max-time 30 \
    -G "${auth[@]}" \
    "${query_base}content/npm/packages/" \
    --data-urlencode "name=${PKG_NAME}" \
    --data-urlencode "repository_version=${repo_ver}" \
    --data-urlencode "limit=100" \
    --data-urlencode "offset=0")"
  if jq -e '(.errors | type) == "array" and (.errors | length) > 0' \
    <<<"${list_json}" >/dev/null 2>&1; then
    echo "ERROR: package list rejected (do not send version= as a filter)" >&2
    echo "${list_json}" >&2
    return 1
  fi

  match="$(jq -c --arg name "${PKG_NAME}" --arg version "${PKG_VERSION}" '
    [.results[]?
      | select((.name // "") == $name and (.version // "") == $version)
    ] | if length == 1 then .[0] else empty end
  ' <<<"${list_json}")"
  if [[ -z "${match}" ]]; then
    echo "VERIFY FAIL: ${PKG_NAME}@${PKG_VERSION} is not in ${PULP_REPOSITORY}" >&2
    echo "Other ${PKG_NAME} versions in this repository version:" >&2
    jq -r '.results[]? | "  - \(.name)@\(.version)  \(.pulp_href)"' \
      <<<"${list_json}" >&2
    return 1
  fi

  echo "Found ${PKG_NAME}@${PKG_VERSION}:"
  jq . <<<"${match}"

  local label
  label="$(jq -r '.pulp_labels["tl.compliance_level"] // empty' <<<"${match}")"
  if [[ -n "${COMPLIANCE_LEVEL}" && "${label}" != "${COMPLIANCE_LEVEL}" ]]; then
    echo "VERIFY FAIL: expected pulp_labels.tl.compliance_level=${COMPLIANCE_LEVEL}," \
      "got '${label:-<missing>}'" >&2
    return 1
  fi
  echo "VERIFY OK: ${PKG_NAME}@${PKG_VERSION} in ${PULP_REPOSITORY}" \
    "label=${label:-<none>}"
}

if [[ "${VERIFY_ONLY}" == true ]]; then
  verify_in_repo
  exit 0
fi

export FILES_DIR="${files_dir}"
export SECRET_DIR
export PULP_BASE_URL PULP_API_ROOT PULP_DOMAIN PULP_REPOSITORY
export PULP_FILE_REPOSITORY
export PULP_TASK_POLL_SECONDS="${PULP_TASK_POLL_SECONDS:-5}"
export PULP_TASK_TIMEOUT_SECONDS="${PULP_TASK_TIMEOUT_SECONDS:-300}"

echo "=== npm-pulp-upload (production script) ==="
"${UPLOAD_SCRIPT}"
echo
echo "=== verify package is in the repository ==="
verify_in_repo
