# 部署与运维

> 模块: Deployment & Operations
> 版本: 1.0.0
> 最后更新: 2024-12-13

---

## 1. 部署架构

### 1.1 总体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Production Architecture                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         Internet                                     │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                           │
│                                  ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     CloudFlare / AWS CloudFront                      │    │
│  │                        (CDN + DDoS Protection)                       │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                           │
│                                  ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         AWS ALB / Nginx                              │    │
│  │                      (Load Balancer + SSL)                           │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                           │
│         ┌────────────────────────┼────────────────────────┐                 │
│         │                        │                        │                 │
│         ▼                        ▼                        ▼                 │
│  ┌─────────────┐          ┌─────────────┐          ┌─────────────┐         │
│  │  API Pod 1  │          │  API Pod 2  │          │  API Pod 3  │         │
│  │ (FastAPI)   │          │ (FastAPI)   │          │ (FastAPI)   │         │
│  └─────────────┘          └─────────────┘          └─────────────┘         │
│                                  │                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     Background Workers (K8s)                         │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐    │    │
│  │  │   Event     │ │  Rebalance  │ │    Risk     │ │  Scheduler  │    │    │
│  │  │  Listener   │ │   Worker    │ │   Monitor   │ │   Worker    │    │    │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                  │                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         Data Layer                                   │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐    │    │
│  │  │ PostgreSQL  │ │   Redis     │ │ TimescaleDB │ │     S3      │    │    │
│  │  │  (Primary)  │ │  (Cluster)  │ │  (Metrics)  │ │  (Backups)  │    │    │
│  │  │  (Replica)  │ │             │ │             │ │             │    │    │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                       Monitoring & Logging                           │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐    │    │
│  │  │ Prometheus  │ │   Grafana   │ │     ELK     │ │  PagerDuty  │    │    │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 环境规划

| 环境 | 用途 | 配置 |
|------|------|------|
| **Development** | 本地开发 | Docker Compose |
| **Staging** | 测试验证 | K8s (1 replica) |
| **Production** | 生产环境 | K8s (3+ replicas) + 高可用 |

---

## 2. Kubernetes 部署

### 2.1 API 服务部署

```yaml
# k8s/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: paimon-api
  labels:
    app: paimon-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: paimon-api
  template:
    metadata:
      labels:
        app: paimon-api
    spec:
      containers:
        - name: api
          image: paimon/api:latest
          ports:
            - containerPort: 8000
          env:
            - name: ENVIRONMENT
              value: production
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: paimon-secrets
                  key: database-url
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: paimon-secrets
                  key: redis-url
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: paimon-api-service
spec:
  selector:
    app: paimon-api
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: paimon-api-ingress
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts:
        - api.paimon.fund
      secretName: paimon-api-tls
  rules:
    - host: api.paimon.fund
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: paimon-api-service
                port:
                  number: 80
```

### 2.2 Event Listener 部署

```yaml
# k8s/event-listener-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: paimon-event-listener
  labels:
    app: paimon-event-listener
spec:
  replicas: 1  # 单实例，避免重复处理
  strategy:
    type: Recreate  # 确保只有一个实例
  selector:
    matchLabels:
      app: paimon-event-listener
  template:
    metadata:
      labels:
        app: paimon-event-listener
    spec:
      containers:
        - name: event-listener
          image: paimon/event-listener:latest
          env:
            - name: BSC_RPC_URL
              valueFrom:
                secretKeyRef:
                  name: paimon-secrets
                  key: bsc-rpc-url
            - name: BSC_WS_URL
              valueFrom:
                secretKeyRef:
                  name: paimon-secrets
                  key: bsc-ws-url
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "200m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8001
            initialDelaySeconds: 30
            periodSeconds: 30
```

### 2.3 Worker 部署

```yaml
# k8s/workers-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: paimon-rebalance-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: paimon-rebalance-worker
  template:
    metadata:
      labels:
        app: paimon-rebalance-worker
    spec:
      containers:
        - name: worker
          image: paimon/worker:latest
          args: ["--worker=rebalance"]
          env:
            - name: AWS_KMS_KEY_ID
              valueFrom:
                secretKeyRef:
                  name: paimon-secrets
                  key: kms-key-id
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: paimon-risk-monitor
spec:
  replicas: 1
  selector:
    matchLabels:
      app: paimon-risk-monitor
  template:
    metadata:
      labels:
        app: paimon-risk-monitor
    spec:
      containers:
        - name: worker
          image: paimon/worker:latest
          args: ["--worker=risk"]
```

### 2.4 Secrets 管理

```yaml
# k8s/secrets.yaml (加密存储)
apiVersion: v1
kind: Secret
metadata:
  name: paimon-secrets
type: Opaque
stringData:
  database-url: "postgresql://user:pass@host:5432/paimon"
  redis-url: "redis://host:6379"
  bsc-rpc-url: "https://bsc-dataseed.binance.org"
  bsc-ws-url: "wss://bsc-ws-node.nariox.org"
  jwt-secret: "<strong-secret>"
  kms-key-id: "arn:aws:kms:..."
```

---

## 3. Docker 配置

### 3.1 Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 创建虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 生产镜像
FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production

# 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制应用代码
COPY ./src ./src
COPY ./alembic ./alembic
COPY ./alembic.ini .

# 非 root 用户
RUN addgroup --system --gid 1001 appgroup
RUN adduser --system --uid 1001 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3.2 Docker Compose (开发环境)

```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=development
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/paimon
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis
    volumes:
      - ./src:/app/src
    command: ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

  event-listener:
    build: .
    command: ["python", "-m", "src.event_listener.main"]
    environment:
      - ENVIRONMENT=development
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/paimon
      - REDIS_URL=redis://redis:6379
      - BSC_RPC_URL=${BSC_RPC_URL}
    depends_on:
      - db
      - redis
    volumes:
      - ./src:/app/src

  celery-worker:
    build: .
    command: ["celery", "-A", "src.workers.celery_app", "worker", "--loglevel=info"]
    environment:
      - ENVIRONMENT=development
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/paimon
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis
    volumes:
      - ./src:/app/src

  db:
    image: timescale/timescaledb:latest-pg16
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=paimon
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

---

## 4. CI/CD 流水线

### 4.1 GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      redis:
        image: redis:7
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run linter
        run: |
          ruff check src/
          mypy src/

      - name: Run tests
        run: pytest tests/ -v --cov=src --cov-report=xml
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test
          REDIS_URL: redis://localhost:6379

      - name: Run e2e tests
        run: pytest tests/e2e/ -v
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test
          REDIS_URL: redis://localhost:6379

  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4

      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets.KUBE_CONFIG_STAGING }}

      - name: Deploy to staging
        run: |
          kubectl set image deployment/paimon-api \
            api=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          kubectl rollout status deployment/paimon-api

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets.KUBE_CONFIG_PRODUCTION }}

      - name: Deploy to production
        run: |
          kubectl set image deployment/paimon-api \
            api=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          kubectl rollout status deployment/paimon-api
```

---

## 5. 监控与告警

### 5.1 Prometheus 指标

```python
# src/core/metrics.py
from prometheus_client import Counter, Gauge, Histogram, REGISTRY

# 业务指标
class Metrics:
    """Prometheus 指标收集"""

    # 赎回相关
    redemption_requests = Counter(
        'paimon_redemption_requests_total',
        'Total redemption requests',
        ['channel', 'status']
    )

    pending_redemptions = Gauge(
        'paimon_pending_redemptions',
        'Current pending redemption count',
        ['channel']
    )

    # 调仓相关
    rebalance_executions = Counter(
        'paimon_rebalance_executions_total',
        'Total rebalance executions',
        ['trigger', 'status']
    )

    # 风控相关
    risk_level = Gauge(
        'paimon_risk_level',
        'Current risk level (1-4)'
    )

    l1_ratio = Gauge(
        'paimon_l1_ratio',
        'Layer 1 liquidity ratio'
    )

    # API 性能
    http_request_duration = Histogram(
        'paimon_http_request_duration_seconds',
        'HTTP request duration',
        ['method', 'route', 'status'],
        buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5]
    )

    # 事件处理
    event_processing_duration = Histogram(
        'paimon_event_processing_duration_seconds',
        'Event processing duration',
        ['event_type'],
        buckets=[0.01, 0.1, 0.5, 1, 5, 10]
    )

    event_queue_size = Gauge(
        'paimon_event_queue_size',
        'Event queue size',
        ['priority']
    )


# 全局实例
metrics = Metrics()
```

### 5.2 Grafana 仪表板

```json
{
  "dashboard": {
    "title": "Paimon Fund Operations",
    "panels": [
      {
        "title": "Risk Level",
        "type": "gauge",
        "targets": [
          { "expr": "paimon_risk_level" }
        ],
        "fieldConfig": {
          "defaults": {
            "thresholds": {
              "steps": [
                { "value": 1, "color": "green" },
                { "value": 2, "color": "yellow" },
                { "value": 3, "color": "orange" },
                { "value": 4, "color": "red" }
              ]
            }
          }
        }
      },
      {
        "title": "Liquidity Ratios",
        "type": "timeseries",
        "targets": [
          { "expr": "paimon_l1_ratio", "legendFormat": "L1" },
          { "expr": "paimon_l2_ratio", "legendFormat": "L2" },
          { "expr": "paimon_l3_ratio", "legendFormat": "L3" }
        ]
      },
      {
        "title": "Redemption Requests (24h)",
        "type": "stat",
        "targets": [
          { "expr": "increase(paimon_redemption_requests_total[24h])" }
        ]
      },
      {
        "title": "API Latency (P99)",
        "type": "timeseries",
        "targets": [
          {
            "expr": "histogram_quantile(0.99, rate(paimon_http_request_duration_seconds_bucket[5m]))"
          }
        ]
      }
    ]
  }
}
```

### 5.3 告警规则

```yaml
# prometheus/alerts.yml
groups:
  - name: paimon-alerts
    rules:
      # 风控告警
      - alert: HighRiskLevel
        expr: paimon_risk_level >= 3
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High risk level detected"
          description: "Risk level is {{ $value }} for more than 5 minutes"

      - alert: LowLiquidity
        expr: paimon_l1_ratio < 0.08
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "L1 liquidity is low"
          description: "L1 ratio is {{ $value }}, below 8% threshold"

      # 性能告警
      - alert: HighAPILatency
        expr: histogram_quantile(0.99, rate(paimon_http_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency"
          description: "P99 latency is {{ $value }}s"

      - alert: EventProcessingLag
        expr: paimon_event_queue_size > 1000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Event processing lag"
          description: "Queue size is {{ $value }}"

      # 服务健康
      - alert: ServiceDown
        expr: up{job="paimon-api"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Paimon API is down"
```

---

## 6. 日志管理

### 6.1 日志格式 (JSON)

```python
# src/core/logging.py
import logging
import sys
import json
from datetime import datetime
from typing import Any
import os


class JSONFormatter(logging.Formatter):
    """JSON 格式日志"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "service": "paimon-api",
            "environment": os.getenv("ENVIRONMENT", "development"),
            "logger": record.name,
        }

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # 添加额外字段
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """配置日志"""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # 清除已有处理器
    root_logger.handlers.clear()

    # 添加 JSON 格式处理器
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """获取日志记录器"""
    return logging.getLogger(name)
```

### 6.2 ELK Stack 配置

```yaml
# filebeat.yml
filebeat.inputs:
  - type: container
    paths:
      - '/var/lib/docker/containers/*/*.log'
    processors:
      - add_kubernetes_metadata:
          host: ${NODE_NAME}
          matchers:
            - logs_path:
                logs_path: "/var/lib/docker/containers/"

output.elasticsearch:
  hosts: ['${ELASTICSEARCH_HOST}']
  index: "paimon-logs-%{+yyyy.MM.dd}"

setup.kibana:
  host: '${KIBANA_HOST}'
```

---

## 7. 备份与恢复

### 7.1 备份策略

| 数据 | 频率 | 保留 | 方式 |
|------|------|------|------|
| PostgreSQL | 每日全量 + 每小时WAL | 30天 | pg_dump + WAL归档 |
| Redis | 每小时 RDB | 7天 | RDB快照 |
| 配置 | 每次变更 | 永久 | Git |
| Secrets | 每日 | 90天 | AWS Secrets Manager |

### 7.2 备份脚本

```bash
#!/bin/bash
# scripts/backup.sh

set -e

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/backups
S3_BUCKET=s3://paimon-backups

# PostgreSQL 备份
echo "Backing up PostgreSQL..."
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME -F c \
  -f $BACKUP_DIR/postgres_$DATE.dump

# 上传到 S3
aws s3 cp $BACKUP_DIR/postgres_$DATE.dump \
  $S3_BUCKET/postgres/$DATE/

# Redis 备份
echo "Backing up Redis..."
redis-cli -h $REDIS_HOST BGSAVE
sleep 5
aws s3 cp /var/lib/redis/dump.rdb \
  $S3_BUCKET/redis/$DATE/

# 清理本地旧备份
find $BACKUP_DIR -mtime +7 -delete

echo "Backup completed: $DATE"
```

### 7.3 恢复流程

```bash
#!/bin/bash
# scripts/restore.sh

set -e

BACKUP_DATE=$1

if [ -z "$BACKUP_DATE" ]; then
  echo "Usage: ./restore.sh YYYYMMDD_HHMMSS"
  exit 1
fi

S3_BUCKET=s3://paimon-backups

# 下载备份
aws s3 cp $S3_BUCKET/postgres/$BACKUP_DATE/postgres_$BACKUP_DATE.dump ./

# 停止服务
kubectl scale deployment paimon-api --replicas=0
kubectl scale deployment paimon-event-listener --replicas=0

# 恢复数据库
pg_restore -h $DB_HOST -U $DB_USER -d $DB_NAME -c \
  postgres_$BACKUP_DATE.dump

# 重启服务
kubectl scale deployment paimon-api --replicas=3
kubectl scale deployment paimon-event-listener --replicas=1

echo "Restore completed from: $BACKUP_DATE"
```

---

## 8. 灾难恢复

### 8.1 RTO/RPO 目标

| 指标 | 目标 | 说明 |
|------|------|------|
| **RPO** | < 1小时 | 最多丢失1小时数据 |
| **RTO** | < 4小时 | 4小时内恢复服务 |

### 8.2 灾难恢复流程

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     Disaster Recovery Procedure                           │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  1. 检测与评估 (0-15分钟)                                                 │
│     • 确认故障范围                                                        │
│     • 评估影响程度                                                        │
│     • 通知相关人员                                                        │
│                                                                           │
│  2. 启动备用环境 (15-60分钟)                                              │
│     • 切换 DNS 到备用区域                                                 │
│     • 启动备用 K8s 集群                                                   │
│     • 验证网络连通性                                                      │
│                                                                           │
│  3. 数据恢复 (60-180分钟)                                                 │
│     • 从最新备份恢复 PostgreSQL                                           │
│     • 应用 WAL 日志                                                       │
│     • 恢复 Redis 缓存                                                     │
│                                                                           │
│  4. 服务恢复 (180-240分钟)                                                │
│     • 部署应用服务                                                        │
│     • 验证 API 功能                                                       │
│     • 恢复事件监听                                                        │
│     • 处理积压事件                                                        │
│                                                                           │
│  5. 验证与监控                                                            │
│     • 全面功能测试                                                        │
│     • 监控系统指标                                                        │
│     • 确认服务正常                                                        │
│                                                                           │
│  6. 事后分析                                                              │
│     • 编写事故报告                                                        │
│     • 分析根本原因                                                        │
│     • 制定改进措施                                                        │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 9. 运维检查清单

### 9.1 每日检查

- [ ] 检查所有服务健康状态
- [ ] 检查风险指标
- [ ] 检查待处理赎回
- [ ] 检查事件处理延迟
- [ ] 审查告警通知
- [ ] 确认备份完成

### 9.2 每周检查

- [ ] 审查 SLA 达成率
- [ ] 检查数据库性能
- [ ] 审查安全日志
- [ ] 检查证书有效期
- [ ] 审查资源使用趋势

### 9.3 每月检查

- [ ] 执行灾难恢复演练
- [ ] 审查访问权限
- [ ] 更新依赖包
- [ ] 审查监控告警阈值
- [ ] 生成月度运维报告

---

## 10. 联系方式

### 10.1 值班表

| 角色 | 联系方式 | 响应时间 |
|------|----------|----------|
| 一线运维 | oncall@paimon.fund | 15分钟 |
| 后端开发 | dev@paimon.fund | 30分钟 |
| 基金经理 | fund@paimon.fund | 1小时 |

### 10.2 升级路径

```
Level 1: 一线运维 (自动告警)
    ↓ 30分钟无响应
Level 2: 后端开发 (Slack + 电话)
    ↓ 1小时无响应
Level 3: 技术负责人 (电话)
    ↓ 重大故障
Level 4: 管理层 (电话会议)
```

---

*文档完成。如需更详细的配置或部署指南，请联系技术团队。*
