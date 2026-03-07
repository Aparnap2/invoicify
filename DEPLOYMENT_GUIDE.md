# 🚀 DEPLOY INVOICIFY TO AZURE - COMPLETE GUIDE

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    INVOICIFY AZURE DEPLOYMENT GUIDE                           ║
║                                                                              ║
║  Production-Ready Deployment to Azure Container Apps + Functions             ║
║  With Key Vault, Container Registry, and GitHub Actions CI/CD                ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## 📖 TABLE OF CONTENTS

```
├── 1. PREREQUISITES
├── 2. AZURE RESOURCES TO CREATE
├── 3. DEPLOYMENT OPTIONS
│   ├── Option A: Azure Container Apps (Recommended)
│   ├── Option B: Azure Functions (Serverless)
│   └── Option C: Azure App Service (Traditional)
├── 4. STEP-BY-STEP DEPLOYMENT
├── 5. SECRETS MANAGEMENT
├── 6. CI/CD PIPELINE
└── 7. POST-DEPLOYMENT VERIFICATION
```

---

## 1. PREREQUISITES

### 1.1 Install Required Tools

```bash
# Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Docker
sudo apt-get install docker.io

# Python 3.11+
python3 --version  # Should be 3.11 or higher

# Azure Container Apps extension
az extension add --name containerapp --upgrade

# Container Apps environment provider
az provider register --namespace Microsoft.App

# Container Apps Infrastructure provider
az provider register --namespace Microsoft.OperationalInsights
```

### 1.2 Login to Azure

```bash
# Login to Azure
az login

# Set subscription (if you have multiple)
az account set --subscription "YOUR_SUBSCRIPTION_ID"

# Verify
az account show
```

### 1.3 Check Free Tier Eligibility

```bash
# Check your Azure subscription type
az account show --query "offerType"

# Should return: "FreeTrial" or "PayAsYouGo"
```

---

## 2. AZURE RESOURCES TO CREATE

### 2.1 Resource Group

```bash
# Create resource group
RESOURCE_GROUP="invoicify-rg"
LOCATION="eastus"

az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION
```

### 2.2 Azure Container Registry (ACR)

```bash
# Create container registry
ACR_NAME="invoicifyacr$(openssl rand -hex 4)"

az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true
```

### 2.3 Azure Container Apps Environment

```bash
# Create Log Analytics workspace
WORKSPACE_NAME="invoicify-log-analytics"

az monitor log-analytics workspace create \
  --resource-group $RESOURCE_GROUP \
  --workspace-name $WORKSPACE_NAME

# Get workspace ID
WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group $RESOURCE_GROUP \
  --workspace-name $WORKSPACE_NAME \
  --query customerId \
  --output tsv)

# Get workspace key
WORKSPACE_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group $RESOURCE_GROUP \
  --workspace-name $WORKSPACE_NAME \
  --query primarySharedKey \
  --output tsv)

# Create Container Apps environment
ENVIRONMENT_NAME="invoicify-env"

az containerapp env create \
  --name $ENVIRONMENT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --logs-workspace-id $WORKSPACE_ID \
  --logs-workspace-key $WORKSPACE_KEY
```

### 2.4 Azure Key Vault (Secrets Management)

```bash
# Create Key Vault
KEY_VAULT_NAME="invoicify-kv$(openssl rand -hex 4)"

az keyvault create \
  --name $KEY_VAULT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku standard

# Store secrets
az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "SARVAM-AI-API-KEY" \
  --value "your_sarvam_api_key_here"

az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "AZURE-OPENAI-KEY" \
  --value "your_azure_openai_key_here"

az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "AZURE-OPENAI-ENDPOINT" \
  --value "https://your-resource.openai.azure.com/"

az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "COSMOS-DB-KEY" \
  --value "your_cosmos_db_key_here"

az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "MSSQL-SA-PASSWORD" \
  --value "YourSecurePassword123!"
```

### 2.5 Azure Cosmos DB (Optional - for production)

```bash
# Create Cosmos DB account
COSMOS_ACCOUNT="invoicify-cosmos$(openssl rand -hex 4)"

az cosmosdb create \
  --resource-group $RESOURCE_GROUP \
  --name $COSMOS_ACCOUNT \
  --kind GlobalDocumentDB \
  --locations regionName=$LOCATION failoverPriority=0 isZoneRedundant=false

# Get Cosmos DB key
COSMOS_KEY=$(az cosmosdb keys list \
  --name $COSMOS_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --query primaryMasterKey \
  --output tsv)

# Update Key Vault with actual key
az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "COSMOS-DB-KEY" \
  --value "$COSMOS_KEY"
```

### 2.6 Azure SQL Database (Optional - for production)

```bash
# Create SQL Server
SQL_SERVER="invoicify-sql$(openssl rand -hex 4)"

az sql server create \
  --name $SQL_SERVER \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --admin-user sqladmin \
  --admin-password "YourSecurePassword123!"

# Create database
az sql db create \
  --resource-group $RESOURCE_GROUP \
  --server $SQL_SERVER \
  --name invoicify-db \
  --sample-name AdventureWorksLT \
  --edition Free

# Get connection string
SQL_CONNECTION_STRING=$(az sql db show-connection-string \
  --client ado.net \
  --name invoicify-db \
  --server $SQL_SERVER \
  --resource-group $RESOURCE_GROUP)

echo "SQL Connection String: $SQL_CONNECTION_STRING"
```

---

## 3. DEPLOYMENT OPTIONS

### Option A: Azure Container Apps (Recommended) ✅

**Best for:**
- Microservices architecture
- Auto-scaling based on demand
- Cost-effective (pay per request)
- Easy CI/CD integration

**Estimated Cost:** $5-20/month (free tier eligible)

### Option B: Azure Functions

**Best for:**
- Event-driven processing
- Serverless architecture
- Pay-per-execution model

**Estimated Cost:** $0-10/month (1M executions free)

### Option C: Azure App Service

**Best for:**
- Traditional web apps
- Always-on requirements
- Simple deployment

**Estimated Cost:** $13-50/month (F1 free tier available)

---

## 4. STEP-BY-STEP DEPLOYMENT

### 4.1 Build Docker Image

```bash
cd /home/aparna/Desktop/invoicify

# Build Docker image
docker build -t invoicify-agent:latest \
  -f apps/agent-core/Dockerfile \
  apps/agent-core/

# Tag for ACR
docker tag invoicify-agent:latest \
  $ACR_NAME.azurecr.io/invoicify-agent:latest
```

### 4.2 Push to Azure Container Registry

```bash
# Login to ACR
az acr login --name $ACR_NAME

# Push image
docker push $ACR_NAME.azurecr.io/invoicify-agent:latest
```

### 4.3 Deploy to Azure Container Apps

```bash
# Get Key Vault URI
KEY_VAULT_URI=$(az keyvault show \
  --name $KEY_VAULT_NAME \
  --resource-group $RESOURCE_GROUP \
  --query properties.vaultUri \
  --output tsv)

# Create Container App
az containerapp create \
  --name invoicify-agent-core \
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
    azure-openai-endpoint=ref:azure-openai-endpoint \
    cosmos-db-key=ref:cosmos-db-key \
    mssql-sa-password=ref:mssql-sa-password
```

### 4.4 Deploy to Azure Functions (Alternative)

```bash
# Install Azure Functions Core Tools
npm install -g azure-functions-core-tools@4 --unsafe-perm true

# Navigate to functions directory
cd apps/azure-functions

# Initialize function app
func init --python --docker

# Create HTTP trigger function
func new --name InvoiceProcessor --template "HTTP trigger" --authlevel "anonymous"

# Build and deploy
func azure functionapp publish invoicify-fn --docker
```

---

## 5. SECRETS MANAGEMENT

### 5.1 Local Development (.env.local)

```bash
# Copy example
cp apps/agent-core/.env.example apps/agent-core/.env.local

# Edit with your values
nano apps/agent-core/.env.local
```

### 5.2 Production (Azure Key Vault)

```bash
# Reference secrets in Container Apps
az containerapp update \
  --name invoicify-agent-core \
  --resource-group $RESOURCE_GROUP \
  --secrets \
    sarvam-api-key=ref:sarvam-ai-api-key \
    azure-openai-key=ref:azure-openai-key
```

### 5.3 GitHub Actions Secrets

```bash
# Add secrets to GitHub repository
# Settings → Secrets and variables → Actions

# Required secrets:
AZURE_CREDENTIALS          # Service principal JSON
ACR_NAME                   # Container registry name
RESOURCE_GROUP             # Resource group name
CONTAINER_APP_NAME         # Container app name
```

---

## 6. CI/CD PIPELINE

### 6.1 Create GitHub Actions Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy to Azure Container Apps

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
  AZURE_RESOURCE_GROUP: invoicify-rg
  AZURE_CONTAINER_ENV: invoicify-env
  AZURE_CONTAINER_APP: invoicify-agent-core

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write

    steps:
    - uses: actions/checkout@v4

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Log in to container registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Build and push container image
      uses: docker/build-push-action@v5
      with:
        context: ./apps/agent-core
        file: ./apps/agent-core/Dockerfile
        push: true
        tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}

    - name: Azure Login
      uses: azure/login@v1
      with:
        creds: ${{ secrets.AZURE_CREDENTIALS }}

    - name: Deploy to Azure Container Apps
      uses: azure/CLI@v1
      with:
        inlineScript: |
          az containerapp update \
            --name ${{ env.AZURE_CONTAINER_APP }} \
            --resource-group ${{ env.AZURE_RESOURCE_GROUP }} \
            --image ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
```

### 6.2 Create Azure Service Principal

```bash
# Create service principal
az ad sp create-for-rbac \
  --name "invoicify-gh-actions" \
  --role contributor \
  --scopes /subscriptions/YOUR_SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP \
  --sdk-auth

# Output will be JSON - copy entire output to GitHub secret AZURE_CREDENTIALS
```

---

## 7. POST-DEPLOYMENT VERIFICATION

### 7.1 Get Container App URL

```bash
# Get FQDN
FQDN=$(az containerapp show \
  --name invoicify-agent-core \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn \
  --output tsv)

echo "Application URL: https://$FQDN"
```

### 7.2 Test Health Endpoint

```bash
# Test health endpoint
curl https://$FQDN/health

# Expected response:
# {"status": "ok", "services": {...}}
```

### 7.3 Test Invoice Upload

```bash
# Test invoice upload
curl -X POST https://$FQDN/api/v1/invoices \
  -H "Content-Type: multipart/form-data" \
  -F "file=@tests/fixtures/invoice_hindi.jpeg" \
  -F "tenant_id=test-tenant"

# Expected response:
# {"invoice_id": "...", "status": "SUBMITTED"}
```

### 7.4 Check Logs

```bash
# Stream logs
az containerapp logs show \
  --name invoicify-agent-core \
  --resource-group $RESOURCE_GROUP \
  --follow
```

### 7.5 Monitor in Azure Portal

```bash
# Open Azure Portal
az portal open

# Navigate to:
# Resource Groups → invoicify-rg → Container Apps → invoicify-agent-core
# View: Monitoring → Log stream
```

---

## 8. COST OPTIMIZATION

### 8.1 Free Tier Resources

| Resource | Free Tier | Your Usage | Status |
|----------|-----------|------------|--------|
| Container Apps | 180,000 vCPU-seconds/month | ~50,000 | ✅ Within Free |
| Container Registry | 10 GB storage | ~2 GB | ✅ Within Free |
| Key Vault | 25,000 transactions/month | ~1,000 | ✅ Within Free |
| Functions | 1M executions/month | ~10,000 | ✅ Within Free |
| Cosmos DB | 1,000 RU/s + 25 GB | ~500 RU/s | ✅ Within Free |

**Estimated Monthly Cost: $0-10** (well within free tiers)

### 8.2 Enable Auto-Shutdown (Dev Environment)

```bash
# Create dev environment with auto-shutdown
az containerapp env create \
  --name invoicify-dev-env \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --logs-workspace-id $WORKSPACE_ID \
  --logs-workspace-key $WORKSPACE_KEY \
  --tags Environment=Development AutoShutdown=true
```

---

## 9. TROUBLESHOOTING

### 9.1 Common Issues

**Issue:** Container app won't start
```bash
# Check logs
az containerapp logs show \
  --name invoicify-agent-core \
  --resource-group $RESOURCE_GROUP

# Check revision status
az containerapp revision list \
  --name invoicify-agent-core \
  --resource-group $RESOURCE_GROUP
```

**Issue:** Secrets not loading
```bash
# Verify Key Vault secrets
az keyvault secret list \
  --vault-name $KEY_VAULT_NAME \
  --query "[].name"

# Verify Container App secret references
az containerapp show \
  --name invoicify-agent-core \
  --resource-group $RESOURCE_GROUP \
  --query identity
```

**Issue:** High latency
```bash
# Check replica count
az containerapp show \
  --name invoicify-agent-core \
  --resource-group $RESOURCE_GROUP \
  --query properties.replicas

# Scale up if needed
az containerapp update \
  --name invoicify-agent-core \
  --resource-group $RESOURCE_GROUP \
  --min-replicas 1 \
  --max-replicas 10
```

---

## 10. SECURITY BEST PRACTICES

### 10.1 Network Security

```bash
# Enable internal-only ingress
az containerapp update \
  --name invoicify-agent-core \
  --resource-group $RESOURCE_GROUP \
  --ingress internal

# Add IP restrictions
az containerapp ingress update \
  --name invoicify-agent-core \
  --resource-group $RESOURCE_GROUP \
  --ip-security-restrictions '[{"name":"AllowOffice","ipAddressRange":"YOUR_OFFICE_IP/32","action":"Allow"}]'
```

### 10.2 Managed Identity

```bash
# Enable system-assigned managed identity
az containerapp identity assign \
  --name invoicify-agent-core \
  --resource-group $RESOURCE_GROUP \
  --system-assigned

# Grant Key Vault access
az keyvault set-policy \
  --name $KEY_VAULT_NAME \
  --resource-group $RESOURCE_GROUP \
  --object-id <MANAGED_IDENTITY_OBJECT_ID> \
  --secret-permissions get list
```

### 10.3 Enable HTTPS Only

```bash
# Force HTTPS
az containerapp ingress update \
  --name invoicify-agent-core \
  --resource-group $RESOURCE_GROUP \
  --target-port 8000 \
  --transport auto
```

---

## 📊 DEPLOYMENT CHECKLIST

```
Pre-Deployment:
[ ] Azure CLI installed
[ ] Logged into Azure
[ ] Resource group created
[ ] Container registry created
[ ] Container Apps environment created
[ ] Key Vault created with secrets
[ ] Docker image built and pushed

Deployment:
[ ] Container app created
[ ] Secrets configured
[ ] Health endpoint responding
[ ] Logs streaming correctly
[ ] Monitoring enabled

Post-Deployment:
[ ] Invoice upload tested
[ ] Sarvam OCR tested
[ ] Azure LLM tested
[ ] Trust Battery working
[ ] QuickBooks sync tested (if configured)
[ ] Cost monitoring enabled
```

---

## 🎯 NEXT STEPS

1. **Deploy to Azure** using this guide
2. **Configure CI/CD** with GitHub Actions
3. **Set up monitoring** with Azure Monitor
4. **Enable auto-scaling** based on demand
5. **Configure backups** for databases
6. **Set up alerts** for errors and costs

---

**Deployed with ❤️ by Invoicify Team**  
**Last Updated:** February 27, 2026  
**Version:** 1.0 (Production Deployment Guide)
