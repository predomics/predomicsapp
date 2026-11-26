<template>
  <div class="sub-content">
    <!-- Timing Flamegraph (debug mode only) -->
    <div v-if="debugMode && timingData" class="flamegraph-panel">
      <h3>{{ $t('results.timingFlamegraph') }}</h3>
      <div class="flamegraph-bar">
        <div
          v-for="(phase, i) in timingData.phases"
          :key="i"
          class="flamegraph-segment"
          :style="{ width: (phase.duration_s / timingData.wall_total_s * 100) + '%', background: flamegraphColors[i % flamegraphColors.length] }"
          :title="`${phase.label}: ${phase.duration_s}s (${(phase.duration_s / timingData.wall_total_s * 100).toFixed(1)}%)`"
        >
          <span v-if="phase.duration_s / timingData.wall_total_s > 0.08" class="flamegraph-label">{{ phase.label }}</span>
        </div>
      </div>
      <div class="flamegraph-legend">
        <div v-for="(phase, i) in timingData.phases" :key="i" class="flamegraph-legend-item">
          <span class="flamegraph-swatch" :style="{ background: flamegraphColors[i % flamegraphColors.length] }"></span>
          <span class="flamegraph-legend-label">{{ phase.label }}</span>
          <span class="flamegraph-legend-value">{{ phase.duration_s }}s ({{ (phase.duration_s / timingData.wall_total_s * 100).toFixed(1) }}%)</span>
        </div>
        <div class="flamegraph-total">{{ $t('results.totalWallTime') }}: {{ timingData.wall_total_s }}s</div>
      </div>
    </div>

    <div class="console-log-panel">
      <div class="console-header">
        <h3>{{ $t('results.consoleLog') }}</h3>
        <div class="console-actions">
          <button class="btn-sm btn-outline" @click="loadConsoleLog" :disabled="consoleLogLoading">
            {{ consoleLogLoading ? $t('results.loading') : $t('results.refresh') }}
          </button>
          <button class="btn-sm btn-outline" @click="copyConsoleLog" v-if="consoleLogContent">
            {{ consoleLogCopied ? $t('results.copied') : $t('results.copyLog') }}
          </button>
          <button class="btn-sm btn-outline" @click="downloadConsoleLog" v-if="consoleLogContent">
            {{ $t('results.downloadLog') }}
          </button>
        </div>
      </div>
      <div v-if="consoleLogLoading" class="loading">{{ $t('results.loadingResults') }}</div>
      <div v-else-if="consoleLogContent" class="console-log-viewer">
        <div class="console-log-info">
          <span>{{ consoleLogLines }} {{ $t('results.lines') }}</span>
          <span v-if="selectedJobInfo">{{ $t('results.status') }}: <strong :class="selectedJobInfo.status">{{ statusLabel(selectedJobInfo.status) }}</strong></span>
          <span v-if="selectedJobInfo?.duration_seconds">{{ $t('results.duration') }}: {{ formatDuration(selectedJobInfo.duration_seconds) }}</span>
        </div>
        <pre class="console-log-content" ref="consoleLogEl">{{ consoleLogContent }}</pre>
      </div>
      <div v-else class="empty">{{ $t('results.noLogsAvailable') }}</div>
    </div>
  </div>
</template>

<script setup>
/**
 * "console" sub-tab of the Results view. Markup only: state and chart rendering
 * live in composables/useResultsTab.js, shared by every sub-tab through useResults().
 */
import { onMounted } from 'vue'
import { useResults } from '../../../composables/useResultsTab'

const {
  consoleLogContent,
  consoleLogCopied,
  consoleLogEl,
  consoleLogLines,
  consoleLogLoading,
  copyConsoleLog,
  debugMode,
  downloadConsoleLog,
  flamegraphColors,
  formatDuration,
  loadConsoleLog,
  selectedJobInfo,
  statusLabel,
  timingData,
  renderActiveTab,
} = useResults()

// The chunk for this tab loads on demand, so its chart containers exist only now.
onMounted(() => { renderActiveTab() })
</script>
