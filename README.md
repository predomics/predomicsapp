# PredomicsApp Web

Modern web application for [gpredomics](https://github.com/predomics/gpredomics) — sparse, interpretable ML model discovery for omics data.

**Architecture:** FastAPI (Python) backend + Vue.js frontend, powered by [gpredomicspy](https://github.com/predomics/gpredomicspy).

## Quick Start

### Backend (development)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Optional: install gpredomicspy for real ML engine
# pip install ../gpredomicspy  # or: cd ../gpredomicspy && maturin develop

uvicorn app.main:app --reload
```

API docs at http://localhost:8000/docs

### Frontend (development)

```bash
cd frontend
npm install
npm run dev
```

Frontend at http://localhost:5173

### Docker (production)

```bash
docker compose up --build
```

App at http://localhost:8000

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check + engine status |
| POST | `/api/projects/` | Create project |
| GET | `/api/projects/` | List projects |
| GET | `/api/projects/{id}` | Get project |
| DELETE | `/api/projects/{id}` | Delete project |
| POST | `/api/projects/{id}/datasets` | Upload dataset |
| POST | `/api/analysis/{id}/run` | Launch analysis |
| GET | `/api/analysis/{id}/jobs/{jid}` | Job status |
| GET | `/api/analysis/{id}/jobs/{jid}/detail` | Full results |

## Project Structure

```
predomicsapp-web/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app
│   │   ├── core/config.py   # Settings
│   │   ├── models/schemas.py # Pydantic models
│   │   ├── routers/         # API endpoints
│   │   └── services/        # Business logic
│   └── tests/
├── frontend/                # Vue.js SPA
├── data/qin2014_cirrhosis/  # Demo dataset (Qin et al. 2014)
├── Dockerfile
└── docker-compose.yml
```

## Tests

### Running Tests

```bash
cd backend
pip install -e ".[dev]"
pytest -v
```

### Coverage Summary

The backend test suite contains **20 tests** organized in 5 categories, covering all API endpoints and input validation:

| Test Class | Tests | What's Covered |
|------------|-------|----------------|
| **TestHealth** | 2 | `/health` endpoint returns correct fields (`status`, `engine_available`, `version`); status is always `"ok"` |
| **TestProjects** | 7 | Full CRUD lifecycle — create, list, get, delete; 404 on missing project; unique IDs; ISO timestamps |
| **TestDatasets** | 4 | TSV and CSV file upload via multipart; 404 on missing project; project metadata updated after upload |
| **TestAnalysis** | 3 | `/run` returns `job_id` with `pending` status; 404 on missing project; empty job list for new projects |
| **TestSchemaValidation** | 4 | Rejects invalid `algo` values (422); rejects invalid `fit` values (422); accepts valid non-default params; defaults are applied correctly |

**Total: 20 tests — all passing.**

### What's Tested

- All 9 REST API endpoints (see table above)
- Request validation via Pydantic schemas (invalid enum values return 422)
- File upload with correct content-type handling
- Project isolation (operations on non-existent projects return 404)
- Default parameter injection for analysis configuration
- Async request handling (tests use `httpx.AsyncClient` with `ASGITransport`)

### Not Yet Covered

- End-to-end analysis execution (requires gpredomicspy + sample data)
- WebSocket/SSE progress streaming (not yet implemented)
- Frontend component tests (planned for Phase 3)
- Docker build integration tests

## CI/CD

GitHub Actions runs on every push and PR:

- **backend-test**: Installs dependencies and runs `pytest`
- **frontend-build**: Installs npm packages and runs `npm run build`
- **docker-build**: Builds the multi-stage Docker image

See [.github/workflows/ci.yml](.github/workflows/ci.yml).

## License

GPL-3.0
