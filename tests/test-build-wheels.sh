#!/bin/bash

set -euo pipefail

# Test framework for build-wheels script
# This script builds the container image and runs tests against the build-wheels script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILDER_DIR="$PROJECT_ROOT/builder"
TEST_OUTPUT_DIR="$SCRIPT_DIR/test-output"
CONTAINER_IMAGE="calunga-builder:test"
IMAGE_PULLSPEC="quay.io/redhat-user-workloads/calunga-tenant/plumbing-builder@sha256:0f4d7eb4092cb3f10c1c5a3fbce6abcb3ee2d0218ec8e6230920acd5280905db"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Test tracking
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
SKIP_BUILD=0 # Default to building the image

# Help function
show_help() {
    cat << EOF
Run build-wheels script test suite.

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --skip-build                    Don't build image, pull the one from IMAGE_PULLSPEC
    --help                          Show this help message
EOF
    exit 0
}

# Cleanup function
cleanup() {
    echo -e "${YELLOW}Cleaning up test output directory...${NC}"
    rm -rf "$TEST_OUTPUT_DIR"
}

# Trap to ensure cleanup on exit
trap cleanup EXIT

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Test assertion functions
assert_success() {
    local test_name="$1"
    local exit_code="$2"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ "$exit_code" -eq 0 ]; then
        log_info "✓ $test_name: PASSED"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        log_error "✗ $test_name: FAILED (exit code: $exit_code)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

assert_failure() {
    local test_name="$1"
    local exit_code="$2"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ "$exit_code" -ne 0 ]; then
        log_info "✓ $test_name: PASSED"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        log_error "✗ $test_name: FAILED (expected failure but got success)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

assert_contains() {
    local test_name="$1"
    local haystack="$2"
    local needle="$3"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [[ "$haystack" == *"$needle"* ]]; then
        log_info "✓ $test_name: PASSED"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        log_error "✗ $test_name: FAILED (expected '$needle' in output)"
        log_error "   Output was: $haystack"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

assert_not_contains() {
    local test_name="$1"
    local haystack="$2"
    local needle="$3"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [[ "$haystack" != *"$needle"* ]]; then
        log_info "✓ $test_name: PASSED"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        log_error "✗ $test_name: FAILED (did not expect '$needle' in output)"
        log_error "   Output was: $haystack"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

assert_file_exists() {
    local test_name="$1"
    local file_path="$2"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ -f "$file_path" ]; then
        log_info "✓ $test_name: PASSED"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        log_error "✗ $test_name: FAILED (file does not exist: $file_path)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

assert_equals() {
    local test_name="$1"
    local expected="$2"
    local actual="$3"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ "$expected" = "$actual" ]; then
        log_info "✓ $test_name: PASSED"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        log_error "✗ $test_name: FAILED (expected '$expected', got '$actual')"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

assert_wheel_contains() {
    local test_name="$1"
    local wheel_path="$2"
    local pattern="$3"

    TESTS_RUN=$((TESTS_RUN + 1))

    if unzip -Z1 "$wheel_path" | grep -q "$pattern"; then
        log_info "✓ $test_name: PASSED"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        log_error "✗ $test_name: FAILED (pattern '$pattern' not found in $wheel_path)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

assert_wheel_not_contains() {
    local test_name="$1"
    local wheel_path="$2"
    local pattern="$3"

    TESTS_RUN=$((TESTS_RUN + 1))

    if unzip -Z1 "$wheel_path" | grep -q "$pattern"; then
        log_error "✗ $test_name: FAILED (pattern '$pattern' unexpectedly found in $wheel_path)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    else
        log_info "✓ $test_name: PASSED"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    fi
}

# Setup function - build or pull container image
setup() {
    log_info "Setting up test environment..."

    # Check if podman is available
    if ! command -v podman &> /dev/null; then
        log_error "podman is required but not installed"
        exit 1
    fi

    # Create test output directory
    mkdir -p "$TEST_OUTPUT_DIR"

    if [ "$SKIP_BUILD" -eq 1 ]; then
        log_info "Skipping build. Pulling container image: $IMAGE_PULLSPEC"
        if podman pull "$IMAGE_PULLSPEC"; then
            CONTAINER_IMAGE="$IMAGE_PULLSPEC"
            log_info "Container image pulled successfully"
        else
            log_error "Failed to pull container image: $IMAGE_PULLSPEC"
            exit 1
        fi
    else
        # Build the container image using builder Containerfile
        log_info "Building container image: $CONTAINER_IMAGE"

        if podman build -t "$CONTAINER_IMAGE" -f "$BUILDER_DIR/Containerfile" "$BUILDER_DIR"; then
            log_info "Container image built successfully"
        else
            log_error "Failed to build container image"
            exit 1
        fi
    fi
}

# Helper function to run build-wheels in container
run_build_wheels() {
    local output_dir="$1"
    shift
    local args=("$@")

    # Ensure output directory exists
    mkdir -p "$output_dir"

    podman run --rm \
        -v "${output_dir}:/mnt/workdir:z" \
        --workdir '/mnt/workdir' \
        "$CONTAINER_IMAGE" \
        build-wheels "${args[@]}" 2>&1
}

# Test Cases

test_help_flag() {
    log_info "Running test: Help flag"

    local output
    set +e
    output=$(run_build_wheels "$TEST_OUTPUT_DIR/help" --help)
    local exit_code=$?
    set -e

    assert_success "Help flag exits successfully" "$exit_code"
    assert_contains "Help contains usage information" "$output" "USAGE:"
    assert_contains "Help contains examples" "$output" "EXAMPLES:"
}

test_invalid_option() {
    log_info "Running test: Invalid option"

    local output
    set +e
    output=$(run_build_wheels "$TEST_OUTPUT_DIR/invalid" --invalid-option 2>&1)
    local exit_code=$?
    set -e

    assert_failure "Invalid option should fail" "$exit_code"
    assert_contains "Error message for invalid option" "$output" "Unknown option"
}

test_missing_package() {
    log_info "Running test: Missing package argument"

    local output
    set +e
    output=$(run_build_wheels "$TEST_OUTPUT_DIR/missing" 2>&1)
    local exit_code=$?
    set -e

    assert_failure "Missing package should fail" "$exit_code"
    assert_contains "Error message for missing package" "$output" "At least one package argument is required"
}

test_multiple_packages() {
    log_info "Running test: Multiple packages"

    local output
    set +e
    # Use real packages for the test - setuptools and wheel are core Python infrastructure
    # packages that are stable and unlikely to become unavailable. Using real packages
    # ensures we test actual functionality rather than mocked behavior.
    output=$(run_build_wheels "$TEST_OUTPUT_DIR/multiple" "setuptools==69.0.0" "wheel==0.42.0" 2>&1)
    local exit_code=$?
    set -e

    assert_success "Multiple packages should succeed" "$exit_code"
    assert_contains "Build completion message" "$output" "Build completed successfully"
    assert_contains "Multiple package processing" "$output" "Processing package: setuptools==69.0.0"
    assert_contains "Multiple package processing" "$output" "Processing package: wheel==0.42.0"
}

test_cache_wheel_server_url_missing_value() {
    log_info "Running test: Cache wheel server URL missing value"

    local output
    set +e
    output=$(run_build_wheels "$TEST_OUTPUT_DIR/cache-missing" --cache-wheel-server-url 2>&1)
    local exit_code=$?
    set -e

    assert_failure "Missing cache URL value should fail" "$exit_code"
    assert_contains "Error message for missing cache URL" "$output" "requires a value"
}

test_basic_functionality() {
    log_info "Running test: Basic functionality with setuptools"

    local test_dir="$TEST_OUTPUT_DIR/basic"
    local output

    # Use a simple, reliable package for testing
    set +e
    output=$(run_build_wheels "$test_dir" "setuptools==69.0.0" 2>&1)
    local exit_code=$?
    set -e

    assert_success "Basic build should succeed" "$exit_code"
    assert_contains "Log contains build completion" "$output" "Build completed successfully"
    assert_contains "Log contains timestamped entries" "$output" "Setting up CA trust"
}

test_file_generation() {
    log_info "Running test: File generation validation"

    local test_dir="$TEST_OUTPUT_DIR/files"
    local output

    # Run a build and check that it mentions file paths in output
    set +e
    output=$(run_build_wheels "$test_dir" "setuptools==69.0.0" 2>&1)
    local exit_code=$?
    set -e

    assert_success "Basic build should succeed" "$exit_code"
    # Check for expected output messages that indicate file generation
    assert_contains "Output mentions source distributions" "$output" "./sdists-repo/downloads/setuptools-69.0.0.tar.gz"
    assert_contains "Output mentions wheels" "$output" "./wheels-repo/downloads/setuptools-69.0.0-0-py3-none-any.whl"
}

test_build_sequence_summaries() {
    log_info "Running test: Build sequence summaries for multiple packages"

    local test_dir="$TEST_OUTPUT_DIR/summaries"
    local output

    # Run a build with multiple packages to test build sequence summary handling
    set +e
    output=$(run_build_wheels "$test_dir" "setuptools==69.0.0" "wheel==0.42.0" 2>&1)
    local exit_code=$?
    set -e

    assert_success "Multiple packages build should succeed" "$exit_code"
    # Check that build sequence summaries are mentioned in output
    assert_contains "Summary for first package" "$output" "./build-sequence-summary-setuptools__69.0.0.json"
    assert_contains "Summary for second package" "$output" "./build-sequence-summary-wheel__0.42.0.json"
}

test_sbom_cyclonedx_removal() {
    log_info "Running test: CycloneDX SBOM removal from manylinux wheels"

    local test_dir="$TEST_OUTPUT_DIR/sbom-cdx-removal"
    local output

    # Build a package with native C extensions to trigger auditwheel repair.
    # auditwheel >= 6.5 injects CycloneDX SBOMs into repaired wheels;
    # build-wheels then calls remove-cyclonedx-sboms to strip them.
    set +e
    output=$(run_build_wheels "$test_dir" "markupsafe==2.1.5" 2>&1)
    local exit_code=$?
    set -e

    assert_success "Build completes successfully" "$exit_code"
    assert_contains "CycloneDX removal ran" "$output" "Removing auditwheel-generated SBOMs from repaired manylinux wheels"

    # Find the manylinux wheel (produced by auditwheel repair)
    local whl
    whl=$(find "$test_dir/output/wheels-repo/downloads" -iname 'markupsafe-*manylinux*.whl' | head -1)

    if [ -z "$whl" ]; then
        TESTS_RUN=$((TESTS_RUN + 1))
        log_error "✗ MarkupSafe manylinux wheel not found on disk: FAILED"
        log_error "  Wheels present: $(ls "$test_dir/output/wheels-repo/downloads/"*.whl 2>/dev/null || echo 'none')"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi

    # Verify CycloneDX SBOMs were removed by remove-cyclonedx-sboms
    assert_wheel_not_contains "No CycloneDX SBOMs in manylinux wheel" "$whl" '\.cdx\.json'

    # Verify Fromager's SPDX SBOM was preserved and renamed
    assert_wheel_not_contains "No fromager.spdx.json (should be renamed)" "$whl" 'fromager\.spdx\.json'
    assert_wheel_contains "redhat.spdx.json present" "$whl" 'redhat\.spdx\.json'
}

test_sbom_integration() {
    log_info "Running test: SBOM integration (end-to-end with container build)"

    local test_dir="$TEST_OUTPUT_DIR/sbom-integration"
    local output

    set +e
    output=$(run_build_wheels "$test_dir" "setuptools==69.0.0" 2>&1)
    local exit_code=$?
    set -e

    assert_success "Build completes successfully" "$exit_code"

    # Find the output wheel
    local whl
    whl=$(find "$test_dir/output/wheels-repo/downloads" -name 'setuptools-*-none-any.whl' | head -1)

    if [ -z "$whl" ]; then
        TESTS_RUN=$((TESTS_RUN + 1))
        log_error "✗ Setuptools wheel not found on disk: FAILED"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi

    # Verify SBOM was renamed from fromager.spdx.json to redhat.spdx.json
    assert_wheel_not_contains "No fromager.spdx.json in output wheel" "$whl" 'fromager\.spdx\.json'
    assert_wheel_contains "redhat.spdx.json present in output wheel" "$whl" 'redhat\.spdx\.json'

    # Verify no CycloneDX SBOMs (setuptools is pure-python so auditwheel doesn't
    # run, but verify the invariant anyway)
    assert_wheel_not_contains "No CycloneDX SBOMs in output wheel" "$whl" '\.cdx\.json'

    # Verify file_name= qualifier in PURL (wheel only, not upstream)
    local sbom_content
    sbom_content=$(unzip -p "$whl" "$(unzip -Z1 "$whl" | grep 'redhat\.spdx\.json')")

    local wheel_purl
    wheel_purl=$(jq -r '.packages[] | select(.SPDXID == "SPDXRef-wheel") | .externalRefs[] | select(.referenceType == "purl") | .referenceLocator' <<< "$sbom_content")

    assert_contains "Wheel PURL has file_name= qualifier" "$wheel_purl" "file_name=$(basename "$whl")"

    local upstream_purl
    upstream_purl=$(jq -r '.packages[] | select(.SPDXID == "SPDXRef-upstream") | .externalRefs[] | select(.referenceType == "purl") | .referenceLocator' <<< "$sbom_content")

    assert_not_contains "Upstream PURL does not have file_name= qualifier" "$upstream_purl" "file_name="

    # Verify creationInfo.creators
    # Value comes from Fromager's overrides/settings.yaml
    local creator_organization
    creator_organization=$(jq '.creationInfo.creators[] | select(contains("Organization"))' <<< "$sbom_content")

    # Should have Organization: Red Hat
    assert_contains "Creator Organization is Red Hat" "$creator_organization" "Organization: Red Hat"
}

test_sbom_record_integrity() {
    log_info "Running test: SBOM RECORD file integrity after patch-sbom-purl"

    local test_dir="$TEST_OUTPUT_DIR/sbom-record"
    local output

    set +e
    output=$(run_build_wheels "$test_dir" "setuptools==69.0.0" 2>&1)
    local exit_code=$?
    set -e

    assert_success "Build completes successfully" "$exit_code"

    # Find the output wheel
    local whl
    whl=$(find "$test_dir/output/wheels-repo/downloads" -name 'setuptools-*-none-any.whl' | head -1)

    if [ -z "$whl" ]; then
        TESTS_RUN=$((TESTS_RUN + 1))
        log_error "✗ Setuptools wheel not found on disk: FAILED"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi

    # Extract RECORD and SBOM to a temp directory
    local tmpdir
    tmpdir=$(mktemp -d)

    local record_path
    record_path=$(unzip -Z1 "$whl" | grep '\.dist-info/RECORD$')
    local sbom_path
    sbom_path=$(unzip -Z1 "$whl" | grep 'redhat\.spdx\.json')

    if [ -z "$record_path" ] || [ -z "$sbom_path" ]; then
        TESTS_RUN=$((TESTS_RUN + 1))
        log_error "✗ RECORD or redhat.spdx.json not found in wheel: FAILED"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        rm -rf "$tmpdir"
        return 1
    fi

    unzip -o "$whl" "$record_path" "$sbom_path" -d "$tmpdir"

    # Parse the SBOM entry from RECORD
    # Format: <path>,sha256=<urlsafe_b64_no_padding>,<size>
    local record_line
    record_line=$(grep 'redhat\.spdx\.json' "$tmpdir/$record_path")
    local record_hash
    record_hash=$(echo "$record_line" | cut -d',' -f2 | sed 's/^sha256=//')
    local record_size
    record_size=$(echo "$record_line" | cut -d',' -f3)

    # Compute actual hash, match what is done in patch-sbom-purl
    # - compute SHA-256 hash of the SBOM file
    # - grab the hex hash (e.g. a1b2c3d4e5f6...)
    # - convert hex text back to binary bytes (Python's hashlib.sha256().digest() returns raw bytes, not hex)
    # - base64 encode raw bytes
    # - swap characters so encoding is URL safe (match Python's base64.urlsafe_b64encode())
    # - strip padding '=' characters from the end
    local actual_hash
    actual_hash=$(sha256sum "$tmpdir/$sbom_path" | cut -d' ' -f1 | xxd -r -p | base64 | tr '+/' '-_' | tr -d '=')
    local actual_size
    actual_size=$(wc -c < "$tmpdir/$sbom_path" | tr -d ' ')

    assert_equals "RECORD hash matches actual SBOM sha256" "$record_hash" "$actual_hash"
    assert_equals "RECORD size matches actual SBOM file size" "$record_size" "$actual_size"

    rm -rf "$tmpdir"
}

# Main execution
main() {
    # Parse command line arguments
    while [[ "$#" -gt 0 ]]; do
        case $1 in
            --help)
                show_help
                ;;
            --skip-build)
                SKIP_BUILD=1
                shift ;;
            -*)
                echo "Error: Unknown option $1" >&2
                echo "Use --help for usage information" >&2
                exit 1
                ;;
            *)
                echo "Error: Invalid argument $1" >&2
                echo "Use --help for usage information" >&2
                exit 1
                ;;
        esac
    done

    echo "======================================="
    echo "  Build-wheels Script Test Suite"
    echo "======================================="
    echo

    setup

    echo
    log_info "Running tests..."
    echo

    # Run all tests
    test_help_flag
    test_invalid_option
    test_missing_package
    test_multiple_packages
    test_cache_wheel_server_url_missing_value
    test_basic_functionality
    test_file_generation
    test_build_sequence_summaries
    test_sbom_cyclonedx_removal
    test_sbom_integration
    test_sbom_record_integrity
    echo
    echo "======================================="
    echo "  Test Results"
    echo "======================================="
    echo "Tests run: $TESTS_RUN"
    echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}"
    echo

    if [ "$TESTS_FAILED" -eq 0 ]; then
        log_info "All tests passed! 🎉"
        exit 0
    else
        log_error "Some tests failed!"
        exit 1
    fi
}

# Run main function
main "$@"
