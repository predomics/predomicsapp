<template>
  <div class="projects-page">
    <!-- Left Panel: Project List -->
    <aside class="list-panel">
      <div class="list-header">
        <h2>Projects</h2>
        <button class="btn-new" @click="showCreate = !showCreate" title="New project">+</button>
      </div>

      <!-- Create form (collapsible) -->
      <div v-if="showCreate" class="create-form">
        <input
          v-model="newName"
          placeholder="Project name..."
          @keyup.enter="createProject"
        />
        <button @click="createProject" :disabled="!newName.trim()">Create</button>
      </div>

      <!-- Search -->
      <input v-model="search" placeholder="Search projects..." class="search-input" />

      <!-- Demo datasets -->
      <div v-if="availableSamples.length > 0" class="section-label">
        Demo Datasets
      </div>
      <div v-for="s in availableSamples" :key="s.id" class="sample-row">
        <span class="sample-name">{{ s.name }}</span>
        <span v-if="s.loaded" class="sample-check">&#10003;</span>
        <button v-else class="sample-btn" @click="loadSample(s.id)" :disabled="loadingSample">
          Load
        </button>
      </div>

      <!-- Own projects -->
      <div v-if="filteredProjects.length > 0" class="section-label">My Projects</div>
      <ProjectCard
        v-for="p in filteredProjects"
        :key="p.project_id"
        :project="p"
        :selected="store.selectedId === p.project_id"
        @select="openProject(p.project_id)"
        @open="openProject(p.project_id)"
      />

      <!-- Shared projects -->
      <div v-if="filteredShared.length > 0" class="section-label">Shared with me</div>
      <ProjectCard
        v-for="sp in filteredShared"
        :key="sp.project_id"
        :project="sp"
        :selected="store.selectedId === sp.project_id"
        :is-shared="true"
        @select="openProject(sp.project_id)"
        @open="openProject(sp.project_id)"
      />

      <div v-if="loading" class="list-status">Loading...</div>
      <div v-else-if="filteredProjects.length === 0 && filteredShared.length === 0 && !search" class="list-status">
        No projects yet
      </div>
    </aside>

    <!-- Right Panel: Detail or Empty State -->
    <main class="detail-area">
      <ProjectDetailPanel
        v-if="selectedProject"
        :project="selectedProject"
        @open="openProject"
        @share="openProject"
        @delete="handleDelete"
      />
      <EmptyState
        v-else
        title="Select a project"
        message="Choose a project from the list or create a new one to get started."
      />
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useProjectStore } from '../stores/project'
import ProjectCard from '../components/projects/ProjectCard.vue'
import ProjectDetailPanel from '../components/projects/ProjectDetailPanel.vue'
import EmptyState from '../components/projects/EmptyState.vue'

const router = useRouter()
const store = useProjectStore()

const newName = ref('')
const showCreate = ref(false)
const search = ref('')
const loading = ref(true)
const samples = ref([])
const loadingSample = ref(false)

const projectNames = computed(() => new Set(store.projects.map(p => p.name)))
const availableSamples = computed(() =>
  samples.value.map(s => ({ ...s, loaded: projectNames.value.has(s.name) }))
)

const allProjects = computed(() => [...store.projects, ...store.sharedProjects])

const selectedProject = computed(() =>
  allProjects.value.find(p => p.project_id === store.selectedId) || null
)

const filteredProjects = computed(() => {
  if (!search.value) return store.projects
  const q = search.value.toLowerCase()
  return store.projects.filter(p => p.name.toLowerCase().includes(q))
})

const filteredShared = computed(() => {
  if (!search.value) return store.sharedProjects
  const q = search.value.toLowerCase()
  return store.sharedProjects.filter(p => p.name.toLowerCase().includes(q))
})

async function fetchData() {
  loading.value = true
  try {
    await Promise.all([
      store.fetchAll(),
      store.fetchSharedProjects(),
      fetchSamples(),
    ])
  } finally {
    loading.value = false
  }
}

async function fetchSamples() {
  try {
    const { data } = await axios.get('/api/samples/')
    samples.value = data.filter(s => s.available)
  } catch { /* ignore */ }
}

async function loadSample(sampleId) {
  loadingSample.value = true
  try {
    const { data } = await axios.post(`/api/samples/${sampleId}/load`)
    await store.fetchAll()
    store.selectedId = data.project_id
    openProject(data.project_id)
  } catch (e) {
    console.error('Failed to load sample:', e)
  } finally {
    loadingSample.value = false
  }
}

async function createProject() {
  if (!newName.value.trim()) return
  try {
    const data = await store.create(newName.value.trim())
    newName.value = ''
    showCreate.value = false
    store.selectedId = data.project_id
  } catch (e) {
    console.error('Failed to create project:', e)
  }
}

function openProject(id) {
  router.push(`/project/${id}`)
}

async function handleDelete(project) {
  if (!confirm(`Delete project "${project.name}"? This cannot be undone.`)) return
  try {
    await store.remove(project.project_id)
  } catch (e) {
    alert('Delete failed: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(fetchData)
</script>

<style scoped>
.projects-page {
  display: grid;
  grid-template-columns: 340px 1fr;
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

.search-input {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  font-size: 0.82rem;
  background: var(--bg-input);
  color: var(--text-body);
  width: 100%;
}

.section-label {
  font-size: 0.72rem;
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
  color: var(--success);
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
</style>
