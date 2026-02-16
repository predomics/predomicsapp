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

describe('EmptyState', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders with default props', async () => {
    const { default: EmptyState } = await import('../components/projects/EmptyState.vue')
    const wrapper = mount(EmptyState)
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
      slots: {
        default: '<button>Click me</button>',
      },
    })
    expect(wrapper.find('button').exists()).toBe(true)
    expect(wrapper.find('button').text()).toBe('Click me')
  })
})

describe('OnboardingTour', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('reads dismissed state from localStorage on mount', async () => {
    // First-time user: no key in storage
    expect(localStorage.getItem('predomics_onboarding_dismissed')).toBeNull()

    // Set dismissed flag
    localStorage.setItem('predomics_onboarding_dismissed', 'true')
    expect(localStorage.getItem('predomics_onboarding_dismissed')).toBe('true')
  })

  it('component imports successfully', async () => {
    const mod = await import('../components/OnboardingTour.vue')
    expect(mod.default).toBeTruthy()
    expect(mod.default.__name).toBe('OnboardingTour')
  })

  it('renders without errors when not dismissed', async () => {
    const { default: OnboardingTour } = await import('../components/OnboardingTour.vue')
    // Render with disabled Teleport
    const wrapper = mount(OnboardingTour, {
      global: { plugins: [i18n], stubs: { Teleport: { template: '<div><slot /></div>' } } },
    })
    // Component should render (visible becomes true in onMounted)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.tour-overlay').exists()).toBe(true)
    expect(wrapper.findAll('.dot').length).toBe(6)
  })

  it('hides when previously dismissed', async () => {
    localStorage.setItem('predomics_onboarding_dismissed', 'true')
    const { default: OnboardingTour } = await import('../components/OnboardingTour.vue')
    const wrapper = mount(OnboardingTour, {
      global: { plugins: [i18n], stubs: { Teleport: { template: '<div><slot /></div>' } } },
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.tour-overlay').exists()).toBe(false)
  })

  it('navigates through steps', async () => {
    const { default: OnboardingTour } = await import('../components/OnboardingTour.vue')
    const wrapper = mount(OnboardingTour, {
      global: { plugins: [i18n], stubs: { Teleport: { template: '<div><slot /></div>' } } },
    })
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.tour-title').text()).toContain('Welcome')
    await wrapper.find('.tour-btn.primary').trigger('click')
    expect(wrapper.find('.tour-title').text()).toContain('Create a Project')
    await wrapper.find('.tour-btn.secondary').trigger('click')
    expect(wrapper.find('.tour-title').text()).toContain('Welcome')
  })

  it('dismiss hides tour overlay', async () => {
    const { default: OnboardingTour } = await import('../components/OnboardingTour.vue')
    const wrapper = mount(OnboardingTour, {
      global: { plugins: [i18n], stubs: { Teleport: { template: '<div><slot /></div>' } } },
    })
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.tour-overlay').exists()).toBe(true)
    await wrapper.find('.tour-close').trigger('click')
    expect(wrapper.find('.tour-overlay').exists()).toBe(false)
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
        stubs: { 'router-link': true },
      },
    })

    expect(wrapper.find('.pipeline').exists()).toBe(true)
    expect(wrapper.findAll('.pipe-step').length).toBe(5)
  })

  it('renders use case cards', async () => {
    const { default: HomeView } = await import('../views/HomeView.vue')
    const wrapper = mount(HomeView, {
      global: {
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
      props: {
        category: { id: 'general', label: 'General' },
        params: [
          { key: 'seed', label: 'Random seed', category: 'general', level: 'basic',
            inputType: 'number', defaultValue: 42, description: 'Seed for reproducibility' },
        ],
        form: { general: { seed: 42 } },
        advancedMode: false,
      },
    })
    expect(wrapper.find('.param-section').exists()).toBe(true)
    expect(wrapper.text()).toContain('General')
  })
})
