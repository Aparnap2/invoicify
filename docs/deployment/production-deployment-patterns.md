# Production Deployment Patterns

## Overview

This document showcases the **senior-level production deployment patterns** implemented in the AP Intake & Validation system. These patterns demonstrate enterprise-grade deployment strategies that ensure high availability, scalability, security, and operational excellence.

---

## 1. Container Orchestration with Kubernetes

### ❌ Junior Anti-Pattern: Basic Deployment

```yaml
# Junior approach - Basic deployment without optimization
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1  # Single point of failure
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: my-api:latest  # No version pinning
        ports:
        - containerPort: 8000
        # No resource limits
        # No health checks
        # No environment configuration
```

**Problems:**
- Single replica (no HA)
- No resource limits
- No health checks
- No environment-specific configs
- No secrets management
- No volume management

### ✅ Senior Pattern: Enterprise-Grade Kubernetes Deployment

```yaml
# Senior approach - Production-ready deployment with comprehensive optimization
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-deployment
  namespace: ap-intake
  labels:
    app: api
    component: backend
    version: v2.0.0
    managed-by: terraform
  annotations:
    kubernetes.io/description: "AP Intake API Service"
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/metrics"
spec:
  replicas: 3  # High availability
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0  # Zero downtime deployment
  selector:
    matchLabels:
      app: api
      component: backend
  template:
    metadata:
      labels:
        app: api
        component: backend
        version: v2.0.0
      annotations:
        kubernetes.io/description: "AP Intake API Container"
        rollme: {{ randAlphaNum 5 | quote }}  # Force updates on config change
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: api
        image: ap-intake/api:2.0.0  # Version pinned
        imagePullPolicy: IfNotPresent
        ports:
        - name: http
          containerPort: 8000
          protocol: TCP
        env:
        # Database configuration from secrets
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: ap-intake-secrets
              key: DATABASE_URL
              optional: false
        # Redis configuration
        - name: REDIS_URL
          value: "redis://redis-service:6379/0"
        # Security configuration
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: ap-intake-secrets
              key: SECRET_KEY
        - name: ENVIRONMENT
          value: "production"
        # LLM configuration
        - name: OPENROUTER_API_KEY
          valueFrom:
            secretKeyRef:
              name: ap-intake-secrets
              key: OPENROUTER_API_KEY
        # Environment-specific config from ConfigMap
        envFrom:
        - configMapRef:
            name: ap-intake-config
        # Volume mounts for persistent storage
        volumeMounts:
        - name: storage-volume
          mountPath: /app/storage
          readOnly: false
        - name: exports-volume
          mountPath: /app/exports
          readOnly: false
        - name: temp-volume
          mountPath: /tmp
          readOnly: false
        - name: logs-volume
          mountPath: /app/logs
          readOnly: false
        # Resource management with limits and requests
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
            ephemeral-storage: "1Gi"
          limits:
            memory: "1Gi"
            cpu: "1000m"
            ephemeral-storage: "2Gi"
        # Comprehensive health checks
        livenessProbe:
          httpGet:
            path: /health/live
            port: http
            scheme: HTTP
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          successThreshold: 1
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health/ready
            port: http
            scheme: HTTP
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 3
          successThreshold: 1
          failureThreshold: 3
        startupProbe:
          httpGet:
            path: /health/startup
            port: http
            scheme: HTTP
          initialDelaySeconds: 10
          periodSeconds: 10
          timeoutSeconds: 5
          successThreshold: 1
          failureThreshold: 6  # Allow 1 minute for startup
        # Security context for container
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop:
            - ALL
        # Volume configuration
      volumes:
      - name: storage-volume
        persistentVolumeClaim:
          claimName: storage-pvc
      - name: exports-volume
        persistentVolumeClaim:
          claimName: exports-pvc
      - name: temp-volume
        emptyDir:
          sizeLimit: 1Gi
      - name: logs-volume
        emptyDir:
          sizeLimit: 500Mi
      # Security and image configuration
      imagePullSecrets:
      - name: registry-secret
      # Node scheduling and affinity
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - api
              topologyKey: kubernetes.io/hostname
      # Tolerations for critical workloads
      tolerations:
      - key: "critical-workload"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
      # Node selector for resource optimization
      nodeSelector:
        node-type: application
      # Pod priority
      priorityClassName: high-priority
---
# Service with comprehensive configuration
apiVersion: v1
kind: Service
metadata:
  name: api-service
  namespace: ap-intake
  labels:
    app: api
    component: backend
  annotations:
    kubernetes.io/description: "AP Intake API Service"
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/metrics"
    cloud.google.com/load-balancer-type: "external"
spec:
  type: ClusterIP  # Internal service, exposed via ingress
  sessionAffinity: None
  ports:
  - name: http
    port: 8000
    targetPort: http
    protocol: TCP
  selector:
    app: api
    component: backend
---
# Service Monitor for Prometheus
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: api-monitor
  namespace: ap-intake
  labels:
    app: api
    component: backend
spec:
  selector:
    matchLabels:
      app: api
  endpoints:
  - port: http
    path: /metrics
    interval: 30s
    scrapeTimeout: 10s
```

**Senior Pattern Benefits:**
- High availability with multiple replicas
- Zero-donutime deployments with rolling updates
- Comprehensive resource management
- Advanced health checks (liveness, readiness, startup)
- Security best practices (non-root, read-only filesystem)
- Persistent volume management
- Pod anti-affinity for distribution
- Integration with monitoring systems

---

## 2. Autoscaling with Advanced Metrics

### ❌ Junior Anti-Pattern: Basic HPA

```yaml
# Junior approach - Basic HPA with only CPU metrics
apiVersion: autoscaling/v1
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 2
  maxReplicas: 5
  targetCPUUtilizationPercentage: 80
```

**Problems:**
- Only CPU-based scaling
- No custom metrics
- No scaling policies
- No stabilization windows
- Basic configuration

### ✅ Senior Pattern: Advanced Autoscaling with Multiple Metrics

```yaml
# Senior approach - Sophisticated autoscaling with custom metrics and policies
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
  namespace: ap-intake
  labels:
    app: api
    component: backend
  annotations:
    kubernetes.io/description: "Advanced HPA for API with custom metrics"
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-deployment
  minReplicas: 3
  maxReplicas: 20
  metrics:
  # CPU utilization with conservative target
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  # Memory utilization with higher threshold
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  # Custom metric for active processing jobs
  - type: External
    external:
      metric:
        name: active_processing_jobs
        selector:
          matchLabels:
            app: api
      target:
        type: AverageValue
        averageValue: "10"
  # Custom metric for request queue length
  - type: External
    external:
      metric:
        name: http_requests_queue_length
      target:
        type: AverageValue
        averageValue: "5"
  # Custom metric for database connections
  - type: External
    external:
      metric:
        name: database_connections_active
      target:
        type: AverageValue
        averageValue: "15"
  # Advanced scaling behavior
  behavior:
    # Scale down behavior (conservative)
    scaleDown:
      stabilizationWindowSeconds: 300  # 5 minutes
      policies:
      - type: Percent
        value: 10  # Scale down by 10% max
        periodSeconds: 60
      - type: Pods
        value: 2  # Remove max 2 pods at once
        periodSeconds: 60
      selectPolicy: Min  # Choose most conservative policy
    # Scale up behavior (aggressive for responsiveness)
    scaleUp:
      stabilizationWindowSeconds: 60  # 1 minute
      policies:
      - type: Percent
        value: 50  # Scale up by 50% initially
        periodSeconds: 60
      - type: Pods
        value: 4  # Add max 4 pods at once
        periodSeconds: 60
      - type: Percent
        value: 100  # Double during high load
        periodSeconds: 15
      selectPolicy: Max  # Choose most aggressive policy
---
# Worker-specific HPA with different characteristics
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: worker-hpa
  namespace: ap-intake
  labels:
    app: worker
    component: backend
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: worker-deployment
  minReplicas: 4
  maxReplicas: 50  # Higher limit for workers
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 80  # Higher CPU utilization for batch workers
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 85
  # Queue depth metric for workers
  - type: External
    external:
      metric:
        name: celery_queue_depth
      target:
        type: AverageValue
        averageValue: "5"
  # Processing rate metric
  - type: External
    external:
      metric:
        name: processing_jobs_per_minute
      target:
        type: AverageValue
        averageValue: "2"
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 600  # 10 minutes for workers (conservative)
      policies:
      - type: Percent
        value: 20
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 30  # Fast scale up for workers
      policies:
      - type: Percent
        value: 100  # Double workers quickly
        periodSeconds: 60
      - type: Pods
        value: 8  # Add up to 8 workers
        periodSeconds: 60
      selectPolicy: Max
---
# Vertical Pod Autoscaler for resource optimization
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: api-vpa
  namespace: ap-intake
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-deployment
  updatePolicy:
    updateMode: "Auto"  # Automatically update resource requests
  resourcePolicy:
    containerPolicies:
    - containerName: api
      maxAllowed:
        cpu: 2
        memory: 4Gi
      minAllowed:
        cpu: 200m
        memory: 256Mi
      controlledResources: ["cpu", "memory"]
```

**Senior Pattern Benefits:**
- Multi-metric autoscaling (CPU, memory, custom metrics)
- Advanced scaling policies with different behaviors
- Custom metrics for business-specific scaling
- Stabilization windows to prevent thrashing
- Vertical autoscaling for resource optimization
- Different scaling strategies for different workloads

---

## 3. Infrastructure as Code with Terraform

### ❌ Junior Anti-Pattern: Manual Infrastructure

```bash
# Junior approach - Manual infrastructure setup
# Create Kubernetes cluster manually through cloud console
# Apply manifests with kubectl apply -f
# No version control for infrastructure
# No automated provisioning
```

**Problems:**
- Manual processes prone to errors
- No version control for infrastructure
- No reproducible environments
- No state management
- No automated testing

### ✅ Senior Pattern: Comprehensive Terraform Infrastructure

```hcl
# Senior approach - Production-ready Terraform infrastructure

# Main terraform configuration
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = "~> 2.0"
    }
  }

  backend "s3" {
    bucket = "ap-intake-terraform-state"
    key    = "production/terraform.tfstate"
    region = "us-east-1"
    encrypt = true
    dynamodb_table = "terraform-locks"
  }
}

# Provider configuration with proper authentication
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "AP Intake"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Owner       = "Platform Engineering"
    }
  }
}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
  }
}

# EKS Cluster configuration
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.15"

  cluster_name    = "${var.project_name}-${var.environment}"
  cluster_version = "1.28"

  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnets

  cluster_endpoint_public_access = false

  # Managed node groups
  eks_managed_node_groups = {
    application_nodes = {
      desired_size = 3
      max_size     = 10
      min_size     = 3

      instance_types = ["m5.large", "m5a.large"]

      k8s_labels = {
        node-type = "application"
      }

      taints = {
        dedicated = {
          key    = "dedicated"
          value  = "application"
          effect = "NO_SCHEDULE"
        }
      }

      additional_tags = {
        Type = "Application Nodes"
      }
    }

    worker_nodes = {
      desired_size = 4
      max_size     = 20
      min_size     = 2

      instance_types = ["c5.large", "c5a.large"]

      k8s_labels = {
        node-type = "worker"
      }

      additional_tags = {
        Type = "Worker Nodes"
      }
    }

    monitoring_nodes = {
      desired_size = 2
      max_size     = 4
      min_size     = 2

      instance_types = ["m5.medium"]

      k8s_labels = {
        node-type = "monitoring"
      }

      taints = {
        monitoring = {
          key    = "monitoring"
          value  = "true"
          effect = "NO_SCHEDULE"
        }
      }

      additional_tags = {
        Type = "Monitoring Nodes"
      }
    }
  }

  # Cluster addons
  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent = true
    }
  }
}

# VPC Configuration with proper networking
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.project_name}-${var.environment}-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = false
  one_nat_gateway_per_az = true

  enable_dns_hostnames = true
  enable_dns_support   = true

  public_subnet_tags = {
    Type = "Public Subnets"
  }

  private_subnet_tags = {
    Type = "Private Subnets"
  }
}

# RDS Database configuration
module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.0"

  identifier = "${var.project_name}-${var.environment}-db"

  engine               = "postgres"
  engine_version       = "15.4"
  family               = "postgres15"
  major_engine_version = "15"
  instance_class       = "db.m5.large"

  allocated_storage     = 100
  max_allocated_storage = 1000
  storage_encrypted     = true
  storage_type          = "gp3"
  iops                  = 3000

  db_name  = "ap_intake"
  username = "postgres"
  port     = 5432

  iam_database_authentication_enabled = true

  vpc_security_group_ids = [module.security_group.database_security_group_id]
  db_subnet_group_name   = module.vpc.database_subnet_group_name

  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"

  deletion_protection = true

  skip_final_snapshot = false
  final_snapshot_identifier = "${var.project_name}-${var.environment}-final-snapshot"

  # Enhanced monitoring
  enhanced_monitoring_interval = 60
  monitoring_interval         = 60
  monitoring_role_arn         = aws_iam_role.rds_enhanced_monitoring.arn

  # Performance insights
  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Redis (ElastiCache) configuration
module "elasticache" {
  source  = "terraform-aws-modules/elasticache/aws"
  version = "~> 1.0"

  cluster_id = "${var.project_name}-${var.environment}-redis"

  engine                    = "redis"
  node_type                 = "cache.m5.large"
  num_cache_nodes           = 3
  parameter_group_name      = "default.redis7"
  port                      = 6379
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = var.redis_auth_token

  subnet_group_name  = module.vpc.elasticache_subnet_group_name
  security_group_ids = [module.security_group.redis_security_group_id]

  log_delivery_configuration = {
    cloudwatch_logs = {
      enabled = true
    }
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# Helm releases for monitoring stack
resource "helm_release" "prometheus" {
  name       = "prometheus"
  namespace  = "monitoring"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  version    = "55.0.0"

  create_namespace = true

  values = [
    file("${path.module}/helm-values/prometheus.yaml")
  ]

  depends_on = [module.eks]
}

resource "helm_release" "ingress" {
  name       = "nginx-ingress"
  namespace  = "ingress"
  repository = "https://kubernetes.github.io/ingress-nginx"
  chart      = "ingress-nginx"
  version    = "4.8.0"

  create_namespace = true

  values = [
    file("${path.module}/helm-values/ingress.yaml")
  ]

  depends_on = [module.eks]
}

# Kubernetes resources provisioned via Terraform
resource "kubernetes_namespace" "ap_intake" {
  metadata {
    name = "ap-intake"
    labels = {
      name        = "ap-intake"
      environment = var.environment
      project     = var.project_name
    }
  }
}

resource "kubernetes_secret" "ap_intake_secrets" {
  metadata {
    name      = "ap-intake-secrets"
    namespace = "ap-intake"
  }

  data = {
    DATABASE_URL         = var.database_url
    SECRET_KEY           = var.app_secret_key
    OPENROUTER_API_KEY   = var.openrouter_api_key
    REDIS_AUTH_TOKEN     = var.redis_auth_token
  }

  type = "Opaque"
}

resource "kubernetes_config_map" "ap_intake_config" {
  metadata {
    name      = "ap-intake-config"
    namespace = "ap-intake"
  }

  data = {
    ENVIRONMENT                        = var.environment
    LOG_LEVEL                          = "INFO"
    METRICS_ENABLED                    = "true"
    TRACING_ENABLED                    = "true"
    DOCLING_CONFIDENCE_THRESHOLD       = "0.8"
    MAX_LLM_COST_PER_INVOICE           = "0.10"
    VALIDATION_STRICT_MODE             = "false"
    ENABLE_REAL_TIME_UPDATES           = "true"
  }
}

# Storage configuration
resource "kubernetes_persistent_volume_claim" "storage_pvc" {
  metadata {
    name      = "storage-pvc"
    namespace = "ap-intake"
  }

  spec {
    access_modes = ["ReadWriteMany"]
    storage_class = "efs-storage"
    resources {
      requests = {
        storage = "100Gi"
      }
    }
  }
}

resource "kubernetes_persistent_volume_claim" "exports_pvc" {
  metadata {
    name      = "exports-pvc"
    namespace = "ap-intake"
  }

  spec {
    access_modes = ["ReadWriteMany"]
    storage_class = "efs-storage"
    resources {
      requests = {
        storage = "50Gi"
      }
    }
  }
}

# Output values for other systems to consume
output "cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "database_endpoint" {
  description = "RDS database endpoint"
  value       = module.rds.db_instance_endpoint
}

output "redis_endpoint" {
  description = "Redis endpoint"
  value       = module.elasticache.redis_primary_endpoint_address
}
```

**Senior Pattern Benefits:**
- Complete infrastructure as code
- Version-controlled infrastructure
- Automated provisioning and updates
- State management with remote backend
- Modular, reusable components
- Proper networking and security
- Comprehensive monitoring stack
- Secrets management integration

---

## 4. Monitoring and Observability

### ❌ Junior Anti-Pattern: Basic Monitoring

```yaml
# Junior approach - Minimal monitoring setup
apiVersion: v1
kind: Service
metadata:
  name: monitoring
spec:
  selector:
    app: api
  ports:
  - port: 9090
```

**Problems:**
- No comprehensive monitoring
- No alerting
- No dashboards
- No log aggregation
- No distributed tracing

### ✅ Senior Pattern: Enterprise Observability Stack

```yaml
# Senior approach - Comprehensive monitoring with Prometheus, Grafana, and Loki

# Prometheus configuration with custom scrape configs
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: monitoring
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
      evaluation_interval: 15s
      external_labels:
        cluster: ap-intake-production
        region: us-east-1

    rule_files:
    - "/etc/prometheus/rules/*.yml"

    alerting:
      alertmanagers:
      - static_configs:
        - targets:
          - alertmanager:9093

    scrape_configs:
    # Kubernetes API server
    - job_name: 'kubernetes-apiservers'
      kubernetes_sd_configs:
      - role: endpoints
      scheme: https
      tls_config:
        ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
      bearer_token_file: /var/run/secrets/kubernetes.io/serviceaccount/token
      relabel_configs:
      - source_labels: [__meta_kubernetes_namespace, __meta_kubernetes_service_name, __meta_kubernetes_endpoint_port_name]
        action: keep
        regex: default;kubernetes;https

    # Application metrics
    - job_name: 'ap-intake-api'
      kubernetes_sd_configs:
      - role: endpoints
        namespaces:
          names:
          - ap-intake
      relabel_configs:
      - source_labels: [__meta_kubernetes_service_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_service_annotation_prometheus_io_path]
        action: replace
        target_label: __metrics_path__
        regex: (.+)
      - source_labels: [__address__, __meta_kubernetes_service_annotation_prometheus_io_port]
        action: replace
        regex: ([^:]+)(?::\d+)?;(\d+)
        replacement: $1:$2
        target_label: __address__
      - action: labelmap
        regex: __meta_kubernetes_service_label_(.+)
      - source_labels: [__meta_kubernetes_namespace]
        action: replace
        target_label: kubernetes_namespace
      - source_labels: [__meta_kubernetes_service_name]
        action: replace
        target_label: kubernetes_name

    # Node metrics
    - job_name: 'kubernetes-nodes'
      kubernetes_sd_configs:
      - role: node
      relabel_configs:
      - action: labelmap
        regex: __meta_kubernetes_node_label_(.+)

    # Worker metrics
    - job_name: 'ap-intake-workers'
      kubernetes_sd_configs:
      - role: endpoints
        namespaces:
          names:
          - ap-intake
      relabel_configs:
      - source_labels: [__meta_kubernetes_service_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_endpoint_address_target_name]
        action: replace
        target_label: instance

  # Custom alerting rules
  alerting_rules.yml: |
    groups:
    - name: ap-intake-alerts
      rules:
      # API availability alerts
      - alert: APIntakeAPIDown
        expr: up{job="ap-intake-api"} == 0
        for: 2m
        labels:
          severity: critical
          service: api
        annotations:
          summary: "AP Intake API is down"
          description: "AP Intake API has been down for more than 2 minutes."

      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
          service: api
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors per second."

      # Performance alerts
      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 2
        for: 5m
        labels:
          severity: warning
          service: api
        annotations:
          summary: "High latency detected"
          description: "95th percentile latency is {{ $value }} seconds."

      # Processing queue alerts
      - alert: ProcessingQueueBacklog
        expr: celery_queue_length > 100
        for: 10m
        labels:
          severity: warning
          service: workers
        annotations:
          summary: "Processing queue backlog detected"
          description: "Queue has {{ $value }} items pending."

      # Database alerts
      - alert: DatabaseConnectionsHigh
        expr: pg_stat_database_numbackends / pg_settings_max_connections * 100 > 80
        for: 5m
        labels:
          severity: warning
          service: database
        annotations:
          summary: "High database connection usage"
          description: "Database connection usage is {{ $value }}%."

      # SLO alerts
      - alert: SLOTimeToReadyBreached
        expr: slo_time_to_ready_achieved_percentage < 95
        for: 15m
        labels:
          severity: critical
          service: slo
        annotations:
          summary: "Time-to-ready SLO breached"
          description: "Time-to-ready SLO achieved percentage is {{ $value }}%."

---
# Grafana dashboard configuration
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboards
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  ap-intake-overview.json: |
    {
      "dashboard": {
        "id": null,
        "title": "AP Intake - Overview",
        "tags": ["ap-intake"],
        "timezone": "browser",
        "panels": [
          {
            "id": 1,
            "title": "Request Rate",
            "type": "graph",
            "targets": [
              {
                "expr": "rate(http_requests_total[5m])",
                "legendFormat": "{{method}} {{status}}"
              }
            ],
            "yAxes": [
              {
                "label": "Requests/sec"
              }
            ]
          },
          {
            "id": 2,
            "title": "Response Time",
            "type": "graph",
            "targets": [
              {
                "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
                "legendFormat": "95th percentile"
              },
              {
                "expr": "histogram_quantile(0.50, rate(http_request_duration_seconds_bucket[5m]))",
                "legendFormat": "50th percentile"
              }
            ],
            "yAxes": [
              {
                "label": "Seconds"
              }
            ]
          },
          {
            "id": 3,
            "title": "Error Rate",
            "type": "graph",
            "targets": [
              {
                "expr": "rate(http_requests_total{status=~\"5..\"}[5m]) / rate(http_requests_total[5m]) * 100",
                "legendFormat": "5xx Error Rate"
              },
              {
                "expr": "rate(http_requests_total{status=~\"4..\"}[5m]) / rate(http_requests_total[5m]) * 100",
                "legendFormat": "4xx Error Rate"
              }
            ],
            "yAxes": [
              {
                "label": "Percentage",
                "max": 100
              }
            ]
          },
          {
            "id": 4,
            "title": "Active Processing Jobs",
            "type": "stat",
            "targets": [
              {
                "expr": "active_processing_jobs",
                "legendFormat": "Active Jobs"
              }
            ]
          },
          {
            "id": 5,
            "title": "SLO Achievement",
            "type": "stat",
            "targets": [
              {
                "expr": "slo_time_to_ready_achieved_percentage",
                "legendFormat": "Time to Ready"
              }
            ]
          }
        ],
        "time": {
          "from": "now-1h",
          "to": "now"
        },
        "refresh": "5s"
      }
    }

---
# AlertManager configuration with routing
apiVersion: v1
kind: ConfigMap
metadata:
  name: alertmanager-config
  namespace: monitoring
data:
  alertmanager.yml: |
    global:
      smtp_smarthost: 'smtp.company.com:587'
      smtp_from: 'alerts@company.com'

    route:
      group_by: ['alertname', 'cluster', 'service']
      group_wait: 10s
      group_interval: 10s
      repeat_interval: 1h
      receiver: 'default'
      routes:
      - match:
          severity: critical
        receiver: 'critical-alerts'
      - match:
          severity: warning
        receiver: 'warning-alerts'
      - match:
          service: slo
        receiver: 'slo-alerts'

    receivers:
    - name: 'default'
      email_configs:
      - to: 'devops@company.com'
        subject: '[AP Intake] {{ .GroupLabels.alertname }}'
        body: |
          {{ range .Alerts }}
          Alert: {{ .Annotations.summary }}
          Description: {{ .Annotations.description }}
          {{ end }}

    - name: 'critical-alerts'
      email_configs:
      - to: 'oncall@company.com'
        subject: '[CRITICAL] AP Intake - {{ .GroupLabels.alertname }}'
        body: |
          CRITICAL ALERT - Immediate attention required
          {{ range .Alerts }}
          Alert: {{ .Annotations.summary }}
          Description: {{ .Annotations.description }}
          {{ end }}
      slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK'
        channel: '#alerts-critical'
        title: 'Critical Alert: {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

    - name: 'warning-alerts'
      email_configs:
      - to: 'dev-team@company.com'
        subject: '[WARNING] AP Intake - {{ .GroupLabels.alertname }}'
        body: |
          Warning alert - Review when convenient
          {{ range .Alerts }}
          Alert: {{ .Annotations.summary }}
          Description: {{ .Annotations.description }}
          {{ end }}

    - name: 'slo-alerts'
      email_configs:
      - to: 'product-team@company.com'
        subject: '[SLO] AP Intake - {{ .GroupLabels.alertname }}'
        body: |
          SLO breach detected
          {{ range .Alerts }}
          Alert: {{ .Annotations.summary }}
          Description: {{ .Annotations.description }}
          {{ end }}
```

**Senior Pattern Benefits:**
- Comprehensive metrics collection
- Custom alerting rules
- SLO monitoring and alerting
- Visual dashboards
- Multi-channel notifications
- Proper alert routing and escalation

---

## 5. CI/CD Pipeline with GitOps

### ❌ Junior Anti-Pattern: Manual Deployment

```bash
# Junior approach - Manual deployment process
git pull origin main
docker build -t my-api .
kubectl apply -f deployment.yaml
```

**Problems:**
- Manual deployment process
- No automated testing
- No deployment gates
- No rollback capability
- No environment promotion

### ✅ Senior Pattern: Automated GitOps Pipeline

```yaml
# Senior approach - Comprehensive GitHub Actions pipeline
name: Deploy AP Intake

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # Code quality and security
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.11]

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-dev.txt

    - name: Lint with flake8
      run: |
        flake8 app/ tests/ --count --select=E9,F63,F7,F82 --show-source --statistics
        flake8 app/ tests/ --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

    - name: Type check with mypy
      run: mypy app/

    - name: Run security scan
      run: |
        bandit -r app/ -f json -o security-report.json
        safety check --json --output safety-report.json

    - name: Run tests with coverage
      env:
        DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test_db
        SECRET_KEY: test-secret-key
      run: |
        pytest tests/ --cov=app --cov-report=xml --cov-report=html --junitxml=test-results.xml

    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml

    - name: Upload test results
      uses: actions/upload-artifact@v3
      if: always()
      with:
        name: test-results
        path: |
          test-results.xml
          htmlcov/
          security-report.json
          safety-report.json

  # Build and security scan container
  build:
    runs-on: ubuntu-latest
    needs: test
    if: github.event_name == 'push'

    steps:
    - uses: actions/checkout@v4

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Log in to Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Extract metadata
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
        tags: |
          type=ref,event=branch
          type=ref,event=pr
          type=sha,prefix={{branch}}-
          type=raw,value=latest,enable={{is_default_branch}}

    - name: Build and push Docker image
      uses: docker/build-push-action@v5
      with:
        context: .
        push: true
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}
        cache-from: type=gha
        cache-to: type=gha,mode=max

    - name: Run container security scan
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
        format: 'sarif'
        output: 'trivy-results.sarif'

    - name: Upload Trivy scan results
      uses: github/codeql-action/upload-sarif@v2
      if: always()
      with:
        sarif_file: 'trivy-results.sarif'

  # Deploy to staging
  deploy-staging:
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/main'
    environment: staging

    steps:
    - uses: actions/checkout@v4

    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v4
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: us-east-1

    - name: Update kubeconfig
      run: aws eks update-kubeconfig --name ap-intake-staging

    - name: Deploy to staging
      run: |
        helm upgrade --install ap-intake ./helm/ap-intake \
          --namespace ap-intake-staging \
          --create-namespace \
          --set image.tag=${{ github.sha }} \
          --set environment=staging \
          --set ingress.host=staging-api.company.com \
          --wait --timeout=10m

    - name: Run smoke tests
      run: |
        ./scripts/smoke-tests.sh https://staging-api.company.com

    - name: Run integration tests
      run: |
        ./scripts/integration-tests.sh staging

  # Deploy to production (manual approval)
  deploy-production:
    runs-on: ubuntu-latest
    needs: [build, deploy-staging]
    if: github.ref == 'refs/heads/main'
    environment: production

    steps:
    - uses: actions/checkout@v4

    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v4
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: us-east-1

    - name: Update kubeconfig
      run: aws eks update-kubeconfig --name ap-intake-production

    - name: Deploy to production
      run: |
        helm upgrade --install ap-intake ./helm/ap-intake \
          --namespace ap-intake \
          --create-namespace \
          --set image.tag=${{ github.sha }} \
          --set environment=production \
          --set ingress.host=api.company.com \
          --wait --timeout=15m

    - name: Run production health checks
      run: |
        ./scripts/health-checks.sh production

    - name: Run load tests
      run: |
        ./scripts/load-tests.sh https://api.company.com

    - name: Notify deployment success
      uses: 8398a7/action-slack@v3
      with:
        status: success
        channel: '#deployments'
        text: '✅ AP Intake deployed to production successfully'
      env:
        SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}

  # Rollback procedure
  rollback:
    runs-on: ubuntu-latest
    if: failure() && github.ref == 'refs/heads/main'
    needs: deploy-production
    environment: production

    steps:
    - uses: actions/checkout@v4

    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v4
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: us-east-1

    - name: Update kubeconfig
      run: aws eks update-kubeconfig --name ap-intake-production

    - name: Rollback deployment
      run: |
        # Get previous successful revision
        PREV_REVISION=$(helm history ap-intake -n ap-intake -o json | jq -r '.[] | select(.status == "deployed") | .revision' | tail -2 | head -1)

        if [ -n "$PREV_REVISION" ]; then
          helm rollback ap-intake $PREV_REVISION -n ap-intake
          echo "Rolled back to revision $PREV_REVISION"
        else
          echo "No previous successful revision found"
          exit 1
        fi

    - name: Notify rollback
      uses: 8398a7/action-slack@v3
      with:
        status: custom
        custom_payload: |
          {
            text: '🚨 AP Intake deployment failed and has been rolled back',
            channel: '#deployments',
            username: 'GitHub Actions'
          }
      env:
        SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

**Senior Pattern Benefits:**
- Automated testing and quality gates
- Container security scanning
- Multi-environment deployment
- Manual approval for production
- Automated rollback on failure
- Comprehensive notification system

---

## Conclusion

The AP Intake & Validation system demonstrates **senior-level production deployment excellence** through:

1. **Enterprise-Grade Kubernetes Configuration** with proper security and resource management
2. **Advanced Autoscaling** with custom metrics and intelligent scaling policies
3. **Complete Infrastructure as Code** with Terraform and GitOps practices
4. **Comprehensive Observability** with monitoring, alerting, and visualization
5. **Automated CI/CD Pipeline** with proper gates and rollback procedures

These deployment patterns ensure the system is **reliable, scalable, maintainable, and secure** in production environments, representing the difference between junior deployments that just work and senior-level production systems that excel.

---

**Deployment Patterns Version**: 1.0.0
**Last Updated**: November 2025
**Target Audience**: DevOps Engineers, Platform Engineers, SREs