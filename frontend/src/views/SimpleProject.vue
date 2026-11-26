<template>
  <div class="simple-project">
    <!-- ── Step 1: data ─────────────────────────────────────────────── -->
    <section class="step" :class="{ done: hasData }" aria-labelledby="simple-step1">
      <h3 id="simple-step1"><span class="step-num" aria-hidden="true">1</span>{{ $t('simple.step1.title') }}</h3>
      <p class="step-help">{{ $t('simple.step1.help') }}</p>

      <div class="file-rows">
        <div v-for="slot in slots" :key="slot.role" class="file-row">
          <div class="file-label">
            <strong>{{ slot.label }}</strong>
            <span class="file-hint">{{ slot.hint }}</span>
          </div>
          <div class="file-state">
            <span v-if="slot.file" class="file-ok">&#10003; {{ slot.file.filename }}</span>
            <span v-else class="file-missing">{{ $t('simple.step1.missing') }}</span>
            <label class="btn btn-secondary" :class="{ busy: uploads[slot.role]?.busy }">
              <template v-if="uploads[slot.role]?.busy">{{ $t('data.uploadingPct', { pct: uploads[slot.role].pct }) }}</template>
              <template v-else>{{ slot.file ? $t('simple.step1.replace') : $t('simple.step1.choose') }}</template>
              <input
                type="file"
                accept=".tsv,.csv,.txt"
                class="sr-only"
                :disabled="!canEdit || uploads[slot.role]?.busy"
                :aria-label="slot.label"
                @change="e => upload(e, slot.role)"
              />
            </label>
          </div>
          <p v-if="uploads[slot.role]?.error" class="msg-error" role="alert">{{ uploads[slot.role].error }}</p>
        </div>
      </div>

      <details class="format-help">
        <summary>{{ $t('simple.step1.formatTitle') }}</summary>
        <p>{{ $t('simple.step1.formatText') }}</p>
        <pre>{{ formatExample }}</pre>
      </details>
    </section>

    <!-- ── Step 2: run ──────────────────────────────────────────────── -->
    <section class="step" :class="{ disabled: !hasData }" aria-labelledby="simple-step2">
      <h3 id="simple-step2"><span class="step-num" aria-hidden="true">2</span>{{ $t('simple.step2.title') }}</h3>
      <p class="step-help">{{ $t('simple.step2.help') }}</p>

      <fieldset class="presets" :disabled="!hasData || !!running">
        <legend class="sr-only">{{ $t('parameters.presets.title') }}</legend>
        <label v-for="p in presetIds" :key="p" class="preset" :class="{ active: preset === p }">
          <input v-model="preset" type="radio" name="simple-preset" :value="p" class="sr-only" />
          <span class="preset-name">{{ $t(`simple.presets.${p}.name`) }}</span>
          <span class="preset-time">{{ $t(`simple.presets.${p}.time`) }}</span>
          <span class="preset-desc">{{ $t(`simple.presets.${p}.desc`) }}</span>
        </label>
      </fieldset>

      <div class="run-bar">
        <button
          type="button"
          class="btn btn-primary btn-run"
          :disabled="!hasData || !canEdit || launching || !!running"
          @click="launch"
        >{{ launching ? $t('parameters.launching') : $t('simple.step2.run') }}</button>
        <span v-if="!hasData" class="run-hint">{{ $t('simple.step2.needData') }}</span>
        <span v-else-if="!canEdit" class="run-hint">{{ $t('simple.step2.readOnly') }}</span>
      </div>
      <p v-if="launchError" class="msg-error" role="alert">{{ launchError }}</p>
    </section>

    <!-- ── Step 3: result ───────────────────────────────────────────── -->
    <section class="step" :class="{ disabled: !running && !result && !lastFailure }" aria-labelledby="simple-step3" aria-live="polite">
      <h3 id="simple-step3"><span class="step-num" aria-hidden="true">3</span>{{ $t('simple.step3.title') }}</h3>

      <!-- Running -->
      <div v-if="running" class="running">
        <p>{{ $t('simple.step3.running') }}</p>
        <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="progressPct">
          <div class="progress-bar" :class="{ indeterminate: !progressPct }" :style="progressPct ? { width: progressPct + '%' } : null"></div>
        </div>
        <p class="progress-text">
          <template v-if="progressPct">{{ $t('simple.step3.progress', { pct: progressPct }) }}</template>
          <template v-else>{{ $t('simple.step3.starting') }}</template>
        </p>
        <button type="button" class="btn btn-link" :disabled="cancelling || !canEdit" @click="cancel">{{ $t('simple.step3.cancel') }}</button>
      </div>

      <!-- Failed -->
      <div v-else-if="lastFailure && !result" class="msg-error" role="alert">
        {{ $t('simple.step3.failed') }}
        <span v-if="lastFailure.error_message" class="fail-detail">{{ lastFailure.error_message }}</span>
      </div>

      <!-- Result -->
      <template v-else-if="result">
        <div v-if="resultLoading" class="muted">{{ $t('common.loading') }}</div>
        <template v-else-if="detail">
          <div class="verdict" :class="grade">
            <div class="verdict-score">
              <span class="score-value">{{ fmt(mainAuc) }}</span>
              <span class="score-label">{{ detail.best_auc_test != null ? $t('simple.result.aucTest') : $t('simple.result.aucTrain') }}</span>
            </div>
            <div class="verdict-text">
              <strong>{{ $t(`simple.grade.${grade || 'chance'}.title`) }}</strong>
              <p>{{ $t(`simple.grade.${grade || 'chance'}.text`) }}</p>
              <p v-if="detail.best_auc_test == null" class="muted small">{{ $t('simple.result.noTest') }}</p>
              <p v-else-if="overfit" class="warn small">{{ $t('simple.result.overfit', { train: fmt(detail.best_auc), test: fmt(detail.best_auc_test) }) }}</p>
            </div>
          </div>

          <dl class="metrics">
            <div><dt>{{ $t('simple.result.k') }}</dt><dd>{{ detail.best_k ?? '—' }}</dd></div>
            <div v-if="best"><dt>{{ $t('simple.result.accuracy') }}</dt><dd>{{ pct(best.accuracy) }}</dd></div>
            <div v-if="best"><dt>{{ $t('simple.result.sensitivity') }}</dt><dd>{{ pct(best.sensitivity) }}</dd></div>
            <div v-if="best"><dt>{{ $t('simple.result.specificity') }}</dt><dd>{{ pct(best.specificity) }}</dd></div>
          </dl>

          <h4>{{ $t('simple.result.signature') }}</h4>
          <p class="step-help">{{ $t('simple.result.signatureHelp') }}</p>
          <div class="signature" :class="{ single: !signature.up.length || !signature.down.length }">
            <div v-if="signature.up.length" class="sig-col up">
              <h5>{{ $t('simple.result.higherIn', { cls: classA }) }} <span class="sig-n">({{ signature.up.length }})</span></h5>
              <ul><li v-for="f in signature.up" :key="f">{{ f }}</li></ul>
            </div>
            <div v-if="signature.down.length" class="sig-col down">
              <h5>{{ $t('simple.result.higherIn', { cls: classB }) }} <span class="sig-n">({{ signature.down.length }})</span></h5>
              <ul><li v-for="f in signature.down" :key="f">{{ f }}</li></ul>
            </div>
          </div>
        </template>

        <div class="result-footer">
          <label v-if="completedJobs.length > 1" class="history">
            {{ $t('simple.result.history') }}
            <select v-model="selectedJobId">
              <option v-for="j in completedJobs" :key="j.job_id" :value="j.job_id">{{ jobLabel(j) }}</option>
            </select>
          </label>
          <button type="button" class="btn btn-link" @click="openExpert">{{ $t('simple.result.openExpert') }}</button>
        </div>
      </template>

      <p v-else class="muted">{{ $t('simple.step3.empty') }}</p>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { useProjectStore } from '../stores/project'
import { useUiModeStore } from '../stores/uiMode'
import { allProjectFiles } from '../utils/analysis'
import { normalizeJobs, isCancelled } from '../utils/jobStatus'
import { classLabel } from '../utils/classNames'
import { apiError, ignoreError } from '../utils/apiError'
import { LONG_TIMEOUT_MS } from '../utils/http'
import { requestPermission, notifyJobCompleted } from '../utils/notify'
import {
  SIMPLE_PRESETS, DEFAULT_SIMPLE_PRESET, buildSimplePayload, aucGrade,
  splitSignature, latestCompletedJob, liveJob,
} from '../utils/simpleRun'

const props = defineProps({
  projectId: { type: String, required: true },
})

const router = useRouter()
const { t, locale } = useI18n()
const store = useProjectStore()
const uiMode = useUiModeStore()

const project = computed(() => (store.current?.project_id === props.projectId ? store.current : null))
// Viewers can read results but not upload or launch.
const canEdit = computed(() => !project.value?.role || ['owner', 'editor'].includes(project.value.role))

// ── Step 1: data ──────────────────────────────────────────────────────────
const files = computed(() => allProjectFiles(project.value?.datasets))
const fileFor = role => files.value.find(f => f.role === role) || null
const slots = computed(() => [
  { role: 'xtrain', label: t('simple.step1.x'), hint: t('simple.step1.xHint'), file: fileFor('xtrain') },
  { role: 'ytrain', label: t('simple.step1.y'), hint: t('simple.step1.yHint'), file: fileFor('ytrain') },
])
const hasData = computed(() => !!(fileFor('xtrain') && fileFor('ytrain')))
const uploads = reactive({})

const formatExample = [
  'feature\tsample_1\tsample_2\tsample_3',
  'msp_0001\t0.0012\t0\t0.0450',
  'msp_0002\t0\t0.0031\t0.0007',
  '',
  'sample\tclass',
  'sample_1\t0',
  'sample_2\t1',
  'sample_3\t1',
].join('\n')

async function upload(event, role) {
  const input = event.target
  const file = input.files?.[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  uploads[role] = { busy: true, pct: 0, error: '' }
  try {
    await api.projects.uploadDataset(props.projectId, formData, {
      params: { role },
      timeout: LONG_TIMEOUT_MS,
      onUploadProgress: (ev) => {
        if (ev.total) uploads[role].pct = Math.min(100, Math.round((ev.loaded / ev.total) * 100))
      },
    })
    await store.fetchOne(props.projectId)
    await refreshJobs()
    uploads[role] = { busy: false, pct: 100, error: fileFor(role) ? '' : t('data.uploadNotAssigned', { name: file.name }) }
  } catch (e) {
    uploads[role] = { busy: false, pct: 0, error: t('data.uploadFailed', { error: apiError(e) }) }
  } finally {
    input.value = ''
  }
}

// ── Step 2: run ───────────────────────────────────────────────────────────
const presetIds = SIMPLE_PRESETS
const preset = ref(DEFAULT_SIMPLE_PRESET)
const launching = ref(false)
const launchError = ref('')

async function launch() {
  if (!hasData.value || launching.value) return
  launching.value = true
  launchError.value = ''
  try {
    const params = { x_file_id: fileFor('xtrain').id, y_file_id: fileFor('ytrain').id }
    // A test set uploaded in expert mode is still used: it gives an honest score.
    if (fileFor('xtest') && fileFor('ytest')) {
      params.xtest_file_id = fileFor('xtest').id
      params.ytest_file_id = fileFor('ytest').id
    }
    params.job_name = t('simple.jobName', { preset: t(`simple.presets.${preset.value}.name`) })
    const { data } = await api.analysis.run(props.projectId, buildSimplePayload(preset.value), { params })
    store.activeJobId = data.job_id
    store.showConsole = false
    requestPermission()
    await refreshJobs()
    startPolling()
  } catch (e) {
    launchError.value = t('parameters.launchFailed', { error: apiError(e) })
  } finally {
    launching.value = false
  }
}

// ── Jobs and progress ─────────────────────────────────────────────────────
const jobs = ref([])
const running = computed(() => liveJob(jobs.value))
const completedJobs = computed(() => {
  const done = jobs.value.filter(j => j.status === 'completed')
  return done.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
})
const lastFailure = computed(() => {
  const sorted = [...jobs.value].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  const last = sorted[0]
  return last && last.status === 'failed' && !isCancelled(last) ? last : null
})
const selectedJobId = ref(null)
const result = computed(() => completedJobs.value.find(j => j.job_id === selectedJobId.value) || null)

const progressPct = ref(0)
const cancelling = ref(false)
let pollTimer = null

async function refreshJobs() {
  try {
    const { data } = await api.analysis.listJobs(props.projectId, { silentError: true })
    const list = normalizeJobs(data)
    const wasRunning = running.value?.job_id
    jobs.value = list
    if (store.current?.project_id === props.projectId) store.current.jobs = list
    // A run just ended (or this is the first load): show the newest result.
    if (!selectedJobId.value || (wasRunning && !running.value)) {
      selectedJobId.value = latestCompletedJob(list)?.job_id || null
      if (wasRunning && !running.value) {
        const finished = list.find(j => j.job_id === wasRunning)
        if (finished?.status === 'completed') {
          notifyJobCompleted(project.value?.name || '', { auc: finished.best_auc, k: finished.best_k, jobId: finished.job_id })
        }
      }
    }
  } catch (e) { ignoreError(e) }
}

async function pollProgress() {
  const job = running.value
  if (!job) { stopPolling(); return }
  try {
    const { data } = await api.analysis.jobProgress(props.projectId, job.job_id, { silentError: true })
    // With cross-validation the folds report in turn: use the furthest generation reached.
    const reached = Math.max(0, ...(data?.points || []).map(p => Number(p.generation) || 0))
    progressPct.value = data?.max_gen && reached ? Math.min(99, Math.round((reached / data.max_gen) * 100)) : 0
  } catch (e) { ignoreError(e) }
  await refreshJobs()
  if (!running.value) stopPolling()
}

function startPolling() {
  stopPolling()
  progressPct.value = 0
  pollTimer = setInterval(pollProgress, 3000)
}
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
}

async function cancel() {
  const job = running.value
  if (!job) return
  cancelling.value = true
  try {
    await api.analysis.cancelJob(props.projectId, job.job_id)
    await refreshJobs()
  } catch (e) { ignoreError(e) } finally {
    cancelling.value = false
  }
}

// ── Step 3: result ────────────────────────────────────────────────────────
const detail = ref(null)
const resultLoading = ref(false)
let detailSeq = 0

watch(selectedJobId, async (id) => {
  detail.value = null
  if (!id) return
  const mine = ++detailSeq
  resultLoading.value = true
  try {
    const { data } = await api.analysis.jobDetail(props.projectId, id, { silentError: true })
    if (mine === detailSeq) detail.value = data
  } catch (e) { ignoreError(e) } finally {
    if (mine === detailSeq) resultLoading.value = false
  }
})

const best = computed(() => detail.value?.best_individual || null)
const mainAuc = computed(() => detail.value?.best_auc_test ?? detail.value?.best_auc)
const grade = computed(() => aucGrade(mainAuc.value))
const overfit = computed(() => {
  const d = detail.value
  return d?.best_auc != null && d?.best_auc_test != null && d.best_auc - d.best_auc_test > 0.1
})
const signature = computed(() => splitSignature(best.value?.features, detail.value?.feature_names))

// Positive coefficients point to the second class of a binary problem.
const classKeys = computed(() => {
  const keys = Object.keys(project.value?.class_names || {})
  return keys.length === 2 ? keys.sort() : ['0', '1']
})
const classA = computed(() => classLabel(classKeys.value[1], project.value?.class_names))
const classB = computed(() => classLabel(classKeys.value[0], project.value?.class_names))

function fmt(v) {
  return v == null ? '—' : Number(v).toFixed(3)
}
function pct(v) {
  return v == null ? '—' : `${Math.round(Number(v) * 100)} %`
}
function jobLabel(j) {
  const when = j.created_at ? new Date(j.created_at).toLocaleString(locale.value) : ''
  const auc = j.best_auc != null ? ` — AUC ${Number(j.best_auc).toFixed(3)}` : ''
  return `${j.name || j.job_id.slice(0, 8)} · ${when}${auc}`
}

function openExpert() {
  uiMode.setMode('expert')
  const jobId = selectedJobId.value
  const target = jobId
    ? { name: 'ProjectJobResults', params: { id: props.projectId, jobId } }
    : { name: 'ProjectResults', params: { id: props.projectId } }
  router.push(target).catch(() => {})
}

onMounted(async () => {
  await refreshJobs()
  if (running.value) startPolling()
})
onBeforeUnmount(stopPolling)
watch(() => props.projectId, async () => {
  stopPolling()
  jobs.value = []
  selectedJobId.value = null
  await refreshJobs()
  if (running.value) startPolling()
})
</script>

<style scoped>
.simple-project {
  max-width: 860px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
.step {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--card-radius);
  padding: 1.25rem 1.5rem;
  box-shadow: var(--card-shadow);
}
.step.disabled { opacity: 0.6; }
.step h3 {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 1.15rem;
  color: var(--text-primary);
  margin-bottom: 0.4rem;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.8rem;
  height: 1.8rem;
  border-radius: 50%;
  background: var(--accent);
  color: var(--accent-text);
  font-size: 0.95rem;
}
.step.done .step-num { background: var(--success); color: #fff; }
.step-help { color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 0.9rem; line-height: 1.45; }

.file-rows { display: flex; flex-direction: column; gap: 0.75rem; }
.file-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  padding: 0.75rem 0.9rem;
  border: 1px solid var(--border-lighter);
  border-radius: 8px;
}
.file-label { display: flex; flex-direction: column; gap: 0.15rem; }
.file-hint { font-size: 0.8rem; color: var(--text-muted); }
.file-state { display: flex; align-items: center; gap: 0.75rem; }
.file-ok { color: var(--success-dark); font-size: 0.88rem; word-break: break-all; }
.file-missing { color: var(--text-faint); font-size: 0.88rem; }
.file-row .msg-error { flex-basis: 100%; }

.format-help { margin-top: 0.9rem; font-size: 0.85rem; color: var(--text-secondary); }
.format-help summary { cursor: pointer; }
.format-help p { margin: 0.5rem 0; }
.format-help pre {
  background: var(--bg-badge);
  padding: 0.6rem 0.8rem;
  border-radius: 6px;
  font-size: 0.78rem;
  overflow-x: auto;
}

.presets {
  border: none;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem;
}
.preset {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.8rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  background: var(--bg-input);
}
.preset:focus-within { outline: 2px solid var(--brand); outline-offset: 2px; }
.preset.active { border-color: var(--info); box-shadow: 0 0 0 1px var(--info); background: var(--info-bg); }
.preset-name { font-weight: 600; color: var(--text-primary); }
.preset-time { font-size: 0.78rem; color: var(--info); }
.preset-desc { font-size: 0.8rem; color: var(--text-secondary); line-height: 1.35; }
.presets:disabled .preset { cursor: not-allowed; }

.run-bar { display: flex; align-items: center; gap: 1rem; margin-top: 1rem; flex-wrap: wrap; }
.run-hint { font-size: 0.85rem; color: var(--text-muted); }

.btn {
  display: inline-flex;
  align-items: center;
  padding: 0.45rem 1rem;
  border-radius: 6px;
  font-size: 0.9rem;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--bg-input);
  color: var(--text-body);
}
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn-primary { background: var(--accent); color: var(--accent-text); border-color: var(--accent); font-weight: 600; }
.btn-primary:not(:disabled):hover { background: var(--accent-hover); }
.btn-run { padding: 0.65rem 1.6rem; font-size: 1rem; }
.btn-secondary:hover { border-color: var(--accent); }
.btn-secondary.busy { cursor: progress; }
.btn-link { border: none; background: none; color: var(--info); padding: 0.3rem 0; text-decoration: underline; }

.running p { margin-bottom: 0.6rem; }
.progress { height: 10px; background: var(--bg-badge); border-radius: 5px; overflow: hidden; }
.progress-bar { height: 100%; background: var(--info); transition: width 0.4s; }
.progress-bar.indeterminate { width: 30%; animation: slide 1.4s ease-in-out infinite; }
@keyframes slide { 0% { margin-left: -30%; } 100% { margin-left: 100%; } }
@media (prefers-reduced-motion: reduce) { .progress-bar.indeterminate { animation: none; width: 100%; opacity: 0.4; } }
.progress-text { font-size: 0.85rem; color: var(--text-muted); margin-top: 0.4rem; }

.verdict {
  display: flex;
  gap: 1.25rem;
  align-items: center;
  padding: 1rem 1.1rem;
  border-radius: 10px;
  background: var(--bg-badge);
  border-left: 5px solid var(--text-faint);
}
.verdict.excellent, .verdict.good { border-left-color: var(--success); background: var(--success-bg); }
.verdict.fair { border-left-color: var(--warning); background: var(--warning-bg); }
.verdict.weak, .verdict.chance { border-left-color: var(--danger); background: var(--danger-bg); }
.verdict-score { display: flex; flex-direction: column; align-items: center; min-width: 6rem; }
.score-value { font-size: 2rem; font-weight: 700; color: var(--text-primary); }
.score-label { font-size: 0.75rem; color: var(--text-secondary); text-align: center; }
.verdict-text p { margin-top: 0.25rem; font-size: 0.9rem; line-height: 1.4; }

.metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.75rem;
  margin: 1rem 0 1.25rem;
}
.metrics div { border: 1px solid var(--border-lighter); border-radius: 8px; padding: 0.5rem 0.75rem; }
.metrics dt { font-size: 0.75rem; color: var(--text-muted); }
.metrics dd { font-size: 1.2rem; font-weight: 600; color: var(--text-primary); }

h4 { font-size: 1rem; color: var(--text-primary); margin-bottom: 0.3rem; }
.signature { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.sig-col { border-radius: 8px; padding: 0.7rem 0.9rem; border: 1px solid var(--border-lighter); }
.sig-col h5 { font-size: 0.85rem; margin-bottom: 0.4rem; }
.sig-col.up h5 { color: var(--info); }
.sig-col.down h5 { color: var(--warning-dark); }
.signature.single { grid-template-columns: 1fr; }
.sig-n { font-weight: 400; color: var(--text-muted); }
.sig-col ul { list-style: none; display: flex; flex-wrap: wrap; gap: 0.35rem; }
.sig-col li {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.78rem;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  background: var(--bg-badge);
  border: 1px solid var(--border-lighter);
  word-break: break-all;
}

.result-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1.25rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border-lighter);
}
.history { font-size: 0.85rem; color: var(--text-secondary); display: flex; gap: 0.5rem; align-items: center; }
.history select { padding: 0.3rem 0.5rem; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-input); color: var(--text-body); max-width: 26rem; }

.msg-error { color: var(--danger-dark); font-size: 0.88rem; margin-top: 0.5rem; }
.fail-detail { display: block; font-size: 0.8rem; margin-top: 0.25rem; color: var(--text-secondary); }
.muted { color: var(--text-muted); }
.small { font-size: 0.8rem; }
.warn { color: var(--warning-dark); }

@media (max-width: 700px) {
  .presets, .signature { grid-template-columns: 1fr; }
  .metrics { grid-template-columns: repeat(2, 1fr); }
  .verdict { flex-direction: column; align-items: flex-start; }
}
</style>
