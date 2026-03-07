#!/usr/bin/env bash
#
# Invoicify End-to-End Full Workflow Test Runner
#
# This script orchestrates the complete E2E test:
# 1. Starts Mockoon mocks for QuickBooks, Salesforce, and Audit services
# 2. Generates test invoice PDFs
# 3. Runs the E2E test suite
# 4. Validates results and outputs a detailed report
# 5. Cleans up all mock services
#
# Usage:
#   ./scripts/test-e2e-full.sh              # Run full test suite
#   ./scripts/test-e2e-full.sh --no-cleanup # Run without cleanup (debug)
#   ./scripts/test-e2e-full.sh --help       # Show help
#
# Requirements:
#   - Node.js 18+ (for Mockoon CLI)
#   - Python 3.11+
#   - uv (Python package manager)
#   - mockoon-cli (npm install -g @mockoon/cli)
#
# Exit Codes:
#   0 - All tests passed
#   1 - Tests failed
#   2 - Setup failed (Mockoon, dependencies)
#   3 - Cleanup failed
#

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Mockoon configuration
MOCKOON_QUICKBOOKS_PORT=3010
MOCKOON_SALESFORCE_PORT=3020
MOCKOON_AUDIT_PORT=3050
MOCKOON_BLOB_PORT=3030
MOCKOON_DI_PORT=3040

# Timeout configuration
MOCKOON_STARTUP_TIMEOUT=30
TEST_TIMEOUT=120  # 2 minutes

# Paths
MOCKS_DIR="${PROJECT_ROOT}/mocks"
TESTS_DIR="${PROJECT_ROOT}/tests/e2e"
REPORTS_DIR="${PROJECT_ROOT}/reports/e2e"
LOGS_DIR="${PROJECT_ROOT}/logs"

# Mockoon data files
QUICKBOOKS_MOCK="${MOCKS_DIR}/quickbooks-mock.json"
SALESFORCE_MOCK="${MOCKS_DIR}/salesforce-mock.json"

# PIDs for cleanup
MOCKOON_PIDS=()

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Flags
NO_CLEANUP=false
VERBOSE=false
SKIP_MOCKS=false

# ─────────────────────────────────────────────────────────────────────────────
# Utility Functions
# ─────────────────────────────────────────────────────────────────────────────

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_step() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}\n"
}

cleanup() {
    local exit_code=$?

    if [[ "$NO_CLEANUP" == "true" ]]; then
        log_warning "Skipping cleanup (--no-cleanup flag set)"
        log_info "Mockoon PIDs: ${MOCKOON_PIDS[*]:-none}"
        return $exit_code
    fi

    log_step "Cleaning Up Mock Services"

    local cleanup_failed=false

    # Kill Mockoon processes
    for pid in "${MOCKOON_PIDS[@]:-}"; do
        if kill -0 "$pid" 2>/dev/null; then
            log_info "Stopping Mockoon process (PID: $pid)..."
            if ! kill -TERM "$pid" 2>/dev/null; then
                log_warning "Failed to stop PID $pid gracefully, forcing..."
                kill -9 "$pid" 2>/dev/null || true
            fi
        fi
    done

    # Wait for processes to terminate
    sleep 2

    # Verify cleanup
    for pid in "${MOCKOON_PIDS[@]:-}"; do
        if kill -0 "$pid" 2>/dev/null; then
            log_error "Failed to stop process $pid"
            cleanup_failed=true
        fi
    done

    if [[ "$cleanup_failed" == "true" ]]; then
        log_error "Cleanup failed - some processes may still be running"
        return 3
    fi

    log_success "Cleanup completed successfully"
    return $exit_code
}

check_dependencies() {
    log_step "Checking Dependencies"

    local missing=()

    # Check Node.js
    if ! command -v node &>/dev/null; then
        missing+=("node")
    else
        local node_version
        node_version=$(node --version)
        log_info "Node.js: $node_version"
    fi

    # Check npm
    if ! command -v npm &>/dev/null; then
        missing+=("npm")
    fi

    # Check Mockoon CLI
    if ! command -v mockoon-cli &>/dev/null; then
        log_warning "Mockoon CLI not found. Installing..."
        if ! npm install -g @mockoon/cli &>/dev/null; then
            missing+=("mockoon-cli")
        else
            log_success "Mockoon CLI installed"
        fi
    else
        local mockoon_version
        mockoon_version=$(mockoon-cli --version 2>&1 || echo "unknown")
        log_info "Mockoon CLI: $mockoon_version"
    fi

    # Check Python
    if ! command -v python3 &>/dev/null; then
        missing+=("python3")
    else
        local python_version
        python_version=$(python3 --version)
        log_info "Python: $python_version"
    fi

    # Check uv
    if ! command -v uv &>/dev/null; then
        log_warning "uv not found. Using pip instead..."
    else
        local uv_version
        uv_version=$(uv --version)
        log_info "uv: $uv_version"
    fi

    # Check pytest
    if ! python3 -m pytest --version &>/dev/null; then
        log_warning "pytest not found. Will install during setup..."
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing dependencies: ${missing[*]}"
        log_info "Install with: npm install -g @mockoon/cli"
        return 2
    fi

    log_success "All dependencies satisfied"
    return 0
}

setup_directories() {
    log_step "Setting Up Directories"

    mkdir -p "$REPORTS_DIR"
    mkdir -p "$LOGS_DIR"
    mkdir -p "$TESTS_DIR"

    log_info "Reports directory: $REPORTS_DIR"
    log_info "Logs directory: $LOGS_DIR"

    log_success "Directories ready"
}

start_mockoon_mock() {
    local name=$1
    local mock_file=$2
    local port=$3

    log_info "Starting $name mock on port $port..."

    if [[ ! -f "$mock_file" ]]; then
        log_error "Mock file not found: $mock_file"
        return 1
    fi

    # Start Mockoon in background
    mockoon-cli start \
        --data "$mock_file" \
        --port "$port" \
        --log-level error \
        &>/dev/null &

    local pid=$!
    MOCKOON_PIDS+=("$pid")

    log_info "$name started (PID: $pid)"

    # Wait for service to be ready
    local retries=0
    local max_retries=$((MOCKOON_STARTUP_TIMEOUT / 2))

    while [[ $retries -lt $max_retries ]]; do
        if curl -s "http://localhost:$port/health" &>/dev/null; then
            log_success "$name is ready (port $port)"
            return 0
        fi
        sleep 2
        ((retries++))
    done

    log_error "$name failed to start on port $port"
    return 1
}

wait_for_service() {
    local name=$1
    local url=$2
    local timeout=${3:-$MOCKOON_STARTUP_TIMEOUT}

    log_info "Waiting for $name at $url..."

    local start_time
    start_time=$(date +%s)

    while true; do
        if curl -s "$url" &>/dev/null; then
            log_success "$name is ready"
            return 0
        fi

        local current_time
        current_time=$(date +%s)
        local elapsed=$((current_time - start_time))

        if [[ $elapsed -ge $timeout ]]; then
            log_error "$name failed to respond within ${timeout}s"
            return 1
        fi

        sleep 1
    done
}

start_all_mocks() {
    log_step "Starting Mock Services"

    # Start QuickBooks mock
    if ! start_mockoon_mock "QuickBooks" "$QUICKBOOKS_MOCK" "$MOCKOON_QUICKBOOKS_PORT"; then
        return 1
    fi

    # Start Salesforce mock
    if ! start_mockoon_mock "Salesforce" "$SALESFORCE_MOCK" "$MOCKOON_SALESFORCE_PORT"; then
        return 1
    fi

    # Wait for services to be ready
    sleep 3

    if ! wait_for_service "QuickBooks" "http://localhost:$MOCKOON_QUICKBOOKS_PORT/health"; then
        return 1
    fi

    if ! wait_for_service "Salesforce" "http://localhost:$MOCKOON_SALESFORCE_PORT/health"; then
        return 1
    fi

    log_success "All mock services started"

    # Print service URLs
    echo ""
    echo "Mock Services:"
    echo "  QuickBooks:  http://localhost:$MOCKOON_QUICKBOOKS_PORT"
    echo "  Salesforce:  http://localhost:$MOCKOON_SALESFORCE_PORT"
    echo ""

    return 0
}

install_test_dependencies() {
    log_step "Installing Test Dependencies"

    cd "$PROJECT_ROOT"

    # Install Python test dependencies
    log_info "Installing Python test dependencies..."

    if command -v uv &>/dev/null; then
        uv pip install -q pytest pytest-asyncio httpx reportlab
    else
        pip3 install -q pytest pytest-asyncio httpx reportlab
    fi

    log_success "Python dependencies installed"

    return 0
}

run_e2e_tests() {
    log_step "Running E2E Tests"

    cd "$PROJECT_ROOT"

    # Set environment variables for test
    export MOCKOON_QUICKBOOKS_URL="http://localhost:$MOCKOON_QUICKBOOKS_PORT"
    export MOCKOON_SALESFORCE_URL="http://localhost:$MOCKOON_SALESFORCE_PORT"
    export MOCKOON_AUDIT_URL="http://localhost:$MOCKOON_AUDIT_PORT"
    export E2E_TIMEOUT_SECONDS="$TEST_TIMEOUT"

    local test_file="${TESTS_DIR}/test_full_workflow.py"

    if [[ ! -f "$test_file" ]]; then
        log_error "Test file not found: $test_file"
        return 1
    fi

    log_info "Test file: $test_file"
    log_info "Timeout: ${TEST_TIMEOUT}s"

    # Run pytest with verbose output
    local pytest_args=(
        "-v"
        "--tb=short"
        "--asyncio-mode=auto"
        "--capture=no"
        "--junitxml=${REPORTS_DIR}/junit-e2e.xml"
    )

    if [[ "$VERBOSE" == "true" ]]; then
        pytest_args+=("-s")
    fi

    log_info "Running: pytest ${pytest_args[*]} $test_file"
    echo ""

    # Run tests and capture exit code
    local test_exit_code=0
    python3 -m pytest "${pytest_args[@]}" "$test_file" || test_exit_code=$?

    echo ""

    if [[ $test_exit_code -eq 0 ]]; then
        log_success "All E2E tests passed!"
    else
        log_error "E2E tests failed (exit code: $test_exit_code)"
    fi

    # Show test report location
    local report_file
    report_file=$(ls -t "${REPORTS_DIR}"/test_report_*.json 2>/dev/null | head -1)
    if [[ -n "$report_file" ]]; then
        log_info "Test report: $report_file"
        echo ""
        echo "Report preview:"
        python3 -c "
import json
with open('$report_file') as f:
    data = json.load(f)
    print(f\"  Test ID: {data['test_id']}\")
    print(f\"  Status: {'PASSED' if data['success'] else 'FAILED'}\")
    print(f\"  Duration: {data['total_duration_ms']}ms\")
    print(f\"  Steps: {len(data['steps'])}\")
"
    fi

    return $test_exit_code
}

print_summary() {
    local exit_code=$1

    log_step "Test Summary"

    if [[ $exit_code -eq 0 ]]; then
        echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║                  ✅ ALL TESTS PASSED ✅                   ║${NC}"
        echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
    else
        echo -e "${RED}╔═══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║                  ❌ TESTS FAILED ❌                       ║${NC}"
        echo -e "${RED}╚═══════════════════════════════════════════════════════════╝${NC}"
    fi

    echo ""
    echo "Reports:"
    echo "  JUnit XML: ${REPORTS_DIR}/junit-e2e.xml"
    echo "  JSON Report: ${REPORTS_DIR}/test_report_*.json"
    echo ""

    if [[ "$NO_CLEANUP" == "true" ]]; then
        echo -e "${YELLOW}Note: Mock services still running (--no-cleanup)${NC}"
        echo "Stop manually with:"
        for pid in "${MOCKOON_PIDS[@]:-}"; do
            echo "  kill $pid"
        done
        echo ""
    fi
}

show_help() {
    cat << EOF
Invoicify End-to-End Full Workflow Test Runner

Usage: $(basename "$0") [OPTIONS]

Options:
  --no-cleanup    Don't stop mock services after tests (for debugging)
  --skip-mocks    Skip starting mocks (use existing running services)
  --verbose       Enable verbose output
  --help          Show this help message

Environment Variables:
  MOCKOON_QUICKBOOKS_URL   QuickBooks mock URL (default: http://localhost:3010)
  MOCKOON_SALESFORCE_URL   Salesforce mock URL (default: http://localhost:3020)
  MOCKOON_AUDIT_URL        Audit service URL (default: http://localhost:3050)
  E2E_TIMEOUT_SECONDS      Test timeout in seconds (default: 120)

Examples:
  # Run full test suite
  $(basename "$0")

  # Run without cleanup (keep mocks running)
  $(basename "$0") --no-cleanup

  # Run with verbose output
  $(basename "$0") --verbose

  # Run against existing mocks
  $(basename "$0") --skip-mocks

Exit Codes:
  0  All tests passed
  1  Tests failed
  2  Setup failed (dependencies, mocks)
  3  Cleanup failed

EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-cleanup)
                NO_CLEANUP=true
                shift
                ;;
            --skip-mocks)
                SKIP_MOCKS=true
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 2
                ;;
        esac
    done
}

# ─────────────────────────────────────────────────────────────────────────────
# Main Execution
# ─────────────────────────────────────────────────────────────────────────────

main() {
    parse_args "$@"

    trap cleanup EXIT

    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║     Invoicify E2E Full Workflow Test Runner              ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""

    # Check dependencies
    if ! check_dependencies; then
        log_error "Dependency check failed"
        exit 2
    fi

    # Setup directories
    setup_directories

    # Install test dependencies
    if ! install_test_dependencies; then
        log_error "Failed to install test dependencies"
        exit 2
    fi

    # Start mock services (unless skipped)
    if [[ "$SKIP_MOCKS" == "false" ]]; then
        if ! start_all_mocks; then
            log_error "Failed to start mock services"
            exit 2
        fi
    else
        log_warning "Skipping mock startup (--skip-mocks)"
    fi

    # Run E2E tests
    local test_exit_code=0
    run_e2e_tests || test_exit_code=$?

    # Print summary
    print_summary "$test_exit_code"

    exit $test_exit_code
}

# Run main function
main "$@"
