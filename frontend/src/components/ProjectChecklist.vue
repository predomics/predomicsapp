<template>
  <section v-if="visible" class="checklist" :aria-label="$t('checklist.title')">
    <div class="checklist-head">
      <h3>{{ $t('checklist.title') }}</h3>
      <span class="checklist-count">{{ $t('checklist.progress', { done: doneCount, total: steps.length }) }}</span>
      <button type="button" class="checklist-dismiss" @click="dismiss">{{ $t('checklist.dismiss') }}</button>
    </div>
    <ol class="checklist-steps">
      <li
        v-for="step in steps"
        :key="step.id"
        :class="{ done: step.done, next: step.id === nextStep?.id }"
        :aria-current="step.id === nextStep?.id ? 'step' : undefined"
      >
        <span class="mark" aria-hidden="true">{{ step.done ? '✓' : step.id === nextStep?.id ? '→' : '○' }}</span>
        <span class="sr-only">{{ step.done ? $t('checklist.stateDone') : step.id === nextStep?.id ? $t('checklist.stateNext') : $t('checklist.stateTodo') }}</span>
        <router-link v-if="step.id === nextStep?.id" :to="`/project/${projectId}/${step.tab}`" class="step-link">
          {{ $t(`checklist.steps.${step.id}.label`) }}
        </router-link>
        <span v-else class="step-label">{{ $t(`checklist.steps.${step.id}.label`) }}</span>
        <span v-if="step.id === nextStep?.id" class="step-hint">{{ $t(`checklist.steps.${step.id}.hint`) }}</span>
      </li>
    </ol>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { checklistFlags, checklistSteps, dismissChecklist } from '../utils/projectChecklist'

const props = defineProps({
  projectId: { type: String, required: true },
  project: { type: Object, default: null },
  jobs: { type: Array, default: () => [] },
})

const flags = ref(checklistFlags(props.projectId))
function reload() { flags.value = checklistFlags(props.projectId) }
watch(() => props.projectId, reload)

function onChange(e) { if (!e.detail || e.detail.projectId === props.projectId) reload() }
onMounted(() => window.addEventListener('predomics:checklist', onChange))
onBeforeUnmount(() => window.removeEventListener('predomics:checklist', onChange))

const steps = computed(() => checklistSteps(props.project, props.jobs, flags.value))
const doneCount = computed(() => steps.value.filter(s => s.done).length)
const nextStep = computed(() => steps.value.find(s => !s.done) || null)
// Shown until every step is done, or the user says they do not need it here.
const visible = computed(() => !!props.project && !flags.value.dismissed && doneCount.value < steps.value.length)

function dismiss() {
  dismissChecklist(props.projectId)
  reload()
}
</script>

<style scoped>
.checklist {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-left: 4px solid var(--info);
  border-radius: 8px;
  padding: 0.7rem 1rem;
  margin-bottom: 1rem;
}
.checklist-head { display: flex; align-items: baseline; gap: 0.75rem; flex-wrap: wrap; }
.checklist-head h3 { font-size: 0.95rem; margin: 0; color: var(--text-primary); }
.checklist-count { font-size: 0.8rem; color: var(--text-secondary); }
.checklist-dismiss {
  margin-left: auto; background: none; border: none; padding: 0.15rem 0.3rem;
  color: var(--text-secondary); font-size: 0.8rem; cursor: pointer; text-decoration: underline;
}
.checklist-steps { list-style: none; display: flex; flex-wrap: wrap; gap: 0.4rem 1.5rem; margin: 0.5rem 0 0; padding: 0; }
.checklist-steps li { display: flex; align-items: baseline; gap: 0.35rem; font-size: 0.85rem; color: var(--text-secondary); }
.checklist-steps li.done { color: var(--success-dark); }
.checklist-steps li.next { color: var(--text-body); font-weight: 600; flex-basis: 100%; order: 5; }
.mark { display: inline-block; width: 1.1em; text-align: center; }
.step-link { color: var(--info); }
.step-hint { font-weight: 400; color: var(--text-secondary); }
</style>
