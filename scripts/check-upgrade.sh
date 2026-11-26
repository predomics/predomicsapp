#!/usr/bin/env bash
# PredomicsApp — upgrade check.
#
# Loads the schema of the previous release (v2.2.0, hand-written migrations,
# no user data) into a throwaway PostgreSQL, adds one user, one project and one
# job in the old layout, starts the given image against it and verifies that the
# application migrates the database and still serves the old rows.
#
# Usage:
#   ./scripts/check-upgrade.sh [IMAGE]        # default: predomics-app:latest
#
# Everything it creates (two containers, one network) is removed at the end.
set -euo pipefail

IMAGE="${1:-predomics-app:latest}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIXTURE="$ROOT/.github/fixtures/schema_v2.2.0.sql"
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"
PREFIX="predomics-upgrade-check-$$"
NET="$PREFIX-net"; DB="$PREFIX-db"; APP="$PREFIX-app"

cleanup() {
    docker stop "$APP" "$DB" > /dev/null 2>&1 || true
    docker network rm "$NET" > /dev/null 2>&1 || true
}
trap cleanup EXIT

psql_db() { docker exec -i "$DB" psql -v ON_ERROR_STOP=1 -q -U predomics -d predomics; }

docker network create "$NET" > /dev/null
docker run -d --rm --name "$DB" --network "$NET" \
    -e POSTGRES_USER=predomics -e POSTGRES_PASSWORD=predomics -e POSTGRES_DB=predomics \
    "$PG_IMAGE" > /dev/null
for _ in $(seq 1 60); do
    docker exec "$DB" pg_isready -U predomics -d predomics -q && break
    sleep 1
done
sleep 2

echo "== loading the v2.2.0 schema"
psql_db < "$FIXTURE" > /dev/null
# Rows in the old layout. The password hash is bcrypt("upgrade-check-password").
psql_db <<'SQL'
INSERT INTO users (id, email, hashed_password, full_name, is_active, is_admin, created_at)
VALUES ('u00000000001', 'upgrade@example.org',
        '$2b$12$5uzQv2ok0s8vYy1cPzZ5QuH0gE0q0Yl0pN8pUu1r8qH8m1Yk9mJ4W', 'Upgrade Check', TRUE, FALSE, now());
INSERT INTO projects (id, name, description, user_id, created_at, updated_at)
VALUES ('p00000000001', 'Old project', '', 'u00000000001', now(), now());
INSERT INTO jobs (id, project_id, user_id, status, created_at)
VALUES ('j00000000001', 'p00000000001', 'u00000000001', 'running', now());
SQL

echo "== starting $IMAGE on that database"
docker run -d --rm --name "$APP" --network "$NET" \
    -e PREDOMICS_DATABASE_URL="postgresql+asyncpg://predomics:predomics@$DB:5432/predomics" \
    -e PREDOMICS_SECRET_KEY=upgrade-check-0123456789abcdef0123456789abcdef \
    "$IMAGE" > /dev/null

ready=""
for _ in $(seq 1 90); do
    if docker exec "$APP" python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready', timeout=5)" 2> /dev/null; then
        ready=yes; break
    fi
    docker inspect "$APP" > /dev/null 2>&1 || break
    sleep 2
done
if [ -z "$ready" ]; then
    echo "FAILED: the application did not become ready on the old database" >&2
    docker logs "$APP" 2>&1 | tail -n 60 >&2 || true
    exit 1
fi

fail() { echo "FAILED: $*" >&2; docker logs "$APP" 2>&1 | tail -n 40 >&2; exit 1; }

echo "== checks"
q() { docker exec "$DB" psql -At -U predomics -d predomics -c "$1"; }

[ "$(q "SELECT count(*) FROM information_schema.columns WHERE table_name='jobs' AND column_name IN ('started_at','pid')")" = "2" ] \
    || fail "jobs.started_at / jobs.pid were not added"
[ "$(q "SELECT count(*) FROM pg_indexes WHERE indexname='ix_jobs_status'")" = "1" ] \
    || fail "index ix_jobs_status was not created"
if [ "$(q "SELECT to_regclass('alembic_version') IS NOT NULL")" = "t" ]; then
    echo "alembic revision: $(q 'SELECT version_num FROM alembic_version')"
    docker exec "$APP" python -m backend.app.migrate check \
        || fail "schema differs from the models after the upgrade"
fi
[ "$(q "SELECT count(*) FROM users WHERE email='upgrade@example.org'")" = "1" ] || fail "the old user row is gone"
[ "$(q "SELECT name FROM projects WHERE id='p00000000001'")" = "Old project" ] || fail "the old project row is gone"
# A job that was 'running' when the old version stopped must not stay running.
[ "$(q "SELECT status FROM jobs WHERE id='j00000000001'")" != "running" ] \
    || fail "the interrupted job is still marked running"
if docker logs "$APP" 2>&1 | grep -qE "Traceback|InFailedSqlTransaction"; then
    fail "errors in the application log during the upgrade"
fi

echo "OK: $IMAGE upgraded a v2.2.0 database"
