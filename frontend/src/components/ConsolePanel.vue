<template>
  <div class="console-panel">
    <div class="console-header">
      <h4>Console Output</h4>
      <span class="status-badge" :class="jobStatus">{{ jobStatus }}</span>
      <button class="close-btn" @click="$emit('close')" title="Minimize console">&#9660;</button>
    </div>
    <div class="console" ref="consoleEl">
      <pre v-html="renderedLog"></pre>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import axios from 'axios'

const props = defineProps({
  projectId: { type: String, required: true },
  jobId: { type: String, required: true },
})

const emit = defineEmits(['close', 'completed', 'failed'])

const logContent = ref('')
const jobStatus = ref('pending')
const consoleEl = ref(null)
let pollTimer = null

let errorCount = 0

/* ── ANSI → HTML converter ───────────────────────────── */
const ANSI_COLORS = {
  30: '#4a4a4a', 31: '#e06c75', 32: '#98c379', 33: '#e5c07b',
  34: '#61afef', 35: '#c678dd', 36: '#56b6c2', 37: '#dcdfe4',
  90: '#7f848e', 91: '#e06c75', 92: '#98c379', 93: '#e5c07b',
  94: '#61afef', 95: '#c678dd', 96: '#56b6c2', 97: '#ffffff',
}

function ansiToHtml(text) {
  if (!text) return 'Waiting for output...'
  // Escape HTML first
  let html = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // Replace ANSI escape sequences
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

/* ── Polling ─────────────────────────────────────────── */
async function pollLogs() {
  try {
    const { data } = await axios.get(`/api/analysis/${props.projectId}/jobs/${props.jobId}/logs`)
    errorCount = 0
    logContent.value = data.log
    jobStatus.value = data.status

    await nextTick()
    if (consoleEl.value) {
      consoleEl.value.scrollTop = consoleEl.value.scrollHeight
    }

    if (data.status === 'completed') {
      stopPolling()
      emit('completed', props.jobId)
    } else if (data.status === 'failed') {
      stopPolling()
      emit('failed', props.jobId)
    }
  } catch (e) {
    errorCount++
    if (errorCount >= 10) {
      logContent.value = '[error] Job not found. Close the console and re-launch the analysis.'
      jobStatus.value = 'failed'
      stopPolling()
      emit('failed', props.jobId)
    }
  }
}

function startPolling() {
  pollLogs()
  pollTimer = setInterval(pollLogs, 1000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

watch(() => props.jobId, (newId) => {
  if (newId) {
    logContent.value = ''
    jobStatus.value = 'pending'
    stopPolling()
    startPolling()
  }
})

onMounted(startPolling)
onUnmounted(stopPolling)
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
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge.pending { background: var(--warning-bg); color: var(--warning-dark); }
.status-badge.running { background: var(--info-bg); color: var(--info); }
.status-badge.completed { background: var(--success-bg); color: var(--success-dark); }
.status-badge.failed { background: var(--danger-bg); color: var(--danger-dark); }

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

.console {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem 1rem;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 0.72rem;
  line-height: 1.4;
}

.console pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
