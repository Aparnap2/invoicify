#!/bin/bash
# Verify no secrets are present in the repository

set -e

echo "🔒 SECURITY VERIFICATION SCAN"
echo "=============================="
echo ""

# Patterns to check
PATTERNS=(
    "sk-or-v1-[0-9a-f]{64}"
    "sk-[0-9a-zA-Z]{48}"
    "ghp_[0-9a-zA-Z]{36}"
    "AKIA[0-9A-Z]{16}"
)

FOUND=0

echo "Scanning working directory (excluding .venv, SECURITY_ADVISORY.md)..."
for pattern in "${PATTERNS[@]}"; do
    if grep -r -E "$pattern" --include="*.py" --include="*.md" --include="*.txt" --include="*.env" \
        --exclude="SECURITY_ADVISORY.md" \
        --exclude-dir=".venv" \
        --exclude-dir="node_modules" \
        . 2>/dev/null; then
        echo "❌ Found potential secret matching: $pattern"
        FOUND=1
    fi
done

echo ""
echo "=============================="
if [ $FOUND -eq 1 ]; then
    echo "❌ VERIFICATION FAILED"
    echo ""
    echo "Secrets were detected in working directory."
    echo "Please remove hardcoded secrets and use environment variables."
    exit 1
else
    echo "✅ WORKING DIRECTORY: CLEAN"
    echo ""
    echo "Note: Git history may still contain old commits with secrets."
    echo "To clean history, run: ./scripts/cleanup-git-history.sh"
    exit 0
fi
