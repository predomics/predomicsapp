<template>
  <div class="data-explore-tab">
    <!-- Sub-tabs -->
    <nav class="sub-tabs">
      <button :class="{ active: subTab === 'summary' }" @click="subTab = 'summary'">Summary</button>
      <button :class="{ active: subTab === 'features' }" @click="subTab = 'features'">Features</button>
      <button :class="{ active: subTab === 'visualizations' }" @click="subTab = 'visualizations'">Visualizations</button>
    </nav>

    <!-- ====== SUMMARY SUB-TAB ====== -->
    <div v-if="subTab === 'summary'" class="sub-content">
      <div v-if="summary" class="summary-grid">
        <div class="stat-card">
          <div class="stat-value">{{ summary.n_features }}</div>
          <div class="stat-label">Total Features</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summary.n_samples }}</div>
          <div class="stat-label">Samples</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summary.n_classes }}</div>
          <div class="stat-label">Classes</div>
        </div>
        <div class="stat-card" v-if="featureStats">
          <div class="stat-value accent">{{ featureStats.selected_count }}</div>
          <div class="stat-label">Selected Features</div>
        </div>
      </div>

      <!-- Class distribution bar chart -->
      <section class="section" v-if="summary">
        <h3>Class Distribution</h3>
        <div ref="classDistChartEl" class="plotly-chart"></div>
      </section>

      <div v-if="!summary && !loading" class="empty">
        No training data found. Upload datasets in the Data &amp; Run tab first.
      </div>
    </div>

    <!-- ====== FEATURES SUB-TAB ====== -->
    <div v-if="subTab === 'features'" class="sub-content">
      <!-- Filter controls -->
      <div class="filter-bar">
        <label class="filter-item">
          <span>Method</span>
          <select v-model="filterMethod" @change="loadFeatureStats">
            <option value="wilcoxon">Wilcoxon</option>
            <option value="studentt">Student t-test</option>
            <option value="bayesian_fisher">Bayesian Fisher</option>
          </select>
        </label>
        <label class="filter-item">
          <span>Min prevalence (%)</span>
          <input type="number" v-model.number="filterPrevalence" min="0" max="100" step="1" @change="loadFeatureStats" />
        </label>
        <label class="filter-item">
          <span>Max adj. p-value</span>
          <input type="number" v-model.number="filterPvalue" min="0" max="1" step="0.01" @change="loadFeatureStats" />
        </label>
        <label class="filter-item">
          <span>Min feature value</span>
          <input type="number" v-model.number="filterMinValue" min="0" step="0.0001" @change="loadFeatureStats" />
        </label>
      </div>

      <!-- Selected count -->
      <div v-if="featureStats" class="selection-info">
        <strong>{{ featureStats.selected_count }}</strong> / {{ featureStats.n_features }} features selected
        ({{ filterMethod }}, p &lt; {{ filterPvalue }})
      </div>

      <!-- Feature table -->
      <div v-if="featureStats && featureStats.features.length > 0" class="section">
        <table class="feature-table">
          <thead>
            <tr>
              <th class="sortable" @click="sortBy('name')">
                Name {{ sortIcon('name') }}
              </th>
              <th class="sortable" @click="sortBy('class')">
                Class {{ sortIcon('class') }}
              </th>
              <th class="sortable" @click="sortBy('significance')">
                Significance {{ sortIcon('significance') }}
              </th>
              <th class="sortable" @click="sortBy('prevalence_0')">
                Prev(0) % {{ sortIcon('prevalence_0') }}
              </th>
              <th class="sortable" @click="sortBy('prevalence_1')">
                Prev(1) % {{ sortIcon('prevalence_1') }}
              </th>
              <th class="sortable" @click="sortBy('mean_0')">
                Mean(0) {{ sortIcon('mean_0') }}
              </th>
              <th class="sortable" @click="sortBy('mean_1')">
                Mean(1) {{ sortIcon('mean_1') }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="f in paginatedFeatures"
              :key="f.index"
              :class="featureRowClass(f)"
              @click="selectFeature(f)"
            >
              <td class="feature-name-cell">{{ f.name }}</td>
              <td>{{ f.class === 0 ? 'Class 0' : f.class === 1 ? 'Class 1' : '—' }}</td>
              <td>{{ f.significance != null ? f.significance.toExponential(2) : '—' }}</td>
              <td>{{ f.prevalence_0 != null ? f.prevalence_0.toFixed(1) : '—' }}</td>
              <td>{{ f.prevalence_1 != null ? f.prevalence_1.toFixed(1) : '—' }}</td>
              <td>{{ f.mean_0 != null ? f.mean_0.toExponential(2) : '—' }}</td>
              <td>{{ f.mean_1 != null ? f.mean_1.toExponential(2) : '—' }}</td>
            </tr>
          </tbody>
        </table>

        <!-- Pagination -->
        <div class="pagination" v-if="sortedFeatures.length > featPageSize">
          <button @click="featPage = Math.max(0, featPage - 1)" :disabled="featPage === 0">&laquo; Prev</button>
          <span>Page {{ featPage + 1 }} / {{ Math.ceil(sortedFeatures.length / featPageSize) }}</span>
          <button @click="featPage++" :disabled="(featPage + 1) * featPageSize >= sortedFeatures.length">Next &raquo;</button>
        </div>
      </div>

      <!-- Feature abundance boxplot (click a feature) -->
      <section class="section" v-if="selectedFeatures.length > 0">
        <h3>
          Feature Abundance
          <button class="clear-selection-btn" @click="selectedFeatures = []">Clear</button>
        </h3>
        <div ref="abundanceChartEl" class="plotly-chart plotly-chart-tall"></div>
      </section>

      <div v-if="loadingFeatures" class="loading">Loading feature statistics...</div>
    </div>

    <!-- ====== VISUALIZATIONS SUB-TAB ====== -->
    <div v-if="subTab === 'visualizations'" class="sub-content">
      <div v-if="distributions">
        <div class="charts-grid">
          <section class="section">
            <h3>Prevalence Distribution</h3>
            <div ref="prevHistChartEl" class="plotly-chart"></div>
          </section>
          <section class="section">
            <h3>Standard Deviation Distribution</h3>
            <div ref="sdHistChartEl" class="plotly-chart"></div>
          </section>
        </div>

        <section class="section" v-if="featureStats">
          <h3>Volcano Plot</h3>
          <div ref="volcanoChartEl" class="plotly-chart plotly-chart-tall"></div>
        </section>
      </div>

      <div v-if="!distributions && !loading" class="empty">
        No training data found. Upload datasets in the Data &amp; Run tab first.
      </div>
    </div>

    <!-- Global loading -->
    <div v-if="loading && !featureStats" class="loading">Loading data exploration...</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import { useThemeStore } from '../stores/theme'
import axios from 'axios'
import Plotly from 'plotly.js-dist-min'

const route = useRoute()
const store = useProjectStore()
const themeStore = useThemeStore()

// State
const loading = ref(false)
const loadingFeatures = ref(false)
const subTab = ref('summary')
const summary = ref(null)
const featureStats = ref(null)
const distributions = ref(null)
const abundanceData = ref([])

// Filter controls
const filterMethod = ref('wilcoxon')
const filterPrevalence = ref(10)
const filterPvalue = ref(0.05)
const filterMinValue = ref(0)

// Feature table state
const featPage = ref(0)
const featPageSize = 50
const sortField = ref('significance')
const sortDir = ref('asc')
const selectedFeatures = ref([])

// Chart refs
const classDistChartEl = ref(null)
const prevHistChartEl = ref(null)
const sdHistChartEl = ref(null)
const volcanoChartEl = ref(null)
const abundanceChartEl = ref(null)

const projectId = computed(() => route.params.id)

// Sorted features for the table
const sortedFeatures = computed(() => {
  if (!featureStats.value?.features) return []
  const arr = [...featureStats.value.features]
  const field = sortField.value
  const dir = sortDir.value === 'asc' ? 1 : -1

  arr.sort((a, b) => {
    let va = a[field]
    let vb = b[field]
    // Nulls go to end
    if (va == null && vb == null) return 0
    if (va == null) return 1
    if (vb == null) return -1
    if (typeof va === 'string') return va.localeCompare(vb) * dir
    return (va - vb) * dir
  })
  return arr
})

const paginatedFeatures = computed(() => {
  const start = featPage.value * featPageSize
  return sortedFeatures.value.slice(start, start + featPageSize)
})

function sortBy(field) {
  if (sortField.value === field) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortDir.value = 'asc'
  }
  featPage.value = 0
}

function sortIcon(field) {
  if (sortField.value !== field) return ''
  return sortDir.value === 'asc' ? '\u25B2' : '\u25BC'
}

function featureRowClass(f) {
  if (!f.selected) return 'row-dimmed'
  if (f.class === 0) return 'row-class0'
  if (f.class === 1) return 'row-class1'
  return ''
}

function selectFeature(f) {
  const idx = selectedFeatures.value.indexOf(f.name)
  if (idx >= 0) {
    selectedFeatures.value.splice(idx, 1)
  } else if (selectedFeatures.value.length < 10) {
    selectedFeatures.value.push(f.name)
  }
  if (selectedFeatures.value.length > 0) {
    loadAbundance()
  }
}

// --- Theme colors ---
function chartColors() {
  const dark = themeStore.isDark
  return {
    class0: dark ? '#4fc3f7' : '#1565c0',
    class1: dark ? '#81c784' : '#2e7d32',
    accent: dark ? '#ce93d8' : '#7b1fa2',
    grid: dark ? '#3a3a52' : '#e0e0e0',
    text: dark ? '#d0d0dc' : '#2c3e50',
    paper: dark ? '#1e1e2e' : '#ffffff',
    dimmed: dark ? '#555566' : '#b0bec5',
    danger: dark ? '#ef5350' : '#e53935',
  }
}

// --- API calls ---
async function loadSummary() {
  try {
    const { data } = await axios.get(`/api/data-explore/${projectId.value}/summary`)
    summary.value = data
  } catch (e) {
    if (e.response?.status === 404) {
      summary.value = null
    } else {
      console.error('Failed to load summary:', e)
    }
  }
}

async function loadFeatureStats() {
  loadingFeatures.value = true
  featPage.value = 0
  try {
    const { data } = await axios.get(`/api/data-explore/${projectId.value}/feature-stats`, {
      params: {
        method: filterMethod.value,
        prevalence_pct: filterPrevalence.value,
        max_pvalue: filterPvalue.value,
        min_feature_value: filterMinValue.value,
      },
    })
    featureStats.value = data
  } catch (e) {
    console.error('Failed to load feature stats:', e)
  } finally {
    loadingFeatures.value = false
  }
}

async function loadDistributions() {
  try {
    const { data } = await axios.get(`/api/data-explore/${projectId.value}/distributions`)
    distributions.value = data
  } catch (e) {
    console.error('Failed to load distributions:', e)
  }
}

async function loadAbundance() {
  if (selectedFeatures.value.length === 0) return
  try {
    const { data } = await axios.get(`/api/data-explore/${projectId.value}/feature-abundance`, {
      params: { features: selectedFeatures.value.join(',') },
    })
    abundanceData.value = data.features || []
    await nextTick()
    renderAbundanceChart()
  } catch (e) {
    console.error('Failed to load abundance:', e)
  }
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadSummary(), loadFeatureStats(), loadDistributions()])
  } finally {
    loading.value = false
  }
}

// --- Chart renderers ---
function chartLayout(overrides = {}) {
  const c = chartColors()
  return {
    margin: { t: 20, b: 50, l: 60, r: 20 },
    height: 300,
    font: { family: 'system-ui, sans-serif', size: 12, color: c.text },
    paper_bgcolor: c.paper,
    plot_bgcolor: c.paper,
    xaxis: { gridcolor: c.grid, color: c.text, ...overrides.xaxis },
    yaxis: { gridcolor: c.grid, color: c.text, ...overrides.yaxis },
    legend: { font: { color: c.text }, ...overrides.legend },
    ...overrides,
  }
}

async function renderClassDistChart() {
  await nextTick()
  if (!classDistChartEl.value || !summary.value) return
  const c = chartColors()
  const labels = Object.keys(summary.value.class_counts)
  const values = Object.values(summary.value.class_counts)
  const colors = [c.class0, c.class1, c.accent, c.danger].slice(0, labels.length)

  Plotly.newPlot(classDistChartEl.value, [{
    x: labels.map(l => `Class ${l}`),
    y: values,
    type: 'bar',
    marker: { color: colors },
    text: values.map(String),
    textposition: 'auto',
  }], chartLayout({
    xaxis: { title: { text: 'Class', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    yaxis: { title: { text: 'Sample Count', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    height: 280,
  }), { responsive: true, displayModeBar: false })
}

async function renderPrevHistChart() {
  await nextTick()
  if (!prevHistChartEl.value || !distributions.value) return
  const c = chartColors()
  const hist = distributions.value.prevalence_histogram
  const x = hist.bin_edges.slice(0, -1).map((e, i) => (e + hist.bin_edges[i + 1]) / 2)

  Plotly.newPlot(prevHistChartEl.value, [{
    x,
    y: hist.counts,
    type: 'bar',
    marker: { color: c.class0, opacity: 0.8 },
  }], chartLayout({
    xaxis: { title: { text: 'Prevalence (%)', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    yaxis: { title: { text: 'Feature Count', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
  }), { responsive: true, displayModeBar: false })
}

async function renderSdHistChart() {
  await nextTick()
  if (!sdHistChartEl.value || !distributions.value) return
  const c = chartColors()
  const hist = distributions.value.sd_histogram
  const x = hist.bin_edges.slice(0, -1).map((e, i) => (e + hist.bin_edges[i + 1]) / 2)

  Plotly.newPlot(sdHistChartEl.value, [{
    x,
    y: hist.counts,
    type: 'bar',
    marker: { color: c.class1, opacity: 0.8 },
  }], chartLayout({
    xaxis: { title: { text: 'Standard Deviation', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    yaxis: { title: { text: 'Feature Count', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
  }), { responsive: true, displayModeBar: false })
}

async function renderVolcanoChart() {
  await nextTick()
  if (!volcanoChartEl.value || !featureStats.value) return
  const c = chartColors()
  const features = featureStats.value.features

  // Separate by class for coloring
  const class0 = features.filter(f => f.selected && f.class === 0)
  const class1 = features.filter(f => f.selected && f.class === 1)
  const notSig = features.filter(f => !f.selected)

  function meanDiff(f) {
    return (f.mean_1 ?? 0) - (f.mean_0 ?? 0)
  }
  function negLog10(f) {
    if (!f.significance || f.significance <= 0) return 0
    return -Math.log10(f.significance)
  }

  const traces = []

  if (notSig.length > 0) {
    traces.push({
      x: notSig.map(meanDiff),
      y: notSig.map(negLog10),
      text: notSig.map(f => f.name),
      mode: 'markers',
      type: 'scatter',
      name: 'Not significant',
      marker: { color: c.dimmed, size: 4, opacity: 0.5 },
    })
  }
  if (class0.length > 0) {
    traces.push({
      x: class0.map(meanDiff),
      y: class0.map(negLog10),
      text: class0.map(f => f.name),
      mode: 'markers',
      type: 'scatter',
      name: 'Class 0',
      marker: { color: c.class0, size: 6 },
    })
  }
  if (class1.length > 0) {
    traces.push({
      x: class1.map(meanDiff),
      y: class1.map(negLog10),
      text: class1.map(f => f.name),
      mode: 'markers',
      type: 'scatter',
      name: 'Class 1',
      marker: { color: c.class1, size: 6 },
    })
  }

  // Threshold line for p-value
  const pThreshold = -Math.log10(filterPvalue.value)

  Plotly.newPlot(volcanoChartEl.value, traces, chartLayout({
    xaxis: { title: { text: 'Mean Difference (Class 1 - Class 0)', font: { color: c.text } }, gridcolor: c.grid, color: c.text, zeroline: true, zerolinecolor: c.grid },
    yaxis: { title: { text: '-log10(significance)', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    legend: { orientation: 'h', y: 1.12, font: { color: c.text } },
    height: 400,
    shapes: [{
      type: 'line',
      x0: 0, x1: 1, xref: 'paper',
      y0: pThreshold, y1: pThreshold,
      line: { color: c.danger, width: 1, dash: 'dash' },
    }],
  }), { responsive: true, displayModeBar: false })
}

async function renderAbundanceChart() {
  await nextTick()
  if (!abundanceChartEl.value || abundanceData.value.length === 0) return
  const c = chartColors()
  const classColors = { '0': c.class0, '1': c.class1 }

  const traces = []
  for (const item of abundanceData.value) {
    for (const [cls, stats] of Object.entries(item.classes)) {
      // Build a box trace from precomputed stats
      traces.push({
        type: 'box',
        name: `${item.name} (Class ${cls})`,
        x: [`${item.name}`],
        q1: [stats.q1],
        median: [stats.median],
        q3: [stats.q3],
        lowerfence: [stats.min],
        upperfence: [stats.max],
        mean: [stats.mean],
        marker: { color: classColors[cls] || c.accent },
        line: { color: classColors[cls] || c.accent },
      })
    }
  }

  Plotly.newPlot(abundanceChartEl.value, traces, chartLayout({
    xaxis: { title: { text: 'Feature', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    yaxis: { title: { text: 'Abundance', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    height: 350,
    boxmode: 'group',
    showlegend: false,
  }), { responsive: true, displayModeBar: false })
}

// Re-render charts when sub-tab changes, data loads, or theme toggles
watch([subTab, summary, () => themeStore.isDark], () => {
  if (subTab.value === 'summary' && summary.value) {
    renderClassDistChart()
  }
})

watch([subTab, distributions, () => themeStore.isDark], () => {
  if (subTab.value === 'visualizations' && distributions.value) {
    renderPrevHistChart()
    renderSdHistChart()
    if (featureStats.value) renderVolcanoChart()
  }
})

watch([subTab, featureStats, () => themeStore.isDark], () => {
  if (subTab.value === 'visualizations' && featureStats.value) {
    renderVolcanoChart()
  }
})

watch(selectedFeatures, () => {
  if (selectedFeatures.value.length > 0) loadAbundance()
}, { deep: true })

onMounted(loadAll)
</script>

<style scoped>
.sub-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid var(--border-light);
}

.sub-tabs button {
  padding: 0.5rem 1.25rem;
  border: none;
  background: none;
  color: var(--text-muted);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}

.sub-tabs button.active {
  color: var(--text-primary);
  border-bottom-color: var(--accent);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stat-card {
  background: var(--bg-card);
  padding: 1.25rem;
  border-radius: 8px;
  box-shadow: var(--shadow);
  text-align: center;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-value.accent {
  color: var(--accent);
}

.stat-label {
  font-size: 0.8rem;
  color: var(--text-faint);
  margin-top: 0.25rem;
}

.section {
  background: var(--bg-card);
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: var(--shadow);
  margin-bottom: 1.5rem;
}

.section h3 {
  margin-bottom: 1rem;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.plotly-chart {
  width: 100%;
  min-height: 280px;
}

.plotly-chart-tall {
  min-height: 350px;
}

.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

@media (max-width: 900px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
}

/* Filter bar */
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 1rem;
  padding: 1rem 1.25rem;
  background: var(--bg-card);
  border-radius: 8px;
  box-shadow: var(--shadow);
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.filter-item select,
.filter-item input {
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
  min-width: 120px;
}

.selection-info {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 1rem;
  padding: 0.5rem 0;
}

.selection-info strong {
  color: var(--accent);
}

/* Feature table */
.feature-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}

.feature-table th {
  text-align: left;
  padding: 0.5rem 0.4rem;
  border-bottom: 2px solid var(--border-light);
  color: var(--text-secondary);
  font-weight: 600;
  white-space: nowrap;
}

.feature-table th.sortable {
  cursor: pointer;
  user-select: none;
}

.feature-table th.sortable:hover {
  color: var(--text-primary);
}

.feature-table td {
  padding: 0.4rem;
  border-bottom: 1px solid var(--border-lighter);
  color: var(--text-body);
}

.feature-table tr {
  cursor: pointer;
  transition: background 0.15s;
}

.feature-table tbody tr:hover {
  background: var(--bg-card-hover);
}

.feature-name-cell {
  font-weight: 500;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Row colors by class */
.row-class0 {
  border-left: 3px solid #1565c0;
}
:root.dark .row-class0 {
  border-left-color: #4fc3f7;
}

.row-class1 {
  border-left: 3px solid #2e7d32;
}
:root.dark .row-class1 {
  border-left-color: #81c784;
}

.row-dimmed {
  opacity: 0.5;
}

/* Pagination */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-top: 1rem;
  font-size: 0.85rem;
}

.pagination button {
  padding: 0.3rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-card);
  color: var(--text-body);
  cursor: pointer;
}

.pagination button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.clear-selection-btn {
  padding: 0.2rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.75rem;
  cursor: pointer;
}

.clear-selection-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.empty {
  text-align: center;
  padding: 3rem;
  color: var(--text-faint);
}

.loading {
  text-align: center;
  padding: 2rem;
  color: var(--text-faint);
}
</style>
