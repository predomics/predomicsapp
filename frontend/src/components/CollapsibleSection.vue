<template>
  <section :class="['collapsible', { collapsed: !isOpen }]">
    <h3 class="collapsible-heading">
      <button
        type="button"
        class="collapsible-toggle"
        :aria-expanded="isOpen ? 'true' : 'false'"
        :aria-controls="bodyId"
        :aria-labelledby="titleId"
        @click="toggle"
      >
        <span class="collapsible-chevron" aria-hidden="true"></span>
        <span :id="titleId" class="collapsible-title"><slot name="title" /></span>
      </button>
    </h3>
    <div v-show="isOpen" :id="bodyId" ref="bodyEl" class="collapsible-body">
      <slot />
    </div>
  </section>
</template>

<script setup>
/**
 * A section whose content can be folded away under its heading.
 *
 * Long result pages are mostly a stack of sections; folding the ones you are not
 * reading keeps the page short. The open/closed state is remembered per section
 * (`sid`) across visits. The content stays mounted while folded (charts keep
 * their state); when it is unfolded, the charts inside are resized to the width
 * they now have.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { isSectionOpen, setSectionOpen, registerSection, unregisterSection } from '../composables/useSections'
import { loadPlotlyLib } from '../utils/plotly'

const props = defineProps({
  /** Stable identifier, e.g. "population.table": the remembered state is stored under it. */
  sid: { type: String, required: true },
  /** State before the user has chosen. */
  defaultOpen: { type: Boolean, default: true },
})

const bodyEl = ref(null)
const bodyId = computed(() => `section-${props.sid.replace(/[^a-z0-9_-]/gi, '-')}`)
const titleId = computed(() => `${bodyId.value}-title`)
const isOpen = computed(() => isSectionOpen(props.sid, props.defaultOpen))

async function resizeCharts() {
  await nextTick()
  const plots = bodyEl.value?.querySelectorAll('.js-plotly-plot') || []
  if (!plots.length) return
  const Plotly = await loadPlotlyLib()
  for (const el of plots) {
    try { Plotly.Plots.resize(el) } catch { /* chart already gone */ }
  }
}

function toggle() {
  const next = !isOpen.value
  setSectionOpen(props.sid, next)
  if (next) resizeCharts()
}

onMounted(() => registerSection(props.sid, props.defaultOpen, resizeCharts))
onBeforeUnmount(() => unregisterSection(props.sid))
</script>

<style scoped>
.collapsible-heading {
  margin: 0 0 0.75rem;
  font-size: inherit;
}
.collapsed .collapsible-heading { margin-bottom: 0; }
.collapsible-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0;
  border: none;
  background: none;
  color: var(--text-primary);
  font: inherit;
  font-size: 1rem;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}
.collapsible-toggle:hover .collapsible-title { text-decoration: underline; text-underline-offset: 3px; }
.collapsible-toggle:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 4px; }
.collapsible-chevron {
  flex: none;
  width: 0.55rem;
  height: 0.55rem;
  border-right: 2px solid var(--text-secondary);
  border-bottom: 2px solid var(--text-secondary);
  transform: rotate(45deg);
  margin: 0 0.15rem 0.2rem 0.1rem;
  transition: transform 0.15s;
}
.collapsed .collapsible-chevron { transform: rotate(-45deg); margin-bottom: 0; }
.collapsible-title { flex: 1; min-width: 0; }
@media (prefers-reduced-motion: reduce) {
  .collapsible-chevron { transition: none; }
}
</style>
