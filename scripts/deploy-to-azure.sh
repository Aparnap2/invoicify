#!/bin/bash
# Deploy Invoicify to Azure Container Apps
# Usage: ./scripts/deploy-to-azure.sh

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           INVOICIFY AZURE DEPLOYMENT SCRIPT                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────
RESOURCE_GROUP="invoicify-rg"
LOCATION="eastus"
ACR_NAME="invoicifyacr$(openssl rand -hex 4)"
ENVIRONMENT_NAME="invoicify-env"
WORKSPACE_NAME="invoicify-log-analytics"
KEY_VAULT_NAME="invoicify-kv$(openssl rand -hex 4)"
CONTAINER_APP_NAME="invoicify-agent-core"

echo "📋 DEPLOYMENT CONFIGURATION"
echo "============================"
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "ACR Name: $ACR_NAME"
echo "Environment: $ENVIRONMENT_NAME"
echo "Key Vault: $KEY_VAULT_NAME"
echo "Container App: $CONTAINER_APP_NAME"
echo ""

# ─────────────────────────────────────────────────────────────────────
# Step 1: Login to Azure
# ─────────────────────────────────────────────────────────────────────
echo "🔐 Step 1: Logging into Azure..."
az login --output none
echo "   ✅ Logged in"
echo ""

# ─────────────────────────────────────────────────────────────────────
# Step 2: Create Resource Group
# ─────────────────────────────────────────────────────────────────────
echo "📦 Step 2: Creating resource group..."
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION \
  --output none
echo "   ✅ Resource group created"
echo ""

# ─────────────────────────────────────────────────────────────────────
# Step 3: Create Container Registry
# ─────────────────────────────────────────────────────────────────────
echo "🛳️  Step 3: Creating Azure Container Registry..."
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true \
  --output none
echo "   ✅ Container registry created: $ACR_NAME"
echo ""

# ─────────────────────────────────────────────────────────────────────
# Step 4: Create Log Analytics Workspace
# ─────────────────────────────────────────────────────────────────────
echo "📊 Step 4: Creating Log Analytics workspace..."
az monitor log-analytics workspace create \
  --resource-group $RESOURCE_GROUP \
  --workspace-name $WORKSPACE_NAME \
  --output none

WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group $RESOURCE_GROUP \
  --workspace-name $WORKSPACE_NAME \
  --query customerId \
  --output tsv)

WORKSPACE_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group $RESOURCE_GROUP \
  --workspace-name $WORKSPACE_NAME \
  --query primarySharedKey \
  --output tsv)

echo "   ✅ Log Analytics workspace created"
echo ""

# ─────────────────────────────────────────────────────────────────────
# Step 5: Create Container Apps Environment
# ─────────────────────────────────────────────────────────────────────
echo "🌍 Step 5: Creating Container Apps environment..."
az containerapp env create \
  --name $ENVIRONMENT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --logs-workspace-id $WORKSPACE_ID \
  --logs-workspace-key $WORKSPACE_KEY \
  --output none
echo "   ✅ Container Apps environment created"
echo ""

# ─────────────────────────────────────────────────────────────────────
# Step 6: Create Azure Key Vault
# ─────────────────────────────────────────────────────────────────────
echo "🔑 Step 6: Creating Azure Key Vault..."
az keyvault create \
  --name $KEY_VAULT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku standard \
  --output none
echo "   ✅ Key Vault created: $KEY_VAULT_NAME"
echo ""

# ─────────────────────────────────────────────────────────────────────
# Step 7: Store Secrets in Key Vault
# ─────────────────────────────────────────────────────────────────────
echo "🔐 Step 7: Storing secrets in Key Vault..."

# Prompt for secrets
read -p "Enter Sarvam AI API Key (or press Enter to skip): " SARVAM_KEY
if [ -n "$SARVAM_KEY" ]; then
  az keyvault secret set \
    --vault-name $KEY_VAULT_NAME \
    --name "SARVAM-AI-API-KEY" \
    --value "$SARVAM_KEY" \
    --output none
  echo "   ✅ Sarvam AI API Key stored"
fi

read -p "Enter Azure OpenAI Key (or press Enter to skip): " AZURE_KEY
if [ -n "$AZURE_KEY" ]; then
  az keyvault secret set \
    --vault-name $KEY_VAULT_NAME \
    --name "AZURE-OPENAI-KEY" \
    --value "$AZURE_KEY" \
    --output none
  echo "   ✅ Azure OpenAI Key stored"
fi

read -p "Enter Azure OpenAI Endpoint (or press Enter to skip): " AZURE_ENDPOINT
if [ -n "$AZURE_ENDPOINT" ]; then
  az keyvault secret set \
    --vault-name $KEY_VAULT_NAME \
    --name "AZURE-OPENAI-ENDPOINT" \
    --value "$AZURE_ENDPOINT" \
    --output none
  echo "   ✅ Azure OpenAI Endpoint stored"
fi

echo ""

# ─────────────────────────────────────────────────────────────────────
# Step 8: Build and Push Docker Image
# ─────────────────────────────────────────────────────────────────────
echo "🐳 Step 8: Building Docker image..."
cd /home/aparna/Desktop/invoicify

docker build -t invoicify-agent:latest \
  -f apps/agent-core/Dockerfile \
  apps/agent-core/

echo "   ✅ Docker image built"
echo ""

# ─────────────────────────────────────────────────────────────────────
# Step 9: Push to Azure Container Registry
# ─────────────────────────────────────────────────────────────────────
echo "📤 Step 9: Pushing image to Azure Container Registry..."
az acr login --name $ACR_NAME

docker tag invoicify-agent:latest \
  $ACR_NAME.azurecr.io/invoicify-agent:latest

docker push $ACR_NAME.azurecr.io/invoicify-agent:latest
echo "   ✅ Image pushed to ACR"
echo ""

# ─────────────────────────────────────────────────────────────────────
# Step 10: Deploy to Azure Container Apps
# ─────────────────────────────────────────────────────────────────────
echo "🚀 Step 10: Deploying to Azure Container Apps..."

KEY_VAULT_URI=$(az keyvault show \
  --name $KEY_VAULT_NAME \
  --resource-group $RESOURCE_GROUP \
  --query properties.vaultUri \
  --output tsv)

az containerapp create \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image $ACR_NAME.azurecr.io/invoicify-agent:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 5 \
  --cpu 0.5 \
  --memory 1.0 \
  --env-vars \
    ENVIRONMENT=prod \
    KEY_VAULT_URI=$KEY_VAULT_URI \
  --secrets \
    sarvam-api-key=ref:sarvam-ai-api-key \
    azure-openai-key=ref:azure-openai-key \
    azure-openai-endpoint=ref:azure-openai-endpoint

echo "   ✅ Container app deployed"
echo ""

# ─────────────────────────────────────────────────────────────────────
# Step 11: Get Application URL
# ─────────────────────────────────────────────────────────────────────
echo "🌐 Step 11: Getting application URL..."
FQDN=$(az containerapp show \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn \
  --output tsv)

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    ✅ DEPLOYMENT COMPLETE                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 DEPLOYMENT SUMMARY"
echo "====================="
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "Container Registry: $ACR_NAME"
echo "Container Apps Env: $ENVIRONMENT_NAME"
echo "Key Vault: $KEY_VAULT_NAME"
echo "Container App: $CONTAINER_APP_NAME"
echo ""
echo "🌐 APPLICATION URL"
echo "=================="
echo "https://$FQDN"
echo ""
echo "🧪 TEST YOUR DEPLOYMENT"
echo "======================="
echo "curl https://$FQDN/health"
echo ""
echo "curl -X POST https://$FQDN/api/v1/invoices \\"
echo "  -F \"file=@tests/fixtures/invoice_hindi.jpeg\" \\"
echo "  -F \"tenant_id=test-tenant\""
echo ""
echo "📝 NEXT STEPS"
echo "============="
echo "1. Configure CI/CD: .github/workflows/deploy.yml"
echo "2. Set up monitoring: Azure Monitor → Log Analytics"
echo "3. Configure backups: Azure Backup → Cosmos DB"
echo "4. Set up alerts: Azure Monitor → Alerts"
echo ""
echo "💰 ESTIMATED COST"
echo "================="
echo "$0-10/month (within free tier limits)"
echo ""
