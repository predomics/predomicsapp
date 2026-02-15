# PredomicsApp-Web — Roadmap

_Last updated: 2026-02-15_

---

## High Impact

### 1. Export & Reports
**Priority:** HIGH | **Effort:** Medium

Add ability to download results as CSV/HTML report from the Results tab.

- **CSV exports:** Best model coefficients, population table, jury predictions, generation tracking
- **HTML report:** Self-contained printable/saveable report with embedded charts (Plotly static images or SVG), metrics summary, and model details
- Backend endpoints: `GET /api/analysis/{pid}/jobs/{jid}/export/csv?section=...` and `GET /api/analysis/{pid}/jobs/{jid}/export/report`
- Frontend: Export dropdown button in Results tab header

### 2. Job Comparison View
**Priority:** HIGH | **Effort:** Medium

Enhance the existing Comparative sub-tab with detailed side-by-side analysis.

- Side-by-side metrics tables for 2+ selected jobs
- Diff highlighting: show which parameters changed between runs
- Feature intersection/union Venn diagram
- Performance delta visualization (improvement/regression arrows)
- Config diff viewer: compact visual showing only parameters that differ

### 3. Real-time Job Progress
**Priority:** HIGH | **Effort:** High

Replace HTTP polling with WebSocket for live AUC evolution during training.

- Backend: WebSocket endpoint at `/ws/jobs/{job_id}` that streams generation_tracking updates
- Frontend: Live-updating AUC chart in ConsolePanel or Summary tab while job runs
- Show progress bar: current generation / max_epochs
- Estimated time remaining based on per-generation timing
- Fallback: Keep polling for environments where WebSocket is blocked

### 4. Notebook Integration
**Priority:** HIGH | **Effort:** Medium

Generate downloadable Python/R notebooks from completed job results.

- Backend: `GET /api/analysis/{pid}/jobs/{jid}/export/notebook?lang=python|r`
- Python notebook (.ipynb): loads data, runs gpredomicspy with same config, displays results
- R notebook (.Rmd): loads data with gpredomicsR, runs analysis, generates plots
- Pre-filled with actual parameter values from the completed job
- Includes data paths and result validation

---

## Medium Impact

### 5. Onboarding Tour
**Priority:** MEDIUM | **Effort:** Low

Interactive first-use walkthrough highlighting key features.

- Lightweight JS tooltip tour (no heavy dependency)
- Steps: Upload data → Configure parameters → Launch analysis → View results
- "Don't show again" preference stored in localStorage
- Contextual help tooltips on complex parameter controls

### 6. Browser Notifications
**Priority:** MEDIUM | **Effort:** Low

Notify user when a long-running job completes or fails.

- Use browser Notification API (requires user permission)
- Trigger on job status transition: running → completed/failed
- Show AUC result in notification body
- Optional sound alert setting

### 7. Batch Runs
**Priority:** MEDIUM | **Effort:** Medium

Launch multiple analysis jobs with parameter sweeps.

- Parameter grid builder: select ranges for k_min, k_max, population_size, etc.
- Queue system: submit all combinations, track progress per job
- Summary view: matrix of results across parameter combinations
- Best configuration auto-detection

### 8. Dataset Tagging & Search
**Priority:** MEDIUM | **Effort:** Low

Organize datasets with tags and enable search/filter.

- Add `tags: JSON` field to Dataset model
- Tag input UI in Dataset Library
- Filter datasets by tag in project assignment dialog
- Pre-defined tags: "benchmark", "clinical", "metagenomic", "16S", etc.

---

## Landing Page

### 9. Animated Workflow Diagram
**Priority:** LOW | **Effort:** Medium

Interactive SVG/CSS animation showing the Predomics pipeline.

- Data input → Feature selection → Evolutionary search → Model evaluation → Jury voting
- Step-by-step animation triggered on scroll
- Clickable steps linking to documentation

### 10. Use Case Examples
**Priority:** LOW | **Effort:** Low

Add real-world use cases with results to the landing page.

- Cirrhosis prediction from gut microbiome
- Cancer classification from gene expression
- Metabolic disease biomarker discovery
- Each with key metrics, model size, and publication reference

---

## Technical Debt

### 11. Test Coverage (55% → 80%+)
**Priority:** MEDIUM | **Effort:** High

Expand test suite to cover critical paths.

- Frontend component tests (Vitest + Vue Test Utils)
- Backend endpoint integration tests for all routers
- Edge cases: concurrent job execution, large datasets, error recovery
- CI pipeline: fail on coverage regression

### 12. API Documentation
**Priority:** LOW | **Effort:** Low

Auto-generate OpenAPI documentation.

- FastAPI already generates `/docs` and `/redoc` endpoints
- Add detailed docstrings and examples to all endpoints
- Generate client SDK types for TypeScript frontend
- Publish API docs on landing page

### 13. Production Deployment Guide
**Priority:** MEDIUM | **Effort:** Low

Documentation for deploying to various environments.

- Docker Compose for single-server deployment (current)
- Kubernetes Helm chart for cluster deployment
- NGINX reverse proxy configuration
- SSL/TLS setup with Let's Encrypt
- PostgreSQL migration from SQLite
- Backup and restore procedures
