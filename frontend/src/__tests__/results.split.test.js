/**
 * The Results view after its split: one lazily-loaded component per sub-tab,
 * all fed by the shared state of composables/useResultsTab.js.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import fs from 'node:fs'
import path from 'node:path'
import axios from 'axios'
import i18n from '../i18n'

const plotly = vi.hoisted(() => ({
  newPlot: vi.fn(() => Promise.resolve()), react: vi.fn(() => Promise.resolve()), purge: vi.fn(), relayout: vi.fn(), register: vi.fn(), Plots: { resize: vi.fn() },
}))
vi.mock('../utils/plotlyBundle', () => ({ default: plotly, TRACE_TYPES_2D: [] }))
vi.mock('../utils/plotly3d', () => ({ default: { name: 'scatter3d' } }))

const SRC = path.resolve(__dirname, '..')
const FEATURES = ['msp_0001', 'msp_0002', 'msp_0003', 'msp_0004']
const individual = (rank, features) => ({
  rank, features, named_features: Object.fromEntries(Object.entries(features).map(([i, c]) => [FEATURES[i], c])),
  metrics: { auc: 0.9 - rank * 0.01, fit: 0.88, accuracy: 0.85, sensitivity: 0.8, specificity: 0.9, threshold: 0.5, k: Object.keys(features).length, language: 'ternary', data_type: 'prevalence', epoch: 3 },
})
const POPULATION = [individual(0, { 0: 1, 1: -1 }), individual(1, { 0: 1, 2: 1 }), individual(2, { 1: -1, 3: 1 })]
const TRACKING = [0, 1, 2].map(g => ({ generation: g, best_auc: 0.8 + g * 0.05, best_auc_test: 0.75 + g * 0.05, best_k: 2 + g, best_fit: 0.8 }))
const PROJECT = { project_id: 'p1', name: 'Demo', class_names: { 0: 'Healthy', 1: 'Cirrhosis' }, datasets: [], jobs: ['j1'] }
const JOB = { job_id: 'j1', name: 'GA run', status: 'completed', best_auc: 0.9, best_k: 2, language: 'ternary', created_at: '2026-01-01T10:00:00Z' }

let saved
function fakeApi(config) {
  const url = config.url.split('?')[0]
  const routes = {
    '/api/analysis/p1/jobs': [JOB],
    '/api/analysis/p1/jobs/j1/detail': { job_id: 'j1', status: 'completed', feature_names: FEATURES, sample_names: ['s1', 's2'], best_individual: { ...POPULATION[0].metrics, features: POPULATION[0].features }, config: { general: { algo: 'ga', fit: 'auc' } } },
    '/api/analysis/p1/jobs/j1/results': { feature_names: FEATURES, sample_names: ['s1', 's2'], population: POPULATION, generation_tracking: TRACKING, best_individual: { ...POPULATION[0].metrics, features: POPULATION[0].features } },
    '/api/analysis/p1/jobs/j1/logs': { log: 'first line\nsecond line\n', status: 'completed' },
    '/api/data-explore/msp-annotations': { annotations: {} },
  }
  const hit = Object.keys(routes).filter(k => url === k || url.startsWith(k + '/')).sort((a, b) => b.length - a.length)[0]
  return Promise.resolve({ status: 200, statusText: 'OK', headers: {}, config, data: JSON.parse(JSON.stringify(hit ? routes[hit] : {})) })
}

async function settle() {
  // async components resolve through dynamic import(): give them a few turns
  for (let i = 0; i < 6; i++) { await flushPromises(); await new Promise(r => setTimeout(r, 0)) }
}

/** Wait until `selector` is rendered (sub-tab components are loaded on demand). */
function appears(wrapper, selector, what = selector) {
  return vi.waitFor(() => {
    if (!wrapper.find(selector).exists()) throw new Error(`${what} did not render`)
  }, { timeout: 5000, interval: 20 })
}

async function mountResults(urlPath = '/project/p1/results/j1') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const { useProjectStore } = await import('../stores/project')
  useProjectStore().current = JSON.parse(JSON.stringify(PROJECT))
  const stub = { template: '<div />' }
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/project/:id/results', name: 'ProjectResults', component: stub },
    { path: '/project/:id/results/:jobId', name: 'ProjectJobResults', component: stub },
    { path: '/:rest(.*)', component: stub },
  ] })
  router.push(urlPath)
  await router.isReady()
  const { default: ResultsTab } = await import('../views/ResultsTab.vue')
  const wrapper = mount(ResultsTab, { global: { plugins: [pinia, i18n, router] }, attachTo: document.body })
  await settle()
  return { wrapper, router }
}

describe('results view, split by sub-tab', () => {
  let errors
  beforeEach(() => {
    localStorage.clear()
    i18n.global.locale.value = 'en'
    saved = axios.defaults.adapter
    axios.defaults.adapter = fakeApi
    plotly.newPlot.mockClear()
    errors = []
    vi.spyOn(console, 'error').mockImplementation((...a) => errors.push(a.map(String).join(' ')))
    vi.spyOn(console, 'warn').mockImplementation((...a) => errors.push(a.map(String).join(' ')))
  })
  afterEach(() => {
    axios.defaults.adapter = saved
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('every sub-tab opens, renders its own markup and keeps the URL in step', async () => {
    const { wrapper, router } = await mountResults()
    const tabs = wrapper.findAll('.sub-tabs [role="tab"], [role="tablist"] [role="tab"]')
    const labels = tabs.map(t => t.text().replace(/\d+$/, '').trim())
    expect(labels).toEqual(expect.arrayContaining(['Insights', 'Summary', 'Best Model', 'Population', 'Comparative', 'Co-presence', 'Enrichment', 'Ecosystem', 'Stability', 'Basket', 'Console']))

    // one distinctive element per extracted sub-tab
    const marker = {
      Summary: '#convergence-summary',
      'Best Model': '.metrics-table',
      Population: 'table',
      Comparative: '.sub-content',
      'Co-presence': '.sub-content',
      Exploration: '.exploration-controls',
      Basket: '.sub-content',
      Console: '.console-log-info, pre',
    }
    for (const tab of tabs) {
      const label = tab.text().replace(/\d+$/, '').trim()
      await tab.trigger('click')
      await settle()
      expect(tab.attributes('aria-selected'), label).toBe('true')
      expect(tab.classes(), label).toContain('active')
      // the tab's chunk is fetched on first use: wait for its markup
      await appears(wrapper, '.sub-content', `${label} content`)
      if (marker[label]) await appears(wrapper, marker[label], `${label} marker ${marker[label]}`)
    }
    expect(router.currentRoute.value.query.tab).toBe('console')
    expect(errors.filter(e => /is not defined|was accessed during render|Unhandled|Failed to resolve/i.test(e))).toEqual([])
    wrapper.unmount()
  })

  it('charts are drawn when a sub-tab chunk arrives, with class names and a text summary', async () => {
    const { wrapper } = await mountResults('/project/p1/results/j1?tab=summary')
    await appears(wrapper, '#convergence-summary')
    await vi.waitFor(() => expect(plotly.newPlot).toHaveBeenCalled(), { timeout: 5000 })
    await settle()
    const summary = wrapper.find('#convergence-summary').text()
    expect(summary).toContain('Over 3 generations')
    expect(summary).toContain('0.800')
    expect(summary).toContain('0.900')
    // the convergence traces are named through i18n and carry two different dashes/colours
    const traces = plotly.newPlot.mock.calls.map(c => c[1]).flat()
    expect(traces.some(t => t.name === 'Train AUC')).toBe(true)
    expect(traces.some(t => t.name === 'Test AUC' && t.line?.dash === 'dash')).toBe(true)
    wrapper.unmount()
  })

  it('opening a tab from the URL works for a lazily-loaded tab', async () => {
    const { wrapper } = await mountResults('/project/p1/results/j1?tab=bestmodel')
    await appears(wrapper, '.metrics-table')
    expect(wrapper.find('#coefficients-summary').text()).toContain('2 features: 1 with a positive coefficient, 1 with a negative one.')
    wrapper.unmount()
  })

  it('sub-tab markup keeps the view\'s scoped styles', async () => {
    const { wrapper } = await mountResults('/project/p1/results/j1?tab=summary')
    await appears(wrapper, '.sub-content .section')
    const root = wrapper.element
    const scope = [...root.attributes].map(a => a.name).find(n => n.startsWith('data-v-'))
    expect(scope).toBeTruthy()
    const inner = wrapper.find('.sub-content .section')
    expect(inner.exists()).toBe(true)
    expect(inner.element.hasAttribute(scope)).toBe(true)
    wrapper.unmount()
  })

  it('each sub-tab is its own module, loaded on demand, and the view stays small', () => {
    const view = fs.readFileSync(path.join(SRC, 'views/ResultsTab.vue'), 'utf8')
    const script = /<script setup>([\s\S]*?)<\/script>/.exec(view)[1]
    const lazy = [...script.matchAll(/const (\w+) = defineAsyncComponent\(\(\) => import\('([^']+)'\)\)/g)].map(m => m[1])
    expect(lazy.sort()).toEqual(['BasketTab', 'BestModelTab', 'CoPresenceTab', 'ComparativeTab', 'ConsoleLogTab', 'EcosystemTab',
      'EnrichmentTab', 'ExplorationTab', 'InsightsTab', 'JuryTab', 'PheromoneTab', 'PopulationTab', 'StabilityTab', 'SummaryTab'])
    expect(script).not.toMatch(/import \w+Tab from/)
    expect(script.split('\n').length).toBeLessThan(120)
    for (const name of lazy.filter(n => !['EcosystemTab', 'EnrichmentTab', 'InsightsTab', 'StabilityTab'].includes(n))) {
      const sfc = fs.readFileSync(path.join(SRC, 'components/results/tabs', `${name}.vue`), 'utf8')
      expect(sfc, name).toContain('useResults()')
      expect(sfc, name).not.toMatch(/<style/)
    }
  })
})
