/**
 * Tests for Pinia stores.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock window.matchMedia before importing stores
vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
  matches: false,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
}))

describe('useThemeStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('defaults to system mode', async () => {
    const { useThemeStore } = await import('../stores/theme')
    const theme = useThemeStore()
    expect(theme.mode).toBe('system')
  })

  it('setMode changes mode and persists to localStorage', async () => {
    const { useThemeStore } = await import('../stores/theme')
    const theme = useThemeStore()
    theme.setMode('dark')
    expect(theme.mode).toBe('dark')
    expect(localStorage.getItem('theme')).toBe('dark')
  })

  it('isDark returns true for dark mode', async () => {
    const { useThemeStore } = await import('../stores/theme')
    const theme = useThemeStore()
    theme.setMode('dark')
    expect(theme.isDark).toBe(true)
  })

  it('isDark returns false for light mode', async () => {
    const { useThemeStore } = await import('../stores/theme')
    const theme = useThemeStore()
    theme.setMode('light')
    expect(theme.isDark).toBe(false)
  })

  it('cycle rotates through light → dark → system', async () => {
    const { useThemeStore } = await import('../stores/theme')
    const theme = useThemeStore()

    // Start at system (default), cycling: system → light
    theme.setMode('light')
    theme.cycle()
    expect(theme.mode).toBe('dark')
    theme.cycle()
    expect(theme.mode).toBe('system')
    theme.cycle()
    expect(theme.mode).toBe('light')
  })
})

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.resetModules()
  })

  it('isLoggedIn is false when no token', async () => {
    const { useAuthStore } = await import('../stores/auth')
    const auth = useAuthStore()
    expect(auth.isLoggedIn).toBe(false)
  })

  it('isAdmin is false when no user', async () => {
    const { useAuthStore } = await import('../stores/auth')
    const auth = useAuthStore()
    expect(auth.isAdmin).toBe(false)
  })

  it('logout clears token and user', async () => {
    const { useAuthStore } = await import('../stores/auth')
    const auth = useAuthStore()
    // Simulate a logged in state
    auth.token = 'fake-token'
    auth.user = { email: 'test@example.com', is_admin: false }
    auth.logout()
    expect(auth.token).toBe('')
    expect(auth.user).toBeNull()
    expect(auth.isLoggedIn).toBe(false)
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('searchUsers returns empty array for short query', async () => {
    const { useAuthStore } = await import('../stores/auth')
    const auth = useAuthStore()
    const result = await auth.searchUsers('a')
    expect(result).toEqual([])
  })
})

describe('useConfigStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('builds defaults from PARAM_DEFS', async () => {
    const { useConfigStore } = await import('../stores/config')
    const config = useConfigStore()
    expect(config.form.general.algo).toBe('ga')
    expect(config.form.general.seed).toBe(42)
    expect(config.form.ga.population_size).toBe(500)
    expect(config.form.ga.max_epochs).toBe(200)
    expect(config.form.ga.k_min).toBe(1)
    expect(config.form.ga.k_max).toBe(200)
  })

  it('has data section with holdout_ratio', async () => {
    const { useConfigStore } = await import('../stores/config')
    const config = useConfigStore()
    expect(config.form.data.holdout_ratio).toBe(0.2)
    expect(config.form.data.features_in_rows).toBe(true)
  })

  it('resetToDefaults restores defaults', async () => {
    const { useConfigStore } = await import('../stores/config')
    const config = useConfigStore()
    config.form.general.seed = 999
    config.form.ga.population_size = 100
    config.resetToDefaults()
    expect(config.form.general.seed).toBe(42)
    expect(config.form.ga.population_size).toBe(500)
  })

  it('resetCategory resets only that category', async () => {
    const { useConfigStore } = await import('../stores/config')
    const config = useConfigStore()
    config.form.general.seed = 999
    config.form.ga.population_size = 100
    config.resetCategory('ga')
    expect(config.form.general.seed).toBe(999) // unchanged
    expect(config.form.ga.population_size).toBe(500) // reset
  })

  it('filterParams returns correct values', async () => {
    const { useConfigStore } = await import('../stores/config')
    const config = useConfigStore()
    expect(config.filterParams.method).toBe('wilcoxon')
    expect(config.filterParams.prevalence_pct).toBe(10)
    expect(config.filterParams.max_pvalue).toBe(0.05)
  })
})
