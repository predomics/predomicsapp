<template>
  <div class="admin-page">
    <h2>{{ $t('admin.userAdmin') }}</h2>

    <div v-if="loading" class="loading">{{ $t('admin.loadingUsers') }}</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>

    <table v-else class="user-table">
      <thead>
        <tr>
          <th>{{ $t('admin.colEmail') }}</th>
          <th>{{ $t('admin.colName') }}</th>
          <th>{{ $t('admin.colActive') }}</th>
          <th>{{ $t('admin.colAdmin') }}</th>
          <th>{{ $t('admin.colProjects') }}</th>
          <th>{{ $t('admin.colDatasets') }}</th>
          <th>{{ $t('admin.colCreated') }}</th>
          <th>{{ $t('admin.colActions') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in users" :key="u.id" :class="{ inactive: !u.is_active }">
          <td>{{ u.email }}</td>
          <td>{{ u.full_name || '—' }}</td>
          <td>
            <button
              class="toggle-btn"
              :class="u.is_active ? 'on' : 'off'"
              @click="toggleActive(u)"
              :disabled="u.id === currentUser.id"
            >
              {{ u.is_active ? $t('admin.yes') : $t('admin.no') }}
            </button>
          </td>
          <td>
            <button
              class="toggle-btn"
              :class="u.is_admin ? 'on' : 'off'"
              @click="toggleAdmin(u)"
              :disabled="u.id === currentUser.id"
            >
              {{ u.is_admin ? $t('admin.yes') : $t('admin.no') }}
            </button>
          </td>
          <td class="count">{{ u.project_count }}</td>
          <td class="count">{{ u.dataset_count }}</td>
          <td class="date">{{ new Date(u.created_at).toLocaleDateString() }}</td>
          <td>
            <button
              class="btn-delete"
              @click="deleteUser(u)"
              :disabled="u.id === currentUser.id"
            >
              {{ $t('admin.delete') }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- Default Parameters Section -->
    <h2 class="section-title">{{ $t('admin.defaultParams') }}</h2>
    <p class="section-desc">{{ $t('admin.defaultParamsDesc') }}</p>

    <div v-if="defaultsLoading" class="loading">{{ $t('admin.loadingDefaults') }}</div>
    <div v-else class="defaults-grid">
      <div v-for="(field, idx) in defaultFields" :key="idx" class="default-field">
        <label :for="'df-' + idx">{{ field.label }}</label>
        <select v-if="field.options" :id="'df-' + idx" v-model="defaults[field.key]">
          <option :value="undefined">{{ $t('admin.useHardcoded') }}</option>
          <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
        </select>
        <input
          v-else-if="field.type === 'number'"
          :id="'df-' + idx"
          type="number"
          v-model.number="defaults[field.key]"
          :placeholder="field.placeholder || ''"
        />
        <select v-else-if="field.type === 'boolean'" :id="'df-' + idx" v-model="defaults[field.key]">
          <option :value="undefined">{{ $t('admin.useHardcoded') }}</option>
          <option :value="true">{{ $t('admin.yes') }}</option>
          <option :value="false">{{ $t('admin.no') }}</option>
        </select>
        <input
          v-else
          :id="'df-' + idx"
          type="text"
          v-model="defaults[field.key]"
          :placeholder="field.placeholder || ''"
        />
      </div>
    </div>
    <div class="defaults-actions">
      <button class="btn-save" @click="saveDefaults" :disabled="defaultsSaving">
        {{ defaultsSaving ? $t('admin.saving') : $t('admin.saveDefaults') }}
      </button>
      <button class="btn-reset" @click="resetDefaults">{{ $t('admin.resetAll') }}</button>
      <span v-if="defaultsSaved" class="save-ok">{{ $t('admin.saved') }}</span>
    </div>

    <!-- Project Templates Section -->
    <h2 class="section-title">{{ $t('admin.projectTemplates') }}</h2>
    <p class="section-desc">{{ $t('admin.templatesDesc') }}</p>

    <div class="template-create">
      <input v-model="tplName" :placeholder="$t('admin.templateName')" class="tpl-input" />
      <input v-model="tplDesc" :placeholder="$t('admin.templateDesc')" class="tpl-input tpl-desc" />
      <button class="btn-save" @click="createTemplate" :disabled="!tplName.trim() || tplSaving">
        {{ tplSaving ? $t('admin.saving') : $t('admin.createTemplate') }}
      </button>
    </div>
    <p class="section-desc">{{ $t('admin.templateConfigHint') }}</p>

    <div v-if="tplTemplates.length > 0" class="tpl-list">
      <div v-for="t in tplTemplates" :key="t.id" class="tpl-card">
        <div class="tpl-info">
          <strong>{{ t.name }}</strong>
          <span v-if="t.description" class="tpl-desc-text">{{ t.description }}</span>
        </div>
        <button class="btn-delete" @click="deleteTemplate(t)">{{ $t('admin.delete') }}</button>
      </div>
    </div>
    <div v-else class="empty-state">{{ $t('admin.noTemplates') }}</div>

    <!-- Audit Log Section -->
    <h2 class="section-title">{{ $t('admin.auditLog') }}</h2>
    <p class="section-desc">{{ $t('admin.auditLogDesc') }}</p>

    <div class="audit-filters">
      <select v-model="auditAction" @change="fetchAuditLog(1)" class="audit-select">
        <option value="">{{ $t('admin.allActions') }}</option>
        <option v-for="a in auditActions" :key="a" :value="a">{{ a }}</option>
      </select>
      <button class="btn-reset" @click="auditAction = ''; fetchAuditLog(1)">{{ $t('admin.clear') }}</button>
      <span class="audit-total" v-if="auditTotal > 0">{{ auditTotal }} {{ $t('admin.entries') }}</span>
    </div>

    <table v-if="auditEntries.length > 0" class="user-table audit-table">
      <thead>
        <tr>
          <th>{{ $t('admin.colTime') }}</th>
          <th>{{ $t('admin.colUser') }}</th>
          <th>{{ $t('admin.colAction') }}</th>
          <th>{{ $t('admin.colResource') }}</th>
          <th>{{ $t('admin.colDetails') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in auditEntries" :key="e.id">
          <td class="date">{{ new Date(e.created_at).toLocaleString() }}</td>
          <td>{{ e.user_email || '—' }}</td>
          <td><span class="audit-action">{{ e.action }}</span></td>
          <td>{{ e.resource_type }}{{ e.resource_id ? ` #${e.resource_id.slice(0, 8)}` : '' }}</td>
          <td class="audit-details">{{ e.details ? JSON.stringify(e.details).slice(0, 80) : '—' }}</td>
        </tr>
      </tbody>
    </table>

    <div v-if="auditTotal > auditPerPage" class="audit-pagination">
      <button :disabled="auditPage <= 1" @click="fetchAuditLog(auditPage - 1)">{{ $t('admin.prev') }}</button>
      <span>{{ $t('admin.page') }} {{ auditPage }} / {{ Math.ceil(auditTotal / auditPerPage) }}</span>
      <button :disabled="auditPage >= Math.ceil(auditTotal / auditPerPage)" @click="fetchAuditLog(auditPage + 1)">{{ $t('admin.next') }}</button>
    </div>

    <!-- System Backup & Restore Section -->
    <h2 class="section-title">{{ $t('admin.backupRestore') }}</h2>
    <p class="section-desc">{{ $t('admin.backupRestoreDesc') }}</p>

    <div class="backup-actions">
      <div class="backup-create">
        <input v-model="backupDescription" :placeholder="$t('admin.backupDescPlaceholder')" class="backup-desc-input" />
        <button class="btn-save" @click="createBackup" :disabled="backupCreating">
          {{ backupCreating ? $t('admin.creating') : $t('admin.createBackup') }}
        </button>
      </div>
      <div class="backup-restore">
        <label class="btn-restore">
          {{ $t('admin.restoreFromFile') }}
          <input type="file" accept=".tar.gz,.tgz" @change="handleRestoreFile" style="display:none" />
        </label>
        <select v-model="restoreMode" class="restore-mode-select">
          <option value="replace">{{ $t('admin.replaceMode') }}</option>
          <option value="merge">{{ $t('admin.mergeMode') }}</option>
        </select>
      </div>
    </div>

    <div v-if="backupMessage" :class="['backup-msg', backupMsgType]">{{ backupMessage }}</div>

    <div v-if="backupLoading" class="loading">{{ $t('admin.loadingBackups') }}</div>
    <table v-else-if="backups.length > 0" class="user-table backup-table">
      <thead>
        <tr>
          <th>{{ $t('admin.colDate') }}</th>
          <th>{{ $t('admin.colDescription') }}</th>
          <th>{{ $t('admin.colSize') }}</th>
          <th>{{ $t('admin.colRecords') }}</th>
          <th>{{ $t('admin.colActions') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in backups" :key="b.backup_id || b.filename">
          <td class="date">{{ formatBackupDate(b.created_at) }}</td>
          <td>{{ b.description || '—' }}</td>
          <td>{{ formatSize(b.size_bytes) }}</td>
          <td class="count">
            <span v-if="b.table_counts">
              {{ Object.values(b.table_counts).reduce((a, c) => a + c, 0) }}
            </span>
            <span v-else>—</span>
          </td>
          <td>
            <button class="btn-download" @click="downloadBackup(b)">{{ $t('admin.download') }}</button>
            <button class="btn-delete" @click="deleteBackupConfirm(b)">{{ $t('admin.delete') }}</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else-if="!backupLoading" class="empty-state">{{ $t('admin.noBackups') }}</div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from 'axios'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'

const { t } = useI18n()
const auth = useAuthStore()
const currentUser = auth.user

const users = ref([])
const loading = ref(true)
const error = ref('')

// Default parameters
const defaults = reactive({})
const defaultsLoading = ref(false)
const defaultsSaving = ref(false)
const defaultsSaved = ref(false)

const defaultFields = [
  { key: 'general.algo', label: 'Algorithm', options: ['ga', 'beam', 'mcmc'] },
  { key: 'general.language', label: 'Languages', placeholder: 'bin,ter,ratio' },
  { key: 'general.data_type', label: 'Data Types', placeholder: 'raw,prev' },
  { key: 'general.fit', label: 'Fitness Function', options: ['auc', 'specificity', 'sensitivity', 'mcc', 'f1_score', 'g_mean'] },
  { key: 'general.seed', label: 'Random Seed', type: 'number', placeholder: '42' },
  { key: 'general.thread_number', label: 'Threads', type: 'number', placeholder: '4' },
  { key: 'ga.population_size', label: 'Population Size', type: 'number', placeholder: '5000' },
  { key: 'ga.max_epochs', label: 'Max Epochs', type: 'number', placeholder: '200' },
  { key: 'ga.k_min', label: 'Min Features (k)', type: 'number', placeholder: '1' },
  { key: 'ga.k_max', label: 'Max Features (k)', type: 'number', placeholder: '200' },
  { key: 'voting.vote', label: 'Enable Voting', type: 'boolean' },
  { key: 'importance.compute_importance', label: 'Compute Importance', type: 'boolean' },
  { key: 'data.holdout_ratio', label: 'Holdout Ratio', type: 'number', placeholder: '0.20' },
  { key: 'data.feature_minimal_prevalence_pct', label: 'Min Prevalence %', type: 'number', placeholder: '10' },
]

async function fetchDefaults() {
  defaultsLoading.value = true
  try {
    const { data } = await axios.get('/api/admin/defaults')
    Object.assign(defaults, data)
  } catch { /* ignore */ }
  finally { defaultsLoading.value = false }
}

async function saveDefaults() {
  defaultsSaving.value = true
  defaultsSaved.value = false
  try {
    // Strip undefined values
    const clean = {}
    for (const [k, v] of Object.entries(defaults)) {
      if (v !== undefined && v !== '' && v !== null) clean[k] = v
    }
    await axios.put('/api/admin/defaults', clean)
    // Reload to confirm
    Object.keys(defaults).forEach(k => delete defaults[k])
    Object.assign(defaults, clean)
    defaultsSaved.value = true
    setTimeout(() => { defaultsSaved.value = false }, 3000)
  } catch (e) {
    alert(t('admin.saveFailed', { error: e.response?.data?.detail || e.message }))
  } finally {
    defaultsSaving.value = false
  }
}

function resetDefaults() {
  if (!confirm(t('admin.resetConfirm'))) return
  Object.keys(defaults).forEach(k => delete defaults[k])
  saveDefaults()
}

async function fetchUsers() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await axios.get('/api/admin/users')
    users.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to load users'
  } finally {
    loading.value = false
  }
}

async function toggleActive(u) {
  try {
    const { data } = await axios.patch(`/api/admin/users/${u.id}`, {
      is_active: !u.is_active,
    })
    Object.assign(u, data)
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to update user')
  }
}

async function toggleAdmin(u) {
  try {
    const { data } = await axios.patch(`/api/admin/users/${u.id}`, {
      is_admin: !u.is_admin,
    })
    Object.assign(u, data)
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to update user')
  }
}

async function deleteUser(u) {
  if (!confirm(t('admin.deleteUserConfirm', { email: u.email }))) return
  try {
    await axios.delete(`/api/admin/users/${u.id}`)
    users.value = users.value.filter(x => x.id !== u.id)
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to delete user')
  }
}

// ---------------------------------------------------------------------------
// Backup & Restore
// ---------------------------------------------------------------------------

const backups = ref([])
const backupLoading = ref(false)
const backupCreating = ref(false)
const backupDescription = ref('')
const backupMessage = ref('')
const backupMsgType = ref('success')
const restoreMode = ref('replace')

async function fetchBackups() {
  backupLoading.value = true
  try {
    const { data } = await axios.get('/api/admin/backup/list')
    backups.value = data
  } catch { /* ignore */ }
  finally { backupLoading.value = false }
}

async function createBackup() {
  backupCreating.value = true
  backupMessage.value = ''
  try {
    const { data } = await axios.post('/api/admin/backup', null, {
      params: { description: backupDescription.value },
    })
    backupMessage.value = `Backup created: ${data.filename} (${formatSize(data.size_bytes)})`
    backupMsgType.value = 'success'
    backupDescription.value = ''
    await fetchBackups()
  } catch (e) {
    backupMessage.value = e.response?.data?.detail || 'Backup failed'
    backupMsgType.value = 'error'
  } finally {
    backupCreating.value = false
  }
}

async function downloadBackup(b) {
  try {
    const resp = await axios.get(`/api/admin/backup/download/${b.backup_id}`, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = b.filename
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    backupMessage.value = 'Download failed'
    backupMsgType.value = 'error'
  }
}

async function deleteBackupConfirm(b) {
  if (!confirm(`Delete backup "${b.filename}"? This cannot be undone.`)) return
  try {
    await axios.delete(`/api/admin/backup/${b.backup_id}`)
    backupMessage.value = 'Backup deleted'
    backupMsgType.value = 'success'
    await fetchBackups()
  } catch (e) {
    backupMessage.value = e.response?.data?.detail || 'Delete failed'
    backupMsgType.value = 'error'
  }
}

async function handleRestoreFile(event) {
  const file = event.target.files[0]
  if (!file) return

  const modeText = restoreMode.value === 'replace'
    ? 'REPLACE all existing data'
    : 'MERGE with existing data (skip conflicts)'

  if (!confirm(`Restore from "${file.name}"?\n\nThis will ${modeText}.\nAre you sure?`)) {
    event.target.value = ''
    return
  }

  const form = new FormData()
  form.append('file', file)

  backupMessage.value = 'Restoring... This may take a while.'
  backupMsgType.value = 'success'

  try {
    const { data } = await axios.post(`/api/admin/restore?mode=${restoreMode.value}`, form)
    const counts = Object.entries(data.restored_counts || {})
      .filter(([, c]) => c > 0)
      .map(([t, c]) => `${t}: ${c}`)
      .join(', ')
    backupMessage.value = `Restored successfully (${data.mode} mode). ${counts}`
    backupMsgType.value = 'success'
    await fetchBackups()
    await fetchUsers()
  } catch (e) {
    backupMessage.value = e.response?.data?.detail || 'Restore failed'
    backupMsgType.value = 'error'
  }
  event.target.value = ''
}

function formatSize(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatBackupDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

const tplTemplates = ref([])
const tplName = ref('')
const tplDesc = ref('')
const tplSaving = ref(false)

async function fetchTemplates() {
  try {
    const { data } = await axios.get('/api/templates/')
    tplTemplates.value = data
  } catch { /* ignore */ }
}

async function createTemplate() {
  if (!tplName.value.trim()) return
  tplSaving.value = true
  try {
    // Use current defaults as the template config
    const clean = {}
    for (const [k, v] of Object.entries(defaults)) {
      if (v !== undefined && v !== '' && v !== null) clean[k] = v
    }
    await axios.post('/api/templates/', {
      name: tplName.value.trim(),
      description: tplDesc.value.trim(),
      config: clean,
    })
    tplName.value = ''
    tplDesc.value = ''
    await fetchTemplates()
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to create template')
  } finally {
    tplSaving.value = false
  }
}

async function deleteTemplate(t) {
  if (!confirm(`Delete template "${t.name}"?`)) return
  try {
    await axios.delete(`/api/templates/${t.id}`)
    await fetchTemplates()
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to delete template')
  }
}

// ---------------------------------------------------------------------------
// Audit Log
// ---------------------------------------------------------------------------

const auditEntries = ref([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditPerPage = 50
const auditAction = ref('')
const auditActions = [
  'login', 'register', 'job.launch', 'job.delete',
  'dataset.upload', 'dataset.delete', 'project.create', 'project.delete',
  'share.create', 'share.revoke', 'admin.user_delete',
]

async function fetchAuditLog(page = 1) {
  auditPage.value = page
  try {
    const params = { page, per_page: auditPerPage }
    if (auditAction.value) params.action = auditAction.value
    const { data } = await axios.get('/api/admin/audit-log', { params })
    auditEntries.value = data.entries
    auditTotal.value = data.total
  } catch { /* ignore */ }
}

onMounted(() => {
  fetchUsers()
  fetchDefaults()
  fetchBackups()
  fetchTemplates()
  fetchAuditLog()
})
</script>

<style scoped>
.admin-page {
  max-width: 1100px;
  margin: 0 auto;
}

.admin-page h2 {
  margin-bottom: 1.5rem;
  color: var(--text-primary);
}

.loading, .error-msg {
  text-align: center;
  padding: 2rem;
  color: var(--text-muted);
}

.error-msg { color: var(--danger); }

.user-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--bg-card);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: var(--shadow);
}

.user-table th, .user-table td {
  padding: 0.6rem 0.75rem;
  text-align: left;
  font-size: 0.85rem;
  border-bottom: 1px solid var(--border-lighter);
}

.user-table th {
  background: var(--bg-badge);
  color: var(--text-secondary);
  font-weight: 600;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.user-table tr.inactive td {
  opacity: 0.5;
}

.count { text-align: center; }
.date { white-space: nowrap; color: var(--text-muted); }

.toggle-btn {
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.78rem;
  font-weight: 500;
  background: var(--bg-input);
  color: var(--text-body);
  transition: all 0.15s;
}

.toggle-btn.on {
  background: var(--success-bg);
  color: var(--success-dark);
  border-color: var(--success);
}

.toggle-btn.off {
  background: var(--bg-input);
  color: var(--text-muted);
}

.toggle-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-delete {
  padding: 0.2rem 0.5rem;
  background: transparent;
  border: 1px solid var(--danger);
  color: var(--danger);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.78rem;
  transition: all 0.15s;
}

.btn-delete:hover {
  background: var(--danger-bg);
}

.btn-delete:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* Default Parameters Section */
.section-title {
  margin-top: 2.5rem;
  margin-bottom: 0.5rem;
}
.section-desc {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-bottom: 1rem;
}
.defaults-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.default-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.default-field label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-secondary);
}
.default-field input,
.default-field select {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
}
.defaults-actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}
.btn-save {
  padding: 0.4rem 1.25rem;
  background: var(--accent);
  color: var(--accent-text);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
}
.btn-save:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-reset {
  padding: 0.4rem 1rem;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
}
.btn-reset:hover { border-color: var(--text-secondary); }
.save-ok {
  font-size: 0.85rem;
  color: var(--success-dark, #2e7d32);
  font-weight: 500;
}

/* Backup & Restore */
.backup-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 1rem;
  align-items: center;
}
.backup-create {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.backup-desc-input {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
  width: 220px;
}
.backup-restore {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-left: auto;
}
.btn-restore {
  padding: 0.4rem 1rem;
  background: var(--warning-bg, #fff3e0);
  color: var(--warning-dark, #e65100);
  border: 1px solid var(--warning, #ff9800);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
}
.btn-restore:hover { opacity: 0.85; }
.restore-mode-select {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
}
.backup-msg {
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.85rem;
  margin-bottom: 1rem;
}
.backup-msg.success {
  background: var(--success-bg, #e8f5e9);
  color: var(--success-dark, #2e7d32);
}
.backup-msg.error {
  background: var(--danger-bg, #ffebee);
  color: var(--danger, #c62828);
}
.backup-table { margin-bottom: 2rem; }
.btn-download {
  padding: 0.2rem 0.5rem;
  background: transparent;
  border: 1px solid var(--accent);
  color: var(--accent);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.78rem;
  margin-right: 0.3rem;
}
.btn-download:hover { background: var(--accent-faint, rgba(59, 130, 246, 0.08)); }
.empty-state {
  text-align: center;
  padding: 2rem;
  color: var(--text-muted);
  font-size: 0.9rem;
}

/* Templates */
.template-create {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  flex-wrap: wrap;
  align-items: center;
}
.tpl-input {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
  min-width: 160px;
}
.tpl-desc { flex: 1; }
.tpl-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-bottom: 1rem;
}
.tpl-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.75rem;
  background: var(--bg-card);
  border-radius: 6px;
  border: 1px solid var(--border-lighter);
}
.tpl-info {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}
.tpl-desc-text {
  font-size: 0.78rem;
  color: var(--text-muted);
}

/* Audit Log */
.audit-filters {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.75rem;
}
.audit-select {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
  min-width: 160px;
}
.audit-total {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-left: auto;
}
.audit-action {
  display: inline-block;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  font-size: 0.72rem;
  font-weight: 600;
  background: var(--bg-badge);
  color: var(--text-secondary);
}
.audit-details {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.75rem;
  color: var(--text-muted);
}
.audit-table { margin-bottom: 0.5rem; }
.audit-pagination {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  justify-content: center;
  padding: 0.5rem 0 1rem;
  font-size: 0.82rem;
  color: var(--text-secondary);
}
.audit-pagination button {
  padding: 0.3rem 0.8rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 0.8rem;
}
.audit-pagination button:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
</style>
