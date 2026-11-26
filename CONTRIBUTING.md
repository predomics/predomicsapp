# Contributing to PredomicsApp

This guide gets a developer from a fresh clone to a running development stack
and passing tests, and explains how the code is organised. Deployment is in
[DEPLOYMENT.md](DEPLOYMENT.md).

## How it fits together

```
browser ── Vue 3 SPA (frontend/) ──HTTP /api, WebSocket /ws──▶ FastAPI app (backend/app)
                                                                 │
                    routers/  request handling, access control  ─┤
                    services/ data analysis, storage, exports   ─┤
                    services/jobs.py  bounded job queue (threads)│
                                   └─ subprocess: services/worker.py
                                          └─ gpredomicspy (Rust engine) or scikit-learn
                                                                 │
                     PostgreSQL (accounts, projects, job records)┘
                     data volume (uploads, results.json, logs, caches)
```

- **`backend/app/routers/`** — one module per API area (`auth`, `projects`,
  `datasets`, `analysis`, `data_explore`, `export`, `admin`, …). Routers check
  access (`core/deps.py`: `get_current_user`, `get_project_with_access`) and
  delegate to services. Heavy or blocking work must not run on the event loop:
  call it through `asyncio.to_thread` (see `data_explore.py`).
- **`backend/app/services/`** — the actual work. `jobs.py` runs analyses: each
  job is a subprocess (`worker.py`) so an engine crash cannot take the API
  down; at most `PREDOMICS_MAX_CONCURRENT_JOBS` run at once and interrupted
  jobs are marked failed at start-up. `engine.py` writes the engine's
  `param.yaml`; `sklearn_runner.py` runs the comparison models; `storage.py`,
  `results_io.py`, `matrix_io.py` read and write files.
- **`backend/app/core/`** — settings (`config.py`, environment variables with
  the `PREDOMICS_` prefix), database sessions, security, rate limiting, errors.
- **`backend/app/models/`** — SQLAlchemy tables (`db_models.py`) and Pydantic
  request/response schemas (`schemas.py`, `auth_schemas.py`).
- **`backend/app/main.py`** — application assembly. Schema upgrades are
  Alembic revisions (`backend/alembic/`), applied by `backend/app/migrate.py`.
- **`frontend/src/`** — `views/` (pages; `DataTab`, `ParametersTab` and
  `ResultsTab` are the three tabs of a project), `components/`, `stores/`
  (Pinia), `composables/`, `data/parameterDefs.js` (the single description of
  every analysis parameter: default, bounds, help text), `i18n/locales/`.
- The app is **single-process by design**: job state, caches and rate-limit
  counters live in the API process. Do not add `--workers`.

[docs/architecture.md](docs/architecture.md) follows one request and one job
through the code.

The engine lives in two other repositories,
[gpredomics](https://github.com/predomics/gpredomics) (Rust) and
[gpredomicspy](https://github.com/predomics/gpredomicspy) (Python bindings);
the image builds them at the commits pinned in the `Dockerfile`.

## Development stack

Requirements: Docker with Compose 2.24+. Nothing else is needed on the host
(Node.js only for the end-to-end tests).

```bash
make dev        # = docker compose -f docker-compose.dev.yml up -d --build
```

| What | Where |
|---|---|
| Frontend with hot reload (Vite) | <http://localhost:5173> |
| Backend API, auto-reloading on changes in `backend/app` | <http://localhost:8000> — docs at <http://localhost:8000/api/docs> |
| PostgreSQL | `localhost:5432`, user/password/database `predomics` |

The first `make dev` builds the backend image, including the Rust engine
(10–25 minutes); afterwards only changed layers are rebuilt. `./backend`,
`./data` and `./samples` are bind-mounted, so code changes apply immediately
and user data lands in `./data` (git-ignored). The stack runs with
`PREDOMICS_DEBUG=true` and creates the demo account `demo@predomics.com` /
`demo`. To get an administrator, start it with your email:
`PREDOMICS_ADMIN_EMAIL=you@example.org make dev`, then register.

Ports taken? `DEV_FRONTEND_PORT=5174 DEV_BACKEND_PORT=8010 DEV_DB_PORT=5442 make dev`.

`make dev-down` stops it. `docker compose -f docker-compose.dev.yml down -v`
also drops the development database.

### Without Docker (frontend only)

Running the backend outside Docker requires building gpredomicspy yourself
(Rust toolchain + `maturin develop` in a gpredomicspy checkout next to a
gpredomics checkout); most contributors should not need it. The frontend alone
is easy, against any running backend:

```bash
cd frontend
npm ci
VITE_API_TARGET=http://localhost:8001 npm run dev    # 8001 = base stack, 8000 = dev stack
```

## Tests

Four suites, all run in Docker (nothing to install but Docker) and all run in
CI on every pull request.

### 1. Backend (pytest)

```bash
make test-backend
# = docker compose -f docker-compose.dev.yml run --rm --build backend-test
# one file / one test:
docker compose -f docker-compose.dev.yml run --rm backend-test \
  python -m pytest tests/test_api.py -k "TestAuth" -q -p no:cacheprovider
```

This runs in the `dev` image, so it has the real engine. By default the tests
use a throw-away SQLite database and temp directories
(`backend/tests/conftest.py`).

**On PostgreSQL.** Set `PREDOMICS_TEST_PG_URL` to run the whole suite on
PostgreSQL instead; the migration tests (Alembic, upgrade of a pre-Alembic
database) only run then. The tests create a scratch database next to the one
named in the URL and drop it at the end, so the user needs `CREATEDB`:

```bash
docker compose -f docker-compose.dev.yml up -d db
docker compose -f docker-compose.dev.yml run --rm \
  -e PREDOMICS_TEST_PG_URL=postgresql+asyncpg://predomics:predomics@db:5432/predomics \
  backend-test
```

Without Docker and without the engine (what the CI `backend-test` job does),
with Python 3.11 on Linux:

```bash
cd backend
python3.11 -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install pytest pytest-asyncio pytest-cov aiosqlite
PYTHONPATH=. python -m pytest tests/ -q
```

Here jobs use the mock engine (`conftest.py` sets
`PREDOMICS_ALLOW_MOCK_ENGINE=true`), so engine behaviour is *not* tested —
that is what `make test-backend` and the end-to-end job test are for. (The lock
only lists Linux wheels; on macOS or Windows use the Docker commands.)

### 2. Frontend (vitest)

```bash
make test-frontend
# = docker compose -f docker-compose.dev.yml run --rm frontend-test
# or, with Node 22 on the host:
cd frontend && npm ci && npm test
```

### 3. End to end (Playwright)

```bash
make build        # the image to test (predomics-app:latest), if not built yet
make test-e2e
```

`make test-e2e` starts its **own** throwaway stack (database, application,
and the NGINX proxy from `nginx/`), runs a real browser against it, and removes
everything afterwards. It never touches your running instance or its database.
The suite registers a user, creates a project, uploads a file, launches a small
real analysis, and (`tests/e2e/csp.spec.mjs`) checks that the Data and Results
pages work under the enforced Content Security Policy.

To test another image: `make test-e2e E2E_IMAGE=predomics-app:dev`. To run the
suite against an instance that already exists (it will create
`e2e_<timestamp>@test.com` accounts there, so use a disposable one; needs
Node.js): `make test-e2e-url BASE_URL=http://localhost:8001`.

### 4. Upgrade

```bash
make check-upgrade        # = ./scripts/check-upgrade.sh predomics-app:latest
```

Starts the image on a database with the schema of the previous release
(`.github/fixtures/schema_v2.2.0.sql`, no user data) and checks that it
migrates and still serves the old rows. Run it whenever you add an Alembic
revision.

### Lint

```bash
make lint            # ruff (backend, configured in backend/pyproject.toml)
cd frontend && npm run lint      # eslint (or in the frontend-test container)
```

### Dependencies

Python dependencies are pinned with hashes in `backend/requirements.lock`
(installed with `pip install --require-hashes`). To change one: edit the
version, run `make lock` (rewrites the hashes from PyPI), rebuild and test.
Base images in the `Dockerfile` and Compose files are pinned by digest;
Dependabot proposes updates for images, GitHub Actions and npm packages.

## Conventions

- **Translations.** Every user-visible string goes through `$t(...)`; add the
  key to **both** `frontend/src/i18n/locales/en.json` and `fr.json`.
- **Analysis parameters.** Add or change them in three places together:
  `frontend/src/data/parameterDefs.js` (UI + help text),
  `backend/app/models/schemas.py` (`RunConfig`, with bounds), and
  `backend/app/services/engine.py` (written to `param.yaml`).
- **Request and response bodies** are Pydantic models, not `dict`.
- **Access control.** Any endpoint that touches a project, dataset or job
  checks the caller's access to *that object* (see `get_project_with_access`);
  add a test that another user gets 403/404.
- **Settings.** New settings go in `backend/app/core/config.py` *and* in the
  table of [DEPLOYMENT.md](DEPLOYMENT.md#settings) and `.env.example`. A setting
  nothing reads should be removed, not documented.
- **Database changes.** Change the model in `models/db_models.py`, then add an
  Alembic revision (`backend/alembic/README.md` has the commands and the
  conventions). Run the migration tests on PostgreSQL
  (`PREDOMICS_TEST_PG_URL`, see Tests) and `make check-upgrade`. Never edit a
  revision that has been released.
- **Dependencies.** Python: loosen/tighten ranges in `backend/pyproject.toml`,
  then regenerate `backend/requirements.lock` (instructions at the top of that
  file) and run the tests in the image. JavaScript: `npm install <pkg>` in
  `frontend/` and commit `package-lock.json`.
- **Engine version.** To move to newer engine code, change `GPREDOMICS_REF` and
  `GPREDOMICSPY_REF` in the `Dockerfile` *and* the same defaults in
  `docker-compose.yml` / `docker-compose.dev.yml`, rebuild, and run all three
  suites.
- **Commits.** Short imperative subject with a type prefix as in the history
  (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`).

## Pull requests

1. Branch from `main`.
2. Make the change with tests; update the docs it makes stale (README,
   DEPLOYMENT, this file) and add a line under **Unreleased** in
   [CHANGELOG.md](CHANGELOG.md) — with an *Upgrade note* if operators must do
   something.
3. `make test` locally; `make check-config` if you touched Compose, NGINX or
   Helm files.
4. Open the pull request. CI runs the backend and frontend tests, validates
   the deployment files, builds the image and runs the end-to-end tests.

## Releases (maintainers)

1. Set the new version in `backend/pyproject.toml` and `appVersion` in
   `helm/predomicsapp/Chart.yaml`; move the **Unreleased** changelog entries
   under a new heading; merge to `main`.
2. Tag that commit: `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. The release workflow checks that the tag is on `main` and matches those two
   files, runs the whole CI, then publishes
   `ghcr.io/predomics/predomicsapp:X.Y.Z` (and `:latest`) for amd64 and arm64.

## Reporting bugs

Open an issue at <https://github.com/predomics/predomicsapp/issues> with the
version shown by `/health`, what you did, what you expected, and the relevant
lines of `docker compose logs app`. Security problems: see
[SECURITY.md](SECURITY.md).
