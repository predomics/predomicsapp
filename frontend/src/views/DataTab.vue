<template>
  <div class="data-tab">
    <!-- Summary stats bar -->
    <div class="summary-bar" v-if="summary">
      <div class="stat-card">
        <div class="stat-value">{{ summary.n_features }}</div>
        <div class="stat-label">{{ $t('data.features') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ summary.n_samples }}</div>
        <div class="stat-label">{{ $t('data.samples') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ summary.n_classes }}</div>
        <div class="stat-label">{{ $t('data.classes') }}</div>
      </div>
      <div class="stat-card" v-if="featureStats">
        <div class="stat-value accent">{{ featureStats.selected_count }}</div>
        <div class="stat-label">{{ $t('data.selected') }}</div>
      </div>
    </div>

    <!-- Two-panel layout -->
    <div class="data-panels">
      <!-- LEFT PANEL -->
      <aside class="left-panel">
        <!-- Dataset slots (2x2) -->
        <section class="section">
          <div class="section-title">{{ $t('data.datasets') }}</div>
          <div class="ds-grid">
            <div v-for="slot in dsSlots" :key="slot.role" class="ds-slot" :class="{ ok: slot.ds, missing: !slot.ds && slot.required, optional: !slot.required && !slot.ds }">
              <span class="ds-role">{{ slot.label }}</span>
              <span v-if="slot.ds" class="ds-file">{{ slot.ds.filename }}
                <button class="ds-clear" @click="clearSlot(slot.role)" title="Remove"><SvgIcon name="x" :size="12" /></button>
              </span>
              <template v-else>
                <select v-if="libraryDatasets.length > 0" class="ds-picker" @change="e => pickFromLibrary(e, slot.role)">
                  <option value="">{{ $t('data.pickFromLibrary') }}</option>
                  <option v-for="d in libraryDatasets" :key="d.id" :value="d.id">{{ d.name }}</option>
                </select>
                <label :class="['ds-upload', { 'ds-optional': !slot.required }]">{{ $t('data.upload') }}<input type="file" accept=".tsv,.csv,.txt" @change="e => uploadFile(e, slot.role)" /></label>
              </template>
            </div>
            <!-- Metadata upload slot -->
            <div class="ds-slot" :class="{ ok: metadataDs, optional: !metadataDs }">
              <span class="ds-role">{{ $t('data.metadata') }}</span>
              <span v-if="metadataDs" class="ds-file">{{ metadataDs.filename }}
                <button class="ds-clear" @click="clearSlot('metadata')" title="Remove"><SvgIcon name="x" :size="12" /></button>
              </span>
              <template v-else>
                <label class="ds-upload ds-optional">{{ $t('data.metadataUpload') }}<input type="file" accept=".tsv,.csv,.txt" @change="e => uploadMetadata(e)" /></label>
              </template>
              <div v-if="metadataDs && metadataColumns.length > 0" class="metadata-y-select">
                <label>{{ $t('data.selectYVariable') }}
                  <select v-model="selectedYColumn" @change="onYColumnSelected">
                    <option value="">--</option>
                    <option v-for="col in metadataColumns" :key="col" :value="col">{{ col }}</option>
                  </select>
                </label>
                <span v-if="selectedYColumn" class="regression-badge">{{ $t('data.regressionMode') }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- Data options -->
        <section class="section">
          <div class="section-title">{{ $t('data.dataOptions') }}</div>
          <label class="inline-check">
            <input type="checkbox" v-model="cfg.data.features_in_rows" />
            {{ $t('data.featuresInRows') }}
          </label>
          <label class="inline-check">
            <input type="checkbox" v-model="cfg.data.inverse_classes" />
            {{ $t('data.inverseClasses') }}
          </label>
          <div class="form-row">
            <label>{{ $t('data.holdoutRatio') }}
              <input type="number" v-model.number="cfg.data.holdout_ratio" min="0" max="1" step="0.05" />
            </label>
          </div>
          <div class="form-col" v-if="summary && summary.class_labels">
            <label>{{ $t('data.classLabels') }}</label>
            <div class="class-labels-row">
              <div
                v-for="(cls, i) in summary.class_labels"
                :key="i"
                class="class-label-chip"
                :class="{ target: isTargetClass(i) }"
              >
                <span class="class-index">{{ cls }}</span>
                <input
                  type="text"
                  :value="classDisplayName(i, cls)"
                  @input="e => setClassLabel(i, e.target.value)"
                  @blur="saveClassNames"
                  class="class-label-input"
                  :placeholder="$t('data.className')"
                />
                <span v-if="isTargetClass(i)" class="target-badge">{{ $t('data.target') }}</span>
                <span v-else class="ref-badge">{{ $t('data.reference') }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- Feature filtering -->
        <section class="section">
          <div class="section-title">{{ $t('data.featureFiltering') }}</div>
          <div class="form-col">
            <label>{{ $t('data.selectionMethod') }}
              <select v-model="cfg.data.feature_selection_method" @change="debouncedRefresh">
                <option value="wilcoxon">{{ $t('data.wilcoxon') }}</option>
                <option value="studentt">{{ $t('data.tTest') }}</option>
                <option value="bayesian_fisher">{{ $t('data.bayesianFisher') }}</option>
                <option value="none">{{ $t('data.none') }}</option>
              </select>
            </label>
            <label>{{ $t('data.minPrevalence') }}
              <input type="number" v-model.number="cfg.data.feature_minimal_prevalence_pct" min="0" max="100" @change="debouncedRefresh" />
            </label>
            <label>{{ $t('data.maxPValue') }}
              <input type="number" v-model.number="cfg.data.feature_maximal_adj_pvalue" min="0" max="1" step="0.01" @change="debouncedRefresh" />
            </label>
            <label>{{ $t('data.minFeatureValue') }}
              <input type="number" v-model.number="cfg.data.feature_minimal_feature_value" min="0" step="0.0001" @change="debouncedRefresh" />
            </label>
          </div>
        </section>

        <!-- Feature table -->
        <section class="section" v-if="featureStats && featureStats.features.length > 0">
          <div class="section-title">
            {{ $t('data.features') }}
            <span class="badge">{{ featureStats.selected_count }}/{{ featureStats.n_features }}</span>
          </div>
          <div class="feature-table-scroll">
            <table class="feature-table">
              <thead>
                <tr>
                  <th class="sortable" @click="sortBy('name')">{{ $t('data.name') }} {{ sortIcon('name') }}</th>
                  <th class="sortable" @click="sortBy('significance')">{{ $t('data.significance') }} {{ sortIcon('significance') }}</th>
                  <th class="sortable" @click="sortBy('prevalence')">{{ $t('data.prevalenceShort') }} {{ sortIcon('prevalence') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="f in paginatedFeatures"
                  :key="f.index"
                  :class="[featureRowClass(f), { 'selected-row': plotFeatureNames.includes(f.name) }]"
                  @click="toggleFeature(f)"
                >
                  <td class="feature-name-cell" :title="mspAnnotations[f.name]?.species || ''">
                    {{ f.name }}
                    <span v-if="mspAnnotations[f.name]?.species" class="species-tag">{{ mspAnnotations[f.name].species.split(' ').length >= 2 ? mspAnnotations[f.name].species.split(' ')[0][0] + '. ' + mspAnnotations[f.name].species.split(' ').slice(1).join(' ') : mspAnnotations[f.name].species }}</span>
                  </td>
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
        <div class="viz-header">
          <nav class="viz-tabs">
            <button :class="{ active: vizTab === 'prevalence' }" @click="vizTab = 'prevalence'">{{ $t('data.prevalence') }}</button>
            <button :class="{ active: vizTab === 'abundance' }" @click="vizTab = 'abundance'">{{ $t('data.abundance') }}</button>
            <button :class="{ active: vizTab === 'barcode' }" @click="vizTab = 'barcode'">{{ $t('data.barcode') }}</button>
            <button :class="{ active: vizTab === 'volcano' }" @click="vizTab = 'volcano'">{{ $t('data.volcano') }}</button>
            <button :class="{ active: vizTab === 'pcoa' }" @click="vizTab = 'pcoa'">{{ $t('data.pcoa') }}</button>
          </nav>
          <label class="topn-control" v-if="featureStats">
            {{ $t('data.top') }}
            <input type="number" v-model.number="topN" :min="1" :max="maxTopN" step="1" class="topn-input" />
            / {{ featureStats.selected_count }} {{ $t('data.features') }}
          </label>
        </div>

        <!-- Prevalence plot -->
        <section class="section viz-section" v-if="vizTab === 'prevalence'">
          <div ref="prevalenceChartEl" class="plotly-chart plotly-chart-tall"></div>
          <p v-if="!featureStats" class="info-text">Upload datasets and run filtering to see prevalence.</p>
        </section>

        <!-- Abundance by class -->
        <section class="section viz-section" v-if="vizTab === 'abundance'">
          <div class="viz-controls">
            <label class="toggle-label">
              <input type="checkbox" v-model="abundanceLogScale" @change="renderAbundanceChart()" />
              Log scale
            </label>
          </div>
          <div ref="abundanceChartEl" class="plotly-chart plotly-chart-tall"></div>
          <p v-if="!featureStats" class="info-text">Upload datasets and run filtering to see abundance.</p>
        </section>

        <!-- Barcode heatmap -->
        <section class="section viz-section" v-if="vizTab === 'barcode'">
          <div ref="barcodeChartEl" class="plotly-chart plotly-chart-tall"></div>
          <p v-if="!featureStats" class="info-text">Upload datasets and run filtering to see barcode.</p>
        </section>

        <!-- Volcano plot -->
        <section class="section viz-section" v-if="vizTab === 'volcano'">
          <div ref="volcanoChartEl" class="plotly-chart plotly-chart-tall"></div>
          <p v-if="!featureStats" class="info-text">Upload datasets and run filtering to see the volcano plot.</p>
        </section>

        <!-- PCoA -->
        <section class="section viz-section" v-if="vizTab === 'pcoa'">
          <div class="pcoa-controls">
            <label class="pcoa-control-item">
              <span>{{ $t('data.ordinationMethod') }}</span>
              <select v-model="pcoaMethod" @change="loadPcoa">
                <option value="pcoa">PCoA</option>
                <option value="tsne">t-SNE</option>
                <option value="umap">UMAP</option>
              </select>
            </label>
            <label class="pcoa-control-item">
              <span>{{ $t('data.pcoaMetric') }}</span>
              <select v-model="pcoaMetric" @change="loadPcoa">
                <option value="braycurtis">Bray-Curtis</option>
                <option value="euclidean">{{ $t('data.euclidean') }}</option>
                <option value="jaccard">Jaccard</option>
                <option value="cosine">{{ $t('data.cosine') }}</option>
              </select>
            </label>
            <label v-if="pcoaMethod === 'tsne'" class="pcoa-control-item">
              <span>{{ $t('data.perplexity') }}</span>
              <input type="number" v-model.number="tsnePerplexity" min="5" max="100" step="5" @change="loadPcoa" class="param-input" />
            </label>
            <label v-if="pcoaMethod === 'umap'" class="pcoa-control-item">
              <span>{{ $t('data.nNeighbors') }}</span>
              <input type="number" v-model.number="umapNeighbors" min="2" max="100" step="1" @change="loadPcoa" class="param-input" />
            </label>
            <label v-if="pcoaMethod === 'umap'" class="pcoa-control-item">
              <span>{{ $t('data.minDist') }}</span>
              <input type="number" v-model.number="umapMinDist" min="0" max="1" step="0.05" @change="loadPcoa" class="param-input" />
            </label>
            <label class="pcoa-control-item">
              <span>{{ $t('data.pcoaFeatures') }}</span>
              <select v-model="pcoaFbmJobId" @change="onFbmJobChange">
                <option value="">{{ $t('data.allFeatures') }}</option>
                <option v-for="j in pcoaJobs" :key="j.id" :value="j.id">{{ j.label }}</option>
              </select>
            </label>
            <label class="toggle-label">
              <input type="checkbox" v-model="pcoaShowEllipses" @change="renderPcoaChart" />
              {{ $t('data.ellipses') }}
            </label>
            <div class="pcoa-dim-toggle">
              <button :class="{ active: pcoaDim === '2d' }" @click="pcoaDim = '2d'">2D</button>
              <button :class="{ active: pcoaDim === '3d' }" @click="pcoaDim = '3d'">3D</button>
            </div>
          </div>
          <div v-if="pcoaData" class="pcoa-stats-row">
            <span class="pcoa-info">
              {{ pcoaData.n_samples }} {{ $t('data.samples').toLowerCase() }}
              &middot; {{ pcoaData.n_features_used }} {{ $t('data.features').toLowerCase() }}
              &middot; {{ pcoaData.metric }}
            </span>
            <span v-if="pcoaData.permanova" class="pcoa-permanova" :class="{ significant: pcoaData.permanova.p_value < 0.05 }">
              PERMANOVA: F={{ pcoaData.permanova.F }}, R&sup2;={{ pcoaData.permanova.R2 }},
              p={{ pcoaData.permanova.p_value < 0.001 ? '< 0.001' : pcoaData.permanova.p_value }}
              <span v-if="pcoaData.permanova.p_value < 0.001" class="sig-star">***</span>
              <span v-else-if="pcoaData.permanova.p_value < 0.01" class="sig-star">**</span>
              <span v-else-if="pcoaData.permanova.p_value < 0.05" class="sig-star">*</span>
            </span>
          </div>
          <div ref="pcoaChartEl" class="plotly-chart plotly-chart-pcoa"></div>
          <div v-if="loadingPcoa" class="loading">{{ $t('data.loadingPcoa') }}</div>
          <p v-if="!hasTrainData && !loadingPcoa" class="info-text">Upload datasets to compute PCoA.</p>
        </section>
      </main>
    </div>

    <div v-if="loading" class="loading">{{ $t('data.loadingData') }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import { useDatasetStore } from '../stores/dataset'
import { useConfigStore } from '../stores/config'
import { useThemeStore } from '../stores/theme'
import { useChartTheme } from '../composables/useChartTheme'
import axios from 'axios'
import Plotly from 'plotly.js-dist-min'
import { useI18n } from 'vue-i18n'
import SvgIcon from '../components/SvgIcon.vue'

const route = useRoute()
const store = useProjectStore()
const dsStore = useDatasetStore()
const configStore = useConfigStore()
const themeStore = useThemeStore()
const { chartColors, chartLayout, featureLabel: _featureLabel } = useChartTheme()
const cfg = configStore.form
const { t } = useI18n()

// State
const loading = ref(false)
const summary = ref(null)
const featureStats = ref(null)
const abundanceData = ref([])
const barcodeData = ref(null)
const mspAnnotations = ref({})
const vizTab = ref('prevalence')
const pcoaData = ref(null)
const loadingPcoa = ref(false)
const pcoaMethod = ref('pcoa')
const pcoaMetric = ref('braycurtis')
const pcoaDim = ref('2d')
const pcoaShowEllipses = ref(true)
const pcoaFbmJobId = ref('')
const pcoaJobs = ref([])
const pcoaFbmFeatures = ref([])
const tsnePerplexity = ref(30)
const umapNeighbors = ref(15)
const umapMinDist = ref(0.1)

// Top N features control — shared across all plots
const abundanceLogScale = ref(false)
const topN = ref(50)
const maxTopN = computed(() => featureStats.value?.selected_count || 50)

// Computed: top N selected features sorted by significance (single source for all plots)
const plotFeatureNames = computed(() => {
  if (!featureStats.value?.features) return []
  return featureStats.value.features
    .filter(f => f.selected)
    .sort((a, b) => (a.significance || 1) - (b.significance || 1))
    .slice(0, topN.value)
    .map(f => f.name)
})

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
const pcoaChartEl = ref(null)

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
const clinicalDs = computed(() => findFile('clinical'))
const metadataDs = computed(() => findFile('metadata'))
const dsSlots = computed(() => [
  { role: 'xtrain', label: 'X train', ds: xTrainDs.value, required: true },
  { role: 'ytrain', label: 'y train', ds: yTrainDs.value, required: true },
  { role: 'xtest', label: 'X test', ds: xTestDs.value, required: false },
  { role: 'ytest', label: 'y test', ds: yTestDs.value, required: false },
  { role: 'clinical', label: 'Clinical metadata', ds: clinicalDs.value, required: false },
])
const hasTrainData = computed(() => xTrainDs.value && yTrainDs.value)

// Metadata column selection for regression
const metadataColumns = ref([])
const selectedYColumn = ref(null)

onMounted(() => {
  dsStore.fetchDatasets()
  // Load metadata columns if metadata file already present
  nextTick(() => { if (metadataDs.value) fetchMetadataColumns() })
})

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
    if (role === 'metadata') {
      metadataColumns.value = []
      selectedYColumn.value = null
    }
  } catch (e) {
    alert('Unassign failed: ' + (e.response?.data?.detail || e.message))
  }
}

async function uploadMetadata(event) {
  const file = event.target.files[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    await axios.post(`/api/projects/${projectId.value}/datasets`, formData, {
      params: { role: 'metadata' },
    })
    await store.fetchOne(projectId.value)
    await dsStore.fetchDatasets()
    await fetchMetadataColumns()
  } catch (e) {
    alert('Upload failed: ' + (e.response?.data?.detail || e.message))
  }
}

async function fetchMetadataColumns() {
  const md = metadataDs.value
  if (!md) { metadataColumns.value = []; return }
  try {
    const { data } = await axios.get(
      `/api/projects/${projectId.value}/datasets/${md.datasetId}/files/${md.id}/columns`
    )
    metadataColumns.value = data.numeric_columns || []
  } catch {
    metadataColumns.value = []
  }
}

async function onYColumnSelected() {
  if (!selectedYColumn.value || !metadataDs.value) return
  try {
    await axios.post(
      `/api/projects/${projectId.value}/datasets/${metadataDs.value.datasetId}/files/${metadataDs.value.id}/extract-y`,
      { column: selectedYColumn.value }
    )
    await store.fetchOne(projectId.value)
    loadAll()
  } catch (e) {
    alert('Failed to set y variable: ' + (e.response?.data?.detail || e.message))
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

// --- Class label editing ---
function setClassLabel(index, value) {
  if (!cfg.data.classes) {
    cfg.data.classes = summary.value?.class_labels ? [...summary.value.class_labels] : []
  }
  cfg.data.classes[index] = value
}

function classDisplayName(index, rawLabel) {
  // Show saved name from project DB, fall back to config, fall back to raw label
  const saved = store.current?.class_names
  if (saved && saved[rawLabel]) return saved[rawLabel]
  if (cfg.data.classes && cfg.data.classes[index]) return cfg.data.classes[index]
  return ''
}

function isTargetClass(index) {
  const labels = summary.value?.class_labels || []
  // By default, last class (typically "1") is the target
  // If inverse_classes is on, first class (typically "0") becomes the target
  if (cfg.data.inverse_classes) return index === 0
  return index === labels.length - 1
}

async function saveClassNames() {
  if (!summary.value?.class_labels) return
  const names = {}
  summary.value.class_labels.forEach((cls, i) => {
    const val = cfg.data.classes?.[i]
    if (val && val !== cls) names[cls] = val
  })
  try {
    await store.updateProject(projectId.value, { class_names: names })
  } catch (e) {
    console.error('Failed to save class names:', e)
  }
}

// --- Theme colors (from shared composable) ---
// chartColors() and chartLayout() imported from useChartTheme

// --- API calls ---
async function loadSummary() {
  if (!hasTrainData.value) return
  try {
    const { data } = await axios.get(`/api/data-explore/${projectId.value}/summary`)
    summary.value = data
    // Restore saved class names into config
    const saved = store.current?.class_names
    if (saved && data.class_labels) {
      cfg.data.classes = data.class_labels.map(cls => saved[cls] || cls)
    }
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
    // Set topN to min(selected_count, 50)
    topN.value = Math.min(data.selected_count || 50, 50)
  } catch (e) {
    console.error('Failed to load feature stats:', e)
  }
}

async function loadAbundance() {
  const feats = plotFeatureNames.value
  if (feats.length === 0 || !hasTrainData.value) return
  try {
    const { data } = await axios.get(`/api/data-explore/${projectId.value}/feature-abundance`, {
      params: { features: feats.join(',') },
    })
    abundanceData.value = data.features || []
  } catch (e) {
    console.error('Failed to load abundance:', e)
  }
}

async function loadMspAnnotations() {
  if (!featureStats.value?.features) return
  const names = featureStats.value.features.map(f => f.name).filter(n => n.startsWith('msp_'))
  if (names.length === 0) return
  try {
    const { data } = await axios.post('/api/data-explore/msp-annotations', { features: names })
    mspAnnotations.value = data.annotations || {}
  } catch (e) {
    console.error('Failed to load MSP annotations:', e)
  }
}

/** Get a short display label for a feature: "msp_0069 P. vulgatus" */
function featureLabel(name) {
  return _featureLabel(name, mspAnnotations.value)
}

async function loadBarcodeData() {
  const feats = plotFeatureNames.value
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

async function loadPcoaJobs() {
  try {
    const { data } = await axios.get(`/api/analysis/${projectId.value}/jobs`)
    pcoaJobs.value = (data || [])
      .filter(j => j.status === 'completed')
      .map(j => ({ id: j.job_id, label: j.name || `Job ${j.job_id.slice(0, 8)}` }))
  } catch { pcoaJobs.value = [] }
}

async function onFbmJobChange() {
  if (!pcoaFbmJobId.value) {
    pcoaFbmFeatures.value = []
    loadPcoa()
    return
  }
  try {
    const { data } = await axios.get(`/api/analysis/${projectId.value}/jobs/${pcoaFbmJobId.value}/results`)
    const pop = data?.population || []
    // FBM filter: models within 95% CI of best fit
    const bestFit = pop[0]?.metrics?.fit
    if (bestFit == null) { pcoaFbmFeatures.value = []; loadPcoa(); return }
    const n = data?.sample_count || pop.length
    const se = Math.sqrt(bestFit * (1 - bestFit) / n)
    const threshold = bestFit - 1.96 * se
    const fbm = pop.filter(ind => ind.metrics?.fit >= threshold)
    // Collect unique feature names across all FBM models
    const nameSet = new Set()
    for (const ind of fbm) {
      if (ind.named_features) {
        Object.keys(ind.named_features).forEach(f => nameSet.add(f))
      }
    }
    pcoaFbmFeatures.value = [...nameSet]
    loadPcoa()
  } catch (e) {
    console.error('Failed to load FBM features:', e)
    pcoaFbmFeatures.value = []
    loadPcoa()
  }
}

async function loadPcoa() {
  if (!hasTrainData.value) return
  loadingPcoa.value = true
  try {
    const params = { method: pcoaMethod.value, metric: pcoaMetric.value }
    if (pcoaMethod.value === 'tsne') {
      params.perplexity = tsnePerplexity.value
    } else if (pcoaMethod.value === 'umap') {
      params.n_neighbors = umapNeighbors.value
      params.min_dist = umapMinDist.value
    }
    if (pcoaDim.value === '3d') params.n_components = 3
    if (pcoaFbmFeatures.value.length > 0) {
      params.features = pcoaFbmFeatures.value.join(',')
    }
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

async function loadAll() {
  if (!hasTrainData.value) return
  loading.value = true
  try {
    await loadSummary()
    await loadFeatureStats()
    await Promise.all([loadAbundance(), loadBarcodeData(), loadMspAnnotations()])
    await nextTick()
    renderCurrentViz()
  } finally {
    loading.value = false
  }
}

// Debounced refresh for filter changes
let _refreshTimer = null
function debouncedRefresh() {
  clearTimeout(_refreshTimer)
  _refreshTimer = setTimeout(async () => {
    await loadFeatureStats()
    await Promise.all([loadAbundance(), loadBarcodeData()])
    renderCurrentViz()
  }, 500)
}

// --- Chart renderers ---
async function renderPrevalenceChart() {
  await nextTick()
  if (!prevalenceChartEl.value || !featureStats.value) return
  const c = chartColors()

  const names = plotFeatureNames.value
  if (names.length === 0) return
  const featureMap = Object.fromEntries(featureStats.value.features.map(f => [f.name, f]))
  const features = names.map(n => featureMap[n]).filter(Boolean)

  const nFeat = features.length
  const barH = 0.35  // half-height of overall bar

  // ggplot-like: numeric y-axis with shapes for equal spacing
  const shapes = []
  const annotations = []

  for (let i = 0; i < nFeat; i++) {
    const f = features[i]
    // Overall prevalence bar (faint background)
    shapes.push({
      type: 'rect', x0: 0, x1: f.prevalence || 0,
      y0: i - barH, y1: i + barH,
      fillcolor: c.dimmed + '55', line: { width: 0 },
    })
    // Significance stars
    if (f.significance != null && f.significance < 0.05) {
      annotations.push({
        x: Math.max(f.prevalence_0 || 0, f.prevalence_1 || 0, f.prevalence || 0) + 3,
        y: i,
        text: f.significance < 0.001 ? '***' : f.significance < 0.01 ? '**' : '*',
        showarrow: false,
        font: { color: c.danger, size: 12, family: 'monospace' },
      })
    }
  }

  // Class-specific markers as scatter traces
  const traces = [
    {
      type: 'scatter', mode: 'markers', name: 'Class 0',
      x: features.map(f => f.prevalence_0),
      y: features.map((_, i) => i),
      marker: { color: c.class0, size: 8, symbol: 'circle' },
    },
    {
      type: 'scatter', mode: 'markers', name: 'Class 1',
      x: features.map(f => f.prevalence_1),
      y: features.map((_, i) => i),
      marker: { color: c.class1, size: 8, symbol: 'diamond' },
    },
  ]

  Plotly.newPlot(prevalenceChartEl.value, traces, chartLayout({
    xaxis: { title: { text: 'Prevalence (%)', font: { color: c.text } }, range: [0, 105], gridcolor: c.grid, color: c.text },
    yaxis: {
      tickvals: features.map((_, i) => i), ticktext: features.map(f => featureLabel(f.name)),
      range: [nFeat - 0.5, -0.5], automargin: true, color: c.text, fixedrange: true,
    },
    height: Math.max(400, nFeat * 22),
    shapes,
    annotations,
    legend: { orientation: 'h', y: 1.05, font: { color: c.text } },
    margin: { t: 30, b: 50, l: 180, r: 40 },
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
  const clsFills = classKeys.map(k => k === '0' ? c.class0Alpha : c.class1Alpha)

  // ggplot-like layout: numeric y for equal spacing, grouped boxes per class
  const boxH = 0.18 / nCls         // half-height of one box (thin)
  const offsets = nCls === 2 ? [-0.14, 0.14] : [0]

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
      const rawStats = features[i].classes[cls]
      if (!rawStats) continue
      // Replace zeros with a value slightly below the mean for log scale
      const logFloor = (rawStats.mean || 1e-6) / 10
      const stats = abundanceLogScale.value
        ? { ...rawStats, min: rawStats.min || logFloor, q1: rawStats.q1 || logFloor, median: rawStats.median || logFloor, q3: rawStats.q3 || logFloor, max: rawStats.max || logFloor }
        : rawStats
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
    xaxis: {
      title: { text: abundanceLogScale.value ? 'Abundance (log)' : 'Abundance', font: { color: c.text } },
      type: abundanceLogScale.value ? 'log' : 'linear',
      gridcolor: c.grid, color: c.text,
    },
    yaxis: {
      tickvals: features.map((_, i) => i), ticktext: features.map(f => featureLabel(f.name)),
      range: [nFeat - 0.5, -0.5], automargin: true, color: c.text, fixedrange: true,
    },
    height: Math.max(400, nFeat * 22),
    shapes,
    annotations,
    legend: { orientation: 'h', y: 1.05, font: { color: c.text } },
    margin: { t: 30, b: 50, l: 180, r: 40 },
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

  if (!isFinite(lo)) lo = -10
  if (!isFinite(hi)) hi = 0
  const floor = lo - 1
  const z = zLog.map(row => row.map(v => v === null ? floor : v))

  // Color scale
  const span = hi - floor
  const whiteEnd = Math.max(0.01, (lo - floor) / span)
  const dataColors = ['#00bfff', '#0000ff', '#00cd00', '#ffff00', '#ffa500', '#ff0000', '#ee4000', '#8b0000']
  const zeroBg = c.paper  // transparent-like: match plot background so zeros fade away
  const colorscale = [[0, zeroBg], [whiteEnd, zeroBg]]
  for (let i = 0; i < dataColors.length; i++) {
    colorscale.push([whiteEnd + (1 - whiteEnd) * (i + 1) / dataColors.length, dataColors[i]])
  }

  // Colorbar ticks in original scale
  const nTicks = 5
  const tickVals = [], tickTexts = []
  for (let i = 0; i <= nTicks; i++) {
    const lv = lo + (hi - lo) * i / nTicks
    tickVals.push(lv)
    tickTexts.push(Math.pow(4, lv).toExponential(1))
  }

  // Split data by class for faceted panels
  const boundaries = [0, ...d.class_boundaries, d.sample_names.length]
  const nCls = d.class_labels.length
  const traces = []
  const annotations = []

  // Compute facet x-axis domains with small gap between panels
  const gap = 0.03
  const totalSpace = 1 - gap * (nCls - 1) - 0.06 // reserve space for colorbar
  const classSizes = []
  for (let ci = 0; ci < nCls; ci++) {
    classSizes.push(boundaries[ci + 1] - boundaries[ci])
  }
  const totalSamples = classSizes.reduce((a, b) => a + b, 0)

  let xPos = 0
  const domains = []
  for (let ci = 0; ci < nCls; ci++) {
    const w = totalSpace * (classSizes[ci] / totalSamples)
    domains.push([xPos, xPos + w])
    xPos += w + gap
  }

  for (let ci = 0; ci < nCls; ci++) {
    const start = boundaries[ci]
    const end = boundaries[ci + 1]
    const classSamples = d.sample_names.slice(start, end)
    const classZ = z.map(row => row.slice(start, end))
    const classRaw = d.matrix.map(row => row.slice(start, end))

    const xRef = ci === 0 ? 'x' : `x${ci + 1}`
    const yRef = ci === 0 ? 'y' : `y${ci + 1}`

    traces.push({
      z: classZ,
      x: classSamples,
      y: d.feature_names.map(n => featureLabel(n)),
      type: 'heatmap',
      colorscale,
      zmin: floor, zmax: hi,
      xaxis: xRef,
      yaxis: yRef,
      showscale: ci === nCls - 1,
      colorbar: ci === nCls - 1 ? {
        title: { text: 'Value (log\u2084)', font: { color: c.text, size: 10 } },
        tickvals: tickVals, ticktext: tickTexts,
        tickfont: { color: c.text, size: 9 },
        len: 0.8, thickness: 12,
      } : undefined,
      hovertemplate: classRaw.map((row, ri) =>
        row.map((v, si) =>
          `Feature: ${d.feature_names[ri]}<br>Sample: ${classSamples[si]}<br>Value: ${v.toExponential(4)}<extra></extra>`
        )
      ),
    })

    // Facet title annotation (class label above each panel)
    annotations.push({
      text: `<b>Class ${d.class_labels[ci]}</b> (n=${classSizes[ci]})`,
      xref: 'paper', yref: 'paper',
      x: (domains[ci][0] + domains[ci][1]) / 2,
      y: 1.04,
      showarrow: false,
      font: { color: c.text, size: 12 },
    })
  }

  // Build layout with multiple x/y axes
  const layout = {
    height: Math.max(300, d.feature_names.length * 20 + 80),
    margin: { t: 40, b: 30, l: 120, r: 60 },
    paper_bgcolor: c.paper,
    plot_bgcolor: c.paper,
    font: { family: 'system-ui, sans-serif', size: 12, color: c.text },
    annotations,
  }

  for (let ci = 0; ci < nCls; ci++) {
    const xKey = ci === 0 ? 'xaxis' : `xaxis${ci + 1}`
    const yKey = ci === 0 ? 'yaxis' : `yaxis${ci + 1}`

    layout[xKey] = {
      domain: domains[ci],
      showticklabels: false,
      color: c.text,
      gridcolor: c.grid,
    }
    layout[yKey] = {
      anchor: ci === 0 ? 'x' : `x${ci + 1}`,
      automargin: true,
      color: c.text,
      showticklabels: ci === 0, // only show feature names on leftmost panel
    }
  }

  Plotly.newPlot(barcodeChartEl.value, traces, layout, { responsive: true, displayModeBar: true })
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

async function renderPcoaChart() {
  await nextTick()
  if (!pcoaChartEl.value || !pcoaData.value) return
  const c = chartColors()
  const d = pcoaData.value
  const ve = d.variance_explained
  const method = d.method || pcoaMethod.value

  // Build axis labels based on method
  const axisLabel = (dim) => {
    if (method === 'pcoa' && ve) return `PCo${dim} (${ve[dim - 1]}%)`
    if (method === 'tsne') return `t-SNE ${dim}`
    if (method === 'umap') return `UMAP ${dim}`
    return `Dim ${dim}`
  }
  const hoverPrefix = method === 'pcoa' ? 'PCo' : method === 'tsne' ? 't-SNE ' : method === 'umap' ? 'UMAP ' : 'Dim '

  const palette = [c.class0, c.class1, c.accent, c.danger]
  const classColorMap = {}
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
        name: `Class ${cls}`,
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
        name: `Class ${cls}`,
        marker: { color: classColorMap[cls], size: 7, opacity: 0.8, line: { color: classColorMap[cls], width: 0.5 } },
        hovertemplate: `%{text}<br>${hoverPrefix}1: %{x:.3f}<br>${hoverPrefix}2: %{y:.3f}<extra></extra>`,
      }
    })

    // Add confidence ellipses as scatter traces (filled closed curves)
    if (pcoaShowEllipses.value && d.ellipses) {
      for (const cls of d.class_labels) {
        const ell = d.ellipses[cls]
        if (!ell) continue
        traces.push({
          x: ell.x,
          y: ell.y,
          mode: 'lines',
          type: 'scatter',
          name: `95% CI – Class ${cls}`,
          line: { color: classColorMap[cls], width: 2, dash: 'dash' },
          fill: 'toself',
          fillcolor: classColorMap[cls] + '18',
          hoverinfo: 'skip',
          showlegend: false,
        })
      }
    }

    Plotly.newPlot(pcoaChartEl.value, traces, chartLayout({
      xaxis: { title: { text: axisLabel(1), font: { color: c.text } }, gridcolor: c.grid, color: c.text, zeroline: true, zerolinecolor: c.grid },
      yaxis: { title: { text: axisLabel(2), font: { color: c.text } }, gridcolor: c.grid, color: c.text, zeroline: true, zerolinecolor: c.grid },
      legend: { orientation: 'h', y: 1.12, font: { color: c.text } },
      height: 500,
    }), { responsive: true, displayModeBar: false })
  }
}

function renderCurrentViz() {
  if (vizTab.value === 'prevalence') renderPrevalenceChart()
  else if (vizTab.value === 'abundance') renderAbundanceChart()
  else if (vizTab.value === 'barcode') renderBarcodeChart()
  else if (vizTab.value === 'volcano') renderVolcanoChart()
  else if (vizTab.value === 'pcoa') {
    if (!pcoaData.value && !loadingPcoa.value) loadPcoa()
    else renderPcoaChart()
  }
}

// Watchers for chart rendering
watch(vizTab, async () => {
  await nextTick()
  renderCurrentViz()
})

watch(() => themeStore.isDark, () => renderCurrentViz())

// When topN changes, reload abundance/barcode data and re-render all
let _topNTimer = null
watch(topN, () => {
  clearTimeout(_topNTimer)
  _topNTimer = setTimeout(async () => {
    await Promise.all([loadAbundance(), loadBarcodeData()])
    renderCurrentViz()
  }, 300)
})

// Re-render PCoA when switching 2D/3D
watch(pcoaDim, () => {
  if (pcoaData.value) renderPcoaChart()
})

// Watch for dataset changes (after upload/assign)
watch(hasTrainData, (val) => { if (val) loadAll() })

onMounted(() => {
  if (hasTrainData.value) loadAll()
  loadPcoaJobs()
  // Restore class names from project DB into config
  const saved = store.current?.class_names
  if (saved && summary.value?.class_labels) {
    cfg.data.classes = summary.value.class_labels.map(cls => saved[cls] || cls)
  }
})
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

.metadata-y-select {
  margin-top: 0.3rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.metadata-y-select label {
  font-size: 0.7rem;
  color: var(--text-secondary);
}
.metadata-y-select select {
  font-size: 0.72rem;
  padding: 0.15rem 0.3rem;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  width: 100%;
}
.regression-badge {
  display: inline-block;
  font-size: 0.6rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--accent);
  background: var(--accent-bg);
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  letter-spacing: 0.03em;
}
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
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.species-tag {
  font-weight: 400;
  font-style: italic;
  font-size: 0.65rem;
  color: var(--text-faint);
  margin-left: 0.2rem;
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

/* Class label inputs */
.class-labels-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-top: 0.3rem;
}
.class-label-chip {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  transition: border-color 0.2s;
}
.class-label-chip.target {
  border-color: var(--brand);
  background: var(--info-bg);
}
.class-index {
  font-weight: 700;
  font-size: 0.8rem;
  color: var(--text-muted);
  min-width: 1.2em;
  text-align: center;
}
.class-label-input {
  width: 100px;
  padding: 0.2rem 0.35rem;
  font-size: 0.75rem;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--text-body);
}
.target-badge, .ref-badge {
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
}
.target-badge {
  background: var(--brand);
  color: var(--accent-text);
}
.ref-badge {
  background: var(--bg-badge);
  color: var(--text-muted);
}

/* Viz header with tabs + top-N control */
.viz-header {
  display: flex;
  align-items: flex-end;
  gap: 1rem;
  margin-bottom: 1rem;
}

.topn-control {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.78rem;
  color: var(--text-secondary);
  white-space: nowrap;
  margin-left: auto;
  margin-bottom: 1px;
}

.topn-input {
  width: 52px;
  padding: 0.2rem 0.3rem;
  font-size: 0.78rem;
  text-align: center;
}

.viz-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}

.toggle-label input[type="checkbox"] {
  accent-color: var(--brand);
}

/* Viz tabs */
.viz-tabs {
  display: flex;
  gap: 0;
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

/* PCoA */
.pcoa-controls {
  display: flex;
  align-items: flex-end;
  gap: 1rem;
  margin-bottom: 0.75rem;
}
.pcoa-control-item {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}
.pcoa-control-item select {
  min-width: 120px;
}
.pcoa-dim-toggle {
  display: flex;
}
.pcoa-dim-toggle button {
  padding: 0.3rem 0.7rem;
  border: 1px solid var(--border);
  background: var(--bg-input);
  color: var(--text-body);
  font-size: 0.8rem;
  cursor: pointer;
}
.pcoa-dim-toggle button:first-child { border-radius: 4px 0 0 4px; }
.pcoa-dim-toggle button:last-child { border-radius: 0 4px 4px 0; border-left: none; }
.pcoa-dim-toggle button.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.pcoa-stats-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}
.pcoa-info { font-size: 0.78rem; color: var(--text-faint); }
.pcoa-permanova {
  font-size: 0.78rem;
  color: var(--text-secondary);
  background: var(--bg-badge);
  padding: 0.2rem 0.6rem;
  border-radius: 6px;
  font-family: monospace;
}
.pcoa-permanova.significant { color: var(--success-dark); background: var(--success-bg-alt); }
.sig-star { color: var(--danger); font-weight: 700; margin-left: 0.2rem; }
.plotly-chart-pcoa { min-height: 500px; }

@media (max-width: 1000px) {
  .data-panels { grid-template-columns: 1fr; }
  .left-panel { max-height: none; position: static; }
}
</style>
