/**
 * Plotly is large: load it once, on demand, and release charts on unmount.
 *
 *   let Plotly = null
 *   async function ensurePlotly() { Plotly = await loadPlotlyLib(); return Plotly }
 *   usePlotlyCleanup()          // purges every chart of this component on unmount
 *
 * loadPlotlyLib() gives the 2-D build (see plotlyBundle.js for the trace types).
 * A chart that needs `scatter3d` must await loadPlotly3d() instead.
 */
import { getCurrentInstance, onBeforeUnmount } from 'vue'
import { withFittedLabels } from './chartLabels'

let _plotly = null      // the real module (used for purge and trace registration)
let _wrapped = null     // what components get: newPlot/react shorten long labels first
let _pending = null
let _pending3d = null

export async function loadPlotlyLib() {
  if (_wrapped) return _wrapped
  if (!_pending) {
    _pending = import('./plotlyBundle').then((mod) => {
      _plotly = mod.default
      // Long feature names would stretch every chart: see chartLabels.js.
      _wrapped = withFittedLabels(_plotly)
      return _wrapped
    })
  }
  return _pending
}

/** Plotly with the 3-D scatter trace registered (extra WebGL chunk, fetched once). */
export async function loadPlotly3d() {
  const plotly = await loadPlotlyLib()
  if (!_pending3d) {
    _pending3d = import('./plotly3d').then((mod) => {
      _plotly.register(mod.default)
      return plotly
    })
  }
  return _pending3d
}

/** Purge every Plotly chart inside an element (frees WebGL contexts, listeners, data). */
export function purgePlots(rootEl) {
  if (!_plotly || !rootEl || typeof rootEl.querySelectorAll !== 'function') return
  for (const el of rootEl.querySelectorAll('.js-plotly-plot')) {
    try { _plotly.purge(el) } catch { /* already gone */ }
  }
}

/** Call in setup(): purges this component's charts just before it unmounts. */
export function usePlotlyCleanup() {
  const inst = getCurrentInstance()
  onBeforeUnmount(() => purgePlots(inst?.proxy?.$el))
}
