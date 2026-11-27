/**
 * Validation of the analysis parameter form, driven by parameterDefs.
 *
 * validateParam(def, value)   → null, or { code, params } for one field
 * validateForm(form, defs)    → { 'ga.k_max': { code, params }, … } incl. cross-field rules
 *
 * Codes map to the `paramErrors.*` locale keys.
 */

function isBlank(v) {
  return v === '' || v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v))
}

export function validateParam(def, value) {
  if (!def) return null
  switch (def.inputType) {
    case 'number': {
      if (isBlank(value)) {
        // A null default means "no limit / automatic": leaving it empty is allowed.
        return def.defaultValue === null ? null : { code: 'required', params: {} }
      }
      if (typeof value !== 'number' || !Number.isFinite(value)) return { code: 'number', params: {} }
      if (def.min !== undefined && value < def.min) return { code: 'min', params: { min: def.min } }
      if (def.max !== undefined && value > def.max) return { code: 'max', params: { max: def.max } }
      if (Number.isInteger(def.step) && Number.isInteger(def.defaultValue ?? 0) && !Number.isInteger(value)) {
        return { code: 'integer', params: {} }
      }
      return null
    }
    case 'checkboxGroup': {
      const picked = String(value || '').split(',').map(v => v.trim()).filter(Boolean)
      if (picked.length === 0) return { code: 'pickOne', params: {} }
      const allowed = new Set((def.options || []).map(o => o.value))
      if (picked.some(v => !allowed.has(v))) return { code: 'option', params: {} }
      return null
    }
    case 'select': {
      const allowed = (def.options || []).map(o => o.value)
      if (!allowed.includes(value)) return { code: 'option', params: {} }
      return null
    }
    default:
      return null
  }
}

/** [category, lowerKey, upperKey, strict] — lower must be <= (or <) upper. */
export const ORDER_RULES = [
  ['ga', 'k_min', 'k_max', false],
  ['ga', 'min_epochs', 'max_epochs', false],
  ['ils', 'k_min', 'k_max', false],
  ['sa', 'k_min', 'k_max', false],
  ['aco', 'k_min', 'k_max', false],
  ['aco', 'min_iterations', 'max_iterations', false],
  ['beam', 'k_start', 'k_stop', false],
  ['lasso', 'alpha_min', 'alpha_max', true],
  ['mcmc', 'n_burn', 'n_iter', true],
]

/**
 * @param form  { category: { key: value } }
 * @param defs  the parameter definitions to check (pass only the visible ones)
 */
export function validateForm(form, defs) {
  const errors = {}
  const active = new Set()
  for (const def of defs) {
    const id = `${def.category}.${def.key}`
    active.add(id)
    const err = validateParam(def, form?.[def.category]?.[def.key])
    if (err) errors[id] = err
  }
  // Options available only for some value of another field of the same section
  // (e.g. OR languages with the Beam algorithm): report them while they are picked.
  for (const def of defs) {
    if (def.inputType !== 'checkboxGroup') continue
    const id = `${def.category}.${def.key}`
    if (errors[id]) continue
    const picked = String(form?.[def.category]?.[def.key] || '').split(',').map(v => v.trim()).filter(Boolean)
    for (const opt of def.options || []) {
      const rule = opt.onlyWith
      if (!rule || !picked.includes(opt.value)) continue
      if (!rule.values.includes(form?.[def.category]?.[rule.key])) {
        errors[id] = { code: 'onlyWith', params: { option: opt.label, other: rule.key, values: rule.values.join(', ') } }
        break
      }
    }
  }
  for (const [cat, lo, hi, strict] of ORDER_RULES) {
    const loId = `${cat}.${lo}`
    const hiId = `${cat}.${hi}`
    if (!active.has(loId) || !active.has(hiId) || errors[loId] || errors[hiId]) continue
    const a = form?.[cat]?.[lo]
    const b = form?.[cat]?.[hi]
    if (typeof a !== 'number' || typeof b !== 'number') continue
    if (strict ? a >= b : a > b) {
      errors[hiId] = { code: strict ? 'greaterThan' : 'atLeast', params: { other: lo, value: a } }
    }
  }
  return errors
}
