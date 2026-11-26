<template>
  <div class="sub-content">
    <!-- Controls -->
    <div class="pop-controls">
      <div class="pop-controls-row">
        <label class="fbm-toggle">
          <input type="checkbox" v-model="copresenceFBM" />
          {{ $t('results.fbmOnly') }}
          <span class="fbm-badge" v-if="copresenceFBM">{{ fbmCount }} / {{ population.length }}</span>
        </label>
        <select :aria-label="$t('results.fbmMethodLabel')" v-if="copresenceFBM" v-model="fbmMethod" class="fbm-method-select">
          <option value="wald">{{ $t('results.fbmWald') }}</option>
          <option value="wald_continuity">{{ $t('results.fbmWaldContinuity') }}</option>
          <option value="wilson">{{ $t('results.fbmWilson') }}</option>
          <option value="agresti_coull">{{ $t('results.fbmAgrestiCoull') }}</option>
          <option value="clopper_pearson">{{ $t('results.fbmClopperPearson') }}</option>
        </select>
        <label class="topn-control" style="margin-left: 1rem;">
          {{ $t('results.minPrevalence') }}
          <input type="number" v-model.number="copresenceMinPrev" :min="2" :max="population.length" step="1" class="topn-input" />
          {{ $t('results.models') }}
        </label>
        <label class="topn-control" style="margin-left: 1rem;" :title="$t('results.copresenceTopHint')">
          {{ $t('results.copresenceTop') }}
          <input type="number" v-model.number="copresenceTopN" :min="0" :max="copresenceData.features.length" step="10" class="topn-input" />
          {{ $t('results.copresenceTopOf', { n: copresenceData.features.length }) }}
        </label>
        <label class="topn-control" style="margin-left: 1rem;">
          {{ $t('results.pValueThreshold') }}
          <select v-model.number="copresenceAlpha" class="topn-input" style="width: 5rem;">
            <option :value="0.2">0.20</option>
            <option :value="0.1">0.10</option>
            <option :value="0.05">0.05</option>
            <option :value="0.01">0.01</option>
          </select>
        </label>
        <label class="fbm-toggle" style="margin-left: 1rem;">
          <input type="checkbox" v-model="copresenceWeighted" />
          {{ $t('results.accuracyWeighted') }}
        </label>
      </div>
    </div>

    <!-- Feature prevalence in population -->
    <CollapsibleSection class="section" v-if="copresencePopulation.length > 1" sid="copresence.featurePrevalenceInPop">
      <template #title>{{ $t('results.featurePrevalenceInPop', { n: copresencePopulation.length }) }}</template>
      <div ref="copresencePrevalenceEl" class="plotly-chart"></div>
    </CollapsibleSection>

    <!-- Functional annotation summary -->
    <CollapsibleSection class="section" v-if="copresencePopulation.length > 1 && Object.keys(mspAnnotations).length > 0" sid="copresence.functionalAnnotations" :default-open="false">
      <template #title>{{ $t('results.functionalAnnotations') }}</template>
      <p class="info-text" style="margin-bottom: 0.5rem;">
        {{ $t('results.funcAnnotDesc') }}
      </p>
      <div ref="funcAnnotChartEl" class="plotly-chart"></div>
      <!-- Annotation table per feature -->
      <details class="advanced-toggle" style="margin-top: 0.75rem;">
        <summary>{{ $t('results.featureAnnotDetails', { n: funcAnnotatedFeatures.length }) }}</summary>
        <table class="pop-table" style="margin-top: 0.5rem;">
          <thead>
            <tr>
              <th>{{ $t('results.colFeature') }}</th>
              <th>{{ $t('results.colTaxonomy') }}</th>
              <th>{{ $t('results.colButyrate') }}</th>
              <th>{{ $t('results.colInflammation') }}</th>
              <th>{{ $t('results.colTransit') }}</th>
              <th>{{ $t('results.colOral') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in funcAnnotatedFeatures" :key="f.name">
              <td><span :title="f.name">{{ shortName(f.name) }}</span></td>
              <td style="font-style: italic; font-size: 0.78rem;">{{ f.species }}</td>
              <td><span v-if="f.butyrate === 1" class="func-badge func-positive">{{ $t('results.producer') }}</span></td>
              <td>
                <span v-if="f.inflammation === 1" class="func-badge func-negative">{{ $t('results.enriched') }}</span>
                <span v-else-if="f.inflammation === -1" class="func-badge func-positive">{{ $t('results.depleted') }}</span>
              </td>
              <td>
                <span v-if="f.transit === 1" class="func-badge func-neutral">{{ $t('results.fast') }}</span>
                <span v-else-if="f.transit === -1" class="func-badge func-neutral">{{ $t('results.slow') }}</span>
              </td>
              <td><span v-if="f.oralisation === 1" class="func-badge func-warn">{{ $t('results.oral') }}</span></td>
            </tr>
          </tbody>
        </table>
      </details>
    </CollapsibleSection>

    <!-- Co-occurrence heatmap -->
    <CollapsibleSection class="section" v-if="copresencePopulation.length > 1" sid="copresence.cooccurrenceMatrix">
      <template #title>{{ $t('results.cooccurrenceMatrix') }}</template>
      <p class="info-text" style="margin-bottom: 0.5rem;">
        {{ $t('results.cooccurrenceMatrixDesc') }}
      </p>
      <div ref="copresenceHeatmapEl" class="plotly-chart"></div>
    </CollapsibleSection>

    <!-- Co-occurrence network -->
    <section class="section" v-if="copresencePopulation.length > 1">
      <div class="network-header">
        <h3>{{ $t('results.cooccurrenceNetwork') }}</h3>
        <div class="layout-selector">
          <label v-for="opt in networkLayoutOptions" :key="opt.value" class="layout-option" :class="{ active: networkLayout === opt.value }">
            <input type="radio" :value="opt.value" v-model="networkLayout" />
            {{ opt.label }}
          </label>
        </div>
      </div>
      <p class="info-text" style="margin-bottom: 0.5rem;">
        {{ $t('results.networkDesc') }}
      </p>
      <div ref="copresenceNetworkEl" class="plotly-chart"></div>
    </section>

    <!-- Co-occurrence statistics table -->
    <CollapsibleSection class="section" v-if="copresenceStats.length > 0" sid="copresence.significantPairs" :default-open="false">
      <template #title>{{ $t('results.significantPairs', { n: copresenceStats.length }) }}</template>
      <table class="pop-table">
        <thead>
          <tr>
            <th>{{ $t('results.colFeature1') }}</th>
            <th>{{ $t('results.colFeature2') }}</th>
            <th>{{ $t('results.colObserved') }}</th>
            <th v-if="copresenceWeighted">{{ $t('results.weightedObs') }}</th>
            <th>{{ $t('results.colExpected') }}</th>
            <th>{{ $t('results.colRatio') }}</th>
            <th v-if="copresenceWeighted">{{ $t('results.wRatio') }}</th>
            <th>{{ $t('results.colPValue') }}</th>
            <th>{{ $t('results.colType') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, ri) in copresenceStatsPaginated" :key="ri">
            <td><span :title="row.f1">{{ shortName(featureLabel(row.f1)) }}</span></td>
            <td><span :title="row.f2">{{ shortName(featureLabel(row.f2)) }}</span></td>
            <td>{{ row.observed }}</td>
            <td v-if="copresenceWeighted">{{ row.wObserved }}</td>
            <td>{{ row.expected.toFixed(1) }}</td>
            <td :style="{ color: row.ratio > 1 ? 'var(--positive, #98c379)' : 'var(--negative, #e06c75)' }">
              {{ row.ratio === Infinity ? '∞' : row.ratio.toFixed(2) }}
            </td>
            <td v-if="copresenceWeighted" :style="{ color: row.wRatio > 1 ? 'var(--positive, #98c379)' : 'var(--negative, #e06c75)' }">
              {{ row.wRatio === Infinity ? '∞' : row.wRatio.toFixed(2) }}
            </td>
            <td>{{ row.pvalue < 0.001 ? row.pvalue.toExponential(1) : row.pvalue.toFixed(3) }}</td>
            <td>
              <span class="cooccur-type" :class="row.type">{{ row.type === 'positive' ? $t('results.cooccur') : $t('results.exclude') }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="pagination" v-if="copresenceStats.length > copresencePageSize">
        <button @click="copresencePage = Math.max(0, copresencePage - 1)" :disabled="copresencePage === 0">&laquo; {{ $t('results.prev') }}</button>
        <span>{{ $t('results.page') }} {{ copresencePage + 1 }} / {{ Math.ceil(copresenceStats.length / copresencePageSize) }}</span>
        <button @click="copresencePage++" :disabled="(copresencePage + 1) * copresencePageSize >= copresenceStats.length">{{ $t('results.next') }} &raquo;</button>
      </div>
    </CollapsibleSection>

    <p v-if="population.length < 2" class="info-text">
      {{ $t('results.copresenceRequires2') }}
    </p>
  </div>
</template>

<script setup>
import CollapsibleSection from '../../CollapsibleSection.vue'
import { shortFeatureName as shortName } from '../../../utils/chartLabels'
/**
 * "copresence" sub-tab of the Results view. Markup only: state and chart rendering
 * live in composables/useResultsTab.js, shared by every sub-tab through useResults().
 */
import { onMounted } from 'vue'
import { useResults } from '../../../composables/useResultsTab'

const {
  copresenceAlpha,
  copresenceFBM,
  copresenceHeatmapEl,
  copresenceMinPrev,
  copresenceTopN,
  copresenceData,
  copresenceNetworkEl,
  copresencePage,
  copresencePageSize,
  copresencePopulation,
  copresencePrevalenceEl,
  copresenceStats,
  copresenceStatsPaginated,
  copresenceWeighted,
  fbmCount,
  fbmMethod,
  featureLabel,
  funcAnnotChartEl,
  funcAnnotatedFeatures,
  mspAnnotations,
  networkLayout,
  networkLayoutOptions,
  population,
  renderActiveTab,
} = useResults()

// The chunk for this tab loads on demand, so its chart containers exist only now.
onMounted(() => { renderActiveTab() })
</script>
