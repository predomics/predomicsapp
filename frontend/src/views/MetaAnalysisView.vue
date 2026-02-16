<template>
  <div class="meta-analysis">
    <h2>{{ $t('meta.title') }}</h2>
    <p class="subtitle">{{ $t('meta.subtitle') }}</p>

    <!-- Job Picker -->
    <section class="section">
      <h3>{{ $t('meta.selectJobs') }}</h3>
      <div class="picker">
        <div class="search-row">
          <input
            type="text"
            v-model="searchQuery"
            class="search-input"
            :placeholder="$t('meta.searchPlaceholder')"
            @input="debouncedSearch"
          />
          <span class="chip-count">{{ $t('meta.selected', { n: selectedJobs.length }) }}</span>
        </div>

        <!-- Search results dropdown -->
        <div class="search-results" v-if="searchResults.length > 0 && searchQuery.length > 0">
          <div
            v-for="job in searchResults"
            :key="job.job_id"
            class="search-item"
            :class="{ disabled: isSelected(job.job_id) }"
            @click="addJob(job)"
          >
            <div class="search-item-main">
              <span class="project-name">{{ job.project_name }}</span>
              <span class="job-name">{{ job.job_name || job.job_id.slice(0, 8) }}</span>
            </div>
            <div class="search-item-meta">
              <span v-if="job.best_auc != null">{{ $t('results.auc') }} {{ job.best_auc.toFixed(4) }}</span>
              <span v-if="job.best_k != null">k={{ job.best_k }}</span>
              <span v-if="job.language">{{ job.language }}</span>
            </div>
          </div>
        </div>
        <div v-if="searchLoading" class="search-loading">{{ $t('meta.searching') }}</div>

        <!-- Selected job chips -->
        <div class="selected-chips" v-if="selectedJobs.length > 0">
          <div class="chip" v-for="job in selectedJobs" :key="job.job_id">
            <span class="chip-project">{{ job.project_name }}</span>
            <span class="chip-job">{{ job.job_name || job.job_id.slice(0, 8) }}</span>
            <button class="chip-remove" @click="removeJob(job.job_id)">&times;</button>
          </div>
        </div>

        <button
          class="btn btn-primary"
          @click="runAnalysis"
          :disabled="selectedJobs.length < 2 || analysisLoading"
        >
          {{ analysisLoading ? $t('meta.analyzing') : $t('meta.runAnalysis') }}
        </button>
      </div>
    </section>

    <!-- Results -->
    <template v-if="results">
      <!-- Meta-AUC Card -->
      <section class="section">
        <div class="meta-auc-card">
          <div class="meta-auc-value">{{ results.meta_auc?.toFixed(4) || '—' }}</div>
          <div class="meta-auc-label">{{ $t('meta.metaAuc', { n: results.jobs.length }) }}</div>
        </div>
      </section>

      <!-- Metrics Comparison Table -->
      <section class="section">
        <h3>{{ $t('meta.metricsComparison') }}</h3>
        <div class="table-wrap">
          <table class="metrics-table">
            <thead>
              <tr>
                <th>{{ $t('results.metric') }}</th>
                <th v-for="job in results.jobs" :key="job.job_id">
                  <div class="col-header">
                    <span class="col-project">{{ job.project_name }}</span>
                    <span class="col-job">{{ job.job_name || job.job_id.slice(0, 8) }}</span>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="metric in metricRows" :key="metric.key">
                <td class="metric-name">{{ metric.label }}</td>
                <td
                  v-for="job in results.jobs"
                  :key="job.job_id"
                  :class="{ 'best-val': isBest(metric.key, job) }"
                >
                  {{ formatMetric(job[metric.key], metric.key) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Feature Overlap Chart -->
      <section class="section">
        <h3>{{ $t('meta.featureOverlap') }}</h3>
        <p class="info-text">{{ $t('meta.featureOverlapDesc') }}</p>
        <div ref="overlapChartEl" class="plotly-chart plotly-chart-tall"></div>
      </section>

      <!-- Concordance Matrix -->
      <section class="section">
        <h3>{{ $t('meta.concordance') }}</h3>
        <p class="info-text">
          {{ $t('meta.concordanceDesc') }}
          <span class="concordant-count">{{ concordantCount }} / {{ totalFeatures }} {{ $t('meta.concordant').toLowerCase() }}</span>
        </p>
        <div class="table-wrap">
          <table class="concordance-table">
            <thead>
              <tr>
                <th>{{ $t('results.colFeature') }}</th>
                <th v-for="job in results.jobs" :key="job.job_id" class="col-narrow">
                  {{ job.job_name || job.job_id.slice(0, 8) }}
                </th>
                <th>{{ $t('meta.status') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="feat in sortedFeatures" :key="feat.name">
                <td class="feature-name">{{ feat.label }}</td>
                <td
                  v-for="job in results.jobs"
                  :key="job.job_id"
                  class="coef-cell"
                  :class="feat.cellClass[job.job_id]"
                >
                  {{ feat.cellValue[job.job_id] }}
                </td>
                <td>
                  <span class="concordance-badge" :class="feat.concordant ? 'concordant' : 'discordant'">
                    {{ feat.concordant ? $t('meta.concordant') : $t('meta.discordant') }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <div v-if="error" class="error-msg">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChartTheme } from '../composables/useChartTheme'
import axios from 'axios'

const { t } = useI18n()
const { chartColors, chartLayout, featureLabel } = useChartTheme()

// Plotly lazy-load
let Plotly = null
async function ensurePlotly() {
  if (!Plotly) {
    const mod = await import('plotly.js-dist-min')
    Plotly = mod.default
  }
}

// State
const searchQuery = ref('')
const searchResults = ref([])
const searchLoading = ref(false)
const selectedJobs = ref([])
const analysisLoading = ref(false)
const results = ref(null)
const error = ref('')
const overlapChartEl = ref(null)

const metricRows = computed(() => [
  { key: 'best_auc', label: t('results.auc') },
  { key: 'accuracy', label: t('results.accuracy') },
  { key: 'sensitivity', label: t('results.sensitivity') },
  { key: 'specificity', label: t('results.specificity') },
  { key: 'best_k', label: t('results.featuresK') },
  { key: 'language', label: t('results.language') },
  { key: 'data_type', label: t('results.dataType') },
])

// Search
let _searchTimer = null
function debouncedSearch() {
  clearTimeout(_searchTimer)
  _searchTimer = setTimeout(doSearch, 300)
}

async function doSearch() {
  if (!searchQuery.value.trim()) {
    searchResults.value = []
    return
  }
  searchLoading.value = true
  try {
    const { data } = await axios.get('/api/meta-analysis/searchable-jobs', {
      params: { q: searchQuery.value.trim() }
    })
    searchResults.value = data
  } catch {
    searchResults.value = []
  } finally {
    searchLoading.value = false
  }
}

function isSelected(jobId) {
  return selectedJobs.value.some(j => j.job_id === jobId)
}

function addJob(job) {
  if (isSelected(job.job_id) || selectedJobs.value.length >= 10) return
  selectedJobs.value.push(job)
  searchQuery.value = ''
  searchResults.value = []
}

function removeJob(jobId) {
  selectedJobs.value = selectedJobs.value.filter(j => j.job_id !== jobId)
}

// Analysis
async function runAnalysis() {
  if (selectedJobs.value.length < 2) return
  analysisLoading.value = true
  error.value = ''
  results.value = null
  try {
    const { data } = await axios.post('/api/meta-analysis/compare', {
      job_ids: selectedJobs.value.map(j => j.job_id)
    })
    results.value = data
    await nextTick()
    await ensurePlotly()
    renderOverlapChart()
  } catch (e) {
    error.value = e.response?.data?.detail || 'Meta-analysis failed'
  } finally {
    analysisLoading.value = false
  }
}

// Metrics helpers
function formatMetric(value, key) {
  if (value == null) return '—'
  if (typeof value === 'number') return value.toFixed(4)
  return value
}

function isBest(key, job) {
  if (!results.value || typeof job[key] !== 'number') return false
  const vals = results.value.jobs.map(j => j[key]).filter(v => typeof v === 'number')
  return job[key] === Math.max(...vals)
}

// Concordance
const concordantCount = computed(() => {
  if (!results.value) return 0
  return Object.values(results.value.concordance).filter(c => c.concordant).length
})

const totalFeatures = computed(() => {
  if (!results.value) return 0
  return Object.keys(results.value.concordance).length
})

const sortedFeatures = computed(() => {
  if (!results.value) return []
  const entries = Object.entries(results.value.concordance)
  // Sort: shared across more jobs first, then by name
  return entries.map(([name, info]) => {
    const jobIds = results.value.feature_overlap[name] || []
    const cellClass = {}
    const cellValue = {}
    for (const job of results.value.jobs) {
      const coef = job.named_features[name]
      if (coef === undefined) {
        cellClass[job.job_id] = 'absent'
        cellValue[job.job_id] = '—'
      } else if (coef > 0) {
        cellClass[job.job_id] = 'positive'
        cellValue[job.job_id] = '+' + coef.toFixed(2)
      } else {
        cellClass[job.job_id] = 'negative'
        cellValue[job.job_id] = coef.toFixed(2)
      }
    }
    return {
      name,
      label: featureLabel(name),
      concordant: info.concordant,
      jobCount: jobIds.length,
      cellClass,
      cellValue,
    }
  }).sort((a, b) => b.jobCount - a.jobCount || a.name.localeCompare(b.name))
})

// Overlap chart
function renderOverlapChart() {
  if (!overlapChartEl.value || !results.value) return
  const c = chartColors()
  const overlap = results.value.feature_overlap
  const jobCount = results.value.jobs.length

  // Group features by how many jobs they appear in
  const groups = {}
  for (const [fname, jids] of Object.entries(overlap)) {
    const count = jids.length
    if (!groups[count]) groups[count] = []
    groups[count].push(fname)
  }

  // Build horizontal bar trace: one bar per feature, grouped
  const allFeatures = []
  const allCounts = []
  const allColors = []

  // Sort: features in most jobs first
  for (let n = jobCount; n >= 1; n--) {
    const feats = groups[n] || []
    feats.sort()
    for (const f of feats) {
      allFeatures.push(featureLabel(f))
      allCounts.push(n)
      // Color intensity by overlap count
      const frac = n / jobCount
      allColors.push(`rgba(79, 195, 247, ${0.3 + 0.7 * frac})`)
    }
  }

  // Reverse for bottom-to-top
  allFeatures.reverse()
  allCounts.reverse()
  allColors.reverse()

  Plotly.newPlot(overlapChartEl.value, [{
    type: 'bar',
    orientation: 'h',
    y: allFeatures,
    x: allCounts,
    marker: { color: allColors },
    hovertemplate: '%{y}<br>Present in %{x} / ' + jobCount + ' cohorts<extra></extra>',
  }], chartLayout({
    xaxis: {
      title: t('meta.cohorts', { n: jobCount }),
      dtick: 1,
      range: [0, jobCount + 0.5],
      color: c.text,
      gridcolor: c.grid,
    },
    yaxis: { automargin: true, color: c.text },
    height: Math.max(300, allFeatures.length * 22 + 80),
    margin: { t: 10, b: 50, l: 200, r: 20 },
  }), { responsive: true, displayModeBar: false })
}

// Load initial results on mount (show all searchable jobs)
onMounted(async () => {
  searchLoading.value = true
  try {
    const { data } = await axios.get('/api/meta-analysis/searchable-jobs')
    searchResults.value = data
  } catch { /* ignore */ }
  finally { searchLoading.value = false }
})
</script>

<style scoped>
.meta-analysis {
  max-width: 1200px;
}
h2 {
  color: var(--text-primary);
  font-size: 1.5rem;
  margin-bottom: 0.25rem;
}
.subtitle {
  color: var(--text-muted);
  font-size: 0.9rem;
  margin-bottom: 1.5rem;
}
.section {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--card-radius, 12px);
  padding: 1.25rem;
  margin-bottom: 1.25rem;
}
.section h3 {
  color: var(--text-primary);
  font-size: 1rem;
  margin-bottom: 0.75rem;
}
.info-text {
  color: var(--text-muted);
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}

/* Picker */
.search-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.5rem;
}
.search-input {
  flex: 1;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-input);
  color: var(--text-body);
  font-size: 0.9rem;
}
.chip-count {
  color: var(--text-muted);
  font-size: 0.82rem;
  white-space: nowrap;
}
.search-results {
  max-height: 250px;
  overflow-y: auto;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  margin-bottom: 0.75rem;
}
.search-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  transition: background 0.1s;
  border-bottom: 1px solid var(--border-lighter);
}
.search-item:hover:not(.disabled) {
  background: var(--bg-card-hover);
}
.search-item.disabled {
  opacity: 0.4;
  cursor: default;
}
.search-item-main {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
}
.project-name {
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--text-primary);
}
.job-name {
  font-size: 0.82rem;
  color: var(--text-secondary);
}
.search-item-meta {
  display: flex;
  gap: 0.75rem;
  font-size: 0.78rem;
  color: var(--text-muted);
}
.search-loading {
  padding: 0.5rem;
  color: var(--text-muted);
  font-size: 0.85rem;
}

/* Chips */
.selected-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.75rem 0;
}
.chip {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.3rem 0.6rem;
  background: var(--bg-badge);
  border: 1px solid var(--border);
  border-radius: 20px;
  font-size: 0.78rem;
}
.chip-project {
  font-weight: 600;
  color: var(--text-primary);
}
.chip-job {
  color: var(--text-secondary);
}
.chip-remove {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 1rem;
  cursor: pointer;
  padding: 0 0.15rem;
  line-height: 1;
}
.chip-remove:hover { color: var(--danger); }

/* Button */
.btn {
  padding: 0.5rem 1.25rem;
  border: none;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-primary {
  background: var(--accent);
  color: var(--accent-text);
}
.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Meta-AUC card */
.meta-auc-card {
  text-align: center;
  padding: 1rem;
}
.meta-auc-value {
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--accent);
}
.meta-auc-label {
  font-size: 0.9rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}

/* Tables */
.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border-light);
  border-radius: 8px;
}
.metrics-table, .concordance-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.metrics-table th, .concordance-table th {
  background: var(--bg-card);
  padding: 0.5rem 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  border-bottom: 2px solid var(--border-light);
  white-space: nowrap;
}
.metrics-table td, .concordance-table td {
  padding: 0.45rem 0.75rem;
  border-bottom: 1px solid var(--border-lighter);
  text-align: center;
}
.metric-name, .feature-name {
  text-align: left !important;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
}
.best-val {
  color: var(--accent);
  font-weight: 700;
}
.col-header {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.col-project {
  font-size: 0.75rem;
  color: var(--text-muted);
}
.col-job {
  font-size: 0.82rem;
}
.col-narrow {
  min-width: 80px;
}

/* Concordance cells */
.coef-cell.positive {
  color: var(--success);
  font-weight: 600;
}
.coef-cell.negative {
  color: var(--danger);
  font-weight: 600;
}
.coef-cell.absent {
  color: var(--text-faint);
}
.concordance-badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  font-size: 0.72rem;
  font-weight: 600;
}
.concordance-badge.concordant {
  background: rgba(100, 200, 100, 0.15);
  color: var(--success);
}
.concordance-badge.discordant {
  background: rgba(200, 80, 80, 0.15);
  color: var(--danger);
}
.concordant-count {
  font-weight: 600;
  color: var(--text-primary);
}

/* Plotly chart */
.plotly-chart {
  width: 100%;
  min-height: 200px;
}
.plotly-chart-tall {
  min-height: 400px;
}

.error-msg {
  background: var(--danger-bg);
  color: var(--danger);
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.85rem;
}
</style>
