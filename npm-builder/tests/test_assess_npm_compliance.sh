#!/usr/bin/env bash
# Fixture tests for assess-npm-compliance.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="${ROOT}/scripts"
export PATH="${SCRIPTS}:${PATH}"

# Prefer bash 4+ / GNU sha256sum when testing from a Mac checkout.
for b in /opt/homebrew/bin/bash /usr/local/bin/bash; do
    if [[ -x "${b}" ]]; then
        export PATH="$(dirname "${b}"):${PATH}"
        break
    fi
done
for p in /opt/homebrew/opt/coreutils/libexec/gnubin /usr/local/opt/coreutils/libexec/gnubin; do
    if [[ -x "${p}/sha256sum" ]]; then
        export PATH="${p}:${PATH}"
        break
    fi
done

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

pack_tgz() {
    local dest="$1"
    local name="$2"
    local version="$3"
    local deps_json="$4"
    local dir
    dir="$(mktemp -d "${TMPDIR:-/tmp}/assess-pack.XXXXXX")"
    mkdir -p "${dir}/package"
    jq -n --arg name "${name}" --arg version "${version}" --argjson deps "${deps_json}" \
        '{name:$name, version:$version, dependencies:$deps}' \
        > "${dir}/package/package.json"
    tar -czf "${dest}" -C "${dir}" package
    rm -rf "${dir}"
}

write_manifest() {
    local path="$1"
    local name="$2"
    local version="$3"
    mkdir -p "$(dirname "${path}")"
    jq -n --arg name "${name}" --arg version "${version}" \
        '{
          name: $name,
          version: $version,
          native_tier: "A",
          source: {url: "https://example.test/repo.git", ref: ("v" + $version)},
          entrypoint: "build.entrypoint.sh",
          smoke: "verify.smoke.sh",
          outputs: [{id:"main", type:"npm-package", path:("out/" + $name + "-" + $version + ".tgz"), pulp_name: $name}]
        }' > "${path}"
}

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/assess-npm.XXXXXX")"
trap 'rm -rf "${tmpdir}"' EXIT

# --- leaf, no dependencies → L3 ---
leaf_root="${tmpdir}/leaf"
mkdir -p "${leaf_root}/artifact" "${leaf_root}/source/packages/leaf/1.0.0"
pack_tgz "${leaf_root}/artifact/leaf-1.0.0.tgz" "leaf" "1.0.0" '{}'
write_manifest "${leaf_root}/source/packages/leaf/1.0.0/manifest.json" "leaf" "1.0.0"
assess-npm-compliance "${leaf_root}/artifact" "${leaf_root}/source" "packages/leaf/1.0.0" \
    >/dev/null
assert_eq "$(jq -r .compliance_level "${leaf_root}/artifact/leaf-1.0.0.tl-compliance.json")" \
    "L3" "no packed dependencies → L3"
assert_eq "$(jq -r '.direct_dependencies | length' "${leaf_root}/artifact/leaf-1.0.0.tl-compliance.json")" \
    "0" "no packed dependencies → empty direct_dependencies"

# Mock registry lookups: missing vs present L3.
mock_bin="${tmpdir}/bin"
mkdir -p "${mock_bin}"
cat > "${mock_bin}/lookup-npm-tl-compliance" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--max-satisfying" ]]; then
  exec "$(command -v lookup-npm-tl-compliance.real)" "$@"
fi
# registry mode
name="$2"
spec="$3"
case "${name}" in
  missing)
    exit 1
    ;;
  present)
    jq -nc --arg name "${name}" --arg requested "${spec}" \
      '{name:$name, requested:$requested, version:"1.0.0", compliance_level:"L3"}'
    exit 0
    ;;
  mid)
    jq -nc --arg name "${name}" --arg requested "${spec}" \
      '{name:$name, requested:$requested, version:"1.0.0", compliance_level:"L2"}'
    exit 0
    ;;
  *)
    echo "unexpected lookup ${name}" >&2
    exit 2
    ;;
esac
EOF
chmod +x "${mock_bin}/lookup-npm-tl-compliance"
cp "${SCRIPTS}/lookup-npm-tl-compliance" "${mock_bin}/lookup-npm-tl-compliance.real"
chmod +x "${mock_bin}/lookup-npm-tl-compliance.real"
export PATH="${mock_bin}:${SCRIPTS}:${PATH}"

# --- missing dep → L1 ---
miss_root="${tmpdir}/miss"
mkdir -p "${miss_root}/artifact" "${miss_root}/source/packages/parent/1.0.0"
pack_tgz "${miss_root}/artifact/parent-1.0.0.tgz" "parent" "1.0.0" '{"missing":"^1.0.0"}'
write_manifest "${miss_root}/source/packages/parent/1.0.0/manifest.json" "parent" "1.0.0"
assess-npm-compliance "${miss_root}/artifact" "${miss_root}/source" "packages/parent/1.0.0" \
    >/dev/null
assert_eq "$(jq -r .compliance_level "${miss_root}/artifact/parent-1.0.0.tl-compliance.json")" \
    "L1" "packed dep missing from TL → L1"
assert_eq "$(jq -r '.schema_version' "${miss_root}/artifact/parent-1.0.0.tl-compliance.json")" \
    "3" "sidecar schema_version is 3"
assert_eq "$(jq -r '.missing_gaps[0]' "${miss_root}/artifact/parent-1.0.0.tl-compliance.json")" \
    "missing@^1.0.0" "missing dep recorded in missing_gaps"

# --- dep on TL at L3 → L3 ---
ok_root="${tmpdir}/ok"
mkdir -p "${ok_root}/artifact" "${ok_root}/source/packages/parent/1.0.0"
pack_tgz "${ok_root}/artifact/parent-1.0.0.tgz" "parent" "1.0.0" '{"present":"^1.0.0"}'
write_manifest "${ok_root}/source/packages/parent/1.0.0/manifest.json" "parent" "1.0.0"
assess-npm-compliance "${ok_root}/artifact" "${ok_root}/source" "packages/parent/1.0.0" \
    >/dev/null
assert_eq "$(jq -r .compliance_level "${ok_root}/artifact/parent-1.0.0.tl-compliance.json")" \
    "L3" "packed dep on TL at L3 → L3"
assert_eq "$(jq -r '.direct_dependencies[0].requested' "${ok_root}/artifact/parent-1.0.0.tl-compliance.json")" \
    "^1.0.0" "sidecar records requested range only"
assert_eq "$(jq -r '.pending_l3_gaps | length' "${ok_root}/artifact/parent-1.0.0.tl-compliance.json")" \
    "0" "L3 dep not listed in pending_l3_gaps"

# --- dep on TL at L2 → L2 ---
mid_root="${tmpdir}/mid"
mkdir -p "${mid_root}/artifact" "${mid_root}/source/packages/parent/1.0.0"
pack_tgz "${mid_root}/artifact/parent-1.0.0.tgz" "parent" "1.0.0" '{"mid":"^1.0.0"}'
write_manifest "${mid_root}/source/packages/parent/1.0.0/manifest.json" "parent" "1.0.0"
assess-npm-compliance "${mid_root}/artifact" "${mid_root}/source" "packages/parent/1.0.0" \
    >/dev/null
assert_eq "$(jq -r .compliance_level "${mid_root}/artifact/parent-1.0.0.tl-compliance.json")" \
    "L2" "packed dep on TL at L2 → L2"
assert_eq "$(jq -r '.pending_l3_gaps[0]' "${mid_root}/artifact/parent-1.0.0.tl-compliance.json")" \
    "mid@1.0.0" "L2 dep listed in pending_l3_gaps"

# --- same-OCI dep: parent waits for leaf sidecar ---
local_root="${tmpdir}/local"
mkdir -p "${local_root}/artifact" \
    "${local_root}/source/packages/leaf/1.0.0" \
    "${local_root}/source/packages/parent/1.0.0"
pack_tgz "${local_root}/artifact/leaf-1.0.0.tgz" "leaf" "1.0.0" '{}'
pack_tgz "${local_root}/artifact/parent-1.0.0.tgz" "parent" "1.0.0" '{"leaf":"^1.0.0"}'
write_manifest "${local_root}/source/packages/leaf/1.0.0/manifest.json" "leaf" "1.0.0"
write_manifest "${local_root}/source/packages/parent/1.0.0/manifest.json" "parent" "1.0.0"
assess-npm-compliance "${local_root}/artifact" "${local_root}/source" \
    "packages/parent/1.0.0" "packages/leaf/1.0.0" >/dev/null
assert_eq "$(jq -r .compliance_level "${local_root}/artifact/leaf-1.0.0.tl-compliance.json")" \
    "L3" "same-OCI leaf → L3"
assert_eq "$(jq -r .compliance_level "${local_root}/artifact/parent-1.0.0.tl-compliance.json")" \
    "L3" "parent of same-OCI L3 leaf → L3"
assert_eq "$(jq -r '.direct_dependencies[0].requested' "${local_root}/artifact/parent-1.0.0.tl-compliance.json")" \
    "^1.0.0" "parent records leaf requested range"

echo
echo "assess-npm-compliance: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
