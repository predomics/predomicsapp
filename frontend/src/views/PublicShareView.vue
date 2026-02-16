<template>
  <div class="public-view">
    <div class="public-header">
      <h1>{{ $t('publicShare.appTitle') }}</h1>
      <span class="public-badge">{{ $t('publicShare.publicView') }}</span>
    </div>

    <div v-if="loading" class="loading">{{ $t('publicShare.loadingResults') }}</div>
    <div v-else-if="error" class="error-box">{{ error }}</div>

    <template v-else-if="projectData">
      <div class="project-info">
        <h2>{{ projectData.project.name }}</h2>
        <p v-if="projectData.project.description" class="project-desc">{{ projectData.project.description }}</p>
      </div>

      <!-- Job list -->
      <div class="jobs-section" v-if="projectData.jobs.length > 0">
        <h3>{{ $t('publicShare.completedJobs') }}</h3>
        <div class="job-cards">
          <div
            v-for="j in projectData.jobs" :key="j.job_id"
            class="job-card"
            :class="{ selected: selectedJobId === j.job_id }"
            @click="selectJob(j.job_id)"
          >
            <div class="job-name">{{ j.name || j.job_id.slice(0, 8) }}</div>
            <div class="job-metrics">
              <span v-if="j.best_auc != null">{{ $t('publicShare.auc') }} {{ j.best_auc.toFixed(4) }}</span>
              <span v-if="j.best_k != null">{{ $t('publicShare.k') }} {{ j.best_k }}</span>
            </div>
            <div class="job-date">{{ formatDate(j.completed_at) }}</div>
          </div>
        </div>
      </div>

      <!-- Selected job results -->
      <div v-if="jobResults" class="results-section">
        <h3>{{ $t('publicShare.results') }}</h3>

        <!-- Summary metrics -->
        <div class="metrics-grid">
          <div class="metric-card" v-if="best.auc != null">
            <div class="metric-value">{{ best.auc.toFixed(4) }}</div>
            <div class="metric-label">{{ $t('publicShare.aucLabel') }}</div>
          </div>
          <div class="metric-card" v-if="best.accuracy != null">
            <div class="metric-value">{{ best.accuracy.toFixed(4) }}</div>
            <div class="metric-label">{{ $t('publicShare.accuracyLabel') }}</div>
          </div>
          <div class="metric-card" v-if="best.sensitivity != null">
            <div class="metric-value">{{ best.sensitivity.toFixed(4) }}</div>
            <div class="metric-label">{{ $t('publicShare.sensitivityLabel') }}</div>
          </div>
          <div class="metric-card" v-if="best.specificity != null">
            <div class="metric-value">{{ best.specificity.toFixed(4) }}</div>
            <div class="metric-label">{{ $t('publicShare.specificityLabel') }}</div>
          </div>
          <div class="metric-card" v-if="best.k != null">
            <div class="metric-value">{{ best.k }}</div>
            <div class="metric-label">{{ $t('publicShare.featuresK') }}</div>
          </div>
          <div class="metric-card" v-if="best.language">
            <div class="metric-value">{{ best.language }}</div>
            <div class="metric-label">{{ $t('publicShare.languageLabel') }}</div>
          </div>
        </div>

        <!-- Feature coefficients -->
        <div v-if="bestFeatures.length > 0" class="features-section">
          <h4>{{ $t('publicShare.modelFeatures') }}</h4>
          <div class="feature-chips">
            <span
              v-for="f in bestFeatures" :key="f.name"
              class="feature-chip"
              :class="f.coef > 0 ? 'positive' : 'negative'"
            >
              {{ f.name }} ({{ f.coef > 0 ? '+' : '' }}{{ f.coef }})
            </span>
          </div>
        </div>
      </div>

      <div v-if="jobLoading" class="loading">{{ $t('publicShare.loadingJobResults') }}</div>
    </template>

    <div class="public-footer">
      {{ $t('publicShare.sharedVia') }} — {{ $t('publicShare.footerSubtitle') }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const route = useRoute()
const token = computed(() => route.params.token)

const loading = ref(true)
const error = ref('')
const projectData = ref(null)
const selectedJobId = ref('')
const jobResults = ref(null)
const jobLoading = ref(false)

const best = computed(() => jobResults.value?.best_individual || {})
const bestFeatures = computed(() => {
  if (!jobResults.value) return []
  const features = best.value.features || {}
  const names = jobResults.value.feature_names || []
  return Object.entries(features)
    .sort(([a], [b]) => parseInt(a) - parseInt(b))
    .map(([idx, coef]) => ({
      name: names[parseInt(idx)] || `feature_${idx}`,
      coef: parseInt(coef),
    }))
})

async function loadProject() {
  loading.value = true
  try {
    const { data } = await axios.get(`/api/public/${token.value}`)
    projectData.value = data
    // Auto-select first job
    if (data.jobs.length > 0) {
      selectJob(data.jobs[0].job_id)
    }
  } catch (e) {
    error.value = e.response?.data?.detail || t('publicShare.invalidLink')
  } finally {
    loading.value = false
  }
}

async function selectJob(jobId) {
  selectedJobId.value = jobId
  jobLoading.value = true
  jobResults.value = null
  try {
    const { data } = await axios.get(`/api/public/${token.value}/jobs/${jobId}/results`)
    jobResults.value = data
  } catch (e) {
    console.error('Failed to load job results:', e)
  } finally {
    jobLoading.value = false
  }
}

function formatDate(isoStr) {
  if (!isoStr) return ''
  return new Date(isoStr).toLocaleDateString()
}

onMounted(loadProject)
</script>

<style scoped>
.public-view {
  max-width: 900px;
  margin: 0 auto;
  padding: 2rem 1rem;
}

.public-header {
  display: flex; align-items: center; gap: 0.75rem;
  margin-bottom: 2rem;
}
.public-header h1 {
  font-size: 1.5rem; color: var(--accent); margin: 0;
}
.public-badge {
  background: var(--info-bg); color: var(--info);
  padding: 0.2rem 0.6rem; border-radius: 10px;
  font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
}

.project-info { margin-bottom: 1.5rem; }
.project-info h2 { margin: 0 0 0.3rem; color: var(--text-primary); }
.project-desc { color: var(--text-muted); font-size: 0.9rem; }

.jobs-section h3 { margin-bottom: 0.75rem; font-size: 1rem; }
.job-cards {
  display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1.5rem;
}
.job-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 0.75rem 1rem;
  cursor: pointer; transition: all 0.2s; min-width: 180px;
}
.job-card:hover { border-color: var(--accent); }
.job-card.selected { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent); }
.job-name { font-weight: 600; font-size: 0.9rem; margin-bottom: 0.3rem; }
.job-metrics { font-size: 0.8rem; color: var(--accent); display: flex; gap: 0.75rem; }
.job-date { font-size: 0.7rem; color: var(--text-muted); margin-top: 0.2rem; }

.results-section h3 { margin-bottom: 0.75rem; }

.metrics-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 0.5rem; margin-bottom: 1.5rem;
}
.metric-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 0.75rem; text-align: center;
}
.metric-value { font-size: 1.3rem; font-weight: 700; color: var(--accent); }
.metric-label { font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; }

.features-section { margin-bottom: 1.5rem; }
.features-section h4 { margin-bottom: 0.5rem; font-size: 0.95rem; }
.feature-chips { display: flex; flex-wrap: wrap; gap: 0.3rem; }
.feature-chip {
  display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px;
  font-size: 0.8rem;
}
.feature-chip.positive {
  background: rgba(0,191,255,0.12); border: 1px solid rgba(0,191,255,0.3); color: #00BFFF;
}
.feature-chip.negative {
  background: rgba(255,48,48,0.12); border: 1px solid rgba(255,48,48,0.3); color: #FF3030;
}

.loading { text-align: center; padding: 3rem; color: var(--text-muted); }
.error-box {
  background: var(--danger-bg); color: var(--danger);
  padding: 1.5rem; border-radius: 8px; text-align: center;
}

.public-footer {
  margin-top: 3rem; padding-top: 1rem;
  border-top: 1px solid var(--border-light);
  text-align: center; font-size: 0.75rem; color: var(--text-muted);
}
</style>
