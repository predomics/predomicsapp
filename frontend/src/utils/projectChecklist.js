/**
 * Per-project "next step" checklist state.
 *
 * Two steps can be read from the project itself (data attached, a job launched).
 * The other two are things only this browser knows: that the user opened the
 * Parameters tab, and that they looked at a finished job's results. Those are
 * remembered in localStorage, keyed by project.
 */
const PREFIX = 'predomics_checklist_'
export const DISMISS_ALL_KEY = 'predomics_checklist_hidden'

function read(projectId) {
  try {
    const raw = localStorage.getItem(PREFIX + projectId)
    const v = raw ? JSON.parse(raw) : {}
    return v && typeof v === 'object' ? v : {}
  } catch {
    return {}
  }
}

function write(projectId, state) {
  try { localStorage.setItem(PREFIX + projectId, JSON.stringify(state)) } catch { /* storage unavailable */ }
}

export function checklistFlags(projectId) {
  return read(projectId)
}

/** Record a step only the browser can know about: 'parameters' or 'results'. */
export function markChecklistStep(projectId, step) {
  if (!projectId) return
  const state = read(projectId)
  if (state[step]) return
  state[step] = true
  write(projectId, state)
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('predomics:checklist', { detail: { projectId } }))
}

export function dismissChecklist(projectId) {
  const state = read(projectId)
  state.dismissed = true
  write(projectId, state)
}

/** Forget every dismissal, so the checklist shows again on unfinished projects. */
export function resetChecklists() {
  try {
    localStorage.removeItem(DISMISS_ALL_KEY)
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i)
      if (!key || !key.startsWith(PREFIX)) continue
      const state = read(key.slice(PREFIX.length))
      if (state.dismissed) { delete state.dismissed; localStorage.setItem(key, JSON.stringify(state)) }
    }
  } catch { /* storage unavailable */ }
}

/**
 * The four steps with their state.
 * @param project  project object ({ datasets: [{ files: [{ role }] }] })
 * @param jobs     job list of the project (objects with a status, or ids)
 * @param flags    checklistFlags(projectId)
 */
export function checklistSteps(project, jobs, flags = {}) {
  const roles = new Set((project?.datasets || []).flatMap(d => (d.files || []).map(f => f.role)))
  const hasData = roles.has('xtrain') && roles.has('ytrain')
  const list = Array.isArray(jobs) ? jobs : []
  const hasJob = list.length > 0
  const hasCompleted = list.some(j => j && typeof j === 'object' && j.status === 'completed')
  return [
    { id: 'data', done: hasData, tab: 'data' },
    { id: 'parameters', done: hasData && (!!flags.parameters || hasJob), tab: 'parameters' },
    { id: 'launch', done: hasJob, tab: 'parameters' },
    { id: 'results', done: hasCompleted && !!flags.results, tab: 'results' },
  ]
}
