# PredomicsApp-Web — Roadmap

_Last updated: 2026-02-15_

---

## High Impact

### 1. Export & Reports ✅
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Add ability to download results as CSV/HTML report from the Results tab.

- CSV exports: coefficients, population, jury, generation tracking
- HTML report: self-contained with embedded charts and metrics
- Backend endpoints for CSV sections and full HTML report
- Frontend: Export dropdown in Results tab header

### 2. Job Comparison View ✅
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Enhance the existing Comparative sub-tab with detailed side-by-side analysis.

- Side-by-side metrics tables for 2+ selected jobs
- Diff highlighting for changed parameters
- Config diff viewer showing only differing parameters
- Performance delta visualization

### 3. Real-time Job Progress ✅
**Priority:** HIGH | **Effort:** High | **Status:** Done

Live progress tracking during training.

- ConsolePanel with ANSI-rendered log output and HTTP polling
- Real-time progress bar: current generation / max_epochs
- Generation, k-value, and language display
- Minimizable console with status badge

### 4. Notebook Integration ✅
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Generate downloadable Python/R notebooks from completed job results.

- Python notebook (.ipynb): loads data, runs gpredomicspy, displays results with matplotlib
- R notebook (.Rmd): loads data with gpredomicsR, generates ggplot2 visualizations
- Pre-filled with actual parameter values from completed jobs
- Download buttons in Results tab export dropdown

---

## Medium Impact

### 5. Onboarding Tour ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Interactive first-use walkthrough highlighting key features.

- Lightweight modal-based tour (OnboardingTour.vue) — no external dependencies
- 6 steps: Welcome → Create project → Upload data → Configure → Launch → Results
- "Don't show again" checkbox stored in localStorage
- Reset tour option in Profile → Preferences
- Auto-shows for first-time users after login

### 6. Browser Notifications ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Notify user when a long-running job completes or fails.

- Uses browser Notification API with permission request on project dashboard load
- Triggers on job status transition: running → completed/failed
- Shows AUC and k in notification body for completed jobs
- Enable/disable toggle in Profile → Preferences
- Auto-close after 10 seconds, click-to-focus

### 7. Batch Runs ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Launch multiple analysis jobs with parameter sweeps.

- Batch Mode toggle in Parameters tab with sweep parameter grid builder
- 7 sweepable params: seed, algo, language, data_type, population_size, max_epochs, k_max
- Cartesian product of sweep values (max 50 jobs per batch)
- `batch_id` column on jobs with migration v10
- Backend: `POST /batch` creates N jobs, `GET /batches` returns batch summaries with best AUC
- Jobs named `[Batch] param=value ...` for easy identification
- Real-time job count preview and max-50 validation

### 8. Dataset Tagging & Search ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Organize datasets with tags and enable search/filter.

- Added `tags: JSON` field to Dataset model with migration v9
- Tag CRUD endpoints (create, update, suggestions, filter)
- Search bar and tag filter dropdown in Dataset Library
- Clickable tag chips, inline tag editor with datalist autocomplete
- Pre-defined tags: benchmark, clinical, metagenomic, 16S, shotgun, WGS, etc.

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
