# GeoInsight API Deployment Guide

## Overview

This guide covers deploying the GeoInsight API in various environments, from development to production. The application is designed to be container-native and cloud-ready.

## Prerequisites

### System Requirements

**Minimum Production Requirements:**
- **CPU**: 4 cores
- **Memory**: 8GB RAM
- **Storage**: 100GB SSD
- **Network**: 1Gbps connection

**Recommended Production Requirements:**
- **CPU**: 8+ cores
- **Memory**: 16GB+ RAM
- **Storage**: 500GB+ SSD with high IOPS
- **Network**: 10Gbps connection

### Software Dependencies

- Docker 20.10+
- Docker Compose 2.0+
- Python 3.11+
- PostgreSQL 15+ with PostGIS 3.3+
- Redis 7.0+
- nginx 1.20+ (for production)

## Local Development Setup

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/your-org/geospatial-api.git
cd geospatial-api

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r tests/requirements.txt
```

### 2. Environment Configuration

Create `.env` file:

```bash
# Database Configuration
DATABASE_URL=postgresql+asyncpg://geoapi:password@localhost:5432/geoapi_dev
DATABASE_TEST_URL=postgresql+asyncpg://geoapi:password@localhost:5432/geoapi_test

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Application Configuration
SECRET_KEY=your-secret-key-here
ENVIRONMENT=development
DEBUG=true
APP_NAME=GeoInsight API
APP_VERSION=1.0.0

# CORS Configuration
BACKEND_CORS_ORIGINS=["http://localhost:3000", "http://localhost:8000"]

# Rate Limiting
RATE_LIMIT_PER_MINUTE=100

# External Services
OSRM_BASE_URL=http://localhost:5000

# Monitoring
ENABLE_METRICS=true
LOG_LEVEL=INFO
```

### 3. Database Setup

```bash
# Start PostgreSQL with PostGIS
docker run -d \
  --name postgres-geoapi \
  -e POSTGRES_DB=geoapi_dev \
  -e POSTGRES_USER=geoapi \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  postgis/postgis:15-3.3

# Run database migrations
alembic upgrade head

# Create test database
docker exec postgres-geoapi createdb -U geoapi geoapi_test
```

### 4. Redis Setup

```bash
# Start Redis
docker run -d \
  --name redis-geoapi \
  -p 6379:6379 \
  redis:7-alpine
```

### 5. Start Development Server

```bash
# Start the API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start Celery worker (separate terminal)
celery -A app.celery_app worker --loglevel=info

# Start Celery beat (separate terminal)
celery -A app.celery_app beat --loglevel=info
```

## Docker Deployment

### 1. Build Docker Image

```bash
# Build the application image
docker build -t geoinsight/api:latest .

# Build with specific tag
docker build -t geoinsight/api:1.0.0 .
```

### 2. Docker Compose Setup

**docker-compose.yml:**

```yaml
version: '3.8'

services:
  postgres:
    image: postgis/postgis:15-3.3
    environment:
      POSTGRES_DB: geoapi
      POSTGRES_USER: geoapi
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U geoapi"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://geoapi:${DB_PASSWORD}@postgres:5432/geoapi
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
      - ENVIRONMENT=production
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  celery-worker:
    build: .
    command: celery -A app.celery_app worker --loglevel=info
    environment:
      - DATABASE_URL=postgresql+asyncpg://geoapi:${DB_PASSWORD}@postgres:5432/geoapi
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      - postgres
      - redis
    deploy:
      replicas: 2

  celery-beat:
    build: .
    command: celery -A app.celery_app beat --loglevel=info
    environment:
      - DATABASE_URL=postgresql+asyncpg://geoapi:${DB_PASSWORD}@postgres:5432/geoapi
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      - postgres
      - redis

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./docker/nginx.conf:/etc/nginx/nginx.conf
      - ./docker/ssl:/etc/nginx/ssl
    depends_on:
      - api

volumes:
  postgres_data:
  redis_data:
```

### 3. Environment Variables

Create `.env` file for production:

```bash
# Generate secure secret key
SECRET_KEY=$(openssl rand -hex 32)

# Database password
DB_PASSWORD=your-secure-db-password

# Other production settings
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
```

### 4. Start Services

```bash
# Start all services
docker-compose up -d

# Run database migrations
docker-compose exec api alembic upgrade head

# Check service status
docker-compose ps

# View logs
docker-compose logs -f api
```

## Production Deployment

### 1. Kubernetes Deployment

**namespace.yaml:**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: geoinsight
```

**configmap.yaml:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: geoinsight-config
  namespace: geoinsight
data:
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
  APP_NAME: "GeoInsight API"
  APP_VERSION: "1.0.0"
  REDIS_URL: "redis://redis-service:6379/0"
  OSRM_BASE_URL: "http://osrm-service:5000"
```

**secret.yaml:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: geoinsight-secrets
  namespace: geoinsight
type: Opaque
data:
  DATABASE_URL: <base64-encoded-database-url>
  SECRET_KEY: <base64-encoded-secret-key>
```

**deployment.yaml:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: geoinsight-api
  namespace: geoinsight
spec:
  replicas: 3
  selector:
    matchLabels:
      app: geoinsight-api
  template:
    metadata:
      labels:
        app: geoinsight-api
    spec:
      containers:
      - name: api
        image: geoinsight/api:1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: geoinsight-secrets
              key: DATABASE_URL
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: geoinsight-secrets
              key: SECRET_KEY
        envFrom:
        - configMapRef:
            name: geoinsight-config
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

**service.yaml:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: geoinsight-api-service
  namespace: geoinsight
spec:
  selector:
    app: geoinsight-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: ClusterIP
```

**ingress.yaml:**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: geoinsight-api-ingress
  namespace: geoinsight
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  tls:
  - hosts:
    - api.geoinsight.example.com
    secretName: geoinsight-tls
  rules:
  - host: api.geoinsight.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: geoinsight-api-service
            port:
              number: 80
```

### 2. Deploy to Kubernetes

```bash
# Apply all configurations
kubectl apply -f k8s/

# Check deployment status
kubectl get pods -n geoinsight

# Check service status
kubectl get services -n geoinsight

# View logs
kubectl logs -f deployment/geoinsight-api -n geoinsight

# Scale deployment
kubectl scale deployment geoinsight-api --replicas=5 -n geoinsight
```

### 3. Database Setup for Production

**PostgreSQL with High Availability:**

```bash
# Using PostgreSQL Operator (example with Zalando)
kubectl apply -f https://raw.githubusercontent.com/zalando/postgres-operator/v1.8.2/manifests/configmap.yaml
kubectl apply -f https://raw.githubusercontent.com/zalando/postgres-operator/v1.8.2/manifests/operator-service-account-rbac.yaml
kubectl apply -f https://raw.githubusercontent.com/zalando/postgres-operator/v1.8.2/manifests/postgres-operator.yaml

# Create PostgreSQL cluster
kubectl apply -f - <<EOF
apiVersion: "acid.zalan.do/v1"
kind: postgresql
metadata:
  name: geoinsight-postgres
  namespace: geoinsight
spec:
  teamId: "geoinsight"
  volume:
    size: 100Gi
    storageClass: fast-ssd
  numberOfInstances: 3
  users:
    geoapi:
    - superuser
    - createdb
  databases:
    geoapi: geoapi
  postgresql:
    version: "15"
    parameters:
      shared_preload_libraries: "pg_stat_statements,postgis"
      max_connections: "200"
      shared_buffers: "256MB"
      effective_cache_size: "1GB"
      maintenance_work_mem: "64MB"
      checkpoint_completion_target: "0.7"
      wal_buffers: "16MB"
      default_statistics_target: "100"
      random_page_cost: "1.1"
      effective_io_concurrency: "200"
EOF
```

### 4. Redis Setup for Production

```bash
# Redis cluster with Redis Operator
kubectl apply -f https://raw.githubusercontent.com/spotahome/redis-operator/v1.2.4/manifests/databases.spotahome.com_redisfailovers.yaml
kubectl apply -f https://raw.githubusercontent.com/spotahome/redis-operator/v1.2.4/example/operator/all-redis-operator-resources.yaml

# Create Redis cluster
kubectl apply -f - <<EOF
apiVersion: databases.spotahome.com/v1
kind: RedisFailover
metadata:
  name: geoinsight-redis
  namespace: geoinsight
spec:
  sentinel:
    replicas: 3
    resources:
      requests:
        cpu: 100m
        memory: 100Mi
      limits:
        cpu: 400m
        memory: 500Mi
  redis:
    replicas: 3
    resources:
      requests:
        cpu: 100m
        memory: 100Mi
      limits:
        cpu: 400m
        memory: 500Mi
    storage:
      persistentVolumeClaim:
        metadata:
          name: geoinsight-redis-data
        spec:
          accessModes:
            - ReadWriteOnce
          resources:
            requests:
              storage: 10Gi
          storageClassName: fast-ssd
EOF
```

## Monitoring and Logging

### 1. Prometheus Monitoring

**prometheus-config.yaml:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: geoinsight
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
    scrape_configs:
    - job_name: 'geoinsight-api'
      static_configs:
      - targets: ['geoinsight-api-service:80']
      metrics_path: /api/v1/monitoring/metrics
    - job_name: 'postgres'
      static_configs:
      - targets: ['postgres-exporter:9187']
    - job_name: 'redis'
      static_configs:
      - targets: ['redis-exporter:9121']
```

### 2. Grafana Dashboard

Import the GeoInsight dashboard from `docs/grafana-dashboard.json`:

```json
{
  "dashboard": {
    "title": "GeoInsight API Dashboard",
    "panels": [
      {
        "title": "API Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(api_requests_total[5m])",
            "legendFormat": "{{method}} {{endpoint}}"
          }
        ]
      },
      {
        "title": "Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, api_response_time_seconds_bucket)",
            "legendFormat": "95th percentile"
          }
        ]
      },
      {
        "title": "Spatial Operations",
        "type": "stat",
        "targets": [
          {
            "expr": "rate(spatial_operations_total[5m])",
            "legendFormat": "{{operation_type}}"
          }
        ]
      }
    ]
  }
}
```

### 3. ELK Stack for Logging

**elasticsearch.yaml:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: elasticsearch
  namespace: geoinsight
spec:
  replicas: 1
  selector:
    matchLabels:
      app: elasticsearch
  template:
    metadata:
      labels:
        app: elasticsearch
    spec:
      containers:
      - name: elasticsearch
        image: elasticsearch:7.17.0
        ports:
        - containerPort: 9200
        env:
        - name: discovery.type
          value: single-node
        - name: ES_JAVA_OPTS
          value: "-Xms1g -Xmx1g"
        volumeMounts:
        - name: elasticsearch-data
          mountPath: /usr/share/elasticsearch/data
      volumes:
      - name: elasticsearch-data
        persistentVolumeClaim:
          claimName: elasticsearch-pvc
```

## Security Considerations

### 1. Network Security

```yaml
# Network policy to restrict traffic
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: geoinsight-network-policy
  namespace: geoinsight
spec:
  podSelector:
    matchLabels:
      app: geoinsight-api
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: postgres
    ports:
    - protocol: TCP
      port: 5432
  - to:
    - podSelector:
        matchLabels:
          app: redis
    ports:
    - protocol: TCP
      port: 6379
```

### 2. Pod Security Policy

```yaml
apiVersion: policy/v1beta1
kind: PodSecurityPolicy
metadata:
  name: geoinsight-psp
spec:
  privileged: false
  allowPrivilegeEscalation: false
  requiredDropCapabilities:
    - ALL
  volumes:
    - 'configMap'
    - 'emptyDir'
    - 'projected'
    - 'secret'
    - 'downwardAPI'
    - 'persistentVolumeClaim'
  runAsUser:
    rule: 'MustRunAsNonRoot'
  seLinux:
    rule: 'RunAsAny'
  fsGroup:
    rule: 'RunAsAny'
```

## Scaling and Performance

### 1. Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: geoinsight-api-hpa
  namespace: geoinsight
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: geoinsight-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### 2. Vertical Pod Autoscaler

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: geoinsight-api-vpa
  namespace: geoinsight
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: geoinsight-api
  updatePolicy:
    updateMode: "Auto"
  resourcePolicy:
    containerPolicies:
    - containerName: api
      minAllowed:
        cpu: 100m
        memory: 256Mi
      maxAllowed:
        cpu: 2000m
        memory: 2Gi
```

## Backup and Recovery

### 1. Database Backup

```bash
# Automated backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/postgres"
DB_NAME="geoapi"

# Create backup
kubectl exec -n geoinsight postgresql-0 -- pg_dump -U geoapi $DB_NAME | gzip > $BACKUP_DIR/geoapi_backup_$DATE.sql.gz

# Upload to S3
aws s3 cp $BACKUP_DIR/geoapi_backup_$DATE.sql.gz s3://geoinsight-backups/postgres/

# Cleanup old backups (keep last 30 days)
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
```

### 2. Redis Backup

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/redis"

# Create Redis backup
kubectl exec -n geoinsight redis-0 -- redis-cli BGSAVE
kubectl cp geoinsight/redis-0:/data/dump.rdb $BACKUP_DIR/redis_backup_$DATE.rdb

# Upload to S3
aws s3 cp $BACKUP_DIR/redis_backup_$DATE.rdb s3://geoinsight-backups/redis/
```

## Troubleshooting

### Common Issues

1. **Database Connection Issues**
   ```bash
   # Check database connectivity
   kubectl exec -n geoinsight deployment/geoinsight-api -- python -c "
   import asyncio
   from app.database import test_connection
   asyncio.run(test_connection())
   "
   ```

2. **Memory Issues**
   ```bash
   # Check memory usage
   kubectl top pods -n geoinsight
   
   # Check memory limits
   kubectl describe pod -n geoinsight <pod-name>
   ```

3. **Performance Issues**
   ```bash
   # Check slow queries
   kubectl exec -n geoinsight postgresql-0 -- psql -U geoapi -c "
   SELECT query, mean_time, calls 
   FROM pg_stat_statements 
   ORDER BY mean_time DESC 
   LIMIT 10;
   "
   ```

### Monitoring Checklist

- [ ] API response times < 200ms (95th percentile)
- [ ] Database connection pool utilization < 80%
- [ ] Memory usage < 80%
- [ ] CPU usage < 70%
- [ ] Disk usage < 80%
- [ ] Error rate < 1%
- [ ] All health checks passing

This deployment guide provides a comprehensive approach to deploying GeoInsight API across different environments while maintaining security, scalability, and observability best practices.