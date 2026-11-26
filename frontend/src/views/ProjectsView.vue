<template>
  <div class="projects-page">
    <!-- Left Panel: Project List -->
    <aside class="list-panel" :aria-label="$t('projects.title')">
      <div class="list-header">
        <h2>{{ $t('projects.title') }}</h2>
        <button type="button" class="btn-new" :aria-expanded="showCreate ? 'true' : 'false'" :title="$t('projects.newProject')" :aria-label="$t('projects.newProject')" @click="toggleCreate"><span aria-hidden="true">+</span></button>
      </div>

      <!-- Create form (collapsible) -->
      <form v-if="showCreate" class="create-form" @submit.prevent="createProject">
        <input
          ref="createInput"
          v-model="newName"
          :placeholder="$t('projects.projectNamePlaceholder')"
          :aria-label="$t('projects.projectName')"
        />
        <button type="submit" :disabled="!newName.trim() || creating">{{ creating ? $t('common.creating') : $t('projects.create') }}</button>
      </form>

      <!-- Search + Archive filter -->
      <div class="filter-row">
        <input v-model="search" type="search" :placeholder="$t('projects.searchPlaceholder')" :aria-label="$t('projects.searchPlaceholder')" class="search-input" />
        <label class="archive-toggle" :title="$t('projects.showArchived')">
          <input type="checkbox" v-model="showArchived" @change="refetchProjects" />
          <span class="archive-label">{{ $t('projects.showArchived') }}</span>
        </label>
      </div>

      <!-- Demo datasets -->
      <div v-if="availableSamples.length > 0" class="section-label">
        {{ $t('projects.demoDatasets') }}
      </div>
      <div v-for="s in availableSamples" :key="s.id" class="sample-row">
        <div class="sample-text">
          <span class="sample-name">{{ s.name }}</span>
          <span v-if="s.description" class="sample-desc">{{ s.description }}</span>
        </div>
        <span v-if="s.loaded" class="sample-check" :title="$t('projects.sampleLoaded')"><span aria-hidden="true">&#10003;</span><span class="sr-only">{{ $t('projects.sampleLoaded') }}</span></span>
        <button v-else type="button" class="sample-btn" :title="$t('projects.loadHint')" @click="loadSample(s.id)" :disabled="!!loadingSample">
          {{ loadingSample === s.id ? $t('projects.loadingSample') : $t('projects.load') }}
        </button>
      </div>

      <!-- Own projects -->
      <div v-if="filteredProjects.length > 0" class="section-label">{{ $t('projects.myProjects') }}</div>
      <ProjectCard
        v-for="p in filteredProjects"
        :key="p.project_id"
        :project="p"
        :selected="store.selectedId === p.project_id"
        @select="store.selectedId = p.project_id"
        @open="openProject(p.project_id)"
      />

      <!-- Shared projects -->
      <div v-if="filteredShared.length > 0" class="section-label">{{ $t('projects.sharedWithMe') }}</div>
      <ProjectCard
        v-for="sp in filteredShared"
        :key="sp.project_id"
        :project="sp"
        :selected="store.selectedId === sp.project_id"
        :is-shared="true"
        @select="store.selectedId = sp.project_id"
        @open="openProject(sp.project_id)"
      />

      <AsyncState
        v-if="loading || loadError"
        :loading="loading"
        :error="loadError"
        :retry="fetchData"
        :loading-text="$t('projects.loading')"
      />
      <div v-else-if="noProjects && search" class="list-status">
        {{ $t('projects.noMatch', { query: search }) }}
      </div>
      <div v-else-if="noProjects" class="list-status">
        {{ $t('projects.noProjects') }}
      </div>
    </aside>

    <!-- Right Panel: Detail or Empty State -->
    <section class="detail-area" :aria-label="$t('projects.detailsRegion')">
      <ProjectDetailPanel
        v-if="selectedProject"
        :project="selectedProject"
        @open="openProject"
        @share="shareProject"
        @archive="handleArchive"
        @delete="handleDelete"
      />
      <EmptyState
        v-else-if="!loading && !hasAnyProject"
        :title="$t('projects.welcomeTitle')"
        :message="$t('projects.welcomeMsg')"
      >
        <div class="empty-actions">
          <button v-if="firstSample" type="button" class="btn-cta" :disabled="!!loadingSample" @click="loadSample(firstSample.id)">
            {{ loadingSample ? $t('projects.loadingSample') : $t('projects.tryDemo') }}
          </button>
          <button type="button" class="btn-cta secondary" @click="toggleCreate(true)">{{ $t('projects.createProject') }}</button>
        </div>
        <p v-if="firstSample" class="empty-sample-desc">{{ firstSample.name }} — {{ firstSample.description }}</p>
      </EmptyState>
      <EmptyState
        v-else
        :title="$t('projects.selectProject')"
        :message="$t('projects.selectProjectMsg')"
      />
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { useProjectStore } from '../stores/project'
import ProjectCard from '../components/projects/ProjectCard.vue'
import ProjectDetailPanel from '../components/projects/ProjectDetailPanel.vue'
import EmptyState from '../components/projects/EmptyState.vue'
import AsyncState from '../components/AsyncState.vue'
import { useToast } from '../composables/useToast'
import { useConfirm } from '../composables/useConfirm'
import { apiError, ignoreError } from '../utils/apiError'

const { t } = useI18n()
const router = useRouter()
const store = useProjectStore()
const { toast, addToast } = useToast()
const { confirmDialog } = useConfirm()

const newName = ref('')
const showCreate = ref(false)
const creating = ref(false)
const createInput = ref(null)
const search = ref('')
const showArchived = ref(false)
const loading = ref(true)
const loadError = ref('')
const samples = ref([])
const loadingSample = ref('')

const projectNames = computed(() => new Set(store.projects.map(p => p.name)))
const availableSamples = computed(() =>
  samples.value.map(s => ({ ...s, loaded: projectNames.value.has(s.name) }))
)
const firstSample = computed(() => availableSamples.value.find(s => !s.loaded) || null)

const allProjects = computed(() => [...store.projects, ...store.sharedProjects])
const hasAnyProject = computed(() => allProjects.value.length > 0)

const selectedProject = computed(() =>
  allProjects.value.find(p => p.project_id === store.selectedId) || null
)

const filteredProjects = computed(() => {
  let list = store.projects
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(p => p.name.toLowerCase().includes(q))
  }
  return list
})

const filteredShared = computed(() => {
  if (!search.value) return store.sharedProjects
  const q = search.value.toLowerCase()
  return store.sharedProjects.filter(p => p.name.toLowerCase().includes(q))
})

const noProjects = computed(() => filteredProjects.value.length === 0 && filteredShared.value.length === 0)

function toggleCreate(force) {
  showCreate.value = force === true ? true : !showCreate.value
  if (showCreate.value) nextTick(() => createInput.value?.focus())
}

async function refetchProjects() {
  try {
    await store.fetchAll(showArchived.value)
  } catch (e) {
    toast.error(apiError(e))
  }
}

async function fetchData() {
  loading.value = true
  loadError.value = ''
  try {
    await Promise.all([
      store.fetchAll(showArchived.value),
      store.fetchSharedProjects(),
      fetchSamples(),
    ])
  } catch (e) {
    loadError.value = apiError(e)
  } finally {
    loading.value = false
  }
}

async function fetchSamples() {
  try {
    const { data } = await api.samples.list({ silentError: true })
    samples.value = data.filter(s => s.available)
  } catch (e) { ignoreError(e) /* demo datasets are optional */ }
}

async function loadSample(sampleId) {
  loadingSample.value = sampleId
  try {
    const { data } = await api.samples.load(sampleId)
    await store.fetchAll(showArchived.value)
    store.selectedId = data.project_id
    openProject(data.project_id)
  } catch (e) {
    toast.error(t('projects.sampleFailed', { error: apiError(e) }))
  } finally {
    loadingSample.value = ''
  }
}

async function createProject() {
  const name = newName.value.trim()
  if (!name || creating.value) return
  creating.value = true
  try {
    const data = await store.create(name)
    newName.value = ''
    showCreate.value = false
    store.selectedId = data.project_id
    // Straight into the project: the next thing to do is add data.
    openProject(data.project_id)
  } catch (e) {
    toast.error(t('projects.createFailed', { error: apiError(e) }))
  } finally {
    creating.value = false
  }
}

function openProject(id) {
  router.push(`/project/${id}`)
}

function shareProject(id) {
  router.push({ path: `/project/${id}/data`, query: { share: '1' } })
}

async function handleArchive(project) {
  const wasArchived = !!project.archived
  try {
    const result = await store.archiveProject(project.project_id)
    if (!showArchived.value && result.archived) {
      // Remove from visible list
      store.projects = store.projects.filter(p => p.project_id !== project.project_id)
      if (store.selectedId === project.project_id) store.selectedId = null
    }
    addToast(
      t(result.archived ? 'projects.archivedToast' : 'projects.unarchivedToast', { name: project.name }),
      'info',
      8000,
      wasArchived ? {} : { action: { label: t('common.undo'), onClick: () => undoArchive(project) } },
    )
  } catch (e) {
    toast.error(t('projects.archiveFailed', { error: apiError(e) }))
  }
}

async function undoArchive(project) {
  try {
    await store.archiveProject(project.project_id)
    await store.fetchAll(showArchived.value)
  } catch (e) {
    toast.error(t('projects.archiveFailed', { error: apiError(e) }))
  }
}

async function handleDelete(project) {
  if (!(await confirmDialog({ message: t('projects.deleteConfirm', { name: project.name }), confirmLabel: t('common.delete'), danger: true }))) return
  try {
    await store.remove(project.project_id)
  } catch (e) {
    toast.error(t('projects.deleteFailed', { error: apiError(e) }))
  }
}

onMounted(fetchData)
</script>

<style scoped>
.projects-page {
  display: grid;
  grid-template-columns: minmax(260px, 340px) 1fr;
  height: calc(100vh - 60px);
  margin: -1.5rem -1rem;
  overflow: hidden;
}

/* Left panel */
.list-panel {
  border-right: 1px solid var(--border-lighter);
  background: var(--bg-card);
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.25rem;
}

.list-header h2 {
  font-size: 1.15rem;
  color: var(--text-primary);
  margin: 0;
}

.btn-new {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1.5px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  font-size: 1.2rem;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.btn-new:hover {
  border-color: var(--brand);
  color: var(--brand);
}

.create-form {
  display: flex;
  gap: 0.4rem;
}

.create-form input {
  flex: 1;
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.82rem;
  background: var(--bg-input);
  color: var(--text-body);
}

.create-form button {
  padding: 0.4rem 0.75rem;
  background: var(--accent);
  color: var(--accent-text);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 500;
}

.create-form button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.filter-row {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.search-input {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  font-size: 0.82rem;
  background: var(--bg-input);
  color: var(--text-body);
  width: 100%;
}

.archive-toggle {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  cursor: pointer;
}

.archive-toggle input[type="checkbox"] {
  margin: 0;
  accent-color: var(--accent);
}

.archive-label {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.section-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-faint);
  font-weight: 600;
  padding: 0.5rem 0 0.15rem;
}

/* Sample rows */
.sample-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.4rem 0.6rem;
  background: var(--success-bg);
  border-radius: 6px;
  font-size: 0.8rem;
}

.sample-name {
  color: var(--text-secondary);
  font-weight: 500;
}

.sample-check {
  color: var(--success-dark);
  font-weight: 700;
}

.sample-btn {
  padding: 0.2rem 0.6rem;
  background: var(--success-dark);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.75rem;
}

.sample-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.list-status {
  text-align: center;
  padding: 2rem 0;
  color: var(--text-faint);
  font-size: 0.85rem;
}

/* Right panel */
.detail-area {
  overflow-y: auto;
  background: var(--bg-page);
}

@media (max-width: 900px) {
  .projects-page {
    grid-template-columns: 1fr;
    height: auto;
  }

  .list-panel {
    border-right: none;
    border-bottom: 1px solid var(--border-lighter);
    max-height: 50vh;
  }
}
.sample-row { align-items: flex-start; }
.sample-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 0.1rem; }
.sample-desc { font-size: 0.75rem; color: var(--text-secondary); line-height: 1.3; }
.empty-actions { display: flex; flex-wrap: wrap; gap: 0.75rem; justify-content: center; margin-top: 1rem; }
.btn-cta {
  padding: 0.6rem 1.2rem; border-radius: 8px; font-size: 0.95rem; font-weight: 600; cursor: pointer;
  background: var(--accent); color: var(--accent-text); border: 1px solid var(--accent);
}
.btn-cta.secondary { background: var(--bg-card); color: var(--text-primary); border-color: var(--border); }
.btn-cta:disabled { opacity: 0.6; cursor: default; }
.empty-sample-desc { margin-top: 0.75rem; font-size: 0.8rem; color: var(--text-secondary); max-width: 520px; }
</style>
