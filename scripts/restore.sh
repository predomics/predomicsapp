#!/usr/bin/env bash
# PredomicsApp — Restore Script
#
# Restores a PostgreSQL dump and/or the data volume from a backup timestamp.
# Before touching anything it takes a safety backup of the current state
# (skip with --no-safety-backup).
#
# Usage:
#   ./scripts/restore.sh 20260215_020000          # restore both DB + data
#   ./scripts/restore.sh 20260215_020000 --db      # restore database only
#   ./scripts/restore.sh 20260215_020000 --data    # restore data volume only
#   ./scripts/restore.sh 20260215_020000 --yes     # no confirmation prompt

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_DIR}/backups}"
DB_CONTAINER="${DB_CONTAINER:-predomics-db}"
APP_CONTAINER="${APP_CONTAINER:-predomics-web}"
DATA_VOLUME="${DATA_VOLUME:-predomics_app-data}"

# --------------------------------------------------------------------------
# Arguments
# --------------------------------------------------------------------------
if [ $# -lt 1 ]; then
    echo "Usage: $0 <TIMESTAMP> [--db|--data] [--yes] [--no-safety-backup]"
    echo ""
    echo "Available backups:"
    find "$BACKUP_DIR" -maxdepth 1 -name 'db_*.dump' 2>/dev/null \
        | sed 's/.*db_//;s/\.dump//' | sort -r | sed 's/^/  /' || true
    exit 1
fi

TIMESTAMP="$1"; shift
MODE="--all"
ASSUME_YES=false
SAFETY=true
for arg in "$@"; do
    case "$arg" in
        --db|--data|--all) MODE="$arg" ;;
        --yes|-y) ASSUME_YES=true ;;
        --no-safety-backup) SAFETY=false ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

DB_FILE="${BACKUP_DIR}/db_${TIMESTAMP}.dump"
DATA_FILE="${BACKUP_DIR}/data_${TIMESTAMP}.tar.gz"

# --------------------------------------------------------------------------
# Validate backup files exist and are readable
# --------------------------------------------------------------------------
if [ "$MODE" = "--all" ] || [ "$MODE" = "--db" ]; then
    [ -s "$DB_FILE" ] || { echo "ERROR: Database backup not found or empty: $DB_FILE" >&2; exit 1; }
    docker exec -i "$DB_CONTAINER" pg_restore -l < "$DB_FILE" > /dev/null \
        || { echo "ERROR: $DB_FILE is not a valid pg_dump archive." >&2; exit 1; }
fi

if [ "$MODE" = "--all" ] || [ "$MODE" = "--data" ]; then
    [ -s "$DATA_FILE" ] || { echo "ERROR: Data backup not found or empty: $DATA_FILE" >&2; exit 1; }
    gzip -t "$DATA_FILE" || { echo "ERROR: $DATA_FILE is corrupt." >&2; exit 1; }
fi

# Image of the running database: already on this host, used for file operations too.
PG_IMAGE="${PG_IMAGE:-$(docker inspect -f '{{.Config.Image}}' "$DB_CONTAINER")}"

echo "=== PredomicsApp Restore — $TIMESTAMP ($MODE) ==="
echo ""
echo "WARNING: This will overwrite current data. The app will be stopped during restore."
if [ "$ASSUME_YES" != true ]; then
    read -rp "Continue? [y/N] " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Aborted."
        exit 0
    fi
fi

# --------------------------------------------------------------------------
# Safety backup of the current state
# --------------------------------------------------------------------------
if [ "$SAFETY" = true ]; then
    echo ""
    echo "Taking a safety backup of the current state first..."
    BACKUP_RETENTION_DAYS=36500 "$SCRIPT_DIR/backup.sh" \
        || { echo "ERROR: safety backup failed; nothing was changed. Use --no-safety-backup to skip." >&2; exit 1; }
fi

# --------------------------------------------------------------------------
# Stop the application (container name works for base and production stacks)
# --------------------------------------------------------------------------
echo ""
echo "Stopping application..."
docker stop "$APP_CONTAINER" > /dev/null

restart_app() {
    echo ""
    echo "Restarting application..."
    docker start "$APP_CONTAINER" > /dev/null
}
trap restart_app EXIT

# --------------------------------------------------------------------------
# Restore database
# --------------------------------------------------------------------------
if [ "$MODE" = "--all" ] || [ "$MODE" = "--db" ]; then
    echo ""
    echo "Restoring database from $DB_FILE ..."
    docker exec -i "$DB_CONTAINER" pg_restore \
        -U predomics -d predomics --clean --if-exists --no-owner --exit-on-error \
        < "$DB_FILE"
    echo "Database restored."
fi

# --------------------------------------------------------------------------
# Restore data volume (in-app backup archives in data/backups are kept)
# --------------------------------------------------------------------------
if [ "$MODE" = "--all" ] || [ "$MODE" = "--data" ]; then
    echo ""
    echo "Restoring data volume from $DATA_FILE ..."
    docker run --rm \
        -v "${DATA_VOLUME}:/data" \
        -v "${BACKUP_DIR}:/backup:ro" \
        "$PG_IMAGE" sh -ec "
            find /data -mindepth 1 -maxdepth 1 ! -name backups -exec rm -rf {} +
            tar xzf /backup/data_${TIMESTAMP}.tar.gz -C /data
        "
    echo "Data volume restored."
fi

echo ""
echo "=== Restore complete ==="
