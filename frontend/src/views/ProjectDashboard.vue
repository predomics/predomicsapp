<template>
  <div class="project-dashboard" v-if="project">
    <header class="project-header">
      <h2>{{ project.name }}</h2>
      <div class="project-meta">
        {{ project.datasets?.length || 0 }} datasets &middot;
        {{ project.jobs?.length || 0 }} jobs
      </div>
    </header>

    <nav class="tab-nav">
      <router-link :to="`/project/${projectId}/data`" class="tab" active-class="active">Data</router-link>
      <router-link :to="`/project/${projectId}/settings`" class="tab" active-class="active">Settings &amp; Run</router-link>
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
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import ConsolePanel from '../components/ConsolePanel.vue'

const route = useRoute()
const store = useProjectStore()

const projectId = computed(() => route.params.id)
const project = computed(() => store.current)

async function loadProject() {
  if (projectId.value) {
    await store.fetchOne(projectId.value)
  }
}

function onJobCompleted(jobId) {
  // Refresh project to update job list
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
  color: #1a1a2e;
}

.project-meta {
  color: #90a4ae;
  font-size: 0.85rem;
}

.tab-nav {
  display: flex;
  gap: 0;
  border-bottom: 2px solid #e0e0e0;
  margin-bottom: 1.5rem;
}

.tab {
  padding: 0.75rem 1.5rem;
  text-decoration: none;
  color: #78909c;
  font-weight: 500;
  font-size: 0.9rem;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.2s;
}

.tab:hover {
  color: #1a1a2e;
}

.tab.active {
  color: #1a1a2e;
  border-bottom-color: #1a1a2e;
}

.dashboard-body {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
  min-height: calc(100vh - 200px);
}

.dashboard-body.with-console {
  grid-template-columns: 1fr 420px;
}

.main-panel {
  min-width: 0;
  padding-right: 0;
}

.dashboard-body.with-console .main-panel {
  padding-right: 1.5rem;
}

.console-aside {
  border-left: 1px solid #e0e0e0;
  border-radius: 0 8px 8px 0;
  overflow: hidden;
  height: calc(100vh - 200px);
  position: sticky;
  top: 80px;
}

.loading {
  text-align: center;
  padding: 3rem;
  color: #90a4ae;
}
</style>
