<template>
  <div class="params-tab">
    <form @submit.prevent="batchMode ? launchBatch() : launch()" novalidate>
      <div class="settings-grid">
        <!-- Left column: General, CV, Data filtering summary -->
        <div class="settings-col">
          <template v-for="cat in leftCategories" :key="cat.id">
            <ParamSection
              v-if="isCategoryVisible(cat)"
              :category="cat"
              :params="paramsByCategory[cat.id] || []"
              :form="cfg[cat.id]"
            />
          </template>

          <!-- Data filtering summary (read-only, not from parameterDefs) -->
          <section class="section info-section">
            <div class="section-title">Data Filtering</div>
            <div class="info-row"><span class="info-label">Method:</span> {{ cfg.data.feature_selection_method }}</div>
            <div class="info-row"><span class="info-label">Min prevalence:</span> {{ cfg.data.feature_minimal_prevalence_pct }}%</div>
            <div class="info-row"><span class="info-label">Max p-value:</span> {{ cfg.data.feature_maximal_adj_pvalue }}</div>
            <div class="info-row"><span class="info-label">Holdout ratio:</span> {{ cfg.data.holdout_ratio }}</div>
            <router-link :to="`/project/${route.params.id}/data`" class="edit-link">Edit in Data tab</router-link>
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
            />
          </template>
        </div>
      </div>

      <!-- Batch Mode Section -->
      <div class="batch-section">
        <label class="batch-toggle">
          <input type="checkbox" v-model="batchMode" />
          <span class="batch-toggle-label">Batch Mode</span>
          <span class="batch-toggle-hint">Sweep parameters across multiple runs</span>
        </label>

        <div v-if="batchMode" class="batch-grid">
          <div v-for="sp in sweepableParams" :key="sp.key" class="sweep-row">
            <label class="sweep-check">
              <input type="checkbox" :checked="sweeps[sp.key]?.enabled" @change="toggleSweep(sp.key)" />
              <span>{{ sp.label }}</span>
            </label>
            <input
              v-if="sweeps[sp.key]?.enabled"
              v-model="sweeps[sp.key].values"
              class="sweep-input"
              :placeholder="sp.placeholder"
              :title="sp.help"
            />
            <span v-if="sweeps[sp.key]?.enabled" class="sweep-count">
              {{ parseSweepValues(sweeps[sp.key].values).length }} values
            </span>
          </div>
          <div class="sweep-summary" v-if="batchJobCount > 0">
            Will launch <strong>{{ batchJobCount }}</strong> job{{ batchJobCount !== 1 ? 's' : '' }}
            <span v-if="batchJobCount > 50" class="sweep-warn">(max 50)</span>
          </div>
        </div>
      </div>

      <!-- Job name + Launch bar -->
      <div class="launch-bar">
        <div class="job-name-row" v-if="!batchMode">
          <label class="job-name-label">Job name</label>
          <input
            v-model="jobName"
            type="text"
            class="job-name-input"
            :placeholder="autoJobName"
            maxlength="255"
          />
          <button type="button" class="btn btn-auto-name" @click="jobName = autoJobName" title="Generate from parameters">Auto</button>
        </div>
        <div class="launch-actions">
          <button type="submit" class="btn btn-launch" :disabled="launching || !canLaunch || (batchMode && (batchJobCount === 0 || batchJobCount > 50))">
            {{ launching ? 'Launching...' : (batchMode ? `Launch ${batchJobCount} Jobs` : 'Launch Analysis') }}
          </button>
          <button type="button" class="btn btn-reset" @click="configStore.resetToDefaults()">Reset defaults</button>
          <span v-if="!canLaunch" class="launch-hint">Upload X and y training datasets in the Data tab first</span>
        </div>
      </div>

      <!-- Batch result message -->
      <div v-if="batchResult" class="batch-result">
        Batch <strong>{{ batchResult.batch_id }}</strong> launched: {{ batchResult.job_count }} jobs queued.
        <router-link :to="`/project/${route.params.id}/results`">View in Results tab</router-link>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import { useConfigStore } from '../stores/config'
import { CATEGORIES, PARAM_DEFS } from '../data/parameterDefs'
import ParamSection from '../components/ParamSection.vue'
import axios from 'axios'

const route = useRoute()
const store = useProjectStore()
const configStore = useConfigStore()
const cfg = configStore.form
const launching = ref(false)
const jobName = ref('')
const batchMode = ref(false)
const batchResult = ref(null)

// Sweepable parameters definition
const sweepableParams = [
  { key: 'general.seed', label: 'Seeds', placeholder: '42, 123, 456', help: 'Comma-separated seed values' },
  { key: 'general.algo', label: 'Algorithms', placeholder: 'ga, beam, mcmc', help: 'Comma-separated algorithms' },
  { key: 'general.language', label: 'Languages', placeholder: 'bin; ter; bin,ter,ratio', help: 'Semicolon-separated language combos' },
  { key: 'general.data_type', label: 'Data types', placeholder: 'raw; prev; raw,prev', help: 'Semicolon-separated data type combos' },
  { key: 'ga.population_size', label: 'Population sizes', placeholder: '1000, 5000, 10000', help: 'Comma-separated values' },
  { key: 'ga.max_epochs', label: 'Max epochs', placeholder: '100, 200, 500', help: 'Comma-separated values' },
  { key: 'ga.k_max', label: 'k_max values', placeholder: '50, 100, 200', help: 'Comma-separated values' },
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
const rightCatIds = ['ga', 'beam', 'mcmc', 'importance', 'voting', 'gpu']
const leftCategories = computed(() => CATEGORIES.filter(c => leftCatIds.includes(c.id)))
const rightCategories = computed(() => CATEGORIES.filter(c => rightCatIds.includes(c.id)))

// Group params by category
const paramsByCategory = computed(() => {
  const map = {}
  for (const p of PARAM_DEFS) {
    if (!map[p.category]) map[p.category] = []
    map[p.category].push(p)
  }
  return map
})

// Visibility logic for conditional categories
function isCategoryVisible(cat) {
  if (cat.algoFilter) return cfg.general.algo === cat.algoFilter
  if (cat.enabledBy) {
    const [section, key] = cat.enabledBy.split('.')
    return cfg[section]?.[key] === true
  }
  return true
}

// Auto-generate job name from config diff vs defaults
const autoJobName = computed(() => {
  const parts = []
  const algo = cfg.general.algo?.toUpperCase() || 'GA'
  parts.push(algo)
  const lang = cfg.general.language || ''
  if (lang !== 'bin,ter,ratio') parts.push(lang.replace(/,/g, '+'))
  const dt = cfg.general.data_type || ''
  if (dt !== 'raw,prev') parts.push(dt.replace(/,/g, '+'))
  if (cfg.general.fit && cfg.general.fit !== 'auc') parts.push(cfg.general.fit)
  if (algo === 'GA') {
    const kMin = cfg.ga.k_min ?? 1
    const kMax = cfg.ga.k_max ?? 200
    if (kMin !== 1 || kMax !== 200) parts.push(`k${kMin}-${kMax}`)
    if (cfg.ga.population_size !== 5000) parts.push(`pop${cfg.ga.population_size}`)
    if (cfg.ga.max_epochs !== 200) parts.push(`${cfg.ga.max_epochs}ep`)
  }
  if (cfg.general.seed !== 42) parts.push(`s${cfg.general.seed}`)
  if (cfg.general.cv) parts.push('CV')
  if (cfg.voting.vote) parts.push('vote')
  return parts.join(' ')
})

// File resolution for launch
const datasets = computed(() => store.current?.datasets || [])
const allFiles = computed(() =>
  datasets.value.flatMap(ds => (ds.files || []).map(f => ({ ...f, datasetId: ds.id })))
)
function findFile(role) { return allFiles.value.find(f => f.role === role) || null }
const xTrainDs = computed(() => findFile('xtrain'))
const yTrainDs = computed(() => findFile('ytrain'))
const xTestDs = computed(() => findFile('xtest'))
const yTestDs = computed(() => findFile('ytest'))
const canLaunch = computed(() => xTrainDs.value && yTrainDs.value)

function _fileParams() {
  const params = { x_file_id: xTrainDs.value.id, y_file_id: yTrainDs.value.id }
  if (xTestDs.value) params.xtest_file_id = xTestDs.value.id
  if (yTestDs.value) params.ytest_file_id = yTestDs.value.id
  return params
}

async function launch() {
  if (!canLaunch.value) return
  launching.value = true
  batchResult.value = null
  try {
    const params = _fileParams()
    const name = jobName.value.trim() || autoJobName.value
    if (name) params.job_name = name

    const { data } = await axios.post(
      `/api/analysis/${route.params.id}/run`,
      cfg,
      { params }
    )
    store.startJob(data.job_id)
  } catch (e) {
    alert('Failed to launch: ' + (e.response?.data?.detail || e.message))
  } finally {
    launching.value = false
  }
}

async function launchBatch() {
  if (!canLaunch.value || batchJobCount.value === 0) return
  launching.value = true
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

    const { data } = await axios.post(
      `/api/analysis/${route.params.id}/batch`,
      { config: cfg, sweep: { sweeps: sweepObj } },
      { params }
    )
    batchResult.value = data
  } catch (e) {
    alert('Batch launch failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    launching.value = false
  }
}
</script>

<style scoped>
.params-tab { max-width: 100%; }

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
  font-size: 0.72rem;
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

@media (max-width: 900px) {
  .settings-grid { grid-template-columns: 1fr; }
}
</style>
