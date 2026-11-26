<template>
  <div class="dashboard">
    <h2>{{ $t('dashboard.title') }}</h2>

    <AsyncState :loading="loading" :error="error" :retry="run" :loading-text="$t('dashboard.loading')">
      <!-- Summary cards -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value">{{ data.projects ?? 0 }}</div>
          <div class="stat-label">{{ $t('dashboard.projects') }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ data.datasets ?? 0 }}</div>
          <div class="stat-label">{{ $t('dashboard.datasets') }}</div>
        </div>
        <div class="stat-card stat-running" v-if="data.running_jobs > 0">
          <div class="stat-value">{{ data.running_jobs }}</div>
          <div class="stat-label">{{ $t('dashboard.runningJobs') }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ data.completed_jobs ?? 0 }}</div>
          <div class="stat-label">{{ $t('dashboard.completed') }}</div>
        </div>
        <div class="stat-card" v-if="data.failed_jobs > 0">
          <div class="stat-value stat-failed"><span aria-hidden="true">&#10007; </span>{{ data.failed_jobs }}</div>
          <div class="stat-label">{{ $t('dashboard.failed') }}</div>
        </div>
        <div class="stat-card" v-if="data.shared_with_me > 0">
          <div class="stat-value">{{ data.shared_with_me }}</div>
          <div class="stat-label">{{ $t('dashboard.sharedWithMe') }}</div>
        </div>
      </div>

      <div class="dashboard-grid">
        <!-- Active Jobs -->
        <section class="card" v-if="data.active_jobs?.length > 0">
          <h3>{{ $t('dashboard.activeJobs') }}</h3>
          <div class="job-list">
            <div v-for="j in data.active_jobs" :key="j.job_id" class="job-row">
              <span class="status-badge" :class="j.status"><span aria-hidden="true">{{ statusGlyph(j.status) }}</span> {{ statusLabel(j.status) }}</span>
              <router-link :to="`/project/${j.project_id}/results/${j.job_id}`" class="job-name">
                {{ j.name || j.job_id.slice(0, 8) }}
              </router-link>
              <span class="job-time">{{ timeAgo(j.created_at) }}</span>
            </div>
          </div>
        </section>

        <!-- Recent Completions -->
        <section class="card" v-if="data.recent_completions?.length > 0">
          <h3>{{ $t('dashboard.recentCompletions') }}</h3>
          <table class="mini-table">
            <thead>
              <tr>
                <th scope="col">{{ $t('dashboard.job') }}</th>
                <th scope="col">{{ $t('dashboard.bestScore') }}</th>
                <th scope="col">{{ $t('dashboard.k') }}</th>
                <th scope="col">{{ $t('dashboard.completedAt') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="j in data.recent_completions" :key="j.job_id">
                <td>
                  <router-link :to="`/project/${j.project_id}/results/${j.job_id}`">
                    {{ j.name || j.job_id.slice(0, 8) }}
                  </router-link>
                </td>
                <td>{{ j.best_auc != null ? Number(j.best_auc).toFixed(4) : '—' }}</td>
                <td>{{ j.best_k || '—' }}</td>
                <td>{{ timeAgo(j.completed_at) }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <!-- Activity Feed -->
        <section class="card" v-if="data.activity?.length > 0">
          <h3>{{ $t('dashboard.recentActivity') }}</h3>
          <div class="activity-feed">
            <div v-for="(a, i) in data.activity" :key="i" class="activity-item">
              <span class="activity-action">{{ formatAction(a.action) }}</span>
              <span class="activity-resource" v-if="a.resource_type">{{ a.resource_type }}</span>
              <span class="activity-time">{{ timeAgo(a.created_at) }}</span>
            </div>
          </div>
        </section>
      </div>

      <div v-if="!data.projects" class="empty-state">
        <p>{{ $t('dashboard.noProjects') }} <router-link to="/projects">{{ $t('dashboard.createFirst') }}</router-link> {{ $t('dashboard.toGetStarted') }}</p>
      </div>
    </AsyncState>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import AsyncState from '../components/AsyncState.vue'
import { useAsync } from '../composables/useAsync'
import { timeAgo } from '../utils/time'
import { statusLabel, statusGlyph } from '../utils/jobStatus'

const data = ref({})

const { loading, error, run } = useAsync(async () => {
  const resp = await api.dashboard.get()
  data.value = resp.data || {}
})
loading.value = true

onMounted(run)

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

.stat-running .stat-value { color: var(--warning-dark); }
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
  font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
}
.status-badge.running { background: var(--warning-bg); color: var(--warning-dark); }
.status-badge.pending { background: var(--info-bg); color: var(--info); }
.status-badge.completed { background: var(--success-bg); color: var(--success-dark); }
.status-badge.failed { background: var(--danger-bg); color: var(--danger); }

.mini-table {
  width: 100%; border-collapse: collapse; font-size: 0.8rem;
}
.mini-table th, .mini-table td {
  padding: 0.4rem 0.5rem; text-align: left;
  border-bottom: 1px solid var(--border-light);
}
.mini-table th {
  font-size: 0.75rem; text-transform: uppercase;
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
  font-size: 0.75rem;
}
.activity-time { margin-left: auto; color: var(--text-muted); font-size: 0.75rem; }

.loading { text-align: center; padding: 2rem; color: var(--text-muted); }
.error-msg { color: var(--danger); text-align: center; padding: 1rem; }
.empty-state { text-align: center; padding: 3rem; color: var(--text-muted); }
.empty-state a { color: var(--accent); }
</style>
