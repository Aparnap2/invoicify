# Azure Functions API for Invoicify

Replaces Cloudflare Workers + Hono with Azure Functions (serverless).

## Structure

```
apps/api/
├── functions/
│   ├── invoice_ingest/
│   │   └── __init__.py    # POST /invoices - ingest invoice PDF
│   ├── invoice_get/
│   │   └── __init__.py    # GET /invoices/{id} - get invoice status
│   └── health/
│       └── __init__.py    # GET /health - health check
├── db/
│   └── sql.py             # Azure SQL client (replaces D1)
├── storage/
│   └── blob.py            # Azure Blob Storage client (replaces R2)
├── requirements.txt
└── function_app.py        # FastAPI on Azure Functions
```

## Local Development

```bash
# Start Azurite (Azure Storage emulator)
docker run -d -p 10000:10000 -p 10001:10001 -p 10002:10002 \
  mcr.microsoft.com/azure-storage/azurite

# Start SQL Server (Azure SQL emulator)
docker run -d -p 1433:1433 -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD=DevPass123! \
  mcr.microsoft.com/mssql/server:2022-latest

# Run functions locally
cd apps/api
func start --python
```

## Deployment

```bash
# Create resource group
az group create --name invoicify-rg --location eastus

# Create storage account
az storage account create --name invoicifystore --resource-group invoicify-rg \
  --location eastus --sku Standard_LRS

# Create function app
az functionapp create --resource-group invoicify-rg --consumption-plan-location eastus \
  --runtime python --functions-version 4 --name invoicify-api \
  --storage-account invoicifystore

# Deploy
func azure functionapp publish invoicify-api
```
