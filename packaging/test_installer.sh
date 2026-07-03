#!/bin/bash
# Test script to verify the MTGO Metagame Deck Builder installer was built correctly
# This performs basic verification of the installer file

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALLER_DIR="$PROJECT_ROOT/dist/installer"
INSTALLER_FILE="$INSTALLER_DIR/MTGOMetagameBuilder_Setup_v0.2.exe"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

echo_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

echo_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
}

TEST_COUNT=0
PASS_COUNT=0
FAIL_COUNT=0

run_test() {
    local test_name="$1"
    local test_command="$2"

    TEST_COUNT=$((TEST_COUNT + 1))
    echo_test "Test $TEST_COUNT: $test_name"

    if eval "$test_command"; then
        echo_pass "$test_name"
        PASS_COUNT=$((PASS_COUNT + 1))
        return 0
    else
        echo_fail "$test_name"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        return 1
    fi
}

echo_info "=========================================="
echo_info "MTGO Metagame Builder Installer Test Suite"
echo_info "=========================================="
echo ""

# Test 1: Check if installer file exists
run_test "Installer file exists" "[ -f '$INSTALLER_FILE' ]" || {
    echo_error "Installer file not found at: $INSTALLER_FILE"
    echo_error "Please run ./build_installer.sh first to create the installer."
    exit 1
}

# Test 2: Check if file is actually an executable
run_test "File is a Windows executable" "file '$INSTALLER_FILE' | grep -q 'PE32+\|PE32\|MS Windows'" || {
    echo_error "File is not a valid Windows executable"
    exit 1
}

# Test 3: Check minimum file size (should be at least 10MB for a bundled app)
MIN_SIZE=$((10 * 1024 * 1024))  # 10 MB in bytes
ACTUAL_SIZE=$(stat -f%z "$INSTALLER_FILE" 2>/dev/null || stat -c%s "$INSTALLER_FILE" 2>/dev/null)
run_test "Installer has reasonable size (>10MB)" "[ $ACTUAL_SIZE -gt $MIN_SIZE ]" || {
    echo_warn "Installer size is only $(numfmt --to=iec-i --suffix=B $ACTUAL_SIZE), which seems small"
    echo_warn "Expected at least $(numfmt --to=iec-i --suffix=B $MIN_SIZE)"
}

# Test 4: Check maximum file size (shouldn't be larger than 500MB for a reasonable app)
MAX_SIZE=$((500 * 1024 * 1024))  # 500 MB in bytes
run_test "Installer size is reasonable (<500MB)" "[ $ACTUAL_SIZE -lt $MAX_SIZE ]" || {
    echo_warn "Installer size is $(numfmt --to=iec-i --suffix=B $ACTUAL_SIZE), which seems large"
}

# Test 5: Check if installer contains Inno Setup signature
run_test "Contains Inno Setup signature" "strings '$INSTALLER_FILE' | grep -q 'Inno Setup'" || {
    echo_warn "Inno Setup signature not found in installer"
}

# Test 6: Check for application name in installer
run_test "Contains application name" "strings '$INSTALLER_FILE' | grep -q 'MTGO Metagame'" || {
    echo_warn "Application name not found in installer"
}

# Test 7: Check for license text in installer
run_test "Contains MIT License text" "strings '$INSTALLER_FILE' | grep -q 'MIT License'" || {
    echo_warn "License text not found in installer"
}

# Test 8: Check for main executable name in installer
run_test "Contains main executable reference" "strings '$INSTALLER_FILE' | grep -q 'mtgo_tools.exe'" || {
    echo_warn "Main executable reference not found in installer"
}

# Test 9: Verify installer is not corrupted (basic check)
if command -v 7z &> /dev/null; then
    run_test "Installer structure is valid (7z test)" "7z t '$INSTALLER_FILE' > /dev/null 2>&1" || {
        echo_warn "7z integrity test failed (file might be corrupted)"
    }
else
    echo_warn "7z not available, skipping structure validation test"
fi

# Test 10: Check file permissions (should be executable)
run_test "Installer has executable permissions" "[ -x '$INSTALLER_FILE' ]" || {
    echo_info "Making installer executable..."
    chmod +x "$INSTALLER_FILE"
}

# Summary
echo ""
echo_info "=========================================="
echo_info "Test Results Summary"
echo_info "=========================================="
echo_info "Total tests: $TEST_COUNT"
echo_pass "Passed: $PASS_COUNT"
if [ $FAIL_COUNT -gt 0 ]; then
    echo_fail "Failed: $FAIL_COUNT"
else
    echo_info "Failed: $FAIL_COUNT"
fi
echo ""

# Display installer details
echo_info "Installer Details:"
echo_info "  Location: $INSTALLER_FILE"
echo_info "  Size: $(numfmt --to=iec-i --suffix=B $ACTUAL_SIZE)"
echo_info "  MD5: $(md5sum "$INSTALLER_FILE" | cut -d' ' -f1)"
echo_info "  SHA256: $(sha256sum "$INSTALLER_FILE" | cut -d' ' -f1)"
echo ""

# Overall result
if [ $FAIL_COUNT -eq 0 ]; then
    echo_pass "=========================================="
    echo_pass "ALL TESTS PASSED!"
    echo_pass "=========================================="
    echo_info "The installer appears to be valid and ready for distribution."
    echo_info "To install on Windows, copy $INSTALLER_FILE to a Windows machine and run it."
    exit 0
else
    echo_fail "=========================================="
    echo_fail "SOME TESTS FAILED!"
    echo_fail "=========================================="
    echo_error "Please review the failures above and rebuild the installer if necessary."
    exit 1
fi
