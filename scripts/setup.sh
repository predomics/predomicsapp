#!/usr/bin/env bash
# =============================================================================
# PredomicsApp — Interactive Setup Script
#
# Generates the .env file used by docker-compose.yml + docker-compose.prod.yml.
# Every answer is written as a setting that the stack actually reads.
# NGINX is configured from templates (nginx/https, nginx/http) by the DOMAIN and
# NGINX_MODE values in .env — this script does not write NGINX files.
#
# Run once before first deployment:
#   ./scripts/setup.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

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
    printf -v "$var_name" '%s' "$value"
}

ask_secret() {
    local prompt="$1"
    local var_name="$2"
    local value

    read -rsp "$(echo -e "${GREEN}?${NC} ${prompt}: ")" value
    echo
    printf -v "$var_name" '%s' "$value"
}

ask_yn() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    local value

    read -rp "$(echo -e "${GREEN}?${NC} ${prompt} [${YELLOW}${default}${NC}]: ")" value
    value="${value:-$default}"
    if [[ "$value" =~ ^[Yy] ]]; then
        printf -v "$var_name" 'true'
    else
        printf -v "$var_name" 'false'
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

if ! docker compose version &>/dev/null; then
    echo -e "${RED}Error: Docker Compose v2 is not available (need >= 2.24).${NC}"
    exit 1
fi
COMPOSE_VERSION="$(docker compose version --short 2>/dev/null | sed 's/^v//')"
echo -e "  ${GREEN}✓${NC} Docker Compose ${COMPOSE_VERSION:-available}"
COMPOSE_MAJOR="${COMPOSE_VERSION%%.*}"
COMPOSE_MINOR="$(echo "$COMPOSE_VERSION" | cut -d. -f2)"
if [[ "$COMPOSE_MAJOR" =~ ^[0-9]+$ && "$COMPOSE_MINOR" =~ ^[0-9]+$ ]]; then
    if [ "$COMPOSE_MAJOR" -lt 2 ] || { [ "$COMPOSE_MAJOR" -eq 2 ] && [ "$COMPOSE_MINOR" -lt 24 ]; }; then
        echo -e "${RED}Error: Docker Compose >= 2.24 is required (found ${COMPOSE_VERSION}).${NC}"
        exit 1
    fi
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

echo -e "${BOLD}${CYAN}1/6 — Domain & SSL${NC}"
echo

ask "Domain name (e.g., predomics.example.com)" "" DOMAIN
if [ -z "$DOMAIN" ]; then
    echo -e "${RED}Error: a domain name (or host name) is required.${NC}"
    exit 1
fi
ask_yn "Terminate HTTPS here with Let's Encrypt? (N = plain HTTP behind another proxy)" "Y" ENABLE_SSL

CERTBOT_EMAIL=""
TRUSTED_PROXY=""
if [ "$ENABLE_SSL" = true ]; then
    ask "Email for Let's Encrypt SSL certificates" "" CERTBOT_EMAIL
    NGINX_MODE="https"
    PUBLIC_URL="https://${DOMAIN}"
else
    NGINX_MODE="http"
    ask "Public URL users will type in their browser" "http://${DOMAIN}" PUBLIC_URL
    # Needed for rate limiting and audit logs to see the real client addresses.
    ask "Address or CIDR of the proxy/load balancer in front of this server (empty if none)" "" TRUSTED_PROXY
fi

echo

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

echo -e "${BOLD}${CYAN}2/6 — Database${NC}"
echo

# The bundled PostgreSQL container always needs a password, even when the app
# is pointed at an external database.
DB_PASSWORD="$(generate_secret | head -c 32)"
ask_yn "Use bundled PostgreSQL container?" "Y" USE_BUNDLED_DB

if [ "$USE_BUNDLED_DB" = true ]; then
    echo -e "  ${GREEN}✓${NC} Database password generated (stored in .env, never displayed)"
    DB_URL="postgresql+asyncpg://predomics:${DB_PASSWORD}@db:5432/predomics"
else
    ask "External PostgreSQL URL" "postgresql+asyncpg://user:pass@host:5432/predomics" DB_URL
    echo -e "  ${YELLOW}Note:${NC} the bundled db container still starts (unused); the backup service dumps the bundled one only."
fi

echo

# ---------------------------------------------------------------------------
# Accounts & security
# ---------------------------------------------------------------------------

echo -e "${BOLD}${CYAN}3/6 — Accounts & security${NC}"
echo

echo -e "  Generating JWT secret key..."
SECRET_KEY="$(generate_secret)"
echo -e "  ${GREEN}✓${NC} Secret key generated"

ask "Administrator email (this account gets admin rights when it registers)" "" ADMIN_EMAIL
ask_yn "Allow anyone to create an account (open registration)?" "Y" REGISTRATION_ENABLED
ask_yn "Create the public demo account (demo@predomics.com / demo)?" "N" SEED_DEMO
ask "Session lifetime in minutes (renewed while the interface is in use; 480 = 8h)" "480" TOKEN_EXPIRY

echo

# ---------------------------------------------------------------------------
# Compute resources
# ---------------------------------------------------------------------------

echo -e "${BOLD}${CYAN}4/6 — Compute resources${NC}"
echo

AVAILABLE_CPUS=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
ask "CPUs the app container may use" "$AVAILABLE_CPUS" CPU_LIMIT
ask "Memory the app container may use (e.g. 4G, 16G)" "4G" MEMORY_LIMIT
ask "Analysis jobs running at the same time (others wait in a queue)" "2" MAX_JOBS
DEFAULT_THREADS=$(( CPU_LIMIT / MAX_JOBS )); [ "$DEFAULT_THREADS" -ge 1 ] || DEFAULT_THREADS=1
ask "Maximum threads per job (0 = all CPUs)" "$DEFAULT_THREADS" MAX_THREADS
ask "Maximum upload size per file (MB)" "500" MAX_UPLOAD_MB

echo

# ---------------------------------------------------------------------------
# Optional: Email
# ---------------------------------------------------------------------------

echo -e "${BOLD}${CYAN}5/6 — Optional services${NC}"
echo

echo -e "  Without SMTP, users cannot reset a forgotten password themselves"
echo -e "  (an administrator resets it through the API, see README)."
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

echo

# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------

echo -e "${BOLD}${CYAN}6/6 — Backups${NC}"
echo

ask "Backup schedule (cron, UTC)" "0 2 * * *" BACKUP_SCHEDULE
ask "Backup retention (days)" "7" BACKUP_DAYS

echo

# ---------------------------------------------------------------------------
# Write .env
# ---------------------------------------------------------------------------

echo -e "${BOLD}Writing .env...${NC}"

# Values are single-quoted where they may contain characters that Compose
# would otherwise interpret.
cat > "$ENV_FILE" << ENVEOF
# PredomicsApp — Production Environment
# Generated by setup.sh on $(date -u '+%Y-%m-%d %H:%M:%S UTC')
# Contains secrets — do NOT commit to git. Reference: DEPLOYMENT.md "Settings".

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------
PREDOMICS_SECRET_KEY=${SECRET_KEY}
POSTGRES_PASSWORD=${DB_PASSWORD}

# --------------------------------------------------------------------------
# Domain & reverse proxy
# --------------------------------------------------------------------------
DOMAIN=${DOMAIN}
NGINX_MODE=${NGINX_MODE}
$( [ -n "$TRUSTED_PROXY" ] && echo "NGINX_TRUSTED_PROXY=${TRUSTED_PROXY}" || echo "# NGINX_TRUSTED_PROXY=" )
NGINX_MAX_BODY=${MAX_UPLOAD_MB}M
CERTBOT_EMAIL=${CERTBOT_EMAIL}

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
PREDOMICS_DATABASE_URL=${DB_URL}

# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------
PREDOMICS_CORS_ORIGINS='["${PUBLIC_URL}"]'
PREDOMICS_FRONTEND_URL=${PUBLIC_URL}
PREDOMICS_ACCESS_TOKEN_EXPIRE_MINUTES=${TOKEN_EXPIRY}

# Accounts
PREDOMICS_ADMIN_EMAIL=${ADMIN_EMAIL}
PREDOMICS_REGISTRATION_ENABLED=${REGISTRATION_ENABLED}
PREDOMICS_SEED_DEMO=${SEED_DEMO}

# Uploads and jobs
PREDOMICS_MAX_UPLOAD_MB=${MAX_UPLOAD_MB}
PREDOMICS_MAX_CONCURRENT_JOBS=${MAX_JOBS}
PREDOMICS_MAX_THREADS_PER_JOB=${MAX_THREADS}
PREDOMICS_JOB_TIMEOUT_MINUTES=0

# Container resource limits (docker-compose.prod.yml)
PREDOMICS_CPU_LIMIT=${CPU_LIMIT}
PREDOMICS_MEMORY_LIMIT=${MEMORY_LIMIT}
ENVEOF

if [ "$ENABLE_SMTP" = true ]; then
    cat >> "$ENV_FILE" << SMTPEOF

# --------------------------------------------------------------------------
# Email (SMTP)
# --------------------------------------------------------------------------
PREDOMICS_SMTP_HOST=${SMTP_HOST}
PREDOMICS_SMTP_PORT=${SMTP_PORT}
PREDOMICS_SMTP_USER=${SMTP_USER}
PREDOMICS_SMTP_FROM=${SMTP_FROM}
SMTPEOF
    # Single-quoted for Compose (literal value; \' escapes a quote).
    printf "PREDOMICS_SMTP_PASSWORD='%s'\n" "${SMTP_PASSWORD//\'/\\\'}" >> "$ENV_FILE"
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
# Backup (docker-compose.prod.yml "backup" service)
# --------------------------------------------------------------------------
BACKUP_SCHEDULE='${BACKUP_SCHEDULE}'
BACKUP_RETENTION_DAYS=${BACKUP_DAYS}
# BACKUP_FAILURE_URL=https://hc-ping.com/<uuid>/fail
# BACKUP_POST_HOOK=rclone copy /backups remote:predomics-backups
BACKUPEOF

chmod 600 "$ENV_FILE"
echo -e "  ${GREEN}✓${NC} .env written (permissions: 600)"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

echo
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Setup complete!${NC}"
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════${NC}"
echo
echo -e "  ${BOLD}Public URL:${NC}   ${PUBLIC_URL}"
echo -e "  ${BOLD}Proxy mode:${NC}   ${NGINX_MODE}"
echo -e "  ${BOLD}Database:${NC}     $([ "$USE_BUNDLED_DB" = true ] && echo "bundled PostgreSQL" || echo "external")"
echo -e "  ${BOLD}Admin:${NC}        ${ADMIN_EMAIL:-"(none — set PREDOMICS_ADMIN_EMAIL in .env)"}"
echo -e "  ${BOLD}Registration:${NC} $([ "$REGISTRATION_ENABLED" = true ] && echo "open" || echo "closed (admins create accounts)")"
echo -e "  ${BOLD}Jobs:${NC}         ${MAX_JOBS} at a time, up to ${MAX_THREADS} threads each"
echo -e "  ${BOLD}SMTP:${NC}         $([ "$ENABLE_SMTP" = true ] && echo -e "${GREEN}configured${NC}" || echo -e "disabled")"
echo -e "  ${BOLD}scitq:${NC}        $([ "$ENABLE_SCITQ" = true ] && echo -e "${GREEN}configured${NC}" || echo -e "disabled")"
echo -e "  ${BOLD}Backups:${NC}      '${BACKUP_SCHEDULE}' UTC, kept ${BACKUP_DAYS} days, in ./backups"
echo
echo -e "  ${BOLD}Next steps:${NC}"
echo

STEP=1
if [ "$ENABLE_SSL" = true ]; then
    echo -e "    ${STEP}. Obtain the SSL certificate (DNS for ${DOMAIN} must point here):"
    echo -e "       ${CYAN}./scripts/ssl-init.sh${NC}"
    echo
    STEP=$((STEP + 1))
fi
echo -e "    ${STEP}. Build and start the production stack (first build: 10-25 minutes):"
echo -e "       ${CYAN}${COMPOSE_CMD} up -d --build${NC}"
echo
STEP=$((STEP + 1))
echo -e "    ${STEP}. Open ${BOLD}${PUBLIC_URL}${NC} and register with the administrator email."
echo
