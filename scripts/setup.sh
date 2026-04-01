#!/usr/bin/env bash
# =============================================================================
# PredomicsApp — Interactive Setup Script
#
# Generates .env, NGINX config, and optionally initializes SSL.
# Run once before first deployment:
#   ./scripts/setup.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
NGINX_CONF="$PROJECT_DIR/nginx/nginx.conf"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════════════╗"
echo "  ║       PredomicsApp — Production Setup         ║"
echo "  ╚═══════════════════════════════════════════════╝"
echo -e "${NC}"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

ask() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    local value

    if [ -n "$default" ]; then
        read -rp "$(echo -e "${GREEN}?${NC} ${prompt} [${YELLOW}${default}${NC}]: ")" value
        value="${value:-$default}"
    else
        read -rp "$(echo -e "${GREEN}?${NC} ${prompt}: ")" value
    fi
    eval "$var_name='$value'"
}

ask_secret() {
    local prompt="$1"
    local var_name="$2"
    local value

    read -rsp "$(echo -e "${GREEN}?${NC} ${prompt}: ")" value
    echo
    eval "$var_name='$value'"
}

ask_yn() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    local value

    read -rp "$(echo -e "${GREEN}?${NC} ${prompt} [${YELLOW}${default}${NC}]: ")" value
    value="${value:-$default}"
    if [[ "$value" =~ ^[Yy] ]]; then
        eval "$var_name=true"
    else
        eval "$var_name=false"
    fi
}

generate_secret() {
    openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || head -c 64 /dev/urandom | base64 | tr -d '/+=' | head -c 64
}

# ---------------------------------------------------------------------------
# Check prerequisites
# ---------------------------------------------------------------------------

echo -e "${BOLD}Checking prerequisites...${NC}"

if ! command -v docker &>/dev/null; then
    echo -e "${RED}Error: Docker is not installed.${NC}"
    exit 1
fi

if ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}Error: Docker daemon is not running.${NC}"
    exit 1
fi

echo -e "  ${GREEN}✓${NC} Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"

if command -v docker compose &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Docker Compose $(docker compose version --short 2>/dev/null || echo 'available')"
else
    echo -e "${RED}Error: Docker Compose is not available.${NC}"
    exit 1
fi

echo

# ---------------------------------------------------------------------------
# Backup existing .env
# ---------------------------------------------------------------------------

if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Existing .env found. It will be backed up to .env.backup${NC}"
    cp "$ENV_FILE" "$ENV_FILE.backup"
fi

# ---------------------------------------------------------------------------
# Domain & SSL
# ---------------------------------------------------------------------------

echo -e "${BOLD}${CYAN}1/5 — Domain & SSL${NC}"
echo

ask "Domain name (e.g., predomics.example.com)" "" DOMAIN
ask "Email for Let's Encrypt SSL certificates" "" CERTBOT_EMAIL
ask_yn "Enable SSL with Let's Encrypt?" "Y" ENABLE_SSL

echo

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

echo -e "${BOLD}${CYAN}2/5 — Database${NC}"
echo

ask_yn "Use bundled PostgreSQL container?" "Y" USE_BUNDLED_DB

if [ "$USE_BUNDLED_DB" = true ]; then
    echo -e "  Generating secure database password..."
    DB_PASSWORD="$(generate_secret | head -c 32)"
    echo -e "  ${GREEN}✓${NC} Password generated (stored in .env, never displayed)"
    DB_URL="postgresql+asyncpg://predomics:${DB_PASSWORD}@db:5432/predomics"
else
    ask "External PostgreSQL URL" "postgresql+asyncpg://user:pass@host:5432/predomics" DB_URL
    DB_PASSWORD=""
fi

echo

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

echo -e "${BOLD}${CYAN}3/5 — Security${NC}"
echo

echo -e "  Generating JWT secret key..."
SECRET_KEY="$(generate_secret)"
echo -e "  ${GREEN}✓${NC} Secret key generated"

ask "JWT token expiry (minutes, 1440 = 24h)" "1440" TOKEN_EXPIRY

echo

# ---------------------------------------------------------------------------
# Compute resources
# ---------------------------------------------------------------------------

echo -e "${BOLD}${CYAN}4/5 — Compute resources${NC}"
echo

AVAILABLE_CPUS=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
ask "Default thread count for gpredomics" "$AVAILABLE_CPUS" THREAD_COUNT
ask "Max concurrent analysis jobs" "4" MAX_JOBS
ask "gpredomics version to build" "v1.0.0" GPREDOMICS_REF

echo

# ---------------------------------------------------------------------------
# Optional: Email
# ---------------------------------------------------------------------------

echo -e "${BOLD}${CYAN}5/5 — Optional services${NC}"
echo

ask_yn "Configure SMTP email?" "N" ENABLE_SMTP

SMTP_HOST="" SMTP_PORT="" SMTP_USER="" SMTP_PASSWORD="" SMTP_FROM=""
if [ "$ENABLE_SMTP" = true ]; then
    ask "SMTP host" "smtp.gmail.com" SMTP_HOST
    ask "SMTP port" "587" SMTP_PORT
    ask "SMTP username" "" SMTP_USER
    ask_secret "SMTP password" SMTP_PASSWORD
    ask "From address" "$SMTP_USER" SMTP_FROM
fi

ask_yn "Enable scitq distributed computing?" "N" ENABLE_SCITQ

SCITQ_SERVER="" SCITQ_TOKEN=""
if [ "$ENABLE_SCITQ" = true ]; then
    ask "scitq server URL" "https://scitq.example.com" SCITQ_SERVER
    ask_secret "scitq token" SCITQ_TOKEN
fi

ask "Backup retention (days)" "7" BACKUP_DAYS

echo

# ---------------------------------------------------------------------------
# Write .env
# ---------------------------------------------------------------------------

echo -e "${BOLD}Writing .env...${NC}"

cat > "$ENV_FILE" << ENVEOF
# PredomicsApp — Production Environment
# Generated by setup.sh on $(date -u '+%Y-%m-%d %H:%M:%S UTC')
# ⚠️  Contains secrets — do NOT commit to git

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------
PREDOMICS_SECRET_KEY=${SECRET_KEY}
POSTGRES_PASSWORD=${DB_PASSWORD}

# --------------------------------------------------------------------------
# Domain & SSL
# --------------------------------------------------------------------------
DOMAIN=${DOMAIN}
CERTBOT_EMAIL=${CERTBOT_EMAIL}

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
PREDOMICS_DATABASE_URL=${DB_URL}

# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------
PREDOMICS_CORS_ORIGINS=["https://${DOMAIN}"]
PREDOMICS_DATA_DIR=/app/data
PREDOMICS_UPLOAD_DIR=/app/data/uploads
PREDOMICS_PROJECT_DIR=/app/data/projects
PREDOMICS_SAMPLES_DIR=/app/samples
PREDOMICS_SAMPLE_DIR=/app/samples/qin2014_cirrhosis
PREDOMICS_ACCESS_TOKEN_EXPIRE_MINUTES=${TOKEN_EXPIRY}
PREDOMICS_DEFAULT_THREAD_NUMBER=${THREAD_COUNT}
MAX_CONCURRENT_JOBS=${MAX_JOBS}

# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
GPREDOMICS_REF=${GPREDOMICS_REF}
GPREDOMICSPY_REF=main
ENVEOF

if [ "$ENABLE_SMTP" = true ]; then
    cat >> "$ENV_FILE" << SMTPEOF

# --------------------------------------------------------------------------
# Email (SMTP)
# --------------------------------------------------------------------------
PREDOMICS_SMTP_HOST=${SMTP_HOST}
PREDOMICS_SMTP_PORT=${SMTP_PORT}
PREDOMICS_SMTP_USER=${SMTP_USER}
PREDOMICS_SMTP_PASSWORD=${SMTP_PASSWORD}
PREDOMICS_SMTP_FROM=${SMTP_FROM}
SMTPEOF
fi

if [ "$ENABLE_SCITQ" = true ]; then
    cat >> "$ENV_FILE" << SCITQEOF

# --------------------------------------------------------------------------
# Distributed computing (scitq)
# --------------------------------------------------------------------------
PREDOMICS_SCITQ_SERVER=${SCITQ_SERVER}
PREDOMICS_SCITQ_TOKEN=${SCITQ_TOKEN}
SCITQEOF
fi

cat >> "$ENV_FILE" << BACKUPEOF

# --------------------------------------------------------------------------
# Backup
# --------------------------------------------------------------------------
BACKUP_RETENTION_DAYS=${BACKUP_DAYS}
BACKUPEOF

chmod 600 "$ENV_FILE"
echo -e "  ${GREEN}✓${NC} .env written (permissions: 600)"

# ---------------------------------------------------------------------------
# Write NGINX config
# ---------------------------------------------------------------------------

echo -e "${BOLD}Writing NGINX config...${NC}"
mkdir -p "$PROJECT_DIR/nginx"

if [ "$ENABLE_SSL" = true ]; then
    cat > "$NGINX_CONF" << 'NGINXEOF'
server {
    listen 80;
    server_name DOMAIN_PLACEHOLDER;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name DOMAIN_PLACEHOLDER;

    ssl_certificate /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    client_max_body_size 500M;

    # Static assets (long cache)
    location /assets/ {
        proxy_pass http://app:8000;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # Health check (no logging)
    location = /health {
        proxy_pass http://app:8000;
        access_log off;
    }

    # API and app
    location / {
        proxy_pass http://app:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Long timeouts for analysis jobs
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
NGINXEOF
    sed -i.bak "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" "$NGINX_CONF" && rm -f "$NGINX_CONF.bak"
else
    cat > "$NGINX_CONF" << 'NGINXEOF'
server {
    listen 80;
    server_name DOMAIN_PLACEHOLDER;

    client_max_body_size 500M;

    location /assets/ {
        proxy_pass http://app:8000;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    location = /health {
        proxy_pass http://app:8000;
        access_log off;
    }

    location / {
        proxy_pass http://app:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
NGINXEOF
    sed -i.bak "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" "$NGINX_CONF" && rm -f "$NGINX_CONF.bak"
fi

echo -e "  ${GREEN}✓${NC} nginx/nginx.conf written for ${DOMAIN}"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Setup complete!${NC}"
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════${NC}"
echo
echo -e "  ${BOLD}Domain:${NC}     ${DOMAIN}"
echo -e "  ${BOLD}SSL:${NC}        $([ "$ENABLE_SSL" = true ] && echo -e "${GREEN}enabled${NC}" || echo -e "${YELLOW}disabled${NC}")"
echo -e "  ${BOLD}Database:${NC}   $([ "$USE_BUNDLED_DB" = true ] && echo "bundled PostgreSQL" || echo "external")"
echo -e "  ${BOLD}Threads:${NC}    ${THREAD_COUNT}"
echo -e "  ${BOLD}Max jobs:${NC}   ${MAX_JOBS}"
echo -e "  ${BOLD}gpredomics:${NC} ${GPREDOMICS_REF}"
echo -e "  ${BOLD}SMTP:${NC}       $([ "$ENABLE_SMTP" = true ] && echo -e "${GREEN}configured${NC}" || echo -e "disabled")"
echo -e "  ${BOLD}scitq:${NC}      $([ "$ENABLE_SCITQ" = true ] && echo -e "${GREEN}configured${NC}" || echo -e "disabled")"
echo
echo -e "  ${BOLD}Next steps:${NC}"
echo

if [ "$ENABLE_SSL" = true ]; then
    echo -e "    1. Obtain SSL certificate:"
    echo -e "       ${CYAN}./scripts/ssl-init.sh${NC}"
    echo
    echo -e "    2. Start the production stack:"
    echo -e "       ${CYAN}docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build${NC}"
else
    echo -e "    1. Start the production stack:"
    echo -e "       ${CYAN}docker compose up -d --build${NC}"
fi

echo
echo -e "    App will be available at: ${BOLD}http$([ "$ENABLE_SSL" = true ] && echo "s")://${DOMAIN}${NC}"
echo
