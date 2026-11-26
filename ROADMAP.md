# PredomicsApp — Roadmap

_Last updated: 2026-11-25 (stale statements corrected; items 1–59 describe the state when each was completed — see [CHANGELOG.md](CHANGELOG.md) for what changed since)_

---

## High Impact

### 1. Export & Reports ✅
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Add ability to download results as CSV/HTML report from the Results tab.

- CSV exports: coefficients, population, jury, generation tracking
- HTML report: single file with embedded data and metrics (the charting library, Plotly, is loaded from `cdn.plot.ly`, so charts need internet access when the file is opened)
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

- **Backend: 207 tests** at the time (69 new) covering the 11 routers that existed then (the suite and the number of routers have grown since; `make test-backend` gives the current count) — datasets (94%), projects (97%), sharing (99%), admin (98%), auth (100%), export (93%), health (100%), analysis (73%), data_explore (90%), samples (97%)
- **Frontend: 59 tests** at the time (all new; more since, `make test-frontend`) — Vitest 4 + Vue Test Utils + jsdom: parameter definitions (13), notification utility (13), Pinia stores (14), Vue components (14), router config (5)
- Edge cases: concurrent jobs, batch runs, error recovery, export helpers
- Coverage config: `pyproject.toml` with `concurrency = ["greenlet", "thread"]` for accurate async tracking
- Remaining uncovered: DB migrations (main.py, PostgreSQL-specific), subprocess worker (worker.py), gpredomicspy internals

### 12. API Documentation ✅
**Priority:** LOW | **Effort:** Low | **Status:** Done

Auto-generate OpenAPI documentation.

- FastAPI Swagger UI available at `/api/docs`, ReDoc at `/api/redoc`, OpenAPI JSON at `/api/openapi.json` (the bare `/docs` path is served by the single-page app)
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

### 30. Multi-Cohort Meta-Analysis ✅
**Priority:** HIGH | **Effort:** High | **Status:** Done

Compare models trained on different datasets for the same phenotype.

- Backend: `GET /api/meta-analysis/searchable-jobs` — cross-project completed job search
- Backend: `POST /api/meta-analysis/compare` — feature overlap, concordance, meta-AUC
- Frontend: new "Meta-Analysis" top-level view with job picker (chip-based, 2-10 jobs)
- Metrics comparison table with best-value highlighting
- Feature overlap chart (horizontal bars by cohort count)
- Concordance matrix: feature × job grid colored by coefficient sign (green/red/grey)
- Meta-AUC card (weighted average across cohorts)
- "Meta-Analysis" link in navbar

### 31. SHAP-Style Feature Explanations ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Per-sample feature contribution breakdown for model interpretability.

- `useShapValues` composable: `computeShapMatrix()` computes SHAP values (feature × coef × sample value)
- Beeswarm plot: horizontal strip per feature, x=SHAP value, color=feature value (Viridis)
- Force plot: waterfall for single sample showing cumulative feature contributions
- Dependence plot: scatter of feature value vs SHAP value, colored by class
- Feature importance ordering by mean |SHAP|
- Entirely client-side using existing barcode-data API
- "Feature Explanations" section in Best Model sub-tab with 3 switchable views

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

### 35. E2E Integration Tests ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Automated end-to-end testing using Playwright.

- `playwright.config.mjs` at repo root with dark theme, 1440×900 viewport
- 10 E2E test cases in `tests/e2e/e2e.spec.mjs`:
  1. Landing page loads and shows brand
  2. User registration flow
  3. Login with credentials
  4. Create project
  5. Upload dataset files
  6. Dashboard displays summary cards
  7. Meta-analysis page accessible
  8. Public share page loads for guests
  9. Health API endpoint returns ok
  10. Swagger docs accessible
- Root `package.json` with `test:e2e` script and `@playwright/test` dependency
- CI integration: the end-to-end tests run in the `image` job of `.github/workflows/ci.yml`, against the image built in that job (on pull requests and on `main`)

### 36. CI/CD Pipeline & Docker Registry ✅
**Priority:** LOW | **Effort:** Low | **Status:** Done

Auto-deploy on tag push with container registry publishing.

- `.github/workflows/release.yml` triggered on `v*` tags
- Single checkout: gpredomics and gpredomicspy are fetched at pinned commits during the image build
- Gated on the full CI workflow; published for amd64 and arm64
- Login to GHCR, build and push with `docker/build-push-action`
- Tags: `ghcr.io/{owner}/predomicsapp:latest` + `:{version}`
- GitHub Actions cache (`type=gha`) for faster rebuilds
- OCI metadata labels in Dockerfile (title, description, source, license)

### 37. Internationalization (i18n) ✅
**Priority:** LOW | **Effort:** High | **Status:** Done

Multi-language support starting with French.

- `vue-i18n@9` integration with JSON locale files
- `frontend/src/i18n/` module with `createI18n()` setup
- English (`en.json`) and French (`fr.json`) locale files (about 100 strings each at the time; over 1,100 keys each today)
- Namespaces: nav, home, login, dashboard, projects, results, meta, common
- Language selector button (EN/FR toggle) in navbar next to theme toggle
- `localStorage.locale` persistence across sessions
- Navbar links translated via `$t('nav.dashboard')` etc.
- Backend: `Accept-Language` header parsing in `core/errors.py` for translated error messages

---

## Phase 5: Advanced Analytics & Population Mining

### 38. t-SNE & UMAP Ordination ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Add t-SNE and UMAP as alternative dimensionality reduction methods alongside PCoA.

- Unified `/api/data-explore/{pid}/ordination` endpoint with `method` param (pcoa, tsne, umap)
- Backend: `compute_tsne()` and `compute_umap()` in `data_analysis.py` using precomputed distance matrices
- Method-specific parameters: perplexity (t-SNE), n_neighbors/min_dist (UMAP)
- Shared `_load_and_prepare()` helper with subsampling (max 1000 samples)
- Dynamic axis labels: "PCo1 (X%)" for PCoA, "t-SNE 1" / "UMAP 1" for others
- PERMANOVA and 95% confidence ellipses for all methods
- Added to DataTab, ResultsTab (Population), and DataExploreTab
- Dependencies: `scikit-learn>=1.0`, `umap-learn>=0.5`

### 39. CI-based FBM Selection (Blaise Method) ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Add the Blaise confidence interval method as alternative to standard Wald CI for FBM filtering.

- Dropdown in Population and Co-Presence tabs to choose between Standard CI and Blaise CI
- Blaise formula: `threshold = r - (0.5/n + 1.96 * sqrt(r*(1-r)/n))` — adds continuity correction
- Shared `fbmMethod` ref between Population and Co-Presence tabs
- i18n: "Standard CI" / "Blaise CI" in EN/FR

### 40. Accuracy-Weighted Co-Presence Network ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Enhance co-presence analysis with model fitness weighting (Shasha Cui internship, 2017).

- Toggle checkbox in Co-Presence controls for accuracy-weighted mode
- Per-node mean accuracy: `meanAccuracy[feature] = sum(model.fit) / count`
- Per-edge accuracy-weighted counts: `wObs = sum(model.fit for co-occurring pairs)`
- Weighted expected: `wExp = (accSum_i * accSum_j) / totalAccSum`
- Weighted ratio: `wRatio = wObs / wExp`
- Prevalence chart: secondary axis with mean accuracy diamonds
- Network: node size by accuracy, edge width by weighted ratio, accuracy in hover
- Stats table: "W. Obs" and "W. Ratio" columns when weighted mode is on
- Hypergeometric test unchanged (stays on binary integer counts for statistical validity)

### 41. Model Basket ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Bookmark individual models from any job's population into a persistent curated collection.

- `useModelBasket.js` composable with localStorage persistence per project (max 50 models)
- Star toggle (★/☆) in Population table to add/remove models
- Basket sub-tab with count badge in Results tab nav bar
- Bookmarked models table with expandable feature chips, remove button
- Metrics comparison grouped bar chart (AUC, Accuracy, Sensitivity, Specificity per model)
- Feature overlap horizontal stacked bar chart with positive/negative direction
- Consensus features display (features common to all basket models)
- Feature coefficient heatmap (features × models, blue-white-red colorscale)
- Cross-job support: basket items store data snapshots, survive job deletion

### 42. Multiple Community Detection Algorithms ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Add dropdown to choose between community detection methods in the Ecosystem network.

- Backend: `_detect_communities(G, method, seed)` dispatcher in `coabundance.py`
- Supported algorithms: Louvain (default), Greedy modularity maximization, Label propagation
- `community_method` parameter added to `compute_coabundance_network()` and cache key
- Endpoint validation: rejects unknown methods with HTTP 400
- Frontend: dropdown in EcosystemTab controls, auto-refetch on change
- Graceful fallback to singleton communities on algorithm failure
- i18n: "Community" / "Greedy modularity" / "Label propagation" in EN/FR

### 43. Module Niche Zoom ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Select a network module and zoom into a higher-resolution sub-network for detailed niche analysis.

- Zoom button per module in the sidebar (magnifying glass icon)
- Extracts member species, re-calls `/coabundance-network` with `features=members` and halved thresholds
- `displayedNetwork` computed property for seamless switching between full and zoomed views
- Breadcrumb navigation bar showing module ID, member count, and "Back to full network" button
- `zoomOut()` restores the full network; parameter changes auto-clear zoom state
- Updated `renderNetwork()` to use `displayedNetwork.value` throughout
- Stats bar, chart visibility, and taxonomy legend all react to zoom state
- i18n: "Zoom into this module" / "Back to full network" in EN/FR

### 44. Aberrant Correlation Diagnostic ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

QC scatter plot comparing per-class Spearman correlations to detect prevalence filtering artifacts.

- Backend: `compute_aberrant_correlations()` in `data_analysis.py` — computes full Spearman correlation matrices per class, extracts upper-triangle pairs
- Prevalence filtering (default 30%), subsampling to 500 features if needed, max 5000 pairs
- Returns `{pairs: [{f1, f2, r0, r1}], n_features, n_pairs, feature_names}`
- New endpoint: `GET /{project_id}/aberrant-correlations` with `min_prevalence_pct` param
- Frontend: new "Aberrant Correlation Diagnostic" sub-tab in DataExploreTab
- Plotly scatter: x = Class 0 rho, y = Class 1 rho, continuous colorscale by deviation from diagonal
- Dashed y=x reference line, equal aspect ratio axes [-1.05, 1.05]
- i18n: aberrant correlation labels in EN/FR

### 45. Dual-Network Comparison ✅
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Side-by-side patient vs. control co-abundance ecosystems highlighting common and condition-specific interactions.

- New endpoint: `GET /{project_id}/dual-network` — computes both class networks in one call
- Edge comparison: identifies common edges (present in both), class-0-specific, and class-1-specific
- Each edge annotated with `shared` boolean flag for coloring
- Frontend: "Dual network" checkbox toggle in EcosystemTab controls
- Side-by-side Plotly panels in a CSS grid (responsive: stacks on mobile)
- Comparison stats header: common edge count + specific counts per class
- Edge coloring: shared = gray (subtle), class-0-specific = teal, class-1-specific = orange
- Auto-refetch on parameter changes when dual mode is active
- i18n: "Dual network" / "Common edges" / "Controls" / "Patients" in EN/FR

### 46. Alluvial/Sankey Module Correspondence ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Visualize how network modules reorganize between patient and control ecosystems via an alluvial/Sankey diagram.

- Backend: module correspondence computation added to `get_dual_network` endpoint in `data_explore.py`
- Species→module mapping per class, intersection of common species, flow counting between module pairs
- `sankey_links` array of `{source_module, target_module, value}` in dual-network response
- Frontend: Plotly Sankey trace in `EcosystemTab.vue` below dual-network panels
- Node labels combine class label, module ID, and dominant phylum
- Link colors: semi-transparent source module color (handles both rgb() and hex)
- Rendered automatically when dual mode is active and sankey_links has data
- i18n: "Module Correspondence" / "Correspondance des modules" in EN/FR

### 47. External Network Import ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Upload and display external network JSON files (e.g. from SCAPIS) with FBM signature annotation.

- Backend: 4 new endpoints in `data_explore.py`:
  - `POST /{project_id}/external-networks` — upload JSON (max 10MB, validates nodes/edges arrays)
  - `GET /{project_id}/external-networks` — list uploaded networks
  - `GET /{project_id}/external-networks/{network_id}` — retrieve full network data
  - `DELETE /{project_id}/external-networks/{network_id}` — delete (editor role)
- Storage: `data/projects/{project_id}/networks/{uuid}.json`
- Frontend: external network section in EcosystemTab with select dropdown, upload button, delete button
- Rendering: uses fixed positions (x, y from JSON) if available, organic layout fallback
- FBM annotation: species matching FBM population features highlighted with gold color, diamond shape, orange border
- Edge styling: positive = solid gray, negative = dashed red, width scaled by |weight|
- i18n: "External Network" / "Réseau externe" in EN/FR

### 48. Ecosystem-guided FBM Filtering ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Filter the Family of Best Models by network module membership to keep only ecologically coherent models.

- Backend: `POST /{project_id}/fbm-module-filter` endpoint in `data_explore.py`
- Loads job results population, computes co-abundance network to get module assignments
- Per-model metrics: module coverage (fraction in selected modules), module coherence (fraction in same module)
- Filters models with ≥50% features in selected modules, sorted by coverage then fitness
- Frontend: "FBM Module Filter" section in EcosystemTab with module checkboxes, apply/clear buttons
- Results table with rank, fit, k, language, coverage bar, coherence, in-module count
- CSV export of filtered models
- Event integration: emits `module-filter-applied` to parent ResultsTab
- Population table: blue highlight + "M" badge for filtered models
- i18n: 12 keys in EN/FR (filter title, description, coverage, coherence, export, etc.)

### 49. Signature Zoo ✅
**Priority:** MEDIUM | **Effort:** High | **Status:** Done

Curated, searchable database of published biomarker signatures for cross-study comparison and reuse.

- Backend: new `signature_zoo.py` router with 7 endpoints:
  - `GET /api/signature-zoo/` — list all signatures with optional disease/method/search filters
  - `GET /api/signature-zoo/compare` — compare 2+ signatures (Jaccard overlap, performance, common features)
  - `GET /api/signature-zoo/{id}` — get single signature
  - `POST /api/signature-zoo/` — create signature (auth required)
  - `PUT /api/signature-zoo/{id}` — update (auth required)
  - `DELETE /api/signature-zoo/{id}` — delete (admin only)
  - `POST /api/signature-zoo/import-from-job` — create from completed job's best model
- File-based JSON storage at `data/signature_zoo.json` with fcntl file locking
- 4 seed signatures: Cirrhosis (Qin 2014), CRC (Zeller 2014), Obesity (Le Chatelier 2013), T2D (Karlsson 2013)
- Frontend: `SignatureZooView.vue` with card grid, filters (disease/method/text), detail modal, compare mode
- Compare mode: Plotly performance bars, Jaccard overlap matrix, common features, feature presence chart
- Route `/signature-zoo` in router.js, navbar link in App.vue
- 35 i18n keys in EN/FR

---

## Phase 6: gpredomics v1.0.0 Integration & Regression

_Updated: 2026-03-31_

### 50. Regression Support ✅ [gpredomics#15](https://github.com/predomics/gpredomics/issues/15), [gpredomics#79](https://github.com/predomics/gpredomics/issues/79)
**Priority:** HIGH | **Effort:** High | **Status:** Done

Data.y changed from Vec<u8> to Vec<f64>. 4 regression fitness functions (spearman, pearson, rmse, mutual_information). Regression-aware display, test metrics, CV fold splitting, voting skip.

### 51. 4 New Optimization Algorithms ✅ [gpredomics#61](https://github.com/predomics/gpredomics/issues/61), [#62](https://github.com/predomics/gpredomics/issues/62), [#65](https://github.com/predomics/gpredomics/issues/65), [#54](https://github.com/predomics/gpredomics/issues/54)
**Priority:** HIGH | **Effort:** High | **Status:** Done

SA (Simulated Annealing), ILS (Iterated Local Search), LASSO/Elastic Net, ACO (Ant Colony Optimization). All integrated in web app.

### 52. MCMC Gibbs Variable Selection ✅ [gpredomics#73](https://github.com/predomics/gpredomics/issues/73), [#70](https://github.com/predomics/gpredomics/issues/70)
**Priority:** HIGH | **Effort:** High | **Status:** Done

Joint feature+coefficient sampling replacing SBS. LASSO prescreen, parallel chains, golden section optimizer. MCMC from OOM/minutes to 5-11 seconds.

### 53. Code Audit & Fixes ✅ [gpredomics#75](https://github.com/predomics/gpredomics/issues/75)
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

12 critical + 14 medium issues fixed. HashMap→BTreeMap for determinism. ClassificationMetrics refactor. -280 lines dead code removed.

### 54. Metadata Upload & Variable Selection ✅ [predomicsapp#1](https://github.com/predomics/predomicsapp/issues/1)
**Priority:** HIGH | **Effort:** Medium | **Status:** Done

Upload metadata TSV, select numeric column as regression y, auto-switch to regression mode. Backend APIs for metadata column parsing and y extraction.

### 55. Feature Selection in UI ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Exposed prevalence, adj_pvalue, selection method in Parameters tab. Documented adaptive FDR relaxation.

### 56. Adaptive BH-FDR ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

When strict FDR selects < 10 features, alpha relaxes progressively (0.05→0.1→0.2→0.5) with warnings. Fallback to top 10 by raw p-value.

### 57. Wetlab Protocol Dataset ✅ [gpredomics#60](https://github.com/predomics/gpredomics/issues/60)
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Paired study (459 subjects, 2 extraction protocols). 1,981 MSPs. Subject-level train/test split. Metadata with age, sex, BMI, Gram+/- counts, gene_count.

### 58. Samples/Data Separation ✅
**Priority:** MEDIUM | **Effort:** Low | **Status:** Done

Bundled demos in samples/ (baked in image). User workspace in data/ (persistent volume for K8s).

### 59. Documentation ✅
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Done

Codebase documentation (the February 2026 HTML/PDF snapshot was retired in favour of `docs/architecture.md`, `docs/tutorial.md` and `docs/api-guide.md`). Fully documented `samples/qin2014_cirrhosis/param.yaml`. The vignette tutorial and the per-algorithm documentation are in the gpredomics repository and on <https://predomics.github.io>, not in this repository.

### Shipped without a roadmap entry

Added after Phase 6 and not listed above (see [CHANGELOG.md](CHANGELOG.md)):
scikit-learn comparison models (random forest, SVM, logistic regression,
XGBoost, LightGBM, extra trees, AdaBoost, k-NN), the Insights tab, taxonomic and
functional enrichment, the z-score data type and data transformations in data
exploration, and the build, deployment and security hardening of November 2026
(pinned engine, non-root image, administrator bootstrap setting, job queue
limits, working scheduled backups).

---

## Phase 7: Upcoming

### 60. Multi-user Workspace Management [predomicsapp#4](https://github.com/predomics/predomicsapp/issues/4)
**Priority:** HIGH | **Effort:** High | **Status:** Open

Per-user disk quotas, dataset deduplication, admin dashboard. (Partly done since: a global job concurrency limit, `PREDOMICS_MAX_CONCURRENT_JOBS`, and a job timeout, `PREDOMICS_JOB_TIMEOUT_MINUTES`, now exist.)

### 61. Data Scanning Console Feedback [predomicsapp#5](https://github.com/predomics/predomicsapp/issues/5)
**Priority:** MEDIUM | **Effort:** Low | **Status:** Open

Show scanning progress during dataset load: feature count, class distribution, prevalence stats, warnings.

### 62. Optuna Hyperparameter Optimization [gpredomics#77](https://github.com/predomics/gpredomics/issues/77)
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Open

Bayesian hyperparameter tuning via Optuna in gpredomicspy. Search space for k_penalty, population_size, algorithm choice, etc.

### 63. Multiclass Classification (OVO/OVA) [gpredomics#52](https://github.com/predomics/gpredomics/issues/52)
**Priority:** HIGH | **Effort:** High | **Status:** Open

One-vs-All and One-vs-One strategies for multi-class problems. Orchestrate K binary gpredomics runs.

### 64. Clinical Data Integration [gpredomics#51](https://github.com/predomics/gpredomics/issues/51)
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Partly done (a "Clinical" parameter section and clinical-file selection exist in the app; the engine-side work tracked in the issue is open)

Stacking, calibration, stratification of omics scores with clinical variables.

### 65. MCMC SBS Fix [gpredomics#81](https://github.com/predomics/gpredomics/issues/81)
**Priority:** MEDIUM | **Effort:** Medium | **Status:** Open

SBS Bayesian evaluation produces inverted AUC after optimization changes.

### 66. Auto-discover Feature Weights [gpredomics#78](https://github.com/predomics/gpredomics/issues/78)
**Priority:** LOW | **Effort:** Medium | **Status:** Open

Compare feature distributions between folds to auto-discover sampling weights.

### 67. More Heuristics [gpredomics#63](https://github.com/predomics/gpredomics/issues/63), [#64](https://github.com/predomics/gpredomics/issues/64), [#66](https://github.com/predomics/gpredomics/issues/66)
**Priority:** LOW | **Effort:** Medium | **Status:** Open

PSO (Particle Swarm), EDA/UMDA, Bayesian Optimization.

### 68. Island Model GA [gpredomics#33](https://github.com/predomics/gpredomics/issues/33)
**Priority:** LOW | **Effort:** High | **Status:** Open

Separate environments with periodic migration for diversity preservation.
