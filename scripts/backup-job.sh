#!/bin/sh
# PredomicsApp — backup job (runs inside the `backup` container of
# docker-compose.prod.yml on the BACKUP_SCHEDULE cron; also usable by hand:
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup backup-job.sh
#
# Writes, atomically (temp file then rename):
#   /backups/db_<UTC timestamp>.dump      PostgreSQL custom-format dump
#   /backups/data_<UTC timestamp>.tar.gz  the application data volume
# Connection settings come from the standard PG* environment variables.
#
# On failure: exits non-zero, leaves /backups/LAST_FAILURE (the container turns
# unhealthy) and calls BACKUP_FAILURE_URL if set. On success: removes that
# marker, updates /backups/LAST_SUCCESS and runs BACKUP_POST_HOOK if set.
set -u

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DATA_DIR="${DATA_DIR:-/app/data}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TS="$(date -u +%Y%m%d_%H%M%S)"

log() { echo "[backup $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

fail() {
    log "FAILED: $*"
    echo "$TS $*" > "$BACKUP_DIR/LAST_FAILURE"
    rm -f "$BACKUP_DIR"/.tmp_*"$TS"* 2>/dev/null
    if [ -n "${BACKUP_FAILURE_URL:-}" ]; then
        wget -q -T 20 -O /dev/null "$BACKUP_FAILURE_URL" || log "could not reach BACKUP_FAILURE_URL"
    fi
    exit 1
}

mkdir -p "$BACKUP_DIR" || { echo "cannot create $BACKUP_DIR" >&2; exit 1; }
log "starting (retention: ${RETENTION_DAYS} days)"

# --- 1. Database ------------------------------------------------------------
DB_TMP="$BACKUP_DIR/.tmp_db_$TS.dump"
DB_OUT="$BACKUP_DIR/db_$TS.dump"
pg_dump -Fc -f "$DB_TMP" || fail "pg_dump returned an error"
[ -s "$DB_TMP" ] || fail "database dump is empty"
pg_restore -l "$DB_TMP" > /dev/null || fail "database dump is not readable by pg_restore"
mv "$DB_TMP" "$DB_OUT" || fail "could not move the database dump into place"
log "database: $(du -h "$DB_OUT" | cut -f1) -> $(basename "$DB_OUT")"

# --- 2. Data volume ---------------------------------------------------------
# In-app backup archives and re-creatable caches are left out.
DATA_TMP="$BACKUP_DIR/.tmp_data_$TS.tar.gz"
DATA_OUT="$BACKUP_DIR/data_$TS.tar.gz"
tar czf "$DATA_TMP" -C "$DATA_DIR" --exclude=./backups --exclude=./cache .
rc=$?
# tar exits 1 when a file changed while being read (a job writing its log):
# the archive is still usable. Anything above 1 is a real error.
[ "$rc" -le 1 ] || fail "tar returned $rc"
[ -s "$DATA_TMP" ] || fail "data archive is empty"
gzip -t "$DATA_TMP" || fail "data archive is corrupt"
mv "$DATA_TMP" "$DATA_OUT" || fail "could not move the data archive into place"
log "data:     $(du -h "$DATA_OUT" | cut -f1) -> $(basename "$DATA_OUT")"

# --- 3. Retention -----------------------------------------------------------
find "$BACKUP_DIR" -maxdepth 1 \( -name 'db_*.dump' -o -name 'data_*.tar.gz' \) \
    -mtime +"$RETENTION_DAYS" -exec rm -f {} + || log "WARNING: retention cleanup failed"
find "$BACKUP_DIR" -maxdepth 1 -name '.tmp_*' -mtime +1 -exec rm -f {} + 2>/dev/null

rm -f "$BACKUP_DIR/LAST_FAILURE"
echo "$TS" > "$BACKUP_DIR/LAST_SUCCESS"

# --- 4. Optional off-host copy ---------------------------------------------
if [ -n "${BACKUP_POST_HOOK:-}" ]; then
    log "running BACKUP_POST_HOOK"
    BACKUP_TIMESTAMP="$TS" sh -c "$BACKUP_POST_HOOK" || fail "BACKUP_POST_HOOK returned an error"
fi

log "done"
