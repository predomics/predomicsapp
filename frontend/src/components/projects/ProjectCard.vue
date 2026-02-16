<template>
  <div
    class="project-card"
    :class="{ selected, shared: isShared }"
    @click="$emit('select')"
    @dblclick.stop="$emit('open')"
  >
    <div class="card-top">
      <h4 class="card-name">{{ project.name }}</h4>
      <span v-if="project.latest_job_status" class="status-dot" :class="project.latest_job_status" :title="project.latest_job_status" />
    </div>
    <div class="card-meta">
      <span class="time">{{ relativeDate(project.updated_at || project.created_at) }}</span>
    </div>
    <div class="card-badges">
      <span class="badge badge-dataset" v-if="datasetCount > 0">{{ datasetCount }} {{ $t('components.dataset', datasetCount) }}</span>
      <span class="badge badge-job" v-if="jobCount > 0">{{ jobCount }} {{ $t('components.job', jobCount) }}</span>
      <span class="badge badge-share" v-if="shareCount > 0">{{ shareCount }} {{ $t('components.shared') }}</span>
      <span v-if="isShared" class="badge badge-role">{{ project.role }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  project: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  isShared: { type: Boolean, default: false },
})

defineEmits(['select', 'open'])

const datasetCount = computed(() => props.project.datasets?.length || 0)
const jobCount = computed(() => props.project.job_count || props.project.jobs?.length || 0)
const shareCount = computed(() => props.project.share_count || 0)

function relativeDate(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return t('components.justNow')
  if (mins < 60) return t('components.minutesAgo', { n: mins })
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return t('components.hoursAgo', { n: hrs })
  const days = Math.floor(hrs / 24)
  if (days < 30) return t('components.daysAgo', { n: days })
  return new Date(iso).toLocaleDateString()
}
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
  font-size: 0.68rem;
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
</style>
