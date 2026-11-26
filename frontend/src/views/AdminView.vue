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
          <th v-if="hasVerifiedFlag">{{ $t('admin.colVerified') }}</th>
          <th>{{ $t('admin.colProjects') }}</th>
          <th>{{ $t('admin.colDatasets') }}</th>
          <th v-if="hasUsage">{{ $t('admin.colStorage') }}</th>
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
          <td v-if="hasVerifiedFlag">
            <button
              class="toggle-btn"
              :class="u.email_verified ? 'on' : 'off'"
              :aria-label="$t('admin.verifiedToggle', { email: u.email })"
              :aria-pressed="u.email_verified ? 'true' : 'false'"
              @click="toggleVerified(u)"
            >
              {{ u.email_verified ? $t('admin.yes') : $t('admin.no') }}
            </button>
          </td>
          <td class="count">{{ u.project_count }}</td>
          <td class="count">{{ u.dataset_count }}</td>
          <td v-if="hasUsage" class="count">{{ formatBytes(u.used_bytes) }}</td>
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

    <!-- Create an account (the only way in when self-registration is off) -->
    <form class="create-user" @submit.prevent="createUser" novalidate>
      <h3>{{ $t('admin.createUserTitle') }}</h3>
      <div class="create-user-grid">
        <div class="create-user-field">
          <label for="new-user-email">{{ $t('admin.colEmail') }}</label>
          <input id="new-user-email" v-model.trim="newUser.email" type="email" autocomplete="off" required />
        </div>
        <div class="create-user-field">
          <label for="new-user-name">{{ $t('admin.colName') }}</label>
          <input id="new-user-name" v-model.trim="newUser.full_name" type="text" autocomplete="off" />
        </div>
        <div class="create-user-field">
          <label for="new-user-password">{{ $t('admin.newUserPassword') }}</label>
          <input id="new-user-password" v-model="newUser.password" type="password" autocomplete="new-password" required aria-describedby="new-user-password-hint" />
          <span id="new-user-password-hint" class="scitq-hint">{{ $t('login.passwordHint', { n: 8 }) }}</span>
        </div>
        <label class="create-user-check">
          <input type="checkbox" v-model="newUser.is_admin" />
          {{ $t('admin.newUserAdmin') }}
        </label>
      </div>
      <p v-if="newUserError" class="error-msg" role="alert">{{ newUserError }}</p>
      <button type="submit" class="btn-save" :disabled="creatingUser || !newUser.email || !newUser.password">
        {{ creatingUser ? $t('admin.creating') : $t('admin.createUser') }}
      </button>
    </form>

    <!-- Data retention -->
    <h2 class="section-title">{{ $t('admin.retentionTitle') }}</h2>
    <p class="section-desc">{{ $t('admin.retentionDesc') }}</p>
    <div class="retention">
      <button type="button" class="btn-test" :disabled="retentionBusy" @click="runRetention(true)">
        {{ retentionBusy === 'preview' ? $t('common.loading') : $t('admin.retentionPreview') }}
      </button>
      <button type="button" class="btn-delete" :disabled="retentionBusy || !retentionResult || !retentionResult.dry_run" @click="runRetention(false)">
        {{ retentionBusy === 'run' ? $t('common.loading') : $t('admin.retentionRun') }}
      </button>
      <p v-if="retentionError" class="error-msg" role="alert">{{ retentionError }}</p>
      <div v-if="retentionResult" class="retention-result" role="status">
        <strong>{{ retentionResult.dry_run ? $t('admin.retentionPreviewResult') : $t('admin.retentionDone') }}</strong>
        <ul v-if="retentionLines.length">
          <li v-for="line in retentionLines" :key="line.key">{{ line.key }}: {{ line.value }}</li>
        </ul>
        <p v-else>{{ $t('admin.retentionNothing') }}</p>
      </div>
    </div>

    <!-- scitq Distributed Task Queue Section -->
    <h2 class="section-title">{{ $t('admin.scitqTitle') }}</h2>
    <p class="section-desc">{{ $t('admin.scitqDesc') }}</p>

    <div v-if="scitqLoading" class="loading">{{ $t('common.loading') }}</div>
    <div v-else class="scitq-section">
      <div class="scitq-status-bar">
        <span class="scitq-badge" :class="scitqConfig.enabled ? 'on' : 'off'">
          {{ scitqConfig.enabled ? $t('admin.scitqEnabled') : $t('admin.scitqDisabled') }}
        </span>
        <span v-if="!scitqConfig.package_installed" class="scitq-warning">
          {{ $t('admin.scitqNotInstalled') }}
        </span>
      </div>

      <div class="scitq-grid">
        <div class="scitq-field">
          <label for="scitq-server">{{ $t('admin.scitqServerLabel') }}</label>
          <input
            id="scitq-server"
            type="text"
            v-model="scitqForm.server"
            placeholder="scitq-server:5000"
          />
        </div>
        <div class="scitq-field">
          <label for="scitq-token">{{ $t('admin.scitqTokenLabel') }}</label>
          <input
            id="scitq-token"
            type="password"
            v-model="scitqForm.token"
            autocomplete="off"
            :placeholder="scitqTokenSet ? $t('admin.scitqTokenKeepPlaceholder') : $t('admin.scitqTokenPlaceholder')"
            aria-describedby="scitq-token-hint"
          />
          <p id="scitq-token-hint" class="scitq-hint">
            <template v-if="scitqTokenSet">
              {{ $t('admin.scitqTokenStored') }}
              <button type="button" class="btn-inline-danger" :disabled="scitqSaving" @click="clearScitqToken">{{ $t('admin.scitqTokenRemove') }}</button>
            </template>
            <template v-else>{{ $t('admin.scitqTokenNone') }}</template>
          </p>
        </div>
        <div class="scitq-field">
          <label for="scitq-container">{{ $t('admin.scitqContainerLabel') }}</label>
          <input
            id="scitq-container"
            type="text"
            v-model="scitqForm.container"
            placeholder="predomics-app:latest"
          />
        </div>
      </div>

      <div class="scitq-actions">
        <button class="btn-save" @click="saveScitq()" :disabled="scitqSaving">
          {{ scitqSaving ? $t('admin.saving') : $t('common.save') }}
        </button>
        <button class="btn-test" @click="testScitq" :disabled="scitqTesting || !scitqForm.server">
          {{ scitqTesting ? $t('admin.scitqTesting') : $t('admin.scitqTestConnection') }}
        </button>
        <span v-if="scitqSaved" class="save-ok">{{ $t('admin.saved') }}</span>
      </div>

      <div v-if="scitqTestResult" :class="['scitq-test-msg', scitqTestResult.ok ? 'success' : 'error']">
        <template v-if="scitqTestResult.ok">
          {{ $t('admin.scitqConnected') }}
          <span v-if="scitqTestResult.workers !== undefined">
            — {{ scitqTestResult.workers }} {{ $t('admin.scitqWorkers') }}
          </span>
        </template>
        <template v-else>
          {{ $t('admin.scitqConnectionFailed') }}: {{ scitqTestResult.error }}
        </template>
      </div>
    </div>

    <!-- Default Parameters Section -->
    <h2 class="section-title">{{ $t('admin.defaultParams') }}</h2>
    <p class="section-desc">{{ $t('admin.defaultParamsDesc') }}</p>

    <div v-if="defaultsLoading" class="loading">{{ $t('admin.loadingDefaults') }}</div>
    <div v-else class="defaults-grid">
      <div v-for="(field, idx) in defaultFields" :key="idx" class="default-field">
        <label :for="'df-' + idx">{{ fieldLabel(field) }}</label>
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
      <input :aria-label="$t('admin.templateName')" v-model="tplName" :placeholder="$t('admin.templateName')" class="tpl-input" />
      <input :aria-label="$t('admin.templateDesc')" v-model="tplDesc" :placeholder="$t('admin.templateDesc')" class="tpl-input tpl-desc" />
      <button class="btn-save" @click="createTemplate" :disabled="!tplName.trim() || tplSaving">
        {{ tplSaving ? $t('admin.saving') : $t('admin.createTemplate') }}
      </button>
    </div>
    <p class="section-desc">{{ $t('admin.templateConfigHint') }}</p>

    <div v-if="tplTemplates.length > 0" class="tpl-list">
      <div v-for="tpl in tplTemplates" :key="tpl.id" class="tpl-card">
        <div class="tpl-info">
          <strong>{{ tpl.name }}</strong>
          <span v-if="tpl.description" class="tpl-desc-text">{{ tpl.description }}</span>
        </div>
        <button class="btn-delete" @click="deleteTemplate(tpl)">{{ $t('admin.delete') }}</button>
      </div>
    </div>
    <div v-else class="empty-state">{{ $t('admin.noTemplates') }}</div>

    <!-- Audit Log Section -->
    <h2 class="section-title">{{ $t('admin.auditLog') }}</h2>
    <p class="section-desc">{{ $t('admin.auditLogDesc') }}</p>

    <div class="audit-filters">
      <select :aria-label="$t('admin.filterByAction')" v-model="auditAction" @change="fetchAuditLog(1)" class="audit-select">
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
        <input :aria-label="$t('admin.backupDescPlaceholder')" v-model="backupDescription" :placeholder="$t('admin.backupDescPlaceholder')" class="backup-desc-input" />
        <button class="btn-save" @click="createBackup" :disabled="backupCreating">
          {{ backupCreating ? $t('admin.creating') : $t('admin.createBackup') }}
        </button>
      </div>
      <div class="backup-restore">
        <label class="btn-restore">
          {{ $t('admin.restoreFromFile') }}
          <input type="file" accept=".tar.gz,.tgz" @change="handleRestoreFile" style="display:none" />
        </label>
        <select :aria-label="$t('admin.restoreModeLabel')" v-model="restoreMode" class="restore-mode-select">
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
import { formatBytes } from '../utils/format'
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { apiError } from '../utils/apiError'
import { useToast } from '../composables/useToast'
import { useConfirm } from '../composables/useConfirm'

const { toast } = useToast()
const { confirmDialog } = useConfirm()

const { t, te } = useI18n()
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

/** Label of a default-parameter field, in the user's language (falls back to the English label). */
function fieldLabel(field) {
  const paramKey = `params.${field.key}.label`
  if (te(paramKey)) return t(paramKey)
  const adminKey = `admin.defaultField.${field.key.replace('.', '_')}`
  return te(adminKey) ? t(adminKey) : field.label
}

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
    const { data } = await api.admin.getDefaults()
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
    await api.admin.setDefaults(clean)
    // Reload to confirm
    Object.keys(defaults).forEach(k => delete defaults[k])
    Object.assign(defaults, clean)
    defaultsSaved.value = true
    setTimeout(() => { defaultsSaved.value = false }, 3000)
  } catch (e) {
    toast.error(t('admin.saveFailed', { error: apiError(e) }))
  } finally {
    defaultsSaving.value = false
  }
}

async function resetDefaults() {
  if (!(await confirmDialog({ message: t('admin.resetConfirm'), danger: true }))) return
  Object.keys(defaults).forEach(k => delete defaults[k])
  saveDefaults()
}

async function fetchUsers() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.admin.listUsers()
    users.value = data
  } catch (e) {
    error.value = apiError(e)
  } finally {
    loading.value = false
  }
}

async function toggleActive(u) {
  try {
    const { data } = await api.admin.updateUser(u.id, {
      is_active: !u.is_active,
    })
    Object.assign(u, data)
  } catch (e) {
    toast.error(t('admin.err.updateUser', { error: apiError(e) }))
  }
}

// Columns that only newer servers report.
const hasVerifiedFlag = computed(() => users.value.some(u => typeof u.email_verified === 'boolean'))
const hasUsage = computed(() => users.value.some(u => typeof u.used_bytes === 'number'))

async function toggleVerified(u) {
  try {
    const { data } = await api.admin.updateUser(u.id, { email_verified: !u.email_verified })
    Object.assign(u, data)
  } catch (e) {
    toast.error(t('admin.err.updateUser', { error: apiError(e) }))
  }
}

// Create an account
const newUser = reactive({ email: '', full_name: '', password: '', is_admin: false })
const creatingUser = ref(false)
const newUserError = ref('')

async function createUser() {
  newUserError.value = ''
  creatingUser.value = true
  try {
    await api.admin.createUser({ ...newUser })
    toast.success(t('admin.userCreated', { email: newUser.email }))
    Object.assign(newUser, { email: '', full_name: '', password: '', is_admin: false })
    await fetchUsers()
  } catch (e) {
    newUserError.value = apiError(e)
  } finally {
    creatingUser.value = false
  }
}

// Data retention: preview first, then run exactly what was previewed.
const retentionBusy = ref('')
const retentionResult = ref(null)
const retentionError = ref('')
const retentionLines = computed(() => {
  const r = retentionResult.value
  if (!r) return []
  return Object.entries(r)
    .filter(([k, v]) => k !== 'dry_run' && (typeof v === 'number' || typeof v === 'string') && v !== 0 && v !== '')
    .map(([key, value]) => ({ key: key.replace(/_/g, ' '), value: /bytes/.test(key) ? formatBytes(value) : value }))
})

async function runRetention(dryRun) {
  if (!dryRun && !(await confirmDialog({ message: t('admin.retentionConfirm'), confirmLabel: t('admin.retentionRun'), danger: true }))) return
  retentionBusy.value = dryRun ? 'preview' : 'run'
  retentionError.value = ''
  try {
    const { data } = await api.admin.runRetention(null, { params: { dry_run: dryRun } })
    retentionResult.value = { ...data, dry_run: dryRun }
  } catch (e) {
    retentionError.value = apiError(e)
  } finally {
    retentionBusy.value = ''
  }
}

async function toggleAdmin(u) {
  try {
    const { data } = await api.admin.updateUser(u.id, {
      is_admin: !u.is_admin,
    })
    Object.assign(u, data)
  } catch (e) {
    toast.error(t('admin.err.updateUser', { error: apiError(e) }))
  }
}

async function deleteUser(u) {
  if (!(await confirmDialog({ message: t('admin.deleteUserConfirm', { email: u.email }), danger: true }))) return
  try {
    await api.admin.deleteUser(u.id)
    users.value = users.value.filter(x => x.id !== u.id)
  } catch (e) {
    toast.error(t('admin.err.deleteUser', { error: apiError(e) }))
  }
}

// ---------------------------------------------------------------------------
// scitq Configuration
// ---------------------------------------------------------------------------

const scitqConfig = reactive({ enabled: false, package_installed: false })
const scitqForm = reactive({ server: '', token: '', container: '' })
// The server never sends the token back, only whether one is stored.
const scitqTokenSet = ref(false)
const scitqLoading = ref(false)
const scitqSaving = ref(false)
const scitqSaved = ref(false)
const scitqTesting = ref(false)
const scitqTestResult = ref(null)

async function fetchScitq() {
  scitqLoading.value = true
  try {
    const { data } = await api.admin.getScitq()
    scitqConfig.enabled = data.enabled
    scitqConfig.package_installed = data.package_installed
    scitqForm.server = data.server || ''
    scitqForm.token = ''
    scitqTokenSet.value = !!(data.token_set ?? data.token)
    scitqForm.container = data.container || ''
  } catch { /* ignore */ }
  finally { scitqLoading.value = false }
}

async function saveScitq({ clearToken = false } = {}) {
  scitqSaving.value = true
  scitqSaved.value = false
  scitqTestResult.value = null
  try {
    // An empty token means "keep the stored one"; removing it is explicit.
    const body = {
      server: scitqForm.server.trim(),
      token: clearToken ? '' : scitqForm.token,
      container: scitqForm.container.trim(),
    }
    if (clearToken) body.clear_token = true
    const { data } = await api.admin.setScitq(body)
    scitqConfig.enabled = data.enabled
    scitqConfig.package_installed = data.package_installed
    scitqTokenSet.value = !!(data.token_set ?? data.token)
    scitqForm.token = ''
    scitqSaved.value = true
    setTimeout(() => { scitqSaved.value = false }, 3000)
  } catch (e) {
    toast.error(t('admin.err.saveScitq', { error: apiError(e) }))
  } finally {
    scitqSaving.value = false
  }
}

async function clearScitqToken() {
  if (!(await confirmDialog({ message: t('admin.scitqTokenRemoveConfirm'), confirmLabel: t('admin.scitqTokenRemove'), danger: true }))) return
  await saveScitq({ clearToken: true })
}

async function testScitq() {
  scitqTesting.value = true
  scitqTestResult.value = null
  try {
    const { data } = await api.admin.testScitq()
    scitqTestResult.value = data
  } catch (e) {
    scitqTestResult.value = { ok: false, error: apiError(e) }
  } finally {
    scitqTesting.value = false
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
    const { data } = await api.admin.listBackups()
    backups.value = data
  } catch { /* ignore */ }
  finally { backupLoading.value = false }
}

async function createBackup() {
  backupCreating.value = true
  backupMessage.value = ''
  try {
    const { data } = await api.admin.createBackup(null, {
      params: { description: backupDescription.value },
    })
    backupMessage.value = t('admin.backupCreated', { name: data.filename, size: formatSize(data.size_bytes) })
    backupMsgType.value = 'success'
    backupDescription.value = ''
    await fetchBackups()
  } catch (e) {
    backupMessage.value = apiError(e)
    backupMsgType.value = 'error'
  } finally {
    backupCreating.value = false
  }
}

async function downloadBackup(b) {
  try {
    const resp = await api.admin.downloadBackup(b.backup_id, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = b.filename
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    backupMessage.value = t('admin.backupDownloadFailed')
    backupMsgType.value = 'error'
  }
}

async function deleteBackupConfirm(b) {
  if (!(await confirmDialog({ message: t('admin.deleteBackupConfirm', { name: b.filename }), danger: true }))) return
  try {
    await api.admin.deleteBackup(b.backup_id)
    backupMessage.value = t('admin.backupDeleted')
    backupMsgType.value = 'success'
    await fetchBackups()
  } catch (e) {
    backupMessage.value = apiError(e)
    backupMsgType.value = 'error'
  }
}

async function handleRestoreFile(event) {
  const file = event.target.files[0]
  if (!file) return

  const confirmKey = restoreMode.value === 'replace' ? 'admin.restoreConfirmReplace' : 'admin.restoreConfirmMerge'

  if (!(await confirmDialog({ message: t(confirmKey, { name: file.name }), confirmLabel: t('admin.restoreAction'), danger: true }))) {
    event.target.value = ''
    return
  }

  const form = new FormData()
  form.append('file', file)

  backupMessage.value = t('admin.restoring')
  backupMsgType.value = 'success'

  try {
    const { data } = await api.admin.restoreBackup(restoreMode.value, form)
    const counts = Object.entries(data.restored_counts || {})
      .filter(([, c]) => c > 0)
      .map(([t, c]) => `${t}: ${c}`)
      .join(', ')
    backupMessage.value = t('admin.restoreDone', { mode: data.mode, counts })
    backupMsgType.value = 'success'
    await fetchBackups()
    await fetchUsers()
  } catch (e) {
    backupMessage.value = apiError(e)
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
    const { data } = await api.templates.list()
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
    await api.templates.create({
      name: tplName.value.trim(),
      description: tplDesc.value.trim(),
      config: clean,
    })
    tplName.value = ''
    tplDesc.value = ''
    await fetchTemplates()
  } catch (e) {
    toast.error(t('admin.err.createTemplate', { error: apiError(e) }))
  } finally {
    tplSaving.value = false
  }
}

async function deleteTemplate(tpl) {
  if (!(await confirmDialog({ message: t('admin.deleteTemplateConfirm', { name: tpl.name }), danger: true }))) return
  try {
    await api.templates.remove(tpl.id)
    await fetchTemplates()
  } catch (e) {
    toast.error(t('admin.err.deleteTemplate', { error: apiError(e) }))
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
    const { data } = await api.admin.auditLog({ params })
    auditEntries.value = data.entries
    auditTotal.value = data.total
  } catch { /* ignore */ }
}

onMounted(() => {
  fetchUsers()
  fetchScitq()
  fetchDefaults()
  fetchBackups()
  fetchTemplates()
  fetchAuditLog()
})
</script>

<style scoped>
.create-user { margin: 1.25rem 0 2rem; padding: 1rem 1.25rem; background: var(--bg-card); border: 1px solid var(--border-light); border-radius: 8px; }
.create-user h3 { font-size: 1rem; margin-bottom: 0.75rem; color: var(--text-primary); }
.create-user-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem 1rem; align-items: end; margin-bottom: 0.75rem; }
.create-user-field { display: flex; flex-direction: column; gap: 0.25rem; }
.create-user-field label { font-size: 0.8rem; color: var(--text-secondary); }
.create-user-field input { padding: 0.45rem 0.6rem; border: 1px solid var(--border-light); border-radius: 6px; background: var(--bg-input); color: var(--text-body); font-size: 0.85rem; }
.create-user-check { display: flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; color: var(--text-body); }
.retention { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: flex-start; margin-bottom: 2rem; }
.retention-result { flex-basis: 100%; font-size: 0.85rem; color: var(--text-body); background: var(--bg-badge); border-radius: 6px; padding: 0.6rem 0.9rem; }
.retention-result ul { margin: 0.3rem 0 0 1.1rem; }

.scitq-hint { font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.3rem; }
.btn-inline-danger {
  background: none; border: none; padding: 0; margin-left: 0.4rem;
  color: var(--danger); text-decoration: underline; cursor: pointer; font-size: 0.8rem;
}
.btn-inline-danger:disabled { opacity: 0.6; cursor: not-allowed; }

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

/* scitq Configuration */
.scitq-section {
  background: var(--bg-card);
  border-radius: 8px;
  padding: 1rem;
  border: 1px solid var(--border-lighter);
  margin-bottom: 1rem;
}
.scitq-status-bar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.scitq-badge {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 4px;
  font-size: 0.78rem;
  font-weight: 600;
}
.scitq-badge.on {
  background: var(--success-bg, #e8f5e9);
  color: var(--success-dark, #2e7d32);
}
.scitq-badge.off {
  background: var(--bg-badge);
  color: var(--text-muted);
}
.scitq-warning {
  font-size: 0.78rem;
  color: var(--warning-dark, #e65100);
  background: var(--warning-bg, #fff3e0);
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
}
.scitq-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.scitq-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.scitq-field label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-secondary);
}
.scitq-field input {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
}
.scitq-actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}
.btn-test {
  padding: 0.4rem 1rem;
  background: transparent;
  border: 1px solid var(--accent);
  color: var(--accent);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
}
.btn-test:hover { background: var(--accent-faint, rgba(59, 130, 246, 0.08)); }
.btn-test:disabled { opacity: 0.5; cursor: not-allowed; }
.scitq-test-msg {
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.85rem;
}
.scitq-test-msg.success {
  background: var(--success-bg, #e8f5e9);
  color: var(--success-dark, #2e7d32);
}
.scitq-test-msg.error {
  background: var(--danger-bg, #ffebee);
  color: var(--danger, #c62828);
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
  font-size: 0.75rem;
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
