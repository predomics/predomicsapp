#!/usr/bin/env bash
# PredomicsApp — First-Time SSL Certificate Setup
#
# Solves the chicken-and-egg problem: NGINX needs certificates to start,
# but certbot needs NGINX running to complete the ACME challenge.
#
# Usage:
#   1. Set DOMAIN and CERTBOT_EMAIL in your .env file (./scripts/setup.sh does it)
#   2. Run: ./scripts/ssl-init.sh
#   3. Start the full stack: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
#
# For testing, pass --staging to use Let's Encrypt staging servers.
#
# NGINX reads the domain from .env through its config template
# (nginx/https/default.conf.template); no file in the repository is modified.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# --------------------------------------------------------------------------
# Load .env
# --------------------------------------------------------------------------
# Only the keys needed here are read (the file is a Compose env file, not a
# shell script: values such as cron expressions must not be evaluated).
env_get() {
    [ -f .env ] || return 0
    grep -E "^$1=" .env | tail -n 1 | cut -d= -f2- | sed -e "s/^[\"']//" -e "s/[\"']\$//" || true
}
DOMAIN="${DOMAIN:-$(env_get DOMAIN)}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-$(env_get CERTBOT_EMAIL)}"
NGINX_MODE="${NGINX_MODE:-$(env_get NGINX_MODE)}"

DOMAIN="${DOMAIN:?ERROR: Set DOMAIN in .env (e.g. predomics.example.com)}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:?ERROR: Set CERTBOT_EMAIL in .env}"
STAGING_FLAG=""

if [ "${1:-}" = "--staging" ]; then
    STAGING_FLAG="--staging"
    echo "Using Let's Encrypt STAGING servers (certificates will not be trusted)."
fi

if [ "${NGINX_MODE:=https}" != "https" ]; then
    echo "ERROR: NGINX_MODE is '${NGINX_MODE}' in .env; SSL setup needs NGINX_MODE=https." >&2
    exit 1
fi

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
CERTBOT_DIR="./certbot"
LIVE_DIR="${CERTBOT_DIR}/conf/live/${DOMAIN}"
RENEWAL_CONF="${CERTBOT_DIR}/conf/renewal/${DOMAIN}.conf"

echo "=== SSL Certificate Setup ==="
echo "Domain: $DOMAIN"
echo "Email:  $CERTBOT_EMAIL"
echo ""

if [ -f "$RENEWAL_CONF" ] && [ -z "$STAGING_FLAG" ]; then
    echo "A Let's Encrypt certificate for ${DOMAIN} already exists (${RENEWAL_CONF})."
    echo "Nothing to do; the certbot service renews it automatically."
    exit 0
fi

# --------------------------------------------------------------------------
# Step 1: Create dummy certificate so NGINX can start
# --------------------------------------------------------------------------
echo "[1/3] Creating temporary self-signed certificate..."
mkdir -p "$LIVE_DIR" "${CERTBOT_DIR}/www"

openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout "${LIVE_DIR}/privkey.pem" \
    -out "${LIVE_DIR}/fullchain.pem" \
    -subj "/CN=${DOMAIN}" 2>/dev/null

echo "      Temporary certificate created."

# --------------------------------------------------------------------------
# Step 2: Start NGINX with the dummy certificate
# --------------------------------------------------------------------------
echo "[2/3] Starting NGINX..."
# --no-deps: only the proxy is needed for the ACME challenge; the application
# does not have to be built yet (NGINX resolves it lazily).
"${COMPOSE[@]}" up -d --no-deps --force-recreate nginx
echo "      Waiting for NGINX to be ready..."
ready=false
for _ in $(seq 1 30); do
    if "${COMPOSE[@]}" exec -T nginx wget -q -O /dev/null http://127.0.0.1/nginx-health 2>/dev/null; then
        ready=true
        break
    fi
    sleep 1
done
if [ "$ready" != true ]; then
    echo "ERROR: NGINX did not start. Check: ${COMPOSE[*]} logs nginx" >&2
    exit 1
fi

# --------------------------------------------------------------------------
# Step 3: Request real certificate from Let's Encrypt
# --------------------------------------------------------------------------
echo "[3/3] Requesting Let's Encrypt certificate..."
# NGINX keeps the dummy certificate in memory. Remove it from disk, otherwise
# certbot would store the real one under live/<domain>-0001.
rm -rf "$LIVE_DIR" "${CERTBOT_DIR}/conf/archive/${DOMAIN}" "$RENEWAL_CONF"

"${COMPOSE[@]}" run --rm --no-deps --entrypoint certbot certbot \
    certonly --webroot \
    -w /var/www/certbot \
    --email "$CERTBOT_EMAIL" \
    --agree-tos \
    --no-eff-email \
    --non-interactive \
    -d "$DOMAIN" \
    ${STAGING_FLAG:+"$STAGING_FLAG"}

# --------------------------------------------------------------------------
# Reload NGINX with the real certificate
# --------------------------------------------------------------------------
echo ""
echo "Reloading NGINX with the real certificate..."
"${COMPOSE[@]}" exec -T nginx nginx -s reload

echo ""
echo "=== SSL setup complete ==="
echo ""
echo "Your certificate is ready. Start the full stack with:"
echo "  ${COMPOSE[*]} up -d --build"
