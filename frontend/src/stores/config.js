import { defineStore } from 'pinia'
import { reactive, computed } from 'vue'
import { PARAM_DEFS, CATEGORIES } from '../data/parameterDefs'

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

export const useConfigStore = defineStore('config', () => {
  const defaults = buildDefaults()

  // Data section is managed separately by DataTab — keep it out of parameterDefs
  const form = reactive({
    ...JSON.parse(JSON.stringify(defaults)),
    data: {
      features_in_rows: true,
      inverse_classes: false,
      holdout_ratio: 0.20,
      feature_selection_method: 'wilcoxon',
      feature_minimal_prevalence_pct: 10,
      feature_maximal_adj_pvalue: 0.05,
      feature_minimal_feature_value: 0,
      classes: null,
    },
  })

  /** Convenience getter for data-explore filtering params */
  const filterParams = computed(() => ({
    method: form.data.feature_selection_method,
    prevalence_pct: form.data.feature_minimal_prevalence_pct,
    max_pvalue: form.data.feature_maximal_adj_pvalue,
    min_feature_value: form.data.feature_minimal_feature_value,
  }))

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

  return { form, filterParams, resetToDefaults, resetCategory }
})
