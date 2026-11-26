#!/usr/bin/env bash
# PredomicsApp — manual backup from the host
#
# Creates a timestamped PostgreSQL dump and a data volume archive in ./backups,
# using the same job as the scheduled backup of the production stack
# (scripts/backup-job.sh). Works with the base stack and the production stack.
#
# Usage:
#   ./scripts/backup.sh                      # 7-day retention
#   BACKUP_RETENTION_DAYS=30 ./scripts/backup.sh
#   0 2 * * * /path/to/scripts/backup.sh     # host cron alternative
#
# Exits non-zero when any part of the backup fails.
# Note: the data archive contains <data>/.secret_key if the app generated its
# own JWT key — store backups as carefully as the .env file.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_DIR}/backups}"
DB_CONTAINER="${DB_CONTAINER:-predomics-db}"
DATA_VOLUME="${DATA_VOLUME:-predomics_app-data}"

mkdir -p "$BACKUP_DIR"

if ! docker inspect -f '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null | grep -q true; then
    echo "ERROR: database container '$DB_CONTAINER' is not running." >&2
    exit 1
fi

# Same image as the running database (already on this host, same pg_dump version).
PG_IMAGE="${PG_IMAGE:-$(docker inspect -f '{{.Config.Image}}' "$DB_CONTAINER")}"

# Run the job in a throwaway container that shares the database container's
# network, so it works whether or not the database port is published.
docker run --rm \
    --network "container:${DB_CONTAINER}" \
    -e PGHOST=127.0.0.1 \
    -e PGUSER=predomics \
    -e PGDATABASE=predomics \
    -e PGPASSWORD="$(docker exec "$DB_CONTAINER" printenv POSTGRES_PASSWORD)" \
    -e BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}" \
    -e TZ=UTC \
    -v "${DATA_VOLUME}:/app/data:ro" \
    -v "${BACKUP_DIR}:/backups" \
    -v "${SCRIPT_DIR}/backup-job.sh:/usr/local/bin/backup-job.sh:ro" \
    --entrypoint /bin/sh \
    "$PG_IMAGE" /usr/local/bin/backup-job.sh

echo ""
echo "Backups in: $BACKUP_DIR"
# shellcheck disable=SC2012
ls -lh "$BACKUP_DIR" | tail -n 6
