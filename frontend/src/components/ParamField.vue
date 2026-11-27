<template>
  <!-- eslint-disable vue/no-mutating-props -- `form` is the shared parameter store section; see the note in the script -->
  <div class="form-field" :class="{ 'full-width': def.inputType === 'text' || def.inputType === 'checkboxGroup', invalid: !!error }">
    <div class="field-label">
      <component :is="isGroup ? 'span' : 'label'" :for="isGroup ? undefined : inputId" :id="labelId" class="label-text">{{ label }}</component>
      <span v-if="def.unit" class="field-unit">({{ def.unit }})</span>
      <span class="info-wrap">
        <button
          type="button"
          class="info-dot"
          :aria-expanded="helpOpen ? 'true' : 'false'"
          :aria-controls="helpId"
          :aria-label="$t('parameters.helpFor', { name: label })"
          @click="helpOpen = !helpOpen"
          @keydown.escape="helpOpen = false"
          @blur="helpOpen = false"
        >?</button>
        <span :id="helpId" class="info-pop" :class="{ open: helpOpen }" role="tooltip">{{ description }}</span>
      </span>
    </div>

    <template v-if="def.inputType === 'checkbox'">
      <label class="inline-check">
        <input :id="inputId" type="checkbox" v-model="form[def.key]" :aria-describedby="describedBy" />
        <span class="check-label">{{ form[def.key] ? $t('parameters.enabled') : $t('parameters.disabled') }}</span>
      </label>
    </template>
    <template v-else-if="def.inputType === 'checkboxGroup'">
      <div class="checkbox-group" role="group" :aria-labelledby="labelId" :aria-describedby="describedBy">
        <label
          v-for="opt in def.options"
          :key="opt.value"
          class="checkbox-group-item"
          :class="{ active: isChecked(opt.value), unavailable: optionUnavailable(opt) }"
          :title="optionUnavailable(opt) && opt.onlyWith.hint ? $t(opt.onlyWith.hint) : undefined"
        >
          <input
            type="checkbox"
            :checked="isChecked(opt.value)"
            :disabled="optionUnavailable(opt) && !isChecked(opt.value)"
            :aria-disabled="optionUnavailable(opt) ? 'true' : undefined"
            @change="toggle(opt.value)"
          />
          <span>{{ optionLabel(def, opt) }}</span>
        </label>
      </div>
    </template>
    <template v-else-if="def.inputType === 'select'">
      <select :aria-labelledby="labelId" :id="inputId" v-model="form[def.key]" :aria-invalid="error ? 'true' : undefined" :aria-describedby="describedBy">
        <option v-for="opt in def.options" :key="opt.value" :value="opt.value">{{ optionLabel(def, opt) }}</option>
      </select>
    </template>
    <template v-else-if="def.inputType === 'number'">
      <input :aria-labelledby="labelId"
        :id="inputId"
        type="number"
        inputmode="decimal"
        :value="form[def.key] ?? ''"
        @input="onNumber"
        :min="def.min"
        :max="def.max"
        :step="def.step"
        :placeholder="def.defaultValue === null ? $t('parameters.automatic') : undefined"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="describedBy"
      />
    </template>
    <template v-else>
      <input :aria-labelledby="labelId" :id="inputId" type="text" v-model="form[def.key]" :aria-describedby="describedBy" />
    </template>

    <p v-if="error" :id="errorId" class="field-error" role="alert">{{ error }}</p>
  </div>
</template>

<script setup>
/* eslint-disable vue/no-mutating-props --
   `form` is a section of the reactive parameter store (stores/config.js), handed
   down so every field edits the one shared object; writing to it is the point. */
/**
 * One parameter of the analysis form: label bound to its control, a help
 * popover reachable by keyboard and touch, and an inline validation message.
 */
import { computed, ref } from 'vue'
import { paramLabel, paramDescription, optionLabel } from '../utils/paramI18n'

const props = defineProps({
  def: { type: Object, required: true },
  form: { type: Object, required: true },
  error: { type: String, default: '' },
})

const helpOpen = ref(false)
const base = computed(() => `param-${props.def.category}-${props.def.key}`)
const inputId = computed(() => base.value)
const labelId = computed(() => `${base.value}-label`)
const helpId = computed(() => `${base.value}-help`)
const errorId = computed(() => `${base.value}-error`)
const isGroup = computed(() => props.def.inputType === 'checkboxGroup')
const describedBy = computed(() => (props.error ? `${errorId.value} ${helpId.value}` : helpId.value))

const label = computed(() => paramLabel(props.def))
const description = computed(() => paramDescription(props.def))

// checkboxGroup — the form value is a comma-separated string like "bin,ter,ratio"
function current() {
  return String(props.form[props.def.key] || '').split(',').map(v => v.trim()).filter(Boolean)
}
function isChecked(value) {
  return current().includes(value)
}
function toggle(value) {
  const cur = current()
  const idx = cur.indexOf(value)
  if (idx >= 0) cur.splice(idx, 1)
  else cur.push(value)
  props.form[props.def.key] = cur.join(',')
}
// An option tied to another field of the same section (`onlyWith`), e.g. the OR
// languages that only Beam Search produces. It stays clickable while checked so
// the user can clear it; validation reports it meanwhile.
function optionUnavailable(opt) {
  const rule = opt.onlyWith
  if (!rule) return false
  return !rule.values.includes(props.form[rule.key])
}

// Number: keep '' → null (so "empty" is explicit and validated) instead of NaN,
// and accept a decimal comma typed under a French locale.
function onNumber(ev) {
  const raw = String(ev.target.value).trim().replace(',', '.')
  if (raw === '') {
    props.form[props.def.key] = null
    return
  }
  const n = Number(raw)
  props.form[props.def.key] = Number.isNaN(n) ? null : n
}
</script>

<style scoped>
.form-field { display: flex; flex-direction: column; gap: 0.2rem; min-width: 0; }
.form-field.full-width { grid-column: 1 / -1; }

.field-label {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
}
.label-text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.field-unit { font-size: 0.75rem; color: var(--text-muted); }

.info-wrap { position: relative; display: inline-flex; }
.info-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: none;
  padding: 0;
  background: var(--border);
  color: var(--text-secondary);
  font-size: 0.75rem;
  font-weight: 700;
  cursor: help;
  flex-shrink: 0;
}
.info-dot:hover, .info-dot[aria-expanded="true"] { background: var(--info); color: #fff; }
.info-pop {
  display: none;
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 30;
  width: max-content;
  max-width: min(340px, 70vw);
  background: var(--text-primary);
  color: var(--bg-card);
  padding: 0.5rem 0.7rem;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 400;
  line-height: 1.4;
  white-space: normal;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}
.info-pop.open, .info-wrap:hover .info-pop { display: block; }

input[type="number"], input[type="text"], select {
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.85rem;
  background: var(--bg-input);
  color: var(--text-body);
  width: 100%;
  min-width: 0;
}
.invalid input[type="number"], .invalid input[type="text"], .invalid select {
  border-color: var(--danger-dark);
  box-shadow: 0 0 0 1px var(--danger-dark);
}
.field-error {
  font-size: 0.75rem;
  color: var(--danger-dark);
  font-weight: 600;
}
.field-error::before { content: '\26A0  '; }

.inline-check { display: flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; cursor: pointer; }
.check-label { color: var(--text-secondary); }

.checkbox-group { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.checkbox-group-item {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.55rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 0.78rem;
  cursor: pointer;
  background: var(--bg-input);
  color: var(--text-body);
}
.checkbox-group-item.active { border-color: var(--info); background: var(--info-bg); color: var(--info); font-weight: 600; }
.checkbox-group-item.unavailable { opacity: 0.55; }
.checkbox-group-item.unavailable input { cursor: not-allowed; }
</style>
