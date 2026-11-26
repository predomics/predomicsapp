<template>
  <div class="sub-content">
    <!-- Job checkboxes -->
    <CollapsibleSection class="section" v-if="completedJobs.length > 1" sid="comparative.selectJobsCompare">
      <template #title>{{ $t('results.selectJobsCompare') }}</template>
      <div class="job-checkboxes">
        <label v-for="j in completedJobs" :key="j.job_id" class="job-check">
          <input type="checkbox" :value="j.job_id" v-model="compareJobIds" />
          <span class="job-check-label">
            {{ j.name || j.job_id.slice(0, 8) }}
            <span v-if="j.best_auc" class="job-check-auc">{{ fitMetricLabel }} {{ j.best_auc.toFixed(4) }}</span>
          </span>
        </label>
      </div>
    </CollapsibleSection>

    <!-- Comparison charts -->
    <template v-if="compareData.length >= 2">
      <!-- Side-by-side metrics table -->
      <CollapsibleSection class="section" sid="comparative.metricsComparison" :default-open="false">
        <template #title>{{ $t('results.metricsComparison') }}</template>
        <div class="compare-table-wrap">
          <table class="compare-table">
            <thead>
              <tr>
                <th>{{ $t('results.metric') }}</th>
                <th v-for="d in compareData" :key="d.job_id">{{ d.name || d.job_id.slice(0, 8) }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in ['auc', 'fit', 'accuracy', 'sensitivity', 'specificity', 'threshold', 'k', 'language', 'data_type']" :key="m">
                <td class="metric-name">{{ metricLabel(m) }}</td>
                <td v-for="d in compareData" :key="d.job_id"
                  :class="{ 'best-val': compareBestMetric(m) === d.job_id }">
                  {{ formatMetricVal(d.best, m) }}
                </td>
              </tr>
              <tr>
                <td class="metric-name">{{ $t('results.time') }}</td>
                <td v-for="d in compareData" :key="d.job_id">{{ d.execution_time ? formatDuration(d.execution_time) : '—' }}</td>
              </tr>
              <tr>
                <td class="metric-name">{{ $t('results.generations') }}</td>
                <td v-for="d in compareData" :key="d.job_id">{{ d.generation_count || '—' }}</td>
              </tr>
              <tr>
                <td class="metric-name">{{ $t('results.population') }}</td>
                <td v-for="d in compareData" :key="d.job_id">{{ d.population?.length || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </CollapsibleSection>

      <!-- Config diff -->
      <CollapsibleSection class="section" v-if="configDiffs.length > 0" sid="comparative.configDifferences" :default-open="false">
        <template #title>{{ $t('results.configDifferences') }}</template>
        <div class="compare-table-wrap">
          <table class="compare-table config-diff-table">
            <thead>
              <tr>
                <th>{{ $t('results.parameter') }}</th>
                <th v-for="d in compareData" :key="d.job_id">{{ d.name || d.job_id.slice(0, 8) }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="diff in configDiffs" :key="diff.path">
                <td class="metric-name">{{ diff.label }}</td>
                <td v-for="(val, i) in diff.values" :key="i" :class="{ 'diff-val': val !== diff.values[0] }">
                  {{ val ?? '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="configDiffs.length === 0" class="info-text">{{ $t('results.identicalConfig') }}</p>
      </CollapsibleSection>

      <CollapsibleSection class="section" sid="comparative.performanceComparison">
        <template #title>{{ $t('results.performanceComparison') }}</template>
        <div ref="comparisonBarEl" class="plotly-chart"></div>
      </CollapsibleSection>

      <!-- Feature analysis -->
      <CollapsibleSection class="section" sid="comparative.featureAnalysis">
        <template #title>{{ $t('results.featureAnalysis') }}</template>
        <div class="feature-analysis">
          <div class="feature-stat">
            <span class="fa-label">{{ $t('results.commonToAll') }}</span>
            <span class="fa-value">{{ featureIntersection.length }} {{ $t('results.features') }}</span>
          </div>
          <div class="feature-stat">
            <span class="fa-label">{{ $t('results.unionAny') }}</span>
            <span class="fa-value">{{ featureUnion.length }} {{ $t('results.features') }}</span>
          </div>
          <div class="feature-stat" v-if="featureIntersection.length > 0">
            <span class="fa-label">{{ $t('results.overlapRatio') }}</span>
            <span class="fa-value">{{ (featureIntersection.length / featureUnion.length * 100).toFixed(1) }}%</span>
          </div>
        </div>
        <div v-if="featureIntersection.length > 0" class="common-features">
          <strong>{{ $t('results.commonFeatures') }}</strong>
          <span v-for="f in featureIntersection" :key="f" class="feature-chip positive"><span :title="f">{{ shortName(featureLabel(f)) }}</span></span>
        </div>
      </CollapsibleSection>

      <CollapsibleSection class="section" sid="comparative.convergenceOverlay">
        <template #title>{{ $t('results.convergenceOverlay') }}</template>
        <div ref="comparisonConvergenceEl" class="plotly-chart"></div>
      </CollapsibleSection>

      <CollapsibleSection class="section" sid="comparative.featureOverlap">
        <template #title>{{ $t('results.featureOverlap') }}</template>
        <div ref="featureOverlapEl" class="plotly-chart"></div>
      </CollapsibleSection>
    </template>

    <p v-if="completedJobs.length < 2" class="info-text">
      {{ $t('results.runAtLeast2') }}
    </p>
    <p v-else-if="compareData.length < 2" class="info-text">
      {{ $t('results.selectAtLeast2') }}
    </p>
  </div>
</template>

<script setup>
import CollapsibleSection from '../../CollapsibleSection.vue'
import { shortFeatureName as shortName } from '../../../utils/chartLabels'
/**
 * "comparative" sub-tab of the Results view. Markup only: state and chart rendering
 * live in composables/useResultsTab.js, shared by every sub-tab through useResults().
 */
import { onMounted } from 'vue'
import { useResults } from '../../../composables/useResultsTab'

const {
  compareBestMetric,
  compareData,
  compareJobIds,
  comparisonBarEl,
  comparisonConvergenceEl,
  completedJobs,
  configDiffs,
  featureIntersection,
  featureLabel,
  featureOverlapEl,
  featureUnion,
  fitMetricLabel,
  formatDuration,
  formatMetricVal,
  metricLabel,
  renderActiveTab,
} = useResults()

// The chunk for this tab loads on demand, so its chart containers exist only now.
onMounted(() => { renderActiveTab() })
</script>
