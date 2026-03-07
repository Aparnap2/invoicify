#!/bin/bash
# Seed Key Vault with all required secrets
# Usage: ./scripts/seed-keyvault.sh POSTGRES_PASSWORD OPENROUTER_KEY GRAPH_ID GRAPH_SECRET QB_ID QB_SECRET SECRET_KEY SENTRY_DSN

set -e

KV="invoicify-kv"
RG="invoicify-rg"

POSTGRES_PASSWORD="${1:-}"
OPENROUTER_API_KEY="${2:-}"
GRAPH_CLIENT_ID="${3:-}"
GRAPH_CLIENT_SECRET="${4:-}"
QUICKBOOKS_CLIENT_ID="${5:-}"
QUICKBOOKS_CLIENT_SECRET="${6:-}"
SECRET_KEY="${7:-dev-secret-key-change-in-prod}"
SENTRY_DSN="${8:-}"

echo "🔐 Seeding Key Vault: $KV"
echo ""

# Get PostgreSQL host
echo "📊 Getting PostgreSQL connection string..."
POSTGRES_HOST=$(az postgres flexible-server show \
  --name invoicify-postgres \
  --resource-group $RG \
  --query fullyQualifiedDomainName \
  --output tsv)

# PostgreSQL connection string (asyncpg format for SQLAlchemy)
DB_URL="postgresql+asyncpg://invoicify_admin:${POSTGRES_PASSWORD}@${POSTGRES_HOST}/invoicify?ssl=require"
az keyvault secret set \
  --vault-name $KV \
  --name "db-url" \
  --value "$DB_URL" \
  --output none
echo "   ✅ db-url"

# Service Bus connection string (Celery broker)
echo "📬 Getting Service Bus connection string..."
SB_CONN=$(az servicebus namespace authorization-rule keys list \
  --resource-group $RG \
  --namespace-name invoicify-sb \
  --name RootManageSharedAccessKey \
  --query primaryConnectionString \
  --output tsv)

az keyvault secret set \
  --vault-name $KV \
  --name "sb-conn" \
  --value "$SB_CONN" \
  --output none
echo "   ✅ sb-conn"

# Document Intelligence key
echo "📄 Getting Document Intelligence key..."
DOC_KEY=$(az cognitiveservices account keys list \
  --resource-group $RG \
  --name invoicify-docai \
  --query key1 \
  --output tsv)

az keyvault secret set \
  --vault-name $KV \
  --name "doc-intelligence-key" \
  --value "$DOC_KEY" \
  --output none
echo "   ✅ doc-intelligence-key"

# AI Search key
echo "🔍 Getting AI Search key..."
SEARCH_KEY=$(az search admin-key show \
  --resource-group $RG \
  --service-name invoicify-search \
  --query primaryKey \
  --output tsv)

az keyvault secret set \
  --vault-name $KV \
  --name "search-key" \
  --value "$SEARCH_KEY" \
  --output none
echo "   ✅ search-key"

# Storage account key
echo "💾 Getting Storage account key..."
STORAGE_KEY=$(az storage account keys list \
  --resource-group $RG \
  --account-name invoicifystore \
  --query "[0].value" \
  --output tsv)

az keyvault secret set \
  --vault-name $KV \
  --name "azure-storage-key" \
  --value "$STORAGE_KEY" \
  --output none
echo "   ✅ azure-storage-key"

# External secrets (optional)
if [ -n "$OPENROUTER_API_KEY" ]; then
  az keyvault secret set \
    --vault-name $KV \
    --name "openrouter-api-key" \
    --value "$OPENROUTER_API_KEY" \
    --output none
  echo "   ✅ openrouter-api-key"
fi

if [ -n "$GRAPH_CLIENT_ID" ]; then
  az keyvault secret set \
    --vault-name $KV \
    --name "graph-client-id" \
    --value "$GRAPH_CLIENT_ID" \
    --output none
  echo "   ✅ graph-client-id"
fi

if [ -n "$GRAPH_CLIENT_SECRET" ]; then
  az keyvault secret set \
    --vault-name $KV \
    --name "graph-client-secret" \
    --value "$GRAPH_CLIENT_SECRET" \
    --output none
  echo "   ✅ graph-client-secret"
fi

if [ -n "$QUICKBOOKS_CLIENT_ID" ]; then
  az keyvault secret set \
    --vault-name $KV \
    --name "quickbooks-client-id" \
    --value "$QUICKBOOKS_CLIENT_ID" \
    --output none
  echo "   ✅ quickbooks-client-id"
fi

if [ -n "$QUICKBOOKS_CLIENT_SECRET" ]; then
  az keyvault secret set \
    --vault-name $KV \
    --name "quickbooks-client-secret" \
    --value "$QUICKBOOKS_CLIENT_SECRET" \
    --output none
  echo "   ✅ quickbooks-client-secret"
fi

az keyvault secret set \
  --vault-name $KV \
  --name "secret-key" \
  --value "$SECRET_KEY" \
  --output none
echo "   ✅ secret-key"

if [ -n "$SENTRY_DSN" ]; then
  az keyvault secret set \
    --vault-name $KV \
    --name "sentry-dsn" \
    --value "$SENTRY_DSN" \
    --output none
  echo "   ✅ sentry-dsn"
fi

echo ""
echo "✅ All secrets seeded to $KV"
