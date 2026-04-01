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

### Development

```bash
git clone https://github.com/predomics/predomicsapp.git && cd predomicsapp
docker compose up -d --build
```

The application will be available on port **8001**.

### Production

A full production stack is provided with NGINX reverse proxy, Let's Encrypt SSL, resource limits, log rotation, and automated daily backups.

```bash
cd predomicsapp

# 1. Configure production environment
cp .env.example .env
# Edit .env — set DOMAIN, CERTBOT_EMAIL, POSTGRES_PASSWORD, PREDOMICS_SECRET_KEY

# 2. Obtain SSL certificate (first time only)
./scripts/ssl-init.sh

# 3. Start the production stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The production override (`docker-compose.prod.yml`) adds:
- **NGINX** reverse proxy with SSL termination (ports 80/443)
- **Certbot** for automatic Let's Encrypt certificate renewal (every 12h)
- **Resource limits** on all services (app: 4G/2CPU, db: 1G/1CPU)
- **Log rotation** (json-file driver with max-size/max-file)
- **Backup service** — daily PostgreSQL dump + data volume archive with configurable retention
- No exposed ports except 80/443 (app and db are internal only)

Key files: [`.env.example`](.env.example) | [`docker-compose.prod.yml`](docker-compose.prod.yml) | [`nginx/nginx.conf`](nginx/nginx.conf) | [`scripts/`](scripts/)

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
| `PREDOMICS_SAMPLES_DIR` | `samples` | Bundled demo datasets directory (baked in image). |
| `PREDOMICS_SAMPLE_DIR` | `samples/qin2014_cirrhosis` | Default demo dataset for backward compatibility. |
| `PREDOMICS_DEBUG` | `false` | Enable debug logging. |
| `PREDOMICS_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins (JSON array). |
| `PREDOMICS_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT token expiry (24 hours). |
| `PREDOMICS_DEFAULT_THREAD_NUMBER` | `4` | Default thread count for gpredomics. |


### Docker Build Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `GPREDOMICS_REF` | `main` | Git ref (tag/branch) for gpredomics. Use `v1.0.0` for pinned releases. |
| `GPREDOMICSPY_REF` | `main` | Git ref for gpredomicspy Python bindings. |

```bash
# Build with pinned versions
docker compose build --build-arg GPREDOMICS_REF=v1.0.0 --build-arg GPREDOMICSPY_REF=main
```

### Dependency Locking

| Layer | Loose deps | Lock file | How to update |
|-------|-----------|-----------|---------------|
| **Rust** | `Cargo.toml` | `Cargo.lock` | `cargo update` |
| **Python** | `pyproject.toml` | `requirements.lock` | `pip freeze > requirements.lock` |
| **JS** | `package.json` | `package-lock.json` | `npm update` |
| **Rust toolchain** | — | Pinned to `1.84.0` | Update in Dockerfile + CI |
| **Python runtime** | — | Pinned to `3.11` | Update Dockerfile base image |

### Architecture

```
predomicsapp/              ← self-contained, no parent directory needed
├── Dockerfile             ← multi-stage: frontend + rust-builder + runtime
├── docker-compose.yml     ← production (context: .)
├── docker-compose.dev.yml ← development with hot-reload
├── backend/               ← FastAPI + gpredomicspy
├── frontend/              ← Vue.js 3
├── samples/               ← bundled demo datasets (baked in image, read-only)
│   ├── qin2014_cirrhosis/
│   ├── derosa2025_ici/
│   └── wetlab_protocol/
└── data/                  ← user workspace (persistent volume mount)
    ├── projects/
    ├── datasets/
    └── uploads/
```

gpredomics and gpredomicspy are **cloned from GitHub during Docker build** — no sibling directories needed.

---

## NGINX Reverse Proxy

The production stack includes an NGINX reverse proxy configured in [`nginx/nginx.conf`](nginx/nginx.conf). It provides:

- HTTP → HTTPS redirect
- SSL/TLS with Let's Encrypt certificates
- Security headers (HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
- WebSocket upgrade support (for job progress streaming)
- Static asset caching (7 days for `/assets/`)
- Large upload support (`client_max_body_size 500M`)
- Long proxy timeouts (600s for analysis jobs)
- Silent `/health` endpoint (no access logging)

The config is mounted read-only into the nginx container. To customize, edit `nginx/nginx.conf` directly.

**Standalone NGINX** (without Docker): Copy the config to `/etc/nginx/sites-available/predomics`, update `proxy_pass` to `http://127.0.0.1:8001`, then:

```bash
ln -s /etc/nginx/sites-available/predomics /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

---

## SSL/TLS with Let's Encrypt

### With the production Docker stack (recommended)

SSL is handled automatically by the `certbot` service in `docker-compose.prod.yml`:

```bash
# First-time setup — obtains initial certificate
./scripts/ssl-init.sh

# Use --staging for testing (non-trusted certs, no rate limits)
./scripts/ssl-init.sh --staging
```

The certbot container automatically renews certificates every 12 hours. Certificates are stored in `./certbot/conf/`.

### Standalone (without Docker)

```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
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

### Automated backups (production stack)

The production `docker-compose.prod.yml` includes a dedicated backup service that runs daily at 02:00 UTC. It creates:
- **PostgreSQL dump** (`backups/db_YYYYMMDD_HHMMSS.dump`) — custom format for efficient restore
- **Data volume archive** (`backups/data_YYYYMMDD_HHMMSS.tar.gz`) — uploads, projects, datasets

Configure retention via `BACKUP_RETENTION_DAYS` in `.env` (default: 7 days).

### Manual backup and restore scripts

```bash
# Manual backup (DB + data volume, with retention cleanup)
./scripts/backup.sh

# List available backups
ls backups/

# Restore from a specific timestamp (both DB + data)
./scripts/restore.sh 20260215_020000

# Restore database only
./scripts/restore.sh 20260215_020000 --db

# Restore data volume only
./scripts/restore.sh 20260215_020000 --data
```

### Quick manual commands

```bash
# Database dump (development)
docker exec predomics-db pg_dump -U predomics predomics > backup.sql

# Database restore (development)
docker compose stop app
docker exec -i predomics-db psql -U predomics predomics < backup.sql
docker compose start app
```

---

## Kubernetes (Helm)

A Helm chart is provided in [`helm/predomicsapp/`](helm/predomicsapp/) for Kubernetes deployment.

### Quick start

```bash
# Install with default values
helm install predomics ./helm/predomicsapp/

# Install with custom values
helm install predomics ./helm/predomicsapp/ \
  --set ingress.enabled=true \
  --set ingress.host=predomics.example.com \
  --set ingress.tls.enabled=true \
  --set ingress.annotations."cert-manager\.io/cluster-issuer"=letsencrypt-prod

# Upgrade
helm upgrade predomics ./helm/predomicsapp/ -f my-values.yaml
```

### Key values

| Parameter | Default | Description |
|-----------|---------|-------------|
| `image.repository` | `ghcr.io/predomics/predomicsapp` | Container image |
| `image.tag` | `latest` | Image tag |
| `replicaCount` | `1` | Number of replicas |
| `resources.limits.memory` | `4Gi` | Memory limit |
| `resources.limits.cpu` | `2` | CPU limit |
| `ingress.enabled` | `false` | Enable Ingress |
| `ingress.host` | `predomics.example.com` | Ingress hostname |
| `persistence.size` | `20Gi` | Data volume size |
| `postgresql.enabled` | `true` | Use bundled PostgreSQL |
| `externalDatabase.url` | `""` | External database URL |

See [`helm/predomicsapp/values.yaml`](helm/predomicsapp/values.yaml) for all configurable values.

### Using an external database

```bash
helm install predomics ./helm/predomicsapp/ \
  --set postgresql.enabled=false \
  --set externalDatabase.url="postgresql+asyncpg://user:pass@host:5432/predomics"
```

### Secrets

The chart auto-generates secrets if `secrets.existingSecret` is not set. For production, create a Kubernetes secret first:

```bash
kubectl create secret generic predomics-secrets \
  --from-literal=secret-key=$(openssl rand -hex 32) \
  --from-literal=postgres-password="STRONG_PASSWORD"

helm install predomics ./helm/predomicsapp/ \
  --set secrets.existingSecret=predomics-secrets
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

- **Swagger UI**: `https://your-domain.com/api/docs`
- **ReDoc**: `https://your-domain.com/api/redoc`
- **OpenAPI JSON**: `https://your-domain.com/api/openapi.json`
