<template>
  <section
    class="param-section"
    :style="{
      background: `var(${category.colorVar})`,
      borderLeftColor: `var(${category.colorVar}-bar)`,
    }"
  >
    <div class="section-header">
      <span class="section-title">{{ category.label }}</span>
      <span class="param-count">{{ params.length }} params</span>
    </div>

    <!-- Basic params — always visible -->
    <div class="form-grid">
      <template v-for="p in basicParams" :key="p.key">
        <div class="form-field" :class="{ 'full-width': p.inputType === 'text' }">
          <label class="field-label">
            <span class="label-text">{{ p.label }}</span>
            <span v-if="p.unit" class="field-unit">({{ p.unit }})</span>
            <span class="info-dot" :data-tooltip="p.description">?</span>
          </label>
          <template v-if="p.inputType === 'checkbox'">
            <label class="inline-check">
              <input type="checkbox" v-model="form[p.key]" />
              <span class="check-label">{{ form[p.key] ? 'Enabled' : 'Disabled' }}</span>
            </label>
          </template>
          <template v-else-if="p.inputType === 'select'">
            <select v-model="form[p.key]">
              <option v-for="opt in p.options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </template>
          <template v-else-if="p.inputType === 'number'">
            <input
              type="number"
              v-model.number="form[p.key]"
              :min="p.min"
              :max="p.max"
              :step="p.step"
            />
          </template>
          <template v-else>
            <input type="text" v-model="form[p.key]" />
          </template>
        </div>
      </template>
    </div>

    <!-- Advanced params — collapsible -->
    <details v-if="advancedParams.length" class="advanced-toggle">
      <summary>Advanced ({{ advancedParams.length }})</summary>
      <div class="form-grid">
        <template v-for="p in advancedParams" :key="p.key">
          <div class="form-field" :class="{ 'full-width': p.inputType === 'text' }">
            <label class="field-label">
              <span class="label-text">{{ p.label }}</span>
              <span v-if="p.unit" class="field-unit">({{ p.unit }})</span>
              <span class="info-dot" :data-tooltip="p.description">?</span>
            </label>
            <template v-if="p.inputType === 'checkbox'">
              <label class="inline-check">
                <input type="checkbox" v-model="form[p.key]" />
                <span class="check-label">{{ form[p.key] ? 'Enabled' : 'Disabled' }}</span>
              </label>
            </template>
            <template v-else-if="p.inputType === 'select'">
              <select v-model="form[p.key]">
                <option v-for="opt in p.options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
            </template>
            <template v-else-if="p.inputType === 'number'">
              <input
                type="number"
                v-model.number="form[p.key]"
                :min="p.min"
                :max="p.max"
                :step="p.step"
              />
            </template>
            <template v-else>
              <input type="text" v-model="form[p.key]" />
            </template>
          </div>
        </template>
      </div>
    </details>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  category: { type: Object, required: true },
  params: { type: Array, required: true },
  form: { type: Object, required: true },
})

const basicParams = computed(() => props.params.filter(p => p.level === 'basic'))
const advancedParams = computed(() => props.params.filter(p => p.level === 'advanced'))
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
  font-size: 0.7rem;
  color: var(--text-faint);
}

/* 2-column form grid */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.6rem 1rem;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.form-field.full-width {
  grid-column: 1 / -1;
}

.field-label {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.label-text {
  white-space: nowrap;
}

.field-unit {
  font-size: 0.7rem;
  color: var(--text-faint);
}

/* Info dot tooltip */
.info-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--border);
  color: var(--text-muted);
  font-size: 0.6rem;
  font-weight: 700;
  cursor: help;
  flex-shrink: 0;
  position: relative;
}

.info-dot::after {
  content: attr(data-tooltip);
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg-navbar);
  color: #e0e0e0;
  padding: 0.4rem 0.6rem;
  border-radius: 6px;
  font-size: 0.72rem;
  font-weight: 400;
  line-height: 1.35;
  white-space: normal;
  width: max-content;
  max-width: 260px;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0,0,0,0.25);
}

.info-dot:hover::after {
  opacity: 1;
}

/* Inputs */
input, select {
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
}

input[type="checkbox"] {
  width: auto;
  margin: 0;
}

.inline-check {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 0.4rem;
  cursor: pointer;
  padding-top: 0.15rem;
}

.check-label {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

/* Advanced toggle */
.advanced-toggle {
  margin-top: 0.6rem;
  border-top: 1px solid var(--border-lighter);
  padding-top: 0.5rem;
}

.advanced-toggle summary {
  cursor: pointer;
  color: var(--text-muted);
  font-size: 0.78rem;
  margin-bottom: 0.5rem;
  user-select: none;
}

.advanced-toggle summary:hover {
  color: var(--text-secondary);
}

@media (max-width: 600px) {
  .form-grid { grid-template-columns: 1fr; }
}
</style>
