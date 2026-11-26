<template>
  <div class="stability-tab">
    <!-- Header -->
    <p class="stab-desc">{{ $t('results.stabilityDesc') }}</p>

    <!-- Loading -->
    <div v-if="loading" class="loading">{{ $t('results.stabLoading') }}</div>

    <!-- Error -->
    <div v-if="error" class="error-text">{{ error }}</div>

    <!-- View selector -->
    <div v-if="stabData && !loading" class="stab-view-selector">
      <button :class="{ active: view === 'indices' }" @click="view = 'indices'">{{ $t('results.stabIndices') }}</button>
      <button :class="{ active: view === 'heatmap' }" @click="view = 'heatmap'">{{ $t('results.stabFeatureHeatmap') }}</button>
      <button :class="{ active: view === 'dendrogram' }" @click="view = 'dendrogram'">{{ $t('results.stabDendrogram') }}</button>
    </div>

    <!-- 1. Stability Indices vs Sparsity -->
    <div v-show="!loading && !error && stabData && view === 'indices'" class="stab-chart-wrap">
      <div ref="indicesChartEl" class="stab-chart"></div>
    </div>

    <!-- 2. Feature × Sparsity Heatmap -->
    <div v-show="!loading && !error && stabData && view === 'heatmap'" class="stab-chart-wrap">
      <div ref="heatmapChartEl" class="stab-chart stab-chart-tall"></div>
    </div>

    <!-- 3. Model Distance / Dendrogram -->
    <div v-show="!loading && !error && stabData && view === 'dendrogram'" class="stab-chart-wrap">
      <div ref="dendroChartEl" class="stab-chart stab-chart-tall"></div>
      <!-- Cluster summary -->
      <div v-if="stabData && stabData.dendrogram" class="stab-clusters">
        <h4>{{ $t('results.stabClusters') }} ({{ stabData.dendrogram.n_clusters }})</h4>
        <div v-for="(count, idx) in clusterCounts" :key="idx" class="stab-cluster-item">
          <span class="stab-cluster-dot" :style="{ backgroundColor: clusterColor(idx) }"></span>
          {{ $t('results.stabCluster') }} {{ idx + 1 }}: <strong>{{ count }}</strong> {{ $t('results.stabModels') }}
        </div>
      </div>
    </div>

    <!-- Stats bar -->
    <div v-if="stabData && !loading" class="stab-stats-bar">
      <span><strong>{{ stabData.stats.n_models }}</strong> {{ $t('results.stabModels') }}</span>
      <span>k: <strong>{{ stabData.stats.k_min }}–{{ stabData.stats.k_max }}</strong></span>
      <span>{{ $t('results.stabPeakStability') }}: <strong>k={{ stabData.stats.peak_stability_k }}</strong></span>
      <span v-if="stabData.dendrogram"><strong>{{ stabData.dendrogram.n_clusters }}</strong> {{ $t('results.stabClusters') }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useChartTheme, withAlpha } from '../../composables/useChartTheme'
import { useI18n } from 'vue-i18n'
import { api } from '../../api'
import { ct } from '../../utils/chartText'
import { loadPlotlyLib, usePlotlyCleanup } from '../../utils/plotly'
import { apiError } from '../../utils/apiError'

let Plotly = null
usePlotlyCleanup()
async function ensurePlotly() {
  if (!Plotly) {
    Plotly = await loadPlotlyLib()
  }
  return Plotly
}

/** Cluster colours come from the theme's categorical series (cycles past 10). */
const clusterColor = (i) => {
  const series = chartColors().series
  return series[i % series.length]
}

const props = defineProps({
  projectId: { type: String, required: true },
  jobId: { type: String, default: '' },
  population: { type: Array, default: () => [] },
  active: { type: Boolean, default: false },
})

const { chartColors, chartLayout } = useChartTheme()
const { t } = useI18n()

// State
const loading = ref(false)
const error = ref(null)
const stabData = ref(null)
const view = ref('indices')

// Chart refs
const indicesChartEl = ref(null)
const heatmapChartEl = ref(null)
const dendroChartEl = ref(null)

// Computed
const clusterCounts = computed(() => {
  if (!stabData.value?.dendrogram?.clusters) return []
  const clusters = stabData.value.dendrogram.clusters
  const counts = {}
  for (const c of clusters) {
    counts[c] = (counts[c] || 0) + 1
  }
  const sorted = Object.keys(counts).sort((a, b) => +a - +b)
  return sorted.map(k => counts[k])
})


// ----------- Fetch -----------

async function fetchStability() {
  if (!props.jobId) return
  loading.value = true
  error.value = null

  try {
    const { data } = await api.analysis.jobStability(props.projectId, props.jobId)
    stabData.value = data
    await nextTick()
    renderActiveView()
  } catch (err) {
    console.error('Stability error:', err)
    error.value = apiError(err)
  } finally {
    loading.value = false
  }
}

// ----------- Rendering -----------

async function renderActiveView() {
  if (!stabData.value) return
  if (view.value === 'indices') await renderIndicesChart()
  else if (view.value === 'heatmap') await renderHeatmap()
  else if (view.value === 'dendrogram') await renderDendrogram()
}

async function renderIndicesChart() {
  if (!stabData.value?.stability_by_k?.length || !indicesChartEl.value) return
  await ensurePlotly()
  const c = chartColors()

  const byK = stabData.value.stability_by_k
  const xVals = byK.map(d => d.k)

  // Stability index traces (left y-axis)
  const tanimotoTrace = {
    x: xVals,
    y: byK.map(d => d.tanimoto),
    name: 'Tanimoto',
    type: 'scatter',
    mode: 'lines+markers',
    line: { color: c.good, width: 2.5 },
    marker: { size: 6 },
    hovertemplate: `k=%{x}<br>Tanimoto=%{y:.3f}<br>n=%{customdata} ${ct('models')}<extra></extra>`,
    customdata: byK.map(d => d.n_models),
  }

  const kunchevaTrace = {
    x: xVals,
    y: byK.map(d => d.kuncheva),
    name: 'Kuncheva',
    type: 'scatter',
    mode: 'lines+markers',
    line: { color: c.accent, width: 2, dash: 'dash' },
    marker: { size: 5 },
    hovertemplate: 'k=%{x}<br>Kuncheva=%{y:.3f}<extra></extra>',
  }

  const cwRelTrace = {
    x: xVals,
    y: byK.map(d => d.cw_rel),
    name: 'CW_rel',
    type: 'scatter',
    mode: 'lines+markers',
    line: { color: c.class0, width: 2, dash: 'dashdot' },
    marker: { size: 5 },
    hovertemplate: 'k=%{x}<br>CW_rel=%{y:.3f}<extra></extra>',
  }

  // AUC trace (right y-axis)
  const aucTrace = {
    x: xVals,
    y: byK.map(d => d.mean_auc),
    name: ct('Mean AUC'),
    type: 'scatter',
    mode: 'lines+markers',
    line: { color: c.class1, width: 2, dash: 'dot' },
    marker: { size: 5 },
    yaxis: 'y2',
    hovertemplate: 'k=%{x}<br>AUC=%{y:.3f}<extra></extra>',
  }

  // Model count bar (background)
  const countTrace = {
    x: xVals,
    y: byK.map(d => d.n_models),
    name: ct('Models'),
    type: 'bar',
    marker: { color: withAlpha(c.neutral, 0.35) },
    yaxis: 'y3',
    hovertemplate: `k=%{x}<br>%{y} ${ct('models')}<extra></extra>`,
  }

  const layout = {
    ...chartLayout(),
    title: t('results.stabIndicesTitle'),
    xaxis: { title: t('results.stabSparsity'), dtick: 1, gridcolor: c.grid },
    yaxis: {
      title: t('results.stabStabilityIndex'),
      range: [-0.1, 1.05],
      gridcolor: c.grid,
    },
    yaxis2: {
      title: 'AUC',
      overlaying: 'y',
      side: 'right',
      range: [0.4, 1.05],
      showgrid: false,
    },
    yaxis3: {
      overlaying: 'y',
      side: 'right',
      visible: false,
    },
    legend: { x: 0, y: -0.25, orientation: 'h' },
    margin: { t: 50, b: 80, l: 60, r: 60 },
    height: 450,
  }

  Plotly.newPlot(
    indicesChartEl.value,
    [countTrace, tanimotoTrace, kunchevaTrace, cwRelTrace, aucTrace],
    layout,
    { responsive: true, displayModeBar: false }
  )
}

async function renderHeatmap() {
  const hm = stabData.value?.feature_sparsity_heatmap
  if (!hm?.features?.length || !heatmapChartEl.value) return
  await ensurePlotly()
  const c = chartColors()

  const trace = {
    z: hm.values,
    x: hm.sparsity_levels.map(k => `k=${k}`),
    y: hm.features,
    type: 'heatmap',
    colorscale: c.sequentialWarm,
    colorbar: { title: ct('Prevalence'), len: 0.8 },
    hovertemplate: `%{y}<br>k=%{x}<br>${ct('Prevalence')}=%{z:.2f}<extra></extra>`,
  }

  const height = Math.max(400, hm.features.length * 18 + 100)
  const layout = {
    ...chartLayout(),
    title: t('results.stabFeatureHeatmapTitle'),
    xaxis: { title: t('results.stabSparsity'), side: 'bottom' },
    yaxis: { autorange: 'reversed', dtick: 1 },
    margin: { t: 50, b: 60, l: 200, r: 80 },
    height,
  }

  Plotly.newPlot(heatmapChartEl.value, [trace], layout, {
    responsive: true,
    displayModeBar: false,
  })
}

async function renderDendrogram() {
  const dendro = stabData.value?.dendrogram
  if (!dendro?.linkage?.length || !dendroChartEl.value) return
  await ensurePlotly()
  const c = chartColors()

  const Z = dendro.linkage       // [[idx1, idx2, dist, count], ...]
  const labels = dendro.labels
  const leafOrder = dendro.leaf_order || []
  const clusters = dendro.clusters || []
  const n = labels.length

  // Build dendrogram tree coordinates from linkage matrix
  // Each merge i creates a new node at index (n + i)
  // nodePos[id] = { x, yMin, yMax } for each node/leaf
  const nodePos = {}

  // Place leaves at positions 0..n-1 in leaf order
  const leafX = {}
  for (let i = 0; i < leafOrder.length; i++) {
    leafX[leafOrder[i]] = i
    nodePos[leafOrder[i]] = { x: i, h: 0 }
  }

  // Build U-shaped links from linkage
  const lineX = []
  const lineY = []
  for (let i = 0; i < Z.length; i++) {
    const [a, b, dist] = Z[i]
    const left = nodePos[a]
    const right = nodePos[b]
    if (!left || !right) continue

    const lx = left.x
    const rx = right.x
    const lh = left.h
    const rh = right.h
    const mergeH = dist

    // U-shape: left vertical, horizontal, right vertical
    lineX.push(lx, lx, rx, rx, null)
    lineY.push(lh, mergeH, mergeH, rh, null)

    // New merged node position
    nodePos[n + i] = { x: (lx + rx) / 2, h: mergeH }
  }

  // Dendrogram line trace
  const dendroTrace = {
    x: lineX,
    y: lineY,
    type: 'scatter',
    mode: 'lines',
    line: { color: c.text, width: 1.5 },
    hoverinfo: 'skip',
    showlegend: false,
  }

  // Leaf markers colored by cluster
  const leafXArr = leafOrder.map((_, i) => i)
  const leafYArr = leafOrder.map(() => 0)
  const leafColors = leafOrder.map(idx => {
    const cl = clusters[idx] || 1
    return clusterColor(cl - 1)
  })
  const leafLabels = leafOrder.map(idx => labels[idx] || `M${idx}`)

  const leafTrace = {
    x: leafXArr,
    y: leafYArr,
    type: 'scatter',
    mode: 'markers',
    marker: { size: 8, color: leafColors, line: { width: 1, color: c.paper } },
    text: leafLabels,
    hovertemplate: '%{text}<extra></extra>',
    showlegend: false,
  }

  // Cutoff line at 0.7
  const cutoffTrace = {
    x: [-0.5, n - 0.5],
    y: [0.7, 0.7],
    type: 'scatter',
    mode: 'lines',
    line: { color: c.class1, width: 1, dash: 'dash' },
    hoverinfo: 'skip',
    showlegend: false,
  }

  const layout = {
    ...chartLayout(),
    title: t('results.stabDendrogramTitle'),
    xaxis: {
      showticklabels: n <= 60,
      tickmode: 'array',
      tickvals: leafXArr,
      ticktext: leafLabels,
      tickangle: 90,
      tickfont: { size: 10 },
      range: [-1, n],
    },
    yaxis: {
      title: ct('Tanimoto distance'),
      gridcolor: c.grid,
      rangemode: 'tozero',
    },
    margin: { t: 50, b: n <= 60 ? 120 : 40, l: 60, r: 30 },
    height: 500,
    annotations: [{
      x: n - 1,
      y: 0.7,
      text: `${ct('cutoff')} = 0.7`,
      showarrow: false,
      font: { size: 10, color: c.class1 },
      yshift: 10,
    }],
  }

  Plotly.newPlot(dendroChartEl.value, [dendroTrace, leafTrace, cutoffTrace], layout, {
    responsive: true,
    displayModeBar: false,
  })
}

// ----------- Watchers -----------

watch(view, async () => {
  await nextTick()
  renderActiveView()
})

watch(() => props.active, (active) => {
  if (active && !stabData.value) fetchStability()
})

watch(() => props.jobId, () => {
  stabData.value = null
  if (props.active && props.jobId) fetchStability()
})

onMounted(() => {
  if (props.active && props.jobId) fetchStability()
})
</script>

<style scoped>
.stability-tab { padding: 0.5rem 0; }

.stab-desc {
  color: var(--text-secondary, #666);
  font-size: 0.9rem;
  margin: 0 0 0.75rem 0;
}

.stab-view-selector {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
.stab-view-selector button {
  padding: 0.4rem 1rem;
  border: 1px solid var(--border, #ddd);
  background: var(--bg-secondary, #f8f9fa);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.15s;
}
.stab-view-selector button.active {
  background: var(--accent, #4f46e5);
  color: #fff;
  border-color: var(--accent, #4f46e5);
}
.stab-view-selector button:hover:not(.active) {
  background: var(--bg-hover, #e9ecef);
}

.stab-chart-wrap { margin: 0.5rem 0; }
.stab-chart { width: 100%; min-height: 400px; }
.stab-chart-tall { min-height: 500px; }

.stab-stats-bar {
  display: flex;
  gap: 1.5rem;
  padding: 0.6rem 1rem;
  background: var(--bg-secondary, #f8f9fa);
  border-radius: 6px;
  font-size: 0.85rem;
  margin-top: 0.75rem;
}

.stab-clusters {
  margin-top: 1rem;
  padding: 0.75rem;
  background: var(--bg-secondary, #f8f9fa);
  border-radius: 6px;
}
.stab-clusters h4 { margin: 0 0 0.5rem 0; font-size: 0.9rem; }
.stab-cluster-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
  font-size: 0.85rem;
}
.stab-cluster-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}

.loading {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary, #888);
}
.error-text {
  color: #d32f2f;
  padding: 1rem;
  background: #fdecea;
  border-radius: 6px;
  margin: 0.5rem 0;
}
</style>
