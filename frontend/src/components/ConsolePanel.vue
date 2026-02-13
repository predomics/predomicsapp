<template>
  <div class="console-panel">
    <div class="console-header">
      <h4>Console Output</h4>
      <span class="status-badge" :class="jobStatus">{{ jobStatus }}</span>
      <button class="close-btn" @click="$emit('close')" title="Close console">&times;</button>
    </div>
    <div class="console" ref="consoleEl">
      <pre>{{ logContent || 'Waiting for output...' }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
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
  background: #1a1a2e;
  color: #e0e0e0;
}

.console-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #2d2d4a;
  flex-shrink: 0;
}

.console-header h4 {
  margin: 0;
  font-size: 0.85rem;
  color: #b0bec5;
  flex: 1;
}

.status-badge {
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge.pending { background: #fff3e0; color: #e65100; }
.status-badge.running { background: #e3f2fd; color: #1565c0; }
.status-badge.completed { background: #e8f5e9; color: #2e7d32; }
.status-badge.failed { background: #fce4ec; color: #c62828; }

.close-btn {
  background: none;
  border: none;
  color: #546e7a;
  font-size: 1.2rem;
  cursor: pointer;
  padding: 0 0.25rem;
  line-height: 1;
}

.close-btn:hover { color: #e0e0e0; }

.console {
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem 1rem;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 0.75rem;
  line-height: 1.5;
}

.console pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
