<template>
  <div class="console-panel">
    <div class="console-header">
      <h4>{{ $t('console.title') }}</h4>
      <span class="status-badge" :class="jobStatus" role="status"><span aria-hidden="true">{{ statusGlyph(jobStatus) }}</span> {{ statusLabel(jobStatus) }}</span>
      <template v-if="progress.generation > 0 && jobStatus === 'running'">
        <div class="progress-info">
          <span class="progress-gen">{{ $t('projectDashboard.gen') }} {{ progress.generation }}<template v-if="progress.maxGen"> / {{ progress.maxGen }}</template></span>
          <span class="progress-k" v-if="progress.k">k={{ progress.k }}</span>
          <span class="progress-lang" v-if="progress.language">{{ progress.language }}</span>
          <span class="progress-eta" v-if="etaDisplay">{{ etaDisplay }}</span>
        </div>
        <div class="progress-bar-wrap" v-if="progress.maxGen" role="progressbar" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(progressPct)" :aria-label="$t('console.progress')">
          <div class="progress-bar" :style="{ width: progressPct + '%' }"></div>
        </div>
      </template>
      <button
        v-if="canCancel"
        type="button"
        class="btn-cancel-job"
        :disabled="cancelling"
        @click="cancelJob"
      >{{ cancelling ? $t('console.cancelling') : $t('console.cancelJob') }}</button>
      <button
        v-if="jobStatus === 'completed'"
        type="button"
        class="btn-view-results"
        @click="$emit('view-results', jobId)"
      >{{ $t('projectDashboard.viewResults') }}</button>
      <button type="button" class="btn-toggle-chart" v-if="progressPoints.length >= 2" @click="showChart = !showChart" :aria-pressed="showChart ? 'true' : 'false'" :title="showChart ? $t('console.hideChart') : $t('console.showChart')" :aria-label="showChart ? $t('console.hideChart') : $t('console.showChart')">
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M1 12 L4 7 L7 9 L10 3 L13 5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <button type="button" class="close-btn" @click="$emit('close')" :title="$t('console.minimize')" :aria-label="$t('console.minimize')"><span aria-hidden="true">&#9660;</span></button>
    </div>

    <!-- Live sparkline charts -->
    <div v-if="showChart && progressPoints.length >= 2" class="chart-strip">
      <svg :viewBox="`0 0 ${chartW} ${chartH}`" class="sparkline-svg" preserveAspectRatio="none" role="img" :aria-label="$t('console.chartLabel', { gen: progress.generation, k: progress.k })">
        <!-- Grid lines -->
        <line x1="0" :y1="chartH * 0.25" :x2="chartW" :y2="chartH * 0.25" stroke="rgba(255,255,255,0.06)" stroke-width="0.5" />
        <line x1="0" :y1="chartH * 0.5" :x2="chartW" :y2="chartH * 0.5" stroke="rgba(255,255,255,0.06)" stroke-width="0.5" />
        <line x1="0" :y1="chartH * 0.75" :x2="chartW" :y2="chartH * 0.75" stroke="rgba(255,255,255,0.06)" stroke-width="0.5" />
        <!-- Generation line (cyan) -->
        <polyline :points="genPath" fill="none" stroke="#00BFFF" stroke-width="1.5" stroke-linejoin="round" />
        <!-- k line (green) -->
        <polyline :points="kPath" fill="none" stroke="#98c379" stroke-width="1.5" stroke-linejoin="round" stroke-dasharray="3,2" />
      </svg>
      <div class="chart-legend">
        <span class="legend-gen">&#9644; {{ $t('console.legendGeneration') }}</span>
        <span class="legend-k">&#9476; {{ $t('console.legendK') }}</span>
        <span class="legend-max" v-if="progress.maxGen">{{ $t('console.legendMax', { n: progress.maxGen }) }}</span>
      </div>
    </div>

    <div class="console" ref="consoleEl" tabindex="0" role="log" :aria-label="$t('console.title')">
      <pre v-html="renderedLog"></pre>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { api } from '../api'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/useToast'
import { useConfirm } from '../composables/useConfirm'
import { apiError, ignoreError } from '../utils/apiError'
import { statusLabel, statusGlyph, isLive, isCancelled } from '../utils/jobStatus'

const auth = useAuthStore()
const { t } = useI18n()
const { toast } = useToast()
const { confirmDialog } = useConfirm()

const props = defineProps({
  projectId: { type: String, required: true },
  jobId: { type: String, required: true },
})

const emit = defineEmits(['close', 'completed', 'failed', 'cancelled', 'progress', 'view-results'])

const logContent = ref('')
const jobStatus = ref('pending')
const consoleEl = ref(null)
const progress = ref({ generation: 0, maxGen: 0, k: 0, language: '' })
const progressPoints = ref([])
const showChart = ref(true)
let pollTimer = null
let ws = null
let wsConnected = false

const cancelling = ref(false)
const canCancel = computed(() => isLive(jobStatus.value))

async function cancelJob() {
  if (!(await confirmDialog({ message: t('console.cancelConfirm'), confirmLabel: t('console.cancelJob'), cancelLabel: t('console.keepRunning'), danger: true }))) return
  cancelling.value = true
  cancelRequested = true
  try {
    await api.analysis.cancelJob(props.projectId, props.jobId)
    toast.info(t('console.cancelRequested'))
  } catch (e) {
    toast.error(t('console.cancelFailed', { error: apiError(e) }))
  } finally {
    cancelling.value = false
  }
}

// The server reports a cancelled job as `failed` with the message "Cancelled by
// user.": tell the two apart so a deliberate stop is not announced as an error.
let cancelRequested = false

async function finish(status) {
  if (status === 'completed') { emit('completed', props.jobId); return }
  if (status === 'cancelled') { jobStatus.value = 'cancelled'; emit('cancelled', props.jobId); return }
  if (status !== 'failed') return
  let cancelled = cancelRequested
  if (!cancelled) {
    try {
      const { data } = await api.analysis.job(props.projectId, props.jobId, { silentError: true })
      cancelled = isCancelled(data)
    } catch (e) { ignoreError(e) }
  }
  if (cancelled) {
    jobStatus.value = 'cancelled'
    emitProgress()
    emit('cancelled', props.jobId)
  } else {
    emit('failed', props.jobId)
  }
}

let errorCount = 0
let startTime = null  // When we first see generation > 0

/* ── Sparkline chart ─────────────────────────────────── */
const chartW = 300
const chartH = 60

function buildPath(points, key, maxVal) {
  if (points.length < 2 || maxVal <= 0) return ''
  const xStep = chartW / (points.length - 1)
  return points.map((p, i) => {
    const x = i * xStep
    const y = chartH - (p[key] / maxVal) * (chartH - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

const genPath = computed(() => {
  const pts = progressPoints.value
  const maxGen = progress.value.maxGen || Math.max(...pts.map(p => p.generation), 1)
  return buildPath(pts, 'generation', maxGen)
})

const kPath = computed(() => {
  const pts = progressPoints.value
  const maxK = Math.max(...pts.map(p => p.k), 1)
  return buildPath(pts, 'k', maxK)
})

/* ── Progress parser ─────────────────────────────────── */
// Parses generation lines like: "#42      | best: Ternary:Prevalence  \t0 ████ 1 [k=55, age=0]"
const GEN_RE = /#(\d+)\s+\|\s+best:\s+(\S+)/
const K_RE = /\[k=(\d+)/

function parseProgress(text) {
  if (!text) return
  // Find the last generation line
  const lines = text.split('\n')
  let lastGen = 0, lastK = 0, lastLang = ''
  for (let i = lines.length - 1; i >= 0; i--) {
    // eslint-disable-next-line no-control-regex -- ESC is what starts an ANSI colour code
    const clean = lines[i].replace(/\x1b\[[0-9;]*m/g, '')
    const gm = clean.match(GEN_RE)
    if (gm) {
      lastGen = parseInt(gm[1])
      lastLang = gm[2]
      const km = clean.match(K_RE)
      if (km) lastK = parseInt(km[1])
      break
    }
  }
  if (lastGen > 0) {
    progress.value.generation = lastGen
    progress.value.k = lastK
    progress.value.language = lastLang
    // Start time tracking on first generation seen
    if (!startTime) startTime = Date.now()
  }
  // Try to extract maxGen from early lines (config echo)
  if (!progress.value.maxGen) {
    for (const line of lines.slice(0, 50)) {
      // eslint-disable-next-line no-control-regex -- ESC is what starts an ANSI colour code
      const clean = line.replace(/\x1b\[[0-9;]*m/g, '')
      // Look for max_epochs in config output
      const em = clean.match(/max_epochs[:\s]+(\d+)/i)
      if (em) { progress.value.maxGen = parseInt(em[1]); break }
    }
  }
  // Emit progress data to parent for minimized bar display
  emitProgress()
}

/* ── Handle structured progress from backend ─────────── */
function handleProgressData(data) {
  if (data.max_gen) progress.value.maxGen = data.max_gen
  if (data.points?.length > 0) {
    progressPoints.value = data.points
    const last = data.points[data.points.length - 1]
    progress.value.generation = last.generation
    progress.value.k = last.k
    progress.value.language = last.language
    if (!startTime && last.generation > 0) startTime = Date.now()
    emitProgress()
  }
}

/* ── ETA calculation ─────────────────────────────────── */
const progressPct = computed(() => {
  if (!progress.value.maxGen || progress.value.generation <= 0) return 0
  return Math.min(100, (progress.value.generation / progress.value.maxGen) * 100)
})

const etaDisplay = computed(() => {
  if (!startTime || !progress.value.maxGen || progress.value.generation <= 0) return ''
  const elapsed = (Date.now() - startTime) / 1000  // seconds
  const pct = progress.value.generation / progress.value.maxGen
  if (pct >= 1) return ''
  const totalEstimate = elapsed / pct
  const remaining = Math.max(0, totalEstimate - elapsed)
  return formatEta(remaining)
})

function formatEta(seconds) {
  let d
  if (seconds < 60) d = `${Math.ceil(seconds)}s`
  else if (seconds < 3600) d = `${Math.floor(seconds / 60)}m ${Math.ceil(seconds % 60)}s`
  else d = `${Math.floor(seconds / 3600)}h ${Math.ceil((seconds % 3600) / 60)}m`
  return t('console.etaLeft', { d })
}

function emitProgress() {
  emit('progress', {
    generation: progress.value.generation,
    maxGen: progress.value.maxGen,
    k: progress.value.k,
    language: progress.value.language,
    pct: progressPct.value,
    eta: etaDisplay.value,
    status: jobStatus.value,
  })
}

/* ── ANSI → HTML converter ───────────────────────────── */
const ANSI_COLORS = {
  30: '#4a4a4a', 31: '#e06c75', 32: '#98c379', 33: '#e5c07b',
  34: '#61afef', 35: '#c678dd', 36: '#56b6c2', 37: '#dcdfe4',
  90: '#7f848e', 91: '#e06c75', 92: '#98c379', 93: '#e5c07b',
  94: '#61afef', 95: '#c678dd', 96: '#56b6c2', 97: '#ffffff',
}

function escapeHtml(text) {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function ansiToHtml(text) {
  if (!text) return escapeHtml(t('console.waiting'))
  // Escape HTML first
  let html = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // Replace ANSI escape sequences
  // eslint-disable-next-line no-control-regex -- ESC is what starts an ANSI colour code
  html = html.replace(/\x1b\[([0-9;]*)m/g, (_, codes) => {
    if (!codes || codes === '0') return '</span>'
    const parts = codes.split(';')
    const styles = []
    for (const code of parts) {
      const n = parseInt(code, 10)
      if (n === 1) styles.push('font-weight:bold')
      else if (n === 3) styles.push('font-style:italic')
      else if (n === 4) styles.push('text-decoration:underline')
      else if (ANSI_COLORS[n]) styles.push(`color:${ANSI_COLORS[n]}`)
    }
    return styles.length ? `<span style="${styles.join(';')}">` : ''
  })
  return html
}

const renderedLog = computed(() => ansiToHtml(logContent.value))

/* ── Fetch max epochs from job config ─────────────────── */
async function fetchMaxEpochs() {
  try {
    const { data } = await api.analysis.job(props.projectId, props.jobId, { silentError: true })
    const epMatch = data.config_summary?.match(/ep=(\d+)/)
    if (epMatch) {
      progress.value.maxGen = parseInt(epMatch[1])
    }
  } catch (e) { ignoreError(e) }
}

/* ── WebSocket ───────────────────────────────────────── */
// The socket is opened with a one-time ticket, never with the access token:
// URLs end up in proxy and access logs. A server without the ticket endpoint
// gets no socket at all and the console polls over HTTP instead.
function getWsUrl(ticket) {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}/ws/jobs/${encodeURIComponent(props.projectId)}/${encodeURIComponent(props.jobId)}?ticket=${encodeURIComponent(ticket)}`
}

let consoleSeq = 0

async function connectWebSocket() {
  if (!auth.token || typeof WebSocket === 'undefined') return
  const seq = consoleSeq
  const ticket = await auth.wsTicket()
  // Unmounted, or switched to another job, while the ticket was being fetched.
  if (!ticket || seq !== consoleSeq) return
  try {
    ws = new WebSocket(getWsUrl(ticket))

    ws.onopen = () => {
      wsConnected = true
      stopPolling()  // WS is live, stop HTTP polling
      // The socket streams the log from its beginning: drop what polling fetched
      // so far, or it would appear twice.
      logContent.value = ''
      logOffset = 0
    }

    ws.onmessage = (event) => {
      let msg
      try { msg = JSON.parse(event.data) } catch { return }
      if (msg.type === 'log') {
        logContent.value += msg.content
        parseProgress(logContent.value)
        nextTick(() => {
          if (consoleEl.value) consoleEl.value.scrollTop = consoleEl.value.scrollHeight
        })
      } else if (msg.type === 'status') {
        jobStatus.value = msg.status
      } else if (msg.type === 'progress') {
        handleProgressData(msg.data)
      } else if (msg.type === 'done') {
        jobStatus.value = msg.status
        emitProgress()
        finish(msg.status)
        closeWebSocket()
      }
    }

    ws.onerror = () => {
      closeWebSocket()
      if (!wsConnected) startPolling()  // WS never connected, fall back
    }

    ws.onclose = () => {
      ws = null
      if (wsConnected && (jobStatus.value === 'running' || jobStatus.value === 'pending')) {
        wsConnected = false
        startPolling()  // Unexpected close, fall back to polling
      }
    }
  } catch {
    startPolling()
  }
}

function closeWebSocket() {
  if (ws) { try { ws.close() } catch { /* ignore */ } ws = null }
}

/* ── HTTP Polling (fallback) ─────────────────────────── */
// Incremental: each poll asks only for what was written since the last one
// (`?offset=`). Servers that do not report `next_offset` send the whole log
// every time, which we then simply replace.
let logOffset = 0
let pollBusy = false

async function pollLogs() {
  if (pollBusy) return
  pollBusy = true
  const seq = consoleSeq
  try {
    const config = { silentError: true }
    if (logOffset > 0) config.params = { offset: logOffset }
    const { data } = await api.analysis.jobLogs(props.projectId, props.jobId, config)
    if (seq !== consoleSeq) return
    errorCount = 0
    const chunk = data.log || ''
    if (typeof data.next_offset === 'number') {
      const from = typeof data.offset === 'number' ? data.offset : logOffset
      // offset 0 (first poll, or the server restarted the log) replaces; otherwise append.
      logContent.value = from > 0 && from === logOffset ? logContent.value + chunk : chunk
      logOffset = data.next_offset
    } else {
      logContent.value = chunk
    }
    jobStatus.value = data.status
    if (chunk) parseProgress(logContent.value)

    await nextTick()
    if (chunk && consoleEl.value) {
      consoleEl.value.scrollTop = consoleEl.value.scrollHeight
    }

    if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
      stopPolling()
      emitProgress()
      finish(data.status)
    }
  } catch (e) {
    ignoreError(e)
    if (seq !== consoleSeq) return
    errorCount++
    if (errorCount >= 10) {
      logContent.value = t('console.lostConnection', { error: apiError(e) })
      jobStatus.value = 'failed'
      stopPolling()
      emit('failed', props.jobId)
    }
  } finally {
    pollBusy = false
  }
}

async function pollProgress() {
  try {
    const { data } = await api.analysis.jobProgress(props.projectId, props.jobId, { silentError: true })
    if (data.points?.length > 0) handleProgressData(data)
  } catch (e) { ignoreError(e) }
}

function startPolling() {
  if (pollTimer) return  // Already polling
  fetchMaxEpochs()
  pollLogs()
  pollProgress()
  pollTimer = setInterval(() => { pollLogs(); pollProgress() }, 1000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

/* ── Lifecycle ───────────────────────────────────────── */
function startConsole() {
  fetchMaxEpochs()
  connectWebSocket()
  // Start polling as initial fallback; will be stopped if WS connects
  startPolling()
}

function stopConsole() {
  consoleSeq++
  stopPolling()
  closeWebSocket()
  wsConnected = false
  logOffset = 0
  cancelRequested = false
}

watch(() => props.jobId, (newId) => {
  if (newId) {
    logContent.value = ''
    jobStatus.value = 'pending'
    progress.value = { generation: 0, maxGen: 0, k: 0, language: '' }
    progressPoints.value = []
    startTime = null
    stopConsole()
    startConsole()
  }
})

onMounted(startConsole)
onUnmounted(stopConsole)
</script>

<style scoped>
.console-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--console-bg);
  color: var(--console-text);
}

.console-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-bottom: 1px solid var(--console-border);
  flex-shrink: 0;
}

.console-header h4 {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-nav-link);
  flex: 1;
}

.status-badge {
  padding: 0.1rem 0.4rem;
  border-radius: 8px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge.pending { background: var(--warning-bg); color: var(--warning-dark); }
.status-badge.running { background: var(--info-bg); color: var(--info); }
.status-badge.completed { background: var(--success-bg); color: var(--success-dark); }
.status-badge.failed { background: var(--danger-bg); color: var(--danger-dark); }
.status-badge.cancelled { background: var(--bg-badge); color: var(--text-secondary); }

.close-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 0.9rem;
  cursor: pointer;
  padding: 0 0.25rem;
  line-height: 1;
}

.close-btn:hover { color: var(--console-text); }

.btn-toggle-chart {
  background: none;
  border: 1px solid rgba(255,255,255,0.15);
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.15rem 0.3rem;
  border-radius: 4px;
  display: flex;
  align-items: center;
  transition: all 0.15s;
}
.btn-toggle-chart:hover {
  border-color: #00BFFF;
  color: #00BFFF;
}

/* Progress indicators */
.progress-info {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  font-size: 0.75rem;
  color: var(--text-nav-link);
}
.progress-gen {
  font-weight: 600;
  color: #00BFFF;
}
.progress-k {
  color: #98c379;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}
.progress-lang {
  color: var(--text-muted);
  font-size: 0.75rem;
}
.progress-eta {
  color: #e5c07b;
  font-size: 0.75rem;
  font-style: italic;
}
.progress-bar-wrap {
  width: 80px;
  height: 6px;
  background: rgba(255,255,255,0.1);
  border-radius: 3px;
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #00BFFF, #00e5ff);
  border-radius: 3px;
  transition: width 0.3s ease;
}

/* Live sparkline chart strip */
.chart-strip {
  padding: 0.4rem 1rem 0.25rem;
  border-bottom: 1px solid var(--console-border);
  flex-shrink: 0;
}

.sparkline-svg {
  width: 100%;
  height: 50px;
  display: block;
}

.chart-legend {
  display: flex;
  gap: 0.75rem;
  font-size: 0.75rem;
  padding-top: 0.15rem;
}
.legend-gen { color: #00BFFF; }
.legend-k { color: #98c379; }
.legend-max { color: var(--text-muted); margin-left: auto; }

.console {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem 1rem;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 0.75rem;
  line-height: 1.4;
}

.console pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}
.btn-cancel-job, .btn-view-results {
  border-radius: 4px;
  padding: 0.15rem 0.6rem;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  background: transparent;
}
.btn-cancel-job { border: 1px solid #e06c75; color: #e06c75; }
.btn-cancel-job:disabled { opacity: 0.6; cursor: default; }
.btn-view-results { border: 1px solid #98c379; color: #98c379; }
</style>
