<template>
  <section
    class="param-section"
    :aria-labelledby="titleId"
    :style="{
      background: `var(${category.colorVar}, var(--bg-badge))`,
      borderLeftColor: `var(${category.colorVar}-bar, var(--border))`,
    }"
  >
    <div class="section-header">
      <h3 :id="titleId" class="section-title">{{ categoryLabel(category) }}</h3>
      <span class="param-count">{{ $t('parameters.paramCount', { n: params.length }) }}</span>
    </div>

    <!-- Essentials — always visible -->
    <div class="form-grid">
      <ParamField
        v-for="p in basicParams"
        :key="p.key"
        :def="p"
        :form="form"
        :error="errorFor(p)"
      />
    </div>

    <!-- Everything else — collapsible; opens by itself when it holds an error -->
    <details v-if="advancedParams.length" class="advanced-toggle" :open="advancedOpen" @toggle="onToggle">
      <summary>{{ $t('parameters.advanced', { n: advancedParams.length }) }}</summary>
      <div class="form-grid">
        <ParamField
          v-for="p in advancedParams"
          :key="p.key"
          :def="p"
          :form="form"
          :error="errorFor(p)"
        />
      </div>
    </details>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import ParamField from './ParamField.vue'
import { categoryLabel, paramErrorText } from '../utils/paramI18n'

const props = defineProps({
  category: { type: Object, required: true },
  params: { type: Array, required: true },
  form: { type: Object, required: true },
  /** { 'category.key': { code, params } } from validateForm(); shown when showErrors. */
  errors: { type: Object, default: () => ({}) },
})

const titleId = computed(() => `param-section-${props.category.id}`)
const basicParams = computed(() => props.params.filter(p => p.level === 'basic'))
const advancedParams = computed(() => props.params.filter(p => p.level === 'advanced'))

function errorFor(p) {
  return paramErrorText(props.errors[`${p.category}.${p.key}`], props.params)
}

const userOpen = ref(false)
const hasAdvancedError = computed(() =>
  advancedParams.value.some(p => props.errors[`${p.category}.${p.key}`]),
)
const advancedOpen = computed(() => userOpen.value || hasAdvancedError.value)
function onToggle(ev) {
  userOpen.value = ev.target.open
}
watch(() => props.category.id, () => { userOpen.value = false })
</script>

<style scoped>
.param-section {
  padding: 1rem 1.25rem;
  border-radius: 8px;
  border-left: 3px solid transparent;
  box-shadow: var(--shadow);
}

.section-header {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.section-title {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-primary);
}

.param-count {
  font-size: 0.75rem;
  color: var(--text-muted);
}

/* 2-column form grid */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.6rem 1rem;
}

.advanced-toggle { margin-top: 0.75rem; }
.advanced-toggle summary {
  cursor: pointer;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
  padding: 0.25rem 0;
  user-select: none;
}
.advanced-toggle[open] summary { margin-bottom: 0.6rem; }

@media (max-width: 640px) {
  .form-grid { grid-template-columns: 1fr; }
}
</style>
