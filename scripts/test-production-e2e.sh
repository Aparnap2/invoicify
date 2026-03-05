#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Invoicify Production E2E Test
# Tests with REAL Azure services + REAL Docker containers
# ═══════════════════════════════════════════════════════════════

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║     Invoicify Production E2E Test                        ║"
echo "║     Real Azure + Real Docker + Real Data                 ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Load environment
if [ -f ".env.azure" ]; then
    export $(grep -v '^#' .env.azure | xargs)
elif [ -f "apps/agent-core/.env.local" ]; then
    export $(grep -v '^#' apps/agent-core/.env.local | xargs)
fi

# ═══════════════════════════════════════════════════════════════
# Step 1: Validate Environment
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Step 1: Validating Environment${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Check Azure credentials
required_vars=(
    "AZURE_OPENAI_ENDPOINT"
    "AZURE_OPENAI_API_KEY"
    "AZURE_OPENAI_DEPLOYMENT"
    "SARVAM_AI_API_KEY"
    "AZURE_STORAGE_ACCOUNT"
    "AZURE_STORAGE_KEY"
)

missing_vars=()
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    echo -e "${RED}[ERROR] Missing required environment variables:${NC}"
    for var in "${missing_vars[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "Please set these in .env.azure or apps/agent-core/.env.local"
    exit 1
fi

echo -e "${GREEN}[✓] Azure credentials validated${NC}"

# Check Docker containers
echo ""
echo "Checking Docker containers..."

check_container() {
    local name=$1
    local port=$2
    if docker ps --format '{{.Names}}' | grep -q "^$name$"; then
        echo -e "${GREEN}[✓] $name running on port $port${NC}"
        return 0
    else
        echo -e "${YELLOW}[!] $name not running (optional for this test)${NC}"
        return 1
    fi
}

check_container "invoicify-redis" "6379" || true
check_container "invoicify-qdrant" "6333" || true

echo ""

# ═══════════════════════════════════════════════════════════════
# Step 2: Start Mock Services
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Step 2: Starting Mock Services${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Check if Mockoon CLI is available
if ! command -v mockoon &> /dev/null; then
    echo -e "${YELLOW}[WARNING] Mockoon CLI not found. Installing...${NC}"
    npm install -g @mockoon/cli > /dev/null 2>&1
fi

# Start QuickBooks mock
echo "Starting QuickBooks mock on port 3010..."
mockoon-cli start \
    --data mocks/quickbooks-prod-mock.json \
    --port 3010 \
    --log-file logs/quickbooks-mock.log &
QB_PID=$!
sleep 2

# Verify QuickBooks mock
if curl -s http://localhost:3010/health > /dev/null; then
    echo -e "${GREEN}[✓] QuickBooks mock started (PID: $QB_PID)${NC}"
else
    echo -e "${RED}[✗] QuickBooks mock failed to start${NC}"
    exit 1
fi

# Start Salesforce mock
echo "Starting Salesforce mock on port 3020..."
mockoon-cli start \
    --data mocks/salesforce-prod-mock.json \
    --port 3020 \
    --log-file logs/salesforce-mock.log &
SF_PID=$!
sleep 2

# Verify Salesforce mock
if curl -s http://localhost:3020/health > /dev/null; then
    echo -e "${GREEN}[✓] Salesforce mock started (PID: $SF_PID)${NC}"
else
    echo -e "${RED}[✗] Salesforce mock failed to start${NC}"
    exit 1
fi

echo ""

# ═══════════════════════════════════════════════════════════════
# Step 3: Run Production E2E Test
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Step 3: Running Production E2E Test${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

cd apps/agent-core

# Create reports directory
mkdir -p ../../reports/e2e

# Run the test
PYTHONPATH=. uv run pytest tests/e2e/test_production_e2e.py \
    -v \
    --tb=short \
    --json-report \
    --json-report-file=../../reports/e2e/production-e2e-report.json \
    --junitxml=../../reports/e2e/production-e2e-results.xml \
    -o log_cli=true \
    -o log_cli_level=INFO \
    2>&1 | tee ../../reports/e2e/production-e2e-output.log

TEST_EXIT_CODE=${PIPESTATUS[0]}

cd ../..

echo ""

# ═══════════════════════════════════════════════════════════════
# Step 4: Cleanup
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Step 4: Cleanup${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

echo "Stopping mock services..."
mockoon-cli stop --port 3010 2>/dev/null || true
mockoon-cli stop --port 3020 2>/dev/null || true

# Kill by PID if still running
kill $QB_PID 2>/dev/null || true
kill $SF_PID 2>/dev/null || true

echo -e "${GREEN}[✓] Mock services stopped${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════
# Step 5: Report
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Step 5: Test Report${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║           PRODUCTION E2E TEST PASSED ✓                    ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Reports generated:"
    echo "  - reports/e2e/production-e2e-report.json"
    echo "  - reports/e2e/production-e2e-results.xml"
    echo "  - reports/e2e/production-e2e-output.log"
    echo ""
    echo -e "${GREEN}Ready for production deployment! 🚀${NC}"
else
    echo -e "${RED}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║           PRODUCTION E2E TEST FAILED ✗                    ║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Check logs:"
    echo "  - reports/e2e/production-e2e-output.log"
    echo ""
    echo -e "${YELLOW}Fix issues before deploying.${NC}"
fi

echo ""
exit $TEST_EXIT_CODE
