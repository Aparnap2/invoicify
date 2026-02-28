targetScope = 'resourceGroup'

@description('Environment name (prod, staging, dev)')
param environment string = 'prod'

@description('Azure region for deployment')
param location string = 'eastus'

@description('Application name prefix')
param appName string = 'invoicify'

@description('Your tenant ID - ADD TO GITHUB SECRETS')
param tenantId string = ''

@description('Your subscription ID - ADD TO GITHUB SECRETS')
param subscriptionId string = ''

@secure()
@description('PostgreSQL administrator password (stored in Key Vault)')
param postgresPassword string

@secure()
@description('OpenRouter API key for LLM (optional - uses free tier by default)')
param openRouterApiKey string = ''

@secure()
@description('Microsoft Graph client ID for email ingestion')
param graphClientId string = ''

@secure()
@description('Microsoft Graph client secret for email ingestion')
param graphClientSecret string = ''

@secure()
@description('QuickBooks client ID (optional)')
param quickbooksClientId string = ''

@secure()
@description('QuickBooks client secret (optional)')
param quickbooksClientSecret string = ''

@secure()
@description('Application secret key for sessions/tokens')
param secretKey string = 'dev-secret-key-change-in-prod'

// ─────────────────────────────────────────────────────────────────────
// CONTAINER REGISTRY (Free 12 months)
// ─────────────────────────────────────────────────────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: '${appName}registry'
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    adminUserEnabled: true
  }
}

// ─────────────────────────────────────────────────────────────────────
// BLOB STORAGE (Free 12 months - 5GB)
// ─────────────────────────────────────────────────────────────────────
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${appName}store'
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource invoicesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'invoices'
  properties: {
    publicAccess: 'None'
  }
}

resource celeryResultsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'celery-results'
  properties: {
    publicAccess: 'None'
  }
}

resource exportsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'exports'
  properties: {
    publicAccess: 'None'
  }
}

// ─────────────────────────────────────────────────────────────────────
// POSTGRESQL FLEXIBLE SERVER (Free 12 months - B1MS Burstable)
// ─────────────────────────────────────────────────────────────────────
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: '${appName}-postgres'
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: 'invoicify_admin'
    administratorLoginPassword: postgresPassword
    version: '16'
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
  }
}

resource postgresDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: postgres
  name: 'invoicify'
}

// Firewall rule for Azure Container Apps access
resource postgresFirewall 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-06-01-preview' = {
  parent: postgres
  name: 'allow-azure-services'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ─────────────────────────────────────────────────────────────────────
// SERVICE BUS - Celery Broker (Free 12 months - Standard tier)
// ─────────────────────────────────────────────────────────────────────
resource serviceBus 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: '${appName}-sb'
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
}

// Celery default queue
resource sbDefaultQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'celery'
  properties: {
    maxDeliveryCount: 5
    lockDuration: 'PT5M'
    defaultMessageTimeToLive: 'P1D'
    deadLetteringOnMessageExpiration: true
  }
}

// Invoice processing queue
resource sbInvoiceQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'invoice-processing'
  properties: {
    maxDeliveryCount: 5
    lockDuration: 'PT5M'
    defaultMessageTimeToLive: 'P1D'
    deadLetteringOnMessageExpiration: true
  }
}

// Validation queue
resource sbValidationQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'validation'
  properties: {
    maxDeliveryCount: 5
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
  }
}

// Export queue
resource sbExportQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'export'
  properties: {
    maxDeliveryCount: 3
    lockDuration: 'PT10M'
    deadLetteringOnMessageExpiration: true
  }
}

// Email processing queue
resource sbEmailQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'email-processing'
  properties: {
    maxDeliveryCount: 3
    lockDuration: 'PT2M'
    deadLetteringOnMessageExpiration: true
  }
}

// Dead letter queue
resource sbDlqQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'dlq-processing'
  properties: {
    maxDeliveryCount: 1
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
  }
}

// ─────────────────────────────────────────────────────────────────────
// EVENT GRID - PDF upload triggers (Free always - 100k ops/month)
// ─────────────────────────────────────────────────────────────────────
resource eventGridTopic 'Microsoft.EventGrid/topics@2022-06-15' = {
  name: '${appName}-events'
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    inputSchema: 'EventGridSchema'
  }
}

// Event subscription: Blob PDF upload → Service Bus invoice queue
resource blobEventSub 'Microsoft.EventGrid/eventSubscriptions@2022-06-15' = {
  name: 'pdf-uploaded-to-worker'
  scope: storage
  properties: {
    destination: {
      endpointType: 'ServiceBusQueue'
      properties: {
        resourceId: sbInvoiceQueue.id
      }
    }
    filter: {
      includedEventTypes: [
        'Microsoft.Storage.BlobCreated'
      ]
      subjectBeginsWith: '/blobServices/default/containers/invoices'
      subjectEndsWith: '.pdf'
    }
    eventDeliverySchema: 'EventGridSchema'
    retryPolicy: {
      maxDeliveryAttempts: 5
      eventTimeToLiveInMinutes: 1440
    }
  }
}

// ─────────────────────────────────────────────────────────────────────
// DOCUMENT INTELLIGENCE - OCR (Free 12 months - 500 pages/month)
// ─────────────────────────────────────────────────────────────────────
resource docIntelligence 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: '${appName}-docai'
  location: location
  kind: 'FormRecognizer'
  sku: {
    name: 'F0'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
    customSubDomainName: '${appName}-docai'
  }
}

// ─────────────────────────────────────────────────────────────────────
// AI SEARCH - Vendor RAG (Free always - 3 indexes, 50MB)
// ─────────────────────────────────────────────────────────────────────
resource aiSearch 'Microsoft.Search/searchServices@2024-03-01-preview' = {
  name: '${appName}-search'
  location: location
  sku: {
    name: 'free'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
  }
}

// ─────────────────────────────────────────────────────────────────────
// KEY VAULT - Secrets management (Free 12 months - 10k transactions)
// ─────────────────────────────────────────────────────────────────────
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${appName}-kv'
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// ─────────────────────────────────────────────────────────────────────
// LOG ANALYTICS - Monitoring (Free - 5GB/month)
// ─────────────────────────────────────────────────────────────────────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${appName}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ─────────────────────────────────────────────────────────────────────
// CONTAINER APPS ENVIRONMENT
// ─────────────────────────────────────────────────────────────────────
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${appName}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ─────────────────────────────────────────────────────────────────────
// CONTAINER APP: API (FastAPI)
// ─────────────────────────────────────────────────────────────────────
resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${appName}-api'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        corsPolicy: {
          allowedOrigins: [
            'https://${staticWebApp.properties.defaultHostname}'
          ]
          allowedMethods: [
            'GET'
            'POST'
            'PUT'
            'DELETE'
            'OPTIONS'
          ]
          allowedHeaders: [
            '*'
          ]
          allowCredentials: true
        }
      }
      secrets: [
        {
          name: 'registry-password'
          value: acr.listCredentials().passwords[0].value
        }
      ]
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'registry-password'
        }
      ]
    }
    template: {
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
      containers: [
        {
          name: 'api'
          image: '${acr.properties.loginServer}/invoicify-api:latest'
          resources: {
            cpu: json('0.5')
            memory: '1.0Gi'
          }
          env: [
            {
              name: 'ENVIRONMENT'
              value: environment
            }
            {
              name: 'KEY_VAULT_URL'
              value: keyVault.properties.vaultUri
            }
            {
              name: 'STORAGE_TYPE'
              value: 'azure'
            }
            {
              name: 'AZURE_STORAGE_ACCOUNT'
              value: storage.name
            }
            {
              name: 'AZURE_STORAGE_ENDPOINT'
              value: storage.properties.primaryEndpoints.blob
            }
            {
              name: 'AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT'
              value: docIntelligence.properties.endpoint
            }
            {
              name: 'AZURE_SEARCH_ENDPOINT'
              value: 'https://${aiSearch.name}.search.windows.net'
            }
            {
              name: 'EVENT_GRID_TOPIC_ENDPOINT'
              value: eventGridTopic.properties.endpoint
            }
            {
              name: 'LLM_PROVIDER'
              value: 'openrouter'
            }
            {
              name: 'LLM_MODEL'
              value: 'z-ai/glm-4.5-air:free'
            }
            {
              name: 'GRAPH_TENANT_ID'
              value: tenantId
            }
            {
              name: 'UI_HOST'
              value: 'https://${staticWebApp.properties.defaultHostname}'
            }
            {
              name: 'SENTRY_ENVIRONMENT'
              value: environment
            }
          ]
          secretEnv: [
            {
              name: 'DATABASE_URL'
              secretRef: 'db-url'
            }
            {
              name: 'AZURE_SB_CONNECTION_STRING'
              secretRef: 'sb-conn'
            }
            {
              name: 'OPENROUTER_API_KEY'
              secretRef: 'openrouter-api-key'
            }
            {
              name: 'SECRET_KEY'
              secretRef: 'secret-key'
            }
            {
              name: 'GRAPH_CLIENT_ID'
              secretRef: 'graph-client-id'
            }
            {
              name: 'GRAPH_CLIENT_SECRET'
              secretRef: 'graph-client-secret'
            }
            {
              name: 'QUICKBOOKS_CLIENT_ID'
              secretRef: 'quickbooks-client-id'
            }
            {
              name: 'QUICKBOOKS_CLIENT_SECRET'
              secretRef: 'quickbooks-client-secret'
            }
            {
              name: 'SENTRY_DSN'
              secretRef: 'sentry-dsn'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 15
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
            }
          ]
        }
      ]
    }
  }
}

// ─────────────────────────────────────────────────────────────────────
// CONTAINER APP: CELERY WORKER
// ─────────────────────────────────────────────────────────────────────
resource workerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${appName}-worker'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      secrets: [
        {
          name: 'registry-password'
          value: acr.listCredentials().passwords[0].value
        }
      ]
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'registry-password'
        }
      ]
    }
    template: {
      scale: {
        minReplicas: 1
        maxReplicas: 5
        rules: [
          {
            name: 'servicebus-queue-depth'
            custom: {
              type: 'azure-servicebus'
              metadata: {
                queueName: 'invoice-processing'
                messageCount: '10'
                namespace: serviceBus.name
              }
              auth: [
                {
                  secretRef: 'sb-conn'
                  triggerParameter: 'connection'
                }
              ]
            }
          }
        ]
      }
      containers: [
        {
          name: 'worker'
          image: '${acr.properties.loginServer}/invoicify-api:latest'
          command: [
            'uv'
            'run'
            'celery'
            '-A'
            'app.workers.celery_app'
            'worker'
            '--loglevel=info'
            '-Q'
            'invoice_processing,validation,export,email_processing,dlq_processing,celery'
          ]
          resources: {
            cpu: json('0.5')
            memory: '1.0Gi'
          }
          env: [
            {
              name: 'ENVIRONMENT'
              value: environment
            }
            {
              name: 'STORAGE_TYPE'
              value: 'azure'
            }
            {
              name: 'AZURE_STORAGE_ACCOUNT'
              value: storage.name
            }
            {
              name: 'AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT'
              value: docIntelligence.properties.endpoint
            }
            {
              name: 'LLM_PROVIDER'
              value: 'openrouter'
            }
            {
              name: 'LLM_MODEL'
              value: 'z-ai/glm-4.5-air:free'
            }
          ]
          secretEnv: [
            {
              name: 'DATABASE_URL'
              secretRef: 'db-url'
            }
            {
              name: 'AZURE_SB_CONNECTION_STRING'
              secretRef: 'sb-conn'
            }
            {
              name: 'OPENROUTER_API_KEY'
              secretRef: 'openrouter-api-key'
            }
            {
              name: 'SECRET_KEY'
              secretRef: 'secret-key'
            }
          ]
        }
      ]
    }
  }
}

// ─────────────────────────────────────────────────────────────────────
// CONTAINER APP: CELERY BEAT (Scheduler)
// ─────────────────────────────────────────────────────────────────────
resource beatApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${appName}-beat'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      secrets: [
        {
          name: 'registry-password'
          value: acr.listCredentials().passwords[0].value
        }
      ]
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'registry-password'
        }
      ]
    }
    template: {
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
      containers: [
        {
          name: 'beat'
          image: '${acr.properties.loginServer}/invoicify-api:latest'
          command: [
            'uv'
            'run'
            'celery'
            '-A'
            'app.workers.celery_app'
            'beat'
            '--loglevel=info'
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'ENVIRONMENT'
              value: environment
            }
          ]
          secretEnv: [
            {
              name: 'DATABASE_URL'
              secretRef: 'db-url'
            }
            {
              name: 'AZURE_SB_CONNECTION_STRING'
              secretRef: 'sb-conn'
            }
            {
              name: 'SECRET_KEY'
              secretRef: 'secret-key'
            }
          ]
        }
      ]
    }
  }
}

// ─────────────────────────────────────────────────────────────────────
// STATIC WEB APP (Frontend)
// ─────────────────────────────────────────────────────────────────────
resource staticWebApp 'Microsoft.Web/staticSites@2023-01-01' = {
  name: '${appName}-web'
  location: 'eastus2'
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    repositoryUrl: 'https://github.com/Aparnap2/invoicify'
    branch: 'main'
    buildProperties: {
      appLocation: '/web'
      outputLocation: '.next'
      appBuildCommand: 'npm run build'
    }
  }
}

// ─────────────────────────────────────────────────────────────────────
// RBAC: Managed Identity → Key Vault
// ─────────────────────────────────────────────────────────────────────
resource kvApiRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, apiApp.id, 'kv-secrets-user')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: apiApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource kvWorkerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, workerApp.id, 'kv-secrets-user')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: workerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ─────────────────────────────────────────────────────────────────────
// RBAC: Managed Identity → Blob Storage
// ─────────────────────────────────────────────────────────────────────
resource storageApiRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, apiApp.id, 'blob-contributor')
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: apiApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource storageWorkerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, workerApp.id, 'blob-contributor')
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: workerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ─────────────────────────────────────────────────────────────────────
// OUTPUTS
// ─────────────────────────────────────────────────────────────────────
output acrLoginServer string = acr.properties.loginServer
output apiUrl string = 'https://${apiApp.properties.configuration.ingress.fqdn}'
output webUrl string = 'https://${staticWebApp.properties.defaultHostname}'
output keyVaultUri string = keyVault.properties.vaultUri
output keyVaultName string = keyVault.name
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output serviceBusNamespace string = serviceBus.name
output storageEndpoint string = storage.properties.primaryEndpoints.blob
output docIntelligenceEndpoint string = docIntelligence.properties.endpoint
output searchEndpoint string = 'https://${aiSearch.name}.search.windows.net'
output eventGridEndpoint string = eventGridTopic.properties.endpoint
output logAnalyticsWorkspaceId string = logAnalytics.properties.customerId
