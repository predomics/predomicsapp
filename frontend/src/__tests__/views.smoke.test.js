/**
 * Smoke tests: mount the main views against a fake API and check the states a
 * user actually meets — loaded, empty, failed (with Retry) — render without
 * errors. These catch template/runtime mistakes the unit tests cannot.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import axios from 'axios'
import i18n from '../i18n'

vi.mock('../utils/plotlyBundle', () => {
  const api = { newPlot: vi.fn(() => Promise.resolve()), react: vi.fn(), purge: vi.fn(), relayout: vi.fn(), register: vi.fn(), Plots: { resize: vi.fn() } }
  return { default: api, TRACE_TYPES_2D: [] }
})
vi.mock('../utils/plotly3d', () => ({ default: { name: 'scatter3d' } }))

const PROJECT = {
  project_id: 'p1', name: 'Demo project', description: '', class_names: {},
  datasets: [{ id: 'd1', name: 'demo', files: [
    { id: 'f1', filename: 'Xtrain.tsv', role: 'xtrain' },
    { id: 'f2', filename: 'Ytrain.tsv', role: 'ytrain' },
  ] }],
  jobs: ['j1', 'j2'],
}
const JOBS = [
  { job_id: 'j1', name: 'GA run', status: 'completed', best_auc: 0.91, best_k: 5, created_at: '2026-01-01T10:00:00Z' },
  { job_id: 'j2', name: 'Second run', status: 'running', created_at: '2026-01-02T10:00:00Z' },
]

let routes
let failing

function fakeApi(config) {
  const url = config.url.split('?')[0]
  const fail = failing.find(f => url.includes(f))
  if (fail) {
    return Promise.reject(Object.assign(new Error('Request failed with status code 500'), {
      isAxiosError: true, config,
      response: { status: 500, data: { error: { code: 'internal', message: 'The data service is unavailable' } }, headers: {}, config },
    }))
  }
  const hit = Object.keys(routes).find(k => url === k) || Object.keys(routes).filter(k => url.startsWith(k)).sort((a, b) => b.length - a.length)[0]
  const data = hit ? routes[hit] : {}
  return Promise.resolve({ status: 200, statusText: 'OK', headers: {}, config, data: JSON.parse(JSON.stringify(data)) })
}

function makeRouter(path) {
  const stub = { template: '<div />' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'Login', component: stub },
      { path: '/forgot-password', name: 'ForgotPassword', component: stub },
      { path: '/projects', name: 'Projects', component: stub },
      { path: '/project/:id/data', name: 'ProjectData', component: stub },
      { path: '/project/:id/parameters', name: 'ProjectParameters', component: stub },
      { path: '/project/:id/results', name: 'ProjectResults', component: stub },
      { path: '/project/:id/results/:jobId', name: 'ProjectJobResults', component: stub },
      { path: '/:rest(.*)', component: stub },
    ],
  })
  router.push(path)
  return router
}

async function mountView(loader, path, { seedProject = false } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  if (seedProject) {
    const { useProjectStore } = await import('../stores/project')
    useProjectStore().current = JSON.parse(JSON.stringify(PROJECT))
  }
  const router = makeRouter(path)
  await router.isReady()
  const { default: Comp } = await loader()
  const wrapper = mount(Comp, {
    global: { plugins: [pinia, i18n, router], stubs: { Teleport: { template: '<div><slot /></div>' } } },
    attachTo: document.body,
  })
  await flushPromises()
  await flushPromises()
  return { wrapper, router, pinia }
}

describe('views render their real states', () => {
  let errorSpy
  let saved

  beforeEach(() => {
    localStorage.clear()
    i18n.global.locale.value = 'en'
    failing = []
    routes = {
      '/api/projects/': [PROJECT],
      '/api/projects/shared-with-me': [],
      '/api/projects/p1': PROJECT,
      '/api/samples/': [{ id: 'qin', name: 'Qin2014', description: '1,980 features, 180 samples', available: true }],
      '/api/dashboard/': { projects: 1, datasets: 1, completed_jobs: 1, running_jobs: 1, failed_jobs: 0, active_jobs: [JOBS[1]].map(j => ({ ...j, project_id: 'p1' })), recent_completions: [{ ...JOBS[0], project_id: 'p1', completed_at: '2026-01-01T11:00:00Z' }], activity: [] },
      '/api/analysis/p1/jobs': JOBS,
      '/api/analysis/p1/jobs/j1/detail': { job_id: 'j1', status: 'completed', best_auc: 0.91, best_k: 5, feature_names: [], best_individual: {} },
      '/api/analysis/p1/jobs/j1/results': { population: [], generation_tracking: [], feature_names: [] },
      '/api/analysis/p1/jobs/j2/logs': { log: '#1 | best: Binary:Raw [k=3, age=0]\n', status: 'running' },
      '/api/analysis/p1/jobs/j2/progress': { points: [] },
      '/api/analysis/p1/jobs/j2': JOBS[1],
      '/api/datasets/': [],
      '/api/templates/public': [],
      '/api/data-explore/p1/summary': { n_features: 10, n_samples: 20, n_classes: 2, class_labels: ['0', '1'] },
      '/api/data-explore/p1/feature-stats': { n_features: 10, selected_count: 2, features: [
        { index: 0, name: 'msp_0001', selected: true, class: 1, significance: 0.001, prevalence: 80, prevalence_0: 60, prevalence_1: 90 },
        { index: 1, name: 'msp_0002', selected: true, class: 0, significance: 0.01, prevalence: 40, prevalence_0: 50, prevalence_1: 30 },
      ] },
      '/api/data-explore/p1/feature-abundance': { features: [] },
      '/api/data-explore/p1/barcode-data': {},
      '/api/data-explore/msp-annotations': { annotations: {} },
    }
    saved = axios.defaults.adapter
    axios.defaults.adapter = fakeApi
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    globalThis.WebSocket = class { constructor() { setTimeout(() => this.onerror && this.onerror(), 0) } close() {} }
  })

  afterEach(() => {
    axios.defaults.adapter = saved
    errorSpy.mockRestore()
    document.body.innerHTML = ''
  })

  it('login: translated form, labelled fields, server message on failure', async () => {
    i18n.global.locale.value = 'fr'
    const { wrapper } = await mountView(() => import('../views/LoginView.vue'), '/login')
    expect(wrapper.text()).toContain('Mot de passe')
    expect(wrapper.find('label[for="login-email"]').exists()).toBe(true)
    i18n.global.locale.value = 'en'

    routes = {}
    axios.defaults.adapter = (config) => Promise.reject(Object.assign(new Error('401'), {
      isAxiosError: true, config, response: { status: 401, data: { error: { message: 'Invalid email or password' } }, config },
    }))
    await wrapper.find('#login-email').setValue('a@b.co')
    await wrapper.find('#login-password').setValue('wrong-password')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.error').text()).toBe('Invalid email or password')
    wrapper.unmount()
  })

  it('login: registration checks the password before calling the server', async () => {
    const { wrapper } = await mountView(() => import('../views/LoginView.vue'), '/login')
    const calls = vi.fn(fakeApi)
    axios.defaults.adapter = calls
    await wrapper.findAll('.tab-switcher button')[1].trigger('click')
    expect(wrapper.text()).toContain('At least 8 characters')
    await wrapper.find('#login-email').setValue('a@b.co')
    await wrapper.find('#login-password').setValue('short')
    await wrapper.find('#login-password2').setValue('short')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.error').text()).toMatch(/at least 8 characters/)
    expect(calls).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('forgot password: works when the server returns no token', async () => {
    routes['/api/auth/forgot-password'] = { message: 'ok' }
    const { wrapper } = await mountView(() => import('../views/ForgotPasswordView.vue'), '/forgot-password')
    await wrapper.find('#forgot-email').setValue('a@b.co')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.success-msg').exists()).toBe(true)
    expect(wrapper.find('.dev-token').exists()).toBe(false)
    expect(wrapper.text()).toMatch(/administrator/)
    wrapper.unmount()
  })

  it('dashboard: shows data, and an error with Retry when the call fails', async () => {
    let { wrapper } = await mountView(() => import('../views/DashboardView.vue'), '/dashboard')
    expect(wrapper.text()).toContain('GA run')
    expect(wrapper.text()).toContain('Best score')
    wrapper.unmount()

    failing = ['/api/dashboard/']
    ;({ wrapper } = await mountView(() => import('../views/DashboardView.vue'), '/dashboard'))
    expect(wrapper.find('[role="alert"]').text()).toContain('The data service is unavailable')
    failing = []
    await wrapper.find('.async-retry').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('GA run')
    wrapper.unmount()
  })

  it('projects: an empty account is offered the demo dataset and "create"', async () => {
    routes['/api/projects/'] = []
    const { wrapper } = await mountView(() => import('../views/ProjectsView.vue'), '/projects')
    expect(wrapper.text()).toContain('Try the demo dataset')
    expect(wrapper.text()).toContain('Create a project')
    expect(wrapper.text()).toContain('1,980 features')
    wrapper.unmount()
  })

  it('projects: creating a project opens it', async () => {
    routes['/api/projects/'] = []
    const { wrapper, router } = await mountView(() => import('../views/ProjectsView.vue'), '/projects')
    const push = vi.spyOn(router, 'push')
    axios.defaults.adapter = (config) => {
      if (config.method === 'post') return Promise.resolve({ status: 200, statusText: 'OK', headers: {}, config, data: { project_id: 'new1', name: 'Mine' } })
      return fakeApi(config)
    }
    await wrapper.find('.btn-new').trigger('click')
    await wrapper.find('.create-form input').setValue('Mine')
    await wrapper.find('.create-form').trigger('submit')
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/project/new1')
    wrapper.unmount()
  })

  it('project page: a failed load shows the reason and Retry instead of "Loading…" forever', async () => {
    failing = ['/api/projects/p1']
    const { wrapper } = await mountView(() => import('../views/ProjectDashboard.vue'), '/project/p1/data')
    expect(wrapper.find('[role="alert"]').text()).toContain('The data service is unavailable')
    expect(wrapper.find('.async-retry').exists()).toBe(true)
    failing = []
    await wrapper.find('.async-retry').trigger('click')
    await flushPromises()
    await flushPromises()
    expect(wrapper.find('.project-header').text()).toContain('Demo project')
    wrapper.unmount()
  })

  it('project page: a running job is picked up again after a refresh', async () => {
    const { wrapper } = await mountView(() => import('../views/ProjectDashboard.vue'), '/project/p1/data')
    const { useProjectStore } = await import('../stores/project')
    expect(useProjectStore().activeJobId).toBe('j2')
    expect(wrapper.find('.console-minimized-bar').exists()).toBe(true)
    wrapper.unmount()
  })

  it('parameters: presets, short essentials, validation blocks the launch', async () => {
    const { wrapper } = await mountView(() => import('../views/ParametersTab.vue'), '/project/p1/parameters', { seedProject: true })
    expect(wrapper.findAll('.preset-btn').length).toBe(3)
    expect(wrapper.find('.preset-btn.active').text()).toContain('Standard')
    const posts = vi.fn()
    axios.defaults.adapter = (config) => {
      if (config.method === 'post') { posts(config); return Promise.resolve({ status: 200, statusText: 'OK', headers: {}, config, data: { job_id: 'j9' } }) }
      return fakeApi(config)
    }
    const pop = wrapper.find('#param-ga-population_size')
    await pop.setValue('3')
    expect(wrapper.find('#param-ga-population_size-error').text()).toContain('at least 10')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(posts).not.toHaveBeenCalled()
    expect(wrapper.find('.launch-errors').exists()).toBe(true)

    await pop.setValue('300')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(posts).toHaveBeenCalledTimes(1)
    const body = JSON.parse(posts.mock.calls[0][0].data)
    expect(body.ga.population_size).toBe(300)
    expect(body.feature_selection).toBeUndefined()
    expect(body.data.feature_minimal_prevalence_pct).toBe(10)
    wrapper.unmount()
  })

  it('data tab: uploads send the role of the slot that was clicked', async () => {
    const project = JSON.parse(JSON.stringify(PROJECT))
    project.datasets = []
    routes['/api/projects/p1'] = project
    const pinia = createPinia()
    setActivePinia(pinia)
    const { useProjectStore } = await import('../stores/project')
    useProjectStore().current = project
    const router = makeRouter('/project/p1/data')
    await router.isReady()
    const { default: DataTab } = await import('../views/DataTab.vue')
    const wrapper = mount(DataTab, { global: { plugins: [pinia, i18n, router] }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.text()).toContain('No data yet')
    expect(wrapper.text()).toContain('one row per feature')

    const posts = vi.fn()
    axios.defaults.adapter = (config) => {
      if (config.method === 'post') { posts(config); return Promise.resolve({ status: 200, statusText: 'OK', headers: {}, config, data: {} }) }
      return fakeApi(config)
    }
    const input = wrapper.findAll('.ds-slot')[0].find('input[type="file"]')
    const file = new File(['a\tb\n'], 'abundance.tsv', { type: 'text/tab-separated-values' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()
    expect(posts).toHaveBeenCalledTimes(1)
    expect(posts.mock.calls[0][0].params).toEqual({ role: 'xtrain' })
    // The fake server did not attach the file: the slot says so instead of staying silently empty.
    expect(wrapper.findAll('.ds-slot')[0].find('.ds-error').text()).toContain('abundance.tsv')
    wrapper.unmount()
  })

  it('data tab: a failed load shows the reason with Retry', async () => {
    failing = ['/api/data-explore/p1/summary']
    const { wrapper } = await mountView(() => import('../views/DataTab.vue'), '/project/p1/data', { seedProject: true })
    expect(wrapper.find('[role="alert"]').text()).toContain('The data service is unavailable')
    failing = []
    await wrapper.find('.async-retry').trigger('click')
    await flushPromises()
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.feature-table').exists()).toBe(true)
    expect(wrapper.find('th[aria-sort]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('results: lists jobs with translated status, puts the job in the URL, offers Cancel for a running job', async () => {
    const { wrapper, router } = await mountView(() => import('../views/ResultsTab.vue'), '/project/p1/results', { seedProject: true })
    await flushPromises()
    expect(wrapper.findAll('.job-table tbody tr').length).toBe(2)
    expect(wrapper.find('.job-table').text()).toContain('completed')
    expect(wrapper.find('.btn-cancel').exists()).toBe(true)
    expect(router.currentRoute.value.params.jobId).toBe('j1')
    expect(wrapper.find('.live-note').exists()).toBe(true)
    wrapper.unmount()
  })

  it('results: a job list that cannot be loaded says so (not "No jobs yet")', async () => {
    failing = ['/api/analysis/p1/jobs']
    const pinia = createPinia()
    setActivePinia(pinia)
    const { useProjectStore } = await import('../stores/project')
    useProjectStore().current = { ...JSON.parse(JSON.stringify(PROJECT)), jobs: [] }
    const router = makeRouter('/project/p1/results')
    await router.isReady()
    const { default: ResultsTab } = await import('../views/ResultsTab.vue')
    const wrapper = mount(ResultsTab, { global: { plugins: [pinia, i18n, router] }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('The data service is unavailable')
    expect(wrapper.text()).not.toContain('No jobs yet')
    wrapper.unmount()
  })

  it('console: translated, with Cancel while the job runs', async () => {
    vi.useFakeTimers()
    const pinia = createPinia()
    setActivePinia(pinia)
    const { default: ConsolePanel } = await import('../components/ConsolePanel.vue')
    const wrapper = mount(ConsolePanel, {
      props: { projectId: 'p1', jobId: 'j2' },
      global: { plugins: [pinia, i18n] },
    })
    await vi.advanceTimersByTimeAsync(50)
    expect(wrapper.find('h4').text()).toBe('Console output')
    expect(wrapper.find('.status-badge').text()).toContain('running')
    expect(wrapper.find('.btn-cancel-job').exists()).toBe(true)
    wrapper.unmount()
    vi.useRealTimers()
  })
})
