#!/bin/bash
#
# Watch mode for TDD
# Usage: ./scripts/test-watch.sh [pattern]
#

PATTERN=${1:-""}

echo "👀 Starting watch mode..."
echo "Tests will re-run on file changes"
echo ""

if [ -n "$PATTERN" ]; then
    docker-compose -f docker-compose.test.yml exec test-runner ptw --runner "pytest -v -k $PATTERN"
else
    docker-compose -f docker-compose.test.yml exec test-runner ptw --runner "pytest -v"
fi
