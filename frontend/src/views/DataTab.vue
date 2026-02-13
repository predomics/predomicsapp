<template>
  <div class="data-tab">
    <!-- Summary stats bar -->
    <div class="summary-bar" v-if="summary">
      <div class="stat-card">
        <div class="stat-value">{{ summary.n_features }}</div>
        <div class="stat-label">Features</div>
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
        <div class="stat-label">Selected</div>
      </div>
    </div>

    <!-- Two-panel layout -->
    <div class="data-panels">
      <!-- LEFT PANEL -->
      <aside class="left-panel">
        <!-- Dataset slots (2x2) -->
        <section class="section">
          <div class="section-title">Datasets</div>
          <div class="ds-grid">
            <div v-for="slot in dsSlots" :key="slot.role" class="ds-slot" :class="{ ok: slot.ds, missing: !slot.ds && slot.required, optional: !slot.required && !slot.ds }">
              <span class="ds-role">{{ slot.label }}</span>
              <span v-if="slot.ds" class="ds-file">{{ slot.ds.filename }}
                <button class="ds-clear" @click="clearSlot(slot.role)" title="Remove">&times;</button>
              </span>
              <template v-else>
                <select v-if="libraryDatasets.length > 0" class="ds-picker" @change="e => pickFromLibrary(e, slot.role)">
                  <option value="">Pick from library...</option>
                  <option v-for="d in libraryDatasets" :key="d.id" :value="d.id">{{ d.name }}</option>
                </select>
                <label :class="['ds-upload', { 'ds-optional': !slot.required }]">Upload<input type="file" accept=".tsv,.csv,.txt" @change="e => uploadFile(e, slot.role)" /></label>
              </template>
            </div>
          </div>
        </section>

        <!-- Data options -->
        <section class="section">
          <div class="section-title">Data Options</div>
          <label class="inline-check">
            <input type="checkbox" v-model="cfg.data.features_in_rows" />
            Features in rows
          </label>
          <div class="form-row">
            <label>Holdout ratio
              <input type="number" v-model.number="cfg.data.holdout_ratio" min="0" max="1" step="0.05" />
            </label>
          </div>
        </section>

        <!-- Feature filtering -->
        <section class="section">
          <div class="section-title">Feature Filtering</div>
          <div class="form-col">
            <label>Selection method
              <select v-model="cfg.data.feature_selection_method" @change="debouncedRefresh">
                <option value="wilcoxon">Wilcoxon</option>
                <option value="studentt">t-test</option>
                <option value="bayesian_fisher">Bayesian Fisher</option>
                <option value="none">None</option>
              </select>
            </label>
            <label>Min prevalence %
              <input type="number" v-model.number="cfg.data.feature_minimal_prevalence_pct" min="0" max="100" @change="debouncedRefresh" />
            </label>
            <label>Max adj. p-value
              <input type="number" v-model.number="cfg.data.feature_maximal_adj_pvalue" min="0" max="1" step="0.01" @change="debouncedRefresh" />
            </label>
            <label>Min feature value
              <input type="number" v-model.number="cfg.data.feature_minimal_feature_value" min="0" step="0.0001" @change="debouncedRefresh" />
            </label>
          </div>
        </section>

        <!-- Feature table -->
        <section class="section" v-if="featureStats && featureStats.features.length > 0">
          <div class="section-title">
            Features
            <span class="badge">{{ featureStats.selected_count }}/{{ featureStats.n_features }}</span>
          </div>
          <div class="feature-table-scroll">
            <table class="feature-table">
              <thead>
                <tr>
                  <th class="sortable" @click="sortBy('name')">Name {{ sortIcon('name') }}</th>
                  <th class="sortable" @click="sortBy('significance')">Signif. {{ sortIcon('significance') }}</th>
                  <th class="sortable" @click="sortBy('prevalence')">Prev % {{ sortIcon('prevalence') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="f in paginatedFeatures"
                  :key="f.index"
                  :class="[featureRowClass(f), { 'selected-row': selectedFeatures.includes(f.name) }]"
                  @click="toggleFeature(f)"
                >
                  <td class="feature-name-cell">{{ f.name }}</td>
                  <td>{{ f.significance != null ? f.significance.toExponential(2) : '—' }}</td>
                  <td>{{ f.prevalence != null ? f.prevalence.toFixed(1) : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="pagination" v-if="sortedFeatures.length > featPageSize">
            <button @click="featPage = Math.max(0, featPage - 1)" :disabled="featPage === 0">&laquo;</button>
            <span>{{ featPage + 1 }}/{{ Math.ceil(sortedFeatures.length / featPageSize) }}</span>
            <button @click="featPage++" :disabled="(featPage + 1) * featPageSize >= sortedFeatures.length">&raquo;</button>
          </div>
        </section>
      </aside>

      <!-- RIGHT PANEL -->
      <main class="right-panel">
        <nav class="viz-tabs">
          <button :class="{ active: vizTab === 'prevalence' }" @click="vizTab = 'prevalence'">Prevalence</button>
          <button :class="{ active: vizTab === 'abundance' }" @click="vizTab = 'abundance'">Abundance</button>
          <button :class="{ active: vizTab === 'barcode' }" @click="vizTab = 'barcode'">Barcode</button>
          <button :class="{ active: vizTab === 'volcano' }" @click="vizTab = 'volcano'">Volcano</button>
        </nav>

        <!-- Prevalence plot -->
        <section class="section viz-section" v-if="vizTab === 'prevalence'">
          <div ref="prevalenceChartEl" class="plotly-chart plotly-chart-tall"></div>
          <p v-if="!featureStats" class="info-text">Upload datasets and run filtering to see prevalence.</p>
        </section>

        <!-- Abundance by class -->
        <section class="section viz-section" v-if="vizTab === 'abundance'">
          <p v-if="selectedFeatures.length === 0" class="info-text">Click features in the table to show abundance by class.</p>
          <div ref="abundanceChartEl" class="plotly-chart plotly-chart-tall" v-if="selectedFeatures.length > 0"></div>
        </section>

        <!-- Barcode heatmap -->
        <section class="section viz-section" v-if="vizTab === 'barcode'">
          <p v-if="selectedFeatures.length === 0 && !autoBarcode" class="info-text">Click features in the table, or top significant features will be shown automatically.</p>
          <div ref="barcodeChartEl" class="plotly-chart plotly-chart-tall"></div>
        </section>

        <!-- Volcano plot -->
        <section class="section viz-section" v-if="vizTab === 'volcano'">
          <div ref="volcanoChartEl" class="plotly-chart plotly-chart-tall"></div>
          <p v-if="!featureStats" class="info-text">Upload datasets and run filtering to see the volcano plot.</p>
        </section>
      </main>
    </div>

    <div v-if="loading" class="loading">Loading data...</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import { useDatasetStore } from '../stores/dataset'
import { useConfigStore } from '../stores/config'
import { useThemeStore } from '../stores/theme'
import axios from 'axios'
import Plotly from 'plotly.js-dist-min'

const route = useRoute()
const store = useProjectStore()
const dsStore = useDatasetStore()
const configStore = useConfigStore()
const themeStore = useThemeStore()
const cfg = configStore.form

// State
const loading = ref(false)
const summary = ref(null)
const featureStats = ref(null)
const abundanceData = ref([])
const barcodeData = ref(null)
const autoBarcode = ref(false)
const vizTab = ref('prevalence')

// Feature table
const featPage = ref(0)
const featPageSize = 50
const sortField = ref('significance')
const sortDir = ref('asc')
const selectedFeatures = ref([])

// Chart refs
const prevalenceChartEl = ref(null)
const abundanceChartEl = ref(null)
const barcodeChartEl = ref(null)
const volcanoChartEl = ref(null)

const projectId = computed(() => route.params.id)

// --- Dataset slot logic (from SettingsTab) ---
const datasets = computed(() => store.current?.datasets || [])
const libraryDatasets = computed(() => dsStore.datasets)
const allFiles = computed(() =>
  datasets.value.flatMap(ds => (ds.files || []).map(f => ({ ...f, datasetId: ds.id, datasetName: ds.name })))
)
function findFile(role) { return allFiles.value.find(f => f.role === role) || null }
const xTrainDs = computed(() => findFile('xtrain'))
const yTrainDs = computed(() => findFile('ytrain'))
const xTestDs = computed(() => findFile('xtest'))
const yTestDs = computed(() => findFile('ytest'))
const dsSlots = computed(() => [
  { role: 'xtrain', label: 'X train', ds: xTrainDs.value, required: true },
  { role: 'ytrain', label: 'y train', ds: yTrainDs.value, required: true },
  { role: 'xtest', label: 'X test', ds: xTestDs.value, required: false },
  { role: 'ytest', label: 'y test', ds: yTestDs.value, required: false },
])
const hasTrainData = computed(() => xTrainDs.value && yTrainDs.value)

onMounted(() => dsStore.fetchDatasets())

async function uploadFile(event, role) {
  const file = event.target.files[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    await axios.post(`/api/projects/${projectId.value}/datasets`, formData)
    await store.fetchOne(projectId.value)
    await dsStore.fetchDatasets()
    loadAll()
  } catch (e) {
    alert('Upload failed: ' + (e.response?.data?.detail || e.message))
  }
}

async function pickFromLibrary(event, role) {
  const dsId = event.target.value
  if (!dsId) return
  try {
    await dsStore.assignDataset(dsId, projectId.value)
    await store.fetchOne(projectId.value)
    loadAll()
  } catch (e) {
    alert('Assign failed: ' + (e.response?.data?.detail || e.message))
  }
  event.target.value = ''
}

async function clearSlot(role) {
  const file = allFiles.value.find(f => f.role === role)
  if (!file) return
  try {
    await dsStore.unassignDataset(file.datasetId, projectId.value)
    await store.fetchOne(projectId.value)
  } catch (e) {
    alert('Unassign failed: ' + (e.response?.data?.detail || e.message))
  }
}

// --- Feature table logic ---
const sortedFeatures = computed(() => {
  if (!featureStats.value?.features) return []
  const arr = [...featureStats.value.features]
  const field = sortField.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  arr.sort((a, b) => {
    let va = a[field], vb = b[field]
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

function toggleFeature(f) {
  const idx = selectedFeatures.value.indexOf(f.name)
  if (idx >= 0) {
    selectedFeatures.value.splice(idx, 1)
  } else if (selectedFeatures.value.length < 20) {
    selectedFeatures.value.push(f.name)
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

// --- API calls ---
async function loadSummary() {
  if (!hasTrainData.value) return
  try {
    const { data } = await axios.get(`/api/data-explore/${projectId.value}/summary`)
    summary.value = data
  } catch { summary.value = null }
}

async function loadFeatureStats() {
  if (!hasTrainData.value) return
  featPage.value = 0
  try {
    const { data } = await axios.get(`/api/data-explore/${projectId.value}/feature-stats`, {
      params: {
        method: cfg.data.feature_selection_method,
        prevalence_pct: cfg.data.feature_minimal_prevalence_pct,
        max_pvalue: cfg.data.feature_maximal_adj_pvalue,
        min_feature_value: cfg.data.feature_minimal_feature_value,
      },
    })
    featureStats.value = data

    // Auto-select top significant features for barcode if none selected
    if (selectedFeatures.value.length === 0) {
      const top = data.features
        .filter(f => f.selected)
        .sort((a, b) => (a.significance || 1) - (b.significance || 1))
        .slice(0, 20)
        .map(f => f.name)
      if (top.length > 0) {
        selectedFeatures.value = top
        autoBarcode.value = true
      }
    }
  } catch (e) {
    console.error('Failed to load feature stats:', e)
  }
}

async function loadAbundance() {
  if (selectedFeatures.value.length === 0 || !hasTrainData.value) return
  try {
    const { data } = await axios.get(`/api/data-explore/${projectId.value}/feature-abundance`, {
      params: { features: selectedFeatures.value.join(',') },
    })
    abundanceData.value = data.features || []
  } catch (e) {
    console.error('Failed to load abundance:', e)
  }
}

async function loadBarcodeData() {
  const feats = selectedFeatures.value
  if (feats.length === 0 || !hasTrainData.value) return
  try {
    const { data } = await axios.get(`/api/data-explore/${projectId.value}/barcode-data`, {
      params: { features: feats.join(',') },
    })
    barcodeData.value = data
  } catch (e) {
    console.error('Failed to load barcode data:', e)
  }
}

async function loadAll() {
  if (!hasTrainData.value) return
  loading.value = true
  try {
    await loadSummary()
    await loadFeatureStats()
    await Promise.all([loadAbundance(), loadBarcodeData()])
  } finally {
    loading.value = false
  }
}

// Debounced refresh for filter changes
let _refreshTimer = null
function debouncedRefresh() {
  clearTimeout(_refreshTimer)
  _refreshTimer = setTimeout(() => {
    loadFeatureStats().then(() => {
      renderCurrentViz()
      loadAbundance()
      loadBarcodeData()
    })
  }, 500)
}

// --- Chart renderers ---
async function renderPrevalenceChart() {
  await nextTick()
  if (!prevalenceChartEl.value || !featureStats.value) return
  const c = chartColors()

  const features = featureStats.value.features
    .filter(f => f.selected)
    .sort((a, b) => (a.significance || 1) - (b.significance || 1))
    .slice(0, 40)

  if (features.length === 0) return

  const names = features.map(f => f.name)

  const traces = [
    {
      y: names, x: features.map(f => f.prevalence),
      type: 'bar', orientation: 'h', name: 'Overall',
      marker: { color: c.dimmed, opacity: 0.4 },
    },
    {
      y: names, x: features.map(f => f.prevalence_0),
      type: 'scatter', mode: 'markers', name: 'Class 0',
      marker: { color: c.class0, size: 8, symbol: 'circle' },
    },
    {
      y: names, x: features.map(f => f.prevalence_1),
      type: 'scatter', mode: 'markers', name: 'Class 1',
      marker: { color: c.class1, size: 8, symbol: 'diamond' },
    },
  ]

  const annotations = features
    .filter(f => f.significance != null && f.significance < 0.05)
    .map(f => ({
      x: Math.max(f.prevalence_0 || 0, f.prevalence_1 || 0, f.prevalence || 0) + 3,
      y: f.name,
      text: f.significance < 0.001 ? '***' : f.significance < 0.01 ? '**' : '*',
      showarrow: false,
      font: { color: c.danger, size: 12, family: 'monospace' },
    }))

  Plotly.newPlot(prevalenceChartEl.value, traces, chartLayout({
    xaxis: { title: { text: 'Prevalence (%)', font: { color: c.text } }, range: [0, 105], gridcolor: c.grid, color: c.text },
    yaxis: { automargin: true, autorange: 'reversed', color: c.text },
    height: Math.max(400, features.length * 18),
    barmode: 'overlay',
    annotations,
    legend: { orientation: 'h', y: 1.05, font: { color: c.text } },
    margin: { t: 30, b: 50, l: 120, r: 40 },
  }), { responsive: true, displayModeBar: false })
}

async function renderAbundanceChart() {
  await nextTick()
  if (!abundanceChartEl.value || abundanceData.value.length === 0) return
  const c = chartColors()

  // Sort features by significance (most significant at top, like prevalence)
  let features = [...abundanceData.value]
  if (featureStats.value) {
    features.sort((a, b) => {
      const sa = featureStats.value.features.find(f => f.name === a.name)
      const sb = featureStats.value.features.find(f => f.name === b.name)
      return (sa?.significance || 1) - (sb?.significance || 1)
    })
  }

  const nFeat = features.length
  const classKeys = [...new Set(features.flatMap(f => Object.keys(f.classes)))].sort()
  const nCls = classKeys.length
  const clsColors = classKeys.map(k => k === '0' ? c.class0 : c.class1)
  const clsFills = classKeys.map(k => k === '0' ? c.class0 + '44' : c.class1 + '44')

  // ggplot-like layout: numeric y for equal spacing, grouped boxes per class
  const boxH = 0.3 / nCls          // half-height of one box
  const offsets = nCls === 2 ? [-0.18, 0.18] : [0]

  const shapes = []
  const traces = []

  // Legend entries (one invisible scatter per class)
  for (let ci = 0; ci < nCls; ci++) {
    traces.push({
      type: 'scatter', mode: 'markers', x: [null], y: [null],
      name: `Class ${classKeys[ci]}`,
      marker: { color: clsColors[ci], size: 10, symbol: 'square' },
      showlegend: true,
    })
  }

  for (let ci = 0; ci < nCls; ci++) {
    const cls = classKeys[ci]
    const col = clsColors[ci]
    const fill = clsFills[ci]

    // Hover trace for this class
    const hoverX = [], hoverY = [], hoverText = []

    for (let i = 0; i < nFeat; i++) {
      const stats = features[i].classes[cls]
      if (!stats) continue
      const yC = i + offsets[ci]

      // IQR box
      shapes.push({
        type: 'rect', x0: stats.q1, x1: stats.q3,
        y0: yC - boxH, y1: yC + boxH,
        fillcolor: fill, line: { color: col, width: 1.5 },
      })
      // Median line
      shapes.push({
        type: 'line', x0: stats.median, x1: stats.median,
        y0: yC - boxH, y1: yC + boxH,
        line: { color: col, width: 2.5 },
      })
      // Left whisker
      shapes.push({
        type: 'line', x0: stats.min, x1: stats.q1, y0: yC, y1: yC,
        line: { color: col, width: 1 },
      })
      // Right whisker
      shapes.push({
        type: 'line', x0: stats.q3, x1: stats.max, y0: yC, y1: yC,
        line: { color: col, width: 1 },
      })
      // Whisker caps
      shapes.push({
        type: 'line', x0: stats.min, x1: stats.min,
        y0: yC - boxH * 0.5, y1: yC + boxH * 0.5,
        line: { color: col, width: 1.5 },
      })
      shapes.push({
        type: 'line', x0: stats.max, x1: stats.max,
        y0: yC - boxH * 0.5, y1: yC + boxH * 0.5,
        line: { color: col, width: 1.5 },
      })

      hoverX.push(stats.median)
      hoverY.push(yC)
      hoverText.push(
        `<b>${features[i].name}</b> (Class ${cls})<br>` +
        `Min: ${stats.min.toFixed(6)}<br>Q1: ${stats.q1.toFixed(6)}<br>` +
        `Median: ${stats.median.toFixed(6)}<br>Q3: ${stats.q3.toFixed(6)}<br>` +
        `Max: ${stats.max.toFixed(6)}<br>Mean: ${stats.mean.toFixed(6)}<br>` +
        `n=${stats.n}<extra></extra>`
      )
    }

    // Invisible scatter for hover tooltips
    traces.push({
      type: 'scatter', mode: 'markers',
      x: hoverX, y: hoverY,
      hovertemplate: hoverText,
      marker: { color: 'rgba(0,0,0,0)', size: 14 },
      showlegend: false,
    })
  }

  // Significance annotations on the right
  const annotations = []
  if (featureStats.value) {
    for (let i = 0; i < nFeat; i++) {
      const item = features[i]
      const fstat = featureStats.value.features.find(f => f.name === item.name)
      if (fstat?.significance != null && fstat.significance < 0.05) {
        const maxVal = Math.max(...Object.values(item.classes).map(s => s.max))
        annotations.push({
          x: maxVal * 1.1, y: i,
          text: fstat.significance < 0.001 ? '***' : fstat.significance < 0.01 ? '**' : '*',
          showarrow: false,
          font: { color: c.danger, size: 12, family: 'monospace' },
        })
      }
    }
  }

  Plotly.newPlot(abundanceChartEl.value, traces, chartLayout({
    xaxis: { title: { text: 'Abundance', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    yaxis: {
      tickvals: features.map((_, i) => i), ticktext: features.map(f => f.name),
      range: [nFeat - 0.5, -0.5], automargin: true, color: c.text, fixedrange: true,
    },
    height: Math.max(400, nFeat * 40),
    shapes,
    annotations,
    legend: { orientation: 'h', y: 1.05, font: { color: c.text } },
    margin: { t: 30, b: 50, l: 120, r: 40 },
  }), { responsive: true, displayModeBar: false })
}

async function renderBarcodeChart() {
  await nextTick()
  if (!barcodeChartEl.value || !barcodeData.value || barcodeData.value.matrix.length === 0) return
  const c = chartColors()
  const d = barcodeData.value

  // Log base-4 transformation (matching R's log_trans(base = 4) in plotBarcode)
  const LOG4 = Math.log(4)
  let lo = Infinity, hi = -Infinity
  const zLog = d.matrix.map(row => row.map(v => {
    if (v <= 0) return null
    const lv = Math.log(v) / LOG4
    if (lv < lo) lo = lv
    if (lv > hi) hi = lv
    return lv
  }))

  // Floor value for zeros → maps to white at position 0
  if (!isFinite(lo)) lo = -10
  if (!isFinite(hi)) hi = 0
  const floor = lo - 1
  const z = zLog.map(row => row.map(v => v === null ? floor : v))

  // R palette: white → deepskyblue → blue → green3 → yellow → orange → red → orangered2 → darkred
  // White band covers floor→lo (zero values), data colors cover lo→hi
  const span = hi - floor
  const whiteEnd = Math.max(0.01, (lo - floor) / span)
  const dataColors = ['#00bfff', '#0000ff', '#00cd00', '#ffff00', '#ffa500', '#ff0000', '#ee4000', '#8b0000']
  const colorscale = [[0, '#ffffff'], [whiteEnd, '#ffffff']]
  for (let i = 0; i < dataColors.length; i++) {
    colorscale.push([whiteEnd + (1 - whiteEnd) * (i + 1) / dataColors.length, dataColors[i]])
  }

  const shapes = d.class_boundaries.map(idx => ({
    type: 'line',
    x0: idx - 0.5, x1: idx - 0.5,
    y0: -0.5, y1: d.feature_names.length - 0.5,
    line: { color: c.danger, width: 2, dash: 'dash' },
  }))

  // Class label annotations below
  const labelAnnotations = []
  const boundaries = [0, ...d.class_boundaries, d.sample_names.length]
  for (let i = 0; i < d.class_labels.length; i++) {
    labelAnnotations.push({
      x: (boundaries[i] + boundaries[i + 1]) / 2,
      y: -0.12, yref: 'paper',
      text: `Class ${d.class_labels[i]}`,
      showarrow: false,
      font: { color: c.text, size: 11 },
    })
  }

  // Build tick values for the colorbar in original scale
  const nTicks = 5
  const tickVals = []
  const tickTexts = []
  for (let i = 0; i <= nTicks; i++) {
    const lv = lo + (hi - lo) * i / nTicks
    tickVals.push(lv)
    tickTexts.push(Math.pow(4, lv).toExponential(1))
  }

  Plotly.newPlot(barcodeChartEl.value, [{
    z, x: d.sample_names, y: d.feature_names,
    type: 'heatmap',
    colorscale,
    zmin: floor, zmax: hi,
    colorbar: {
      title: { text: 'Value (log\u2084)', font: { color: c.text } },
      tickvals: tickVals, ticktext: tickTexts,
      tickfont: { color: c.text },
    },
    hovertemplate: d.matrix.map((row, ri) =>
      row.map((v, ci) =>
        `Feature: ${d.feature_names[ri]}<br>Sample: ${d.sample_names[ci]}<br>Value: ${v.toExponential(4)}<extra></extra>`
      )
    ),
  }], chartLayout({
    xaxis: { showticklabels: false, title: { text: 'Samples (ordered by class)', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    yaxis: { automargin: true, color: c.text },
    height: Math.max(300, d.feature_names.length * 20 + 100),
    margin: { t: 20, b: 60, l: 120, r: 20 },
    shapes,
    annotations: labelAnnotations,
  }), { responsive: true, displayModeBar: true })
}

async function renderVolcanoChart() {
  await nextTick()
  if (!volcanoChartEl.value || !featureStats.value) return
  const c = chartColors()
  const features = featureStats.value.features

  const class0 = features.filter(f => f.selected && f.class === 0)
  const class1 = features.filter(f => f.selected && f.class === 1)
  const notSig = features.filter(f => !f.selected)

  function meanDiff(f) { return (f.mean_1 ?? 0) - (f.mean_0 ?? 0) }
  function negLog10(f) {
    if (!f.significance || f.significance <= 0) return 0
    return -Math.log10(f.significance)
  }

  const traces = []
  if (notSig.length > 0) {
    traces.push({
      x: notSig.map(meanDiff), y: notSig.map(negLog10),
      text: notSig.map(f => f.name), mode: 'markers', type: 'scatter',
      name: 'Not significant', marker: { color: c.dimmed, size: 4, opacity: 0.5 },
    })
  }
  if (class0.length > 0) {
    traces.push({
      x: class0.map(meanDiff), y: class0.map(negLog10),
      text: class0.map(f => f.name), mode: 'markers', type: 'scatter',
      name: 'Class 0', marker: { color: c.class0, size: 6 },
    })
  }
  if (class1.length > 0) {
    traces.push({
      x: class1.map(meanDiff), y: class1.map(negLog10),
      text: class1.map(f => f.name), mode: 'markers', type: 'scatter',
      name: 'Class 1', marker: { color: c.class1, size: 6 },
    })
  }

  const pThreshold = -Math.log10(cfg.data.feature_maximal_adj_pvalue)

  Plotly.newPlot(volcanoChartEl.value, traces, chartLayout({
    xaxis: { title: { text: 'Mean Difference (Class 1 - Class 0)', font: { color: c.text } }, gridcolor: c.grid, color: c.text, zeroline: true, zerolinecolor: c.grid },
    yaxis: { title: { text: '-log10(significance)', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    legend: { orientation: 'h', y: 1.12, font: { color: c.text } },
    height: 400,
    shapes: [{
      type: 'line', x0: 0, x1: 1, xref: 'paper',
      y0: pThreshold, y1: pThreshold,
      line: { color: c.danger, width: 1, dash: 'dash' },
    }],
  }), { responsive: true, displayModeBar: false })
}

function renderCurrentViz() {
  if (vizTab.value === 'prevalence') renderPrevalenceChart()
  else if (vizTab.value === 'abundance') renderAbundanceChart()
  else if (vizTab.value === 'barcode') renderBarcodeChart()
  else if (vizTab.value === 'volcano') renderVolcanoChart()
}

// Watchers for chart rendering
watch(vizTab, async () => {
  await nextTick()
  if (vizTab.value === 'prevalence') renderPrevalenceChart()
  else if (vizTab.value === 'abundance') { await loadAbundance(); renderAbundanceChart() }
  else if (vizTab.value === 'barcode') { await loadBarcodeData(); renderBarcodeChart() }
  else if (vizTab.value === 'volcano') renderVolcanoChart()
})

watch(() => themeStore.isDark, () => renderCurrentViz())

watch(selectedFeatures, async () => {
  autoBarcode.value = false
  if (selectedFeatures.value.length > 0) {
    await Promise.all([loadAbundance(), loadBarcodeData()])
    if (vizTab.value === 'abundance') renderAbundanceChart()
    if (vizTab.value === 'barcode') renderBarcodeChart()
  }
}, { deep: true })

// Watch for dataset changes (after upload/assign)
watch(hasTrainData, (val) => { if (val) loadAll() })

onMounted(() => { if (hasTrainData.value) loadAll() })
</script>

<style scoped>
.data-tab { max-width: 100%; }

.summary-bar {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
}

.stat-card {
  background: var(--bg-card);
  padding: 0.75rem 1.25rem;
  border-radius: 8px;
  box-shadow: var(--shadow);
  text-align: center;
  flex: 1;
}

.stat-value {
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--text-primary);
}
.stat-value.accent { color: var(--accent); }
.stat-label { font-size: 0.75rem; color: var(--text-faint); margin-top: 0.15rem; }

/* Two-panel layout */
.data-panels {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 1.5rem;
  align-items: start;
}

.left-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: calc(100vh - 200px);
  overflow-y: auto;
  position: sticky;
  top: 80px;
}

.right-panel {
  min-width: 0;
}

/* Dataset slots (2x2) */
.ds-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
}

.ds-slot {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.4rem 0.6rem;
  border-radius: 6px;
  border: 1.5px dashed var(--border);
  font-size: 0.75rem;
}
.ds-slot.ok { border-color: var(--success); border-style: solid; background: var(--success-bg-alt); }
.ds-slot.missing { border-color: var(--warning); background: var(--warning-bg-alt); }
.ds-slot.optional:not(.ok) { border-color: var(--border-light); background: var(--bg-badge); }

.ds-role {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.ds-file {
  color: var(--success-dark);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ds-upload {
  cursor: pointer;
  color: var(--text-primary);
  font-size: 0.7rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.15rem 0.4rem;
  text-align: center;
  transition: background 0.15s;
}
.ds-upload:hover { background: var(--bg-card-hover); }
.ds-upload.ds-optional { color: var(--text-faint); border-color: var(--border-light); }
.ds-upload input[type="file"] { display: none; }

.ds-picker {
  font-size: 0.7rem;
  padding: 0.15rem 0.25rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--text-body);
  max-width: 100%;
}

.ds-clear {
  background: none;
  border: none;
  color: var(--text-faint);
  cursor: pointer;
  font-size: 0.85rem;
  padding: 0 0.15rem;
  line-height: 1;
  vertical-align: middle;
}
.ds-clear:hover { color: var(--danger); }

/* Sections */
.section {
  background: var(--bg-card);
  padding: 0.75rem 1rem;
  border-radius: 8px;
  box-shadow: var(--shadow);
}

.section-title {
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.badge {
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--accent);
  background: var(--bg-badge);
  padding: 0.1rem 0.4rem;
  border-radius: 10px;
}

/* Form layout */
.form-col {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.form-row {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.4rem;
  flex-wrap: wrap;
}

.form-col label, .form-row label {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
  flex: 1;
  min-width: 80px;
}

input, select {
  padding: 0.3rem 0.4rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.8rem;
  background: var(--bg-input);
  color: var(--text-body);
}

input[type="checkbox"] {
  width: auto;
  align-self: flex-start;
  margin-top: 0.1rem;
}

.inline-check {
  flex-direction: row !important;
  align-items: center;
  gap: 0.35rem !important;
  font-weight: 600;
  font-size: 0.8rem;
  color: var(--text-primary) !important;
  margin-bottom: 0.4rem;
}

/* Feature table */
.feature-table-scroll {
  max-height: 320px;
  overflow-y: auto;
}

.feature-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.75rem;
}

.feature-table th {
  text-align: left;
  padding: 0.35rem 0.3rem;
  border-bottom: 2px solid var(--border-light);
  color: var(--text-secondary);
  font-weight: 600;
  white-space: nowrap;
  position: sticky;
  top: 0;
  background: var(--bg-card);
  z-index: 1;
}

.feature-table th.sortable { cursor: pointer; user-select: none; }
.feature-table th.sortable:hover { color: var(--text-primary); }

.feature-table td {
  padding: 0.3rem;
  border-bottom: 1px solid var(--border-lighter);
  color: var(--text-body);
}

.feature-table tr { cursor: pointer; transition: background 0.15s; }
.feature-table tbody tr:hover { background: var(--bg-card-hover); }

.feature-name-cell {
  font-weight: 500;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-class0 { border-left: 3px solid #1565c0; }
:root.dark .row-class0 { border-left-color: #4fc3f7; }
.row-class1 { border-left: 3px solid #2e7d32; }
:root.dark .row-class1 { border-left-color: #81c784; }
.row-dimmed { opacity: 0.45; }
.selected-row { background: var(--bg-badge) !important; }

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  font-size: 0.75rem;
}
.pagination button {
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-card);
  color: var(--text-body);
  cursor: pointer;
}
.pagination button:disabled { opacity: 0.5; cursor: not-allowed; }

/* Viz tabs */
.viz-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 1rem;
  border-bottom: 1px solid var(--border-light);
}

.viz-tabs button {
  padding: 0.45rem 1rem;
  border: none;
  background: none;
  color: var(--text-muted);
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}

.viz-tabs button.active {
  color: var(--text-primary);
  border-bottom-color: var(--accent);
}

.viz-section { min-height: 350px; }

.plotly-chart { width: 100%; min-height: 300px; }
.plotly-chart-tall { min-height: 400px; }

.info-text { color: var(--text-faint); font-size: 0.82rem; font-style: italic; text-align: center; padding: 2rem 0; }
.loading { text-align: center; padding: 2rem; color: var(--text-faint); }

@media (max-width: 1000px) {
  .data-panels { grid-template-columns: 1fr; }
  .left-panel { max-height: none; position: static; }
}
</style>
