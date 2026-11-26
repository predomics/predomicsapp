<template>
  <div class="sub-content">
    <div class="summary-grid">
      <div class="stat-card">
        <div class="stat-value">{{ detail.best_auc?.toFixed(4) || '—' }}</div>
        <div class="stat-label">{{ isRegressionJob ? $t('results.fitMetric') : $t('results.bestAuc') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ detail.best_k || '—' }}</div>
        <div class="stat-label">{{ $t('results.featuresK') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ detail.execution_time?.toFixed(1) }}s</div>
        <div class="stat-label">{{ $t('results.time') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ detail.generation_count }}</div>
        <div class="stat-label">{{ $t('results.generations') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ detail.feature_count }}</div>
        <div class="stat-label">{{ $t('results.totalFeatures') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ detail.sample_count }}</div>
        <div class="stat-label">{{ $t('results.samples') }}</div>
      </div>
    </div>

    <!-- Convergence chart -->
    <CollapsibleSection class="section" v-if="generationTracking.length > 0" sid="summary.aucEvolution">
      <template #title>{{ $t('results.aucEvolution') }}</template>
      <p v-if="convergenceSummary" id="convergence-summary" class="chart-summary">{{ convergenceSummary }}</p>
      <div ref="convergenceChartEl" class="plotly-chart" role="img" :aria-label="$t('results.aucEvolution')" aria-describedby="convergence-summary"></div>
    </CollapsibleSection>

    <!-- Feature count + fit evolution -->
    <div class="chart-row" v-if="generationTracking.length > 0">
      <CollapsibleSection class="section chart-half" sid="summary.modelComplexity">
        <template #title>{{ $t('results.modelComplexity') }}</template>
        <p v-if="complexitySummary" id="complexity-summary" class="chart-summary">{{ complexitySummary }}</p>
        <div ref="featureCountChartEl" class="plotly-chart" role="img" :aria-label="$t('results.modelComplexity')" aria-describedby="complexity-summary"></div>
      </CollapsibleSection>
      <CollapsibleSection class="section chart-half" sid="summary.fitVsAuc">
        <template #title>{{ $t('results.fitVsAuc') }}</template>
        <div ref="fitEvolutionChartEl" class="plotly-chart"></div>
      </CollapsibleSection>
    </div>
  </div>
</template>

<script setup>
import CollapsibleSection from '../../CollapsibleSection.vue'
/**
 * "summary" sub-tab of the Results view. Markup only: state and chart rendering
 * live in composables/useResultsTab.js, shared by every sub-tab through useResults().
 */
import { onMounted } from 'vue'
import { useResults } from '../../../composables/useResultsTab'

const {
  complexitySummary,
  convergenceChartEl,
  convergenceSummary,
  detail,
  featureCountChartEl,
  fitEvolutionChartEl,
  generationTracking,
  isRegressionJob,
  renderActiveTab,
} = useResults()

// The chunk for this tab loads on demand, so its chart containers exist only now.
onMounted(() => { renderActiveTab() })
</script>
