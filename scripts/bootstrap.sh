#!/bin/bash
# Bootstrap Azure infrastructure and GitHub OIDC
# Usage: ./scripts/bootstrap.sh

set -e

# Your Azure credentials - REPLACE WITH YOUR OWN
SUBSCRIPTION="${AZURE_SUBSCRIPTION_ID:-}"
TENANT="${AZURE_TENANT_ID:-}"
RESOURCE_GROUP="invoicify-rg"
LOCATION="eastus"

# Validate credentials are provided
if [ -z "$SUBSCRIPTION" ] || [ -z "$TENANT" ]; then
    echo "❌ Error: Azure credentials not set"
    echo ""
    echo "Please set environment variables:"
    echo "  export AZURE_SUBSCRIPTION_ID=your-subscription-id"
    echo "  export AZURE_TENANT_ID=your-tenant-id"
    echo ""
    echo "Or edit this script with your actual values."
    exit 1
fi

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           INVOICIFY AZURE BOOTSTRAP                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Login to Azure
echo "🔐 Step 1: Logging into Azure..."
az login --output none
az account set --subscription $SUBSCRIPTION
echo "   ✅ Logged in"
echo ""

# Create resource group
echo "📦 Step 2: Creating resource group..."
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION \
  --output none
echo "   ✅ Resource group created: $RESOURCE_GROUP"
echo ""

# Create OIDC App Registration for GitHub Actions
echo "🔑 Step 3: Creating OIDC App Registration..."
APP_ID=$(az ad app create \
  --display-name "invoicify-github-actions" \
  --query appId \
  --output tsv)

OBJ_ID=$(az ad app show \
  --id $APP_ID \
  --query id \
  --output tsv)

az ad sp create --id $APP_ID
echo "   ✅ App registration created: $APP_ID"
echo ""

# Add federated credential for GitHub OIDC
echo "🔗 Step 4: Adding federated credential..."
az ad app federated-credential create \
  --id $OBJ_ID \
  --parameters '{
    "name": "invoicify-main",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:Aparnap2/invoicify:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'
echo "   ✅ Federated credential added"
echo ""

# Assign Contributor role on resource group
echo "📋 Step 5: Assigning Contributor role..."
az role assignment create \
  --role Contributor \
  --assignee $APP_ID \
  --scope /subscriptions/$SUBSCRIPTION/resourceGroups/$RESOURCE_GROUP \
  --output none
echo "   ✅ Role assigned"
echo ""

# Generate random PostgreSQL password
POSTGRES_PASSWORD=$(openssl rand -base64 24)

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          ADD TO GITHUB SECRETS (REQUIRED)                    ║"
echo "║   https://github.com/Aparnap2/invoicify/settings/secrets    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "AZURE_CLIENT_ID       = $APP_ID"
echo "AZURE_TENANT_ID       = $TENANT"
echo "AZURE_SUBSCRIPTION_ID = $SUBSCRIPTION"
echo "POSTGRES_PASSWORD     = $POSTGRES_PASSWORD"
echo ""
echo "Optional (for full functionality):"
echo "OPENROUTER_API_KEY    = <your OpenRouter key or leave empty for free tier>"
echo "GRAPH_CLIENT_ID       = <Microsoft Graph client ID>"
echo "GRAPH_CLIENT_SECRET   = <Microsoft Graph client secret>"
echo "QUICKBOOKS_CLIENT_ID  = <QuickBooks sandbox client ID>"
echo "QUICKBOOKS_SECRET     = <QuickBooks sandbox client secret>"
echo "SECRET_KEY            = <random secret key for sessions>"
echo "SENTRY_DSN            = <Sentry DSN for error tracking>"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "⚠️  SAVE THE POSTGRES_PASSWORD ABOVE - YOU'LL NEED IT!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
read -p "Press Enter after adding secrets to GitHub..."

# Deploy infrastructure
echo ""
echo "🚀 Step 6: Deploying infrastructure with Bicep..."
az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file infra/main.bicep \
  --parameters \
    environment=prod \
    location=$LOCATION \
    appName=invoicify \
    tenantId=$TENANT \
    subscriptionId=$SUBSCRIPTION \
    postgresPassword=$POSTGRES_PASSWORD \
    openRouterApiKey="${OPENROUTER_API_KEY:-}" \
    graphClientId="${GRAPH_CLIENT_ID:-}" \
    graphClientSecret="${GRAPH_CLIENT_SECRET:-}" \
    quickbooksClientId="${QUICKBOOKS_CLIENT_ID:-}" \
    quickbooksClientSecret="${QUICKBOOKS_CLIENT_SECRET:-}" \
    secretKey="${SECRET_KEY:-dev-secret-key-change-in-prod}"

echo "   ✅ Infrastructure deployed"
echo ""

# Seed Key Vault with secrets
echo "🔐 Step 7: Seeding Key Vault with secrets..."
bash scripts/seed-keyvault.sh \
  "$POSTGRES_PASSWORD" \
  "${OPENROUTER_API_KEY:-}" \
  "${GRAPH_CLIENT_ID:-}" \
  "${GRAPH_CLIENT_SECRET:-}" \
  "${QUICKBOOKS_CLIENT_ID:-}" \
  "${QUICKBOOKS_CLIENT_SECRET:-}" \
  "${SECRET_KEY:-dev-secret-key-change-in-prod}" \
  "${SENTRY_DSN:-}"

echo "   ✅ Key Vault seeded"
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    ✅ DEPLOYMENT COMPLETE                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 RESOURCES CREATED:"
echo "   - Resource Group: $RESOURCE_GROUP"
echo "   - Container Registry: invoicifyregistry"
echo "   - PostgreSQL Server: invoicify-postgres"
echo "   - Service Bus: invoicify-sb"
echo "   - Blob Storage: invoicifystore"
echo "   - Key Vault: invoicify-kv"
echo "   - Document Intelligence: invoicify-docai"
echo "   - AI Search: invoicify-search"
echo "   - Event Grid: invoicify-events"
echo "   - Container Apps: invoicify-api, invoicify-worker, invoicify-beat"
echo "   - Static Web App: invoicify-web"
echo ""
echo "🌐 NEXT STEPS:"
echo "   1. Push to main branch to trigger CI/CD"
echo "   2. Monitor deployment: GitHub → Actions → Deploy Invoicify"
echo "   3. View logs: Azure Portal → Container Apps → Log stream"
echo ""
echo "💰 ESTIMATED COST: \$0/month (all within free tier limits)"
echo ""
