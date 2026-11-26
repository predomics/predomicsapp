<template>
  <div
    class="project-card"
    :class="{ selected, shared: isShared, archived: project.archived }"
  >
    <button type="button" class="card-main" :aria-label="$t('projects.openNamed', { name: project.name })" @click="$emit('open')">
      <span class="card-top">
        <span class="card-name">{{ project.name }}</span>
        <span v-if="project.latest_job_status" class="status-dot" :class="project.latest_job_status" :title="statusLabel(project.latest_job_status)">
          <span class="sr-only">{{ statusLabel(project.latest_job_status) }}</span>
        </span>
      </span>
      <span class="card-meta">
        <span class="time">{{ timeAgo(project.updated_at || project.created_at) }}</span>
        <span v-if="project.archived" class="archived-tag">{{ $t('projects.archivedTag') }}</span>
      </span>
      <span class="card-badges">
        <span class="badge badge-dataset" v-if="datasetCount > 0">{{ datasetCount }} {{ $t('components.dataset', datasetCount) }}</span>
        <span class="badge badge-job" v-if="jobCount > 0">{{ jobCount }} {{ $t('components.job', jobCount) }}</span>
        <span class="badge badge-share" v-if="shareCount > 0">{{ shareCount }} {{ $t('components.shared') }}</span>
        <span v-if="isShared" class="badge badge-role">{{ project.role }}</span>
      </span>
    </button>
    <button
      type="button"
      class="card-details"
      :aria-pressed="selected ? 'true' : 'false'"
      :title="$t('projects.detailsNamed', { name: project.name })"
      :aria-label="$t('projects.detailsNamed', { name: project.name })"
      @click="$emit('select')"
    ><span aria-hidden="true">&#8943;</span></button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { timeAgo } from '../../utils/time'
import { statusLabel } from '../../utils/jobStatus'

const props = defineProps({
  project: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  isShared: { type: Boolean, default: false },
})

defineEmits(['select', 'open'])

const datasetCount = computed(() => props.project.datasets?.length || 0)
const jobCount = computed(() => props.project.job_count || props.project.jobs?.length || 0)
const shareCount = computed(() => props.project.share_count || 0)
</script>

<style scoped>
.project-card {
  padding: 0.75rem 1rem;
  border-radius: var(--card-radius, 12px);
  background: var(--bg-card);
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.15s ease;
  box-shadow: var(--card-shadow, 0 1px 3px rgba(0,0,0,0.06));
}

.project-card:hover {
  box-shadow: var(--card-shadow-hover, 0 4px 12px rgba(0,0,0,0.1));
}

.project-card.selected {
  border-color: var(--brand);
  box-shadow: var(--card-shadow-active, 0 0 0 2px var(--brand));
}

.project-card.shared {
  border-left: 3px solid var(--info);
}

.project-card.archived {
  opacity: 0.55;
  border-left: 3px solid var(--warning, #ff9800);
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.card-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin: 0;
}

.card-meta {
  margin-top: 0.25rem;
}

.time {
  font-size: 0.75rem;
  color: var(--text-faint);
}

.card-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.4rem;
}

.badge {
  font-size: 0.75rem;
  padding: 0.1rem 0.45rem;
  border-radius: 10px;
  font-weight: 600;
  white-space: nowrap;
}

.badge-dataset { background: var(--badge-dataset, #e3f2fd); color: var(--badge-dataset-text, #1565c0); }
.badge-job { background: var(--badge-job, #f3e5f5); color: var(--badge-job-text, #7b1fa2); }
.badge-share { background: var(--badge-share, #e8f5e9); color: var(--badge-share-text, #2e7d32); }
.badge-role {
  background: var(--info-bg);
  color: var(--info);
  text-transform: uppercase;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.completed { background: var(--status-completed, #4caf50); }
.status-dot.running { background: var(--status-running, #ff9800); animation: pulse 1.5s infinite; }
.status-dot.failed { background: var(--status-failed, #e53935); }
.status-dot.pending { background: var(--text-faint); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.project-card { display: flex; align-items: stretch; gap: 0.25rem; }
.card-main {
  flex: 1; min-width: 0;
  display: flex; flex-direction: column; gap: 0.2rem;
  background: none; border: none; padding: 0; margin: 0;
  font: inherit; color: inherit; text-align: left; cursor: pointer;
}
.card-main .card-top { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.card-main .card-name { font-weight: 600; font-size: 0.95rem; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-main .card-meta, .card-main .card-badges { display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; }
.archived-tag { font-size: 0.75rem; padding: 0 0.35rem; border: 1px solid var(--border); border-radius: 4px; color: var(--text-secondary); }
.card-details {
  align-self: center;
  background: transparent; border: 1px solid transparent; border-radius: 6px;
  color: var(--text-secondary); font-size: 1.1rem; line-height: 1;
  padding: 0.3rem 0.45rem; cursor: pointer;
}
.card-details:hover, .card-details[aria-pressed="true"] { border-color: var(--border); background: var(--bg-card-hover); color: var(--text-primary); }
</style>
