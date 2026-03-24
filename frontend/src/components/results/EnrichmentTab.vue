<template>
  <div class="enrichment-tab">
    <!-- Description -->
    <p class="section-desc">{{ $t('results.enrichmentDesc') }}</p>

    <!-- Controls -->
    <div class="enrichment-controls">
      <label class="enr-control">
        {{ $t('results.enrichmentSignatureLevel') }}
        <select v-model="signatureLevel">
          <option value="individual">{{ $t('results.enrichmentIndividual') }}</option>
          <option value="fbm">{{ $t('results.enrichmentFbm') }}</option>
          <option v-if="props.juryData" value="jury">{{ $t('results.enrichmentJury') }}</option>
        </select>
      </label>

      <label v-if="signatureLevel === 'individual'" class="enr-control">
        {{ $t('results.enrichmentSelectModel') }}
        <select v-model.number="modelIndex">
          <option v-for="i in Math.min(population.length, 50)" :key="i - 1" :value="i - 1">
            #{{ i - 1 }} — k={{ population[i - 1]?.metrics?.k || '?' }}, fit={{ (population[i - 1]?.metrics?.fit || 0).toFixed(3) }}
          </option>
        </select>
      </label>

      <label class="enr-control">
        {{ $t('results.enrichmentAnnotationType') }}
        <select v-model="annotationType">
          <option value="phylum">Phylum</option>
          <option value="family">Family</option>
          <option value="butyrate">Butyrate</option>
          <option value="inflammation">Inflammation</option>
          <option value="transit">Transit</option>
          <option value="oralisation">Oralisation</option>
        </select>
      </label>

      <button class="btn-sm btn-primary" @click="runEnrichment" :disabled="loading">
        {{ loading ? $t('results.enrichmentComputing') : $t('results.enrichmentRun') }}
      </button>
    </div>

    <!-- Summary cards -->
    <div v-if="enrichmentData" class="summary-grid">
      <div class="stat-card">
        <span class="stat-value">{{ enrichmentData.annotated_signature }} / {{ enrichmentData.signature_size }}</span>
        <span class="stat-label">{{ $t('results.enrichmentSignatureSize') }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ enrichmentData.annotated_background }} / {{ enrichmentData.background_size }}</span>
        <span class="stat-label">{{ $t('results.enrichmentBackgroundSize') }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ significantCount }}</span>
        <span class="stat-label">{{ $t('results.enrichmentSignificant') }}</span>
      </div>
    </div>

    <!-- Chart view toggle -->
    <div v-if="enrichmentData && enrichmentData.results.length > 0" class="chart-toggle">
      <button :class="{ active: chartView === 'proportion' }" @click="chartView = 'proportion'; renderChart()">
        {{ $t('results.enrichmentProportionView') }}
      </button>
      <button :class="{ active: chartView === 'significance' }" @click="chartView = 'significance'; renderChart()">
        {{ $t('results.enrichmentSignificanceView') }}
      </button>
    </div>

    <!-- Chart -->
    <div v-if="enrichmentData && enrichmentData.results.length > 0" ref="chartEl" class="plotly-chart"></div>

    <!-- No results message -->
    <p v-if="enrichmentData && enrichmentData.results.length === 0" class="no-results">
      {{ $t('results.enrichmentNoResults') }}
    </p>

    <!-- Results table -->
    <table v-if="enrichmentData && enrichmentData.results.length > 0" class="pop-table enr-table">
      <thead>
        <tr>
          <th>{{ $t('results.enrichmentCategory') }}</th>
          <th>{{ $t('results.enrichmentInSignature') }}</th>
          <th>{{ $t('results.enrichmentInBackground') }}</th>
          <th>% sig</th>
          <th>% bg</th>
          <th>{{ $t('results.enrichmentFoldEnrichment') }}</th>
          <th>{{ $t('results.enrichmentPvalue') }}</th>
          <th>{{ $t('results.enrichmentFdr') }}</th>
          <th>{{ $t('results.enrichmentDirection') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in enrichmentData.results" :key="row.category"
            :class="{ 'sig-row': row.significant }">
          <td class="cat-cell">{{ row.category }}</td>
          <td class="num-cell">{{ row.count_in_signature }}</td>
          <td class="num-cell">{{ row.count_in_background }}</td>
          <td class="num-cell">{{ row.pct_in_signature }}%</td>
          <td class="num-cell">{{ row.pct_in_background }}%</td>
          <td class="num-cell">{{ row.fold_enrichment }}x</td>
          <td class="num-cell">{{ row.p_value < 0.001 ? row.p_value.toExponential(2) : row.p_value.toFixed(4) }}</td>
          <td class="num-cell" :class="{ 'fdr-sig': row.significant }">
            {{ row.fdr < 0.001 ? row.fdr.toExponential(2) : row.fdr.toFixed(4) }}
          </td>
          <td>
            <span :class="['dir-badge', row.direction]">
              {{ row.direction === 'enriched' ? $t('results.enrichmentEnriched') : $t('results.enrichmentDepleted') }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { useChartTheme } from '../../composables/useChartTheme'

let Plotly = null
async function loadPlotly() {
  if (Plotly) return Plotly
  const mod = await import('plotly.js-dist-min')
  Plotly = mod.default
  return Plotly
}

const props = defineProps({
  projectId: { type: String, required: true },
  jobId: { type: String, default: '' },
  population: { type: Array, default: () => [] },
  juryData: { type: Object, default: null },
  detail: { type: Object, default: null },
  mspAnnotations: { type: Object, default: () => ({}) },
  active: { type: Boolean, default: false },
})

const { chartColors, chartLayout } = useChartTheme()
const { t } = useI18n()

// Controls
const signatureLevel = ref('individual')
const modelIndex = ref(0)
const annotationType = ref('phylum')
const loading = ref(false)
const enrichmentData = ref(null)
const chartView = ref('proportion')
const chartEl = ref(null)

const significantCount = computed(() => {
  if (!enrichmentData.value) return 0
  return enrichmentData.value.results.filter(r => r.significant).length
})

// Auto-run enrichment when tab becomes active
watch(() => props.active, (isActive) => {
  if (isActive && !enrichmentData.value && !loading.value && props.jobId) {
    runEnrichment()
  }
})

async function runEnrichment() {
  loading.value = true
  try {
    const { data } = await axios.post(
      `/api/data-explore/${props.projectId}/enrichment`,
      {
        job_id: props.jobId,
        signature_level: signatureLevel.value,
        model_index: modelIndex.value,
        annotation_type: annotationType.value,
      }
    )
    enrichmentData.value = data
    await nextTick()
    renderChart()
  } catch (e) {
    console.error('Enrichment failed:', e)
    enrichmentData.value = null
  } finally {
    loading.value = false
  }
}

async function renderChart() {
  if (!enrichmentData.value || !chartEl.value) return
  const P = await loadPlotly()
  const results = enrichmentData.value.results

  if (chartView.value === 'proportion') {
    renderProportionChart(P, results)
  } else {
    renderSignificanceChart(P, results)
  }
}

function renderProportionChart(P, results) {
  const categories = results.map(r => r.category)
  const sigPct = results.map(r => r.pct_in_signature)
  const bgPct = results.map(r => r.pct_in_background)

  const traces = [
    {
      name: t('results.enrichmentInSignature'),
      x: sigPct,
      y: categories,
      type: 'bar',
      orientation: 'h',
      marker: { color: results.map(r => r.significant ? '#2196F3' : '#90CAF9') },
    },
    {
      name: t('results.enrichmentInBackground'),
      x: bgPct,
      y: categories,
      type: 'bar',
      orientation: 'h',
      marker: { color: '#BDBDBD' },
    },
  ]

  const layout = {
    ...chartLayout(),
    barmode: 'group',
    xaxis: { title: '%', zeroline: true },
    yaxis: { automargin: true },
    margin: { l: 200, r: 40, t: 30, b: 50 },
    height: Math.max(300, results.length * 35 + 80),
    legend: { orientation: 'h', y: -0.15 },
  }

  P.react(chartEl.value, traces, layout, { responsive: true })
}

function renderSignificanceChart(P, results) {
  const sorted = [...results].sort((a, b) => a.p_value - b.p_value)
  const categories = sorted.map(r => r.category)
  const negLogFdr = sorted.map(r => r.fdr > 0 ? -Math.log10(r.fdr) : 5)
  const colors = sorted.map(r => {
    if (!r.significant) return '#BDBDBD'
    return r.direction === 'enriched' ? '#1976D2' : '#E53935'
  })

  const traces = [{
    x: negLogFdr,
    y: categories,
    type: 'bar',
    orientation: 'h',
    marker: { color: colors },
    text: sorted.map(r => `${r.fold_enrichment}x ${r.direction}`),
    hovertemplate: '%{y}<br>-log10(FDR) = %{x:.2f}<br>%{text}<extra></extra>',
  }]

  const fdrThreshold = -Math.log10(0.05)
  const layout = {
    ...chartLayout(),
    xaxis: { title: '-log10(FDR)', zeroline: true },
    yaxis: { automargin: true },
    margin: { l: 200, r: 40, t: 30, b: 50 },
    height: Math.max(300, sorted.length * 35 + 80),
    shapes: [{
      type: 'line',
      x0: fdrThreshold, x1: fdrThreshold,
      y0: -0.5, y1: sorted.length - 0.5,
      line: { color: '#E53935', width: 1.5, dash: 'dash' },
    }],
    annotations: [{
      x: fdrThreshold, y: sorted.length - 0.5,
      text: 'FDR = 0.05',
      showarrow: false, xanchor: 'left', font: { size: 10, color: '#E53935' },
    }],
  }

  P.react(chartEl.value, traces, layout, { responsive: true })
}
</script>

<style scoped>
.enrichment-tab {
  padding: 0.5rem 0;
}
.section-desc {
  color: var(--text-secondary, #666);
  font-size: 0.85rem;
  margin-bottom: 1rem;
}
.enrichment-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: flex-end;
  margin-bottom: 1.5rem;
  padding: 0.75rem;
  background: var(--bg-secondary, #f5f5f5);
  border-radius: 8px;
}
.enr-control {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary, #666);
}
.enr-control select {
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--border, #ddd);
  border-radius: 4px;
  font-size: 0.85rem;
  min-width: 150px;
}
.btn-primary {
  background: var(--accent, #1976D2);
  color: #fff;
  border: none;
  padding: 0.45rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  align-self: flex-end;
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-primary:hover:not(:disabled) {
  filter: brightness(1.1);
}
.summary-grid {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
}
.stat-card {
  flex: 1;
  background: var(--bg-secondary, #f8f9fa);
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 6px;
  padding: 0.75rem 1rem;
  text-align: center;
}
.stat-value {
  display: block;
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--text-primary, #212121);
}
.stat-label {
  display: block;
  font-size: 0.75rem;
  color: var(--text-secondary, #666);
  margin-top: 0.2rem;
}
.chart-toggle {
  display: flex;
  gap: 0;
  margin-bottom: 0.5rem;
}
.chart-toggle button {
  padding: 0.35rem 0.75rem;
  border: 1px solid var(--border, #ddd);
  background: var(--bg-secondary, #f5f5f5);
  cursor: pointer;
  font-size: 0.8rem;
}
.chart-toggle button:first-child { border-radius: 4px 0 0 4px; }
.chart-toggle button:last-child { border-radius: 0 4px 4px 0; }
.chart-toggle button.active {
  background: var(--accent, #1976D2);
  color: #fff;
  border-color: var(--accent, #1976D2);
}
.plotly-chart {
  width: 100%;
  margin-bottom: 1.5rem;
}
.enr-table {
  font-size: 0.82rem;
  width: 100%;
  border-collapse: collapse;
}
.enr-table th {
  text-align: left;
  padding: 0.4rem 0.6rem;
  border-bottom: 2px solid var(--border, #ddd);
  font-size: 0.75rem;
  color: var(--text-secondary, #666);
}
.enr-table td {
  padding: 0.35rem 0.6rem;
  border-bottom: 1px solid var(--border-light, #eee);
}
.num-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.cat-cell {
  font-weight: 500;
}
.sig-row {
  background: var(--bg-highlight, #e3f2fd);
}
.fdr-sig {
  font-weight: 700;
  color: var(--accent, #1976D2);
}
.dir-badge {
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  font-size: 0.75rem;
  font-weight: 600;
}
.dir-badge.enriched {
  background: #e3f2fd;
  color: #1565C0;
}
.dir-badge.depleted {
  background: #ffebee;
  color: #c62828;
}
.no-results {
  color: var(--text-secondary, #999);
  font-style: italic;
  text-align: center;
  padding: 2rem;
}
</style>
