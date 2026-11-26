<template>
  <div class="project-dashboard" v-if="project && !loadError">
    <header class="project-header">
      <h2>{{ project.name }}</h2>
      <div class="project-meta">
        {{ project.datasets?.length || 0 }} {{ $t('projectDashboard.datasets') }} &middot;
        {{ project.jobs?.length || 0 }} {{ $t('projectDashboard.jobs') }}
      </div>
      <template v-if="!uiMode.isSimple">
      <button type="button" class="share-btn" @click="showShare = true">{{ $t('projectDashboard.share') }}</button>
      <button type="button" class="share-btn" @click="showPublicShare = true">{{ $t('projectDashboard.publicLink') }}</button>
      <button type="button" class="share-btn" :aria-expanded="showComments ? 'true' : 'false'" @click="showComments = !showComments">{{ $t('projectDashboard.notes') }}</button>
      </template>
    </header>

    <!-- Simple mode: one guided page instead of the tabs -->
    <SimpleProject v-if="uiMode.isSimple" :project-id="projectId" />

    <template v-else>

    <ShareModal
      v-if="showShare"
      :project-id="projectId"
      @close="showShare = false"
    />

    <PublicShareModal
      v-if="showPublicShare"
      :project-id="projectId"
      @close="showPublicShare = false"
    />

    <CommentsSidebar
      :project-id="projectId"
      :visible="showComments"
      @close="showComments = false"
    />

    <nav class="tab-nav" :aria-label="$t('projectDashboard.sectionsNav')">
      <router-link :to="`/project/${projectId}/data`" class="tab" :class="{ active: isSection('data') }" :aria-current="isSection('data') ? 'page' : undefined">{{ $t('projectDashboard.dataTab') }}</router-link>
      <router-link :to="`/project/${projectId}/parameters`" class="tab" :class="{ active: isSection('parameters') }" :aria-current="isSection('parameters') ? 'page' : undefined">{{ $t('projectDashboard.parametersTab') }}</router-link>
      <router-link :to="`/project/${projectId}/results`" class="tab" :class="{ active: isSection('results') }" :aria-current="isSection('results') ? 'page' : undefined">{{ $t('projectDashboard.resultsTab') }}</router-link>
    </nav>

    <div class="dashboard-body">
      <div class="main-panel">
        <ProjectChecklist :project-id="projectId" :project="project" :jobs="checklistJobs" />
        <router-view />
      </div>
      <div v-if="store.activeJobId" class="console-bottom" :class="{ minimized: !store.showConsole }">
        <button v-if="!store.showConsole" type="button" class="console-minimized-bar" :aria-label="$t('projectDashboard.expandConsole')" @click="store.showConsole = true">
          <ProgressCircle
            v-if="jobProgress.pct > 0 && jobProgress.status === 'running'"
            :pct="jobProgress.pct"
            :size="28"
            :stroke-width="3"
          />
          <span>{{ $t('projectDashboard.console') }}</span>
          <span class="status-badge-mini" :class="miniStatus">{{ $t(`common.${miniStatus}`) }}</span>
          <template v-if="jobProgress.status === 'running' && jobProgress.generation > 0">
            <span class="mini-gen">{{ $t('projectDashboard.gen') }} {{ jobProgress.generation }}<template v-if="jobProgress.maxGen"> / {{ jobProgress.maxGen }}</template></span>
            <span class="mini-eta" v-if="jobProgress.eta">{{ jobProgress.eta }}</span>
          </template>
          <span class="expand-icon" aria-hidden="true">&#9650;</span>
        </button>
        <ConsolePanel
          v-else
          :project-id="projectId"
          :job-id="store.activeJobId"
          @close="store.showConsole = false"
          @completed="onJobCompleted"
          @failed="onJobFailed"
          @cancelled="onJobCancelled"
          @view-results="viewResults"
          @progress="onProgress"
        />
      </div>
    </div>
    </template>
  </div>
  <div v-else class="project-dashboard">
    <AsyncState
      :loading="loading"
      :error="loadError"
      :retry="loadProject"
      :loading-text="$t('projectDashboard.loadingProject')"
      :error-title="$t('projectDashboard.loadFailed')"
    />
    <p v-if="loadError" class="back-to-projects">
      <router-link to="/projects">{{ $t('projectDashboard.backToProjects') }}</router-link>
    </p>
  </div>
</template>

<script setup>
import { normalizeJobs } from '../utils/jobStatus'
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { useProjectStore } from '../stores/project'
import { useConfigStore } from '../stores/config'
import ConsolePanel from '../components/ConsolePanel.vue'
import ProjectChecklist from '../components/ProjectChecklist.vue'
import { markChecklistStep } from '../utils/projectChecklist'
import ProgressCircle from '../components/ProgressCircle.vue'
import ShareModal from '../components/ShareModal.vue'
import CommentsSidebar from '../components/CommentsSidebar.vue'
import PublicShareModal from '../components/PublicShareModal.vue'
import AsyncState from '../components/AsyncState.vue'
import SimpleProject from './SimpleProject.vue'
import { useUiModeStore } from '../stores/uiMode'
import { notifyJobCompleted, notifyJobFailed } from '../utils/notify'
import { apiError, ignoreError } from '../utils/apiError'
import { useToast } from '../composables/useToast'
import { useI18n } from 'vue-i18n'

const route = useRoute()
const router = useRouter()
const store = useProjectStore()
const uiMode = useUiModeStore()
const { addToast } = useToast()
const { t } = useI18n()
const showShare = ref(route.query.share === '1')
const showPublicShare = ref(false)
const showComments = ref(false)
const jobProgress = reactive({ generation: 0, maxGen: 0, k: 0, language: '', pct: 0, eta: '', status: 'pending' })

const loading = ref(false)
const loadError = ref('')

// Parameter draft and data filters belong to one project.
const configStore = useConfigStore()
configStore.bindProject(route.params.id)

const projectId = computed(() => route.params.id)
// Never show another project's data while the requested one is loading.
const project = computed(() => (store.current?.project_id === projectId.value ? store.current : null))

// ── Next-step checklist ────────────────────────────────────────────────────
const checklistJobs = computed(() => (Array.isArray(project.value?.jobs) ? project.value.jobs : []))
// "Parameters reviewed" and "results viewed" are facts about what the user has
// opened, so they are recorded here as the route changes.
watch(
  () => [route.name, projectId.value, checklistJobs.value.some(j => j && typeof j === 'object' && j.status === 'completed')],
  ([name, id, hasCompleted]) => {
    if (!id) return
    if (name === 'ProjectParameters') markChecklistStep(id, 'parameters')
    if ((name === 'ProjectResults' || name === 'ProjectJobResults') && hasCompleted) markChecklistStep(id, 'results')
  },
  { immediate: true },
)
const KNOWN_STATUSES = ['pending', 'running', 'completed', 'failed', 'cancelled']
const miniStatus = computed(() => {
  const job = store.current?.jobs?.find(j => j.job_id === store.activeJobId)
  const st = job?.status || jobProgress.status || 'running'
  return KNOWN_STATUSES.includes(st) ? st : 'running'
})

let loadSeq = 0
async function loadProject({ quiet = false } = {}) {
  const id = projectId.value
  if (!id) return
  const mine = ++loadSeq
  if (!quiet) {
    loading.value = true
    loadError.value = ''
    if (store.current?.project_id !== id) store.current = null
  }
  try {
    await store.fetchOne(id)
  } catch (e) {
    if (mine !== loadSeq || quiet) { ignoreError(e); return }
    loadError.value = apiError(e)
    loading.value = false
    return
  }
  if (mine !== loadSeq) return
  loading.value = false
  // Immediately fetch full job list so store.current.jobs contains objects
  // (the project endpoint only returns job IDs as strings)
  try {
    const { data: rawJobs } = await api.analysis.listJobs(id, { silentError: true })
    if (mine !== loadSeq) return
    const data = normalizeJobs(rawJobs)
    if (store.current) store.current.jobs = data
    reattachActiveJob(data)
  } catch (e) { ignoreError(e) /* ResultsTab loads and reports its own list */ }
}

/** After a refresh or a return to the project, pick the running job back up. */
function reattachActiveJob(jobs) {
  if (!Array.isArray(jobs)) return
  const current = jobs.find(j => j.job_id === store.activeJobId)
  if (current && (current.status === 'running' || current.status === 'pending')) return
  const live = jobs.find(j => j.status === 'running') || jobs.find(j => j.status === 'pending')
  if (live) {
    store.activeJobId = live.job_id
    // Minimised: visible progress without covering the page the user came back to.
    if (!current) store.showConsole = false
  } else if (!current) {
    store.activeJobId = null
  }
}

function viewResults(jobId) {
  router.push({ name: 'ProjectJobResults', params: { id: projectId.value, jobId } }).catch(() => {})
}

async function onJobCompleted(jobId) {
  await loadProject({ quiet: true })
  const action = { label: t('projectDashboard.viewResults'), onClick: () => viewResults(jobId) }
  // Send browser notification + in-app toast with AUC if available
  try {
    const { data } = await api.analysis.job(projectId.value, jobId, { silentError: true })
    const aucStr = data.best_auc != null ? ` — AUC ${Number(data.best_auc).toFixed(4)}` : ''
    const kStr = data.best_k != null ? ` (k=${data.best_k})` : ''
    addToast(`${t('projectDashboard.jobCompleted')}${aucStr}${kStr}`, 'success', 15000, { action })
    notifyJobCompleted(project.value?.name || t('projectDashboard.projectFallback'), {
      auc: data.best_auc,
      k: data.best_k,
      jobId,
    })
  } catch (e) {
    ignoreError(e)
    addToast(t('projectDashboard.jobCompleted'), 'success', 15000, { action })
    notifyJobCompleted(project.value?.name || t('projectDashboard.projectFallback'), { jobId })
  }
}

async function onJobFailed(jobId) {
  await loadProject({ quiet: true })
  addToast(t('projectDashboard.jobFailed'), 'error', 12000, {
    action: { label: t('projectDashboard.viewDetails'), onClick: () => viewResults(jobId) },
  })
  notifyJobFailed(project.value?.name || t('projectDashboard.projectFallback'), { jobId })
}

async function onJobCancelled() {
  await loadProject({ quiet: true })
  addToast(t('projectDashboard.jobCancelled'), 'info', 6000)
}

function onProgress(data) {
  Object.assign(jobProgress, data)
}

watch(projectId, () => {
  // The console belongs to one project; do not carry it into another.
  store.activeJobId = null
  store.showConsole = false
  configStore.bindProject(projectId.value)
  loadProject()
})
onMounted(() => loadProject())

/**
 * Project tab state from the URL prefix: "/results/<job id>" is a separate route
 * from "/results", so router-link's own active class missed it.
 */
function isSection(segment) {
  return route.path.startsWith(`/project/${projectId.value}/${segment}`)
}
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
  position: relative;
  z-index: 11;
  background: var(--bg-card, #fff);
}

.tab {
  padding: 0.75rem 1.5rem;
  text-decoration: none;
  color: var(--text-secondary);
  font-weight: 600;
  font-size: 0.95rem;
  border-bottom: 3px solid transparent;
  margin-bottom: -2px;
  transition: all 0.2s;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.tab:hover {
  color: var(--text-primary);
  background: rgba(0, 0, 0, 0.03);
  border-bottom-color: var(--border-light);
}

.tab.active {
  color: var(--tab-active);
  border-bottom-color: var(--tab-active);
  background: var(--bg-badge);
  font-weight: 700;
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
  font-size: 0.75rem;
}

.status-badge-mini {
  padding: 0.1rem 0.4rem;
  border-radius: 8px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge-mini.pending { background: var(--warning-bg); color: var(--warning-dark); }
.status-badge-mini.running { background: var(--info-bg); color: var(--info); }
.status-badge-mini.completed { background: var(--success-bg); color: var(--success-dark); }
.status-badge-mini.failed { background: var(--danger-bg); color: var(--danger-dark); }

.mini-gen {
  font-size: 0.75rem;
  font-weight: 600;
  color: #00BFFF;
}
.mini-eta {
  font-size: 0.75rem;
  color: #e5c07b;
  font-style: italic;
}

.loading {
  text-align: center;
  padding: 3rem;
  color: var(--text-faint);
}
.back-to-projects { margin-top: 0.75rem; font-size: 0.9rem; }
button.console-minimized-bar {
  width: 100%;
  border: none;
  font: inherit;
  text-align: left;
}
@media (max-width: 700px) {
  .project-header { flex-wrap: wrap; gap: 0.4rem; }
  .tab-nav { overflow-x: auto; white-space: nowrap; }
}
</style>
