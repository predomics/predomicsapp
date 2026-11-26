<template>
  <div class="sub-content">
    <template v-if="juryData">
      <!-- Jury summary cards -->
      <div class="summary-grid">
        <div class="stat-card">
          <div class="stat-value">{{ juryData.method }}</div>
          <div class="stat-label">{{ $t('results.votingMethod') }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ juryData.expert_count }}</div>
          <div class="stat-label">{{ $t('results.experts') }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ juryData.test?.auc?.toFixed(4) || '—' }}</div>
          <div class="stat-label">{{ $t('results.testAucLabel') }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ juryData.test?.accuracy?.toFixed(4) || '—' }}</div>
          <div class="stat-label">{{ $t('results.testAccuracy') }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ juryData.test?.sensitivity?.toFixed(4) || '—' }}</div>
          <div class="stat-label">{{ $t('results.testSensitivity') }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ juryData.test?.specificity?.toFixed(4) || '—' }}</div>
          <div class="stat-label">{{ $t('results.testSpecificity') }}</div>
        </div>
      </div>

      <!-- Jury vs Best Model comparison -->
      <CollapsibleSection class="section" sid="jury.juryVsBest">
        <template #title>{{ $t('results.juryVsBest') }}</template>
        <div ref="juryComparisonEl" class="plotly-chart"></div>
      </CollapsibleSection>

      <!-- Concordance + Confusion matrices -->
      <div class="chart-row">
        <CollapsibleSection class="section chart-half" v-if="juryData.sample_predictions?.length || juryData.confusion_train" sid="jury.classificationConcordance">
          <template #title>{{ $t('results.classificationConcordance') }}</template>
          <div ref="juryConcordanceEl" class="plotly-chart"></div>
        </CollapsibleSection>
        <div class="chart-half jury-cm-stack">
          <CollapsibleSection class="section" v-if="juryData.confusion_train" sid="jury.confusionTrain">
            <template #title>{{ $t('results.confusionTrain') }}</template>
            <div ref="juryConfusionTrainEl" class="plotly-chart"></div>
          </CollapsibleSection>
          <CollapsibleSection class="section" v-if="juryData.confusion_test" sid="jury.confusionTest">
            <template #title>{{ $t('results.confusionTest') }}</template>
            <div ref="juryConfusionTestEl" class="plotly-chart"></div>
          </CollapsibleSection>
        </div>
      </div>

      <!-- Vote Matrix Heatmap -->
      <CollapsibleSection class="section" v-if="juryData.vote_matrix" sid="jury.voteMatrix">
        <template #title>{{ $t('results.voteMatrix') }} ({{ $t('results.samplesExperts', { samples: juryData.vote_matrix.sample_names?.length, experts: juryData.vote_matrix.n_experts }) }})</template>
        <div ref="voteMatrixEl" class="plotly-chart plotly-chart-tall"></div>
      </CollapsibleSection>

      <!-- Per-sample predictions visual (paginated, ordered by error rate) -->
      <CollapsibleSection class="section" v-if="juryData.sample_predictions?.length > 0" sid="jury.samplePredictions">
        <template #title>{{ $t('results.samplePredictions', { n: juryData.sample_predictions.length }) }}</template>
        <div ref="samplePredictionsEl" class="plotly-chart"></div>
        <div class="pagination" v-if="juryData.sample_predictions.length > samplePredPageSize">
          <button @click="changeSamplePredPage(samplePredPage - 1)" :disabled="samplePredPage === 0">&laquo; {{ $t('results.prev') }}</button>
          <span>{{ $t('results.page') }} {{ samplePredPage + 1 }} / {{ Math.ceil(juryData.sample_predictions.length / samplePredPageSize) }}</span>
          <button @click="changeSamplePredPage(samplePredPage + 1)" :disabled="(samplePredPage + 1) * samplePredPageSize >= juryData.sample_predictions.length">{{ $t('results.next') }} &raquo;</button>
        </div>
      </CollapsibleSection>

      <!-- FBM info -->
      <CollapsibleSection class="section" v-if="juryData.fbm" sid="jury.fbmExpertPop" :default-open="false">
        <template #title>{{ $t('results.fbmExpertPop', { n: juryData.fbm.count }) }}</template>
        <table class="metrics-table" style="max-width: 100%;">
          <tr>
            <td class="metric-name"></td>
            <td class="metric-value" style="font-size: 0.75rem; color: var(--text-muted);">{{ $t('results.train') }}</td>
            <td class="metric-value" style="font-size: 0.75rem; color: var(--text-muted);">{{ $t('results.test') }}</td>
          </tr>
          <tr v-for="m in ['auc', 'accuracy', 'sensitivity', 'specificity']" :key="m">
            <td class="metric-name">{{ m.charAt(0).toUpperCase() + m.slice(1) }}</td>
            <td class="metric-value">{{ juryData.fbm.train[m]?.toFixed(4) }}</td>
            <td class="metric-value">{{ juryData.fbm.test[m]?.toFixed(4) }}</td>
          </tr>
        </table>
      </CollapsibleSection>
    </template>
    <p v-else class="info-text">
      {{ $t('results.juryNotAvailable') }}
    </p>
  </div>
</template>

<script setup>
import CollapsibleSection from '../../CollapsibleSection.vue'
/**
 * "jury" sub-tab of the Results view. Markup only: state and chart rendering
 * live in composables/useResultsTab.js, shared by every sub-tab through useResults().
 */
import { onMounted } from 'vue'
import { useResults } from '../../../composables/useResultsTab'

const {
  changeSamplePredPage,
  juryComparisonEl,
  juryConcordanceEl,
  juryConfusionTestEl,
  juryConfusionTrainEl,
  juryData,
  samplePredPage,
  samplePredPageSize,
  samplePredictionsEl,
  voteMatrixEl,
  renderActiveTab,
} = useResults()

// The chunk for this tab loads on demand, so its chart containers exist only now.
onMounted(() => { renderActiveTab() })
</script>
