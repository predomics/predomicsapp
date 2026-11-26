# Architecture

A short map of the code for people who will change it. Operating an instance
is covered in [DEPLOYMENT.md](../DEPLOYMENT.md); the HTTP interface in the
[API guide](api-guide.md) and at `/api/docs`.

## The pieces

```
browser ──HTTPS──▶ nginx ──▶ FastAPI application (one process) ──▶ PostgreSQL
                              │   ├─ REST API  /api/*
                              │   ├─ websocket /ws/jobs/{project}/{job}
                              │   ├─ built Vue application (static files)
                              │   └─ job runner (bounded queue, in memory)
                              │          └─ worker subprocess per job ──▶ gpredomics (Rust)
                              └──▶ data volume: uploaded files, job directories, small JSON stores
```

| Part | Where | Notes |
|---|---|---|
| Frontend | `frontend/` | Vue 3, Vite, Pinia, vue-i18n (English and French), Plotly for charts. Built into `backend/app/static/` in the image. |
| API | `backend/app/routers/` | One module per area (auth, projects, datasets, analysis, data exploration, export, admin, …). Request and response models are Pydantic classes in `backend/app/models/`. |
| Business logic | `backend/app/services/` | No HTTP in here. Blocking work (pandas, files, outgoing HTTP) is called from the routers through `asyncio.to_thread`, never directly on the event loop. |
| Cross-cutting | `backend/app/core/` | settings (`config.py`), authentication and tokens (`security.py`, `deps.py`), rate limiting, error envelope, logging and request ids (`observability.py`), metrics. |
| Database | `backend/app/models/db_models.py`, `backend/alembic/` | SQLAlchemy 2 (async for requests, a sync session for the job runner). Schema changes are Alembic revisions; `backend/app/migrate.py` applies them. |
| Engine | [gpredomics](https://github.com/predomics/gpredomics) through [gpredomicspy](https://github.com/predomics/gpredomicspy) | Compiled into the image at the commits pinned in the `Dockerfile`. |
| Deployment | `Dockerfile`, `docker-compose*.yml`, `nginx/`, `helm/`, `scripts/` | See DEPLOYMENT.md. |

## One request, one job

1. **Upload.** A file is read with a size limit (`core/uploads.py`), its name
   is reduced to a safe single component and it is written under
   `<data>/datasets/<user>/` (`services/storage.py`). The database row
   (`dataset_files`) keeps the display name, the role (xtrain, ytrain, …) and
   the path.
2. **Launch.** `routers/analysis.py` checks that the files belong to the
   project, merges the parameters (built-in defaults ← administrator defaults ←
   request), writes `param.yaml` into the job directory and hands the job to
   `services/jobs.py`.
3. **Queue.** The job runner starts at most `PREDOMICS_MAX_CONCURRENT_JOBS`
   jobs (and per user, `PREDOMICS_MAX_JOBS_PER_USER`). Each job is a separate
   process, `python -m backend.app.services.worker`, so a crash of the engine
   cannot take the API down. The runner records the process id and start time,
   enforces the optional timeout, and kills the process group on cancel.
4. **Run.** The worker loads the matrices (`services/matrix_io.py`, aligned by
   sample and feature name), calls the engine (or a scikit-learn comparator in
   `services/sklearn_runner.py`) and writes `results.json` atomically, plus a
   small `summary.json` used by status polls.
5. **Follow.** The parent appends the worker's output to `console.log`. The
   browser asks for a one-time ticket and opens the websocket, which relays
   status, log lines and progress; the REST endpoints offer the same by
   polling.
6. **Read.** Results endpoints load the JSON off the event loop. Scoring new
   samples (`services/prediction.py`) reproduces the engine's formulas for each
   language and data type and is tested against the engine's own predictions.
7. **Restart.** At start-up `jobs.reconcile_orphaned_jobs()` puts waiting jobs
   back in the queue and marks jobs that were running as failed (or queues them
   again with `PREDOMICS_REQUEUE_INTERRUPTED`).

## Why a single process

Running jobs, the queue, one-time websocket tickets, login back-off counters,
rate-limit counters and a few caches live in the memory of the application
process, and files live on one volume. The application therefore runs as **one
process, one replica** (the Helm chart refuses more). Scaling is vertical —
more CPUs for more or bigger jobs — or by sending jobs to an external scitq
queue. Making it horizontally scalable would mean moving that state to a
shared store and the job runner to a separate worker service.

## Data

Fifteen tables: `users`, `projects`, `datasets`, `dataset_files`,
`project_datasets`, `dataset_versions`, `jobs`, `project_shares`,
`public_shares`, `project_comments`, `api_keys`, `webhooks`,
`password_reset_tokens`, `audit_logs`, and `schema_versions` (history of the
pre-Alembic migrations). Datasets belong to a user's library and are linked to
projects; jobs belong to a project.

On the data volume: `datasets/<user>/` (uploaded files), `projects/<project>/jobs/<job>/`
(`param.yaml`, `console.log`, `results.json`, `summary.json`), `backups/`
(archives made from the Admin page), `cache/` (species annotations fetched
from biobanks.gmt.bio), and small JSON files (signature collection,
administrator defaults, scitq settings, `.secret_key` when the signing key was
generated).

## Access control

Every project route goes through `core/deps.get_project_with_access`, which
resolves the caller's role (owner, editor, viewer through a share) or answers
404. Datasets are always filtered by owner. Administrator routes depend on
`get_admin_user`. Authentication is a JWT (`Authorization: Bearer`) or an API
key (`X-API-Key`); the token embeds a fingerprint of the password hash, so a
password change invalidates older tokens.

## Tests

| Suite | Where | Runs on |
|---|---|---|
| Backend | `backend/tests/` (pytest) | SQLite by default; PostgreSQL when `PREDOMICS_TEST_PG_URL` is set (required for the migration tests). The engine tests need the image. |
| Frontend | `frontend/src/__tests__/` (vitest) | jsdom |
| End to end | `tests/e2e/` (Playwright) | a throwaway stack; includes a real job and the Content-Security-Policy check |
| Upgrade | `scripts/check-upgrade.sh` | the image started on a v2.2.0 schema |

`make test`, `make test-e2e`, `make check-upgrade` — see
[CONTRIBUTING.md](../CONTRIBUTING.md).
