# PredomicsApp — Deployment and Administration Guide

For a first look on your own machine, the [README](README.md) quick start is
enough. This guide is for whoever installs and operates an instance for others.

## Table of Contents

1. [Requirements](#requirements)
2. [The three Compose files](#the-three-compose-files)
3. [Production stack](#production-stack)
4. [Accounts and administration](#accounts-and-administration)
5. [Settings](#settings)
6. [NGINX reverse proxy and TLS](#nginx-reverse-proxy-and-tls)
7. [Data, backup and restore](#data-backup-and-restore)
8. [Upgrades](#upgrades)
9. [Building the image, reproducibility](#building-the-image-reproducibility)
10. [Network access](#network-access)
11. [PostgreSQL](#postgresql)
12. [Kubernetes (Helm)](#kubernetes-helm)
13. [Monitoring and health checks](#monitoring-and-health-checks)
14. [Storage, quotas and retention](#storage-quotas-and-retention)
15. [Security checklist](#security-checklist)
16. [Troubleshooting](#troubleshooting)

---

## Requirements

| | |
|---|---|
| Docker | Engine 23+ (BuildKit) with **Compose 2.24+** — the Compose files use `!override` and optional `env_file` |
| CPU / memory | 2 CPUs and 4 GB at the very least; see [sizing](#sizing) |
| Disk | ~6 GB to build, 1.5 GB for the image, plus your data (results of large runs are tens of MB each) |
| Build time | 10–25 minutes for the first build (the Rust engine is compiled); a minute or two afterwards |
| Outbound network during the build | Docker Hub, `sh.rustup.rs`, `static.rust-lang.org`, `github.com`, `crates.io`, `pypi.org`, `files.pythonhosted.org`, `registry.npmjs.org` |
| Inbound (production) | ports 80 and 443; a DNS name pointing to the server |

Tagged releases are also published as a ready-made image,
`ghcr.io/predomics/predomicsapp:<version>` (amd64 and arm64), by the release
workflow. To use it instead of building, put `PREDOMICS_IMAGE=ghcr.io/predomics/predomicsapp:<version>`
in `.env` and start with `--no-build` (`docker compose … up -d --no-build`).

### Sizing

One analysis job loads the dataset in memory and uses up to
`PREDOMICS_MAX_THREADS_PER_JOB` threads. Plan for
`PREDOMICS_MAX_CONCURRENT_JOBS × PREDOMICS_MAX_THREADS_PER_JOB` CPUs and keep
that product within the container's CPU limit (`PREDOMICS_CPU_LIMIT`). The demo
datasets (about 2,000 features × 200–900 samples) run comfortably in 4 GB; raise
`PREDOMICS_MEMORY_LIMIT` for larger tables or several concurrent jobs. Data
exploration (ordination, networks) runs in the web process and competes with it
for the same CPUs.

---

## The three Compose files

| File | Purpose | Ports published on the host |
|---|---|---|
| `docker-compose.yml` | Base stack: app + PostgreSQL. Local use and evaluation. | app `127.0.0.1:8001`, PostgreSQL `127.0.0.1:5433` (change with `PREDOMICS_PORT`, `PREDOMICS_DB_PORT`, `PREDOMICS_BIND`) |
| `docker-compose.prod.yml` | **Override** used on top of the base file: NGINX, TLS, backups, limits. | 80 and 443 only |
| `docker-compose.dev.yml` | Separate development stack with hot reload and test runners (see [CONTRIBUTING.md](CONTRIBUTING.md)). | frontend `127.0.0.1:5173`, API `127.0.0.1:8000`, PostgreSQL `127.0.0.1:5432` |

All of them read an optional `.env` file in the repository root, and pass it to
the application container: every `PREDOMICS_*` line in `.env` is effective.

---

## Production stack

```bash
git clone https://github.com/predomics/predomicsapp.git && cd predomicsapp

# 1. Configure (interactive; writes .env with generated secrets, mode 600)
./scripts/setup.sh
#    …or by hand: cp .env.example .env and fill in DOMAIN, POSTGRES_PASSWORD,
#    PREDOMICS_SECRET_KEY, PREDOMICS_ADMIN_EMAIL

# 2. First HTTPS certificate (skip with NGINX_MODE=http)
./scripts/ssl-init.sh            # add --staging to rehearse without rate limits

# 3. Build and start
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

`make prod-up` is the same as step 3. The override adds:

- **NGINX** reverse proxy: TLS termination, security headers, WebSocket
  upgrade, upload limit, long timeouts;
- **Certbot**: renews the Let's Encrypt certificate (checks every 12 h); NGINX
  reloads every 6 h so the renewed certificate is actually served;
- **no published app or database ports** — only 80/443;
- **resource limits** on the app and the database, **log rotation** on every service;
- **scheduled backups** of the database and the data volume (cron, 02:00 UTC by default).

Required in `.env` for this stack: `DOMAIN`, `POSTGRES_PASSWORD`,
`PREDOMICS_SECRET_KEY`. Compose refuses to start with a clear message if one is
missing.

Then open `https://<DOMAIN>`, register with the administrator email, and read
the [security checklist](#security-checklist).

---

## Accounts and administration

**First administrator.** Set `PREDOMICS_ADMIN_EMAIL` to the email of the person
who will administer the instance. That account receives administrator rights
when it registers; if it already exists it is promoted at the next start. This
is the only bootstrap mechanism: an instance without `PREDOMICS_ADMIN_EMAIL`
(and without an existing administrator) has no administrator. Administrators
can promote other users from the **Admin** page.

Fallback, directly in the database:

```bash
docker exec -it predomics-db psql -U predomics -d predomics \
  -c "UPDATE users SET is_admin = TRUE WHERE email = 'you@example.org';"
```

**Registration.** Open by default: anyone who can reach the instance can create
an account. Two ways to restrict it:

- `PREDOMICS_REGISTRATION_ENABLED=false` closes self-registration.
  Administrators then create accounts from the Admin page
  (`POST /api/admin/users`).
- `PREDOMICS_REQUIRE_EMAIL_VERIFICATION=true` keeps registration open but a
  new account cannot log in until its owner has followed the link sent to the
  address. It needs SMTP: the application refuses to start with this setting on
  and no `PREDOMICS_SMTP_HOST`.

Passwords must have at least `PREDOMICS_PASSWORD_MIN_LENGTH` characters
(default 8).

**Sessions.** A login is valid for `PREDOMICS_ACCESS_TOKEN_EXPIRE_MINUTES`
(default 480, i.e. 8 hours). The web interface renews it while it is in use
(`POST /api/auth/refresh`); an idle session expires. Changing or resetting a
password ends every earlier session of that account.

**Failed logins.** After `PREDOMICS_LOGIN_THROTTLE_FREE_ATTEMPTS` (5) wrong
passwords for an account, or from one client address, each further failure
doubles the wait before the next attempt, up to
`PREDOMICS_LOGIN_THROTTLE_MAX_MINUTES` (15). The server answers `429` with a
`Retry-After` header meanwhile. A successful login clears the account's
counter; a restart clears all of them.

**Demo account.** Not created unless `PREDOMICS_SEED_DEMO=true`, which adds
`demo@predomics.com` / `demo` (a regular user). Instances installed before this
setting existed already have that account in their database: change its
password or deactivate it from the Admin page if the instance is exposed.

**What an administrator can do** (Admin page, or `/api/admin/*`): create,
list, deactivate, promote and delete users; reset a user's password
(`POST /api/admin/users/{id}/reset-password`); set the default analysis
parameters; read the audit log; create and restore in-app backups; configure
scitq.

### Email and password reset

With SMTP configured (`PREDOMICS_SMTP_*`, and `PREDOMICS_FRONTEND_URL` set to
the public URL — the production stack derives it from `DOMAIN`), "Forgot
password" emails a link valid for one hour.

Without SMTP, no email is sent and the response contains no token (it only does
in debug mode, for development): an administrator resets the password as shown
above.

How the connection to the mail server is made (each mode was tested against a
mail catcher):

| `PREDOMICS_SMTP_PORT` | `PREDOMICS_SMTP_TLS` | Connection |
|---|---|---|
| `587` or `25` (or any port but 465) | `true` (default) | plain connection upgraded with STARTTLS; fails if the server does not offer it |
| `465` | `true` | TLS from the first byte |
| any | `false` | no encryption — only for a relay on the same host or a trusted network |

The server certificate is always verified. If your mail server uses a
certificate from a private authority, mount the authority's certificate bundle
into the app container and set `SSL_CERT_FILE` to its path. A failed delivery
is written to the application log (`Email send failed: …`); the user still sees
the neutral "if the account exists…" message.

---

## Settings

All application settings are environment variables with the `PREDOMICS_`
prefix (defined in `backend/app/core/config.py`). Put them in `.env`.

### Application

| Variable | Default | Description |
|---|---|---|
| `PREDOMICS_SECRET_KEY` | *(generated)* | JWT signing key. If unset or a known default, a random key is generated and stored in `<data dir>/.secret_key`. Required explicitly by the production stack. Changing it logs everyone out. |
| `PREDOMICS_DATABASE_URL` | bundled PostgreSQL | `postgresql+asyncpg://user:password@host:5432/dbname` |
| `PREDOMICS_ADMIN_EMAIL` | *(empty)* | Account that is granted administrator rights. |
| `PREDOMICS_REGISTRATION_ENABLED` | `true` | `false`: only administrators create accounts. |
| `PREDOMICS_SEED_DEMO` | `false` | `true`: create `demo@predomics.com` / `demo` at start-up. |
| `PREDOMICS_PASSWORD_MIN_LENGTH` | `8` | Minimum password length. |
| `PREDOMICS_REQUIRE_EMAIL_VERIFICATION` | `false` | `true`: new accounts must confirm their email before logging in. Needs SMTP; the app refuses to start otherwise (except in debug mode). |
| `PREDOMICS_LOGIN_THROTTLE_ENABLED` | `true` | Back-off after repeated failed logins, per account and per client address. |
| `PREDOMICS_LOGIN_THROTTLE_FREE_ATTEMPTS` | `5` | Failures allowed before the back-off starts. |
| `PREDOMICS_LOGIN_THROTTLE_MAX_MINUTES` | `15` | Longest wait between two attempts. |
| `PREDOMICS_ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Session lifetime (8 hours; was 24 hours up to v2.2.0). Renewed while the web interface is in use. |
| `PREDOMICS_JWT_ALGORITHM` | `HS256` | JWT signature algorithm. |
| `PREDOMICS_CORS_ORIGINS` | `["http://localhost:5173","http://localhost:3000"]` | Allowed browser origins. **A JSON array** (in `.env`, wrap it in single quotes). The production stack sets `["https://<DOMAIN>"]`. |
| `PREDOMICS_FRONTEND_URL` | `http://localhost:5173` | Public base URL, used in password-reset emails. The production stack sets `https://<DOMAIN>`. |
| `PREDOMICS_MAX_UPLOAD_MB` | `500` | Per-file upload limit. Keep `NGINX_MAX_BODY` at least as large. |
| `PREDOMICS_MAX_CONCURRENT_JOBS` | `2` | Analysis jobs running at once; further jobs wait. |
| `PREDOMICS_MAX_THREADS_PER_JOB` | `0` | Upper bound on a job's threads (`0` = number of CPUs). |
| `PREDOMICS_JOB_TIMEOUT_MINUTES` | `0` | Stop a job after this long (`0` = never). |
| `PREDOMICS_MAX_JOBS_PER_USER` | `0` | Jobs one user may run at the same time (`0` = no per-user limit); the rest wait in the queue. |
| `PREDOMICS_REQUEUE_INTERRUPTED` | `false` | What happens to jobs that were running when the app stopped: `false` marks them failed ("interrupted by a server restart"), `true` queues them again from the start. Jobs that were still waiting are always queued again. |
| `PREDOMICS_USER_QUOTA_MB` | `0` | Storage per user (dataset files and job results), in MB. `0` = unlimited. See [Storage, quotas and retention](#storage-quotas-and-retention). |
| `PREDOMICS_JOB_RETENTION_DAYS` | `0` | Delete finished jobs older than this many days. `0` = keep forever. |
| `PREDOMICS_BACKUP_RETENTION_COUNT` | `0` | Keep only the newest N in-app backup archives. `0` = keep all. |
| `PREDOMICS_AUTO_MIGRATE` | `true` | Upgrade the database schema at start-up. `false`: refuse to start on an out-of-date database (run `python -m backend.app.migrate` yourself). |
| `PREDOMICS_LOG_FORMAT` | `text` | `json`: one JSON object per line, for log collectors. |
| `PREDOMICS_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `PREDOMICS_METRICS_TOKEN` | *(empty)* | Bearer token for `GET /metrics` (Prometheus). Empty = the endpoint answers 404. |
| `PREDOMICS_SENTRY_DSN` | *(empty)* | Error tracking; only used when the optional `sentry-sdk` package is installed in the image. |
| `PREDOMICS_API_DOCS` | `true` | `false`: do not serve `/api/docs`, `/api/redoc`, `/api/openapi.json`. |
| `PREDOMICS_ALLOW_MOCK_ENGINE` | `false` | `true`: return fake results when the engine is missing. For tests and UI development only — never in production. |
| `PREDOMICS_WEBHOOK_ALLOW_PRIVATE` | `false` | `true`: user webhooks may target private/intranet addresses. |
| `PREDOMICS_RATE_LIMIT_ENABLED` | `true` | Request rate limiting. |
| `PREDOMICS_RATE_LIMIT_API` | `100/minute` | General per-user limit (login, reset and upload have fixed stricter limits). |
| `PREDOMICS_DEBUG` | `false` | Development mode: verbose SQL logging, relaxed secret-key rules, reset tokens returned by the API. Never in production. |
| `PREDOMICS_DATA_DIR` | `data` (`/app/data` in the image) | Root of all persistent files. |
| `PREDOMICS_UPLOAD_DIR`, `PREDOMICS_PROJECT_DIR` | under the data dir | Upload and project/job directories. |
| `PREDOMICS_SAMPLES_DIR` | `samples` (`/app/samples` in the image) | Bundled demo datasets (read-only). |
| `PREDOMICS_SMTP_HOST`, `_PORT` (`587`), `_USER`, `_PASSWORD`, `_FROM`, `_TLS` (`true`) | *(empty)* | Outgoing email. Empty host = email disabled. |
| `PREDOMICS_SCITQ_SERVER`, `_TOKEN`, `_CONTAINER` | *(empty)* | Optional [scitq](https://github.com/gmtsciencedev/scitq) task queue for distributed execution. Empty = jobs run in the app container. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Proxies whose `X-Forwarded-*` headers are trusted (read by uvicorn). The production stack and the Helm chart set `*` because the app is then only reachable through the proxy. Leave the default when the app port is published directly. |

The image additionally sets `PREDOMICS_VERSION`, `PREDOMICS_ENGINE_REF` and
`PREDOMICS_ENGINEPY_REF` at build time; `/health` reports them.

### Compose-level variables (not read by the application)

| Variable | Default | Used by |
|---|---|---|
| `DOMAIN` | — (required in production) | NGINX `server_name`, certificate path, default CORS origin and frontend URL |
| `NGINX_MODE` | `https` | `https` or `http`: which template directory under `nginx/` is used |
| `NGINX_MAX_BODY` | `500M` | NGINX `client_max_body_size` |
| `NGINX_TRUSTED_PROXY` | `127.0.0.1` | address or CIDR of a proxy in front of NGINX whose `X-Forwarded-For`/`-Proto` are believed |
| `NGINX_HTTP_PORT`, `NGINX_HTTPS_PORT` | `80`, `443` | published ports of NGINX |
| `CERTBOT_DIR` | `./certbot` | host directory with the certificates and the ACME webroot |
| `BACKUP_DIR` | `./backups` | host directory that receives the scheduled and manual backups |
| `PREDOMICS_STACK` | `predomics` | container-name prefix (`<prefix>-web`, `-db`, `-nginx`, …); change it together with `docker compose -p <name>` to run a second stack on one host |
| `CERTBOT_EMAIL` | — | `scripts/ssl-init.sh` |
| `POSTGRES_PASSWORD` | `predomics` (base) / required (production) | bundled PostgreSQL and the default database URL |
| `PREDOMICS_CPU_LIMIT`, `PREDOMICS_MEMORY_LIMIT` | `2.0`, `4G` | resource limits of the app container (production) |
| `BACKUP_SCHEDULE` | `0 2 * * *` | cron expression (UTC) of the backup service |
| `BACKUP_RETENTION_DAYS` | `7` | backups older than this are deleted |
| `BACKUP_FAILURE_URL` | *(empty)* | URL fetched when a backup fails |
| `BACKUP_POST_HOOK` | *(empty)* | command run in the backup container after a successful backup |
| `PREDOMICS_PORT`, `PREDOMICS_DB_PORT`, `PREDOMICS_BIND` | `8001`, `5433`, `127.0.0.1` | published ports of the **base** stack |
| `PREDOMICS_IMAGE` | `predomics-app:latest` | image name built/used for the app |
| `GPREDOMICS_REF`, `GPREDOMICSPY_REF` | pinned in the `Dockerfile` | engine commits/tags compiled into the image |
| `DEV_BACKEND_PORT`, `DEV_FRONTEND_PORT`, `DEV_DB_PORT` | `8000`, `5173`, `5432` | published ports of the development stack |

---

## NGINX reverse proxy and TLS

The proxy configuration is generated at container start from a template:
`nginx/https/default.conf.template` (default) or `nginx/http/default.conf.template`
(`NGINX_MODE=http`), plus the shared files in `nginx/snippets/`. `${DOMAIN}` and
`${NGINX_MAX_BODY}` are substituted from `.env`. Nothing in the repository is
rewritten by the scripts; to customise the proxy, edit the template or snippets.

`${NGINX_TRUSTED_PROXY}` is substituted the same way.

It provides: HTTP→HTTPS redirect and the ACME challenge path; TLS 1.2/1.3;
HSTS (HTTPS mode only), `X-Frame-Options`, `X-Content-Type-Options`,
`Referrer-Policy`, `Permissions-Policy` and the Content Security Policy (also
on `/assets/`; the copies the application sets itself are dropped so each
header appears once); WebSocket upgrade for live job progress, logged without
its query string; a 7-day cache for hashed static assets; the upload limit;
600 s proxy timeouts; unlogged `/health` and `/health/ready`; `/metrics` is
never served to the outside (404).

**Client addresses.** NGINX passes the address of whoever connected to it and
discards any `X-Forwarded-For` the client sent — otherwise a client could
choose its own address and escape the login rate limit. If a load balancer or
institutional proxy sits in front of NGINX, set `NGINX_TRUSTED_PROXY` to its
address or CIDR: the address and scheme *it* reports are then used.

**Content Security Policy.** Enforced
(`nginx/snippets/security-headers.conf`): scripts, styles, fonts and network
connections are limited to the instance's own origin, inline scripts and
`eval` are refused, and the page cannot be framed. Inline *styles* are allowed
because the charting library positions elements with style attributes. The
end-to-end suite (`tests/e2e/csp.spec.mjs`) loads the Data and Results pages
under this exact policy and fails on any violation, so a frontend change that
needs a looser policy is caught before release. If you add an external
resource (a CDN font, an analytics script), extend the matching directive
there. Exported HTML reports are standalone files opened from disk and are not
covered by this policy.

Without the bundled NGINX (base stack, Kubernetes), the application sends
`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` and
`Permissions-Policy` itself but no Content Security Policy: add the header in
your own proxy or ingress with the value from
`nginx/snippets/security-headers.conf`. For ingress-nginx:

```yaml
ingress:
  annotations:
    nginx.ingress.kubernetes.io/configuration-snippet: |
      add_header Content-Security-Policy "<the policy string>" always;
```

**Certificates.** `./scripts/ssl-init.sh` obtains the first certificate
(temporary self-signed certificate → NGINX starts → real certificate). The
`certbot` service then renews it automatically; certificates live in
`./certbot/conf/`. Use `--staging` for trial runs.

**Plain HTTP mode** (`NGINX_MODE=http`) is for installations where TLS is
terminated by an institutional proxy or load balancer in front. Set
`PREDOMICS_CORS_ORIGINS` and `PREDOMICS_FRONTEND_URL` to the public `https://…`
URL in that case (`setup.sh` asks for it).

**Your own NGINX, without the bundled one.** Run only the base stack and proxy
to `127.0.0.1:8001`. Start from `nginx/https/default.conf.template` and
`nginx/snippets/locations.conf`, replacing `$predomics_app` by
`http://127.0.0.1:8001` and removing the `resolver` line. Keep
`X-Forwarded-Proto`, the WebSocket headers and a generous
`client_max_body_size`; set `X-Forwarded-For $remote_addr` (not
`$proxy_add_x_forwarded_for`, which forwards what the client claims); return
404 for `/metrics`; and set `FORWARDED_ALLOW_IPS` to your proxy's address as
seen by the container (the Docker gateway).

---

## Data, backup and restore

### Where the data is

| Volume | Content | If lost |
|---|---|---|
| `predomics_pg-data` | PostgreSQL: accounts, projects, dataset and job records, shares, API keys, audit log | everything is gone |
| `predomics_app-data` (`/app/data`) | uploaded files (`datasets/`), job results (`projects/`), caches (`cache/`), in-app backups (`backups/`), small JSON stores (signature zoo, templates, admin defaults), the generated key (`.secret_key`) | results and uploads are gone; database rows point to missing files |

Both are needed together: a backup of one without the other is not restorable
to a consistent state. `docker compose down` keeps them; `down -v` deletes them.

Nothing is cleaned up automatically: job results and uploads accumulate until
users delete them. Watch the free space of the Docker volume directory.

### Scheduled backups (production stack)

The `backup` service runs `scripts/backup-job.sh` on the `BACKUP_SCHEDULE` cron
expression (default every day at 02:00 UTC) and writes to `./backups/`:

- `db_<timestamp>.dump` — `pg_dump` custom format, verified with `pg_restore -l`;
- `data_<timestamp>.tar.gz` — the data volume without `cache/` and `backups/`.

Files are written under a temporary name and renamed when complete. Backups
older than `BACKUP_RETENTION_DAYS` are deleted. When a backup fails, the job
logs the reason, leaves `./backups/LAST_FAILURE`, the container becomes
*unhealthy* (`docker ps`) and `BACKUP_FAILURE_URL` is called if set.

```bash
docker logs predomics-backup            # last runs
cat backups/LAST_SUCCESS                # timestamp of the last good backup
# run one now:
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup backup-job.sh
```

**Copy the backups off the server.** `./backups` is on the same disk as the
data. Either sync that directory from the host (rsync, restic, your site's
backup agent) or set `BACKUP_POST_HOOK` to a command the backup container can
run. The data archive may contain `.secret_key`: protect backups like `.env`.

### Manual backup and restore

```bash
./scripts/backup.sh                      # same job, from the host (any stack)

./scripts/restore.sh                     # list available timestamps
./scripts/restore.sh 20260215_020000     # restore database + data
./scripts/restore.sh 20260215_020000 --db      # database only
./scripts/restore.sh 20260215_020000 --data    # data volume only
```

`restore.sh` validates the archives, takes a safety backup of the current
state, stops the app, restores, and starts the app again. **Rehearse a restore**
on a spare machine before you need one.

### In-app backups (Admin page)

Administrators can also create and restore an archive from the Admin page. It
is a convenience for moving a small instance, not a replacement for the
backups above: use the scheduled dumps as the reference.

---

## Upgrades

```bash
# 1. Back up first (database + data)
./scripts/backup.sh

# 2. Get the new version
git fetch --tags && git checkout vX.Y.Z      # or: git pull

# 3. Rebuild and restart
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps   # app "healthy"
curl -s https://<DOMAIN>/health                                      # new version
```

- **Back up first, every time.** The first start of a new version upgrades the
  database schema (see below). Schema upgrades only go forward: to return to
  the previous version, restore the backup taken in step 1 and check out the
  previous tag.
- **Running jobs are interrupted** by a restart and marked failed with an
  explanation; jobs still waiting in the queue start again by themselves. Wait
  for running jobs to finish, relaunch them afterwards, or set
  `PREDOMICS_REQUEUE_INTERRUPTED=true` to have them queued again automatically.
- Read [CHANGELOG.md](CHANGELOG.md) for settings that changed.

**Upgrading from an image that ran as root** (before the non-root user was
introduced): nothing to do. The container fixes the ownership of the data
volume at its first start and then runs as user `app` (uid 10001).

### Upgrading from v2.2.0 or earlier

Besides the steps above, expect the following on the first start:

| What changes | What you see | What to do |
|---|---|---|
| The database moves to Alembic migrations | the log shows the legacy migrations finishing and the baseline revision being stamped, then newer revisions being applied | nothing, apart from the backup beforehand |
| Sessions are signed differently and last 8 hours instead of 24 | every user has to log in again, once | tell your users; passwords are unchanged |
| The demo account is no longer created | an existing `demo@predomics.com` that still has the password `demo` is **deactivated** at start-up (a warning is logged) | set `PREDOMICS_SEED_DEMO=true` if you really want a public demo account |
| The hard-coded administrator rule is gone | existing administrators keep their rights | set `PREDOMICS_ADMIN_EMAIL` so the bootstrap is explicit |
| The application's ports are published on `127.0.0.1` only in the base stack | the instance is no longer reachable from other machines without the production stack | use `docker-compose.prod.yml`, or set `PREDOMICS_BIND=0.0.0.0` knowingly |
| The websocket for live job progress takes a one-time ticket instead of the session token | old browser tabs stop streaming until reloaded | reload the page |
| Password-reset requests no longer return the token when no email server is configured | "Forgot password" does nothing visible without SMTP | configure SMTP, or reset passwords from the Admin page |

Two changes affect **results**, not operations:

- **Epsilon.** Up to v2.2.0 the value entered for the prevalence threshold
  `epsilon` never reached the engine, which used its own default. It is now
  passed. Analyses run with a non-default epsilon give different models after
  the upgrade than before; analyses with the default are unchanged.
- **Prediction with z-score models.** Jobs run before the upgrade did not store
  the training statistics needed to score new samples with a `zscore` model.
  "Validate"/"Predict" on such a job answers with an explanation; run the
  analysis again to use it for prediction. Raw, prevalence and log models are
  unaffected, and their scores now match the engine's exactly (ties in the AUC
  included), so a validation AUC may differ slightly from the one shown before.

### Schema migrations

Schema changes are [Alembic](https://alembic.sqlalchemy.org/) revisions in
`backend/alembic/versions/`. At start-up the application brings the database
to the latest revision, under a PostgreSQL advisory lock (so two instances
starting together do not race):

- an **empty database** gets the current schema;
- a database **already managed by Alembic** gets the pending revisions;
- a database **from v2.2.0 or earlier** (tables present, no `alembic_version`
  table) is first brought to the last pre-Alembic state by the frozen legacy
  migrations, stamped at the baseline revision, and then upgraded like any
  other. This happens in one transaction: if anything fails, the database is
  left exactly as it was and the application does not start.

```bash
docker compose exec app python -m backend.app.migrate status   # current revision, pending ones
docker compose exec app python -m backend.app.migrate check    # exit 1 if the schema differs from the code
docker compose logs app | grep -iE "alembic|migrat"
```

To run migrations as a separate deployment step (several replicas of a
stateless front, change control), set `PREDOMICS_AUTO_MIGRATE=false`: the
application then refuses to start on an out-of-date database, and you run

```bash
docker compose run --rm app python -m backend.app.migrate
```

before starting the new version. There is no downgrade across the baseline;
restoring a backup is the way back. `make check-upgrade` (or
`./scripts/check-upgrade.sh <image>`) starts an image on a copy of the v2.2.0
schema and verifies the upgrade end to end; CI runs it on every pull request.

---

## Building the image, reproducibility

The `Dockerfile` has three build stages (frontend with Node, engine with Rust,
Python runtime) plus an optional `dev` stage with the test tools.

| Input | How it is fixed |
|---|---|
| gpredomics, gpredomicspy | **exact commits**, `GPREDOMICS_REF` / `GPREDOMICSPY_REF` in the `Dockerfile` (also in the Compose `build.args`). The built commits are stored in the image (`/app/engine/*.sha`, image labels) and shown by `/health` (`engine_ref`, `enginepy_ref`). |
| Rust toolchain | `RUST_TOOLCHAIN` (1.88.0) |
| maturin | `MATURIN_VERSION` |
| Python packages | `backend/requirements.lock`: exact versions **with SHA-256 hashes**, installed with `pip install --require-hashes` (a tampered or substituted package fails the build). `make lock` recomputes the hashes after a version change. |
| JavaScript packages | `frontend/package-lock.json` (`npm ci`) |
| Base images | **pinned by digest** in the `Dockerfile` and the Compose files (`python:3.11-slim@sha256:…`, `node:22-alpine@…`, `postgres:16-alpine@…`, `nginx:1.27-alpine@…`, `certbot/certbot:v2.11.0@…`). Dependabot proposes digest updates. |
| GitHub Actions | pinned by commit SHA in `.github/workflows/` |

Known gaps, so that nobody assumes more than is true:

- the engine commits should be replaced by **release tags** once gpredomics and
  gpredomicspy are tagged for the versions this app needs;
- gpredomicspy does not commit its `Cargo.lock`, so the Rust crates are
  resolved at build time (`maturin build --locked` is not possible yet);
- system packages installed with `apt-get` inside the image are not pinned;
- the image built by the release workflow is rebuilt from the cached layers of
  the tested build rather than being the very same image.

To build against another engine version (for testing):

```bash
GPREDOMICS_REF=<commit-or-tag> GPREDOMICSPY_REF=<commit-or-tag> docker compose build app
```

The image runs as the unprivileged user `app` (uid 10001). Its entrypoint
starts as root only to fix the ownership of the data volume, then drops
privileges.

---

## Network access

**At run time** the application needs no internet access, with two exceptions:

| What | Destination | Data sent | Without it |
|---|---|---|---|
| Annotation of MSP features (taxonomy, functional traits) in data exploration, enrichment and insights | `https://biobanks.gmt.bio/msp/` | the MSP identifiers (`msp_0001`, …) of the dataset | no annotations; nothing else is affected. Answers are cached in `data/cache/msp_annotations.json`; failed lookups are retried later. |
| Exported HTML reports | `https://cdn.plot.ly` (loaded by the *reader's* browser) | none | charts in the exported file do not render offline |

Other outbound traffic only if you configure it: SMTP, user-defined webhooks
(private addresses are refused unless `PREDOMICS_WEBHOOK_ALLOW_PRIVATE=true`),
scitq, Let's Encrypt, `BACKUP_FAILURE_URL`.

To clear the annotation cache: delete `cache/msp_annotations.json` in the data
volume and restart the app.

---

## PostgreSQL

### Changing the bundled database password

The database volume keeps the password it was initialised with; editing
`POSTGRES_PASSWORD` afterwards makes the app fail to connect. Change it inside
PostgreSQL first, then in `.env`:

```bash
docker exec -it predomics-db psql -U predomics -d predomics -c "ALTER USER predomics PASSWORD 'new-password';"
```

### External database

Set `PREDOMICS_DATABASE_URL=postgresql+asyncpg://user:password@db-host:5432/predomics`
in `.env`. The bundled `db` container still starts (unused), and the scheduled
backup dumps the bundled database only: back up the external one with your
own tooling.

### Suggested PostgreSQL settings (4–8 GB server)

```ini
shared_buffers = 1GB
effective_cache_size = 3GB
work_mem = 16MB
maintenance_work_mem = 256MB
max_connections = 100
```

---

## Kubernetes (Helm)

A chart is provided in [`helm/predomicsapp/`](helm/predomicsapp/). It deploys
the app as **one replica** (the chart refuses more: job state is in the
process and the data volume is ReadWriteOnce) and, by default, a small
single-instance PostgreSQL. The chart is rendered and linted in CI and was
installed on a local single-node cluster (kind, Kubernetes 1.32) for this
release: the pod became ready as a non-root user with a read-only root
filesystem, ran an analysis, kept its data across pod restarts, and
`helm upgrade` kept the generated secrets. It has not been exercised on a
production cluster, with an ingress controller, or with a network storage
class: test it on yours.

```bash
# Defaults: app + bundled PostgreSQL, no ingress
helm install predomics ./helm/predomicsapp --set env.PREDOMICS_ADMIN_EMAIL=you@example.org

# With an ingress and TLS (cert-manager)
helm install predomics ./helm/predomicsapp \
  --set env.PREDOMICS_ADMIN_EMAIL=you@example.org \
  --set ingress.enabled=true \
  --set ingress.host=predomics.example.com \
  --set ingress.tls.enabled=true \
  --set-string ingress.annotations."cert-manager\.io/cluster-issuer"=letsencrypt-prod

# External database instead of the bundled one
helm install predomics ./helm/predomicsapp \
  --set postgresql.enabled=false \
  --set externalDatabase.url="postgresql+asyncpg://user:pass@host:5432/predomics"

helm upgrade predomics ./helm/predomicsapp -f my-values.yaml
```

| Value | Default | Description |
|---|---|---|
| `image.repository` | `ghcr.io/predomics/predomicsapp` | image published by the release workflow |
| `image.tag` | chart `appVersion` | pin a version; avoid `latest` |
| `replicaCount` | `1` | must stay 1 |
| `resources.limits` | 2 CPU / 4Gi | size together with `env.PREDOMICS_MAX_CONCURRENT_JOBS` × `PREDOMICS_MAX_THREADS_PER_JOB` |
| `persistence.size` | `20Gi` | data volume (`existingClaim` to bring your own) |
| `postgresql.enabled` | `true` | bundled single-instance PostgreSQL (no HA, no backups) |
| `externalDatabase.url` | `""` | used when `postgresql.enabled=false` |
| `env.*` | see `values.yaml` | application settings (ConfigMap) |
| `publicUrl` | from `ingress.host` | sets CORS origin and frontend URL |
| `ingress.annotations` | body size 500m, timeouts 600 s | defaults for ingress-nginx |
| `secrets.existingSecret` | `""` | bring your own Secret (`secret-key`, optionally `metrics-token`, and `postgres-password` or `database-url`) |
| `secrets.metricsToken` | `""` | bearer token enabling `GET /metrics` |
| `metrics.podAnnotations` | `false` | add `prometheus.io/*` scrape annotations to the pod |

**Secrets.** If you do not provide them, the JWT key and the database password
are generated at the first install, **kept across upgrades**, and kept on
`helm uninstall` (as are the data volumes). To manage them yourself:

```bash
kubectl create secret generic predomics-secrets \
  --from-literal=secret-key=$(openssl rand -hex 32) \
  --from-literal=postgres-password=$(openssl rand -hex 16)
helm install predomics ./helm/predomicsapp --set secrets.existingSecret=predomics-secrets
```

**Security context.** The pod runs as uid 10001 with a read-only root
filesystem (writable: the data volume and `/tmp`), no privilege escalation and
no capabilities.

**Metrics and policy headers.** `/metrics` answers only to the bearer token, but
an ingress routes it like any other path: scrape the Service from inside the
cluster and, if your ingress controller allows it, deny the path there. The
application does not send a Content Security Policy itself; add it at the
ingress (see [NGINX reverse proxy and TLS](#nginx-reverse-proxy-and-tls)).

**Schema upgrades.** The pod migrates the database when it starts
(`PREDOMICS_AUTO_MIGRATE: "true"`); the start-up probe allows five minutes.
Back up the database before `helm upgrade`.

**Not included:** backups (schedule `pg_dump` and a volume snapshot with your
cluster's tooling), NetworkPolicies, and a PodDisruptionBudget.

---

## Monitoring and health checks

| Endpoint | Meaning |
|---|---|
| `GET /health` | Liveness: the API process answers. Returns the app version, `gpredomicspy_available`, and the engine commits. |
| `GET /health/ready` | Readiness: additionally checks the database connection and the data volume (free space). HTTP 503 with details when degraded. |

```json
{
  "status": "ok",
  "version": "2.2.0",
  "gpredomicspy_available": true,
  "engine_version": "0.1.0",
  "engine_ref": "faff348892ca…",
  "enginepy_ref": "d963ec310be7…",
  "scitq_enabled": false
}
```

`gpredomicspy_available` must be `true` on a production instance: it means the
compiled engine loaded. If it is `false`, analyses are refused (they are not
replaced by mock results unless `PREDOMICS_ALLOW_MOCK_ENGINE=true`).

The image's `HEALTHCHECK` and the Compose health check call `/health/ready`;
`docker compose ps` shows the result. The Helm chart uses `/health` for
start-up and liveness and `/health/ready` for readiness.

```bash
curl -sf https://<DOMAIN>/health/ready | jq .
docker compose logs --since 1h app
```

### Logs

Logs go to the container's standard output (rotated by Docker in the
production stack: 10 MB × 5 files per service). Every request gets an id,
returned in the `X-Request-ID` response header and written on each log line it
causes — quote it when reporting a problem. `PREDOMICS_LOG_FORMAT=json` writes
one JSON object per line for collectors such as Loki or Elasticsearch;
`PREDOMICS_LOG_LEVEL` sets the verbosity.

### Metrics (Prometheus)

Set `PREDOMICS_METRICS_TOKEN` to a long random value to enable `GET /metrics`;
without it the endpoint answers 404. The bundled NGINX never serves `/metrics`
to the outside: scrape the application container directly, from inside the
Docker network or the cluster.

```yaml
# prometheus.yml
scrape_configs:
  - job_name: predomics
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials: "<PREDOMICS_METRICS_TOKEN>"
    static_configs:
      - targets: ["predomics-web:8000"]     # Kubernetes: <release>-predomicsapp:80
```

| Metric | Meaning |
|---|---|
| `predomics_http_requests_total{method,route,status}` | requests served |
| `predomics_http_request_duration_seconds{method,route}` | request duration (histogram) |
| `predomics_jobs{status}` | jobs in the database by status |
| `predomics_jobs_running`, `predomics_jobs_queued` | the job runner right now |
| `predomics_data_disk_free_bytes`, `predomics_data_disk_total_bytes` | the data volume |
| `predomics_app_info{version}` | running version |

Worth alerting on: `/health/ready` not 200, `predomics_data_disk_free_bytes`
low, `predomics_jobs_queued` staying above zero for hours, a rising rate of
`status="5xx"` requests, and the backup container turning unhealthy.

### Error tracking (optional)

`PREDOMICS_SENTRY_DSN` sends unhandled errors to Sentry or a compatible
service. The `sentry-sdk` package is not in the image: add it in a derived
image (`FROM ghcr.io/predomics/predomicsapp:<version>` then
`RUN pip install sentry-sdk`). Without the package the setting is ignored.

---

## Storage, quotas and retention

Everything a user stores counts towards their usage: the files of their
dataset library (including files kept for older versions of a dataset) and the
results, logs and parameters of the jobs in the projects they own. A user sees
their usage on the Profile page (`GET /api/auth/me/usage`).

- **Quota.** `PREDOMICS_USER_QUOTA_MB` caps that usage. An upload, or loading a
  demo dataset, that would exceed it is refused with a clear message; nothing
  already stored is touched, and jobs on data already uploaded still run (their
  results count towards the usage afterwards). `0` (default) means no limit.
- **Job retention.** `PREDOMICS_JOB_RETENTION_DAYS` deletes finished jobs
  (completed or failed) older than that many days — their results and logs, and
  their entry in the project. Running and queued jobs are never touched.
  Models added to the Signature Zoo are separate copies and stay.
- **In-app backup retention.** `PREDOMICS_BACKUP_RETENTION_COUNT` keeps only
  the newest N archives created from the Admin page.

Both retention rules are off by default: nothing is deleted automatically
unless you set them. When on, they run once a day. See what a run would remove
before enabling them, or trigger one by hand:

```bash
# what would be deleted (nothing is)
curl -s -X POST "https://<DOMAIN>/api/admin/retention/run?dry_run=true"  -H "Authorization: Bearer <admin token>" | jq .
# do it now
curl -s -X POST "https://<DOMAIN>/api/admin/retention/run?dry_run=false" -H "Authorization: Bearer <admin token>" | jq .
```

The scheduled backups in `./backups` have their own retention
(`BACKUP_RETENTION_DAYS`, see [Scheduled backups](#scheduled-backups-production-stack)).

---

## Security checklist

Before giving the URL to users:

- [ ] `PREDOMICS_SECRET_KEY` and `POSTGRES_PASSWORD` are long random values (`setup.sh` generates them); `.env` is mode 600 and not in git.
- [ ] `PREDOMICS_ADMIN_EMAIL` is set and that account is registered with a strong password.
- [ ] `PREDOMICS_SEED_DEMO` is not `true`; on an older database, the `demo@predomics.com` account is deactivated or has a new password.
- [ ] `PREDOMICS_REGISTRATION_ENABLED=false` unless open sign-up is intended; with open sign-up, consider `PREDOMICS_REQUIRE_EMAIL_VERIFICATION=true` and a `PREDOMICS_USER_QUOTA_MB`.
- [ ] If a proxy or load balancer sits in front of the bundled NGINX, `NGINX_TRUSTED_PROXY` is set to its address (otherwise every user shares one rate-limit bucket).
- [ ] `PREDOMICS_METRICS_TOKEN`, if set, is long and random, and `/metrics` is not reachable from outside (`curl -s -o /dev/null -w '%{http_code}' https://<DOMAIN>/metrics` prints `404`).
- [ ] `PREDOMICS_DEBUG` and `PREDOMICS_ALLOW_MOCK_ENGINE` are unset.
- [ ] Only ports 80/443 are reachable from outside (`docker ps`: no `0.0.0.0:8001` or `:5433`).
- [ ] HTTPS works and `http://` redirects to it.
- [ ] A backup has run (`backups/LAST_SUCCESS`), is copied off the server, and a restore has been rehearsed.
- [ ] SMTP is configured, or users know to ask an administrator for password resets.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

---

## Troubleshooting

**The build fails on a download** (`tls handshake eof`, `Read timed out`,
`DeadlineExceeded`). Network hiccup: run the same build command again; completed
steps are cached, and pip, cargo and git retry by themselves.

**"port is already allocated".** Another program uses 8001 or 5433. Set
`PREDOMICS_PORT` / `PREDOMICS_DB_PORT` in `.env` (base stack), or stop the other
program. For the development stack: `DEV_BACKEND_PORT`, `DEV_FRONTEND_PORT`,
`DEV_DB_PORT`.

**The app container restarts or is "unhealthy".**

```bash
docker compose logs --tail 100 app
curl -s http://localhost:8001/health/ready     # which check fails?
docker compose exec db pg_isready -U predomics
```

- `password authentication failed`: `POSTGRES_PASSWORD` differs from the one the
  database volume was created with (see [PostgreSQL](#postgresql)).
- `required variable … is missing a value`: fill it in `.env`.
- A pydantic error mentioning `cors_origins`: the value must be a JSON array,
  e.g. `PREDOMICS_CORS_ORIGINS='["https://predomics.example.com"]'`.

**`gpredomicspy_available` is `false`.** The engine wheel did not load:
`docker compose exec app python -c "import gpredomicspy"` shows why. Rebuild
without cache for the engine stage if the build was interrupted:
`docker compose build --no-cache app`.

**Everyone was logged out after a restart.** The JWT key changed: either
`PREDOMICS_SECRET_KEY` was edited, or it was never set and the data volume
(which holds the generated `.secret_key`) was replaced.

**Uploads fail with 413.** Raise `NGINX_MAX_BODY` and `PREDOMICS_MAX_UPLOAD_MB`
together, then recreate the containers (`up -d`).

**Old accounts are still there after reinstalling.** The database volume
persisted. `docker compose down -v` erases it (and all results).

**Job stuck in "running" after a restart.** Jobs do not survive a restart; the
application marks interrupted jobs as failed at start-up. Relaunch them.

### API documentation

FastAPI serves interactive API docs:

- **Swagger UI**: `https://<DOMAIN>/api/docs`
- **ReDoc**: `https://<DOMAIN>/api/redoc`
- **OpenAPI JSON**: `https://<DOMAIN>/api/openapi.json`
