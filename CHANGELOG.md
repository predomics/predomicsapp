# Changelog

Notable changes per release. Versions are the git tags (`vX.Y.Z`); the same
number is in `backend/pyproject.toml` and the Helm chart's `appVersion`.
Detailed feature descriptions for past releases are in [ROADMAP.md](ROADMAP.md)
(its "Done" items), and the full history in `git log`.

Sections: **Added**, **Changed**, **Fixed**, **Security**, and — important for
operators — **Upgrade notes**.

## Unreleased

### Upgrade notes

- **Back up before upgrading** (`./scripts/backup.sh`). The first start
  migrates the database to Alembic revisions (the pre-Alembic state is
  converted in one transaction; on failure nothing is changed and the app does
  not start). There is no downgrade: the backup is the way back.
  `PREDOMICS_AUTO_MIGRATE=false` makes migration a separate step
  (`python -m backend.app.migrate`).
- **Everyone has to log in again once.** Sessions now last 8 hours instead of
  24 (`PREDOMICS_ACCESS_TOKEN_EXPIRE_MINUTES`) and are renewed while the web
  interface is in use. A password change ends earlier sessions.
- **An existing `demo@predomics.com` account that still has the password
  `demo` is deactivated at start-up** unless `PREDOMICS_SEED_DEMO=true`.
- **Results can differ for analyses with a non-default epsilon**: the value was
  not passed to the engine before and now is.
- **Jobs run with a `zscore` data type before this version cannot be used for
  prediction** (their training statistics were not stored): run them again.
  Scores and AUC computed by the application now match the engine exactly, so a
  validation AUC may differ slightly from the one shown before.
- **The websocket for live progress takes a one-time ticket**
  (`POST /api/auth/ws-ticket`, then `?ticket=`); `?token=` is no longer
  accepted. API clients that followed jobs over the websocket must be updated;
  polling `/logs` is unchanged.
- **Password-reset requests never return the token** outside debug mode.
  Without SMTP, administrators reset passwords.
- **The production proxy enforces a Content Security Policy** and no longer
  forwards a client-supplied `X-Forwarded-For`. If a load balancer sits in
  front of the bundled NGINX, set `NGINX_TRUSTED_PROXY` to its address. Custom
  NGINX snippets: `hsts.conf` is gone (HSTS is in `security-headers.conf`).
- **Base images are pinned by digest and Python packages are installed with
  hash checking.** A rebuilt image recreates the `db` container on the pinned
  PostgreSQL image (same major version; the data volume is kept).
- **Docker Compose 2.24 or newer is required.**
- **Published ports of the base stack are now bound to `127.0.0.1`.** To expose
  the base stack on the network set `PREDOMICS_BIND=0.0.0.0` — or, better, use
  the production stack.
- **The image runs as a non-root user** (`app`, uid 10001). Existing data
  volumes are re-owned automatically at the first start.
- **NGINX configuration moved** from `nginx/nginx.conf` to templates
  (`nginx/https/`, `nginx/http/`, `nginx/snippets/`). If you edited
  `nginx/nginx.conf`, port your changes to the template. Set `DOMAIN` in `.env`
  (and `NGINX_MODE=http` if you used the HTTP-only configuration).
- **The whole `.env` file now reaches the application.** Settings that were
  silently ignored before (SMTP, scitq, token lifetime) become effective.
  Remove the obsolete `PREDOMICS_SAMPLE_DIR`, `PREDOMICS_DEFAULT_*` and
  `MAX_CONCURRENT_JOBS` lines (use `PREDOMICS_MAX_CONCURRENT_JOBS`).
- **No demo account and no implicit administrator on new installations.** Set
  `PREDOMICS_ADMIN_EMAIL`; enable the demo account explicitly with
  `PREDOMICS_SEED_DEMO=true`. Existing databases keep their accounts.
- **The JWT secret can no longer be a known default.** If
  `PREDOMICS_SECRET_KEY` is unset or a shipped default, a random key is
  generated and stored in the data volume (users are logged out once).
- **Scheduled backups now run on a real cron schedule** (`BACKUP_SCHEDULE`,
  default 02:00 UTC) and exclude `cache/` and in-app backup archives.
- Helm: the image repository is `ghcr.io/predomics/predomicsapp`, generated
  secrets survive upgrades, the pod runs as non-root with a read-only root
  filesystem, and a PostgreSQL StatefulSet is now actually deployed when
  `postgresql.enabled=true`.

### Added — migrations, accounts, operations

- Alembic migrations with an explicit `migrate` command, status and schema
  check; `make check-upgrade` and a CI job that upgrade a v2.2.0 database.
- Optional email verification (`PREDOMICS_REQUIRE_EMAIL_VERIFICATION`),
  back-off on failed logins, session renewal, account creation by
  administrators (`POST /api/admin/users`).
- Per-user storage quota (`PREDOMICS_USER_QUOTA_MB`) and usage display;
  retention of old jobs and in-app backups (`PREDOMICS_JOB_RETENTION_DAYS`,
  `PREDOMICS_BACKUP_RETENTION_COUNT`), both off by default.
- Per-user job limit (`PREDOMICS_MAX_JOBS_PER_USER`); waiting jobs survive a
  restart; `PREDOMICS_REQUEUE_INTERRUPTED` re-runs interrupted ones.
- Prometheus metrics (`/metrics`, token-protected, not exposed by the proxy),
  JSON logs with request ids, optional Sentry.
- `docs/tutorial.md`, `docs/api-guide.md`, `docs/architecture.md`.
- `make test-e2e` runs the browser tests on its own throwaway stack behind the
  NGINX configuration, including a Content-Security-Policy check.
- `NGINX_TRUSTED_PROXY`, `NGINX_HTTP_PORT`/`NGINX_HTTPS_PORT`, `CERTBOT_DIR`,
  `BACKUP_DIR`, `PREDOMICS_STACK` (second stack on one host).

### Fixed — deployment

- Helm: the database wait container never succeeded when running as a non-root
  user without a passwd entry, so the application pod stayed in `Init`.
- NGINX: a client could choose its own address with `X-Forwarded-For` and
  escape the login rate limit; security headers were sent twice; HSTS was sent
  over plain HTTP; websocket URLs (with their credential) were written to the
  access log.

### Removed

- `docs/codebase-documentation.html` and its PDF (a February 2026 snapshot that
  no longer matched the code), replaced by `docs/architecture.md`.

### Added

- `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CITATION.cff`, this changelog,
  a README for the `wetlab_protocol` sample, a `Makefile`.
- Settings: `PREDOMICS_ADMIN_EMAIL`, `PREDOMICS_REGISTRATION_ENABLED`,
  `PREDOMICS_SEED_DEMO`, `PREDOMICS_PASSWORD_MIN_LENGTH`,
  `PREDOMICS_MAX_UPLOAD_MB`, `PREDOMICS_MAX_CONCURRENT_JOBS`,
  `PREDOMICS_MAX_THREADS_PER_JOB`, `PREDOMICS_JOB_TIMEOUT_MINUTES`,
  `PREDOMICS_ALLOW_MOCK_ENGINE`.
- `/health` reports the application version and the engine commits;
  `/health/ready` checks the database and the data volume.
- Development stack: `backend-test` and `frontend-test` runners; a `dev` image
  stage with the test tools.
- CI: frontend unit tests, image build and end-to-end tests on pull requests
  (including one real analysis job), checks of the Compose files, NGINX
  templates, Helm chart and shell scripts, dependency and image scans
  (informational), Dependabot.
- Releases: gated on the full CI run, published for amd64 and arm64.

### Changed

- The engine (gpredomics, gpredomicspy) is pinned to exact commits instead of
  the `main` branches.
- Image: locked Python dependencies are installed before the engine wheel;
  `xgboost` is replaced by the CPU-only `xgboost-cpu` build (about 600 MB
  smaller); build caches and download retries make builds survive a poor
  connection; Node 22.
- `scripts/setup.sh` only asks questions whose answers are used, and no longer
  writes NGINX files. `scripts/restore.sh` takes a safety backup first.

### Fixed

- Certificates renewed by certbot are now picked up by NGINX (periodic reload).
- Security headers were missing on `/assets/`.
- `scripts/ssl-init.sh` stored the real certificate under `<domain>-0001`.
- End-to-end tests pointed at a directory that no longer exists and passed
  without uploading anything.

## 2.2.0 — 2026-04-01

Metadata upload and regression support; Simulated Annealing, LASSO, ILS and Ant
Colony Optimization; scikit-learn comparison classifiers; clinical data
combination; new demo dataset (`wetlab_protocol`); `samples/` separated from
the user data directory; self-contained Docker build; interactive setup script.

## 2.1.0 — 2026-02-17

See ROADMAP.md.

## 2.0.0 and 1.0.0 — 2026-02-16

See ROADMAP.md.

## 1.3.0 — 2026-02-14

See ROADMAP.md.
