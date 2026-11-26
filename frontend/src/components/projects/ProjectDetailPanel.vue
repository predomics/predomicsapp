<template>
  <div class="detail-panel" v-if="project">
    <!-- Header -->
    <div class="detail-header">
      <div class="header-info">
        <div class="name-row">
          <h2 v-if="!editing" @dblclick="startEdit">{{ project.name }}</h2>
          <input
            v-else
            ref="nameInput"
            v-model="editName"
            class="name-edit"
            :aria-label="$t('projects.projectName')"
            @keyup.enter="saveEdit"
            @keyup.escape="cancelEdit"
            @blur="saveEdit"
          />
          <button v-if="!editing" type="button" class="btn-icon-sm" @click="startEdit" :title="$t('projects.rename')" :aria-label="$t('projects.rename')"><SvgIcon name="pencil" :size="14" /></button>
        </div>
        <p v-if="!editingDesc && project.description" class="desc" @dblclick="startDescEdit">{{ project.description }}</p>
        <p v-if="!editingDesc && !project.description" class="desc desc-placeholder">
          <button type="button" class="link-btn" @click="startDescEdit">{{ $t('projects.addDescription') }}</button>
        </p>
        <textarea
          v-if="editingDesc"
          v-model="editDesc"
          class="desc-edit"
          rows="2"
          @keyup.escape="cancelDescEdit"
          @blur="saveDescEdit"
:placeholder="$t('projects.descriptionPlaceholder')"
          :aria-label="$t('projects.descriptionPlaceholder')"
        ></textarea>
        <div class="dates">
          <span>{{ $t('projects.createdOn', { date: formatDate(project.created_at) }) }}</span>
          <span v-if="project.updated_at"> &middot; {{ $t('projects.modified', { when: timeAgo(project.updated_at) }) }}</span>
        </div>
      </div>
      <div class="header-actions">
        <button type="button" class="btn btn-primary" @click="$emit('open', project.project_id)">{{ $t('projects.openProject') }}</button>
        <button type="button" class="btn btn-outline" @click="$emit('share', project.project_id)">{{ $t('projectDashboard.share') }}</button>
        <button type="button" class="btn btn-outline" @click="$emit('archive', project)">
          {{ project.archived ? $t('projects.unarchive') : $t('projects.archive') }}
        </button>
        <button type="button" class="btn btn-danger-outline" @click="$emit('delete', project)">{{ $t('common.delete') }}</button>
      </div>
    </div>

    <!-- Stat badges row -->
    <div class="stat-row">
      <div class="stat badge-dataset">
        <span class="stat-num">{{ project.datasets?.length || 0 }}</span>
        <span class="stat-label">{{ $t('dashboard.datasets') }}</span>
      </div>
      <div class="stat badge-job">
        <span class="stat-num">{{ project.job_count || project.jobs?.length || 0 }}</span>
        <span class="stat-label">{{ $t('projects.jobs') }}</span>
      </div>
      <div class="stat badge-share">
        <span class="stat-num">{{ project.share_count || 0 }}</span>
        <span class="stat-label">{{ $t('projects.shared') }}</span>
      </div>
    </div>

    <!-- Datasets section -->
    <section v-if="project.datasets?.length > 0" class="detail-section">
      <h3>{{ $t('dashboard.datasets') }}</h3>
      <div v-for="ds in project.datasets" :key="ds.id" class="ds-group-card">
        <div class="ds-group-name">{{ ds.name }}</div>
        <div class="ds-files">
          <span v-for="f in ds.files" :key="f.id" class="file-chip" :class="f.role">
            {{ f.filename }}
            <span v-if="f.role" class="file-role">{{ f.role }}</span>
          </span>
        </div>
      </div>
    </section>

    <!-- Recent Jobs section -->
    <section v-if="project.jobs?.length > 0" class="detail-section">
      <h3>{{ $t('projects.recentJobs') }}</h3>
      <ul class="job-list">
        <li v-for="job in recentJobs" :key="job.id" class="job-row">
          <span class="job-id">{{ job.label }}</span>
          <span v-if="job.status" class="job-status">{{ statusLabel(job.status) }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { useProjectStore } from '../../stores/project'
import SvgIcon from '../SvgIcon.vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '../../composables/useToast'
import { apiError } from '../../utils/apiError'
import { timeAgo } from '../../utils/time'
import { statusLabel } from '../../utils/jobStatus'

const { t, locale } = useI18n()
const { toast } = useToast()

const props = defineProps({
  project: { type: Object, default: null },
})

defineEmits(['open', 'share', 'archive', 'delete'])

const store = useProjectStore()

const editing = ref(false)
const editName = ref('')
const nameInput = ref(null)
const editingDesc = ref(false)
const editDesc = ref('')

const recentJobs = computed(() => {
  const jobs = props.project?.jobs || []
  return jobs.slice(0, 5).map((j, i) => {
    const id = typeof j === 'string' ? j : j.job_id || j.id || ''
    const name = typeof j === 'object' && j ? j.name : ''
    return {
      id: id || String(i),
      // A short id means nothing to a reader: prefer the job's name, else number it.
      label: name || t('projects.jobNumbered', { n: jobs.length - i, id: id.slice(0, 8) }),
      status: typeof j === 'object' && j ? j.status : '',
    }
  })
})

function startEdit() {
  editName.value = props.project.name
  editing.value = true
  nextTick(() => nameInput.value?.focus())
}

function cancelEdit() {
  editing.value = false
}

async function saveEdit() {
  if (!editing.value) return
  editing.value = false
  const newName = editName.value.trim()
  if (!newName || newName === props.project.name) return
  try {
    await store.updateProject(props.project.project_id, { name: newName })
  } catch (e) {
    toast.error(t('projects.renameFailed', { error: apiError(e) }))
  }
}

function startDescEdit() {
  editDesc.value = props.project.description || ''
  editingDesc.value = true
}

function cancelDescEdit() {
  editingDesc.value = false
}

async function saveDescEdit() {
  if (!editingDesc.value) return
  editingDesc.value = false
  const newDesc = editDesc.value.trim()
  if (newDesc === (props.project.description || '')) return
  try {
    await store.updateProject(props.project.project_id, { description: newDesc })
  } catch (e) {
    toast.error(t('projects.updateFailed', { error: apiError(e) }))
  }
}

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(locale.value, { year: 'numeric', month: 'short', day: 'numeric' })
}

</script>

<style scoped>
.detail-panel {
  padding: 1.5rem;
  height: 100%;
  overflow-y: auto;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.name-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.header-info h2 {
  font-size: 1.4rem;
  color: var(--text-primary);
  margin: 0 0 0.25rem;
  cursor: default;
}

.name-edit {
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--text-primary);
  border: 1px solid var(--brand);
  border-radius: 4px;
  padding: 0.1rem 0.4rem;
  background: var(--bg-input);
  width: 100%;
}

.btn-icon-sm {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 4px;
  font-size: 0.85rem;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.btn-icon-sm:hover {
  background: var(--bg-card-hover);
  color: var(--text-primary);
}

.desc {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 0.25rem;
  cursor: default;
}
.desc-placeholder {
  color: var(--text-faint);
  font-style: italic;
  cursor: pointer;
}
.desc-edit {
  font-size: 0.85rem;
  color: var(--text-body);
  border: 1px solid var(--brand);
  border-radius: 4px;
  padding: 0.3rem 0.5rem;
  background: var(--bg-input);
  width: 100%;
  resize: vertical;
  margin-bottom: 0.25rem;
}

.dates {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.header-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}

.btn {
  padding: 0.4rem 1rem;
  border-radius: 6px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border: 1.5px solid transparent;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--accent);
  color: var(--accent-text);
}

.btn-primary:hover { opacity: 0.9; }

.btn-outline {
  background: transparent;
  border-color: var(--border);
  color: var(--text-secondary);
}

.btn-outline:hover {
  border-color: var(--text-secondary);
  color: var(--text-primary);
}

.btn-danger-outline {
  background: transparent;
  border-color: var(--border);
  color: var(--text-muted);
}

.btn-danger-outline:hover {
  border-color: var(--danger);
  color: var(--danger);
}

/* Stat row */
.stat-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.75rem 1.25rem;
  border-radius: 10px;
  min-width: 80px;
}

.stat.badge-dataset { background: var(--badge-dataset, #e3f2fd); }
.stat.badge-job { background: var(--badge-job, #f3e5f5); }
.stat.badge-share { background: var(--badge-share, #e8f5e9); }

.stat-num {
  font-size: 1.3rem;
  font-weight: 700;
  line-height: 1;
}

.stat.badge-dataset .stat-num { color: var(--badge-dataset-text, #1565c0); }
.stat.badge-job .stat-num { color: var(--badge-job-text, #7b1fa2); }
.stat.badge-share .stat-num { color: var(--badge-share-text, #2e7d32); }

.stat-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 0.2rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

/* Sections */
.detail-section {
  margin-bottom: 1.5rem;
}

.detail-section h3 {
  font-size: 0.9rem;
  color: var(--text-secondary);
  margin-bottom: 0.75rem;
  font-weight: 600;
}

/* Dataset group cards */
.ds-group-card {
  background: var(--bg-card);
  border: 1px solid var(--border-lighter);
  border-radius: 8px;
  padding: 0.75rem 1rem;
  margin-bottom: 0.5rem;
}

.ds-group-name {
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--text-primary);
  margin-bottom: 0.4rem;
}

.ds-files {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.file-chip {
  font-size: 0.75rem;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  background: var(--bg-badge);
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}

.file-role {
  font-size: 0.75rem;
  padding: 0 0.25rem;
  border-radius: 3px;
  background: var(--badge-dataset, #e3f2fd);
  color: var(--badge-dataset-text, #1565c0);
  font-weight: 600;
  text-transform: uppercase;
}

/* Job list */
.job-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.4rem 0;
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.job-id {
  font-family: monospace;
  font-size: 0.78rem;
  color: var(--text-muted);
}
.link-btn { background: none; border: none; padding: 0; font: inherit; color: var(--text-secondary); cursor: pointer; text-decoration: underline; }
.job-list { list-style: none; padding: 0; }
.job-status { margin-left: 0.5rem; font-size: 0.75rem; color: var(--text-secondary); }
@media (max-width: 700px) { .detail-header { flex-direction: column; gap: 0.75rem; } .header-actions { flex-wrap: wrap; } }
</style>
