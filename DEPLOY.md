# 🚀 DEPLOY INVOICIFY TO AZURE

## QUICK DEPLOY (5 minutes)

```bash
# 1. Make script executable
chmod +x scripts/deploy-to-azure.sh

# 2. Run deployment script
./scripts/deploy-to-azure.sh
```

**That's it!** The script will:
- ✅ Create all Azure resources
- ✅ Build and push Docker image
- ✅ Deploy to Azure Container Apps
- ✅ Configure secrets in Key Vault
- ✅ Provide you with the application URL

---

## MANUAL DEPLOYMENT (Step-by-Step)

For detailed manual deployment instructions, see:
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Complete guide with all options

---

## PREREQUISITES

```bash
# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Install Docker
sudo apt-get install docker.io

# Login to Azure
az login
```

---

## DEPLOYMENT OPTIONS

| Option | Best For | Cost | Time |
|--------|----------|------|------|
| **Automated Script** | Quick deployment | $0-10/mo | 5 min |
| **Manual (Container Apps)** | Production | $5-20/mo | 20 min |
| **Azure Functions** | Serverless | $0-10/mo | 15 min |
| **App Service** | Traditional | $13-50/mo | 15 min |

---

## POST-DEPLOYMENT

### Test Health Endpoint

```bash
# Get URL from deployment output
FQDN="your-app.azurecontainerapps.io"

# Test health
curl https://$FQDN/health
```

### Test Invoice Upload

```bash
curl -X POST https://$FQDN/api/v1/invoices \
  -F "file=@tests/fixtures/invoice_hindi.jpeg" \
  -F "tenant_id=test-tenant"
```

### View Logs

```bash
az containerapp logs show \
  --name invoicify-agent-core \
  --resource-group invoicify-rg \
  --follow
```

---

## CI/CD SETUP

### 1. Create GitHub Secret

```bash
# Create service principal
az ad sp create-for-rbac \
  --name "invoicify-gh-actions" \
  --role contributor \
  --scopes /subscriptions/YOUR_SUBSCRIPTION_ID/resourceGroups/invoicify-rg \
  --sdk-auth

# Copy JSON output to GitHub → Settings → Secrets → Actions → AZURE_CREDENTIALS
```

### 2. Enable GitHub Actions

```bash
# The deployment workflow is already created
# Just push to main branch and it will auto-deploy
git push origin main
```

---

## COST OPTIMIZATION

### Free Tier Resources

| Resource | Free Tier | Your Usage | Status |
|----------|-----------|------------|--------|
| Container Apps | 180k vCPU-sec/mo | ~50k | ✅ Free |
| Container Registry | 10 GB storage | ~2 GB | ✅ Free |
| Key Vault | 25k transactions | ~1k | ✅ Free |
| Functions | 1M executions | ~10k | ✅ Free |

**Total: $0-10/month**

---

## TROUBLESHOOTING

### Container won't start

```bash
# Check logs
az containerapp logs show \
  --name invoicify-agent-core \
  --resource-group invoicify-rg
```

### Secrets not loading

```bash
# Verify Key Vault
az keyvault secret list \
  --vault-name invoicify-kv-xxxx
```

### High latency

```bash
# Scale up
az containerapp update \
  --name invoicify-agent-core \
  --min-replicas 1 \
  --max-replicas 10
```

---

## SECURITY

### Managed Identity

```bash
# Enable system-assigned identity
az containerapp identity assign \
  --name invoicify-agent-core \
  --resource-group invoicify-rg
```

### IP Restrictions

```bash
# Add IP restrictions
az containerapp ingress update \
  --name invoicify-agent-core \
  --ip-security-restrictions '[{"name":"Office","ipAddressRange":"YOUR_IP/32","action":"Allow"}]'
```

---

## RESOURCES

- **Full Guide:** [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **Azure Portal:** https://portal.azure.com
- **Container Apps Docs:** https://learn.microsoft.com/azure/container-apps
- **Support:** Open an issue on GitHub

---

**Deployed with ❤️ by Invoicify Team**
