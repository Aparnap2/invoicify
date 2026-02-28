# 🚀 DEPLOY INVOICIFY TO AZURE

## ARCHITECTURE OVERVIEW

```
╔══════════════════════════════════════════════════════════════╗
║                    INVOICIFY — FULL AZURE                     ║
║                   $0/month (12 months free)                   ║
╚══════════════════════════════════════════════════════════════╝

User → Azure Static Web Apps (web/ → Next.js)
         FREE always · 100GB BW · .5GB storage

       → Azure Container Apps: invoicify-api (FastAPI)
           FREE always · 180k vCPU-sec/month
           ├── Azure DB for PostgreSQL Flexible B1MS
           │     FREE 12 months · 750hrs · 32GB
           │     ← Alembic migrations run on startup
           ├── Azure Blob Storage
           │     FREE 12 months · 5GB hot
           │     ← PDF storage
           │     ← Celery result backend
           ├── Azure Key Vault
           │     FREE 12 months · 10k transactions
           ├── Azure Document Intelligence
           │     FREE 12 months · 500 pages/month
           │     ← OCR extraction
           ├── Azure AI Search
           │     FREE always · 3 indexes · 50MB
           │     ← Vendor policy RAG
           ├── Azure Event Grid
           │     FREE always · 100k ops/month
           │     ← PDF upload → triggers worker
           └── Microsoft Graph API
                 FREE · Email ingestion

       → Azure Container Apps: invoicify-worker (Celery)
           FREE always · same vCPU pool
           Queues: invoice_processing, validation,
                   export, email_processing, dlq_processing
           Beat: cleanup (1h), health-check (5m), reports (12h)
           └── Azure Service Bus (Standard)
                 FREE 12 months · 750hrs · 13M ops
                 ← Celery broker (replaces Redis)
```

---

## QUICK DEPLOY (5 minutes)

### Prerequisites

```bash
# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Install Docker
sudo apt-get install docker.io

# Login to Azure
az login
```

### One-Command Deploy

```bash
# Make bootstrap script executable
chmod +x scripts/bootstrap.sh

# Run deployment
./scripts/bootstrap.sh
```

**The script will:**
1. ✅ Create resource group
2. ✅ Set up GitHub OIDC authentication
3. ✅ Deploy all Azure resources (Bicep)
4. ✅ Seed Key Vault with secrets
5. ✅ Provide GitHub secrets to add

**After the script:**
1. Add the displayed secrets to GitHub
2. Push to main branch
3. Watch deployment in GitHub Actions

---

## MANUAL DEPLOYMENT

### Step 1: Create GitHub Secrets

Go to: `https://github.com/Aparnap2/invoicify/settings/secrets/actions`

**Required:**
```
AZURE_CLIENT_ID       = <from bootstrap output>
AZURE_TENANT_ID       = <your Azure tenant ID>
AZURE_SUBSCRIPTION_ID = <your Azure subscription ID>
POSTGRES_PASSWORD     = <strong password>
```

**To find your Azure Tenant ID and Subscription ID:**
```bash
# Login to Azure
az login

# Show account info
az account show --query "{tenantId: tenantId, subscriptionId: id}"
```

**Optional (for full functionality):**
```
OPENROUTER_API_KEY    = <your OpenRouter key>
GRAPH_CLIENT_ID       = <Microsoft Graph client ID>
GRAPH_CLIENT_SECRET   = <Microsoft Graph client secret>
QUICKBOOKS_CLIENT_ID  = <QuickBooks sandbox client ID>
QUICKBOOKS_SECRET     = <QuickBooks sandbox client secret>
SECRET_KEY            = <random secret key>
SENTRY_DSN            = <Sentry DSN>
```

### Step 2: Deploy Infrastructure

```bash
az deployment group create \
  --resource-group invoicify-rg \
  --template-file infra/main.bicep \
  --parameters @infra/parameters.json
```

### Step 3: Build and Push

```bash
# Login to ACR
az acr login --name invoicifyregistry

# Build
docker build -t invoicifyregistry.azurecr.io/invoicify-api:latest \
  -f apps/agent-core/Dockerfile \
  apps/agent-core/

# Push
docker push invoicifyregistry.azurecr.io/invoicify-api:latest
```

### Step 4: Deploy Container Apps

```bash
# API
az containerapp update --name invoicify-api \
  --resource-group invoicify-rg \
  --image invoicifyregistry.azurecr.io/invoicify-api:latest

# Worker
az containerapp update --name invoicify-worker \
  --resource-group invoicify-rg \
  --image invoicifyregistry.azurecr.io/invoicify-api:latest

# Beat
az containerapp update --name invoicify-beat \
  --resource-group invoicify-rg \
  --image invoicifyregistry.azurecr.io/invoicify-api:latest
```

---

## POST-DEPLOYMENT

### Test Health Endpoint

```bash
# Get FQDN
FQDN=$(az containerapp show \
  --name invoicify-api \
  --resource-group invoicify-rg \
  --query properties.configuration.ingress.fqdn \
  --output tsv)

# Test health
curl https://$FQDN/health

# Test invoice upload
curl -X POST https://$FQDN/api/v1/invoices \
  -F "file=@tests/fixtures/invoice_hindi.jpeg" \
  -F "tenant_id=test-tenant"
```

### View Logs

```bash
# API logs
az containerapp logs show \
  --name invoicify-api \
  --resource-group invoicify-rg \
  --follow

# Worker logs
az containerapp logs show \
  --name invoicify-worker \
  --resource-group invoicify-rg \
  --follow
```

### Monitor in Azure Portal

1. Go to: https://portal.azure.com
2. Navigate to: Resource Group → invoicify-rg
3. Click: Container Apps → invoicify-api
4. Select: Log stream

---

## COST BREAKDOWN

| Service | Tier | Free Period | After Free |
|---------|------|-------------|------------|
| Container Apps (API + Worker + Beat) | Consumption | Always | Always free |
| Container Registry | Standard | 12 months | ~$20/mo |
| PostgreSQL Flexible B1MS | Burstable | 12 months | ~$12/mo |
| Blob Storage 5GB | Hot LRS | 12 months | ~$0.10/mo |
| Service Bus Standard | Standard | 12 months | ~$10/mo |
| Document Intelligence F0 | 500 pages | 12 months | Pay-per-page |
| AI Search | Free | Always | Always |
| Key Vault | Standard | 12 months | ~$0 |
| Static Web Apps | Free | Always | Always |
| Event Grid | Basic | Always | Always |
| Log Analytics | 5GB free | Always | Per GB |

**Total Month 1-12:** $0/month  
**Total Month 13+:** ~$42/month

---

## TROUBLESHOOTING

### Container won't start

```bash
# Check logs
az containerapp logs show \
  --name invoicify-api \
  --resource-group invoicify-rg

# Check events
az containerapp show \
  --name invoicify-api \
  --resource-group invoicify-rg \
  --query properties.latestRevisionName \
  --output tsv
```

### Database connection fails

```bash
# Verify Key Vault secret
az keyvault secret show \
  --vault-name invoicify-kv \
  --name db-url

# Check PostgreSQL firewall
az postgres flexible-server firewall-rule list \
  --name invoicify-postgres \
  --resource-group invoicify-rg
```

### Celery worker not processing

```bash
# Check Service Bus queues
az servicebus queue show \
  --resource-group invoicify-rg \
  --namespace-name invoicify-sb \
  --name invoice-processing

# Check worker logs
az containerapp logs show \
  --name invoicify-worker \
  --resource-group invoicify-rg
```

---

## SECURITY

### Managed Identity

Container Apps use system-assigned managed identity to access:
- Key Vault (secrets)
- Blob Storage (PDFs)
- Service Bus (queues)

No credentials in code or environment variables.

### Key Vault Access

```bash
# Grant access to user
az keyvault set-policy \
  --name invoicify-kv \
  --resource-group invoicify-rg \
  --upn your.email@company.com \
  --secret-permissions get list set
```

### IP Restrictions

```bash
# Add IP restrictions to API
az containerapp ingress update \
  --name invoicify-api \
  --resource-group invoicify-rg \
  --ip-security-restrictions '[
    {
      "name": "Office",
      "ipAddressRange": "YOUR_IP/32",
      "action": "Allow"
    }
  ]'
```

---

## CI/CD PIPELINE

### Automatic Deployment

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]

# Jobs:
# 1. test - Run pytest
# 2. deploy-infra - Deploy Bicep (on infra/ changes)
# 3. deploy-backend - Build + push + deploy Container Apps
# 4. deploy-frontend - Deploy Static Web App (on web/ changes)
```

### Manual Trigger

```bash
# Go to: GitHub → Actions → Deploy Invoicify
# Click: Run workflow
# Select branch: main
# Click: Run workflow
```

---

## RESOURCE CLEANUP

```bash
# Delete entire resource group
az group delete \
  --name invoicify-rg \
  --yes \
  --no-wait

# Verify deletion
az group show --name invoicify-rg
```

---

## NEXT STEPS

1. **Configure Custom Domain**
   - Azure DNS Zone
   - SSL certificate (App Service Managed)

2. **Set up Monitoring**
   - Azure Monitor Alerts
   - Application Insights

3. **Enable Auto-Scaling**
   - Scale rules based on HTTP traffic
   - Scale rules based on Service Bus queue depth

4. **Configure Backups**
   - PostgreSQL geo-redundant backup
   - Blob Storage soft delete

---

**Deployed with ❤️ by Invoicify Team**  
**Last Updated:** February 28, 2026
