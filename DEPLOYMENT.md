# PredomicsApp — Production Deployment Guide

## Table of Contents

1. [Quick Start (Docker Compose)](#quick-start-docker-compose)
2. [Environment Variables](#environment-variables)
3. [NGINX Reverse Proxy](#nginx-reverse-proxy)
4. [SSL/TLS with Let's Encrypt](#ssltls-with-lets-encrypt)
5. [PostgreSQL Configuration](#postgresql-configuration)
6. [Backup & Restore](#backup--restore)
7. [Kubernetes (Helm)](#kubernetes-helm)
8. [Monitoring & Health Checks](#monitoring--health-checks)
9. [Troubleshooting](#troubleshooting)

---

## Quick Start (Docker Compose)

The simplest way to deploy PredomicsApp is with the included `docker-compose.yml`.

```bash
# Clone the repository
git clone <repo-url> && cd predomics_suite

# Create a .env file with production settings
cat > predomicsapp-web/.env <<EOF
PREDOMICS_SECRET_KEY=$(openssl rand -hex 32)
PREDOMICS_DATABASE_URL=postgresql+asyncpg://predomics:STRONG_PASSWORD@db:5432/predomics
POSTGRES_PASSWORD=STRONG_PASSWORD
EOF

# Build and start
cd predomicsapp-web
docker compose up -d --build
```

The application will be available on port **8001** (configurable via `docker-compose.yml`).

### Production docker-compose.yml overrides

Create a `docker-compose.prod.yml` to override development defaults:

```yaml
services:
  db:
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - /opt/predomics/pgdata:/var/lib/postgresql/data
    restart: always

  app:
    ports:
      - "127.0.0.1:8001:8000"   # bind to localhost only (NGINX will proxy)
    environment:
      - PREDOMICS_SECRET_KEY=${PREDOMICS_SECRET_KEY}
      - PREDOMICS_DATABASE_URL=${PREDOMICS_DATABASE_URL}
      - PREDOMICS_CORS_ORIGINS=["https://your-domain.com"]
    volumes:
      - /opt/predomics/data:/app/data
    restart: always
```

Launch with:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## Environment Variables

All settings use the `PREDOMICS_` prefix (via pydantic-settings).

| Variable | Default | Description |
|----------|---------|-------------|
| `PREDOMICS_SECRET_KEY` | `CHANGE-ME-IN-PRODUCTION` | JWT signing key. **Must** be changed. |
| `PREDOMICS_DATABASE_URL` | `postgresql+asyncpg://predomics:predomics@localhost:5432/predomics` | Async database connection string. |
| `PREDOMICS_DATA_DIR` | `data` | Root directory for all persistent data. |
| `PREDOMICS_UPLOAD_DIR` | `data/uploads` | Directory for uploaded dataset files. |
| `PREDOMICS_PROJECT_DIR` | `data/projects` | Directory for project/job result files. |
| `PREDOMICS_SAMPLE_DIR` | `data/qin2014_cirrhosis` | Demo dataset directory. |
| `PREDOMICS_DEBUG` | `false` | Enable debug logging. |
| `PREDOMICS_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins (JSON array). |
| `PREDOMICS_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT token expiry (24 hours). |
| `PREDOMICS_DEFAULT_THREAD_NUMBER` | `4` | Default thread count for gpredomics. |

---

## NGINX Reverse Proxy

Place this in `/etc/nginx/sites-available/predomics`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Redirect HTTP → HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Max upload size (for dataset files)
    client_max_body_size 500M;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (if needed in future)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts for long-running analysis jobs
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    # Cache static assets
    location /assets/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_cache_valid 200 7d;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable and reload:

```bash
ln -s /etc/nginx/sites-available/predomics /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

---

## SSL/TLS with Let's Encrypt

```bash
# Install certbot
apt install certbot python3-certbot-nginx

# Obtain certificate
certbot --nginx -d your-domain.com

# Auto-renewal (certbot adds a systemd timer by default)
certbot renew --dry-run
```

---

## PostgreSQL Configuration

### Migrating from the bundled PostgreSQL

For production workloads, you may want to run PostgreSQL on a dedicated server or managed service (AWS RDS, Google Cloud SQL, etc.).

1. **Update the connection string:**

```bash
PREDOMICS_DATABASE_URL=postgresql+asyncpg://user:password@db-host:5432/predomics
```

2. **Remove the `db` service** from docker-compose and the `depends_on` clause.

### Recommended PostgreSQL settings

For a server with 4–8 GB RAM handling typical workloads:

```ini
# postgresql.conf
shared_buffers = 1GB
effective_cache_size = 3GB
work_mem = 16MB
maintenance_work_mem = 256MB
max_connections = 100
```

### Schema migrations

PredomicsApp runs schema migrations automatically on startup. The `schema_versions` table tracks which migrations have been applied. Migrations are idempotent and safe to re-run.

Current migrations: v2 (dataset library) → v3 (composite datasets) → v4 (admin flag) → v5 (job name) → v6 (job user_id) → v7 (config hash) → v8 (disk size) → v9 (dataset tags) → v10 (batch_id).

---

## Backup & Restore

### Database backup

```bash
# Dump the database from the Docker container
docker exec predomics-db pg_dump -U predomics predomics > backup_$(date +%Y%m%d).sql

# Or from an external host
pg_dump -h localhost -p 5433 -U predomics predomics > backup_$(date +%Y%m%d).sql
```

### Database restore

```bash
# Stop the app first
docker compose stop app

# Restore
docker exec -i predomics-db psql -U predomics predomics < backup_20260215.sql

# Restart
docker compose start app
```

### File data backup

Back up the data volume which contains uploads, project results, and datasets:

```bash
# If using named volume
docker run --rm -v predomics_app-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/predomics-data-$(date +%Y%m%d).tar.gz -C /data .

# If using bind mount
tar czf predomics-data-$(date +%Y%m%d).tar.gz /opt/predomics/data/
```

### Automated backup script

```bash
#!/bin/bash
# /opt/predomics/backup.sh — run via cron daily
BACKUP_DIR=/opt/predomics/backups
mkdir -p "$BACKUP_DIR"
DATE=$(date +%Y%m%d)

# Database
docker exec predomics-db pg_dump -U predomics predomics | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# Files
docker run --rm -v predomics_app-data:/data -v "$BACKUP_DIR":/backup alpine \
  tar czf "/backup/data_$DATE.tar.gz" -C /data .

# Keep last 30 days
find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete
```

Add to crontab: `0 2 * * * /opt/predomics/backup.sh`

---

## Kubernetes (Helm)

A basic Kubernetes deployment consists of:

### Deployment manifest (predomics-deployment.yaml)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: predomics-web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: predomics-web
  template:
    metadata:
      labels:
        app: predomics-web
    spec:
      containers:
        - name: app
          image: your-registry/predomics-web:latest
          ports:
            - containerPort: 8000
          env:
            - name: PREDOMICS_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: predomics-secrets
                  key: secret-key
            - name: PREDOMICS_DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: predomics-secrets
                  key: database-url
          volumeMounts:
            - name: data
              mountPath: /app/data
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "2000m"
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: predomics-data

---
apiVersion: v1
kind: Service
metadata:
  name: predomics-web
spec:
  selector:
    app: predomics-web
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: predomics-data
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 20Gi
```

### Secrets

```bash
kubectl create secret generic predomics-secrets \
  --from-literal=secret-key=$(openssl rand -hex 32) \
  --from-literal=database-url="postgresql+asyncpg://user:pass@postgres-svc:5432/predomics"
```

### Ingress (with cert-manager)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: predomics-ingress
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts: [your-domain.com]
      secretName: predomics-tls
  rules:
    - host: your-domain.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: predomics-web
                port:
                  number: 80
```

---

## Monitoring & Health Checks

### Health endpoint

The application exposes `GET /health` which returns:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "gpredomicspy_available": true
}
```

### Docker health check

The Dockerfile includes a built-in health check:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
```

### Monitoring with external tools

```bash
# Simple uptime check with curl
curl -sf http://localhost:8001/health | jq .status

# Prometheus-style check (integrate with your monitoring stack)
# The /health endpoint can be scraped directly
```

---

## Troubleshooting

### Application won't start

```bash
# Check logs
docker compose logs app

# Common issues:
# - Database not ready: ensure db healthcheck passes before app starts
# - Port conflict: change the host port in docker-compose.yml
# - Missing gpredomicspy: check Rust build stage in Docker logs
```

### Database connection errors

```bash
# Verify database is running
docker compose exec db pg_isready -U predomics

# Check connection from app container
docker compose exec app python -c "
import asyncio, asyncpg
asyncio.run(asyncpg.connect('postgresql://predomics:predomics@db:5432/predomics'))
print('OK')
"
```

### Migration issues

Migrations are idempotent. If a migration fails, check logs and restart:

```bash
docker compose logs app | grep -i migration
docker compose restart app
```

### Large dataset uploads timing out

Increase NGINX and proxy timeouts:

```nginx
client_max_body_size 1G;
proxy_read_timeout 900s;
```

### API documentation

FastAPI auto-generates interactive API docs:

- **Swagger UI**: `https://your-domain.com/docs`
- **ReDoc**: `https://your-domain.com/redoc`
- **OpenAPI JSON**: `https://your-domain.com/openapi.json`
