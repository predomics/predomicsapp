<template>
  <div class="sub-content">
    <ModelFormula
      v-if="detail.best_individual"
      :model="detail.best_individual"
      :feature-names="detail.feature_names || []"
      :label-of="featureLabel"
      :class-name-for="classNameFor"
      :is-regression="isRegressionJob"
    />

    <section class="section" v-if="detail.best_individual">
      <div class="best-model-layout">
        <!-- Left column: metrics + radar -->
        <div class="metrics-col">
          <h3>{{ $t('results.metrics') }}</h3>
          <table class="metrics-table">
            <tr v-for="(val, key) in bestMetrics" :key="key">
              <td class="metric-name">{{ key }}</td>
              <td class="metric-value">{{ typeof val === 'number' ? val.toFixed(4) : val }}</td>
            </tr>
          </table>
          <div ref="radarChartEl" class="plotly-chart" style="margin-top: 1rem;"></div>
        </div>
        <!-- Right column: coefficients bar chart -->
        <div class="coefficients-col">
          <h3>{{ $t('results.modelCoefficients') }}</h3>
          <p v-if="coefficientsSummary" id="coefficients-summary" class="chart-summary">{{ coefficientsSummary }}</p>
          <div ref="coefficientsChartEl" class="plotly-chart" role="img" :aria-label="$t('results.modelCoefficients')" aria-describedby="coefficients-summary"></div>
        </div>
      </div>
    </section>

    <!-- Feature importance -->
    <CollapsibleSection class="section" v-if="importanceData && importanceData.length > 0" sid="bestmodel.featureImportanceMDA">
      <template #title>{{ $t('results.featureImportanceMDA') }}</template>
      <div ref="importanceChartEl" class="plotly-chart"></div>
    </CollapsibleSection>
    <p v-else-if="detail.best_individual" class="info-text">
      {{ $t('results.featureImportanceNotAvailable') }}
    </p>

    <!-- Coefficient direction chart -->
    <CollapsibleSection class="section" v-if="detail.best_individual" sid="bestmodel.coefficientDirection">
      <template #title>{{ $t('results.coefficientDirection') }}</template>
      <div ref="directionChartEl" class="plotly-chart"></div>
    </CollapsibleSection>

    <!-- Feature contribution waterfall -->
    <CollapsibleSection class="section" v-if="detail.best_individual" sid="bestmodel.featureContributionWaterfall">
      <template #title>{{ $t('results.featureContributionWaterfall') }}</template>
      <div ref="waterfallChartEl" class="plotly-chart"></div>
    </CollapsibleSection>

    <!-- Per-sample contribution heatmap -->
    <CollapsibleSection class="section" v-if="detail.best_individual" sid="bestmodel.perSampleContributions">
      <template #title>{{ $t('results.perSampleContributions') }}</template>
      <button v-if="!contributionData && !contributionLoading" class="btn-sm btn-outline" @click="loadContributionHeatmap">
        {{ $t('results.computeContributions') }}
      </button>
      <div v-if="contributionLoading" class="loading">{{ $t('results.computingContributions') }}</div>
      <div v-if="contributionData" ref="contributionHeatmapEl" class="plotly-chart plotly-chart-tall"></div>
    </CollapsibleSection>

    <!-- SHAP-style Feature Explanations -->
    <CollapsibleSection class="section" v-if="detail.best_individual" sid="bestmodel.featureExplanations">
      <template #title>{{ $t('results.featureExplanations') }}</template>
      <p class="info-text">{{ $t('results.shapDescription') }}</p>
      <button v-if="!shapData && !shapLoading" class="btn-sm btn-outline" @click="loadShapData">
        {{ $t('results.computeExplanations') }}
      </button>
      <div v-if="shapLoading" class="loading">{{ $t('results.computingShap') }}</div>
      <template v-if="shapData">
        <div class="shap-tabs">
          <button :class="{ active: shapView === 'beeswarm' }" @click="shapView = 'beeswarm'">{{ $t('results.beeswarm') }}</button>
          <button :class="{ active: shapView === 'force' }" @click="shapView = 'force'">{{ $t('results.forcePlot') }}</button>
          <button :class="{ active: shapView === 'dependence' }" @click="shapView = 'dependence'">{{ $t('results.dependence') }}</button>
        </div>
        <!-- Beeswarm: strip plot per feature, x=SHAP value, color=feature value -->
        <div v-if="shapView === 'beeswarm'" ref="beeswarmChartEl" class="plotly-chart plotly-chart-tall"></div>
        <!-- Force: waterfall for single sample -->
        <div v-if="shapView === 'force'" class="shap-control-row">
          <label>{{ $t('results.sampleLabel') }}
            <select v-model="shapSampleIdx" class="shap-select">
              <option v-for="(s, i) in shapData.sampleNames" :key="i" :value="i">{{ s }}</option>
            </select>
          </label>
          <div ref="forceChartEl" class="plotly-chart"></div>
        </div>
        <!-- Dependence: feature value vs SHAP value scatter -->
        <div v-if="shapView === 'dependence'" class="shap-control-row">
          <label>{{ $t('results.featureLabel') }}
            <select v-model="shapFeatureIdx" class="shap-select">
              <option v-for="(f, i) in shapData.featureImportance" :key="i" :value="f.index" :title="f.name">{{ shortName(featureLabel(f.name)) }}</option>
            </select>
          </label>
          <div ref="dependenceChartEl" class="plotly-chart"></div>
        </div>
      </template>
    </CollapsibleSection>

    <!-- External validation -->
    <CollapsibleSection class="section" v-if="detail.best_individual" sid="bestmodel.externalValidation">
      <template #title>{{ $t('results.externalValidation') }}</template>
      <p class="info-text">{{ $t('results.externalValidationDesc') }}</p>
      <button class="btn-sm btn-outline" @click="showValidateModal = true">
        {{ $t('results.validateOnNewData') }}
      </button>
    </CollapsibleSection>

    <!-- Deploy as API -->
    <CollapsibleSection class="section" v-if="detail.best_individual" sid="bestmodel.predictionApi">
      <template #title>{{ $t('results.predictionApi') }}</template>
      <p class="info-text">{{ $t('results.predictionApiDesc') }}</p>
      <div class="deploy-box">
        <div class="deploy-endpoint">
          <code>POST {{ apiBaseUrl }}/api/predict/{{ selectedJobId }}</code>
          <button class="btn-sm btn-outline" @click="copyDeployUrl">{{ deployCopied ? $t('results.copied') : $t('results.copy') }}</button>
        </div>
        <details class="deploy-example">
          <summary>{{ $t('results.usageExample') }}</summary>
          <pre class="code-block">curl -X POST {{ apiBaseUrl }}/api/predict/{{ selectedJobId }} \
    -H "X-API-Key: YOUR_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
    "features": {
    "feature_1": [0.1, 0.2],
    "feature_2": [0.3, 0.4]
    },
    "sample_names": ["sample_A", "sample_B"]
    }'</pre>
        </details>
      </div>
    </CollapsibleSection>

    <ValidateModal
      v-if="showValidateModal"
      :project-id="route.params.id"
      :job-id="selectedJobId"
      @close="showValidateModal = false"
    />
  </div>
</template>

<script setup>
import CollapsibleSection from '../../CollapsibleSection.vue'
import { shortFeatureName as shortName } from '../../../utils/chartLabels'
/**
 * "bestmodel" sub-tab of the Results view. Markup only: state and chart rendering
 * live in composables/useResultsTab.js, shared by every sub-tab through useResults().
 */
import { onMounted } from 'vue'
import { useResults } from '../../../composables/useResultsTab'
import ValidateModal from '../../ValidateModal.vue'
import ModelFormula from '../ModelFormula.vue'

const {
  apiBaseUrl,
  beeswarmChartEl,
  bestMetrics,
  classNameFor,
  coefficientsChartEl,
  coefficientsSummary,
  contributionData,
  contributionHeatmapEl,
  contributionLoading,
  copyDeployUrl,
  dependenceChartEl,
  deployCopied,
  detail,
  directionChartEl,
  featureLabel,
  forceChartEl,
  importanceChartEl,
  importanceData,
  isRegressionJob,
  loadContributionHeatmap,
  loadShapData,
  radarChartEl,
  route,
  selectedJobId,
  shapData,
  shapFeatureIdx,
  shapLoading,
  shapSampleIdx,
  shapView,
  showValidateModal,
  waterfallChartEl,
  renderActiveTab,
} = useResults()

// The chunk for this tab loads on demand, so its chart containers exist only now.
onMounted(() => { renderActiveTab() })
</script>
