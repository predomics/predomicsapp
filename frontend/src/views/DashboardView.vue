<template>
  <div class="dashboard">
    <h2>Dashboard</h2>

    <!-- Summary cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{{ data.projects }}</div>
        <div class="stat-label">Projects</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ data.datasets }}</div>
        <div class="stat-label">Datasets</div>
      </div>
      <div class="stat-card stat-running" v-if="data.running_jobs > 0">
        <div class="stat-value">{{ data.running_jobs }}</div>
        <div class="stat-label">Running Jobs</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ data.completed_jobs }}</div>
        <div class="stat-label">Completed</div>
      </div>
      <div class="stat-card" v-if="data.failed_jobs > 0">
        <div class="stat-value stat-failed">{{ data.failed_jobs }}</div>
        <div class="stat-label">Failed</div>
      </div>
      <div class="stat-card" v-if="data.shared_with_me > 0">
        <div class="stat-value">{{ data.shared_with_me }}</div>
        <div class="stat-label">Shared With Me</div>
      </div>
    </div>

    <div class="dashboard-grid">
      <!-- Active Jobs -->
      <section class="card" v-if="data.active_jobs?.length > 0">
        <h3>Active Jobs</h3>
        <div class="job-list">
          <div v-for="j in data.active_jobs" :key="j.job_id" class="job-row">
            <span class="status-badge" :class="j.status">{{ j.status }}</span>
            <router-link :to="`/project/${j.project_id}/results/${j.job_id}`" class="job-name">
              {{ j.name || j.job_id.slice(0, 8) }}
            </router-link>
            <span class="job-time">{{ timeAgo(j.created_at) }}</span>
          </div>
        </div>
      </section>

      <!-- Recent Completions -->
      <section class="card" v-if="data.recent_completions?.length > 0">
        <h3>Recent Completions</h3>
        <table class="mini-table">
          <thead>
            <tr><th>Job</th><th>AUC</th><th>k</th><th>Completed</th></tr>
          </thead>
          <tbody>
            <tr v-for="j in data.recent_completions" :key="j.job_id">
              <td>
                <router-link :to="`/project/${j.project_id}/results/${j.job_id}`">
                  {{ j.name || j.job_id.slice(0, 8) }}
                </router-link>
              </td>
              <td>{{ j.best_auc?.toFixed(4) || '—' }}</td>
              <td>{{ j.best_k || '—' }}</td>
              <td>{{ timeAgo(j.completed_at) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Activity Feed -->
      <section class="card" v-if="data.activity?.length > 0">
        <h3>Recent Activity</h3>
        <div class="activity-feed">
          <div v-for="(a, i) in data.activity" :key="i" class="activity-item">
            <span class="activity-action">{{ formatAction(a.action) }}</span>
            <span class="activity-resource" v-if="a.resource_type">{{ a.resource_type }}</span>
            <span class="activity-time">{{ timeAgo(a.created_at) }}</span>
          </div>
        </div>
      </section>
    </div>

    <div v-if="loading" class="loading">Loading dashboard...</div>
    <div v-if="error" class="error-msg">{{ error }}</div>
    <div v-if="!loading && !data.projects && !error" class="empty-state">
      <p>No projects yet. <router-link to="/projects">Create your first project</router-link> to get started.</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const data = ref({})
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const resp = await axios.get('/api/dashboard/')
    data.value = resp.data
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
})

function timeAgo(isoStr) {
  if (!isoStr) return ''
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function formatAction(action) {
  return (action || '').replace(/[._]/g, ' ')
}
</script>

<style scoped>
.dashboard h2 {
  margin-bottom: 1.25rem;
  color: var(--text-primary);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem;
  text-align: center;
  box-shadow: var(--shadow);
}

.stat-value {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--accent);
}

.stat-running .stat-value { color: var(--warning); }
.stat-failed { color: var(--danger) !important; }

.stat-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 0.2rem;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 1rem;
}

.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.25rem;
  box-shadow: var(--shadow);
}

.card h3 {
  font-size: 1rem;
  margin-bottom: 0.75rem;
  color: var(--text-primary);
}

.job-list { display: flex; flex-direction: column; gap: 0.5rem; }
.job-row {
  display: flex; align-items: center; gap: 0.5rem;
  font-size: 0.85rem;
}
.job-name {
  color: var(--accent); text-decoration: none;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.job-name:hover { text-decoration: underline; }
.job-time { margin-left: auto; color: var(--text-muted); font-size: 0.75rem; }

.status-badge {
  display: inline-block; padding: 0.15rem 0.5rem; border-radius: 10px;
  font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
}
.status-badge.running { background: var(--warning-bg); color: var(--warning); }
.status-badge.pending { background: var(--info-bg); color: var(--info); }
.status-badge.completed { background: var(--success-bg); color: var(--success); }
.status-badge.failed { background: var(--danger-bg); color: var(--danger); }

.mini-table {
  width: 100%; border-collapse: collapse; font-size: 0.8rem;
}
.mini-table th, .mini-table td {
  padding: 0.4rem 0.5rem; text-align: left;
  border-bottom: 1px solid var(--border-light);
}
.mini-table th {
  font-size: 0.7rem; text-transform: uppercase;
  color: var(--text-muted); font-weight: 600;
}
.mini-table a {
  color: var(--accent); text-decoration: none;
}
.mini-table a:hover { text-decoration: underline; }

.activity-feed { display: flex; flex-direction: column; gap: 0.4rem; }
.activity-item {
  display: flex; align-items: center; gap: 0.5rem;
  font-size: 0.8rem; color: var(--text-secondary);
}
.activity-action { font-weight: 500; text-transform: capitalize; }
.activity-resource {
  background: var(--bg-badge); padding: 0.1rem 0.4rem; border-radius: 4px;
  font-size: 0.7rem;
}
.activity-time { margin-left: auto; color: var(--text-muted); font-size: 0.7rem; }

.loading { text-align: center; padding: 2rem; color: var(--text-muted); }
.error-msg { color: var(--danger); text-align: center; padding: 1rem; }
.empty-state { text-align: center; padding: 3rem; color: var(--text-muted); }
.empty-state a { color: var(--accent); }
</style>
