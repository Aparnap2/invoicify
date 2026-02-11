#!/bin/bash
#
# Nivi Integration Tests
# Usage: ./scripts/test-integration.sh
#

set -e

echo "🔗 Running integration tests..."

docker-compose -f docker-compose.test.yml exec -T test-runner pytest \
    temporal/tests/integration ai/tests/integration \
    -v --tb=short --color=yes --timeout=120
