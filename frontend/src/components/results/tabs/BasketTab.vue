<template>
  <div class="sub-content">
    <p v-if="basketCount === 0" class="info-text">
      {{ $t('results.basketEmpty') }}
    </p>

    <template v-if="basketCount > 0">
      <div class="basket-header">
        <span class="basket-count-label">
          {{ $t('results.basketCount', { n: basketCount, max: MAX_BASKET_SIZE }) }}
        </span>
        <button class="btn-sm btn-outline" @click="confirmClearBasket">
          {{ $t('results.basketClearAll') }}
        </button>
      </div>

      <!-- Basket models table -->
      <CollapsibleSection class="section" sid="basket.basketModels" :default-open="false">
        <template #title>{{ $t('results.basketModels') }}</template>
        <table class="pop-table">
          <thead>
            <tr>
              <th style="width:30px"></th>
              <th>{{ $t('results.colName') }}</th>
              <th>{{ $t('results.rank') }}</th>
              <th>{{ $t('results.auc') }}</th>
              <th>{{ $t('results.fit') }}</th>
              <th>{{ $t('results.accuracy') }}</th>
              <th>{{ $t('results.sensitivity') }}</th>
              <th>{{ $t('results.specificity') }}</th>
              <th>{{ $t('results.k') }}</th>
              <th>{{ $t('results.language') }}</th>
              <th>{{ $t('results.dataType') }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="item in basketItems" :key="item.id">
              <tr tabindex="0" @keydown.enter.self.prevent="toggleBasketExpand(item.id)" @click="toggleBasketExpand(item.id)" class="clickable-row">
                <td @click.stop>
                  <button :aria-label="$t('results.basketRemove')" class="btn-icon btn-delete" @click.stop="removeFromBasket(item.id)" :title="$t('results.basketRemove')">
                    <SvgIcon name="x" :size="12" />
                  </button>
                </td>
                <td :title="item.jobId">{{ item.jobName }}</td>
                <td>{{ item.rank + 1 }}</td>
                <td>{{ item.metrics.auc?.toFixed(4) }}</td>
                <td>{{ item.metrics.fit?.toFixed(4) }}</td>
                <td>{{ item.metrics.accuracy?.toFixed(4) }}</td>
                <td>{{ item.metrics.sensitivity?.toFixed(4) }}</td>
                <td>{{ item.metrics.specificity?.toFixed(4) }}</td>
                <td>{{ item.metrics.k }}</td>
                <td>{{ item.metrics.language }}</td>
                <td>{{ item.metrics.data_type }}</td>
              </tr>
              <tr v-if="basketExpandedId === item.id" class="detail-row">
                <td colspan="11">
                  <div class="feature-list">
                    <div
                      v-for="[name, coef] in sortedFeatures(item.named_features)"
                      :key="name"
                      class="feature-chip"
                      :class="{ positive: coef > 0, negative: coef < 0 }"
                    >
                      <span :title="name">{{ shortName(featureLabel(name)) }}</span> ({{ coef > 0 ? '+' : '' }}{{ coef }})
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </CollapsibleSection>

      <!-- Metrics comparison chart (needs >= 2 models) -->
      <CollapsibleSection class="section" v-if="basketCount >= 2" sid="basket.basketMetricsComparison">
        <template #title>{{ $t('results.basketMetricsComparison') }}</template>
        <div ref="basketMetricsChartEl" class="plotly-chart"></div>
      </CollapsibleSection>

      <!-- Feature overlap -->
      <CollapsibleSection class="section" v-if="basketCount >= 2" sid="basket.basketFeatureOverlap">
        <template #title>{{ $t('results.basketFeatureOverlap') }}</template>
        <div class="basket-feature-stats">
          <span class="stat-pill">{{ $t('results.commonToAll') }}: {{ basketFeatureIntersection.length }}</span>
          <span class="stat-pill">{{ $t('results.unionAny') }}: {{ basketFeatureUnion.length }}</span>
          <span class="stat-pill" v-if="basketFeatureUnion.length > 0">{{ $t('results.overlapRatio') }}: {{ (basketFeatureIntersection.length / basketFeatureUnion.length * 100).toFixed(1) }}%</span>
        </div>
        <div v-if="basketFeatureIntersection.length > 0" class="basket-consensus">
          <strong>{{ $t('results.basketConsensusFeatures') }}</strong>
          <span v-for="f in basketFeatureIntersection" :key="f" class="feature-chip positive"><span :title="f">{{ shortName(featureLabel(f)) }}</span></span>
        </div>
        <div ref="basketFeatureOverlapEl" class="plotly-chart"></div>
      </CollapsibleSection>

      <!-- Coefficient heatmap -->
      <CollapsibleSection class="section" v-if="basketCount >= 2" sid="basket.basketCoefficientHeatmap">
        <template #title>{{ $t('results.basketCoefficientHeatmap') }}</template>
        <div ref="basketHeatmapEl" class="plotly-chart"></div>
      </CollapsibleSection>
    </template>
  </div>
</template>

<script setup>
import CollapsibleSection from '../../CollapsibleSection.vue'
import { shortFeatureName as shortName } from '../../../utils/chartLabels'
/**
 * "basket" sub-tab of the Results view. Markup only: state and chart rendering
 * live in composables/useResultsTab.js, shared by every sub-tab through useResults().
 */
import { onMounted } from 'vue'
import { useResults } from '../../../composables/useResultsTab'
import SvgIcon from '../../SvgIcon.vue'

const {
  MAX_BASKET_SIZE,
  basketCount,
  basketExpandedId,
  basketFeatureIntersection,
  basketFeatureOverlapEl,
  basketFeatureUnion,
  basketHeatmapEl,
  basketItems,
  basketMetricsChartEl,
  confirmClearBasket,
  featureLabel,
  removeFromBasket,
  sortedFeatures,
  toggleBasketExpand,
  renderActiveTab,
} = useResults()

// The chunk for this tab loads on demand, so its chart containers exist only now.
onMounted(() => { renderActiveTab() })
</script>
