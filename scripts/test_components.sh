#!/bin/bash
# Test individual components

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🧪 Testing Invoicify Components"
echo "================================"

# Test 1: Ollama
echo ""
echo "1️⃣ Testing Ollama..."
if curl -s http://localhost:11434/api/tags > /dev/null; then
    echo -e "${GREEN}✅ Ollama is running${NC}"
    # Show available models
    echo "   Available models:"
    curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | cut -d'"' -f4 | sed 's/^/     - /'
else
    echo -e "${RED}❌ Ollama is not running${NC}"
    echo "   Run: ./scripts/start_ollama.sh"
fi

# Test 2: MinIO (R2)
echo ""
echo "2️⃣ Testing MinIO (R2 storage)..."
if curl -s http://localhost:9000/minio/health/live > /dev/null; then
    echo -e "${GREEN}✅ MinIO is running${NC}"
else
    echo -e "${RED}❌ MinIO is not running${NC}"
    echo "   Run: ./scripts/start_storage.sh"
fi

# Test 3: QuickBooks Mock
echo ""
echo "3️⃣ Testing QuickBooks Mock..."
if curl -s http://localhost:3001/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ QBO Mock is running${NC}"
else
    echo -e "${YELLOW}⚠️  QBO Mock is not running (optional)${NC}"
fi

# Test 4: D1 (via wrangler)
echo ""
echo "4️⃣ Testing D1 Database..."
if [ -f "invoicify-worker/wrangler.toml" ]; then
    echo -e "${GREEN}✅ Wrangler config exists${NC}"
    echo "   Run migrations with: wrangler d1 migrations apply invoicify-db --local"
else
    echo -e "${RED}❌ Wrangler config not found${NC}"
fi

# Test 5: Invoicify Worker
echo ""
echo "5️⃣ Testing Invoicify Worker..."
if curl -s http://localhost:8787/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Worker is running${NC}"
    # Get health status
    curl -s http://localhost:8787/health | sed 's/^/   /'
else
    echo -e "${YELLOW}⚠️  Worker is not running${NC}"
    echo "   Run: cd invoicify-worker && npm run dev"
fi

echo ""
echo "================================"
echo "🎯 Component testing complete!"
