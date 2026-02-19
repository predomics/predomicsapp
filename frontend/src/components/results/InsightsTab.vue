<template>
  <div class="insights-tab">
    <p class="section-desc">{{ $t('results.insightsDesc') }}</p>

    <!-- Loading -->
    <div v-if="loading" class="loading-msg">{{ $t('results.insightsLoading') }}</div>

    <!-- Error -->
    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- Content -->
    <template v-if="data && !loading">
      <!-- Severity summary row -->
      <div class="severity-summary">
        <span v-if="data.summary.success" class="sev-chip success">{{ data.summary.success }} {{ $t('results.insightsSuccess') }}</span>
        <span v-if="data.summary.info" class="sev-chip info">{{ data.summary.info }} {{ $t('results.insightsInfo') }}</span>
        <span v-if="data.summary.warning" class="sev-chip warning">{{ data.summary.warning }} {{ $t('results.insightsWarning') }}</span>
        <span v-if="data.summary.critical" class="sev-chip critical">{{ data.summary.critical }} {{ $t('results.insightsCritical') }}</span>
      </div>

      <!-- Radar chart -->
      <div ref="radarEl" class="plotly-chart radar-chart"></div>

      <!-- Category sections -->
      <div v-for="cat in visibleCategories" :key="cat.key" class="insight-category">
        <button class="cat-header" @click="toggleCategory(cat.key)">
          <span class="cat-arrow">{{ expandedCats[cat.key] ? '\u25BC' : '\u25B6' }}</span>
          <span class="cat-title">{{ cat.label }}</span>
          <span class="cat-count">{{ cat.insights.length }}</span>
          <span v-if="data.scores[cat.key] != null" class="cat-score"
                :class="scoreClass(data.scores[cat.key])">
            {{ data.scores[cat.key] }}/100
          </span>
        </button>
        <div v-if="expandedCats[cat.key]" class="cat-body">
          <div v-for="ins in cat.insights" :key="ins.key"
               :class="['insight-card', ins.severity]">
            <div class="insight-header">
              <span class="sev-dot" :class="ins.severity"></span>
              <span class="insight-title">{{ ins.title }}</span>
              <span v-if="ins.value" class="insight-value">{{ ins.value }}</span>
            </div>
            <p class="insight-message">{{ ins.message }}</p>
            <div v-if="ins.details && ins.details.core_features" class="insight-details">
              <span v-for="feat in ins.details.core_features" :key="feat" class="feature-tag">{{ feat }}</span>
            </div>
            <div v-if="ins.details && ins.details.phylum_distribution" class="insight-details">
              <span v-for="(count, phylum) in ins.details.phylum_distribution" :key="phylum" class="feature-tag">
                {{ phylum }}: {{ count }}
              </span>
            </div>
            <div v-if="ins.details && ins.details.enriched" class="insight-details">
              <span v-for="cat_name in ins.details.enriched" :key="cat_name" class="feature-tag enriched">{{ cat_name }}</span>
            </div>
            <!-- Threshold stats -->
            <div v-if="ins.details && ins.details.mean != null && ins.details.std != null" class="insight-details threshold-stats">
              <span class="feature-tag">mean: {{ ins.details.mean }}</span>
              <span class="feature-tag">std: {{ ins.details.std }}</span>
              <span class="feature-tag">range: [{{ ins.details.min }}, {{ ins.details.max }}]</span>
              <span class="feature-tag">n={{ ins.details.count }}</span>
            </div>
            <!-- Threshold CI details -->
            <div v-if="ins.details && ins.details.lower != null && ins.details.upper != null && ins.details.width != null" class="insight-details threshold-stats">
              <span class="feature-tag">lower: {{ ins.details.lower }}</span>
              <span class="feature-tag">threshold: {{ ins.details.threshold }}</span>
              <span class="feature-tag">upper: {{ ins.details.upper }}</span>
              <span v-if="ins.details.rejection_rate" class="feature-tag">rejection: {{ (ins.details.rejection_rate * 100).toFixed(1) }}%</span>
            </div>
          </div>
        </div>
      </div>

      <!-- No insights -->
      <p v-if="data.insights.length === 0" class="no-results">{{ $t('results.insightsNoData') }}</p>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
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

const loading = ref(false)
const error = ref(null)
const data = ref(null)
const radarEl = ref(null)
const expandedCats = ref({
  performance: true,
  overfitting: true,
  threshold: true,
  robustness: true,
  biology: true,
  jury: true,
  recommendation: true,
})

const categoryMeta = [
  { key: 'performance', labelKey: 'results.insightsPerformance' },
  { key: 'overfitting', labelKey: 'results.insightsOverfitting' },
  { key: 'threshold', labelKey: 'results.insightsThreshold' },
  { key: 'robustness', labelKey: 'results.insightsRobustness' },
  { key: 'biology', labelKey: 'results.insightsBiology' },
  { key: 'jury', labelKey: 'results.insightsJury' },
  { key: 'recommendation', labelKey: 'results.insightsRecommendations' },
]

const visibleCategories = computed(() => {
  if (!data.value) return []
  return categoryMeta
    .map(cat => ({
      key: cat.key,
      label: t(cat.labelKey),
      insights: data.value.insights.filter(i => i.category === cat.key),
    }))
    .filter(cat => cat.insights.length > 0)
})

function toggleCategory(key) {
  expandedCats.value[key] = !expandedCats.value[key]
}

function scoreClass(score) {
  if (score >= 80) return 'score-good'
  if (score >= 50) return 'score-moderate'
  return 'score-poor'
}

async function fetchInsights() {
  if (!props.jobId) return
  loading.value = true
  error.value = null
  try {
    const { data: resp } = await axios.get(
      `/api/data-explore/${props.projectId}/insights/${props.jobId}`
    )
    data.value = resp
    await nextTick()
    renderRadar()
  } catch (e) {
    console.error('Insights fetch failed:', e)
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

async function renderRadar() {
  if (!data.value || !radarEl.value) return
  const P = await loadPlotly()
  const scores = data.value.scores
  const c = chartColors()

  const cats = []
  const vals = []
  for (const cat of categoryMeta) {
    if (scores[cat.key] != null) {
      cats.push(t(cat.labelKey))
      vals.push(scores[cat.key])
    }
  }
  if (cats.length < 3) return // need at least 3 axes for radar

  // Close the polygon
  cats.push(cats[0])
  vals.push(vals[0])

  const trace = {
    type: 'scatterpolar',
    r: vals,
    theta: cats,
    fill: 'toself',
    fillcolor: c.isDark ? 'rgba(0, 191, 255, 0.15)' : 'rgba(25, 118, 210, 0.12)',
    line: { color: c.isDark ? '#00BFFF' : '#1976D2', width: 2 },
    marker: { size: 6, color: c.isDark ? '#00BFFF' : '#1976D2' },
    hovertemplate: '%{theta}: %{r}/100<extra></extra>',
  }

  const layout = {
    ...chartLayout(),
    polar: {
      radialaxis: {
        visible: true,
        range: [0, 100],
        gridcolor: c.grid,
        color: c.text,
        tickfont: { size: 10 },
      },
      angularaxis: {
        color: c.text,
        tickfont: { size: 11 },
      },
      bgcolor: c.paper,
    },
    height: 320,
    margin: { t: 30, b: 30, l: 60, r: 60 },
    showlegend: false,
  }

  P.react(radarEl.value, [trace], layout, { responsive: true, displayModeBar: false })
}

onMounted(() => {
  if (props.active && props.jobId) fetchInsights()
})

watch(() => props.active, (active) => {
  if (active && !data.value && props.jobId) fetchInsights()
})

watch(() => props.jobId, () => {
  data.value = null
  if (props.active && props.jobId) fetchInsights()
})
</script>

<style scoped>
.insights-tab {
  padding: 0.5rem 0;
}
.section-desc {
  color: var(--text-secondary, #666);
  font-size: 0.85rem;
  margin-bottom: 1rem;
}
.loading-msg {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary, #999);
  font-style: italic;
}
.error-msg {
  color: #d32f2f;
  padding: 0.75rem 1rem;
  background: #fdecea;
  border-radius: 6px;
  margin-bottom: 1rem;
  font-size: 0.85rem;
}

/* Severity summary */
.severity-summary {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}
.sev-chip {
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.78rem;
  font-weight: 600;
}
.sev-chip.success { background: #e8f5e9; color: #2e7d32; }
.sev-chip.info { background: #e3f2fd; color: #1565c0; }
.sev-chip.warning { background: #fff3e0; color: #e65100; }
.sev-chip.critical { background: #ffebee; color: #c62828; }

/* Radar */
.radar-chart {
  width: 100%;
  max-width: 480px;
  margin: 0 auto 1.5rem;
}

/* Category sections */
.insight-category {
  margin-bottom: 0.75rem;
  border: 1px solid var(--border-light, #e0e0e0);
  border-radius: 8px;
  overflow: hidden;
}
.cat-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.65rem 1rem;
  border: none;
  background: var(--bg-secondary, #f5f5f5);
  cursor: pointer;
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text-primary, #212121);
  text-align: left;
}
.cat-header:hover {
  background: var(--bg-hover, #eeeeee);
}
.cat-arrow {
  font-size: 0.7rem;
  width: 1rem;
  color: var(--text-secondary, #666);
}
.cat-title {
  flex: 1;
}
.cat-count {
  font-size: 0.72rem;
  background: var(--bg-badge, #e0e0e0);
  color: var(--text-secondary, #666);
  padding: 0.1rem 0.5rem;
  border-radius: 10px;
  font-weight: 600;
}
.cat-score {
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.1rem 0.5rem;
  border-radius: 10px;
}
.score-good { background: #e8f5e9; color: #2e7d32; }
.score-moderate { background: #fff3e0; color: #e65100; }
.score-poor { background: #ffebee; color: #c62828; }

/* Insight cards */
.cat-body {
  padding: 0.5rem 0.75rem;
}
.insight-card {
  padding: 0.6rem 0.75rem;
  margin-bottom: 0.5rem;
  border-radius: 6px;
  border-left: 4px solid transparent;
  background: var(--bg-card, #fff);
}
.insight-card.success { border-left-color: #4caf50; }
.insight-card.info { border-left-color: #2196f3; }
.insight-card.warning { border-left-color: #ff9800; }
.insight-card.critical { border-left-color: #f44336; }

.insight-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.sev-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.sev-dot.success { background: #4caf50; }
.sev-dot.info { background: #2196f3; }
.sev-dot.warning { background: #ff9800; }
.sev-dot.critical { background: #f44336; }

.insight-title {
  font-weight: 600;
  font-size: 0.85rem;
  flex: 1;
  color: var(--text-primary, #212121);
}
.insight-value {
  font-size: 0.8rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary, #555);
}
.insight-message {
  font-size: 0.82rem;
  color: var(--text-secondary, #555);
  margin: 0.3rem 0 0 1.5rem;
  line-height: 1.4;
}
.insight-details {
  margin: 0.4rem 0 0 1.5rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}
.feature-tag {
  font-size: 0.72rem;
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  background: var(--bg-badge, #e8eaf6);
  color: var(--text-secondary, #555);
  font-weight: 500;
}
.feature-tag.enriched {
  background: #e3f2fd;
  color: #1565c0;
}
.no-results {
  color: var(--text-secondary, #999);
  font-style: italic;
  text-align: center;
  padding: 2rem;
}

.plotly-chart {
  width: 100%;
}
</style>
