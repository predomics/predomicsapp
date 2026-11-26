/**
 * The backend API, one function per endpoint.
 *
 * Components call these instead of building URLs for axios themselves, so an
 * endpoint is spelled once and a change of path or parameter is a one-line edit.
 *
 * Every function returns the axios promise (use `const { data } = await ...`).
 * Path parameters come first and are URL-encoded. Then:
 *   - GET / DELETE:        (…pathParams, config)
 *   - POST / PUT / PATCH:  (…pathParams, body, config)
 * `config` is a normal axios config: `params`, `timeout`, `responseType`, and the
 * two flags understood by utils/http.js — `silentError` (no global toast) and
 * `errorContext` (prefix for the global toast).
 *
 * This file is generated from the endpoint table; keep it sorted by resource.
 */
import axios from 'axios'

/** The shared axios instance (interceptors are installed in utils/http.js). */
export const http = axios

const enc = encodeURIComponent

export const auth = {
  /** GET /api/auth/api-keys — API keys of the current user. */
  listApiKeys: (config) => http.get('/api/auth/api-keys', config),
  /** POST /api/auth/api-keys — Create an API key (shown once). */
  createApiKey: (body, config) => http.post('/api/auth/api-keys', body, config),
  /** DELETE /api/auth/api-keys/… — Revoke an API key. */
  deleteApiKey: (keyId, config) => http.delete(`/api/auth/api-keys/${enc(keyId)}`, config),
  /** POST /api/auth/forgot-password — Ask for a password-reset email. */
  forgotPassword: (body, config) => http.post('/api/auth/forgot-password', body, config),
  /** POST /api/auth/login — Exchange email and password for an access token. */
  login: (body, config) => http.post('/api/auth/login', body, config),
  /** GET /api/auth/me — Current user. */
  me: (config) => http.get('/api/auth/me', config),
  /** PUT /api/auth/me — Update the current user's profile. */
  updateMe: (body, config) => http.put('/api/auth/me', body, config),
  /** PUT /api/auth/me/password — Change password; answers with a fresh access token. */
  changePassword: (body, config) => http.put('/api/auth/me/password', body, config),
  /** GET /api/auth/me/usage — Storage used and quota of the current user. */
  usage: (config) => http.get('/api/auth/me/usage', config),
  /** POST /api/auth/refresh — Exchange a still-valid access token for a fresh one. */
  refresh: (body, config) => http.post('/api/auth/refresh', body, config),
  /** POST /api/auth/register — Create an account. */
  register: (body, config) => http.post('/api/auth/register', body, config),
  /** POST /api/auth/resend-verification — Send the verification email again. */
  resendVerification: (body, config) => http.post('/api/auth/resend-verification', body, config),
  /** POST /api/auth/reset-password — Set a new password with a reset token. */
  resetPassword: (body, config) => http.post('/api/auth/reset-password', body, config),
  /** GET /api/auth/users/search — Find users by email prefix (params.q, 3+ characters). */
  searchUsers: (config) => http.get('/api/auth/users/search', config),
  /** POST /api/auth/verify-email — Confirm an email address with the emailed token. */
  verifyEmail: (body, config) => http.post('/api/auth/verify-email', body, config),
  /** POST /api/auth/ws-ticket — One-time, short-lived ticket for opening a WebSocket. */
  wsTicket: (body, config) => http.post('/api/auth/ws-ticket', body, config),
}

export const projects = {
  /** GET /api/projects/ — Projects of the current user. */
  list: (config) => http.get('/api/projects/', config),
  /** POST /api/projects/ — Create a project (name, description via config.params). */
  create: (body, config) => http.post('/api/projects/', body, config),
  /** GET /api/projects/shared-with-me — Projects other users shared with me. */
  sharedWithMe: (config) => http.get('/api/projects/shared-with-me', config),
  /** DELETE /api/projects/… — Delete a project. */
  remove: (projectId, config) => http.delete(`/api/projects/${enc(projectId)}`, config),
  /** GET /api/projects/… — One project with its datasets and jobs. */
  get: (projectId, config) => http.get(`/api/projects/${enc(projectId)}`, config),
  /** PATCH /api/projects/… — Rename, describe or set class names. */
  update: (projectId, body, config) => http.patch(`/api/projects/${enc(projectId)}`, body, config),
  /** POST /api/projects/…/archive — Archive or unarchive a project. */
  toggleArchive: (projectId, body, config) => http.post(`/api/projects/${enc(projectId)}/archive`, body, config),
  /** GET /api/projects/…/comments — Notes on a project. */
  comments: (projectId, config) => http.get(`/api/projects/${enc(projectId)}/comments`, config),
  /** POST /api/projects/…/comments — Add a note. */
  addComment: (projectId, body, config) => http.post(`/api/projects/${enc(projectId)}/comments`, body, config),
  /** DELETE /api/projects/…/comments/… — Delete a note. */
  deleteComment: (projectId, commentId, config) => http.delete(`/api/projects/${enc(projectId)}/comments/${enc(commentId)}`, config),
  /** PUT /api/projects/…/comments/… — Edit a note. */
  updateComment: (projectId, commentId, body, config) => http.put(`/api/projects/${enc(projectId)}/comments/${enc(commentId)}`, body, config),
  /** POST /api/projects/…/datasets — Upload a file straight into a project (params.role). */
  uploadDataset: (projectId, body, config) => http.post(`/api/projects/${enc(projectId)}/datasets`, body, config),
  /** GET /api/projects/…/datasets/…/files/…/columns — Column names of a project file. */
  fileColumns: (projectId, datasetId, fileId, config) => http.get(`/api/projects/${enc(projectId)}/datasets/${enc(datasetId)}/files/${enc(fileId)}/columns`, config),
  /** GET /api/projects/…/public — Public links of a project. */
  publicLinks: (projectId, config) => http.get(`/api/projects/${enc(projectId)}/public`, config),
  /** POST /api/projects/…/public — Create a public link. */
  createPublicLink: (projectId, body, config) => http.post(`/api/projects/${enc(projectId)}/public`, body, config),
  /** DELETE /api/projects/…/public/… — Revoke a public link. */
  revokePublicLink: (projectId, linkId, config) => http.delete(`/api/projects/${enc(projectId)}/public/${enc(linkId)}`, config),
  /** POST /api/projects/…/share — Share a project with a user. */
  share: (projectId, body, config) => http.post(`/api/projects/${enc(projectId)}/share`, body, config),
  /** GET /api/projects/…/shares — Who a project is shared with. */
  shares: (projectId, config) => http.get(`/api/projects/${enc(projectId)}/shares`, config),
  /** DELETE /api/projects/…/shares/… — Stop sharing with a user. */
  revokeShare: (projectId, shareId, config) => http.delete(`/api/projects/${enc(projectId)}/shares/${enc(shareId)}`, config),
  /** PUT /api/projects/…/shares/… — Change a share's role. */
  updateShare: (projectId, shareId, body, config) => http.put(`/api/projects/${enc(projectId)}/shares/${enc(shareId)}`, body, config),
}

export const datasets = {
  /** GET /api/datasets/ — Dataset library of the current user. */
  list: (config) => http.get('/api/datasets/', config),
  /** POST /api/datasets/ — Create an empty dataset group (name via config.params). */
  create: (body, config) => http.post('/api/datasets/', body, config),
  /** GET /api/datasets/tags/suggestions — Tags already in use. */
  tagSuggestions: (config) => http.get('/api/datasets/tags/suggestions', config),
  /** DELETE /api/datasets/… — Delete a dataset and its files. */
  remove: (datasetId, config) => http.delete(`/api/datasets/${enc(datasetId)}`, config),
  /** GET /api/datasets/… — One dataset. */
  get: (datasetId, config) => http.get(`/api/datasets/${enc(datasetId)}`, config),
  /** PATCH /api/datasets/… — Rename or describe a dataset. */
  update: (datasetId, body, config) => http.patch(`/api/datasets/${enc(datasetId)}`, body, config),
  /** POST /api/datasets/…/archive — Archive or unarchive a dataset. */
  toggleArchive: (datasetId, body, config) => http.post(`/api/datasets/${enc(datasetId)}/archive`, body, config),
  /** DELETE /api/datasets/…/assign/… — Detach a dataset from a project. */
  unassign: (datasetId, projectId, config) => http.delete(`/api/datasets/${enc(datasetId)}/assign/${enc(projectId)}`, config),
  /** POST /api/datasets/…/assign/… — Attach a dataset to a project. */
  assign: (datasetId, projectId, body, config) => http.post(`/api/datasets/${enc(datasetId)}/assign/${enc(projectId)}`, body, config),
  /** PATCH /api/datasets/…/class-names — Display names for class labels. */
  setClassNames: (datasetId, body, config) => http.patch(`/api/datasets/${enc(datasetId)}/class-names`, body, config),
  /** POST /api/datasets/…/files — Upload a file into a dataset (params.role). */
  uploadFile: (datasetId, body, config) => http.post(`/api/datasets/${enc(datasetId)}/files`, body, config),
  /** DELETE /api/datasets/…/files/… — Remove a file from a dataset. */
  deleteFile: (datasetId, fileId, config) => http.delete(`/api/datasets/${enc(datasetId)}/files/${enc(fileId)}`, config),
  /** GET /api/datasets/…/files/…/preview — First rows of a file. */
  previewFile: (datasetId, fileId, config) => http.get(`/api/datasets/${enc(datasetId)}/files/${enc(fileId)}/preview`, config),
  /** GET /api/datasets/…/metadata-columns — Columns of the metadata file. */
  metadataColumns: (datasetId, config) => http.get(`/api/datasets/${enc(datasetId)}/metadata-columns`, config),
  /** POST /api/datasets/…/scan — Recompute dataset statistics. */
  scan: (datasetId, body, config) => http.post(`/api/datasets/${enc(datasetId)}/scan`, body, config),
  /** PATCH /api/datasets/…/tags — Replace the tags of a dataset. */
  setTags: (datasetId, body, config) => http.patch(`/api/datasets/${enc(datasetId)}/tags`, body, config),
  /** GET /api/datasets/…/versions — Version history. */
  versions: (datasetId, config) => http.get(`/api/datasets/${enc(datasetId)}/versions`, config),
  /** POST /api/datasets/…/versions/…/restore — Restore a previous version. */
  restoreVersion: (datasetId, versionId, body, config) => http.post(`/api/datasets/${enc(datasetId)}/versions/${enc(versionId)}/restore`, body, config),
  /** POST /api/datasets/…/y-from-metadata — Build a label file from a metadata column. */
  yFromMetadata: (datasetId, body, config) => http.post(`/api/datasets/${enc(datasetId)}/y-from-metadata`, body, config),
}

export const samples = {
  /** GET /api/samples/ — Bundled demo datasets. */
  list: (config) => http.get('/api/samples/', config),
  /** POST /api/samples/…/load — Create a project from a demo dataset. */
  load: (sampleId, body, config) => http.post(`/api/samples/${enc(sampleId)}/load`, body, config),
}

export const analysis = {
  /** POST /api/analysis/…/batch — Launch a parameter sweep. */
  runBatch: (projectId, body, config) => http.post(`/api/analysis/${enc(projectId)}/batch`, body, config),
  /** GET /api/analysis/…/jobs — Jobs of a project. */
  listJobs: (projectId, config) => http.get(`/api/analysis/${enc(projectId)}/jobs`, config),
  /** GET /api/analysis/…/jobs/duplicates — Groups of jobs with identical configuration. */
  duplicates: (projectId, config) => http.get(`/api/analysis/${enc(projectId)}/jobs/duplicates`, config),
  /** DELETE /api/analysis/…/jobs/… — Delete a job. */
  deleteJob: (projectId, jobId, config) => http.delete(`/api/analysis/${enc(projectId)}/jobs/${enc(jobId)}`, config),
  /** GET /api/analysis/…/jobs/… — Job status summary. */
  job: (projectId, jobId, config) => http.get(`/api/analysis/${enc(projectId)}/jobs/${enc(jobId)}`, config),
  /** POST /api/analysis/…/jobs/…/cancel — Cancel a pending or running job. */
  cancelJob: (projectId, jobId, body, config) => http.post(`/api/analysis/${enc(projectId)}/jobs/${enc(jobId)}/cancel`, body, config),
  /** GET /api/analysis/…/jobs/…/config — Configuration a job was launched with. */
  jobConfig: (projectId, jobId, config) => http.get(`/api/analysis/${enc(projectId)}/jobs/${enc(jobId)}/config`, config),
  /** GET /api/analysis/…/jobs/…/detail — Best model and summary of a completed job. */
  jobDetail: (projectId, jobId, config) => http.get(`/api/analysis/${enc(projectId)}/jobs/${enc(jobId)}/detail`, config),
  /** GET /api/analysis/…/jobs/…/logs — Console log; pass params.offset to fetch only new output. */
  jobLogs: (projectId, jobId, config) => http.get(`/api/analysis/${enc(projectId)}/jobs/${enc(jobId)}/logs`, config),
  /** GET /api/analysis/…/jobs/…/progress — Structured progress of a running job. */
  jobProgress: (projectId, jobId, config) => http.get(`/api/analysis/${enc(projectId)}/jobs/${enc(jobId)}/progress`, config),
  /** POST /api/analysis/…/jobs/…/rerun — Launch the same configuration again. */
  rerunJob: (projectId, jobId, body, config) => http.post(`/api/analysis/${enc(projectId)}/jobs/${enc(jobId)}/rerun`, body, config),
  /** GET /api/analysis/…/jobs/…/results — Full results (population, tracking); can be large. */
  jobResults: (projectId, jobId, config) => http.get(`/api/analysis/${enc(projectId)}/jobs/${enc(jobId)}/results`, config),
  /** GET /api/analysis/…/jobs/…/stability — Feature stability across the population. */
  jobStability: (projectId, jobId, config) => http.get(`/api/analysis/${enc(projectId)}/jobs/${enc(jobId)}/stability`, config),
  /** POST /api/analysis/…/jobs/…/validate — Score an external dataset with a job's best model. */
  validateJob: (projectId, jobId, body, config) => http.post(`/api/analysis/${enc(projectId)}/jobs/${enc(jobId)}/validate`, body, config),
  /** POST /api/analysis/…/run — Launch one analysis job. */
  run: (projectId, body, config) => http.post(`/api/analysis/${enc(projectId)}/run`, body, config),
}

export const dataExplore = {
  /** POST /api/data-explore/msp-annotations — Taxonomy annotations for MSP feature names. */
  mspAnnotations: (body, config) => http.post('/api/data-explore/msp-annotations', body, config),
  /** GET /api/data-explore/reference-networks/list — Bundled reference networks. */
  referenceNetworks: (config) => http.get('/api/data-explore/reference-networks/list', config),
  /** GET /api/data-explore/…/barcode-data — Per-sample values of selected features. */
  barcode: (projectId, config) => http.get(`/api/data-explore/${enc(projectId)}/barcode-data`, config),
  /** GET /api/data-explore/…/class-heatmap — Class-level heatmap of top features. */
  classHeatmap: (projectId, config) => http.get(`/api/data-explore/${enc(projectId)}/class-heatmap`, config),
  /** GET /api/data-explore/…/coabundance-network — Co-abundance network. */
  coabundanceNetwork: (projectId, config) => http.get(`/api/data-explore/${enc(projectId)}/coabundance-network`, config),
  /** GET /api/data-explore/…/dual-network — Per-class co-abundance networks. */
  dualNetwork: (projectId, config) => http.get(`/api/data-explore/${enc(projectId)}/dual-network`, config),
  /** POST /api/data-explore/…/enrichment — Enrichment of a signature against the background. */
  enrichment: (projectId, body, config) => http.post(`/api/data-explore/${enc(projectId)}/enrichment`, body, config),
  /** GET /api/data-explore/…/external-networks — Uploaded external networks. */
  externalNetworks: (projectId, config) => http.get(`/api/data-explore/${enc(projectId)}/external-networks`, config),
  /** POST /api/data-explore/…/external-networks — Upload an external network. */
  uploadExternalNetwork: (projectId, body, config) => http.post(`/api/data-explore/${enc(projectId)}/external-networks`, body, config),
  /** DELETE /api/data-explore/…/external-networks/… — Delete an external network. */
  deleteExternalNetwork: (projectId, networkId, config) => http.delete(`/api/data-explore/${enc(projectId)}/external-networks/${enc(networkId)}`, config),
  /** POST /api/data-explore/…/fbm-module-filter — Models of the family of best models touching given modules. */
  fbmModuleFilter: (projectId, body, config) => http.post(`/api/data-explore/${enc(projectId)}/fbm-module-filter`, body, config),
  /** GET /api/data-explore/…/feature-abundance — Abundance distribution of features by class. */
  featureAbundance: (projectId, config) => http.get(`/api/data-explore/${enc(projectId)}/feature-abundance`, config),
  /** GET /api/data-explore/…/feature-stats — Per-feature statistics and tests. */
  featureStats: (projectId, config) => http.get(`/api/data-explore/${enc(projectId)}/feature-stats`, config),
  /** GET /api/data-explore/…/insights/… — Automatic biological reading of a job. */
  insights: (projectId, jobId, config) => http.get(`/api/data-explore/${enc(projectId)}/insights/${enc(jobId)}`, config),
  /** GET /api/data-explore/…/ordination — PCoA / t-SNE / UMAP coordinates. */
  ordination: (projectId, config) => http.get(`/api/data-explore/${enc(projectId)}/ordination`, config),
  /** GET /api/data-explore/…/summary — Dataset summary. */
  summary: (projectId, config) => http.get(`/api/data-explore/${enc(projectId)}/summary`, config),
}

export const metaAnalysis = {
  /** POST /api/meta-analysis/compare — Compare jobs across projects. */
  compare: (body, config) => http.post('/api/meta-analysis/compare', body, config),
  /** GET /api/meta-analysis/searchable-jobs — Completed jobs available for comparison. */
  searchableJobs: (config) => http.get('/api/meta-analysis/searchable-jobs', config),
}

export const signatureZoo = {
  /** GET /api/signature-zoo/ — Published signatures. */
  list: (config) => http.get('/api/signature-zoo/', config),
  /** GET /api/signature-zoo/compare — Compare signatures (params.ids). */
  compare: (config) => http.get('/api/signature-zoo/compare', config),
}

export const dashboard = {
  /** GET /api/dashboard/ — Cross-project dashboard. */
  get: (config) => http.get('/api/dashboard/', config),
}

export const templates = {
  /** GET /api/templates/ — Parameter templates (admin). */
  list: (config) => http.get('/api/templates/', config),
  /** POST /api/templates/ — Create a parameter template. */
  create: (body, config) => http.post('/api/templates/', body, config),
  /** GET /api/templates/public — Parameter templates offered to users. */
  listPublic: (config) => http.get('/api/templates/public', config),
  /** DELETE /api/templates/… — Delete a parameter template. */
  remove: (templateId, config) => http.delete(`/api/templates/${enc(templateId)}`, config),
}

export const webhooks = {
  /** GET /api/webhooks/ — Webhooks of the current user. */
  list: (config) => http.get('/api/webhooks/', config),
  /** POST /api/webhooks/ — Register a webhook (secret shown once). */
  create: (body, config) => http.post('/api/webhooks/', body, config),
  /** DELETE /api/webhooks/… — Delete a webhook. */
  remove: (webhookId, config) => http.delete(`/api/webhooks/${enc(webhookId)}`, config),
  /** POST /api/webhooks/…/test — Send a test event. */
  test: (webhookId, body, config) => http.post(`/api/webhooks/${enc(webhookId)}/test`, body, config),
}

export const admin = {
  /** GET /api/admin/audit-log — Audit log entries (filters via config.params). */
  auditLog: (config) => http.get('/api/admin/audit-log', config),
  /** POST /api/admin/backup — Create a full backup (description via config.params). */
  createBackup: (body, config) => http.post('/api/admin/backup', body, config),
  /** GET /api/admin/backup/download/… — Download a backup archive (use responseType: "blob"). */
  downloadBackup: (backupId, config) => http.get(`/api/admin/backup/download/${enc(backupId)}`, config),
  /** GET /api/admin/backup/list — List backups. */
  listBackups: (config) => http.get('/api/admin/backup/list', config),
  /** DELETE /api/admin/backup/… — Delete a backup. */
  deleteBackup: (backupId, config) => http.delete(`/api/admin/backup/${enc(backupId)}`, config),
  /** GET /api/admin/defaults — Server-wide parameter defaults. */
  getDefaults: (config) => http.get('/api/admin/defaults', config),
  /** PUT /api/admin/defaults — Replace server-wide parameter defaults. */
  setDefaults: (body, config) => http.put('/api/admin/defaults', body, config),
  /** POST /api/admin/restore?mode=… — Restore from an uploaded archive; mode is "replace" or "merge". */
  restoreBackup: (mode, body, config) => http.post(`/api/admin/restore?mode=${enc(mode)}`, body, config),
  /** POST /api/admin/retention/run — Preview (params.dry_run=true) or run the data-retention clean-up. */
  runRetention: (body, config) => http.post('/api/admin/retention/run', body, config),
  /** GET /api/admin/scitq — scitq settings (the token itself is never returned). */
  getScitq: (config) => http.get('/api/admin/scitq', config),
  /** PUT /api/admin/scitq — Update scitq settings. */
  setScitq: (body, config) => http.put('/api/admin/scitq', body, config),
  /** POST /api/admin/scitq/test — Test the scitq connection. */
  testScitq: (body, config) => http.post('/api/admin/scitq/test', body, config),
  /** GET /api/admin/users — All users. */
  listUsers: (config) => http.get('/api/admin/users', config),
  /** POST /api/admin/users — Create an account (the only way when self-registration is off). */
  createUser: (body, config) => http.post('/api/admin/users', body, config),
  /** DELETE /api/admin/users/… — Delete a user. */
  deleteUser: (userId, config) => http.delete(`/api/admin/users/${enc(userId)}`, config),
  /** PATCH /api/admin/users/… — Change a user's active/admin flags. */
  updateUser: (userId, body, config) => http.patch(`/api/admin/users/${enc(userId)}`, body, config),
}

export const publicShare = {
  /** GET /api/public/… — Project behind a public link. */
  get: (token, config) => http.get(`/api/public/${enc(token)}`, config),
  /** GET /api/public/…/jobs/…/results — Results of a job behind a public link. */
  jobResults: (token, jobId, config) => http.get(`/api/public/${enc(token)}/jobs/${enc(jobId)}/results`, config),
}

export const system = {
  /** GET /health — Liveness and versions. */
  health: (config) => http.get('/health', config),
}

export const api = { auth, projects, datasets, samples, analysis, dataExplore, metaAnalysis, signatureZoo, dashboard, templates, webhooks, admin, publicShare, system }

export default api
