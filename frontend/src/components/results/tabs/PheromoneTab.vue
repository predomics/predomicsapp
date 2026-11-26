<template>
  <div class="sub-content">
    <!-- 1. Pheromone bar chart (final values) -->
    <section class="section">
      <div class="section-title">{{ $t('results.pheromone1Title') }}</div>
      <p class="info-text" style="margin-bottom: 8px;">
        {{ $t('results.pheromone1Desc') }}
      </p>
      <div class="pheromone-controls">
        <label>{{ $t('results.topFeaturesLabel') }} <input type="number" v-model.number="pheromoneTopN" min="5" max="200" step="5" style="width:60px" /></label>
      </div>
      <div ref="pheromoneChartEl" class="plotly-chart" style="min-height: 400px;"></div>
    </section>

    <!-- 2. Pheromone evolution timeline -->
    <section class="section" v-if="fullResults?.pheromone_timeline">
      <div class="section-title">{{ $t('results.pheromone2Title') }}</div>
      <p class="info-text" style="margin-bottom: 8px;">
        {{ $t('results.pheromone2Desc') }}
      </p>
      <div ref="pheromoneTimelineEl" class="plotly-chart" style="min-height: 400px;"></div>
    </section>

    <!-- 3. Convergence entropy curve -->
    <section class="section" v-if="fullResults?.pheromone_timeline">
      <div class="section-title">{{ $t('results.pheromone3Title') }}</div>
      <p class="info-text" style="margin-bottom: 8px;">
        {{ $t('results.pheromone3Desc') }}
      </p>
      <div ref="entropyChartEl" class="plotly-chart" style="min-height: 300px;"></div>
    </section>

    <!-- 4. Feature co-selection network -->
    <section class="section" v-if="fullResults?.feature_cooccurrence">
      <div class="section-title">{{ $t('results.pheromone4Title') }}</div>
      <p class="info-text" style="margin-bottom: 8px;">
        {{ $t('results.pheromone4Desc') }}
      </p>
      <div ref="cooccurrenceChartEl" class="plotly-chart" style="min-height: 500px;"></div>
    </section>

    <!-- 5. Feature discovery timeline -->
    <section class="section" v-if="fullResults?.feature_discovery">
      <div class="section-title">{{ $t('results.pheromone5Title') }}</div>
      <p class="info-text" style="margin-bottom: 8px;">
        {{ $t('results.pheromone5Desc') }}
      </p>
      <div ref="discoveryChartEl" class="plotly-chart" style="min-height: 400px;"></div>
    </section>
  </div>
</template>

<script setup>
/**
 * "pheromone" sub-tab of the Results view. Markup only: state and chart rendering
 * live in composables/useResultsTab.js, shared by every sub-tab through useResults().
 */
import { onMounted } from 'vue'
import { useResults } from '../../../composables/useResultsTab'

const {
  cooccurrenceChartEl,
  discoveryChartEl,
  entropyChartEl,
  fullResults,
  pheromoneChartEl,
  pheromoneTimelineEl,
  pheromoneTopN,
  renderActiveTab,
} = useResults()

// The chunk for this tab loads on demand, so its chart containers exist only now.
onMounted(() => { renderActiveTab() })
</script>
