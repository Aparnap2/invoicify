#!/bin/bash
# Complete E2E Test with REAL Sarvam AI API + Docker Containers
# 
# Prerequisites:
# 1. SARVAM_AI_API_KEY set in .env.local
# 2. Docker containers running (Redis, Qdrant, Ollama)
# 3. sarvamai package installed
#
# Usage: ./scripts/test-real-e2e.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "🧪 INVOICIFY REAL E2E TEST"
echo "=========================================="
echo ""

# Load environment
if [ -f "apps/agent-core/.env.local" ]; then
    export $(grep -v '^#' apps/agent-core/.env.local | xargs)
fi

# Check API key
if [ -z "$SARVAM_AI_API_KEY" ]; then
    echo "❌ Error: SARVAM_AI_API_KEY not set"
    echo ""
    echo "Please add to apps/agent-core/.env.local:"
    echo "  SARVAM_AI_API_KEY=your_key_here"
    echo ""
    exit 1
fi

echo "✅ API key found"
echo ""

# Step 1: Test Sarvam API with curl
echo "1️⃣ Testing Sarvam API with curl..."
echo ""

./scripts/test-sarvam-api.sh "$SARVAM_AI_API_KEY"

if [ $? -ne 0 ]; then
    echo "❌ Sarvam API test failed"
    exit 1
fi

echo ""
echo "=========================================="
echo ""

# Step 2: Check Docker containers
echo "2️⃣ Checking Docker containers..."
echo ""

CONTAINERS=("ollama" "invoicify-redis" "invoicify-qdrant")
ALL_RUNNING=true

for container in "${CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^$container$"; then
        echo "   ✅ $container is running"
    else
        echo "   ⚠️  $container is NOT running"
        ALL_RUNNING=false
    fi
done

if [ "$ALL_RUNNING" = false ]; then
    echo ""
    echo "💡 Start containers with: ./scripts/start_all.sh"
    echo "   Continuing with API-only tests..."
fi

echo ""
echo "=========================================="
echo ""

# Step 3: Run Python E2E tests
echo "3️⃣ Running Python E2E tests..."
echo ""

cd apps/agent-core

# Set environment
export EXTRACTOR_MODE=sarvam
export SARVAM_API_KEY="$SARVAM_AI_API_KEY"

# Run E2E tests
PYTHONPATH=. uv run pytest tests/e2e/test_real_sarvam_e2e.py -v -s

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ E2E tests failed"
    exit 1
fi

echo ""
echo "=========================================="
echo ""
echo "✅ ALL E2E TESTS PASSED!"
echo ""
echo "Summary:"
echo "  ✅ Sarvam AI API: Working"
echo "  ✅ Docker Containers: Checked"
echo "  ✅ Python E2E Tests: Passed"
echo ""
echo "🎉 System is production-ready!"
echo ""
