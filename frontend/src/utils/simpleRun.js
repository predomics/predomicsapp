/**
 * Simple mode: what is sent to the engine and how a result is read aloud.
 *
 * Simple mode never reads the expert parameter draft of a project: a run always
 * starts from the documented defaults (genetic algorithm, AUC) with one of the
 * three built-in presets on top. Switching modes therefore cannot carry a
 * forgotten expert setting into a "simple" run.
 */
import { buildDefaults, dataDefaults } from '../stores/config'
import { PRESETS } from '../data/presets'

export const SIMPLE_PRESETS = PRESETS.map(p => p.id)
export const DEFAULT_SIMPLE_PRESET = 'standard'

/** Full engine payload for a simple-mode run with the given preset. */
export function buildSimplePayload(presetId = DEFAULT_SIMPLE_PRESET) {
  const payload = { ...buildDefaults(), data: dataDefaults() }
  const preset = PRESETS.find(p => p.id === presetId) || PRESETS.find(p => p.id === DEFAULT_SIMPLE_PRESET)
  for (const [cat, vals] of Object.entries(preset.values)) {
    if (!payload[cat]) continue
    Object.assign(payload[cat], vals)
  }
  return payload
}

/**
 * A plain-language grade for an AUC (0.5 = chance, 1 = perfect).
 * Returns one of: 'excellent' | 'good' | 'fair' | 'weak' | 'chance' | null.
 */
export function aucGrade(auc) {
  if (auc == null || Number.isNaN(Number(auc))) return null
  const a = Number(auc)
  if (a >= 0.9) return 'excellent'
  if (a >= 0.8) return 'good'
  if (a >= 0.7) return 'fair'
  if (a >= 0.6) return 'weak'
  return 'chance'
}

/**
 * Split a best model's features into the two directions of the signature.
 * `features` is { featureIndex: sign } from the engine, `names` the feature
 * names of the run. A positive coefficient pushes towards the second class.
 */
export function splitSignature(features, names) {
  const up = []
  const down = []
  for (const [idx, sign] of Object.entries(features || {})) {
    const name = names?.[Number(idx)] ?? `#${idx}`
    if (Number(sign) > 0) up.push(name)
    else if (Number(sign) < 0) down.push(name)
  }
  up.sort((a, b) => a.localeCompare(b))
  down.sort((a, b) => a.localeCompare(b))
  return { up, down }
}

/** The job to show by default: the most recent completed one. */
export function latestCompletedJob(jobs) {
  const done = (jobs || []).filter(j => j && typeof j === 'object' && j.status === 'completed')
  done.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  return done[0] || null
}

/** The job still in progress, if any. */
export function liveJob(jobs) {
  const list = (jobs || []).filter(j => j && typeof j === 'object')
  return list.find(j => j.status === 'running') || list.find(j => j.status === 'pending') || null
}
