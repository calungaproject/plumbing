#!/bin/bash
set -euo pipefail

# Tests for collect-build-files denylist matching, especially hyphenated sdist names.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COLLECT="${SCRIPT_DIR}/../builder/scripts/collect-build-files"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

assert_file_exists() {
    local test_name="$1"
    local file_path="$2"
    TESTS_RUN=$((TESTS_RUN + 1))
    if [[ -f "$file_path" ]]; then
        log_info "✓ $test_name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        log_error "✗ $test_name (missing: $file_path)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

assert_file_absent() {
    local test_name="$1"
    local file_path="$2"
    TESTS_RUN=$((TESTS_RUN + 1))
    if [[ ! -f "$file_path" ]]; then
        log_info "✓ $test_name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        log_error "✗ $test_name (unexpected file: $file_path)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

# Create empty placeholder artifacts in a Fromager-like layout.
make_artifact() {
    local path="$1"
    mkdir -p "$(dirname "$path")"
    : > "$path"
}

setup_tree() {
    local root="$1"
    mkdir -p \
        "${root}/source/wheels-repo/downloads" \
        "${root}/source/sdists-repo/builds" \
        "${root}/dest"

    # Denied packages (wheels use underscores; sdists use hyphens).
    make_artifact "${root}/source/wheels-repo/downloads/lxml-6.1.2-cp312-cp312-manylinux_2_28_x86_64.whl"
    make_artifact "${root}/source/wheels-repo/downloads/pyarrow-19.0.0-cp312-cp312-manylinux_2_28_x86_64.whl"
    make_artifact "${root}/source/wheels-repo/downloads/freeze_core-1.0.0-py3-none-any.whl"
    make_artifact "${root}/source/wheels-repo/downloads/numpy-2.5.2-cp312-cp312-manylinux_2_28_x86_64.whl"
    make_artifact "${root}/source/sdists-repo/builds/lxml-6.1.2.tar.gz"
    make_artifact "${root}/source/sdists-repo/builds/pyarrow-19.0.0.tar.gz"
    make_artifact "${root}/source/sdists-repo/builds/freeze-core-1.0.0.tar.gz"
    make_artifact "${root}/source/sdists-repo/builds/numpy-2.5.2.tar.gz"

    # Still-onboarded packages whose names are prefixes of a denied name, or
    # whose sdist name is hyphenated. These must NOT be treated as denied.
    make_artifact "${root}/source/wheels-repo/downloads/lxml_html_clean-0.4.5-py3-none-any.whl"
    make_artifact "${root}/source/wheels-repo/downloads/pyarrow_hotfix-0.7-py3-none-any.whl"
    make_artifact "${root}/source/sdists-repo/builds/lxml-html-clean-0.4.5.tar.gz"
    make_artifact "${root}/source/sdists-repo/builds/pyarrow-hotfix-0.7.tar.gz"

    # Unrelated package that should always be collected.
    make_artifact "${root}/source/wheels-repo/downloads/requests-2.32.0-py3-none-any.whl"
    make_artifact "${root}/source/sdists-repo/builds/requests-2.32.0.tar.gz"

    cat > "${root}/denied_packages.txt" <<'EOF'
# comment line
pillow
pyarrow
freeze-core
numpy
cryptography
lxml
cffi
EOF
}

test_denylist_hyphenated_names() {
    local tmp
    tmp="$(mktemp -d)"
    setup_tree "$tmp"
    "$COLLECT" --denylist "${tmp}/denied_packages.txt" "${tmp}/source" "${tmp}/dest"

    local dest="${tmp}/dest"

    # Denied wheels
    assert_file_absent "deny lxml wheel" "${dest}/lxml-6.1.2-cp312-cp312-manylinux_2_28_x86_64.whl"
    assert_file_absent "deny pyarrow wheel" "${dest}/pyarrow-19.0.0-cp312-cp312-manylinux_2_28_x86_64.whl"
    assert_file_absent "deny freeze-core wheel" "${dest}/freeze_core-1.0.0-py3-none-any.whl"
    assert_file_absent "deny numpy wheel" "${dest}/numpy-2.5.2-cp312-cp312-manylinux_2_28_x86_64.whl"

    # Denied sdists (hyphenated names must match the full package, not the first token)
    assert_file_absent "deny lxml sdist" "${dest}/lxml-6.1.2.tar.gz"
    assert_file_absent "deny pyarrow sdist" "${dest}/pyarrow-19.0.0.tar.gz"
    assert_file_absent "deny freeze-core sdist" "${dest}/freeze-core-1.0.0.tar.gz"
    assert_file_absent "deny numpy sdist" "${dest}/numpy-2.5.2.tar.gz"

    # Related onboarded packages must still be collected
    assert_file_exists "keep lxml-html-clean wheel" "${dest}/lxml_html_clean-0.4.5-py3-none-any.whl"
    assert_file_exists "keep lxml-html-clean sdist" "${dest}/lxml-html-clean-0.4.5.tar.gz"
    assert_file_exists "keep pyarrow-hotfix wheel" "${dest}/pyarrow_hotfix-0.7-py3-none-any.whl"
    assert_file_exists "keep pyarrow-hotfix sdist" "${dest}/pyarrow-hotfix-0.7.tar.gz"

    assert_file_exists "keep requests wheel" "${dest}/requests-2.32.0-py3-none-any.whl"
    assert_file_exists "keep requests sdist" "${dest}/requests-2.32.0.tar.gz"

    rm -rf "$tmp"
}

test_missing_denylist_fails() {
    local tmp
    tmp="$(mktemp -d)"
    setup_tree "$tmp"

    local rc=0
    "$COLLECT" --denylist "${tmp}/does-not-exist.txt" "${tmp}/source" "${tmp}/dest" || rc=$?

    TESTS_RUN=$((TESTS_RUN + 1))
    if [[ "$rc" -ne 0 ]]; then
        log_info "✓ missing denylist file fails the collect"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        log_error "✗ missing denylist file fails the collect (expected nonzero exit)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi

    rm -rf "$tmp"
}

test_no_denylist_collects_all() {
    local tmp
    tmp="$(mktemp -d)"
    setup_tree "$tmp"
    "$COLLECT" "${tmp}/source" "${tmp}/dest"

    local dest="${tmp}/dest"
    assert_file_exists "no denylist: collect lxml sdist" "${dest}/lxml-6.1.2.tar.gz"
    assert_file_exists "no denylist: collect freeze-core sdist" "${dest}/freeze-core-1.0.0.tar.gz"
    assert_file_exists "no denylist: collect lxml-html-clean sdist" "${dest}/lxml-html-clean-0.4.5.tar.gz"
    assert_file_exists "no denylist: collect requests wheel" "${dest}/requests-2.32.0-py3-none-any.whl"

    rm -rf "$tmp"
}

echo "======================================="
echo "  collect-build-files denylist tests"
echo "======================================="
echo

test_denylist_hyphenated_names
test_missing_denylist_fails
test_no_denylist_collects_all

echo
echo "======================================="
echo "  Test Results"
echo "======================================="
echo "Tests run: $TESTS_RUN"
echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}"
echo

if [[ "$TESTS_FAILED" -ne 0 ]]; then
    log_error "Some tests failed!"
    exit 1
fi

log_info "All tests passed!"
