<template>
  <div class="results">
    <h2>Results</h2>

    <!-- Console output -->
    <section class="console-section" v-if="showConsole">
      <div class="console-header">
        <h3>Console Output</h3>
        <span class="status-badge" :class="jobStatus">{{ jobStatus }}</span>
      </div>
      <div class="console" ref="consoleEl">
        <pre>{{ logContent || 'Waiting for output...' }}</pre>
      </div>
    </section>

    <!-- Loading -->
    <div v-if="loading && !showConsole" class="loading">Loading results...</div>

    <!-- Detail view -->
    <template v-if="detail">
      <div class="summary-grid">
        <div class="stat-card">
          <div class="stat-value">{{ detail.best_auc?.toFixed(4) || '—' }}</div>
          <div class="stat-label">Best AUC</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ detail.best_k || '—' }}</div>
          <div class="stat-label">Features (k)</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ detail.execution_time?.toFixed(1) }}s</div>
          <div class="stat-label">Time</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ detail.generation_count }}</div>
          <div class="stat-label">Generations</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ detail.feature_count }}</div>
          <div class="stat-label">Total Features</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ detail.sample_count }}</div>
          <div class="stat-label">Samples</div>
        </div>
      </div>

      <!-- Best model -->
      <section class="section" v-if="detail.best_individual">
        <h3>Best Model</h3>
        <table class="metrics-table">
          <tr v-for="(val, key) in bestMetrics" :key="key">
            <td class="metric-name">{{ key }}</td>
            <td class="metric-value">{{ typeof val === 'number' ? val.toFixed(4) : val }}</td>
          </tr>
        </table>

        <h4>Selected Features</h4>
        <div class="feature-list">
          <div
            v-for="(coef, idx) in detail.best_individual.features"
            :key="idx"
            class="feature-chip"
            :class="{ positive: coef > 0, negative: coef < 0 }"
          >
            {{ featureName(idx) }} ({{ coef > 0 ? '+1' : '-1' }})
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'

const route = useRoute()
const loading = ref(true)
const detail = ref(null)
const logContent = ref('')
const jobStatus = ref('pending')
const showConsole = ref(true)
const consoleEl = ref(null)
let pollTimer = null

const bestMetrics = computed(() => {
  if (!detail.value?.best_individual) return {}
  const b = detail.value.best_individual
  return {
    AUC: b.auc,
    Fit: b.fit,
    Accuracy: b.accuracy,
    Sensitivity: b.sensitivity,
    Specificity: b.specificity,
    Threshold: b.threshold,
    Language: b.language,
    'Data Type': b.data_type,
    Epoch: b.epoch,
  }
})

function featureName(idx) {
  if (detail.value?.feature_names?.length > idx) {
    return detail.value.feature_names[idx]
  }
  return `feature_${idx}`
}

async function pollLogs() {
  const pid = route.params.id
  const jid = route.params.jobId
  try {
    const { data } = await axios.get(`/api/analysis/${pid}/jobs/${jid}/logs`)
    logContent.value = data.log
    jobStatus.value = data.status

    // Auto-scroll console
    await nextTick()
    if (consoleEl.value) {
      consoleEl.value.scrollTop = consoleEl.value.scrollHeight
    }

    // If completed, fetch detail results and stop polling
    if (data.status === 'completed' || data.status === 'failed') {
      stopPolling()
      if (data.status === 'completed') {
        try {
          const { data: d } = await axios.get(`/api/analysis/${pid}/jobs/${jid}/detail`)
          detail.value = d
        } catch (e) {
          console.error('Failed to fetch detail:', e)
        }
      }
      loading.value = false
    }
  } catch (e) {
    console.error('Failed to poll logs:', e)
  }
}

function startPolling() {
  pollLogs()
  pollTimer = setInterval(pollLogs, 1000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(() => {
  loading.value = false
  startPolling()
})

onUnmounted(stopPolling)
</script>

<style scoped>
.console-section {
  margin-bottom: 2rem;
}

.console-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.console-header h3 {
  color: #1a1a2e;
}

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge.pending {
  background: #fff3e0;
  color: #e65100;
}

.status-badge.running {
  background: #e3f2fd;
  color: #1565c0;
}

.status-badge.completed {
  background: #e8f5e9;
  color: #2e7d32;
}

.status-badge.failed {
  background: #fce4ec;
  color: #c62828;
}

.console {
  background: #1a1a2e;
  color: #e0e0e0;
  border-radius: 8px;
  padding: 1rem;
  max-height: 500px;
  overflow-y: auto;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 0.8rem;
  line-height: 1.5;
}

.console pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: white;
  padding: 1.25rem;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  text-align: center;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1a1a2e;
}

.stat-label {
  font-size: 0.8rem;
  color: #90a4ae;
  margin-top: 0.25rem;
}

.section {
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  margin-bottom: 1.5rem;
}

.section h3 {
  margin-bottom: 1rem;
}

.section h4 {
  margin: 1.5rem 0 0.75rem;
  color: #546e7a;
}

.metrics-table {
  width: 100%;
  max-width: 400px;
}

.metrics-table td {
  padding: 0.4rem 0;
  border-bottom: 1px solid #eceff1;
}

.metric-name {
  color: #78909c;
  font-size: 0.9rem;
}

.metric-value {
  text-align: right;
  font-weight: 600;
}

.feature-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.feature-chip {
  padding: 0.35rem 0.75rem;
  border-radius: 20px;
  font-size: 0.85rem;
  font-weight: 500;
}

.feature-chip.positive {
  background: #e8f5e9;
  color: #2e7d32;
}

.feature-chip.negative {
  background: #fce4ec;
  color: #c62828;
}

.loading {
  text-align: center;
  padding: 3rem;
  color: #90a4ae;
}
</style>
