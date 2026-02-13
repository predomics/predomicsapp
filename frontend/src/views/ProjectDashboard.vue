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

    <div class="dashboard-body" :class="{ 'with-console': store.showConsole && store.activeJobId }">
      <div class="main-panel">
        <router-view />
      </div>
      <aside v-if="store.showConsole && store.activeJobId" class="console-aside">
        <ConsolePanel
          :project-id="projectId"
          :job-id="store.activeJobId"
          @close="store.closeConsole()"
          @completed="onJobCompleted"
          @failed="onJobFailed"
        />
      </aside>
    </div>
  </div>
  <div v-else class="loading">Loading project...</div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import ConsolePanel from '../components/ConsolePanel.vue'
import ShareModal from '../components/ShareModal.vue'

const route = useRoute()
const store = useProjectStore()
const showShare = ref(false)

const projectId = computed(() => route.params.id)
const project = computed(() => store.current)

async function loadProject() {
  if (projectId.value) {
    await store.fetchOne(projectId.value)
  }
}

function onJobCompleted(jobId) {
  loadProject()
}

function onJobFailed(jobId) {
  loadProject()
}

watch(projectId, loadProject)
onMounted(loadProject)
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
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
  min-height: calc(100vh - 180px);
}

.dashboard-body.with-console {
  grid-template-columns: 1fr 600px;
}

.main-panel {
  min-width: 0;
  padding-right: 0;
}

.dashboard-body.with-console .main-panel {
  padding-right: 1.5rem;
}

.console-aside {
  border-left: 1px solid var(--border-light);
  border-radius: 0 8px 8px 0;
  overflow: hidden;
  height: calc(100vh - 180px);
  position: sticky;
  top: 80px;
}

.loading {
  text-align: center;
  padding: 3rem;
  color: var(--text-faint);
}
</style>
