#!/bin/bash
# Comprehensive Repository Security Cleanup
# This script removes all traces of leaked API keys from git history

set -e

echo "🔒 INVOICIFY REPOSITORY SECURITY CLEANUP"
echo "=========================================="
echo ""
echo "⚠️  WARNING: This script will rewrite git history!"
echo "    All collaborators will need to re-clone the repository."
echo ""
read -p "Continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Cleanup aborted."
    exit 1
fi

echo ""
echo "📋 Step 1: Creating backup branch..."
git branch backup-before-cleanup-$(date +%Y%m%d-%H%M%S)
echo "✅ Backup created"

echo ""
echo "📋 Step 2: Installing BFG Repo-Cleaner..."
if command -v bfg &> /dev/null; then
    echo "BFG already installed"
else
    echo "Please install BFG from: https://rtyley.github.io/bfg-repo-cleaner/"
    echo "Or run: brew install bfg (macOS)"
    exit 1
fi

echo ""
echo "📋 Step 3: Creating passwords.txt for replacement..."
cat > passwords.txt << 'EOF'
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==>REDACTED_OPENROUTER_KEY
EOF
echo "✅ passwords.txt created"

echo ""
echo "📋 Step 4: Running BFG to remove secrets..."
bfg --replace-text passwords.txt --no-blob-protection .

echo ""
echo "📋 Step 5: Removing dangling commits..."
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo ""
echo "📋 Step 6: Verifying cleanup..."
if git rev-list --all | xargs git grep -l "sk-or-v1-0fb14" 2>/dev/null; then
    echo "❌ FAILED: Secret still found in history!"
    exit 1
else
    echo "✅ SUCCESS: No secrets found in history"
fi

echo ""
echo "📋 Step 7: Updating .gitignore..."
# Already updated in previous commit

echo ""
echo "📋 Step 8: Installing pre-commit hook..."
cp .githooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
echo "✅ Pre-commit hook installed"

echo ""
echo "=========================================="
echo "✅ CLEANUP COMPLETE!"
echo "=========================================="
echo ""
echo "NEXT STEPS:"
echo "1. Force push to GitHub:"
echo "   git push --force origin feat/azure-native-migration"
echo ""
echo "2. Notify all collaborators to re-clone:"
echo "   git clone <repo-url>"
echo ""
echo "3. Rotate the compromised API key at:"
echo "   https://openrouter.ai/keys"
echo ""
echo "4. Close the GitHub security alert as 'revoked'"
echo ""
echo "5. Delete backup branch when confident:"
echo "   git branch -D backup-before-cleanup-*"
echo ""
