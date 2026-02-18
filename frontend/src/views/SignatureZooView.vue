<template>
  <div class="signature-zoo">
    <h2>{{ $t('signatureZoo.title') }}</h2>
    <p class="subtitle">{{ $t('signatureZoo.subtitle') }}</p>

    <!-- Filters bar -->
    <section class="section filters-bar">
      <div class="filters-row">
        <select v-model="filterDisease" class="filter-select">
          <option value="">{{ $t('signatureZoo.allDiseases') }}</option>
          <option v-for="d in diseaseOptions" :key="d" :value="d">{{ d }}</option>
        </select>
        <select v-model="filterMethod" class="filter-select">
          <option value="">{{ $t('signatureZoo.allMethods') }}</option>
          <option v-for="m in methodOptions" :key="m" :value="m">{{ m }}</option>
        </select>
        <input
          type="text"
          v-model="searchQuery"
          class="search-input"
          :placeholder="$t('signatureZoo.searchPlaceholder')"
        />
        <button
          v-if="compareSelection.length >= 2"
          class="btn btn-primary"
          @click="runCompare"
          :disabled="compareLoading"
        >
          {{ compareLoading ? $t('common.loading') : $t('signatureZoo.compareSelected', { n: compareSelection.length }) }}
        </button>
      </div>
    </section>

    <!-- Loading state -->
    <div v-if="loading" class="loading-msg">{{ $t('common.loading') }}</div>

    <!-- Signature cards grid -->
    <div v-else class="cards-grid">
      <div
        v-for="sig in filteredSignatures"
        :key="sig.id"
        class="sig-card"
        :class="{ 'sig-card-selected': compareSelection.includes(sig.id) }"
      >
        <div class="sig-card-header">
          <h3 class="sig-name">{{ sig.name }}</h3>
          <label class="compare-check" :title="$t('signatureZoo.selectCompare')">
            <input
              type="checkbox"
              :checked="compareSelection.includes(sig.id)"
              @change="toggleCompare(sig.id)"
            />
          </label>
        </div>
        <div class="sig-badges">
          <span class="badge badge-disease">{{ sig.disease || sig.phenotype }}</span>
          <span class="badge badge-method">{{ sig.method }}</span>
        </div>
        <div class="sig-citation" v-if="sig.publication && sig.publication.author">
          {{ sig.publication.author }} ({{ sig.publication.year }}) &mdash; <em>{{ sig.publication.journal }}</em>
        </div>
        <div class="sig-stats">
          <span class="stat">
            <strong>{{ sig.features ? sig.features.length : 0 }}</strong> {{ $t('signatureZoo.features') }}
          </span>
          <span v-if="sig.performance && sig.performance.auc" class="stat auc-stat">
            AUC <strong>{{ sig.performance.auc.toFixed(2) }}</strong>
          </span>
        </div>
        <div class="sig-tags" v-if="sig.tags && sig.tags.length">
          <span class="tag-chip" v-for="tag in sig.tags" :key="tag">{{ tag }}</span>
        </div>
        <div class="sig-actions">
          <button class="btn btn-sm" @click="viewSignature(sig)">{{ $t('signatureZoo.view') }}</button>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!loading && filteredSignatures.length === 0" class="empty-state">
      {{ $t('signatureZoo.noSignatures') }}
    </div>

    <!-- Detail Modal -->
    <div v-if="detailSig" class="modal-overlay" @click.self="detailSig = null">
      <div class="modal-content">
        <div class="modal-header">
          <h2>{{ detailSig.name }}</h2>
          <button class="modal-close" @click="detailSig = null">&times;</button>
        </div>

        <div class="modal-body">
          <!-- Badges -->
          <div class="sig-badges" style="margin-bottom: 1rem;">
            <span class="badge badge-disease">{{ detailSig.disease || detailSig.phenotype }}</span>
            <span class="badge badge-method">{{ detailSig.method }}</span>
          </div>

          <!-- Publication -->
          <div class="detail-section" v-if="detailSig.publication && detailSig.publication.author">
            <h4>{{ $t('signatureZoo.publication') }}</h4>
            <p>
              {{ detailSig.publication.author }} ({{ detailSig.publication.year }}).
              <em>{{ detailSig.publication.journal }}</em>.
              <a v-if="detailSig.publication.doi" :href="'https://doi.org/' + detailSig.publication.doi" target="_blank" rel="noopener">
                DOI: {{ detailSig.publication.doi }}
              </a>
            </p>
          </div>

          <!-- Cohort info -->
          <div class="detail-section" v-if="detailSig.cohort_info">
            <h4>{{ $t('signatureZoo.cohortInfo') }}</h4>
            <div class="cohort-grid">
              <div v-if="detailSig.cohort_info.n_samples" class="cohort-item">
                <span class="cohort-label">{{ $t('signatureZoo.nSamples') }}</span>
                <span class="cohort-value">{{ detailSig.cohort_info.n_samples }}</span>
              </div>
              <div v-if="detailSig.cohort_info.n_cases" class="cohort-item">
                <span class="cohort-label">{{ $t('signatureZoo.nCases') }}</span>
                <span class="cohort-value">{{ detailSig.cohort_info.n_cases }}</span>
              </div>
              <div v-if="detailSig.cohort_info.n_controls" class="cohort-item">
                <span class="cohort-label">{{ $t('signatureZoo.nControls') }}</span>
                <span class="cohort-value">{{ detailSig.cohort_info.n_controls }}</span>
              </div>
              <div v-if="detailSig.cohort_info.population" class="cohort-item">
                <span class="cohort-label">{{ $t('signatureZoo.population') }}</span>
                <span class="cohort-value">{{ detailSig.cohort_info.population }}</span>
              </div>
              <div v-if="detailSig.cohort_info.country" class="cohort-item">
                <span class="cohort-label">{{ $t('signatureZoo.country') }}</span>
                <span class="cohort-value">{{ detailSig.cohort_info.country }}</span>
              </div>
            </div>
          </div>

          <!-- Performance metrics -->
          <div class="detail-section" v-if="detailSig.performance">
            <h4>{{ $t('signatureZoo.performanceMetrics') }}</h4>
            <div class="perf-grid">
              <div v-if="detailSig.performance.auc != null" class="perf-item">
                <span class="perf-label">AUC</span>
                <span class="perf-value">{{ detailSig.performance.auc.toFixed(4) }}</span>
                <div class="perf-bar">
                  <div class="perf-bar-fill" :style="{ width: (detailSig.performance.auc * 100) + '%' }"></div>
                </div>
              </div>
              <div v-if="detailSig.performance.accuracy != null" class="perf-item">
                <span class="perf-label">{{ $t('signatureZoo.accuracy') }}</span>
                <span class="perf-value">{{ detailSig.performance.accuracy.toFixed(4) }}</span>
                <div class="perf-bar">
                  <div class="perf-bar-fill" :style="{ width: (detailSig.performance.accuracy * 100) + '%' }"></div>
                </div>
              </div>
              <div v-if="detailSig.performance.sensitivity != null" class="perf-item">
                <span class="perf-label">{{ $t('signatureZoo.sensitivity') }}</span>
                <span class="perf-value">{{ detailSig.performance.sensitivity.toFixed(4) }}</span>
                <div class="perf-bar">
                  <div class="perf-bar-fill" :style="{ width: (detailSig.performance.sensitivity * 100) + '%' }"></div>
                </div>
              </div>
              <div v-if="detailSig.performance.specificity != null" class="perf-item">
                <span class="perf-label">{{ $t('signatureZoo.specificity') }}</span>
                <span class="perf-value">{{ detailSig.performance.specificity.toFixed(4) }}</span>
                <div class="perf-bar">
                  <div class="perf-bar-fill" :style="{ width: (detailSig.performance.specificity * 100) + '%' }"></div>
                </div>
              </div>
            </div>
          </div>

          <!-- Feature table -->
          <div class="detail-section">
            <h4>{{ $t('signatureZoo.featureTable') }} ({{ detailSig.features ? detailSig.features.length : 0 }})</h4>
            <div class="table-wrap">
              <table class="features-table">
                <thead>
                  <tr>
                    <th>{{ $t('signatureZoo.featureName') }}</th>
                    <th>{{ $t('signatureZoo.coefficient') }}</th>
                    <th>{{ $t('signatureZoo.direction') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="feat in sortedFeatures" :key="feat.name">
                    <td class="feature-name">{{ feat.name }}</td>
                    <td :class="feat.coefficient > 0 ? 'coef-positive' : 'coef-negative'">
                      {{ feat.coefficient > 0 ? '+' : '' }}{{ feat.coefficient.toFixed(2) }}
                    </td>
                    <td>
                      <span class="direction-badge" :class="feat.direction">
                        {{ feat.direction === 'enriched' ? $t('signatureZoo.enriched') : $t('signatureZoo.depleted') }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Tags -->
          <div class="detail-section" v-if="detailSig.tags && detailSig.tags.length">
            <h4>{{ $t('signatureZoo.tags') }}</h4>
            <div class="sig-tags">
              <span class="tag-chip" v-for="tag in detailSig.tags" :key="tag">{{ tag }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Compare Results Modal -->
    <div v-if="compareResults" class="modal-overlay" @click.self="compareResults = null">
      <div class="modal-content modal-wide">
        <div class="modal-header">
          <h2>{{ $t('signatureZoo.comparisonResults') }}</h2>
          <button class="modal-close" @click="compareResults = null">&times;</button>
        </div>

        <div class="modal-body">
          <!-- Performance comparison -->
          <div class="detail-section">
            <h4>{{ $t('signatureZoo.performanceComparison') }}</h4>
            <div ref="perfChartEl" class="plotly-chart"></div>
          </div>

          <!-- Overlap matrix -->
          <div class="detail-section">
            <h4>{{ $t('signatureZoo.featureOverlapMatrix') }}</h4>
            <div class="table-wrap">
              <table class="features-table">
                <thead>
                  <tr>
                    <th></th>
                    <th v-for="sig in compareResults.signatures" :key="sig.id">
                      {{ sig.name.length > 30 ? sig.name.slice(0, 30) + '...' : sig.name }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in compareResults.overlap_matrix" :key="i">
                    <td class="feature-name">{{ compareResults.signatures[i].name.length > 30 ? compareResults.signatures[i].name.slice(0, 30) + '...' : compareResults.signatures[i].name }}</td>
                    <td v-for="(cell, j) in row" :key="j" :class="{ 'best-val': i === j }">
                      {{ cell.shared }} (J={{ cell.jaccard.toFixed(2) }})
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Common features -->
          <div class="detail-section">
            <h4>{{ $t('signatureZoo.commonFeatures') }} ({{ compareResults.common_features.length }})</h4>
            <div v-if="compareResults.common_features.length > 0" class="common-features-list">
              <span class="tag-chip tag-common" v-for="f in compareResults.common_features" :key="f">{{ f }}</span>
            </div>
            <p v-else class="info-text">{{ $t('signatureZoo.noCommonFeatures') }}</p>
          </div>

          <!-- Feature presence chart -->
          <div class="detail-section">
            <h4>{{ $t('signatureZoo.featurePresence') }}</h4>
            <div ref="overlapChartEl" class="plotly-chart plotly-chart-tall"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Error message -->
    <div v-if="error" class="error-msg">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'

const { t } = useI18n()

// Plotly lazy-load
let Plotly = null
async function ensurePlotly() {
  if (!Plotly) {
    const mod = await import('plotly.js-dist-min')
    Plotly = mod.default
  }
}

// State
const signatures = ref([])
const loading = ref(true)
const error = ref('')
const searchQuery = ref('')
const filterDisease = ref('')
const filterMethod = ref('')
const detailSig = ref(null)
const compareSelection = ref([])
const compareResults = ref(null)
const compareLoading = ref(false)
const perfChartEl = ref(null)
const overlapChartEl = ref(null)

// Computed
const diseaseOptions = computed(() => {
  const set = new Set()
  for (const s of signatures.value) {
    if (s.disease) set.add(s.disease)
  }
  return Array.from(set).sort()
})

const methodOptions = computed(() => {
  const set = new Set()
  for (const s of signatures.value) {
    if (s.method) set.add(s.method)
  }
  return Array.from(set).sort()
})

const filteredSignatures = computed(() => {
  let result = signatures.value

  if (filterDisease.value) {
    const dl = filterDisease.value.toLowerCase()
    result = result.filter(s =>
      (s.disease || '').toLowerCase().includes(dl) ||
      (s.phenotype || '').toLowerCase().includes(dl)
    )
  }

  if (filterMethod.value) {
    const ml = filterMethod.value.toLowerCase()
    result = result.filter(s => (s.method || '').toLowerCase().includes(ml))
  }

  if (searchQuery.value.trim()) {
    const sl = searchQuery.value.trim().toLowerCase()
    result = result.filter(s =>
      s.name.toLowerCase().includes(sl) ||
      (s.features || []).some(f => f.name.toLowerCase().includes(sl)) ||
      (s.tags || []).some(tag => tag.toLowerCase().includes(sl))
    )
  }

  return result
})

const sortedFeatures = computed(() => {
  if (!detailSig.value || !detailSig.value.features) return []
  return [...detailSig.value.features].sort((a, b) => b.coefficient - a.coefficient)
})

// Methods
async function fetchSignatures() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await axios.get('/api/signature-zoo/')
    signatures.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to load signatures'
  } finally {
    loading.value = false
  }
}

function viewSignature(sig) {
  detailSig.value = sig
}

function toggleCompare(id) {
  const idx = compareSelection.value.indexOf(id)
  if (idx >= 0) {
    compareSelection.value.splice(idx, 1)
  } else {
    if (compareSelection.value.length >= 10) return
    compareSelection.value.push(id)
  }
}

async function runCompare() {
  if (compareSelection.value.length < 2) return
  compareLoading.value = true
  error.value = ''
  compareResults.value = null
  try {
    const { data } = await axios.get('/api/signature-zoo/compare', {
      params: { ids: compareSelection.value.join(',') }
    })
    compareResults.value = data
    await nextTick()
    await ensurePlotly()
    renderPerfChart()
    renderOverlapChart()
  } catch (e) {
    error.value = e.response?.data?.detail || 'Comparison failed'
  } finally {
    compareLoading.value = false
  }
}

function renderPerfChart() {
  if (!perfChartEl.value || !compareResults.value) return
  const perf = compareResults.value.performance_comparison
  const names = perf.map(p => p.name.length > 25 ? p.name.slice(0, 25) + '...' : p.name)

  const metrics = ['auc', 'accuracy', 'sensitivity', 'specificity']
  const colors = ['#4fc3f7', '#66bb6a', '#ffa726', '#ef5350']

  const traces = metrics.map((metric, i) => ({
    name: metric.toUpperCase(),
    type: 'bar',
    x: names,
    y: perf.map(p => p[metric]),
    marker: { color: colors[i] },
  }))

  Plotly.newPlot(perfChartEl.value, traces, {
    barmode: 'group',
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { color: getComputedStyle(document.documentElement).getPropertyValue('--text-body').trim() || '#2c3e50' },
    margin: { t: 20, b: 80, l: 50, r: 20 },
    yaxis: { range: [0, 1], gridcolor: 'rgba(128,128,128,0.2)' },
    xaxis: { tickangle: -20 },
    legend: { orientation: 'h', y: 1.1 },
    height: 320,
  }, { responsive: true, displayModeBar: false })
}

function renderOverlapChart() {
  if (!overlapChartEl.value || !compareResults.value) return

  const presence = compareResults.value.feature_presence
  const sigCount = compareResults.value.signatures.length

  // Group features by how many signatures they appear in
  const entries = Object.entries(presence)
    .map(([name, ids]) => ({ name, count: ids.length }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))

  const featureNames = entries.map(e => e.name)
  const counts = entries.map(e => e.count)
  const barColors = counts.map(c => {
    const frac = c / sigCount
    return `rgba(79, 195, 247, ${0.3 + 0.7 * frac})`
  })

  // Reverse for bottom-to-top
  featureNames.reverse()
  counts.reverse()
  barColors.reverse()

  const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-body').trim() || '#2c3e50'

  Plotly.newPlot(overlapChartEl.value, [{
    type: 'bar',
    orientation: 'h',
    y: featureNames,
    x: counts,
    marker: { color: barColors },
    hovertemplate: '%{y}<br>Present in %{x} / ' + sigCount + ' signatures<extra></extra>',
  }], {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { color: textColor },
    xaxis: {
      title: t('signatureZoo.signaturesCount', { n: sigCount }),
      dtick: 1,
      range: [0, sigCount + 0.5],
      gridcolor: 'rgba(128,128,128,0.2)',
    },
    yaxis: { automargin: true },
    height: Math.max(300, featureNames.length * 22 + 80),
    margin: { t: 10, b: 50, l: 220, r: 20 },
  }, { responsive: true, displayModeBar: false })
}

// Lifecycle
onMounted(() => {
  fetchSignatures()
})
</script>

<style scoped>
.signature-zoo {
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

/* Filters */
.section {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--card-radius, 12px);
  padding: 1rem 1.25rem;
  margin-bottom: 1.25rem;
}
.filters-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.filter-select {
  padding: 0.45rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-input);
  color: var(--text-body);
  font-size: 0.85rem;
  min-width: 140px;
}
.search-input {
  flex: 1;
  min-width: 200px;
  padding: 0.45rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-input);
  color: var(--text-body);
  font-size: 0.85rem;
}

/* Cards grid */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.sig-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--card-radius, 12px);
  padding: 1.25rem;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.sig-card:hover {
  box-shadow: var(--card-shadow-hover);
}
.sig-card-selected {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px var(--brand);
}
.sig-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.sig-name {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
}
.compare-check input {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--brand);
}
.sig-badges {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}
.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.badge-disease {
  background: var(--info-bg);
  color: var(--info);
}
.badge-method {
  background: var(--badge-job);
  color: var(--badge-job-text);
}
.sig-citation {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
  line-height: 1.4;
}
.sig-stats {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.5rem;
}
.stat {
  font-size: 0.82rem;
  color: var(--text-secondary);
}
.auc-stat strong {
  color: var(--accent);
}
.sig-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-bottom: 0.75rem;
}
.tag-chip {
  display: inline-block;
  padding: 0.12rem 0.4rem;
  background: var(--bg-badge);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  font-size: 0.7rem;
  color: var(--text-muted);
}
.tag-common {
  background: var(--success-bg);
  color: var(--success);
  border-color: var(--success);
}
.sig-actions {
  display: flex;
  gap: 0.5rem;
}

/* Buttons */
.btn {
  padding: 0.4rem 1rem;
  border: none;
  border-radius: 8px;
  font-size: 0.82rem;
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
.btn-sm {
  padding: 0.3rem 0.75rem;
  font-size: 0.78rem;
  background: var(--bg-badge);
  color: var(--text-secondary);
  border: 1px solid var(--border);
}
.btn-sm:hover {
  background: var(--bg-card-hover);
  border-color: var(--brand);
  color: var(--brand);
}

/* Modal overlay */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 2rem;
}
.modal-content {
  background: var(--bg-card);
  border-radius: var(--card-radius, 12px);
  max-width: 700px;
  width: 100%;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: var(--shadow-card);
}
.modal-wide {
  max-width: 950px;
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 1.5rem 0.75rem;
  border-bottom: 1px solid var(--border-light);
}
.modal-header h2 {
  font-size: 1.15rem;
  margin: 0;
}
.modal-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.25rem;
  line-height: 1;
}
.modal-close:hover {
  color: var(--danger);
}
.modal-body {
  padding: 1.25rem 1.5rem;
}

/* Detail sections */
.detail-section {
  margin-bottom: 1.25rem;
}
.detail-section h4 {
  font-size: 0.9rem;
  color: var(--text-primary);
  font-weight: 600;
  margin-bottom: 0.5rem;
}
.detail-section p {
  font-size: 0.85rem;
  color: var(--text-secondary);
  line-height: 1.5;
}
.detail-section a {
  color: var(--brand);
  text-decoration: none;
}
.detail-section a:hover {
  text-decoration: underline;
}

/* Cohort grid */
.cohort-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 0.5rem;
}
.cohort-item {
  display: flex;
  flex-direction: column;
  background: var(--bg-badge);
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
}
.cohort-label {
  font-size: 0.72rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.cohort-value {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}

/* Performance grid */
.perf-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 0.75rem;
}
.perf-item {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.perf-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.perf-value {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--accent);
}
.perf-bar {
  height: 4px;
  background: var(--border-light);
  border-radius: 2px;
  overflow: hidden;
}
.perf-bar-fill {
  height: 100%;
  background: var(--brand);
  border-radius: 2px;
  transition: width 0.3s;
}

/* Feature table */
.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border-light);
  border-radius: 8px;
}
.features-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.features-table th {
  background: var(--bg-card);
  padding: 0.5rem 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  border-bottom: 2px solid var(--border-light);
  white-space: nowrap;
  text-align: left;
}
.features-table td {
  padding: 0.4rem 0.75rem;
  border-bottom: 1px solid var(--border-lighter);
}
.feature-name {
  font-weight: 500;
  color: var(--text-secondary);
  font-style: italic;
}
.coef-positive {
  color: var(--success);
  font-weight: 600;
}
.coef-negative {
  color: var(--danger);
  font-weight: 600;
}
.direction-badge {
  display: inline-block;
  padding: 0.1rem 0.4rem;
  border-radius: 8px;
  font-size: 0.7rem;
  font-weight: 600;
}
.direction-badge.enriched {
  background: rgba(100, 200, 100, 0.15);
  color: var(--success);
}
.direction-badge.depleted {
  background: rgba(200, 80, 80, 0.15);
  color: var(--danger);
}
.best-val {
  font-weight: 700;
  color: var(--accent);
}

/* Common features list */
.common-features-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

/* Plotly chart */
.plotly-chart {
  width: 100%;
  min-height: 320px;
}
.plotly-chart-tall {
  min-height: 400px;
}

/* States */
.loading-msg {
  text-align: center;
  color: var(--text-muted);
  font-size: 0.9rem;
  padding: 2rem;
}
.empty-state {
  text-align: center;
  color: var(--text-muted);
  font-size: 0.9rem;
  padding: 3rem;
  background: var(--bg-card);
  border-radius: var(--card-radius, 12px);
  border: 1px solid var(--border-light);
}
.error-msg {
  background: var(--danger-bg);
  color: var(--danger);
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.85rem;
  margin-top: 1rem;
}
.info-text {
  color: var(--text-muted);
  font-size: 0.85rem;
}
</style>
