#!/bin/bash
#
# Nivi Unit Tests Only
# Usage: ./scripts/test-unit.sh [test_pattern]
#

set -e

PATTERN=${1:-""}

echo "🧪 Running unit tests..."

if [ -n "$PATTERN" ]; then
    echo "🔍 Pattern: $PATTERN"
    docker-compose -f docker-compose.test.yml exec -T test-runner pytest \
        temporal/tests/unit ai/tests/unit \
        -k "$PATTERN" \
        -v --tb=short --color=yes
else
    docker-compose -f docker-compose.test.yml exec -T test-runner pytest \
        temporal/tests/unit ai/tests/unit \
        -v --tb=short --color=yes
fi
