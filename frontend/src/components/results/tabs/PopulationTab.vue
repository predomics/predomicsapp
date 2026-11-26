<template>
  <div class="sub-content">
    <!-- Controls -->
    <div class="pop-controls">
      <div class="pop-controls-row">
        <label class="topn-control">
          {{ $t('results.top') }}
          <input type="number" v-model.number="topNModels" :min="5" :max="filteredPopulation.length" step="5" class="topn-input" />
          / {{ filteredPopulation.length }} {{ $t('results.models') }}
        </label>
        <label class="fbm-toggle">
          <input type="checkbox" v-model="fbmEnabled" />
          {{ $t('results.fbmOnly') }}
          <span class="fbm-badge" v-if="fbmEnabled">{{ fbmCount }} / {{ population.length }}</span>
        </label>
        <select :aria-label="$t('results.fbmMethodLabel')" v-if="fbmEnabled" v-model="fbmMethod" class="fbm-method-select">
          <option value="wald">{{ $t('results.fbmWald') }}</option>
          <option value="wald_continuity">{{ $t('results.fbmWaldContinuity') }}</option>
          <option value="wilson">{{ $t('results.fbmWilson') }}</option>
          <option value="agresti_coull">{{ $t('results.fbmAgrestiCoull') }}</option>
          <option value="clopper_pearson">{{ $t('results.fbmClopperPearson') }}</option>
        </select>
      </div>

      <!-- Language filter -->
      <div class="filter-row" v-if="availableLanguages.length > 1">
        <span class="filter-label">{{ $t('results.languageFilter') }}</span>
        <label v-for="lang in availableLanguages" :key="lang" class="filter-check">
          <input type="checkbox" :value="lang" v-model="selectedLanguages" />
          {{ lang }}
        </label>
        <button v-if="selectedLanguages.length > 0" class="filter-clear" @click="selectedLanguages = []">{{ $t('results.clear') }}</button>
      </div>

      <!-- Data type filter -->
      <div class="filter-row" v-if="availableDataTypes.length > 1">
        <span class="filter-label">{{ $t('results.dataTypeFilter') }}</span>
        <label v-for="dt in availableDataTypes" :key="dt" class="filter-check">
          <input type="checkbox" :value="dt" v-model="selectedDataTypes" />
          {{ dt }}
        </label>
        <button v-if="selectedDataTypes.length > 0" class="filter-clear" @click="selectedDataTypes = []">{{ $t('results.clear') }}</button>
      </div>
    </div>

    <!-- Language / Data Type composition -->
    <div class="chart-row" v-if="filteredPopulation.length > 0">
      <CollapsibleSection class="section chart-half" sid="population.compositionByType">
        <template #title>{{ $t('results.compositionByType') }}</template>
        <div ref="compositionChartEl" class="plotly-chart"></div>
      </CollapsibleSection>
      <CollapsibleSection class="section chart-half" sid="population.aucDistribution">
        <template #title>{{ $t('results.aucDistribution') }}</template>
        <div ref="metricsByTypeEl" class="plotly-chart"></div>
      </CollapsibleSection>
    </div>

    <!-- Feature-model heatmap -->
    <CollapsibleSection class="section" v-if="filteredPopulation.length > 0" sid="population.featureModelCoefficients">
      <template #title>{{ $t('results.featureModelCoefficients') }}</template>
      <div ref="featureHeatmapEl" class="plotly-chart"></div>
    </CollapsibleSection>

    <!-- Feature prevalence + pop metrics side by side -->
    <div class="chart-row" v-if="filteredPopulation.length > 0">
      <CollapsibleSection class="section chart-half" sid="population.featurePrevalence">
        <template #title>{{ $t('results.featurePrevalence') }}</template>
        <div ref="featurePrevalenceEl" class="plotly-chart"></div>
      </CollapsibleSection>
      <CollapsibleSection class="section chart-half" sid="population.populationMetrics">
        <template #title>{{ $t('results.populationMetrics') }}</template>
        <div ref="popMetricsEl" class="plotly-chart"></div>
      </CollapsibleSection>
    </div>

    <!-- PCoA on FBM features -->
    <CollapsibleSection class="section" v-if="filteredPopulation.length > 0" sid="population.pcoaFbm">
      <template #title>{{ $t('results.pcoaFbm') }}</template>
      <div class="pcoa-controls">
        <label class="pcoa-control-item">
          <span>{{ $t('data.ordinationMethod') }}</span>
          <select v-model="popPcoaMethod" @change="loadPopPcoa">
            <option value="pcoa">PCoA</option>
            <option value="tsne">t-SNE</option>
            <option value="umap">UMAP</option>
          </select>
        </label>
        <label class="pcoa-control-item">
          <span>{{ $t('data.pcoaMetric') }}</span>
          <select v-model="popPcoaMetric" @change="loadPopPcoa">
            <option value="braycurtis">Bray-Curtis</option>
            <option value="euclidean">{{ $t('data.euclidean') }}</option>
            <option value="jaccard">Jaccard</option>
            <option value="cosine">{{ $t('data.cosine') }}</option>
          </select>
        </label>
        <label v-if="popPcoaMethod === 'tsne'" class="pcoa-control-item">
          <span>{{ $t('data.perplexity') }}</span>
          <input type="number" v-model.number="popTsnePerplexity" min="5" max="100" step="5" @change="loadPopPcoa" class="param-input" />
        </label>
        <label v-if="popPcoaMethod === 'umap'" class="pcoa-control-item">
          <span>{{ $t('data.nNeighbors') }}</span>
          <input type="number" v-model.number="popUmapNeighbors" min="2" max="100" step="1" @change="loadPopPcoa" class="param-input" />
        </label>
        <label v-if="popPcoaMethod === 'umap'" class="pcoa-control-item">
          <span>{{ $t('data.minDist') }}</span>
          <input type="number" v-model.number="popUmapMinDist" min="0" max="1" step="0.05" @change="loadPopPcoa" class="param-input" />
        </label>
        <label class="toggle-label">
          <input type="checkbox" v-model="popPcoaShowEllipses" @change="renderPopPcoaChart" />
          {{ $t('data.ellipses') }}
        </label>
        <div class="pcoa-dim-toggle">
          <button :class="{ active: popPcoaDim === '2d' }" @click="popPcoaDim = '2d'">2D</button>
          <button :class="{ active: popPcoaDim === '3d' }" @click="popPcoaDim = '3d'">3D</button>
        </div>
      </div>
      <div v-if="popPcoaData" class="pcoa-stats-row">
        <span class="pcoa-info">
          {{ popPcoaData.n_samples }} {{ $t('data.samples').toLowerCase() }}
          &middot; {{ popPcoaData.n_features_used }} {{ $t('data.features').toLowerCase() }}
          &middot; {{ popPcoaData.metric }}
        </span>
        <span v-if="popPcoaData.permanova" class="pcoa-permanova" :class="{ significant: popPcoaData.permanova.p_value < 0.05 }">
          PERMANOVA: F={{ popPcoaData.permanova.F }}, R&sup2;={{ popPcoaData.permanova.R2 }},
          p={{ popPcoaData.permanova.p_value < 0.001 ? '&lt; 0.001' : popPcoaData.permanova.p_value }}
          <span v-if="popPcoaData.permanova.p_value < 0.001" class="sig-star">***</span>
          <span v-else-if="popPcoaData.permanova.p_value < 0.01" class="sig-star">**</span>
          <span v-else-if="popPcoaData.permanova.p_value < 0.05" class="sig-star">*</span>
        </span>
      </div>
      <div ref="popPcoaChartEl" class="plotly-chart plotly-chart-pcoa"></div>
      <div v-if="loadingPopPcoa" class="loading">{{ $t('data.loadingPcoa') }}</div>
    </CollapsibleSection>

    <!-- Population table -->
    <CollapsibleSection class="section" v-if="filteredPopulation.length > 0" sid="population.populationTable" :default-open="false">
      <template #title>{{ $t('results.populationTable', { n: filteredPopulation.length }) }}</template>
      <table class="pop-table">
        <thead>
          <tr>
            <th class="col-basket"></th>
            <th>{{ $t('results.rank') }}</th>
            <th>{{ $t('results.auc') }}</th>
            <th>{{ $t('results.fit') }}</th>
            <th>{{ $t('results.accuracy') }}</th>
            <th>{{ $t('results.k') }}</th>
            <th>{{ $t('results.language') }}</th>
            <th>{{ $t('results.dataType') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="ind in paginatedPopulation" :key="ind.rank">
            <tr tabindex="0" @keydown.enter.self.prevent="toggleExpand(ind.rank)" @click="toggleExpand(ind.rank)" class="clickable-row" :class="{ 'module-filtered': moduleFilteredIndices && moduleFilteredIndices.has(ind.rank) }">
              <td class="col-basket" @click.stop>
                <button :aria-label="isInBasket(selectedJobId, ind.rank) ? $t('results.basketRemove') : basketFull ? $t('results.basketFull') : $t('results.basketAdd')"
                  class="btn-icon btn-basket"
                  :class="{ 'in-basket': isInBasket(selectedJobId, ind.rank) }"
                  :disabled="basketFull && !isInBasket(selectedJobId, ind.rank)"
                  :title="isInBasket(selectedJobId, ind.rank) ? $t('results.basketRemove') : basketFull ? $t('results.basketFull') : $t('results.basketAdd')"
                  @click.stop="toggleBasket(selectedJobId, selectedJobInfo?.name, ind)"
                >
                  <span v-if="isInBasket(selectedJobId, ind.rank)">&#9733;</span>
                  <span v-else>&#9734;</span>
                </button>
              </td>
              <td>
                {{ ind.rank + 1 }}
                <span v-if="moduleFilteredIndices && moduleFilteredIndices.has(ind.rank)" class="module-badge" :title="$t('results.ecoFbmFilterTitle')">M</span>
              </td>
              <td>{{ ind.metrics.auc?.toFixed(4) }}</td>
              <td>{{ ind.metrics.fit?.toFixed(4) }}</td>
              <td>{{ ind.metrics.accuracy?.toFixed(4) }}</td>
              <td>{{ ind.metrics.k }}</td>
              <td>{{ ind.metrics.language }}</td>
              <td>{{ ind.metrics.data_type }}</td>
            </tr>
            <tr v-if="expandedRank === ind.rank" class="detail-row">
              <td colspan="8">
                <div class="feature-list">
                  <div
                    v-for="[name, coef] in sortedFeatures(ind.named_features)"
                    :key="name"
                    class="feature-chip"
                    :class="{ positive: coef > 0, negative: coef < 0 }"
                  >
                    <span :title="name">{{ shortName(featureLabel(name)) }}</span> ({{ coef > 0 ? '+1' : '-1' }})
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <div class="pagination" v-if="filteredPopulation.length > popPageSize">
        <button @click="popPage = Math.max(0, popPage - 1)" :disabled="popPage === 0">&laquo; {{ $t('results.prev') }}</button>
        <span>{{ $t('results.page') }} {{ popPage + 1 }} / {{ Math.ceil(filteredPopulation.length / popPageSize) }}</span>
        <button @click="popPage++" :disabled="(popPage + 1) * popPageSize >= filteredPopulation.length">{{ $t('results.next') }} &raquo;</button>
      </div>
    </CollapsibleSection>
    <p v-if="population.length === 0" class="info-text">{{ $t('results.popNotAvailable') }}</p>
    <p v-else-if="filteredPopulation.length === 0" class="info-text">{{ $t('results.noModelsMatch') }}</p>
  </div>
</template>

<script setup>
import CollapsibleSection from '../../CollapsibleSection.vue'
import { shortFeatureName as shortName } from '../../../utils/chartLabels'
/**
 * "population" sub-tab of the Results view. Markup only: state and chart rendering
 * live in composables/useResultsTab.js, shared by every sub-tab through useResults().
 */
import { onMounted } from 'vue'
import { useResults } from '../../../composables/useResultsTab'

const {
  availableDataTypes,
  availableLanguages,
  basketFull,
  compositionChartEl,
  expandedRank,
  fbmCount,
  fbmEnabled,
  fbmMethod,
  featureHeatmapEl,
  featureLabel,
  featurePrevalenceEl,
  filteredPopulation,
  isInBasket,
  loadPopPcoa,
  loadingPopPcoa,
  metricsByTypeEl,
  moduleFilteredIndices,
  paginatedPopulation,
  popMetricsEl,
  popPage,
  popPageSize,
  popPcoaChartEl,
  popPcoaData,
  popPcoaDim,
  popPcoaMethod,
  popPcoaMetric,
  popPcoaShowEllipses,
  popTsnePerplexity,
  popUmapMinDist,
  popUmapNeighbors,
  population,
  renderPopPcoaChart,
  selectedDataTypes,
  selectedJobId,
  selectedJobInfo,
  selectedLanguages,
  sortedFeatures,
  toggleBasket,
  toggleExpand,
  topNModels,
  renderActiveTab,
} = useResults()

// The chunk for this tab loads on demand, so its chart containers exist only now.
onMounted(() => { renderActiveTab() })
</script>
