/**
 * Built-in run presets: one click sets how hard the search works, without
 * touching what is being asked (algorithm, fit, languages, data types, seed).
 *
 *  - quick:    a first look in a fraction of the time; scores are indicative.
 *  - standard: the documented defaults.
 *  - thorough: a larger search with cross-validation, feature importance and
 *              the voting ensemble — for results you intend to report.
 *
 * `values` is { category: { key: value } }; only listed keys change.
 */
import { paramDefault } from './parameterDefs'

const d = (cat, key) => paramDefault(cat, key)

export const PRESETS = [
  {
    id: 'quick',
    values: {
      general: { cv: false },
      ga: { population_size: 200, max_epochs: 50, k_max: 50 },
      beam: { k_stop: 20, max_nb_of_models: 200 },
      mcmc: { n_iter: 300, n_burn: 150 },
      sa: { max_iterations: 300 },
      ils: { max_iterations: 30 },
      aco: { n_ants: 30, max_iterations: 50, k_max: 50 },
      importance: { compute_importance: false },
      voting: { vote: false },
    },
  },
  {
    id: 'standard',
    values: {
      general: { cv: d('general', 'cv') },
      ga: { population_size: d('ga', 'population_size'), max_epochs: d('ga', 'max_epochs'), k_max: d('ga', 'k_max') },
      beam: { k_stop: d('beam', 'k_stop'), max_nb_of_models: d('beam', 'max_nb_of_models') },
      mcmc: { n_iter: d('mcmc', 'n_iter'), n_burn: d('mcmc', 'n_burn') },
      sa: { max_iterations: d('sa', 'max_iterations') },
      ils: { max_iterations: d('ils', 'max_iterations') },
      aco: { n_ants: d('aco', 'n_ants'), max_iterations: d('aco', 'max_iterations'), k_max: d('aco', 'k_max') },
      cv: { outer_folds: d('cv', 'outer_folds') },
      importance: { compute_importance: d('importance', 'compute_importance') },
      voting: { vote: d('voting', 'vote') },
    },
  },
  {
    id: 'thorough',
    values: {
      general: { cv: true },
      ga: { population_size: 5000, max_epochs: 200, k_max: 200 },
      beam: { k_stop: 100, max_nb_of_models: 5000 },
      mcmc: { n_iter: 5000, n_burn: 2500 },
      sa: { max_iterations: 5000 },
      ils: { max_iterations: 300 },
      aco: { n_ants: 300, max_iterations: 300, k_max: 200 },
      cv: { outer_folds: 5 },
      importance: { compute_importance: true },
      voting: { vote: true },
    },
  },
]

/** Which preset (if any) the current form matches exactly. */
export function matchingPreset(form) {
  for (const preset of PRESETS) {
    let ok = true
    for (const [cat, vals] of Object.entries(preset.values)) {
      for (const [key, val] of Object.entries(vals)) {
        if (form?.[cat]?.[key] !== val) { ok = false; break }
      }
      if (!ok) break
    }
    if (ok) return preset.id
  }
  return ''
}
