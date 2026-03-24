<template>
  <div class="ecosystem-tab">
    <!-- Controls -->
    <div class="eco-controls">
      <div class="eco-controls-row">
        <label class="eco-control">
          {{ $t('results.ecoPrevalence') }}
          <input type="range" v-model.number="prevalenceThreshold" min="5" max="80" step="5" />
          <span class="eco-value">{{ prevalenceThreshold }}%</span>
        </label>
        <label class="eco-control">
          {{ $t('results.ecoCorrelation') }}
          <input type="range" v-model.number="correlationThreshold" min="0.1" max="0.8" step="0.05" />
          <span class="eco-value">{{ correlationThreshold.toFixed(2) }}</span>
        </label>
        <label class="eco-control">
          {{ $t('results.ecoClassFilter') }}
          <select v-model="classFilter">
            <option value="all">{{ $t('results.ecoAllSamples') }}</option>
            <option value="0">{{ classLabels[0] || 'Class 0' }}</option>
            <option value="1">{{ classLabels[1] || 'Class 1' }}</option>
          </select>
        </label>
        <label class="eco-control">
          {{ $t('results.ecoColorBy') }}
          <select v-model="colorMode">
            <option value="taxonomy">{{ $t('results.ecoTaxonomy') }}</option>
            <option value="module">{{ $t('results.ecoModule') }}</option>
            <option value="enrichment">{{ $t('results.ecoEnrichment') }}</option>
          </select>
        </label>
        <label class="eco-control">
          {{ $t('results.ecoLayout') }}
          <select v-model="layoutMode">
            <option value="organic">{{ $t('results.ecoOrganic') }}</option>
            <option value="force">{{ $t('results.forceDirected') }}</option>
            <option value="circle">{{ $t('results.circle') }}</option>
            <option value="radial">{{ $t('results.radial') }}</option>
          </select>
        </label>
        <label class="eco-control">
          {{ $t('results.ecoCommunity') }}
          <select v-model="communityMethod">
            <option value="louvain">Louvain</option>
            <option value="greedy">{{ $t('results.ecoGreedy') }}</option>
            <option value="label_propagation">{{ $t('results.ecoLabelProp') }}</option>
          </select>
        </label>
        <label class="eco-control" v-if="jobId">
          <input type="checkbox" v-model="fbmOverlay" />
          {{ $t('results.ecoFbmOverlay') }}
        </label>
        <label class="eco-control">
          <input type="checkbox" v-model="dualMode" />
          {{ $t('results.ecoDualMode') }}
        </label>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading">{{ $t('results.ecoLoading') }}</div>

    <!-- Error -->
    <div v-if="error" class="error-text">{{ error }}</div>

    <!-- Zoom breadcrumb -->
    <div v-if="zoomedModule !== null" class="eco-breadcrumb">
      <button class="btn-sm btn-outline" @click="zoomOut">&#8592; {{ $t('results.ecoBackToFull') }}</button>
      <span class="eco-breadcrumb-label">{{ $t('results.ecoModule') }} {{ zoomedModule + 1 }} &mdash; {{ zoomedMembers.length }} {{ $t('results.ecoNodes') }}</span>
    </div>

    <!-- Network Chart -->
    <div v-show="!loading && !error && displayedNetwork" class="eco-chart-wrap">
      <div ref="networkChartEl" class="eco-chart"></div>
    </div>

    <!-- Stats bar -->
    <div v-if="displayedNetwork && !loading" class="eco-stats-bar">
      <span><strong>{{ displayedNetwork.stats.n_nodes }}</strong> {{ $t('results.ecoNodes') }}</span>
      <span><strong>{{ displayedNetwork.stats.n_edges }}</strong> {{ $t('results.ecoEdges') }}</span>
      <span><strong>{{ displayedNetwork.stats.n_modules }}</strong> {{ $t('results.ecoModules') }}</span>
      <span>{{ $t('results.ecoModularity') }}: <strong>{{ displayedNetwork.stats.modularity }}</strong></span>
      <span>{{ $t('results.ecoFeaturesFiltered') }}: <strong>{{ displayedNetwork.stats.n_features_filtered }}</strong> / {{ displayedNetwork.stats.n_features_total }}</span>
    </div>

    <!-- Dual Network View -->
    <div v-if="dualMode && dualData && !loading" class="eco-dual-wrap">
      <div class="eco-dual-header">
        <span class="eco-dual-stats">
          {{ $t('results.ecoCommonEdges') }}: <strong>{{ dualData.comparison.common_edges }}</strong>
          &middot; {{ classLabels[0] || 'Class 0' }}: <strong>{{ dualData.comparison.specific_0 }}</strong> {{ $t('results.ecoSpecific') }}
          &middot; {{ classLabels[1] || 'Class 1' }}: <strong>{{ dualData.comparison.specific_1 }}</strong> {{ $t('results.ecoSpecific') }}
        </span>
      </div>
      <div class="eco-dual-grid">
        <div class="eco-dual-panel">
          <h4>{{ classLabels[0] || 'Class 0' }} ({{ $t('results.ecoControls') }})</h4>
          <div ref="dualChart0El" class="eco-chart eco-chart-dual"></div>
        </div>
        <div class="eco-dual-panel">
          <h4>{{ classLabels[1] || 'Class 1' }} ({{ $t('results.ecoPatients') }})</h4>
          <div ref="dualChart1El" class="eco-chart eco-chart-dual"></div>
        </div>
      </div>
    </div>

    <!-- Sankey Module Correspondence -->
    <div v-if="dualMode && dualData && dualData.sankey_links && dualData.sankey_links.length > 0 && !loading" class="eco-sankey-wrap">
      <h4>{{ $t('results.ecoSankeyTitle') }}</h4>
      <p class="eco-sankey-desc">{{ $t('results.ecoSankeyDesc') }}</p>
      <div ref="sankeyChartEl" class="eco-chart eco-chart-sankey"></div>
    </div>

    <!-- Module + Legend section -->
    <div v-if="displayedNetwork && !loading" class="eco-bottom">
      <!-- Module list -->
      <section class="eco-modules">
        <h4>{{ $t('results.ecoModulesTitle') }}</h4>
        <div v-for="mod in networkData.modules" :key="mod.id" class="eco-module-item"
             :class="{ highlighted: highlightedModule === mod.id }"
             @click="toggleModuleHighlight(mod.id)">
          <span class="eco-module-dot" :style="{ backgroundColor: mod.color }"></span>
          <span>{{ $t('results.ecoModule') }} {{ mod.id + 1 }}</span>
          <span class="eco-module-size">{{ mod.size }} {{ $t('results.ecoNodes') }}</span>
          <span class="eco-module-phylum">{{ mod.dominant_phylum }}</span>
          <button class="btn-icon btn-zoom" @click.stop="zoomIntoModule(mod)" :title="$t('results.ecoZoomModule')">&#128269;</button>
        </div>
      </section>

      <!-- Taxonomy legend -->
      <section class="eco-legend" v-if="colorMode === 'taxonomy'">
        <h4>{{ $t('results.ecoTaxonomyLegend') }}</h4>
        <div class="eco-legend-grid">
          <div v-for="entry in displayedNetwork.taxonomy_legend" :key="entry.family" class="eco-legend-item">
            <span class="eco-legend-dot" :style="{ backgroundColor: entry.color }"></span>
            <span class="eco-legend-family">{{ entry.family }}</span>
            <span class="eco-legend-phylum">{{ entry.phylum }}</span>
          </div>
        </div>
      </section>
    </div>

    <!-- External Network Import -->
    <div class="eco-external-section">
      <div class="eco-external-header">
        <h4>{{ $t('results.ecoExternalTitle') }}</h4>
        <div class="eco-external-controls">
          <select v-model="selectedExternalId" class="eco-external-select" v-if="allNetworks.length > 0">
            <option value="">{{ $t('results.ecoSelectNetwork') }}</option>
            <optgroup v-if="referenceNetworks.length" :label="$t('results.ecoReferenceNetworks')">
              <option v-for="net in referenceNetworks" :key="net.id" :value="net.id">
                {{ net.name }} ({{ net.n_nodes }} {{ $t('results.ecoNodes') }})
              </option>
            </optgroup>
            <optgroup v-if="externalNetworks.length" :label="$t('results.ecoUploadedNetworks')">
              <option v-for="net in externalNetworks" :key="net.id" :value="net.id">
                {{ net.name }} ({{ net.n_nodes }} {{ $t('results.ecoNodes') }})
              </option>
            </optgroup>
          </select>
          <label class="eco-external-upload btn-sm btn-outline">
            {{ $t('results.ecoUploadNetwork') }}
            <input type="file" accept=".json" @change="uploadExternalNetwork" hidden />
          </label>
          <button v-if="selectedExternalId && allNetworks.find(n => n.id === selectedExternalId)?.source === 'uploaded'" class="btn-sm btn-danger-outline" @click="deleteExternalNetwork">
            {{ $t('common.delete') }}
          </button>
        </div>
      </div>
      <div v-if="externalNetworkData" class="eco-chart-wrap">
        <div ref="externalChartEl" class="eco-chart"></div>
      </div>
      <div v-if="loadingExternal" class="loading">{{ $t('common.loading') }}</div>
    </div>

    <!-- FBM Module Filter -->
    <div v-if="networkData && networkData.modules.length > 0 && population.length > 0" class="eco-fbm-filter-section">
      <h4>{{ $t('results.ecoFbmFilterTitle') }}</h4>
      <p class="eco-fbm-filter-desc">{{ $t('results.ecoFbmFilterDesc') }}</p>

      <div class="eco-fbm-filter-controls">
        <div class="eco-module-checkboxes">
          <label v-for="mod in networkData.modules" :key="mod.id" class="eco-module-check">
            <input type="checkbox" :value="mod.id" v-model="selectedModuleIds" />
            <span class="eco-module-dot" :style="{ backgroundColor: mod.color }"></span>
            {{ $t('results.ecoModule') }} {{ mod.id + 1 }}
            <span class="eco-module-size">({{ mod.size }} {{ $t('results.ecoNodes') }})</span>
            <span class="eco-module-phylum">{{ mod.dominant_phylum }}</span>
          </label>
        </div>

        <div class="eco-fbm-filter-actions">
          <button
            class="btn-sm btn-primary"
            :disabled="selectedModuleIds.length === 0 || fbmFilterLoading"
            @click="applyFbmModuleFilter"
          >
            {{ fbmFilterLoading ? $t('common.loading') : $t('results.ecoFbmApplyFilter') }}
          </button>
          <button
            v-if="fbmFilterResult"
            class="btn-sm btn-outline"
            @click="clearFbmFilter"
          >
            {{ $t('results.clear') }}
          </button>
        </div>
      </div>

      <!-- Filter error -->
      <div v-if="fbmFilterError" class="error-text">{{ fbmFilterError }}</div>

      <!-- Filter results -->
      <div v-if="fbmFilterResult" class="eco-fbm-filter-results">
        <div class="eco-fbm-filter-summary">
          <span>
            <strong>{{ fbmFilterResult.filtered_count }}</strong> / {{ fbmFilterResult.total_models }}
            {{ $t('results.models') }} {{ $t('results.ecoFbmPassFilter') }}
          </span>
          <span class="eco-fbm-module-species">
            {{ $t('results.ecoFbmModuleSpecies') }}: <strong>{{ fbmFilterResult.module_species_count }}</strong>
          </span>
        </div>

        <div v-if="fbmFilterResult.filtered_models.length > 0" class="eco-fbm-table-wrap">
          <table class="eco-fbm-table">
            <thead>
              <tr>
                <th>#</th>
                <th>{{ $t('results.fit') }}</th>
                <th>{{ $t('results.k') }}</th>
                <th>{{ $t('results.language') }}</th>
                <th>{{ $t('results.ecoFbmCoverage') }}</th>
                <th>{{ $t('results.ecoFbmCoherence') }}</th>
                <th>{{ $t('results.ecoFbmInModule') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(model, i) in fbmFilterResult.filtered_models.slice(0, fbmFilterShowCount)" :key="i">
                <td>{{ model.index + 1 }}</td>
                <td>{{ model.fit != null ? model.fit.toFixed(4) : '—' }}</td>
                <td>{{ model.k }}</td>
                <td>{{ model.language || '—' }}</td>
                <td>
                  <span class="eco-fbm-bar-wrap">
                    <span class="eco-fbm-bar" :style="{ width: (model.module_coverage * 100) + '%' }"></span>
                    <span class="eco-fbm-bar-label">{{ (model.module_coverage * 100).toFixed(0) }}%</span>
                  </span>
                </td>
                <td>{{ (model.module_coherence * 100).toFixed(0) }}%</td>
                <td>{{ model.features_in_module }} / {{ model.total_features }}</td>
              </tr>
            </tbody>
          </table>
          <button
            v-if="fbmFilterResult.filtered_models.length > fbmFilterShowCount"
            class="btn-sm btn-outline eco-fbm-show-more"
            @click="fbmFilterShowCount += 20"
          >
            {{ $t('results.ecoFbmShowMore') }} ({{ fbmFilterResult.filtered_models.length - fbmFilterShowCount }} {{ $t('results.ecoFbmRemaining') }})
          </button>
        </div>

        <button
          v-if="fbmFilterResult.filtered_models.length > 0"
          class="btn-sm btn-outline eco-fbm-export"
          @click="exportFilteredFbm"
        >
          {{ $t('results.ecoFbmExportCsv') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useChartTheme } from '../../composables/useChartTheme'
import { useI18n } from 'vue-i18n'
import { MODULE_COLORS } from '../../utils/taxonomyColors'
import axios from 'axios'

let Plotly = null
async function ensurePlotly() {
  if (!Plotly) {
    const mod = await import('plotly.js-dist-min')
    Plotly = mod.default
  }
  return Plotly
}

const props = defineProps({
  projectId: { type: String, required: true },
  jobId: { type: String, default: '' },
  population: { type: Array, default: () => [] },
  classLabels: { type: Array, default: () => [] },
  active: { type: Boolean, default: false },
})

const emit = defineEmits(['module-filter-applied'])

const { chartColors, chartLayout } = useChartTheme()
const { t } = useI18n()

// Controls
const prevalenceThreshold = ref(30)
const correlationThreshold = ref(0.3)
const classFilter = ref('all')
const colorMode = ref('taxonomy')
const layoutMode = ref('organic')
const communityMethod = ref('louvain')
const fbmOverlay = ref(false)
const highlightedModule = ref(null)

// Zoom state
const zoomedModule = ref(null)       // Module ID currently zoomed into
const zoomedNetworkData = ref(null)  // Network data for the zoomed module
const zoomedMembers = ref([])        // Feature IDs in the zoomed module

// Dual mode state
const dualMode = ref(false)
const dualData = ref(null)
const dualChart0El = ref(null)
const dualChart1El = ref(null)
const sankeyChartEl = ref(null)

// State
const loading = ref(false)
const error = ref(null)
const networkData = ref(null)
const networkChartEl = ref(null)

// External network state
const externalNetworks = ref([])
const referenceNetworks = ref([])
const selectedExternalId = ref('')
const externalNetworkData = ref(null)
const externalChartEl = ref(null)
const loadingExternal = ref(false)

// FBM Module Filter state
const selectedModuleIds = ref([])
const fbmFilterLoading = ref(false)
const fbmFilterError = ref(null)
const fbmFilterResult = ref(null)
const fbmFilterShowCount = ref(20)

// Computed: currently displayed network (zoomed or full)
const displayedNetwork = computed(() => zoomedNetworkData.value || networkData.value)

// Debounce timer
let fetchTimer = null

function toggleModuleHighlight(modId) {
  highlightedModule.value = highlightedModule.value === modId ? null : modId
  if (networkData.value) renderNetwork()
}

async function zoomIntoModule(mod) {
  // Extract feature IDs that belong to this module
  const members = networkData.value.nodes
    .filter(n => n.module === mod.id)
    .map(n => n.id)

  if (members.length < 2) return

  zoomedModule.value = mod.id
  zoomedMembers.value = members
  loading.value = true
  error.value = null

  try {
    const params = {
      min_prevalence_pct: Math.max(5, prevalenceThreshold.value * 0.5),
      correlation_threshold: Math.max(0.1, correlationThreshold.value * 0.5),
      class_filter: classFilter.value,
      features: members.join(','),
    }
    if (fbmOverlay.value && props.jobId) {
      params.job_id = props.jobId
    }
    const { data } = await axios.get(`/api/data-explore/${props.projectId}/coabundance-network`, { params })
    zoomedNetworkData.value = data
    await nextTick()
    await renderNetwork()
  } catch (err) {
    error.value = err.response?.data?.detail || err.message
  } finally {
    loading.value = false
  }
}

function zoomOut() {
  zoomedModule.value = null
  zoomedNetworkData.value = null
  zoomedMembers.value = []
  renderNetwork()
}

async function fetchNetwork() {
  // Clear zoom state when parameters change
  zoomedModule.value = null
  zoomedNetworkData.value = null
  zoomedMembers.value = []

  loading.value = true
  error.value = null

  try {
    const params = {
      min_prevalence_pct: prevalenceThreshold.value,
      correlation_threshold: correlationThreshold.value,
      class_filter: classFilter.value,
      community_method: communityMethod.value,
    }

    // Add FBM features if overlay is enabled
    if (fbmOverlay.value && props.jobId) {
      params.job_id = props.jobId
    }

    // Add FBM feature names if available
    if (props.population.length > 0) {
      const allFeatures = new Set()
      for (const ind of props.population) {
        const named = ind.named_features || {}
        for (const f of Object.keys(named)) allFeatures.add(f)
      }
      if (allFeatures.size > 0 && allFeatures.size < 500) {
        // Only send features filter if FBM overlay and reasonable size
        // For full ecosystem view, we compute on all features
      }
    }

    const { data } = await axios.get(`/api/data-explore/${props.projectId}/coabundance-network`, { params })
    networkData.value = data

    await nextTick()
    await renderNetwork()
  } catch (err) {
    console.error('Ecosystem network error:', err)
    error.value = err.response?.data?.detail || err.message
  } finally {
    loading.value = false
  }
}

async function fetchDualNetwork() {
  loading.value = true
  error.value = null
  try {
    const params = {
      min_prevalence_pct: prevalenceThreshold.value,
      correlation_threshold: correlationThreshold.value,
      community_method: communityMethod.value,
    }
    if (fbmOverlay.value && props.jobId) {
      params.job_id = props.jobId
    }
    const { data } = await axios.get(`/api/data-explore/${props.projectId}/dual-network`, { params })
    dualData.value = data
    await nextTick()
    renderDualNetworks()
  } catch (err) {
    error.value = err.response?.data?.detail || err.message
  } finally {
    loading.value = false
  }
}

async function renderDualNetworks() {
  if (!dualData.value || !dualChart0El.value || !dualChart1El.value) return
  await ensurePlotly()
  const c = chartColors()

  const renderOne = (netData, el, specificColor) => {
    const { nodes, edges } = netData
    if (!nodes.length) return

    const { x: nodeX, y: nodeY } = getLayout(nodes, edges)
    const idxMap = {}
    nodes.forEach((nd, i) => { idxMap[nd.id] = i })

    const edgeTraces = []
    for (const edge of edges) {
      const i = idxMap[edge.source]
      const j = idxMap[edge.target]
      if (i === undefined || j === undefined) continue
      const isShared = edge.shared
      edgeTraces.push({
        type: 'scatter',
        mode: 'lines',
        x: [nodeX[i], nodeX[j], null],
        y: [nodeY[i], nodeY[j], null],
        line: {
          color: isShared ? 'rgba(150,150,150,0.3)' : specificColor,
          width: isShared ? 1 : Math.min(4, 0.5 + Math.abs(edge.correlation) * 3),
          dash: edge.correlation > 0 ? 'solid' : 'dash',
        },
        hoverinfo: 'skip',
        showlegend: false,
      })
    }

    const nodeColors = nodes.map(nd => nd.color)
    const maxDegree = Math.max(1, ...nodes.map(n => n.degree))
    const nodeSizes = nodes.map(nd => 6 + (nd.degree / maxDegree) * 18)
    const hoverTexts = nodes.map(nd => {
      let t = `<b>${nd.species || nd.id}</b><br>`
      t += `${nd.phylum} / ${nd.family}<br>`
      t += `Degree: ${nd.degree} | Module: ${nd.module + 1}`
      return t
    })

    const nodeTrace = {
      type: 'scatter',
      mode: 'markers',
      x: nodeX, y: nodeY,
      marker: {
        size: nodeSizes,
        color: nodeColors,
        symbol: nodes.map(nd => nd.enriched_class === 1 ? 'square' : 'circle'),
        opacity: 0.85,
        line: { color: c.text, width: 0.8 },
      },
      hovertemplate: '%{customdata}<extra></extra>',
      customdata: hoverTexts,
      showlegend: false,
    }

    const layout = chartLayout({
      xaxis: { visible: false, showgrid: false, zeroline: false },
      yaxis: { visible: false, showgrid: false, zeroline: false, scaleanchor: 'x' },
      height: 450,
      margin: { t: 10, b: 10, l: 10, r: 10 },
      hovermode: 'closest',
    })

    Plotly.newPlot(el, [...edgeTraces, nodeTrace], layout, { responsive: true, displayModeBar: false })
  }

  renderOne(dualData.value.network_0, dualChart0El.value, 'rgba(38,166,154,0.7)')
  renderOne(dualData.value.network_1, dualChart1El.value, 'rgba(255,152,0,0.7)')

  await nextTick()
  renderSankeyChart()
}

async function renderSankeyChart() {
  if (!dualData.value || !dualData.value.sankey_links || !dualData.value.sankey_links.length || !sankeyChartEl.value) return
  await ensurePlotly()
  const c = chartColors()

  const links = dualData.value.sankey_links
  const mods0 = dualData.value.network_0.modules
  const mods1 = dualData.value.network_1.modules

  // Sankey nodes: first all class 0 modules, then all class 1 modules
  const n0 = mods0.length

  const nodeLabels = [
    ...mods0.map(m => `${props.classLabels[0] || 'Class 0'} M${m.id + 1} (${m.dominant_phylum})`),
    ...mods1.map(m => `${props.classLabels[1] || 'Class 1'} M${m.id + 1} (${m.dominant_phylum})`),
  ]
  const nodeColors = [
    ...mods0.map(m => m.color || MODULE_COLORS[m.id % MODULE_COLORS.length]),
    ...mods1.map(m => m.color || MODULE_COLORS[m.id % MODULE_COLORS.length]),
  ]

  // Build link arrays
  const source = []
  const target = []
  const value = []
  const linkColor = []

  for (const link of links) {
    source.push(link.source_module)          // index in class 0 modules
    target.push(n0 + link.target_module)     // offset by n0 for class 1
    value.push(link.value)
    // Color by source module with transparency
    const col = mods0[link.source_module]?.color || MODULE_COLORS[link.source_module % MODULE_COLORS.length]
    // Handle both rgb() and hex color formats
    if (col.startsWith('rgb(')) {
      linkColor.push(col.replace(')', ', 0.4)').replace('rgb(', 'rgba('))
    } else if (col.startsWith('#')) {
      // Convert hex to rgba
      const r = parseInt(col.slice(1, 3), 16)
      const g = parseInt(col.slice(3, 5), 16)
      const b = parseInt(col.slice(5, 7), 16)
      linkColor.push(`rgba(${r}, ${g}, ${b}, 0.4)`)
    } else {
      linkColor.push(col)
    }
  }

  const trace = {
    type: 'sankey',
    orientation: 'h',
    node: {
      pad: 15,
      thickness: 20,
      line: { color: c.text, width: 0.5 },
      label: nodeLabels,
      color: nodeColors,
    },
    link: {
      source,
      target,
      value,
      color: linkColor,
    },
  }

  const layout = chartLayout({
    height: 400,
    margin: { t: 10, b: 10, l: 10, r: 10 },
    font: { size: 11, color: c.text },
  })

  Plotly.newPlot(sankeyChartEl.value, [trace], layout, { responsive: true, displayModeBar: false })
}

function debouncedFetch() {
  clearTimeout(fetchTimer)
  fetchTimer = setTimeout(() => {
    fetchNetwork()
    if (dualMode.value) fetchDualNetwork()
  }, 400)
}

// --- Layout algorithms ---

// Seeded PRNG for reproducible layouts
function mulberry32(seed) {
  return function() {
    let t = seed += 0x6D2B79F5
    t = Math.imul(t ^ t >>> 15, t | 1)
    t ^= t + Math.imul(t ^ t >>> 7, t | 61)
    return ((t ^ t >>> 14) >>> 0) / 4294967296
  }
}

function layoutCircle(n) {
  const x = [], y = []
  for (let i = 0; i < n; i++) {
    const angle = (2 * Math.PI * i) / n
    x.push(Math.cos(angle))
    y.push(Math.sin(angle))
  }
  return { x, y }
}

function layoutRadial(nodes) {
  const n = nodes.length
  if (n === 0) return { x: [], y: [] }

  const sorted = [...nodes].sort((a, b) => (b.degree || 0) - (a.degree || 0))
  const positions = {}
  positions[sorted[0].id] = { x: 0, y: 0 }

  let ringIdx = 0, placed = 1
  while (placed < n) {
    ringIdx++
    const radius = ringIdx * 1.5
    const ringCapacity = Math.max(6, Math.floor(2 * Math.PI * radius / 0.8))
    const ringCount = Math.min(ringCapacity, n - placed)
    for (let i = 0; i < ringCount; i++) {
      const angle = (2 * Math.PI * i) / ringCount
      positions[sorted[placed].id] = { x: radius * Math.cos(angle), y: radius * Math.sin(angle) }
      placed++
    }
  }
  return {
    x: nodes.map(nd => positions[nd.id]?.x || 0),
    y: nodes.map(nd => positions[nd.id]?.y || 0),
  }
}

/**
 * Fruchterman-Reingold organic layout.
 * Random initialization, attractive/repulsive forces, simulated annealing.
 * Produces natural, non-circular network shapes.
 */
function layoutOrganic(nodes, edges) {
  const n = nodes.length
  if (n === 0) return { x: [], y: [] }

  const idxMap = {}
  nodes.forEach((nd, i) => { idxMap[nd.id] = i })

  // Build adjacency for quick lookup
  const adj = Array.from({ length: n }, () => [])
  for (const edge of edges) {
    const i = idxMap[edge.source], j = idxMap[edge.target]
    if (i !== undefined && j !== undefined) {
      adj[i].push({ j, w: Math.abs(edge.correlation) })
      adj[j].push({ i: i, w: Math.abs(edge.correlation) })
    }
  }

  // Optimal distance (Fruchterman-Reingold k parameter)
  const area = n * 8
  const k = Math.sqrt(area / n)
  const k2 = k * k

  // Random initial positions (seeded for reproducibility)
  const rng = mulberry32(42)
  const spread = Math.sqrt(n) * 2
  const nodeX = Array.from({ length: n }, () => (rng() - 0.5) * spread)
  const nodeY = Array.from({ length: n }, () => (rng() - 0.5) * spread)

  // Simulated annealing temperature
  let temperature = spread * 0.2
  const cooling = 0.95
  const iterations = 200

  for (let iter = 0; iter < iterations; iter++) {
    const fx = new Array(n).fill(0)
    const fy = new Array(n).fill(0)

    // Repulsive forces between all pairs
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = nodeX[i] - nodeX[j]
        let dy = nodeY[i] - nodeY[j]
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01)
        // FR repulsion: k^2 / dist
        const repForce = k2 / dist
        const rx = (dx / dist) * repForce
        const ry = (dy / dist) * repForce
        fx[i] += rx; fy[i] += ry
        fx[j] -= rx; fy[j] -= ry
      }
    }

    // Attractive forces along edges
    for (const edge of edges) {
      const i = idxMap[edge.source], j = idxMap[edge.target]
      if (i === undefined || j === undefined) continue
      let dx = nodeX[j] - nodeX[i]
      let dy = nodeY[j] - nodeY[i]
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01)
      // FR attraction: dist^2 / k, weighted by correlation strength
      const attForce = (dist * dist / k) * (0.5 + Math.abs(edge.correlation) * 0.5)
      const ax = (dx / dist) * attForce
      const ay = (dy / dist) * attForce
      fx[i] += ax; fy[i] += ay
      fx[j] -= ax; fy[j] -= ay
    }

    // Mild gravity toward center to prevent drift
    const gravity = 0.02
    for (let i = 0; i < n; i++) {
      fx[i] -= nodeX[i] * gravity
      fy[i] -= nodeY[i] * gravity
    }

    // Apply displacement, limited by temperature
    for (let i = 0; i < n; i++) {
      const disp = Math.sqrt(fx[i] * fx[i] + fy[i] * fy[i])
      if (disp > 0) {
        const capped = Math.min(disp, temperature)
        nodeX[i] += (fx[i] / disp) * capped
        nodeY[i] += (fy[i] / disp) * capped
      }
    }

    temperature *= cooling
  }

  return { x: nodeX, y: nodeY }
}

function layoutForceDirected(nodes, edges) {
  const n = nodes.length
  if (n === 0) return { x: [], y: [] }

  const idxMap = {}
  nodes.forEach((nd, i) => { idxMap[nd.id] = i })

  // Random initial positions (not circle) for non-circular result
  const rng = mulberry32(123)
  const spread = Math.sqrt(n) * 2
  const nodeX = Array.from({ length: n }, () => (rng() - 0.5) * spread)
  const nodeY = Array.from({ length: n }, () => (rng() - 0.5) * spread)

  for (let iter = 0; iter < 120; iter++) {
    const fx = new Array(n).fill(0)
    const fy = new Array(n).fill(0)

    // Repulsion
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = nodeX[i] - nodeX[j]
        const dy = nodeY[i] - nodeY[j]
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.3)
        const force = 400 / (dist * dist)
        fx[i] += force * dx / dist
        fy[i] += force * dy / dist
        fx[j] -= force * dx / dist
        fy[j] -= force * dy / dist
      }
    }

    // Attraction along edges
    for (const edge of edges) {
      const i = idxMap[edge.source], j = idxMap[edge.target]
      if (i === undefined || j === undefined) continue
      const dx = nodeX[j] - nodeX[i]
      const dy = nodeY[j] - nodeY[i]
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.3)
      const sign = edge.correlation > 0 ? 1 : -0.3
      const force = sign * Math.abs(edge.correlation) * 0.15
      fx[i] += force * dx / dist
      fy[i] += force * dy / dist
      fx[j] -= force * dx / dist
      fy[j] -= force * dy / dist
    }

    // Gravity
    for (let i = 0; i < n; i++) {
      fx[i] -= nodeX[i] * 0.01
      fy[i] -= nodeY[i] * 0.01
    }

    const damping = 0.7 / (1 + iter * 0.04)
    for (let i = 0; i < n; i++) {
      nodeX[i] += fx[i] * damping
      nodeY[i] += fy[i] * damping
    }
  }

  return { x: nodeX, y: nodeY }
}

function getLayout(nodes, edges) {
  if (layoutMode.value === 'circle') return layoutCircle(nodes.length)
  if (layoutMode.value === 'radial') return layoutRadial(nodes, edges)
  if (layoutMode.value === 'organic') return layoutOrganic(nodes, edges)
  return layoutForceDirected(nodes, edges)
}

// --- Rendering ---

async function renderNetwork() {
  const data = displayedNetwork.value
  if (!data || !networkChartEl.value) return

  await ensurePlotly()
  const c = chartColors()
  const { nodes, edges } = data

  if (!nodes.length) return

  // Compute layout
  const { x: nodeX, y: nodeY } = getLayout(nodes, edges)

  // Build id→index mapping
  const idxMap = {}
  nodes.forEach((nd, i) => { idxMap[nd.id] = i })

  // Edge traces
  const edgeTraces = []
  for (const edge of edges) {
    const i = idxMap[edge.source]
    const j = idxMap[edge.target]
    if (i === undefined || j === undefined) continue

    const isPositive = edge.correlation > 0
    edgeTraces.push({
      type: 'scatter',
      mode: 'lines',
      x: [nodeX[i], nodeX[j], null],
      y: [nodeY[i], nodeY[j], null],
      line: {
        color: isPositive
          ? `rgba(150, 150, 150, ${highlightedModule.value !== null ? 0.1 : 0.3})`
          : `rgba(200, 80, 80, ${highlightedModule.value !== null ? 0.1 : 0.35})`,
        width: Math.min(4, 0.5 + Math.abs(edge.correlation) * 3),
        dash: isPositive ? 'solid' : 'dash',
      },
      hoverinfo: 'skip',
      showlegend: false,
    })
  }

  // Node colors by mode
  const nodeColors = nodes.map(nd => {
    if (highlightedModule.value !== null && nd.module !== highlightedModule.value) {
      return c.dimmed
    }
    if (colorMode.value === 'taxonomy') {
      return nd.color
    } else if (colorMode.value === 'module') {
      return MODULE_COLORS[nd.module % MODULE_COLORS.length]
    } else {
      // enrichment
      return nd.enriched_class === 1 ? c.class1 : c.class0
    }
  })

  // Node sizes: by degree (scaled)
  const maxDegree = Math.max(1, ...nodes.map(n => n.degree))
  const nodeSizes = nodes.map(nd => 8 + (nd.degree / maxDegree) * 22)

  // Node symbols: square for enriched_class 1, circle for 0
  const nodeSymbols = nodes.map(nd => {
    if (fbmOverlay.value && nd.fbm_coefficient != null) {
      return nd.fbm_coefficient > 0 ? 'diamond' : nd.fbm_coefficient < 0 ? 'square' : 'circle'
    }
    return nd.enriched_class === 1 ? 'square' : 'circle'
  })

  // Node opacity
  const nodeOpacity = nodes.map(nd => {
    if (highlightedModule.value !== null && nd.module !== highlightedModule.value) return 0.2
    return 0.9
  })

  // Build hover text
  const hoverTexts = nodes.map(nd => {
    let text = `<b>${nd.species || nd.id}</b><br>`
    text += `${nd.phylum} / ${nd.family}<br>`
    text += `Degree: ${nd.degree}<br>`
    text += `Module: ${nd.module + 1}<br>`
    text += `Betweenness: ${nd.betweenness}<br>`
    text += `Prev(0): ${(nd.prevalence_0 * 100).toFixed(1)}% | Prev(1): ${(nd.prevalence_1 * 100).toFixed(1)}%`
    if (fbmOverlay.value && nd.fbm_prevalence != null) {
      text += `<br>FBM prev: ${(nd.fbm_prevalence * 100).toFixed(1)}%`
      text += ` | coeff: ${nd.fbm_coefficient > 0 ? '+1' : nd.fbm_coefficient < 0 ? '-1' : '0'}`
    }
    return text
  })

  // Node border: highlight FBM nodes
  const nodeBorderWidth = nodes.map(nd => {
    if (fbmOverlay.value && nd.fbm_prevalence != null) return 2.5
    return 1
  })
  const nodeBorderColor = nodes.map(nd => {
    if (fbmOverlay.value && nd.fbm_prevalence != null) {
      return nd.fbm_coefficient > 0 ? c.class1 : nd.fbm_coefficient < 0 ? c.class0 : c.text
    }
    return c.text
  })

  const nodeTrace = {
    type: 'scatter',
    mode: 'markers+text',
    x: nodeX,
    y: nodeY,
    text: nodes.map(nd => {
      // Short label: first letter + species
      const sp = nd.species || nd.id
      if (sp.length > 20) return sp.substring(0, 18) + '..'
      return sp
    }),
    textposition: 'top center',
    textfont: { color: c.text, size: 8 },
    marker: {
      size: nodeSizes,
      color: nodeColors,
      symbol: nodeSymbols,
      opacity: nodeOpacity,
      line: { color: nodeBorderColor, width: nodeBorderWidth },
    },
    hovertemplate: '%{customdata}<extra></extra>',
    customdata: hoverTexts,
    showlegend: false,
  }

  const layout = chartLayout({
    xaxis: { visible: false, showgrid: false, zeroline: false },
    yaxis: { visible: false, showgrid: false, zeroline: false, scaleanchor: 'x' },
    height: 600,
    margin: { t: 10, b: 10, l: 10, r: 10 },
    hovermode: 'closest',
  })

  Plotly.newPlot(networkChartEl.value, [...edgeTraces, nodeTrace], layout, {
    responsive: true,
    displayModeBar: false,
  })
}

// Watchers
watch([prevalenceThreshold, correlationThreshold, classFilter, fbmOverlay, communityMethod], debouncedFetch)
watch([colorMode, layoutMode, highlightedModule], () => {
  if (networkData.value) renderNetwork()
})

watch(dualMode, (val) => {
  if (val) fetchDualNetwork()
})

watch(() => props.active, (active) => {
  if (active && !networkData.value) fetchNetwork()
})

// --- External network functions ---

async function fetchExternalNetworks() {
  try {
    const [userRes, refRes] = await Promise.all([
      axios.get(`/api/data-explore/${props.projectId}/external-networks`),
      axios.get('/api/data-explore/reference-networks/list'),
    ])
    externalNetworks.value = userRes.data.map(n => ({ ...n, source: 'uploaded' }))
    referenceNetworks.value = refRes.data.map(n => ({ ...n, source: 'reference' }))
  } catch { /* ignore */ }
}

const allNetworks = computed(() => [
  ...referenceNetworks.value,
  ...externalNetworks.value,
])

async function uploadExternalNetwork(event) {
  const file = event.target.files?.[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    loadingExternal.value = true
    await axios.post(`/api/data-explore/${props.projectId}/external-networks`, formData)
    await fetchExternalNetworks()
  } catch (err) {
    error.value = err.response?.data?.detail || 'Upload failed'
  } finally {
    loadingExternal.value = false
    event.target.value = ''  // reset file input
  }
}

async function deleteExternalNetwork() {
  if (!selectedExternalId.value) return
  try {
    await axios.delete(`/api/data-explore/${props.projectId}/external-networks/${selectedExternalId.value}`)
    selectedExternalId.value = ''
    externalNetworkData.value = null
    await fetchExternalNetworks()
  } catch (err) {
    error.value = err.response?.data?.detail || 'Delete failed'
  }
}

async function loadExternalNetwork(id) {
  if (!id) { externalNetworkData.value = null; return }
  loadingExternal.value = true
  try {
    const net = allNetworks.value.find(n => n.id === id)
    const url = net?.source === 'reference'
      ? `/api/data-explore/reference-networks/${id}`
      : `/api/data-explore/${props.projectId}/external-networks/${id}`
    const { data } = await axios.get(url)
    externalNetworkData.value = data
    await nextTick()
    renderExternalNetwork()
  } catch (err) {
    error.value = err.response?.data?.detail || 'Load failed'
  } finally {
    loadingExternal.value = false
  }
}

async function renderExternalNetwork() {
  if (!externalNetworkData.value || !externalChartEl.value) return
  await ensurePlotly()
  const c = chartColors()
  const { nodes, edges } = externalNetworkData.value

  if (!nodes.length) return

  // Use fixed positions if provided, otherwise fall back to organic layout
  let nodeX, nodeY
  const hasPositions = nodes.every(n => n.x !== undefined && n.y !== undefined)
  if (hasPositions) {
    nodeX = nodes.map(n => n.x)
    nodeY = nodes.map(n => n.y)
  } else {
    // Convert to format expected by layoutOrganic
    const fakeEdges = edges.map(e => ({
      source: e.source, target: e.target,
      correlation: e.weight || 0.5,
    }))
    const layout = layoutOrganic(nodes, fakeEdges)
    nodeX = layout.x
    nodeY = layout.y
  }

  const idxMap = {}
  nodes.forEach((nd, i) => { idxMap[nd.id] = i })

  // Check which nodes are in the FBM signature
  const fbmFeatures = new Set()
  if (props.population.length > 0) {
    for (const ind of props.population) {
      const named = ind.named_features || {}
      for (const f of Object.keys(named)) fbmFeatures.add(f)
    }
  }

  // Edge traces
  const edgeTraces = []
  for (const edge of edges) {
    const i = idxMap[edge.source]
    const j = idxMap[edge.target]
    if (i === undefined || j === undefined) continue
    const isPositive = (edge.type === 'positive') || (edge.weight > 0)
    edgeTraces.push({
      type: 'scatter', mode: 'lines',
      x: [nodeX[i], nodeX[j], null],
      y: [nodeY[i], nodeY[j], null],
      line: {
        color: isPositive ? 'rgba(150,150,150,0.3)' : 'rgba(200,80,80,0.35)',
        width: Math.min(4, 0.5 + Math.abs(edge.weight || 0.5) * 3),
        dash: isPositive ? 'solid' : 'dash',
      },
      hoverinfo: 'skip',
      showlegend: false,
    })
  }

  // Node trace
  const nodeColors = nodes.map(nd => {
    if (fbmFeatures.has(nd.id)) return '#FFD700'  // gold for FBM species
    return nd.color || c.class0
  })
  const nodeSizes = nodes.map(nd => fbmFeatures.has(nd.id) ? 16 : 10)
  const nodeBorderWidth = nodes.map(nd => fbmFeatures.has(nd.id) ? 2.5 : 1)
  const nodeBorderColor = nodes.map(nd => fbmFeatures.has(nd.id) ? '#FF6F00' : c.text)

  const hoverTexts = nodes.map(nd => {
    let t = `<b>${nd.label || nd.id}</b>`
    if (nd.group) t += `<br>${nd.group}`
    if (fbmFeatures.has(nd.id)) t += `<br><b>In FBM signature</b>`
    return t
  })

  const nodeTrace = {
    type: 'scatter', mode: 'markers+text',
    x: nodeX, y: nodeY,
    text: nodes.map(nd => {
      const label = nd.label || nd.id
      return label.length > 20 ? label.substring(0, 18) + '..' : label
    }),
    textposition: 'top center',
    textfont: { color: c.text, size: 8 },
    marker: {
      size: nodeSizes,
      color: nodeColors,
      symbol: nodes.map(nd => fbmFeatures.has(nd.id) ? 'diamond' : 'circle'),
      opacity: 0.9,
      line: { color: nodeBorderColor, width: nodeBorderWidth },
    },
    hovertemplate: '%{customdata}<extra></extra>',
    customdata: hoverTexts,
    showlegend: false,
  }

  const extLayout = chartLayout({
    xaxis: { visible: false, showgrid: false, zeroline: false },
    yaxis: { visible: false, showgrid: false, zeroline: false, scaleanchor: 'x' },
    height: 600,
    margin: { t: 10, b: 10, l: 10, r: 10 },
    hovermode: 'closest',
  })

  Plotly.newPlot(externalChartEl.value, [...edgeTraces, nodeTrace], extLayout, {
    responsive: true, displayModeBar: false,
  })
}

// --- FBM Module Filter functions ---

async function applyFbmModuleFilter() {
  if (selectedModuleIds.value.length === 0 || !props.jobId) return

  fbmFilterLoading.value = true
  fbmFilterError.value = null
  fbmFilterResult.value = null
  fbmFilterShowCount.value = 20

  try {
    const { data } = await axios.post(
      `/api/data-explore/${props.projectId}/fbm-module-filter`,
      {
        job_id: props.jobId,
        module_ids: selectedModuleIds.value,
        min_prevalence_pct: prevalenceThreshold.value,
        correlation_threshold: correlationThreshold.value,
        community_method: communityMethod.value,
      }
    )
    fbmFilterResult.value = data
    emit('module-filter-applied', data)
  } catch (err) {
    fbmFilterError.value = err.response?.data?.detail || err.message
  } finally {
    fbmFilterLoading.value = false
  }
}

function clearFbmFilter() {
  fbmFilterResult.value = null
  fbmFilterError.value = null
  fbmFilterShowCount.value = 20
  emit('module-filter-applied', null)
}

function exportFilteredFbm() {
  if (!fbmFilterResult.value || !fbmFilterResult.value.filtered_models.length) return

  const models = fbmFilterResult.value.filtered_models
  const headers = ['rank', 'fit', 'k', 'language', 'data_type', 'module_coverage', 'module_coherence', 'features_in_module', 'total_features', 'features']
  const rows = models.map(m => [
    m.index + 1,
    m.fit != null ? m.fit : '',
    m.k,
    m.language || '',
    m.data_type || '',
    m.module_coverage,
    m.module_coherence,
    m.features_in_module,
    m.total_features,
    m.in_module_features.join(';'),
  ])

  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'fbm_module_filtered.csv'
  a.click()
  URL.revokeObjectURL(url)
}

watch(selectedExternalId, (id) => {
  if (id) loadExternalNetwork(id)
  else externalNetworkData.value = null
})

onMounted(() => {
  if (props.active) fetchNetwork()
  fetchExternalNetworks()
})
</script>

<style scoped>
.ecosystem-tab {
  padding: 0.5rem 0;
}

.eco-controls {
  margin-bottom: 1rem;
}

.eco-controls-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
}

.eco-control {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
  color: var(--text-secondary, #666);
}

.eco-control input[type="range"] {
  width: 100px;
}

.eco-control select {
  padding: 0.2rem 0.4rem;
  border: 1px solid var(--border, #ddd);
  border-radius: 4px;
  background: var(--bg-surface, #fff);
  color: var(--text, #333);
  font-size: 0.82rem;
}

.eco-value {
  font-weight: 600;
  min-width: 3rem;
  text-align: right;
  font-size: 0.85rem;
}

.eco-chart-wrap {
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  overflow: hidden;
}

.eco-chart {
  width: 100%;
  min-height: 600px;
}

.eco-stats-bar {
  display: flex;
  gap: 1.5rem;
  padding: 0.6rem 1rem;
  font-size: 0.85rem;
  color: var(--text-secondary, #666);
  border: 1px solid var(--border, #ddd);
  border-top: none;
  border-radius: 0 0 8px 8px;
  background: var(--bg-surface-alt, #fafafa);
}

.eco-bottom {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 1rem;
  margin-top: 1rem;
}

.eco-modules h4,
.eco-legend h4 {
  font-size: 0.9rem;
  margin: 0 0 0.5rem;
}

.eco-module-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.5rem;
  border-radius: 4px;
  font-size: 0.82rem;
  cursor: pointer;
  transition: background 0.15s;
}

.eco-module-item:hover {
  background: var(--bg-hover, #f0f0f0);
}

.eco-module-item.highlighted {
  background: var(--bg-active, #e0e8f0);
  font-weight: 600;
}

.eco-module-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}

.eco-module-size {
  color: var(--text-secondary, #999);
  font-size: 0.78rem;
}

.eco-module-phylum {
  color: var(--text-secondary, #999);
  font-size: 0.78rem;
  font-style: italic;
  margin-left: auto;
}

.eco-legend-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1rem;
}

.eco-legend-item {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.78rem;
}

.eco-legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.eco-legend-family {
  font-weight: 500;
}

.eco-legend-phylum {
  color: var(--text-secondary, #999);
  font-style: italic;
}

.loading {
  text-align: center;
  padding: 3rem;
  color: var(--text-secondary, #999);
}

.error-text {
  color: var(--danger, #e53935);
  padding: 1rem;
  text-align: center;
}

.eco-breadcrumb {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  margin-bottom: 0.5rem;
  background: var(--bg-surface-alt, #f0f4f8);
  border-radius: 6px;
  font-size: 0.85rem;
}
.eco-breadcrumb-label {
  color: var(--text-secondary);
  font-weight: 600;
}
.btn-zoom {
  margin-left: auto;
  font-size: 0.8rem;
  opacity: 0.5;
  transition: opacity 0.15s;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.1rem 0.3rem;
}
.btn-zoom:hover { opacity: 1; }

.eco-dual-wrap {
  margin-top: 1rem;
}
.eco-dual-header {
  text-align: center;
  padding: 0.5rem;
  font-size: 0.85rem;
  color: var(--text-secondary, #666);
}
.eco-dual-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}
.eco-dual-panel {
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  overflow: hidden;
}
.eco-dual-panel h4 {
  text-align: center;
  padding: 0.4rem;
  margin: 0;
  font-size: 0.85rem;
  background: var(--bg-surface-alt, #fafafa);
  border-bottom: 1px solid var(--border, #ddd);
}
.eco-chart-dual {
  min-height: 450px;
}

.eco-sankey-wrap {
  margin-top: 1rem;
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  padding: 0.75rem;
}
.eco-sankey-wrap h4 {
  margin: 0 0 0.25rem;
  font-size: 0.9rem;
}
.eco-sankey-desc {
  font-size: 0.82rem;
  color: var(--text-secondary, #666);
  margin: 0 0 0.5rem;
}
.eco-chart-sankey {
  min-height: 400px;
}

.eco-external-section {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border, #ddd);
}
.eco-external-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.eco-external-header h4 {
  margin: 0;
  font-size: 0.9rem;
}
.eco-external-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.eco-external-select {
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border, #ddd);
  border-radius: 4px;
  background: var(--bg-surface, #fff);
  color: var(--text, #333);
  font-size: 0.82rem;
}
.eco-external-upload {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.6rem;
  font-size: 0.82rem;
  border: 1px solid var(--border, #ddd);
  border-radius: 4px;
  background: var(--bg-surface, #fff);
  color: var(--text, #333);
  transition: background 0.15s;
}
.eco-external-upload:hover {
  background: var(--bg-hover, #f0f0f0);
}
.btn-danger-outline {
  padding: 0.25rem 0.6rem;
  font-size: 0.82rem;
  border: 1px solid var(--danger, #e53935);
  border-radius: 4px;
  background: transparent;
  color: var(--danger, #e53935);
  cursor: pointer;
}
.btn-danger-outline:hover {
  background: var(--danger, #e53935);
  color: white;
}

/* FBM Module Filter */
.eco-fbm-filter-section {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border, #ddd);
}
.eco-fbm-filter-section h4 {
  margin: 0 0 0.25rem;
  font-size: 0.9rem;
}
.eco-fbm-filter-desc {
  font-size: 0.82rem;
  color: var(--text-secondary, #666);
  margin: 0 0 0.75rem;
}
.eco-fbm-filter-controls {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.eco-module-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
}
.eco-module-check {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.82rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border, #ddd);
  border-radius: 4px;
  transition: background 0.15s;
}
.eco-module-check:hover {
  background: var(--bg-hover, #f0f0f0);
}
.eco-fbm-filter-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.eco-fbm-filter-results {
  margin-top: 1rem;
}
.eco-fbm-filter-summary {
  display: flex;
  gap: 1.5rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.85rem;
  color: var(--text-secondary, #666);
  background: var(--bg-surface-alt, #fafafa);
  border: 1px solid var(--border, #ddd);
  border-radius: 6px;
  margin-bottom: 0.75rem;
}
.eco-fbm-module-species {
  margin-left: auto;
}
.eco-fbm-table-wrap {
  overflow-x: auto;
  margin-bottom: 0.75rem;
}
.eco-fbm-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.eco-fbm-table th,
.eco-fbm-table td {
  text-align: left;
  padding: 0.4rem 0.6rem;
  border-bottom: 1px solid var(--border, #eee);
}
.eco-fbm-table th {
  font-weight: 600;
  color: var(--text-secondary, #666);
  background: var(--bg-surface-alt, #fafafa);
  position: sticky;
  top: 0;
}
.eco-fbm-table tr:hover {
  background: var(--bg-hover, #f5f5f5);
}
.eco-fbm-bar-wrap {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  width: 100%;
}
.eco-fbm-bar {
  display: inline-block;
  height: 14px;
  background: var(--primary, #1976d2);
  border-radius: 3px;
  opacity: 0.7;
  min-width: 2px;
}
.eco-fbm-bar-label {
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
}
.eco-fbm-show-more {
  margin-top: 0.5rem;
}
.eco-fbm-export {
  margin-top: 0.5rem;
}

@media (max-width: 768px) {
  .eco-bottom {
    grid-template-columns: 1fr;
  }
  .eco-controls-row {
    flex-direction: column;
    align-items: flex-start;
  }
  .eco-dual-grid {
    grid-template-columns: 1fr;
  }
}
</style>
