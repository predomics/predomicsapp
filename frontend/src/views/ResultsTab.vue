<template>
  <div class="results-tab">
    <!-- Job selector -->
    <div class="job-selector" v-if="jobs.length > 0">
      <label>Job:
        <select v-model="selectedJobId" @change="loadJobResults">
          <option v-for="j in jobs" :key="j.job_id" :value="j.job_id">
            {{ j.job_id.slice(0, 8) }} &mdash; {{ j.status }}
            <template v-if="j.best_auc"> (AUC {{ j.best_auc.toFixed(4) }})</template>
          </option>
        </select>
      </label>
    </div>

    <!-- Sub-tabs -->
    <nav class="sub-tabs" v-if="detail">
      <button :class="{ active: subTab === 'summary' }" @click="subTab = 'summary'">Summary</button>
      <button :class="{ active: subTab === 'population' }" @click="subTab = 'population'">Population</button>
      <button :class="{ active: subTab === 'bestmodel' }" @click="subTab = 'bestmodel'">Best Model</button>
      <button :class="{ active: subTab === 'comparative' }" @click="subTab = 'comparative'">Comparative</button>
    </nav>

    <!-- Summary sub-tab -->
    <div v-if="detail && subTab === 'summary'" class="sub-content">
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

      <!-- Convergence chart placeholder -->
      <section class="section" v-if="generationTracking.length > 0">
        <h3>Convergence</h3>
        <div class="convergence-chart">
          <div class="chart-bars">
            <div
              v-for="g in generationTracking"
              :key="g.generation"
              class="chart-bar"
              :style="{ height: (g.best_auc * 100) + '%' }"
              :title="`Gen ${g.generation}: AUC ${g.best_auc.toFixed(4)}`"
            ></div>
          </div>
          <div class="chart-label">Generation &rarr;</div>
        </div>
      </section>
    </div>

    <!-- Best Model sub-tab -->
    <div v-if="detail && subTab === 'bestmodel'" class="sub-content">
      <section class="section" v-if="detail.best_individual">
        <h3>Best Model Metrics</h3>
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
    </div>

    <!-- Population sub-tab -->
    <div v-if="detail && subTab === 'population'" class="sub-content">
      <section class="section">
        <h3>Population of Models ({{ population.length }} individuals)</h3>
        <div v-if="population.length > 0">
          <table class="pop-table">
            <thead>
              <tr>
                <th>#</th>
                <th>AUC</th>
                <th>Fit</th>
                <th>Accuracy</th>
                <th>k</th>
                <th>Language</th>
                <th>Data Type</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="ind in paginatedPopulation" :key="ind.rank">
                <tr @click="toggleExpand(ind.rank)" class="clickable-row">
                  <td>{{ ind.rank + 1 }}</td>
                  <td>{{ ind.metrics.auc?.toFixed(4) }}</td>
                  <td>{{ ind.metrics.fit?.toFixed(4) }}</td>
                  <td>{{ ind.metrics.accuracy?.toFixed(4) }}</td>
                  <td>{{ ind.metrics.k }}</td>
                  <td>{{ ind.metrics.language }}</td>
                  <td>{{ ind.metrics.data_type }}</td>
                </tr>
                <tr v-if="expandedRank === ind.rank" class="detail-row">
                  <td colspan="7">
                    <div class="feature-list">
                      <div
                        v-for="(coef, name) in ind.named_features"
                        :key="name"
                        class="feature-chip"
                        :class="{ positive: coef > 0, negative: coef < 0 }"
                      >
                        {{ name }} ({{ coef > 0 ? '+1' : '-1' }})
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
          <div class="pagination" v-if="population.length > popPageSize">
            <button @click="popPage = Math.max(0, popPage - 1)" :disabled="popPage === 0">&laquo; Prev</button>
            <span>Page {{ popPage + 1 }} / {{ Math.ceil(population.length / popPageSize) }}</span>
            <button @click="popPage++" :disabled="(popPage + 1) * popPageSize >= population.length">Next &raquo;</button>
          </div>
        </div>
        <p v-else class="info-text">Population data not available for this job.</p>
      </section>
    </div>

    <!-- Comparative sub-tab -->
    <div v-if="detail && subTab === 'comparative'" class="sub-content">
      <section class="section">
        <h3>Comparative Analysis</h3>
        <p class="info-text">Multi-job comparison will be available in a future update.</p>
      </section>
    </div>

    <!-- Empty state -->
    <div v-if="!detail && jobs.length === 0" class="empty">
      No analysis jobs yet. Go to Settings &amp; Run to launch an analysis.
    </div>
    <div v-if="!detail && jobs.length > 0 && !loading" class="empty">
      Select a completed job above to view results.
    </div>
    <div v-if="loading" class="loading">Loading results...</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import axios from 'axios'

const route = useRoute()
const store = useProjectStore()

const loading = ref(false)
const detail = ref(null)
const population = ref([])
const generationTracking = ref([])
const subTab = ref('summary')
const selectedJobId = ref('')
const expandedRank = ref(null)
const popPage = ref(0)
const popPageSize = 50

const jobs = computed(() => {
  const allJobs = store.current?.jobs || []
  // If jobs are just strings (IDs), wrap them
  return allJobs.map(j => typeof j === 'string' ? { job_id: j, status: 'unknown' } : j)
})

const paginatedPopulation = computed(() => {
  const start = popPage.value * popPageSize
  return population.value.slice(start, start + popPageSize)
})

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

function toggleExpand(rank) {
  expandedRank.value = expandedRank.value === rank ? null : rank
}

async function loadJobResults() {
  if (!selectedJobId.value) return
  loading.value = true
  const pid = route.params.id
  const jid = selectedJobId.value

  try {
    const { data } = await axios.get(`/api/analysis/${pid}/jobs/${jid}/detail`)
    detail.value = data

    // Try to load extended results (population + tracking) from the results.json
    try {
      const { data: fullResults } = await axios.get(`/api/analysis/${pid}/jobs/${jid}/results`)
      population.value = fullResults.population || []
      generationTracking.value = fullResults.generation_tracking || []
    } catch {
      population.value = []
      generationTracking.value = []
    }
  } catch (e) {
    console.error('Failed to load results:', e)
    detail.value = null
  } finally {
    loading.value = false
  }
}

async function loadJobList() {
  const pid = route.params.id
  try {
    const { data } = await axios.get(`/api/analysis/${pid}/jobs`)
    // Store jobs in a local ref for the selector
    if (store.current) {
      store.current.jobs = data
    }
    // Auto-select from route param or first completed job
    const jobIdFromRoute = route.params.jobId
    if (jobIdFromRoute) {
      selectedJobId.value = jobIdFromRoute
    } else if (data.length > 0) {
      const completed = data.find(j => j.status === 'completed')
      if (completed) selectedJobId.value = completed.job_id
    }
    if (selectedJobId.value) loadJobResults()
  } catch (e) {
    console.error('Failed to load jobs:', e)
  }
}

watch(() => route.params.jobId, (newId) => {
  if (newId && newId !== selectedJobId.value) {
    selectedJobId.value = newId
    loadJobResults()
  }
})

onMounted(loadJobList)
</script>

<style scoped>
.job-selector {
  margin-bottom: 1rem;
}

.job-selector label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: #546e7a;
}

.job-selector select {
  padding: 0.4rem 0.6rem;
  border: 1px solid #cfd8dc;
  border-radius: 4px;
  font-size: 0.9rem;
  min-width: 300px;
}

.sub-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid #e0e0e0;
}

.sub-tabs button {
  padding: 0.5rem 1.25rem;
  border: none;
  background: none;
  color: #78909c;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}

.sub-tabs button.active {
  color: #1a1a2e;
  border-bottom-color: #1a1a2e;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
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

.section h3 { margin-bottom: 1rem; }
.section h4 { margin: 1.5rem 0 0.75rem; color: #546e7a; }

.metrics-table { width: 100%; max-width: 400px; }
.metrics-table td { padding: 0.4rem 0; border-bottom: 1px solid #eceff1; }
.metric-name { color: #78909c; font-size: 0.9rem; }
.metric-value { text-align: right; font-weight: 600; }

.feature-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.feature-chip { padding: 0.35rem 0.75rem; border-radius: 20px; font-size: 0.85rem; font-weight: 500; }
.feature-chip.positive { background: #e8f5e9; color: #2e7d32; }
.feature-chip.negative { background: #fce4ec; color: #c62828; }

.convergence-chart {
  padding: 1rem 0;
}

.chart-bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 150px;
  border-bottom: 1px solid #e0e0e0;
}

.chart-bar {
  flex: 1;
  background: #1a1a2e;
  border-radius: 2px 2px 0 0;
  min-width: 3px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.chart-bar:hover { opacity: 0.7; }

.chart-label {
  text-align: center;
  color: #90a4ae;
  font-size: 0.75rem;
  margin-top: 0.5rem;
}

.pop-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.pop-table th {
  text-align: left;
  padding: 0.5rem;
  border-bottom: 2px solid #e0e0e0;
  color: #546e7a;
  font-weight: 600;
}

.pop-table td {
  padding: 0.5rem;
  border-bottom: 1px solid #eceff1;
}

.clickable-row { cursor: pointer; }
.clickable-row:hover { background: #f5f7fa; }

.detail-row td {
  background: #fafafa;
  padding: 1rem;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-top: 1rem;
  font-size: 0.85rem;
}

.pagination button {
  padding: 0.3rem 0.75rem;
  border: 1px solid #cfd8dc;
  border-radius: 4px;
  background: white;
  cursor: pointer;
}

.pagination button:disabled { opacity: 0.5; cursor: not-allowed; }

.info-text { color: #90a4ae; font-size: 0.85rem; font-style: italic; }
.empty { text-align: center; padding: 3rem; color: #90a4ae; }
.loading { text-align: center; padding: 3rem; color: #90a4ae; }
</style>
