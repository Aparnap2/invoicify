#!/bin/bash
# Pre-commit secret scanner
# Automatically scans for secrets before allowing commits

set -e

echo "🔒 Scanning for secrets..."

# Patterns to detect
PATTERNS=(
    'sk-[a-zA-Z0-9]{32,}'
    'api[_-]?key[_-]?=[^$]'
    'password[_-]?=[^$]'
    'secret[_-]?=[^$]'
    'AKIA[0-9A-Z]{16}'
    'ghp_[a-zA-Z0-9]{36}'
)

FOUND=0

for pattern in "${PATTERNS[@]}"; do
    if git diff --cached --name-only | xargs grep -l -E "$pattern" 2>/dev/null; then
        echo "❌ Potential secret detected: $pattern"
        FOUND=1
    fi
done

if [ $FOUND -eq 1 ]; then
    echo ""
    echo "🛑 COMMIT BLOCKED: Potential secrets detected!"
    echo ""
    echo "Please remove secrets and use environment variables instead."
    echo "To bypass (false positive): git commit --no-verify"
    exit 1
fi

echo "✅ No secrets detected"
exit 0
