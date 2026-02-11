#!/bin/bash
#
# Nivi Test Runner - All Tests
# Usage: ./scripts/test-all.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}           🧪 Nivi Enterprise Test Suite                ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Start infrastructure
echo -e "${YELLOW}📦 Starting test infrastructure...${NC}"
docker-compose -f docker-compose.test.yml down -v 2>/dev/null || true
docker-compose -f docker-compose.test.yml up -d

# Wait for services
echo -e "${YELLOW}⏳ Waiting for services to be healthy...${NC}"
sleep 15

# Check service health
echo -e "${BLUE}🔍 Checking service health...${NC}"
docker-compose -f docker-compose.test.yml ps

# Create Kafka topics
echo -e "${YELLOW}📋 Creating Kafka topics...${NC}"
docker-compose -f docker-compose.test.yml exec -T redpanda \
    rpk topic create invoice.ingested --brokers localhost:9092 2>/dev/null || true
docker-compose -f docker-compose.test.yml exec -T redpanda \
    rpk topic create invoice.processed --brokers localhost:9092 2>/dev/null || true
docker-compose -f docker-compose.test.yml exec -T redpanda \
    rpk topic create invoice.approval_needed --brokers localhost:9092 2>/dev/null || true

# Run tests
echo ""
echo -e "${GREEN}🧪 Running test suite...${NC}"
echo ""

docker-compose -f docker-compose.test.yml exec -T test-runner pytest \
    --cov=temporal \
    --cov=ai \
    --cov-report=html \
    --cov-report=term-missing:skip-covered \
    --tb=short \
    --color=yes \
    -v 2>&1 | tee test-output.log

TEST_EXIT_CODE=${PIPESTATUS[0]}

# Generate report
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
else
    echo -e "${RED}❌ Some tests failed (exit code: $TEST_EXIT_CODE)${NC}"
fi
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"

# Show coverage
echo ""
echo -e "${YELLOW}📊 Coverage report available at: htmlcov/index.html${NC}"

# Cleanup prompt
echo ""
read -p "🧹 Do you want to stop test infrastructure? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Stopping services...${NC}"
    docker-compose -f docker-compose.test.yml down -v
    echo -e "${GREEN}✅ Cleanup complete${NC}"
else
    echo -e "${YELLOW}⚠️  Services still running. Use 'docker-compose -f docker-compose.test.yml down' to stop.${NC}"
fi

exit $TEST_EXIT_CODE
