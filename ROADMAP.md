# PredomicsApp-Web — Roadmap

_Last updated: 2026-02-16_

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

### 9. Animated Workflow Diagram ✅
**Priority:** LOW | **Effort:** Medium | **Status:** Done

Interactive CSS animation showing the Predomics pipeline on the landing page.

- 5-step pipeline: Data Input → Feature Selection → Evolutionary Search → Model Evaluation → Jury Voting
- CSS keyframe fadeSlideIn animation with staggered delays
- Arrow connectors between steps, responsive layout
- Each step has icon, label, and description

### 10. Use Case Examples ✅
**Priority:** LOW | **Effort:** Low | **Status:** Done

Real-world use cases with results on the landing page.

- 4 use cases: Cirrhosis (Qin 2014), Cancer (Zeller 2014), Treatment Response (Gopalakrishnan 2018), Metabolic Disease (Karlsson 2013)
- Each card has icon, description, key metrics (AUC, features, samples), and publication reference
- Hover effects, responsive grid layout

---

## Technical Debt

### 11. Test Coverage (55% → 86%) ✅
**Priority:** MEDIUM | **Effort:** High | **Status:** Done

Expanded test suite to cover critical paths — **86% coverage** on testable backend code.

- **Backend: 207 tests** (69 new) covering all 11 routers — datasets (94%), projects (97%), sharing (99%), admin (98%), auth (100%), export (93%), health (100%), analysis (73%), data_explore (90%), samples (97%)
- **Frontend: 59 tests** (all new) — Vitest 4 + Vue Test Utils + jsdom: parameter definitions (13), notification utility (13), Pinia stores (14), Vue components (14), router config (5)
- Edge cases: concurrent jobs, batch runs, error recovery, export helpers
- Coverage config: `pyproject.toml` with `concurrency = ["greenlet", "thread"]` for accurate async tracking
- Remaining uncovered: DB migrations (main.py, PostgreSQL-specific), subprocess worker (worker.py), gpredomicspy internals

### 12. API Documentation ✅
**Priority:** LOW | **Effort:** Low | **Status:** Done

Auto-generate OpenAPI documentation.

- Fixed SPA catch-all to not intercept `/docs`, `/redoc`, `/openapi.json` paths
- FastAPI Swagger UI available at `/docs`, ReDoc at `/redoc`
- OpenAPI JSON schema at `/openapi.json`

### 13. Production Deployment Guide ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Comprehensive DEPLOYMENT.md covering all deployment scenarios.

- Docker Compose single-server deployment with production overrides
- Full environment variable reference table
- NGINX reverse proxy configuration with security headers
- SSL/TLS setup with Let's Encrypt and certbot
- PostgreSQL configuration and managed database migration
- Backup & restore procedures (database + files) with automated cron script
- Kubernetes deployment manifests with Ingress and cert-manager
- Health check and monitoring guidance
- Troubleshooting section

---

## Enhancements (Phase 2)

### 14. Database Backup & Import ✅
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Full system backup and restore via portable tar.gz archives.

- Backend service: JSON export of all DB tables in FK dependency order
- Archive includes: database JSON, dataset files, job results, admin defaults, manifest
- Restore modes: **replace** (wipe + restore) or **merge** (skip existing records)
- Admin UI: create backup, list/download/delete backups, upload & restore
- 5 new admin API endpoints

### 15. WebSocket Live Job Logs ✅
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Real-time log streaming via WebSocket with HTTP polling fallback.

- WebSocket endpoint: `/ws/jobs/{project_id}/{job_id}?token=JWT`
- Tail-f style log streaming with 0.5s refresh
- JWT authentication via query parameter
- Automatic fallback to HTTP polling if WebSocket fails
- Status change broadcasts (running → completed/failed)

### 16. Dataset File Preview ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Preview dataset file contents without downloading.

- Backend: CSV/TSV parsing with first N rows, column types, basic stats (min/max/mean/std)
- Frontend modal with scrollable table, sticky headers, row numbers
- Stats footer row, file metadata badges
- Preview buttons in Dataset Library file rows

### 17. Performance Optimizations ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Improve response times and initial load performance.

- In-memory TTL cache decorator for expensive backend endpoints
- GZip response compression middleware (min 1KB)
- Dynamic import for Plotly.js (~3MB) — loaded on demand in Results tab

### 18. Error Handling & UX Polish ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Structured error responses and user-facing notifications.

- Backend: structured `{error: {code, message}}` JSON responses for all HTTP errors
- Generic catch-all 500 handler with server-side logging
- Toast notification system: composable + ToastContainer component
- Axios response interceptor for global error display
- Exponential backoff retry utility for transient failures

---

## Phase 3: Security, Integrations & Data Management

### 19. Feature Importance Visualization ✅
**Priority:** HIGH | **Effort:** Low | **Status:** Done

Richer charts in the Best Model sub-tab for exploring feature contributions.

- Coefficient direction chart: horizontal bars colored by sign (green=positive, red=negative)
- Feature contribution waterfall: cumulative sorted contributions using Plotly waterfall trace
- Per-sample contribution heatmap: button-triggered, computes coefficient × feature values matrix
- All data sourced from existing results JSON — no backend changes needed

### 20. Project Templates ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Admin-managed parameter presets available to all users.

- File-based JSON storage at `data/templates.json` (same pattern as admin defaults)
- CRUD endpoints: GET/POST/PUT/DELETE + public GET (no auth)
- Admin UI: create/delete templates from current default config
- Parameters tab: "Load Template" dropdown applies preset config values

### 21. Audit Log ✅
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Track all user actions with timestamps, queryable by admins.

- `AuditLog` model: user_id, action, resource_type, resource_id, details (JSON), ip_address
- 14 action constants: login, register, job.launch/delete, dataset.upload/delete, project.create/delete, share.create/revoke, admin operations
- Instrumented across 6 routers (auth, analysis, datasets, projects, sharing, admin)
- Admin UI: paginated audit log table with action filter
- Migration v11

### 22. Password Reset & Email ✅
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Self-service password reset with optional SMTP email delivery.

- `PasswordResetToken` model with bcrypt-hashed tokens and 1-hour expiry
- `email_verified` field on User model (migration v12)
- aiosmtplib integration (optional dep — graceful ImportError handling)
- Dev mode: returns reset token directly when no SMTP configured
- Frontend: ForgotPasswordView + ResetPasswordView with router guard
- Admin: direct password reset for any user

### 23. API Key Management ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Programmatic access via API keys as alternative to JWT Bearer tokens.

- `ApiKey` model with bcrypt-hashed keys, 8-char prefix, last_used_at tracking
- Keys shown only once on creation
- Dual auth: `get_current_user` accepts both `Authorization: Bearer` and `X-API-Key` header
- Frontend: create/list/revoke API keys in Profile view
- Migration v13

### 24. Webhook Notifications ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

HTTP POST callbacks to external URLs when jobs complete or fail.

- `Webhook` model with HMAC-SHA256 signing via secret
- Delivery with configurable retries and exponential backoff (httpx)
- CRUD + test endpoint (send test payload)
- Fired from background job runner on completion/failure
- Frontend: create/list/delete/test webhooks in Profile view
- Migration v14

### 25. Dataset Versioning ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Automatic snapshots on file changes with restore capability.

- `DatasetVersion` model: version_number, files_snapshot (JSON), created_by, note
- Auto-snapshot on file upload and file delete
- Version history endpoint with restore to any previous version
- Frontend: "History" button per dataset with version list and restore
- Migration v15

### 26. Rate Limiting ✅
**Priority:** HIGH | **Effort:** Low | **Status:** Done

Per-user and per-IP rate limits using slowapi (in-memory, no Redis required).

- User-or-IP key extraction from JWT, API key prefix, or client IP
- Configurable limits: auth (10/min), API (100/min), upload (20/min), admin (30/min)
- Limiter decorators on auth, upload, and admin endpoints
- 429 toast handling in frontend Axios interceptor
- Global enable/disable via config setting

---

## Phase 4: Analytics, Collaboration & Infrastructure

### 27. External Validation ✅
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Score new samples against trained models without re-training.

- Shared prediction service (`services/prediction.py`): coefficient extraction, data_type transform, score computation, threshold classification
- Upload X_valid.tsv + optional Y_valid.tsv via multipart form
- Validation metrics: AUC, accuracy, sensitivity, specificity, confusion matrix
- Per-sample prediction table with scores and classifications
- Backend: `POST /api/analysis/{id}/jobs/{jid}/validate` endpoint
- Frontend: ValidateModal in Best Model sub-tab with file upload and results display

### 28. Model Deployment API ✅
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Serve trained models as live prediction endpoints.

- `POST /api/predict/{job_id}` — JSON body with `{features: {name: [values]}, sample_names: [...]}`
- Returns scores, predicted_classes, threshold, matched/missing features
- Reuses shared `prediction.py` service from F27
- API key authentication (`X-API-Key` header) for programmatic access
- Frontend: "Prediction API" section in Best Model sub-tab with endpoint URL, curl example, and copy button

### 29. Biomarker Discovery Report ✅
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Auto-generate publication-ready PDF summarizing analysis findings.

- 3-page PDF report using reportlab (`services/pdf_report.py`)
- Page 1: Performance metrics (AUC, accuracy, sensitivity, specificity), jury summary
- Page 2: Feature table with coefficients, taxonomy annotations, functional properties
- Page 3: Configuration summary, generation tracking highlights
- Backend: `GET /api/export/{pid}/jobs/{jid}/pdf` endpoint
- Frontend: "PDF Biomarker Report" option in Export dropdown

### 30. Multi-Cohort Meta-Analysis
**Priority:** HIGH | **Effort:** High | **Status:** Pending

Compare models trained on different datasets for the same phenotype.

- Select multiple completed jobs (cross-project) for comparison
- Shared feature overlap analysis (Venn diagram or UpSet plot)
- Concordance of feature directions (same sign across cohorts)
- Meta-AUC estimation across datasets
- Frontend: new "Meta-Analysis" top-level view
- Backend: cross-project job query endpoint

### 31. SHAP-Style Feature Explanations
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Pending

Per-sample feature contribution breakdown for model interpretability.

- Compute Shapley-like values: feature × coefficient × sample value
- Beeswarm plot: feature impact distribution across all samples
- Force plot: single-sample waterfall of feature contributions
- Dependence plot: feature value vs. SHAP value scatter
- All computed client-side from existing results + barcode data
- Frontend: "Explanations" section in Best Model sub-tab

### 32. Project Comments & Activity Feed ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Threaded notes/discussion per project.

- `ProjectComment` model: id, project_id, user_id, content (Text), created_at, updated_at
- CRUD endpoints: create, list, update (author only), delete (author or project owner)
- CommentsSidebar component: slide-out panel with comment list, add/edit/delete
- User initials avatar, timestamps, Ctrl+Enter submit shortcut
- "Notes" button in project dashboard header
- Migration v17

### 33. Public Sharing Links ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Share results via read-only public links (no login required).

- `PublicShare` model: id, project_id, token (64-char, unique indexed), created_by, expires_at, is_active
- Authenticated endpoints: create, list, revoke links (project owner only)
- Unauthenticated endpoints: `GET /api/public/{token}` for project info + jobs, `GET /api/public/{token}/jobs/{jid}/results` for full results
- PublicShareModal: create links with expiry options (7/30/90 days or never), copy URL, revoke
- PublicShareView: guest-accessible page with project summary, job cards, metrics grid, feature display
- "Public Link" button in project dashboard header
- Router guard allows both authenticated and unauthenticated access
- Migration v18

### 34. Dashboard Overview ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Global view of all projects with summary statistics and recent activity.

- Backend: `GET /api/dashboard/` — aggregates counts (projects, datasets, running/completed/failed jobs, shared)
- Active jobs section with status badges and links to project console
- Recent completions mini-table (project name, AUC, k, date)
- Activity feed from audit_logs with action icons, resource links, timeAgo formatting
- Summary cards grid: Projects, Datasets, Running, Completed, Failed, Shared
- "Dashboard" link in navbar (before Projects)

### 35. E2E Integration Tests
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Pending

Automated end-to-end testing using Playwright.

- Extend existing `capture_screenshots.mjs` into full test suite
- Test flows: register → create project → upload data → run analysis → view results
- Assert page content, not just screenshots
- CI integration: run E2E tests in GitHub Actions with Docker
- Smoke test for production deployments

### 36. CI/CD Pipeline & Docker Registry
**Priority:** LOW | **Effort:** Low | **Status:** Pending

Auto-deploy on tag push with container registry publishing.

- GitHub Actions: build + push Docker image to GHCR on version tags
- Auto-deploy to staging on main push (optional webhook)
- Release artifact: pre-built Docker image for easy deployment
- Version label in Docker image metadata

### 37. Internationalization (i18n)
**Priority:** LOW | **Effort:** High | **Status:** Pending

Multi-language support starting with French.

- vue-i18n integration with JSON locale files
- Extract all user-facing strings to translation keys
- Language selector in navbar or profile settings
- Initial languages: English (default), French
- Backend: translatable error messages
