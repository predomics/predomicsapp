<template>
  <div class="params-tab">
    <form @submit.prevent="batchMode ? launchBatch() : launch()" novalidate>
      <!-- Built-in presets: how hard the search works, in one click -->
      <fieldset class="preset-bar">
        <legend class="preset-legend">{{ $t('parameters.presets.title') }}</legend>
        <div class="preset-options">
          <button
            v-for="p in PRESETS"
            :key="p.id"
            type="button"
            class="preset-btn"
            :class="{ active: activePreset === p.id }"
            :aria-pressed="activePreset === p.id ? 'true' : 'false'"
            @click="choosePreset(p.id)"
          >
            <span class="preset-name"><span v-if="activePreset === p.id" aria-hidden="true">&#10003; </span>{{ $t(`parameters.presets.${p.id}.name`) }}</span>
            <span class="preset-desc">{{ $t(`parameters.presets.${p.id}.desc`) }}</span>
          </button>
        </div>
        <p class="preset-hint">{{ activePreset ? $t('parameters.presets.hintActive') : $t('parameters.presets.hintCustom') }}</p>
      </fieldset>

      <!-- Template loader (templates published by an administrator) -->
      <div class="template-bar" v-if="templates.length > 0">
        <label class="template-label" for="template-select">{{ $t('parameters.loadTemplate') }}</label>
        <select id="template-select" v-model="selectedTemplate" @change="applyTemplate" class="template-select">
          <option value="">{{ $t('parameters.selectTemplate') }}</option>
          <option v-for="tpl in templates" :key="tpl.id" :value="tpl.id">{{ tpl.name }}</option>
        </select>
        <span v-if="templateMsg" class="template-msg" role="status">{{ templateMsg }}</span>
      </div>

      <!-- Regression mode indicator -->
      <div v-if="isRegression" class="regression-badge">
        <span class="regression-badge-label">{{ $t('parameters.regressionMode') }}</span>
        <span class="regression-badge-hint">{{ $t('parameters.votingDisabledRegression') }}</span>
      </div>

      <div class="settings-grid">
        <!-- Left column: General, CV, Data filtering summary -->
        <div class="settings-col">
          <template v-for="cat in leftCategories" :key="cat.id">
            <ParamSection
              v-if="isCategoryVisible(cat)"
              :category="cat"
              :params="paramsByCategory[cat.id] || []"
              :form="cfg[cat.id]"
              :errors="shownErrors"
            />
          </template>

          <!-- Data filtering summary (read-only, not from parameterDefs) -->
          <section class="section info-section">
            <div class="section-title">{{ $t('parameters.dataFiltering') }}</div>
            <p class="info-note">{{ $t('parameters.dataFilteringNote') }}</p>
            <div class="info-row"><span class="info-label">{{ $t('parameters.method') }}</span> {{ cfg.data.feature_selection_method }}</div>
            <div class="info-row"><span class="info-label">{{ $t('parameters.minPrevalence') }}</span> {{ cfg.data.feature_minimal_prevalence_pct }}%</div>
            <div class="info-row"><span class="info-label">{{ $t('parameters.maxPValue') }}</span> {{ cfg.data.feature_maximal_adj_pvalue }}</div>
            <div class="info-row"><span class="info-label">{{ $t('parameters.holdoutRatio') }}</span> {{ cfg.data.holdout_ratio }}</div>
            <router-link :to="`/project/${route.params.id}/data`" class="edit-link">{{ $t('parameters.editInDataTab') }}</router-link>
          </section>
        </div>

        <!-- Right column: Algo-specific, Importance, Voting, GPU -->
        <div class="settings-col">
          <template v-for="cat in rightCategories" :key="cat.id">
            <ParamSection
              v-if="isCategoryVisible(cat)"
              :category="cat"
              :params="paramsByCategory[cat.id] || []"
              :form="cfg[cat.id]"
              :errors="shownErrors"
            />
          </template>
        </div>
      </div>

      <!-- Batch Mode Section -->
      <div class="batch-section">
        <label class="batch-toggle">
          <input type="checkbox" v-model="batchMode" />
          <span class="batch-toggle-label">{{ $t('parameters.batchMode') }}</span>
          <span class="batch-toggle-hint">{{ $t('parameters.batchDesc') }}</span>
        </label>

        <div v-if="batchMode" class="batch-grid">
          <div v-for="sp in sweepableParams" :key="sp.key" class="sweep-row">
            <label class="sweep-check">
              <input type="checkbox" :checked="sweeps[sp.key]?.enabled" @change="toggleSweep(sp.key)" />
              <span>{{ $t(`parameters.sweep.${sp.id}`) }}</span>
            </label>
            <input
              v-if="sweeps[sp.key]?.enabled"
              v-model="sweeps[sp.key].values"
              class="sweep-input"
              :placeholder="sp.placeholder"
              :aria-label="$t(`parameters.sweep.${sp.id}`)"
              :title="sp.semicolon ? $t('parameters.sweep.helpSemicolon') : $t('parameters.sweep.helpComma')"
            />
            <span v-if="sweeps[sp.key]?.enabled" class="sweep-count">
              {{ parseSweepValues(sweeps[sp.key].values).length }} {{ $t('parameters.values') }}
            </span>
          </div>
          <div class="sweep-summary" v-if="batchJobCount > 0">
            {{ $t('parameters.willLaunch') }} <strong>{{ batchJobCount }}</strong> {{ $t('parameters.jobsCount') }}
            <span v-if="batchJobCount > 50" class="sweep-warn">{{ $t('parameters.maxJobs') }}</span>
          </div>
        </div>
      </div>

      <!-- Batch result message -->
      <div v-if="batchResult" class="batch-result" role="status">
        {{ $t('parameters.batchLaunched', { id: batchResult.batch_id, n: batchResult.job_count }) }}
        <router-link :to="`/project/${route.params.id}/results`">{{ $t('parameters.viewInResults') }}</router-link>
      </div>

      <!-- Job name + Launch bar (sticks to the bottom of the window) -->
      <div class="launch-bar">
        <div v-if="showErrors && errorCount > 0" class="launch-errors" role="alert">
          <strong>{{ $t('parameters.fixErrors', errorCount) }}</strong>
          <ul>
            <li v-for="e in errorList" :key="e.id">
              <a :href="`#param-${e.id.replace('.', '-')}`" @click.prevent="focusField(e.id)">{{ e.label }}</a> — {{ e.message }}
            </li>
          </ul>
        </div>
        <p v-if="launchError" class="launch-errors" role="alert">{{ launchError }}</p>
        <div class="job-name-row" v-if="!batchMode">
          <label class="job-name-label" for="job-name-input">{{ $t('parameters.jobName') }}</label>
          <input
            id="job-name-input"
            v-model="jobName"
            type="text"
            class="job-name-input"
            :placeholder="autoJobName"
            maxlength="255"
          />
          <button type="button" class="btn btn-auto-name" @click="jobName = autoJobName" :title="$t('parameters.autoTitle')">{{ $t('parameters.auto') }}</button>
        </div>
        <div class="launch-actions">
          <button type="submit" class="btn btn-launch" :disabled="launching || !canLaunch || (batchMode && (batchJobCount === 0 || batchJobCount > 50))">
            {{ launching ? $t('parameters.launching') : (batchMode ? $t('parameters.launchJobs', { n: batchJobCount }) : $t('parameters.launchAnalysis')) }}
          </button>
          <button type="button" class="btn btn-reset" @click="resetAll">{{ $t('parameters.resetDefaults') }}</button>
          <span v-if="!canLaunch" class="launch-hint">
            {{ $t('parameters.uploadFirst') }}
            <router-link :to="`/project/${route.params.id}/data`">{{ $t('parameters.goToData') }}</router-link>
          </span>
          <span v-else class="launch-summary">{{ launchSummary }}</span>
        </div>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import { useConfigStore } from '../stores/config'
import { CATEGORIES, PARAM_DEFS, PARAM_INDEX, paramDefault } from '../data/parameterDefs'
import { PRESETS, matchingPreset } from '../data/presets'
import ParamSection from '../components/ParamSection.vue'
import { api } from '../api'
import { useI18n } from 'vue-i18n'
import { useToast } from '../composables/useToast'
import { useConfirm } from '../composables/useConfirm'
import { apiError, ignoreError } from '../utils/apiError'
import { validateForm } from '../utils/paramValidation'
import { paramLabel, paramErrorText } from '../utils/paramI18n'
import { requestPermission } from '../utils/notify'
import { REGRESSION_FITS, SKLEARN_ALGOS, findFileByRole } from '../utils/analysis'

const route = useRoute()
const store = useProjectStore()
const configStore = useConfigStore()
const cfg = configStore.form
const launching = ref(false)
// What the server said when it refused a launch (e.g. settings that cannot run),
// shown next to the Launch button until the next attempt.
const launchError = ref('')
const jobName = ref('')
const batchMode = ref(false)
const batchResult = ref(null)
const { t } = useI18n()
const { toast, addToast } = useToast()
const { confirmDialog } = useConfirm()

// The draft of this project (restored after a refresh, kept apart per project)
configStore.bindProject(route.params.id)

// Presets
const activePreset = computed(() => matchingPreset(cfg))
function choosePreset(id) {
  configStore.applyPreset(id)
  toast.info(t('parameters.presets.applied', { name: t(`parameters.presets.${id}.name`) }), 3000)
}

// Templates
const templates = ref([])
const selectedTemplate = ref('')
const templateMsg = ref('')

async function fetchTemplates() {
  try {
    const { data } = await api.templates.listPublic({ silentError: true })
    templates.value = Array.isArray(data) ? data : []
  } catch (e) { ignoreError(e) /* templates are optional */ }
}

function applyTemplate() {
  const tpl = templates.value.find(t => t.id === selectedTemplate.value)
  if (!tpl || !tpl.config) return
  // Apply template config values to the form
  configStore.applyValues(tpl.config)
  templateMsg.value = t('parameters.templateLoaded', { name: tpl.name })
  setTimeout(() => { templateMsg.value = '' }, 3000)
}

onMounted(() => { fetchTemplates() })

// Sweepable parameters definition
const sweepableParams = [
  { key: 'general.seed', id: 'seed', placeholder: '42, 123, 456' },
  { key: 'general.algo', id: 'algo', placeholder: 'ga, beam, rf, xgboost' },
  { key: 'general.language', id: 'language', placeholder: 'bin; ter; bin,ter,ratio', semicolon: true },
  { key: 'general.data_type', id: 'dataType', placeholder: 'raw; prev; raw,prev', semicolon: true },
  { key: 'ga.population_size', id: 'populationSize', placeholder: '1000, 5000, 10000' },
  { key: 'ga.max_epochs', id: 'maxEpochs', placeholder: '100, 200, 500' },
  { key: 'ga.k_max', id: 'kMax', placeholder: '50, 100, 200' },
]

const sweeps = reactive({})
for (const sp of sweepableParams) {
  sweeps[sp.key] = { enabled: false, values: '' }
}

function toggleSweep(key) {
  sweeps[key].enabled = !sweeps[key].enabled
  if (!sweeps[key].enabled) sweeps[key].values = ''
}

function parseSweepValues(str) {
  if (!str.trim()) return []
  // Use semicolon for multi-value params like language, comma for numeric
  const sep = str.includes(';') ? ';' : ','
  return str.split(sep).map(v => v.trim()).filter(Boolean)
}

function coerceSweepValue(key, val) {
  // Numeric params should be parsed as numbers
  if (['general.seed', 'ga.population_size', 'ga.max_epochs', 'ga.k_max'].includes(key)) {
    const n = Number(val)
    return isNaN(n) ? val : n
  }
  return val
}

const batchJobCount = computed(() => {
  const activeSweeps = Object.entries(sweeps).filter(([, v]) => v.enabled && v.values.trim())
  if (activeSweeps.length === 0) return 0
  return activeSweeps.reduce((total, [, v]) => total * parseSweepValues(v.values).length, 1)
})

// Split categories into left/right columns
const leftCatIds = ['general', 'cv']
const rightCatIds = ['ga', 'beam', 'mcmc', 'aco', 'sa', 'lasso', 'ils', 'rf', 'svm', 'logistic', 'xgboost', 'lightgbm', 'extra_trees', 'adaboost', 'knn', 'clinical', 'importance', 'voting', 'gpu']
const leftCategories = computed(() => CATEGORIES.filter(c => leftCatIds.includes(c.id)))
const rightCategories = computed(() => CATEGORIES.filter(c => rightCatIds.includes(c.id)))

// Group params by category, filtering out hidden params
const paramsByCategory = computed(() => {
  const map = {}
  for (const p of PARAM_DEFS) {
    if (!isParamVisible(p)) continue
    if (!map[p.category]) map[p.category] = []
    map[p.category].push(p)
  }
  return map
})

// Regression mode detection
const isRegression = computed(() => REGRESSION_FITS.has(cfg.general.fit))

// Sklearn algorithms (no gpredomics-specific options)
const isSklearn = computed(() => SKLEARN_ALGOS.has(cfg.general.algo))

// General params hidden for sklearn algos (they don't apply)
const GPREDOMICS_GENERAL_KEYS = new Set(['language', 'data_type', 'epsilon', 'k_penalty', 'fr_penalty', 'bias_penalty',
  'threshold_ci_n_bootstrap', 'threshold_ci_penalty', 'threshold_ci_alpha', 'threshold_ci_frac_bootstrap',
  'user_feature_penalties_weight', 'n_model_to_display', 'display_colorful', 'gpu'])

// Visibility logic for conditional categories
function isCategoryVisible(cat) {
  if (cat.gpredomicsOnly && isSklearn.value) return false
  // Hide voting category in regression mode (voting is not applicable)
  if (cat.id === 'voting' && isRegression.value) return false
  if (cat.algoFilter) return cfg.general.algo === cat.algoFilter
  if (cat.enabledBy) {
    const [section, key] = cat.enabledBy.split('.')
    return cfg[section]?.[key] === true
  }
  return true
}

// Visibility logic for individual params (hide gpredomics-specific general params for sklearn)
function isParamVisible(paramDef) {
  if (isSklearn.value && paramDef.category === 'general' && GPREDOMICS_GENERAL_KEYS.has(paramDef.key)) return false
  // Hide threshold CI params in regression mode (no classification threshold)
  if (isRegression.value && paramDef.key.startsWith('threshold_ci')) return false
  return true
}

// Auto-generate job name from config diff vs defaults
const autoJobName = computed(() => {
  const parts = []
  const algo = cfg.general.algo?.toUpperCase() || 'GA'
  parts.push(algo)
  // Only what differs from the defaults in parameterDefs is worth naming.
  const def = (cat, key) => paramDefault(cat, key)
  const lang = cfg.general.language || ''
  if (lang !== def('general', 'language')) parts.push(lang.replace(/,/g, '+'))
  const dt = cfg.general.data_type || ''
  if (dt !== def('general', 'data_type')) parts.push(dt.replace(/,/g, '+'))
  if (cfg.general.fit && cfg.general.fit !== def('general', 'fit')) parts.push(cfg.general.fit)
  if (algo === 'GA') {
    const kMin = cfg.ga.k_min ?? def('ga', 'k_min')
    const kMax = cfg.ga.k_max ?? def('ga', 'k_max')
    if (kMin !== def('ga', 'k_min') || kMax !== def('ga', 'k_max')) parts.push(`k${kMin}-${kMax}`)
    if (cfg.ga.population_size !== def('ga', 'population_size')) parts.push(`pop${cfg.ga.population_size}`)
    if (cfg.ga.max_epochs !== def('ga', 'max_epochs')) parts.push(`${cfg.ga.max_epochs}ep`)
  }
  if (cfg.general.seed !== def('general', 'seed')) parts.push(`s${cfg.general.seed}`)
  if (cfg.general.cv) parts.push('CV')
  if (cfg.voting.vote) parts.push('vote')
  return parts.join(' ')
})

// File resolution for launch
const datasets = computed(() => store.current?.datasets || [])
function findFile(role) { return findFileByRole(datasets.value, role) }
const xTrainDs = computed(() => findFile('xtrain'))
const yTrainDs = computed(() => findFile('ytrain'))
const xTestDs = computed(() => findFile('xtest'))
const yTestDs = computed(() => findFile('ytest'))
const clinicalDs = computed(() => findFile('clinical'))
const canLaunch = computed(() => xTrainDs.value && yTrainDs.value)

function _fileParams() {
  const params = { x_file_id: xTrainDs.value.id, y_file_id: yTrainDs.value.id }
  if (xTestDs.value) params.xtest_file_id = xTestDs.value.id
  if (yTestDs.value) params.ytest_file_id = yTestDs.value.id
  if (clinicalDs.value) params.clinical_file_id = clinicalDs.value.id
  return params
}

// ---- Validation -----------------------------------------------------------
const visibleDefs = computed(() =>
  PARAM_DEFS.filter(p => {
    const cat = CATEGORIES.find(c => c.id === p.category)
    return cat && isCategoryVisible(cat) && isParamVisible(p)
  }),
)
const errors = computed(() => validateForm(cfg, visibleDefs.value))
const errorCount = computed(() => Object.keys(errors.value).length)
// Out-of-range values are flagged as soon as they are typed; "required"
// complaints wait until the user tries to launch.
const showErrors = ref(false)
const shownErrors = computed(() => {
  if (showErrors.value) return errors.value
  const out = {}
  for (const [id, err] of Object.entries(errors.value)) {
    if (err.code !== 'required' && err.code !== 'pickOne') out[id] = err
  }
  return out
})
const errorList = computed(() =>
  Object.entries(errors.value).map(([id, err]) => {
    const def = PARAM_INDEX[id]
    const siblings = PARAM_DEFS.filter(p => p.category === def?.category)
    return { id, label: def ? paramLabel(def) : id, message: paramErrorText(err, siblings) }
  }),
)

function focusField(id) {
  const el = document.getElementById(`param-${id.replace('.', '-')}`)
  if (!el) return
  const details = el.closest('details')
  if (details) details.open = true
  nextTick(() => {
    el.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
    el.focus({ preventScroll: true })
  })
}

function checkBeforeLaunch() {
  showErrors.value = true
  if (errorCount.value === 0) return true
  toast.warning(t('parameters.fixErrors', errorCount.value))
  nextTick(() => focusField(Object.keys(errors.value)[0]))
  return false
}

const launchSummary = computed(() => {
  const algoDef = PARAM_INDEX['general.algo']
  const opt = algoDef?.options?.find(o => o.value === cfg.general.algo)
  return t('parameters.launchSummary', { algo: opt?.label || cfg.general.algo, fit: cfg.general.fit })
})

async function resetAll() {
  if (!(await confirmDialog({ message: t('parameters.resetConfirm'), confirmLabel: t('parameters.resetDefaults'), danger: true }))) return
  const before = configStore.snapshot()
  configStore.resetToDefaults()
  showErrors.value = false
  addToast(t('parameters.resetDone'), 'info', 8000, {
    action: { label: t('common.undo'), onClick: () => configStore.applyValues(before) },
  })
}

async function launch() {
  if (!canLaunch.value) return
  if (!checkBeforeLaunch()) return
  launching.value = true
  launchError.value = ''
  batchResult.value = null
  try {
    const params = _fileParams()
    const name = jobName.value.trim() || autoJobName.value
    if (name) params.job_name = name

    const { data } = await api.analysis.run(route.params.id,
      configStore.payload(),
      { params }
    )
    store.startJob(data.job_id)
    // Ask for notifications when they become useful: a job has just started.
    requestPermission()
  } catch (e) {
    launchError.value = t('parameters.launchFailed', { error: apiError(e) })
  } finally {
    launching.value = false
  }
}

async function launchBatch() {
  if (!canLaunch.value || batchJobCount.value === 0) return
  if (!checkBeforeLaunch()) return
  launching.value = true
  launchError.value = ''
  batchResult.value = null
  try {
    const params = _fileParams()

    // Build sweep object
    const sweepObj = {}
    for (const [key, s] of Object.entries(sweeps)) {
      if (s.enabled && s.values.trim()) {
        sweepObj[key] = parseSweepValues(s.values).map(v => coerceSweepValue(key, v))
      }
    }

    const { data } = await api.analysis.runBatch(route.params.id,
      { config: configStore.payload(), sweep: { sweeps: sweepObj } },
      { params }
    )
    batchResult.value = data
  } catch (e) {
    launchError.value = t('parameters.batchFailed', { error: apiError(e) })
  } finally {
    launching.value = false
  }
}
</script>

<style scoped>
.params-tab { max-width: 100%; }

.template-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
  padding: 0.5rem 0.75rem;
  background: var(--bg-badge);
  border-radius: 6px;
}
.template-label {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
}
.template-select {
  padding: 0.35rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
  min-width: 200px;
}
.template-msg {
  font-size: 0.8rem;
  color: var(--success-dark, #2e7d32);
}

.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1rem;
}

.settings-col {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.info-section { background: var(--bg-badge); padding: 1rem 1.25rem; border-radius: 8px; box-shadow: var(--shadow); }
.section-title {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-primary);
  margin-bottom: 0.75rem;
}
.info-row {
  font-size: 0.8rem;
  color: var(--text-body);
  margin-bottom: 0.3rem;
}
.info-label {
  color: var(--text-muted);
  display: inline-block;
  min-width: 100px;
}
.edit-link {
  font-size: 0.8rem;
  color: var(--accent);
  text-decoration: none;
  margin-top: 0.5rem;
  display: inline-block;
}
.edit-link:hover { text-decoration: underline; }

/* Batch mode */
.batch-section {
  border-top: 1px solid var(--border-lighter);
  padding: 0.75rem 0;
  margin-bottom: 0.5rem;
}

.batch-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.88rem;
}
.batch-toggle input { cursor: pointer; }
.batch-toggle-label {
  font-weight: 600;
  color: var(--text-primary);
}
.batch-toggle-hint {
  color: var(--text-faint);
  font-size: 0.78rem;
}

.batch-grid {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0.75rem 1rem;
  background: var(--bg-badge);
  border-radius: 8px;
}

.sweep-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.sweep-check {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  min-width: 140px;
  font-size: 0.82rem;
  color: var(--text-body);
  cursor: pointer;
}
.sweep-check input { cursor: pointer; }

.sweep-input {
  flex: 1;
  max-width: 300px;
  padding: 0.3rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.8rem;
  background: var(--bg-input);
  color: var(--text-body);
}

.sweep-count {
  font-size: 0.75rem;
  color: var(--text-muted);
  white-space: nowrap;
}

.sweep-summary {
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--border-lighter);
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.sweep-warn {
  color: var(--danger);
  font-weight: 600;
}

/* Launch bar */
.launch-bar {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.75rem 0;
}

.job-name-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.job-name-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  white-space: nowrap;
  font-weight: 500;
}
.job-name-input {
  flex: 1;
  max-width: 400px;
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
}
.job-name-input::placeholder { color: var(--text-faint); }
.btn-auto-name {
  padding: 0.35rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.75rem;
  cursor: pointer;
  background: transparent;
  color: var(--text-secondary);
  transition: all 0.2s;
}
.btn-auto-name:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.launch-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.btn-launch {
  padding: 0.65rem 2rem;
  border: none;
  border-radius: 6px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  background: var(--accent);
  color: var(--accent-text);
  transition: opacity 0.15s;
}

.btn-launch:hover:not(:disabled) { opacity: 0.9; }
.btn-launch:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-reset {
  padding: 0.5rem 1rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.8rem;
  cursor: pointer;
  background: transparent;
  color: var(--text-secondary);
  transition: all 0.2s;
}
.btn-reset:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.launch-hint { color: var(--warning-dark); font-size: 0.8rem; }

.batch-result {
  margin-top: 0.75rem;
  padding: 0.75rem 1rem;
  background: var(--success-bg);
  color: var(--success-dark);
  border-radius: 6px;
  font-size: 0.85rem;
}
.batch-result a {
  color: var(--accent);
  font-weight: 600;
}

/* Regression mode badge */
.regression-badge {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  padding: 0.4rem 0.75rem;
  background: #e3f2fd;
  border: 1px solid #90caf9;
  border-radius: 6px;
}
.regression-badge-label {
  font-size: 0.82rem;
  font-weight: 600;
  color: #1565c0;
}
.regression-badge-hint {
  font-size: 0.75rem;
  color: #42a5f5;
}

@media (max-width: 900px) {
  .settings-grid { grid-template-columns: 1fr; }
}
.preset-bar {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 0.6rem 0.9rem 0.7rem;
  margin-bottom: 1rem;
  background: var(--bg-card);
}
.preset-legend { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); padding: 0 0.35rem; }
.preset-options { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.6rem; }
.preset-btn {
  display: flex; flex-direction: column; gap: 0.15rem; text-align: left;
  padding: 0.55rem 0.75rem; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--border); background: var(--bg-input); color: var(--text-body); font: inherit;
}
.preset-btn.active { border-color: var(--info); box-shadow: 0 0 0 1px var(--info); background: var(--info-bg); }
.preset-name { font-weight: 600; font-size: 0.9rem; color: var(--text-primary); }
.preset-desc { font-size: 0.76rem; color: var(--text-secondary); line-height: 1.3; }
.preset-hint { margin-top: 0.45rem; font-size: 0.76rem; color: var(--text-secondary); }
.info-note { font-size: 0.76rem; color: var(--text-secondary); margin-bottom: 0.5rem; }

/* Launch is always within reach, whatever the length of the form. */
.launch-bar {
  position: sticky;
  bottom: 0;
  z-index: 20;
  background: var(--bg-card);
  border-top: 1px solid var(--border-light);
  box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.08);
  padding: 0.75rem 1rem;
  margin: 0 -0.5rem;
  border-radius: 8px 8px 0 0;
}
.launch-errors {
  background: var(--danger-bg); color: var(--danger-dark);
  border: 1px solid var(--danger); border-radius: 6px;
  padding: 0.5rem 0.75rem; font-size: 0.82rem; max-height: 9rem; overflow: auto;
}
.launch-errors ul { margin: 0.25rem 0 0 1.1rem; }
.launch-errors a { color: inherit; font-weight: 600; }
.launch-summary { font-size: 0.8rem; color: var(--text-secondary); }
.launch-hint a { margin-left: 0.35rem; }

@media (max-width: 900px) {
  .settings-grid { grid-template-columns: 1fr; }
  .preset-options { grid-template-columns: 1fr; }
}
</style>
