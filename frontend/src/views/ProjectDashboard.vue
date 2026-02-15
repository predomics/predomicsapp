<template>
  <div class="project-dashboard" v-if="project">
    <header class="project-header">
      <h2>{{ project.name }}</h2>
      <div class="project-meta">
        {{ project.datasets?.length || 0 }} datasets &middot;
        {{ project.jobs?.length || 0 }} jobs
      </div>
      <button class="share-btn" @click="showShare = true">Share</button>
    </header>

    <ShareModal
      v-if="showShare"
      :project-id="projectId"
      @close="showShare = false"
    />

    <nav class="tab-nav">
      <router-link :to="`/project/${projectId}/data`" class="tab" active-class="active">Data</router-link>
      <router-link :to="`/project/${projectId}/parameters`" class="tab" active-class="active">Parameters &amp; Run</router-link>
      <router-link :to="`/project/${projectId}/results`" class="tab" active-class="active">Results</router-link>
    </nav>

    <div class="dashboard-body">
      <div class="main-panel">
        <router-view />
      </div>
      <div v-if="store.activeJobId" class="console-bottom" :class="{ minimized: !store.showConsole }">
        <div v-if="!store.showConsole" class="console-minimized-bar" @click="store.showConsole = true">
          <span>Console</span>
          <span class="status-badge-mini" :class="miniStatus">{{ miniStatus }}</span>
          <span class="expand-icon">&#9650;</span>
        </div>
        <ConsolePanel
          v-else
          :project-id="projectId"
          :job-id="store.activeJobId"
          @close="store.showConsole = false"
          @completed="onJobCompleted"
          @failed="onJobFailed"
        />
      </div>
    </div>
  </div>
  <div v-else class="loading">Loading project...</div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import { useProjectStore } from '../stores/project'
import ConsolePanel from '../components/ConsolePanel.vue'
import ShareModal from '../components/ShareModal.vue'
import { requestPermission, notifyJobCompleted, notifyJobFailed } from '../utils/notify'

const route = useRoute()
const store = useProjectStore()
const showShare = ref(false)

const projectId = computed(() => route.params.id)
const project = computed(() => store.current)
const miniStatus = computed(() => {
  const job = store.current?.jobs?.find(j => j.job_id === store.activeJobId)
  return job?.status || 'running'
})

async function loadProject() {
  if (projectId.value) {
    await store.fetchOne(projectId.value)
  }
}

async function onJobCompleted(jobId) {
  await loadProject()
  // Send browser notification with AUC if available
  try {
    const { data } = await axios.get(`/api/analysis/${projectId.value}/jobs/${jobId}`)
    notifyJobCompleted(project.value?.name || 'Project', {
      auc: data.best_auc,
      k: data.best_k,
      jobId,
    })
  } catch {
    notifyJobCompleted(project.value?.name || 'Project', { jobId })
  }
}

function onJobFailed(jobId) {
  loadProject()
  notifyJobFailed(project.value?.name || 'Project', { jobId })
}

watch(projectId, loadProject)
onMounted(() => {
  loadProject()
  requestPermission()
})
</script>

<style scoped>
.project-dashboard {
  max-width: 1600px;
  margin: 0 auto;
  padding: 0 1rem;
}

.project-header {
  display: flex;
  align-items: baseline;
  gap: 1rem;
  margin-bottom: 0.5rem;
}

.project-header h2 {
  margin: 0;
  color: var(--text-primary);
}

.project-meta {
  color: var(--text-faint);
  font-size: 0.85rem;
}

.share-btn {
  margin-left: auto;
  padding: 0.35rem 1rem;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}

.share-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.tab-nav {
  display: flex;
  gap: 0;
  border-bottom: 2px solid var(--border-light);
  margin-bottom: 1rem;
}

.tab {
  padding: 0.75rem 1.5rem;
  text-decoration: none;
  color: var(--text-muted);
  font-weight: 500;
  font-size: 0.9rem;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.2s;
}

.tab:hover {
  color: var(--text-primary);
}

.tab.active {
  color: var(--text-primary);
  border-bottom-color: var(--accent);
}

.dashboard-body {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 180px);
}

.main-panel {
  flex: 1;
  min-width: 0;
}

.console-bottom {
  border-top: 1px solid var(--border-light);
  border-radius: 8px 8px 0 0;
  height: 250px;
  margin-top: 1rem;
  overflow: hidden;
  position: sticky;
  bottom: 0;
  background: var(--console-bg);
  z-index: 10;
}

.console-bottom.minimized {
  height: auto;
}

.console-minimized-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 1rem;
  cursor: pointer;
  font-size: 0.8rem;
  color: var(--text-muted);
  transition: background 0.15s;
}

.console-minimized-bar:hover {
  background: var(--bg-hover);
}

.console-minimized-bar .expand-icon {
  margin-left: auto;
  font-size: 0.65rem;
}

.status-badge-mini {
  padding: 0.1rem 0.4rem;
  border-radius: 8px;
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge-mini.pending { background: var(--warning-bg); color: var(--warning-dark); }
.status-badge-mini.running { background: var(--info-bg); color: var(--info); }
.status-badge-mini.completed { background: var(--success-bg); color: var(--success-dark); }
.status-badge-mini.failed { background: var(--danger-bg); color: var(--danger-dark); }

.loading {
  text-align: center;
  padding: 3rem;
  color: var(--text-faint);
}
</style>
