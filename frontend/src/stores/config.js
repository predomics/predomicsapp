import { defineStore } from 'pinia'
import { reactive, computed, ref, watch } from 'vue'
import { PARAM_DEFS, CATEGORIES } from '../data/parameterDefs'
import { PRESETS } from '../data/presets'

const DRAFT_PREFIX = 'predomics_params_'
const DRAFT_VERSION = 1

/**
 * Build default form values from PARAM_DEFS — single source of truth.
 * Structure: { general: {...}, ga: {...}, beam: {...}, ... }
 */
function buildDefaults() {
  const form = {}
  for (const cat of CATEGORIES) form[cat.id] = {}
  for (const p of PARAM_DEFS) form[p.category][p.key] = p.defaultValue
  return form
}

/** Data section: loading options + feature pre-filtering, edited in the Data tab. */
function dataDefaults() {
  return {
    features_in_rows: true,
    inverse_classes: false,
    holdout_ratio: 0.20,
    feature_selection_method: 'wilcoxon',
    feature_minimal_prevalence_pct: 10,
    feature_maximal_adj_pvalue: 0.05,
    feature_minimal_feature_value: 0,
    classes: null,
  }
}

function clone(o) {
  return JSON.parse(JSON.stringify(o))
}

export const useConfigStore = defineStore('config', () => {
  const defaults = buildDefaults()

  // Data section is managed by DataTab — it is not part of parameterDefs.
  const form = reactive({
    ...clone(defaults),
    data: dataDefaults(),
  })

  /** Project whose draft is loaded (null = not bound, nothing is persisted). */
  const projectId = ref(null)
  let applying = false

  /** Convenience getter for data-explore filtering params */
  const filterParams = computed(() => ({
    method: form.data.feature_selection_method,
    prevalence_pct: form.data.feature_minimal_prevalence_pct,
    max_pvalue: form.data.feature_maximal_adj_pvalue,
    min_feature_value: form.data.feature_minimal_feature_value,
  }))

  /** Copy known keys of `source` into the form (unknown sections/keys are ignored). */
  function applyValues(source) {
    if (!source || typeof source !== 'object') return
    for (const [section, params] of Object.entries(source)) {
      if (!params || typeof params !== 'object') continue
      // Jobs launched before the duplicate was removed stored the filtering
      // settings under "feature_selection": fold them into the data section.
      const target = section === 'feature_selection' ? form.data : form[section]
      if (!target) continue
      for (const [key, value] of Object.entries(params)) {
        if (key in target) target[key] = value
      }
    }
  }

  /** Reset all parameter categories to defaults (preserves data section) */
  function resetToDefaults() {
    const fresh = buildDefaults()
    for (const cat of CATEGORIES) {
      Object.assign(form[cat.id], fresh[cat.id])
    }
  }

  /** Reset a single category to its defaults */
  function resetCategory(catId) {
    const fresh = buildDefaults()
    if (fresh[catId]) Object.assign(form[catId], fresh[catId])
  }

  /** Snapshot of the parameter categories (for undo). */
  function snapshot() {
    const snap = {}
    for (const cat of CATEGORIES) snap[cat.id] = clone(form[cat.id])
    return snap
  }

  /** Load configuration from an existing job's stored config.
   *  Used for the "Duplicate & modify" workflow — pre-fills the Parameters form. */
  function loadFromJobConfig(config) {
    applyValues(config)
  }

  /** Apply a built-in preset by id ('quick' | 'standard' | 'thorough'). */
  function applyPreset(id) {
    const preset = PRESETS.find(p => p.id === id)
    if (!preset) return false
    applyValues(preset.values)
    return true
  }

  /** The body sent to the engine: parameter categories + data section only. */
  function payload() {
    const out = { data: clone(form.data) }
    for (const cat of CATEGORIES) out[cat.id] = clone(form[cat.id])
    return out
  }

  // ---- Draft per project ---------------------------------------------------

  function draftKey(id) {
    return `${DRAFT_PREFIX}${id}`
  }

  function saveDraft() {
    if (!projectId.value || applying) return
    try {
      localStorage.setItem(draftKey(projectId.value), JSON.stringify({ v: DRAFT_VERSION, form: payload() }))
    } catch { /* storage full or unavailable: the form still works */ }
  }

  /**
   * Bind the form to a project: start from defaults, then restore that
   * project's saved draft. A refresh or a visit to another project no longer
   * loses (or leaks) settings.
   */
  function bindProject(id) {
    if (!id || projectId.value === id) return
    applying = true
    projectId.value = id
    resetToDefaults()
    Object.assign(form.data, dataDefaults())
    try {
      const raw = localStorage.getItem(draftKey(id))
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed && parsed.v === DRAFT_VERSION) applyValues(parsed.form)
      }
    } catch { /* corrupted draft: keep defaults */ }
    applying = false
  }

  function clearDraft(id = projectId.value) {
    if (!id) return
    try { localStorage.removeItem(draftKey(id)) } catch { /* ignore */ }
  }

  let saveTimer = null
  watch(form, () => {
    if (!projectId.value || applying) return
    clearTimeout(saveTimer)
    saveTimer = setTimeout(saveDraft, 300)
  }, { deep: true })

  return {
    form, filterParams, projectId,
    resetToDefaults, resetCategory, loadFromJobConfig,
    applyValues, applyPreset, snapshot, payload,
    bindProject, saveDraft, clearDraft,
  }
})
