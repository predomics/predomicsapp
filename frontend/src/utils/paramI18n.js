/**
 * Translated text for parameter definitions, with the English source in
 * parameterDefs.js as the fallback (so a missing key never shows a raw key).
 */
import i18n from '../i18n'

function lookup(key, fallback) {
  const { t, te } = i18n.global
  return te(key) ? t(key) : fallback
}

export function paramLabel(def) {
  return lookup(`params.${def.category}.${def.key}.label`, def.label)
}

export function paramDescription(def) {
  return lookup(`params.${def.category}.${def.key}.desc`, def.description)
}

export function optionLabel(def, opt) {
  return lookup(`params.${def.category}.${def.key}.opt.${opt.value}`, opt.label)
}

export function categoryLabel(cat) {
  return lookup(`paramCategories.${cat.id}`, cat.label)
}

/** Text for a validation error from utils/paramValidation.js. */
export function paramErrorText(err, defs = []) {
  if (!err) return ''
  const params = { ...(err.params || {}) }
  if (params.other) {
    const other = defs.find(d => d.key === params.other)
    params.other = other ? paramLabel(other) : params.other
  }
  const key = `paramErrors.${err.code}`
  return i18n.global.te(key) ? i18n.global.t(key, params) : err.code
}
