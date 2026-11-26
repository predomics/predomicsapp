/**
 * Tests for Vue components.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import i18n from '../i18n/index.js'

// Mock matchMedia for theme store
vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
  matches: false,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
}))

// Mock IntersectionObserver for HomeView scroll reveal
vi.stubGlobal('IntersectionObserver', class {
  observe() {}
  unobserve() {}
  disconnect() {}
})

describe('EmptyState', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders with default props', async () => {
    const { default: EmptyState } = await import('../components/projects/EmptyState.vue')
    const wrapper = mount(EmptyState, { global: { plugins: [i18n] } })
    expect(wrapper.find('h3').text()).toBe('No project selected')
    expect(wrapper.find('p').text()).toContain('Select a project')
  })

  it('renders with custom props', async () => {
    const { default: EmptyState } = await import('../components/projects/EmptyState.vue')
    const wrapper = mount(EmptyState, {
      props: {
        title: 'Custom Title',
        message: 'Custom message here',
      },
    })
    expect(wrapper.find('h3').text()).toBe('Custom Title')
    expect(wrapper.find('p').text()).toBe('Custom message here')
  })

  it('renders slot content', async () => {
    const { default: EmptyState } = await import('../components/projects/EmptyState.vue')
    const wrapper = mount(EmptyState, {
      global: { plugins: [i18n] },
      slots: {
        default: '<button>Click me</button>',
      },
    })
    expect(wrapper.find('button').exists()).toBe(true)
    expect(wrapper.find('button').text()).toBe('Click me')
  })
})

describe('ProjectChecklist', () => {
  const PROJECT_EMPTY = { project_id: 'p1', datasets: [] }
  const PROJECT_DATA = { project_id: 'p1', datasets: [{ files: [{ role: 'xtrain' }, { role: 'ytrain' }] }] }

  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  async function mountChecklist(props) {
    const { default: ProjectChecklist } = await import('../components/ProjectChecklist.vue')
    return mount(ProjectChecklist, {
      props: { projectId: 'p1', ...props },
      global: { plugins: [i18n], stubs: { 'router-link': { props: ['to'], template: '<a :href="to"><slot /></a>' } } },
    })
  }

  it('steps follow the project state', async () => {
    const { checklistSteps } = await import('../utils/projectChecklist')
    const done = (project, jobs, flags) => checklistSteps(project, jobs, flags).filter(s => s.done).map(s => s.id)
    expect(done(PROJECT_EMPTY, [], {})).toEqual([])
    expect(done(PROJECT_DATA, [], {})).toEqual(['data'])
    expect(done(PROJECT_DATA, [], { parameters: true })).toEqual(['data', 'parameters'])
    expect(done(PROJECT_DATA, [{ status: 'running' }], {})).toEqual(['data', 'parameters', 'launch'])
    // results count only once a job has completed AND the user has looked at them
    expect(done(PROJECT_DATA, [{ status: 'completed' }], {})).toEqual(['data', 'parameters', 'launch'])
    expect(done(PROJECT_DATA, [{ status: 'completed' }], { results: true })).toEqual(['data', 'parameters', 'launch', 'results'])
  })

  it('points at the first unfinished step', async () => {
    const wrapper = await mountChecklist({ project: PROJECT_DATA, jobs: [] })
    expect(wrapper.find('.checklist').exists()).toBe(true)
    const next = wrapper.find('li.next')
    expect(next.find('a').attributes('href')).toBe('/project/p1/parameters')
    expect(wrapper.findAll('li.done')).toHaveLength(1)
  })

  it('hides once every step is done', async () => {
    const { markChecklistStep } = await import('../utils/projectChecklist')
    markChecklistStep('p1', 'parameters')
    markChecklistStep('p1', 'results')
    const wrapper = await mountChecklist({ project: PROJECT_DATA, jobs: [{ status: 'completed' }] })
    expect(wrapper.find('.checklist').exists()).toBe(false)
  })

  it('stays hidden after being dismissed, for that project only', async () => {
    const wrapper = await mountChecklist({ project: PROJECT_EMPTY, jobs: [] })
    await wrapper.find('.checklist-dismiss').trigger('click')
    expect(wrapper.find('.checklist').exists()).toBe(false)
    const again = await mountChecklist({ project: PROJECT_EMPTY, jobs: [] })
    expect(again.find('.checklist').exists()).toBe(false)
    const other = await mountChecklist({ projectId: 'p2', project: { ...PROJECT_EMPTY, project_id: 'p2' }, jobs: [] })
    expect(other.find('.checklist').exists()).toBe(true)
  })

  it('reappears after "show checklists again"', async () => {
    const { dismissChecklist, resetChecklists } = await import('../utils/projectChecklist')
    dismissChecklist('p1')
    resetChecklists()
    const wrapper = await mountChecklist({ project: PROJECT_EMPTY, jobs: [] })
    expect(wrapper.find('.checklist').exists()).toBe(true)
  })
})

describe('HomeView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders pipeline steps', async () => {
    // Mock axios
    vi.mock('axios', () => ({
      default: {
        get: vi.fn().mockResolvedValue({ data: { status: 'ok', version: '0.1.0', gpredomicspy_available: true } }),
        defaults: { headers: { common: {} } },
      },
    }))

    const { default: HomeView } = await import('../views/HomeView.vue')
    const wrapper = mount(HomeView, {
      global: {
        plugins: [i18n],
        stubs: { 'router-link': true },
      },
    })

    expect(wrapper.find('.workflow-track').exists()).toBe(true)
    expect(wrapper.findAll('.wf-step').length).toBe(4)
  })

  it('renders use case cards', async () => {
    const { default: HomeView } = await import('../views/HomeView.vue')
    const wrapper = mount(HomeView, {
      global: {
        plugins: [i18n],
        stubs: { 'router-link': true },
      },
    })

    expect(wrapper.find('.case-grid').exists()).toBe(true)
    expect(wrapper.findAll('.case-card').length).toBe(4)
  })

  it('renders tech highlights', async () => {
    const { default: HomeView } = await import('../views/HomeView.vue')
    const wrapper = mount(HomeView, {
      global: {
        plugins: [i18n],
        stubs: { 'router-link': true },
      },
    })

    expect(wrapper.find('.tech-grid').exists()).toBe(true)
    const techItems = wrapper.findAll('.tech-item')
    expect(techItems.length).toBe(6)
  })

  it('displays Get Started button', async () => {
    const { default: HomeView } = await import('../views/HomeView.vue')
    const wrapper = mount(HomeView, {
      global: {
        plugins: [i18n],
        stubs: { 'router-link': true },
      },
    })

    expect(wrapper.find('.btn-primary').exists()).toBe(true)
  })
})

describe('ParamSection', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders with category and params', async () => {
    const { default: ParamSection } = await import('../components/ParamSection.vue')
    const wrapper = mount(ParamSection, {
      global: { plugins: [i18n] },
      props: {
        category: { id: 'general', label: 'General' },
        params: [
          { key: 'seed', label: 'Random seed', category: 'general', level: 'basic',
            inputType: 'number', defaultValue: 42, description: 'Seed for reproducibility' },
        ],
        form: { seed: 42 },
      },
    })
    expect(wrapper.find('.param-section').exists()).toBe(true)
    expect(wrapper.text()).toContain('General')
  })

  it('binds each label to its input and exposes help to the keyboard', async () => {
    const { default: ParamSection } = await import('../components/ParamSection.vue')
    const form = { seed: 42, epsilon: 0.00001 }
    const wrapper = mount(ParamSection, {
      global: { plugins: [i18n] },
      props: {
        category: { id: 'general', label: 'General' },
        params: [
          { key: 'seed', label: 'Random seed', category: 'general', level: 'basic',
            inputType: 'number', defaultValue: 42, description: 'Seed for reproducibility', min: 0, step: 1 },
          { key: 'epsilon', label: 'Epsilon', category: 'general', level: 'advanced',
            inputType: 'number', defaultValue: 0.00001, description: 'Threshold', min: 0 },
        ],
        form,
      },
    })
    const input = wrapper.find('#param-general-seed')
    expect(input.exists()).toBe(true)
    expect(wrapper.find('label[for="param-general-seed"]').text()).toBe('Random seed')
    const help = wrapper.find('button.info-dot')
    expect(help.attributes('aria-expanded')).toBe('false')
    await help.trigger('click')
    expect(help.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('#param-general-seed-help').text()).toContain('Seed for reproducibility')
    // advanced settings stay folded until asked for
    expect(wrapper.find('details').element.open).toBe(false)
  })

  it('shows a validation message next to the field and opens Advanced when the error is there', async () => {
    const { default: ParamSection } = await import('../components/ParamSection.vue')
    const wrapper = mount(ParamSection, {
      global: { plugins: [i18n] },
      props: {
        category: { id: 'general', label: 'General' },
        params: [
          { key: 'seed', label: 'Random seed', category: 'general', level: 'basic',
            inputType: 'number', defaultValue: 42, description: 'Seed', min: 0, step: 1 },
          { key: 'epsilon', label: 'Epsilon', category: 'general', level: 'advanced',
            inputType: 'number', defaultValue: 0.00001, description: 'Threshold', min: 0 },
        ],
        form: { seed: -1, epsilon: null },
        errors: {
          'general.seed': { code: 'min', params: { min: 0 } },
          'general.epsilon': { code: 'required', params: {} },
        },
      },
    })
    const err = wrapper.find('#param-general-seed-error')
    expect(err.text()).toContain('at least 0')
    expect(wrapper.find('#param-general-seed').attributes('aria-invalid')).toBe('true')
    expect(wrapper.find('details').element.open).toBe(true)
  })

  it('an emptied number becomes null (reported as required), not NaN', async () => {
    const { default: ParamSection } = await import('../components/ParamSection.vue')
    const form = { seed: 42 }
    const wrapper = mount(ParamSection, {
      global: { plugins: [i18n] },
      props: {
        category: { id: 'general', label: 'General' },
        params: [{ key: 'seed', label: 'Random seed', category: 'general', level: 'basic',
          inputType: 'number', defaultValue: 42, description: 'Seed', min: 0, step: 1 }],
        form,
      },
    })
    const input = wrapper.find('#param-general-seed')
    await input.setValue('')
    expect(form.seed).toBeNull()
    await input.setValue('7')
    expect(form.seed).toBe(7)
  })
})
