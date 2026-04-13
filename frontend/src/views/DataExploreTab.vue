<template>
  <div class="data-explore-tab">
    <!-- Sub-tabs -->
    <nav class="sub-tabs">
      <button :class="{ active: subTab === 'summary' }" @click="subTab = 'summary'">{{ $t('dataExplore.summary') }}</button>
      <button :class="{ active: subTab === 'features' }" @click="subTab = 'features'">{{ $t('dataExplore.features') }}</button>
      <button :class="{ active: subTab === 'visualizations' }" @click="subTab = 'visualizations'">{{ $t('dataExplore.visualizations') }}</button>
      <button :class="{ active: subTab === 'pcoa' }" @click="subTab = 'pcoa'">{{ $t('dataExplore.pcoa') }}</button>
      <button :class="{ active: subTab === 'aberrant' }" @click="subTab = 'aberrant'">{{ $t('dataExplore.aberrantCorrelations') }}</button>
    </nav>

    <!-- ====== SUMMARY SUB-TAB ====== -->
    <div v-if="subTab === 'summary'" class="sub-content">
      <div v-if="summary" class="summary-grid">
        <div class="stat-card">
          <div class="stat-value">{{ summary.n_features }}</div>
          <div class="stat-label">{{ $t('dataExplore.totalFeatures') }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summary.n_samples }}</div>
          <div class="stat-label">{{ $t('dataExplore.samples') }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summary.n_classes }}</div>
          <div class="stat-label">{{ $t('dataExplore.classes') }}</div>
        </div>
        <div class="stat-card" v-if="featureStats">
          <div class="stat-value accent">{{ featureStats.selected_count }}</div>
          <div class="stat-label">{{ $t('dataExplore.selectedFeatures') }}</div>
        </div>
      </div>

      <!-- Class distribution bar chart -->
      <section class="section" v-if="summary">
        <h3>{{ $t('dataExplore.classDistribution') }}</h3>
        <div ref="classDistChartEl" class="plotly-chart"></div>
      </section>

      <div v-if="!summary && !loading" class="empty">
        {{ $t('dataExplore.noTrainingData') }}
      </div>
    </div>

    <!-- ====== FEATURES SUB-TAB ====== -->
    <div v-if="subTab === 'features'" class="sub-content">
      <!-- Filter controls -->
      <div class="filter-bar">
        <label class="filter-item">
          <span>{{ $t('dataExplore.method') }}</span>
          <select v-model="filterMethod" @change="loadFeatureStats">
            <option value="wilcoxon">{{ $t('dataExplore.wilcoxon') }}</option>
            <option value="studentt">{{ $t('dataExplore.studentTTest') }}</option>
            <option value="bayesian_fisher">{{ $t('dataExplore.bayesianFisher') }}</option>
          </select>
        </label>
        <label class="filter-item">
          <span>{{ $t('dataExplore.minPrevalence') }}</span>
          <input type="number" v-model.number="filterPrevalence" min="0" max="100" step="1" @change="loadFeatureStats" />
        </label>
        <label class="filter-item">
          <span>{{ $t('dataExplore.maxPValue') }}</span>
          <input type="number" v-model.number="filterPvalue" min="0" max="1" step="0.01" @change="loadFeatureStats" />
        </label>
        <label class="filter-item">
          <span>{{ $t('dataExplore.minFeatureValue') }}</span>
          <input type="number" v-model.number="filterMinValue" min="0" step="0.0001" @change="loadFeatureStats" />
        </label>
      </div>

      <!-- Selected count -->
      <div v-if="featureStats" class="selection-info">
        <strong>{{ featureStats.selected_count }}</strong> / {{ featureStats.n_features }} {{ $t('dataExplore.featuresSelected') }}
        ({{ filterMethod }}, p &lt; {{ filterPvalue }})
      </div>

      <!-- Feature table -->
      <div v-if="featureStats && featureStats.features.length > 0" class="section">
        <table class="feature-table">
          <thead>
            <tr>
              <th class="sortable" @click="sortBy('name')">
                {{ $t('dataExplore.name') }} {{ sortIcon('name') }}
              </th>
              <th class="sortable" @click="sortBy('class')">
                {{ $t('dataExplore.class') }} {{ sortIcon('class') }}
              </th>
              <th class="sortable" @click="sortBy('significance')">
                {{ $t('dataExplore.significance') }} {{ sortIcon('significance') }}
              </th>
              <th class="sortable" @click="sortBy('prevalence_0')">
                {{ $t('dataExplore.prev0') }} {{ sortIcon('prevalence_0') }}
              </th>
              <th class="sortable" @click="sortBy('prevalence_1')">
                {{ $t('dataExplore.prev1') }} {{ sortIcon('prevalence_1') }}
              </th>
              <th class="sortable" @click="sortBy('mean_0')">
                {{ $t('dataExplore.mean0') }} {{ sortIcon('mean_0') }}
              </th>
              <th class="sortable" @click="sortBy('mean_1')">
                {{ $t('dataExplore.mean1') }} {{ sortIcon('mean_1') }}
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
              <td>{{ f.class === 0 ? $t('dataExplore.class') + ' 0' : f.class === 1 ? $t('dataExplore.class') + ' 1' : '—' }}</td>
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
          <button @click="featPage = Math.max(0, featPage - 1)" :disabled="featPage === 0">&laquo; {{ $t('dataExplore.prev') }}</button>
          <span>{{ $t('dataExplore.page') }} {{ featPage + 1 }} / {{ Math.ceil(sortedFeatures.length / featPageSize) }}</span>
          <button @click="featPage++" :disabled="(featPage + 1) * featPageSize >= sortedFeatures.length">{{ $t('dataExplore.next') }} &raquo;</button>
        </div>
      </div>

      <!-- Feature abundance boxplot (click a feature) -->
      <section class="section" v-if="selectedFeatures.length > 0">
        <h3>
          {{ $t('dataExplore.featureAbundance') }}
          <button class="clear-selection-btn" @click="selectedFeatures = []">{{ $t('dataExplore.clear') }}</button>
        </h3>
        <div class="abundance-controls">
          <label class="filter-item">
            <span>{{ $t('dataExplore.transform') }}</span>
            <select v-model="dataTransform" @change="loadAbundance">
              <option value="raw">Raw</option>
              <option value="log">Log</option>
              <option value="zscore">Z-score</option>
            </select>
          </label>
        </div>
        <div ref="abundanceChartEl" class="plotly-chart plotly-chart-tall"></div>
      </section>

      <div v-if="loadingFeatures" class="loading">{{ $t('dataExplore.loadingStats') }}</div>
    </div>

    <!-- ====== VISUALIZATIONS SUB-TAB ====== -->
    <div v-if="subTab === 'visualizations'" class="sub-content">
      <div v-if="distributions">
        <div class="charts-grid">
          <section class="section">
            <h3>{{ $t('dataExplore.prevalenceDistribution') }}</h3>
            <div ref="prevHistChartEl" class="plotly-chart"></div>
          </section>
          <section class="section">
            <h3>{{ $t('dataExplore.stdDevDistribution') }}</h3>
            <div ref="sdHistChartEl" class="plotly-chart"></div>
          </section>
        </div>

        <section class="section" v-if="featureStats">
          <h3>{{ $t('dataExplore.volcanoPlot') }}</h3>
          <div ref="volcanoChartEl" class="plotly-chart plotly-chart-tall"></div>
        </section>
      </div>

      <div v-if="!distributions && !loading" class="empty">
        {{ $t('dataExplore.noTrainingData') }}
      </div>
    </div>

    <!-- ====== PCoA SUB-TAB ====== -->
    <div v-if="subTab === 'pcoa'" class="sub-content">
      <div class="pcoa-controls">
        <label class="filter-item">
          <span>{{ $t('dataExplore.ordinationMethod') }}</span>
          <select v-model="pcoaMethod" @change="loadPcoa">
            <option value="pcoa">PCoA</option>
            <option value="tsne">t-SNE</option>
            <option value="umap">UMAP</option>
          </select>
        </label>
        <label class="filter-item">
          <span>{{ $t('dataExplore.pcoaMetric') }}</span>
          <select v-model="pcoaMetric" @change="loadPcoa">
            <option value="braycurtis">Bray-Curtis</option>
            <option value="euclidean">{{ $t('dataExplore.euclidean') }}</option>
            <option value="jaccard">Jaccard</option>
            <option value="cosine">{{ $t('dataExplore.cosine') }}</option>
          </select>
        </label>
        <label class="filter-item">
          <span>{{ $t('dataExplore.transform') }}</span>
          <select v-model="dataTransform" @change="loadPcoa">
            <option value="raw">Raw</option>
            <option value="log">Log</option>
            <option value="zscore">Z-score</option>
          </select>
        </label>
        <label v-if="pcoaMethod === 'tsne'" class="filter-item">
          <span>{{ $t('dataExplore.perplexity') }}</span>
          <input type="number" v-model.number="tsnePerplexity" min="5" max="100" step="5" @change="loadPcoa" class="param-input" />
        </label>
        <label v-if="pcoaMethod === 'umap'" class="filter-item">
          <span>{{ $t('dataExplore.nNeighbors') }}</span>
          <input type="number" v-model.number="umapNeighbors" min="2" max="100" step="1" @change="loadPcoa" class="param-input" />
        </label>
        <label v-if="pcoaMethod === 'umap'" class="filter-item">
          <span>{{ $t('dataExplore.minDist') }}</span>
          <input type="number" v-model.number="umapMinDist" min="0" max="1" step="0.05" @change="loadPcoa" class="param-input" />
        </label>
        <label class="filter-item pcoa-dim-toggle">
          <span>{{ $t('dataExplore.pcoaDimensions') }}</span>
          <div class="dim-buttons">
            <button :class="{ active: pcoaDim === '2d' }" @click="pcoaDim = '2d'">2D</button>
            <button :class="{ active: pcoaDim === '3d' }" @click="pcoaDim = '3d'">3D</button>
          </div>
        </label>
      </div>

      <section class="section" v-if="pcoaData">
        <h3>{{ $t('dataExplore.pcoaTitle') }}</h3>
        <p class="pcoa-info">
          {{ pcoaData.n_samples }} {{ $t('dataExplore.samples').toLowerCase() }}
          &middot; {{ $t('dataExplore.pcoaMetric') }}: {{ pcoaData.metric }}
        </p>
        <div ref="pcoaChartEl" class="plotly-chart plotly-chart-pcoa"></div>
      </section>

      <div v-if="loadingPcoa" class="loading">{{ $t('dataExplore.loadingPcoa') }}</div>
      <div v-if="!pcoaData && !loadingPcoa && !loading" class="empty">
        {{ $t('dataExplore.noTrainingData') }}
      </div>
    </div>

    <!-- ====== ABERRANT CORRELATIONS SUB-TAB ====== -->
    <div v-if="subTab === 'aberrant'" class="sub-content">
      <section class="section">
        <h3>{{ $t('dataExplore.aberrantCorrelations') }}</h3>
        <p class="aberrant-desc">{{ $t('dataExplore.aberrantDesc') }}</p>
        <div class="aberrant-controls">
          <label class="filter-item">
            <span>{{ $t('dataExplore.minPrevalence') }}</span>
            <input type="number" v-model.number="aberrantPrevalence" min="0" max="100" step="5" class="param-input" />
          </label>
          <button class="aberrant-compute-btn" @click="loadAberrantCorrelations" :disabled="loadingAberrant">
            {{ loadingAberrant ? $t('common.loading') : $t('dataExplore.loadAberrant') }}
          </button>
        </div>
      </section>

      <section class="section" v-if="aberrantData && aberrantData.pairs.length > 0">
        <p class="aberrant-info">
          {{ aberrantData.n_features }} {{ $t('dataExplore.features').toLowerCase() }}
          &middot; {{ aberrantData.n_pairs }} {{ $t('dataExplore.featuresSelected').split(' ')[0] === 'features' ? 'pairs' : 'paires' }}
        </p>
        <div ref="aberrantChartEl" class="plotly-chart plotly-chart-tall"></div>
      </section>

      <div v-if="aberrantData && aberrantData.pairs.length === 0 && !loadingAberrant" class="empty">
        {{ $t('common.noData') }}
      </div>
      <div v-if="loadingAberrant" class="loading">{{ $t('common.loading') }}</div>
    </div>

    <!-- Global loading -->
    <div v-if="loading && !featureStats" class="loading">{{ $t('dataExplore.loadingExplore') }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import { useThemeStore } from '../stores/theme'
import axios from 'axios'
import Plotly from 'plotly.js-dist-min'
import { useI18n } from 'vue-i18n'

const route = useRoute()
const store = useProjectStore()
const themeStore = useThemeStore()
const { t } = useI18n()

// State
const loading = ref(false)
const loadingFeatures = ref(false)
const subTab = ref('summary')
const summary = ref(null)
const featureStats = ref(null)
const distributions = ref(null)
const abundanceData = ref([])
const pcoaData = ref(null)
const loadingPcoa = ref(false)
const pcoaMethod = ref('pcoa')
const pcoaMetric = ref('braycurtis')
const dataTransform = ref('raw')
const pcoaDim = ref('2d')
const tsnePerplexity = ref(30)
const umapNeighbors = ref(15)
const umapMinDist = ref(0.1)
const aberrantData = ref(null)
const loadingAberrant = ref(false)
const aberrantPrevalence = ref(30)

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
const pcoaChartEl = ref(null)
const aberrantChartEl = ref(null)

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
      params: { features: selectedFeatures.value.join(','), transform: dataTransform.value },
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

// --- PCoA / t-SNE / UMAP ---
async function loadPcoa() {
  loadingPcoa.value = true
  try {
    const params = { method: pcoaMethod.value, metric: pcoaMetric.value, transform: dataTransform.value }
    if (pcoaMethod.value === 'tsne') {
      params.perplexity = tsnePerplexity.value
    } else if (pcoaMethod.value === 'umap') {
      params.n_neighbors = umapNeighbors.value
      params.min_dist = umapMinDist.value
    }
    if (pcoaDim.value === '3d') params.n_components = 3
    const { data } = await axios.get(`/api/data-explore/${projectId.value}/ordination`, { params })
    pcoaData.value = data
    await nextTick()
    renderPcoaChart()
  } catch (e) {
    if (e.response?.status === 404) {
      pcoaData.value = null
    } else {
      console.error('Failed to load ordination:', e)
    }
  } finally {
    loadingPcoa.value = false
  }
}

// --- Aberrant correlations ---
async function loadAberrantCorrelations() {
  loadingAberrant.value = true
  try {
    const { data } = await axios.get(`/api/data-explore/${projectId.value}/aberrant-correlations`, {
      params: { min_prevalence_pct: aberrantPrevalence.value },
    })
    aberrantData.value = data
    await nextTick()
    renderAberrantChart()
  } catch (e) {
    console.error('Failed to load aberrant correlations:', e)
  } finally {
    loadingAberrant.value = false
  }
}

async function renderAberrantChart() {
  await nextTick()
  if (!aberrantChartEl.value || !aberrantData.value || aberrantData.value.pairs.length === 0) return
  const c = chartColors()
  const pairs = aberrantData.value.pairs

  // Compute deviation from diagonal for coloring
  const r0 = pairs.map(p => p.r0)
  const r1 = pairs.map(p => p.r1)
  const deviations = pairs.map(p => Math.abs(p.r0 - p.r1))
  const hoverText = pairs.map(p => `${p.f1} — ${p.f2}<br>Class 0: ${p.r0}<br>Class 1: ${p.r1}<br>|dev|: ${Math.abs(p.r0 - p.r1).toFixed(4)}`)

  const traces = [
    // Scatter points colored by deviation
    {
      x: r0,
      y: r1,
      text: hoverText,
      mode: 'markers',
      type: 'scatter',
      name: 'Feature pairs',
      marker: {
        color: deviations,
        colorscale: [[0, c.class0], [0.5, c.accent], [1, c.danger]],
        size: 4,
        opacity: 0.6,
        colorbar: { title: '|dev|', len: 0.5, thickness: 12, tickfont: { color: c.text } },
      },
      hovertemplate: '%{text}<extra></extra>',
    },
    // Diagonal line y=x
    {
      x: [-1, 1],
      y: [-1, 1],
      mode: 'lines',
      type: 'scatter',
      name: 'y = x',
      line: { color: c.dimmed, width: 1.5, dash: 'dash' },
      showlegend: true,
      hoverinfo: 'skip',
    },
  ]

  Plotly.newPlot(aberrantChartEl.value, traces, chartLayout({
    xaxis: {
      title: { text: t('dataExplore.class0Corr'), font: { color: c.text } },
      gridcolor: c.grid, color: c.text, range: [-1.05, 1.05],
      zeroline: true, zerolinecolor: c.grid,
    },
    yaxis: {
      title: { text: t('dataExplore.class1Corr'), font: { color: c.text } },
      gridcolor: c.grid, color: c.text, range: [-1.05, 1.05],
      zeroline: true, zerolinecolor: c.grid,
      scaleanchor: 'x', scaleratio: 1,
    },
    legend: { orientation: 'h', y: 1.12, font: { color: c.text } },
    height: 500,
  }), { responsive: true, displayModeBar: false })
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
  const colors = [c.class0Alpha, c.class1Alpha, c.accentAlpha, c.class1Alpha].slice(0, labels.length)
  const borderColors = [c.class0, c.class1, c.accent, c.class1].slice(0, labels.length)

  Plotly.newPlot(classDistChartEl.value, [{
    x: labels.map(l => `Class ${l}`),
    y: values,
    type: 'bar',
    marker: { color: colors, line: { color: borderColors, width: 1.5 } },
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

async function renderPcoaChart() {
  await nextTick()
  if (!pcoaChartEl.value || !pcoaData.value) return
  const c = chartColors()
  const d = pcoaData.value
  const ve = d.variance_explained
  const method = d.method || pcoaMethod.value

  const axisLabel = (dim) => {
    if (method === 'pcoa' && ve) return `PCo${dim} (${ve[dim - 1]}%)`
    if (method === 'tsne') return `t-SNE ${dim}`
    if (method === 'umap') return `UMAP ${dim}`
    return `Dim ${dim}`
  }
  const hoverPrefix = method === 'pcoa' ? 'PCo' : method === 'tsne' ? 't-SNE ' : method === 'umap' ? 'UMAP ' : 'Dim '

  const classColorMap = {}
  const palette = [c.class0, c.class1, c.accent, c.danger]
  d.class_labels.forEach((lbl, i) => { classColorMap[lbl] = palette[i % palette.length] })

  if (pcoaDim.value === '3d') {
    const traces = d.class_labels.map(cls => {
      const mask = d.sample_classes.map((sc, i) => String(sc) === cls ? i : -1).filter(i => i >= 0)
      return {
        x: mask.map(i => d.coords[i][0]),
        y: mask.map(i => d.coords[i][1]),
        z: mask.map(i => d.coords[i][2]),
        text: mask.map(i => d.sample_names[i]),
        mode: 'markers',
        type: 'scatter3d',
        name: `${t('dataExplore.class')} ${cls}`,
        marker: { color: classColorMap[cls], size: 4, opacity: 0.85 },
        hovertemplate: `%{text}<br>${hoverPrefix}1: %{x:.3f}<br>${hoverPrefix}2: %{y:.3f}<br>${hoverPrefix}3: %{z:.3f}<extra></extra>`,
      }
    })

    Plotly.newPlot(pcoaChartEl.value, traces, {
      ...chartLayout({ height: 550 }),
      scene: {
        xaxis: { title: { text: axisLabel(1), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
        yaxis: { title: { text: axisLabel(2), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
        zaxis: { title: { text: axisLabel(3), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
        bgcolor: c.paper,
      },
      legend: { orientation: 'h', y: -0.05, font: { color: c.text } },
    }, { responsive: true, displayModeBar: true })
  } else {
    const traces = d.class_labels.map(cls => {
      const mask = d.sample_classes.map((sc, i) => String(sc) === cls ? i : -1).filter(i => i >= 0)
      return {
        x: mask.map(i => d.coords[i][0]),
        y: mask.map(i => d.coords[i][1]),
        text: mask.map(i => d.sample_names[i]),
        mode: 'markers',
        type: 'scatter',
        name: `${t('dataExplore.class')} ${cls}`,
        marker: { color: classColorMap[cls], size: 7, opacity: 0.8, line: { color: classColorMap[cls], width: 0.5 } },
        hovertemplate: `%{text}<br>${hoverPrefix}1: %{x:.3f}<br>${hoverPrefix}2: %{y:.3f}<extra></extra>`,
      }
    })

    Plotly.newPlot(pcoaChartEl.value, traces, chartLayout({
      xaxis: { title: { text: axisLabel(1), font: { color: c.text } }, gridcolor: c.grid, color: c.text, zeroline: true, zerolinecolor: c.grid },
      yaxis: { title: { text: axisLabel(2), font: { color: c.text } }, gridcolor: c.grid, color: c.text, zeroline: true, zerolinecolor: c.grid },
      legend: { orientation: 'h', y: 1.12, font: { color: c.text } },
      height: 500,
    }), { responsive: true, displayModeBar: false })
  }
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

// Load PCoA when tab activated (lazy load)
watch([subTab, () => themeStore.isDark], () => {
  if (subTab.value === 'pcoa') {
    if (!pcoaData.value && !loadingPcoa.value) {
      loadPcoa()
    } else if (pcoaData.value) {
      renderPcoaChart()
    }
  }
})

// Re-render when switching 2D/3D
watch(pcoaDim, () => {
  if (pcoaData.value) renderPcoaChart()
})

// Load aberrant correlations when tab activated (lazy load) + re-render on theme change
watch([subTab, () => themeStore.isDark], () => {
  if (subTab.value === 'aberrant') {
    if (aberrantData.value) {
      renderAberrantChart()
    }
  }
})

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

/* PCoA */
.pcoa-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  align-items: flex-end;
  margin-bottom: 1rem;
  padding: 1rem 1.25rem;
  background: var(--bg-card);
  border-radius: 8px;
  box-shadow: var(--shadow);
}

.pcoa-dim-toggle .dim-buttons {
  display: flex;
  gap: 0;
}

.pcoa-dim-toggle .dim-buttons button {
  padding: 0.35rem 0.75rem;
  border: 1px solid var(--border);
  background: var(--bg-input);
  color: var(--text-body);
  font-size: 0.85rem;
  cursor: pointer;
}

.pcoa-dim-toggle .dim-buttons button:first-child {
  border-radius: 4px 0 0 4px;
}

.pcoa-dim-toggle .dim-buttons button:last-child {
  border-radius: 0 4px 4px 0;
  border-left: none;
}

.pcoa-dim-toggle .dim-buttons button.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.pcoa-info {
  font-size: 0.82rem;
  color: var(--text-faint);
  margin-bottom: 0.75rem;
}

.plotly-chart-pcoa {
  min-height: 500px;
}

/* Aberrant correlations */
.aberrant-desc {
  font-size: 0.85rem;
  color: var(--text-faint);
  margin-bottom: 1rem;
}

.aberrant-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: flex-end;
}

.aberrant-compute-btn {
  padding: 0.4rem 1rem;
  border: 1px solid var(--accent);
  border-radius: 4px;
  background: var(--accent);
  color: #fff;
  font-size: 0.85rem;
  cursor: pointer;
  transition: opacity 0.15s;
}

.aberrant-compute-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.aberrant-compute-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.aberrant-info {
  font-size: 0.82rem;
  color: var(--text-faint);
  margin-bottom: 0.75rem;
}

.param-input {
  min-width: 80px;
}
</style>
