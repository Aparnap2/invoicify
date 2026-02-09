#!/bin/bash
#
# Nivi E2E Tests
# Usage: ./scripts/test-e2e.sh
#

set -e

echo "🎭 Running E2E tests..."

docker-compose -f docker-compose.test.yml exec -T test-runner pytest \
    tests/e2e \
    -v --tb=short --color=yes --timeout=300
