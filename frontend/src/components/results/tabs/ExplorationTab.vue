<template>
  <div class="sub-content">
    <section class="section">
      <div class="section-title">{{ $t('results.explorationTitle') }}</div>
      <p class="info-text" style="margin-bottom: 12px;">
        {{ $t('results.explorationDesc') }}
      </p>
      <div class="exploration-controls" style="display:flex; gap:16px; align-items:center; margin-bottom:12px;">
        <label>{{ $t('results.generationLabel') }}
          <input type="range" v-model.number="explorationGen" :min="-1" :max="generationTracking.length - 1" style="width:200px" />
          <span style="min-width:60px; display:inline-block">{{ explorationGen === -1 ? $t('results.allGenerations') : explorationGen }}</span>
        </label>
        <button type="button" class="btn-sm btn-outline" @click="animateExploration"><span aria-hidden="true">▶</span> {{ $t('results.animate') }}</button>
        <div style="flex:1"></div>
        <div class="exploration-stats" v-if="explorationStats">
          <span><strong>{{ $t('results.totalModels') }}</strong> {{ explorationStats.totalModels.toLocaleString() }}</span>
          <span style="margin-left:16px"><strong>{{ $t('results.uniqueSampled') }}</strong> {{ explorationStats.uniqueSampled.toLocaleString() }}</span>
          <span style="margin-left:16px"><strong>{{ $t('results.generationsCount') }}</strong> {{ explorationStats.nGens }}</span>
        </div>
      </div>
      <div ref="explorationChartEl" class="plotly-chart" style="min-height: 500px;"></div>
    </section>
  </div>
</template>

<script setup>
/**
 * "exploration" sub-tab of the Results view. Markup only: state and chart rendering
 * live in composables/useResultsTab.js, shared by every sub-tab through useResults().
 */
import { onMounted } from 'vue'
import { useResults } from '../../../composables/useResultsTab'

const {
  animateExploration,
  explorationChartEl,
  explorationGen,
  explorationStats,
  generationTracking,
  renderActiveTab,
} = useResults()

// The chunk for this tab loads on demand, so its chart containers exist only now.
onMounted(() => { renderActiveTab() })
</script>
