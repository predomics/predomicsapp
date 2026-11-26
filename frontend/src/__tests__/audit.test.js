/**
 * Tests for the audit fixes: one error helper, session expiry, request
 * language, parameter validation, per-project drafts, translation parity.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import fs from 'node:fs'
import path from 'node:path'
import axios from 'axios'
import i18n from '../i18n'
import en from '../i18n/locales/en.json'
import fr from '../i18n/locales/fr.json'
import { apiError, extractApiError, ignoreError } from '../utils/apiError'
import { setupHttp, safeRedirect, isAuthRequest, DEFAULT_TIMEOUT_MS } from '../utils/http'
import { validateParam, validateForm } from '../utils/paramValidation'
import { PARAM_DEFS, PARAM_INDEX, CATEGORIES, ESSENTIAL_PARAMS } from '../data/parameterDefs'
import { PRESETS, matchingPreset } from '../data/presets'
import { paramLabel, paramDescription, paramErrorText } from '../utils/paramI18n'
import { ct, chartKey } from '../utils/chartText'
import { statusLabel, isLive } from '../utils/jobStatus'

const SRC = path.resolve(__dirname, '..')

function httpError(status, data, extra = {}) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data },
    config: { url: '/api/thing' },
    ...extra,
  })
}

// ---------------------------------------------------------------------------
// apiError
// ---------------------------------------------------------------------------
describe('apiError', () => {
  beforeEach(() => { i18n.global.locale.value = 'en' })

  it('reads the backend error envelope {error: {message}}', () => {
    const e = httpError(401, { error: { code: 'unauthorized', message: 'Invalid email or password' } })
    expect(apiError(e)).toBe('Invalid email or password')
  })

  it('reads a legacy string detail', () => {
    expect(apiError(httpError(400, { detail: 'Dataset not found' }))).toBe('Dataset not found')
  })

  it('joins a FastAPI 422 detail array instead of printing [object Object]', () => {
    const e = httpError(422, {
      detail: [
        { loc: ['body', 'ga', 'population_size'], msg: 'Input should be greater than 0', type: 'greater_than' },
        { loc: ['query', 'x_file_id'], msg: 'Field required', type: 'missing' },
      ],
    })
    const msg = apiError(e)
    expect(msg).toContain('ga.population_size: Input should be greater than 0')
    expect(msg).toContain('x_file_id: Field required')
    expect(msg).not.toContain('[object Object]')
  })

  it('explains a timeout and an unreachable server in plain words', () => {
    const timeout = Object.assign(new Error('timeout of 60000ms exceeded'), { code: 'ECONNABORTED', request: {} })
    expect(apiError(timeout)).toMatch(/too long/i)
    const offline = Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK', request: {} })
    expect(apiError(offline)).toMatch(/cannot reach the server/i)
  })

  it('uses the caller fallback only when the server said nothing', () => {
    expect(apiError(httpError(500, ''), 'Could not save')).toBe('Could not save')
    expect(apiError(httpError(500, { error: { message: 'Disk full' } }), 'Could not save')).toBe('Disk full')
  })

  it('handles 429 and translates generic messages', () => {
    expect(apiError(httpError(429, {}))).toMatch(/too many requests/i)
    i18n.global.locale.value = 'fr'
    expect(apiError(httpError(429, {}))).toMatch(/trop de requêtes/i)
    i18n.global.locale.value = 'en'
  })

  it('marks the error handled; extractApiError does not', () => {
    const a = httpError(400, { detail: 'x' })
    extractApiError(a)
    expect(a._handled).toBeUndefined()
    apiError(a)
    expect(a._handled).toBe(true)
    const b = httpError(400, {})
    ignoreError(b)
    expect(b._handled).toBe(true)
  })

  it('never throws on odd input', () => {
    expect(typeof apiError(null)).toBe('string')
    expect(typeof apiError(new Error('boom'))).toBe('string')
    expect(apiError(new Error('boom'))).toBe('boom')
  })
})

// ---------------------------------------------------------------------------
// HTTP setup: timeout, language header, 401, single error channel
// ---------------------------------------------------------------------------
describe('setupHttp', () => {
  let addToast, router, auth, lastConfig
  let clock = Date.now()

  function respondWith(status, data) {
    return (config) => {
      lastConfig = config
      if (status >= 200 && status < 300) {
        return Promise.resolve({ status, data, headers: {}, config, statusText: 'OK' })
      }
      return Promise.reject(Object.assign(new Error(`Request failed with status code ${status}`), {
        isAxiosError: true, config, response: { status, data, headers: {}, config },
      }))
    }
  }

  beforeEach(() => {
    vi.useFakeTimers()
    // Each test starts well after the previous one: the "session expired"
    // message is de-duplicated over a few seconds.
    vi.setSystemTime(clock += 60000)
    axios.interceptors.request.clear()
    axios.interceptors.response.clear()
    localStorage.clear()
    addToast = vi.fn()
    auth = { token: 'tok', logout: vi.fn(() => { auth.token = '' }) }
    router = {
      currentRoute: { value: { name: 'ProjectData', fullPath: '/project/abc/data?viz=pcoa', meta: {} } },
      push: vi.fn(() => Promise.resolve()),
    }
    i18n.global.locale.value = 'en'
    setupHttp({ router, i18n, addToast, getAuthStore: () => auth })
  })

  afterEach(() => {
    vi.useRealTimers()
    axios.interceptors.request.clear()
    axios.interceptors.response.clear()
  })

  it('sets a default timeout so no request can hang forever', () => {
    expect(axios.defaults.timeout).toBe(DEFAULT_TIMEOUT_MS)
    expect(DEFAULT_TIMEOUT_MS).toBeGreaterThan(0)
  })

  it('sends the UI language with every request', async () => {
    i18n.global.locale.value = 'fr'
    await axios.get('/api/x', { adapter: respondWith(200, {}) })
    expect(lastConfig.headers['Accept-Language']).toBe('fr')
    i18n.global.locale.value = 'en'
  })

  it('401 on an API call logs out, explains, and redirects back to the page', async () => {
    await expect(axios.get('/api/projects/', { adapter: respondWith(401, { error: { message: 'Not authenticated' } }) })).rejects.toBeTruthy()
    expect(auth.logout).toHaveBeenCalledTimes(1)
    expect(addToast).toHaveBeenCalledTimes(1)
    expect(addToast.mock.calls[0][0]).toMatch(/session has expired/i)
    expect(router.push).toHaveBeenCalledWith({ name: 'Login', query: { redirect: '/project/abc/data?viz=pcoa' } })
  })

  it('several 401s at once produce one message and one redirect', async () => {
    const calls = [1, 2, 3].map(() => axios.get('/api/a', { adapter: respondWith(401, {}) }).catch(() => {}))
    await Promise.all(calls)
    expect(addToast).toHaveBeenCalledTimes(1)
    expect(router.push).toHaveBeenCalledTimes(1)
  })

  it('401 on login is a wrong password, not an expired session', async () => {
    const p = axios.post('/api/auth/login', {}, { adapter: respondWith(401, { error: { message: 'Invalid email or password' } }) })
    let caught
    await p.catch((e) => { caught = e })
    expect(auth.logout).not.toHaveBeenCalled()
    expect(router.push).not.toHaveBeenCalled()
    expect(apiError(caught)).toBe('Invalid email or password')
    vi.runAllTimers()
    expect(addToast).not.toHaveBeenCalled()
    expect(isAuthRequest({ url: '/api/auth/login' })).toBe(true)
    expect(isAuthRequest({ url: '/api/auth/me' })).toBe(false)
  })

  it('an error nobody handles is shown once as a toast, with the server message', async () => {
    await axios.get('/api/x', { adapter: respondWith(500, { error: { message: 'Database is down' } }) }).catch(() => {})
    expect(addToast).not.toHaveBeenCalled()
    vi.runAllTimers()
    expect(addToast).toHaveBeenCalledTimes(1)
    expect(addToast.mock.calls[0]).toEqual(['Database is down', 'error'])
  })

  it('an error the component reports itself is not toasted a second time', async () => {
    let shown = ''
    await axios.get('/api/x', { adapter: respondWith(400, { detail: 'Bad file' }) }).catch((e) => { shown = apiError(e) })
    vi.runAllTimers()
    expect(shown).toBe('Bad file')
    expect(addToast).not.toHaveBeenCalled()
  })

  it('silentError requests never toast', async () => {
    await axios.get('/api/optional', { silentError: true, adapter: respondWith(404, {}) }).catch(() => {})
    vi.runAllTimers()
    expect(addToast).not.toHaveBeenCalled()
  })
})

describe('safeRedirect', () => {
  it('accepts in-app paths only', () => {
    expect(safeRedirect('/project/1/results/abc?tab=jury')).toBe('/project/1/results/abc?tab=jury')
    expect(safeRedirect('https://evil.example/')).toBe('/projects')
    expect(safeRedirect('//evil.example/')).toBe('/projects')
    expect(safeRedirect(undefined)).toBe('/projects')
    expect(safeRedirect('/login?redirect=/x')).toBe('/projects')
  })
})

// ---------------------------------------------------------------------------
// Parameter validation
// ---------------------------------------------------------------------------
describe('parameter validation', () => {
  const def = (id) => PARAM_INDEX[id]

  it('requires a value for ordinary numbers but not for "automatic" ones', () => {
    expect(validateParam(def('ga.population_size'), null)).toEqual({ code: 'required', params: {} })
    expect(validateParam(def('ga.population_size'), NaN)).toEqual({ code: 'required', params: {} })
    expect(validateParam(def('ga.population_size'), '')).toEqual({ code: 'required', params: {} })
    expect(def('rf.max_depth').defaultValue).toBeNull()
    expect(validateParam(def('rf.max_depth'), null)).toBeNull()
  })

  it('enforces min and max from the definitions', () => {
    expect(validateParam(def('ga.population_size'), 5)).toEqual({ code: 'min', params: { min: 10 } })
    expect(validateParam(def('general.thread_number'), 65)).toEqual({ code: 'max', params: { max: 64 } })
    expect(validateParam(def('general.thread_number'), 4)).toBeNull()
  })

  it('rejects decimals where a whole number is expected', () => {
    expect(validateParam(def('ga.population_size'), 500.5)).toEqual({ code: 'integer', params: {} })
    expect(validateParam(def('general.k_penalty'), 0.0005)).toBeNull()
  })

  it('needs at least one language / data type', () => {
    expect(validateParam(def('general.language'), '')).toEqual({ code: 'pickOne', params: {} })
    expect(validateParam(def('general.language'), 'bin,ter')).toBeNull()
    expect(validateParam(def('general.language'), 'bin,klingon')).toEqual({ code: 'option', params: {} })
  })

  it('every default value is valid', () => {
    for (const p of PARAM_DEFS) {
      expect(validateParam(p, p.defaultValue), `${p.category}.${p.key}`).toBeNull()
    }
  })

  it('checks that minimums do not exceed maximums', () => {
    const form = { ga: {} }
    const gaDefs = PARAM_DEFS.filter(p => p.category === 'ga')
    for (const p of gaDefs) form.ga[p.key] = p.defaultValue
    expect(validateForm(form, gaDefs)).toEqual({})
    form.ga.k_min = 50
    form.ga.k_max = 10
    const errors = validateForm(form, gaDefs)
    expect(errors['ga.k_max']).toEqual({ code: 'atLeast', params: { other: 'k_min', value: 50 } })
    expect(paramErrorText(errors['ga.k_max'], gaDefs)).toContain('k min')
  })

  it('only validates what is passed in (hidden sections are skipped)', () => {
    const form = { ga: { population_size: null }, general: { seed: 42 } }
    const errors = validateForm(form, [def('general.seed')])
    expect(errors).toEqual({})
  })

  it('has a translated message for every error code', () => {
    for (const code of ['required', 'number', 'min', 'max', 'integer', 'pickOne', 'option', 'atLeast', 'greaterThan']) {
      expect(i18n.global.te(`paramErrors.${code}`, 'en'), code).toBe(true)
      expect(i18n.global.te(`paramErrors.${code}`, 'fr'), code).toBe(true)
    }
  })
})

// ---------------------------------------------------------------------------
// Parameter definitions: essentials, presets, no duplicated filtering section
// ---------------------------------------------------------------------------
describe('parameter form shape', () => {
  it('shows a short list of essentials for the default algorithm', () => {
    const basicsFor = (cat) => PARAM_DEFS.filter(p => p.category === cat && p.level === 'basic').length
    expect(basicsFor('general')).toBeLessThanOrEqual(6)
    expect(basicsFor('general') + basicsFor('ga')).toBeLessThanOrEqual(10)
    for (const id of ESSENTIAL_PARAMS) expect(PARAM_INDEX[id], id).toBeTruthy()
  })

  it('does not define feature filtering a second time', () => {
    expect(CATEGORIES.some(c => c.id === 'feature_selection')).toBe(false)
    expect(PARAM_DEFS.some(p => p.category === 'feature_selection')).toBe(false)
  })

  it('built-in presets only touch existing parameters with valid values', () => {
    expect(PRESETS.map(p => p.id)).toEqual(['quick', 'standard', 'thorough'])
    for (const preset of PRESETS) {
      for (const [cat, vals] of Object.entries(preset.values)) {
        for (const [key, value] of Object.entries(vals)) {
          const d = PARAM_INDEX[`${cat}.${key}`]
          expect(d, `${preset.id}: ${cat}.${key}`).toBeTruthy()
          expect(validateParam(d, value), `${preset.id}: ${cat}.${key}`).toBeNull()
        }
      }
      expect(i18n.global.te(`parameters.presets.${preset.id}.name`)).toBe(true)
    }
  })
})

describe('config store: presets and per-project drafts', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.useFakeTimers()
  })
  afterEach(() => { vi.useRealTimers() })

  it('the defaults are the "standard" preset', async () => {
    const { useConfigStore } = await import('../stores/config')
    const config = useConfigStore()
    expect(matchingPreset(config.form)).toBe('standard')
    config.applyPreset('quick')
    expect(matchingPreset(config.form)).toBe('quick')
    expect(config.form.ga.population_size).toBe(200)
    config.form.ga.population_size = 321
    expect(matchingPreset(config.form)).toBe('')
  })

  it('payload carries the filters once, under "data"', async () => {
    const { useConfigStore } = await import('../stores/config')
    const config = useConfigStore()
    config.form.data.feature_minimal_prevalence_pct = 30
    const body = config.payload()
    expect(body.feature_selection).toBeUndefined()
    expect(body.data.feature_minimal_prevalence_pct).toBe(30)
    expect(body.general.algo).toBe('ga')
  })

  it('an old job config with a feature_selection section lands in data', async () => {
    const { useConfigStore } = await import('../stores/config')
    const config = useConfigStore()
    config.loadFromJobConfig({ feature_selection: { feature_minimal_prevalence_pct: 25 }, ga: { k_max: 77, bogus: 1 } })
    expect(config.form.data.feature_minimal_prevalence_pct).toBe(25)
    expect(config.form.ga.k_max).toBe(77)
    expect(config.form.ga.bogus).toBeUndefined()
  })

  it('keeps a draft per project across a reload, and keeps projects apart', async () => {
    const { useConfigStore } = await import('../stores/config')
    let config = useConfigStore()
    config.bindProject('p1')
    config.form.general.seed = 7
    config.form.data.holdout_ratio = 0.3
    await vi.advanceTimersByTimeAsync(500)
    expect(JSON.parse(localStorage.getItem('predomics_params_p1')).form.general.seed).toBe(7)

    // Another project starts from the defaults, not from p1's settings.
    config.bindProject('p2')
    expect(config.form.general.seed).toBe(42)
    expect(config.form.data.holdout_ratio).toBe(0.2)

    // "Reload": a fresh store restores p1's draft.
    setActivePinia(createPinia())
    config = useConfigStore()
    config.bindProject('p1')
    expect(config.form.general.seed).toBe(7)
    expect(config.form.data.holdout_ratio).toBe(0.3)
  })

  it('survives a corrupted draft', async () => {
    localStorage.setItem('predomics_params_px', '{not json')
    const { useConfigStore } = await import('../stores/config')
    const config = useConfigStore()
    config.bindProject('px')
    expect(config.form.general.seed).toBe(42)
  })
})

// ---------------------------------------------------------------------------
// Translations
// ---------------------------------------------------------------------------
function flatten(obj, prefix = '', out = {}) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object') flatten(v, key, out)
    else out[key] = v
  }
  return out
}

function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name)
    if (fs.statSync(full).isDirectory()) {
      if (name !== '__tests__' && name !== 'locales') walk(full, out)
    } else if (/\.(vue|js)$/.test(name)) out.push(full)
  }
  return out
}

describe('i18n', () => {
  const enFlat = flatten(en)
  const frFlat = flatten(fr)

  it('en.json and fr.json have exactly the same keys', () => {
    const enKeys = Object.keys(enFlat).sort()
    const frKeys = Object.keys(frFlat).sort()
    expect(frKeys.filter(k => !(k in enFlat))).toEqual([])
    expect(enKeys.filter(k => !(k in frFlat))).toEqual([])
  })

  it('no empty translations', () => {
    for (const [k, v] of Object.entries(enFlat)) expect(String(v).trim(), `en ${k}`).not.toBe('')
    for (const [k, v] of Object.entries(frFlat)) expect(String(v).trim(), `fr ${k}`).not.toBe('')
  })

  it('placeholders match between the two languages', () => {
    const vars = (s) => [...String(s).matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort().join(',')
    const mismatched = Object.keys(enFlat).filter(k => vars(enFlat[k]) !== vars(frFlat[k]))
    expect(mismatched).toEqual([])
  })

  it('every message compiles in both languages', () => {
    const errors = []
    const spy = vi.spyOn(console, 'warn').mockImplementation((...a) => { errors.push(a.join(' ')) })
    for (const locale of ['en', 'fr']) {
      i18n.global.locale.value = locale
      for (const key of Object.keys(enFlat)) {
        try { i18n.global.t(key, { n: 2, name: 'x', error: 'x' }) } catch (e) { errors.push(`${locale} ${key}: ${e.message}`) }
      }
    }
    i18n.global.locale.value = 'en'
    spy.mockRestore()
    expect(errors.filter(e => /compil|syntax|invalid/i.test(e))).toEqual([])
  })

  it('every key used with a literal in the source exists', () => {
    const used = new Set()
    for (const file of walk(SRC)) {
      const text = fs.readFileSync(file, 'utf8')
      for (const m of text.matchAll(/(?:\$t|\bt|\bte|\btr)\(\s*'([a-zA-Z][\w]*(?:\.[\w]+)+)'/g)) used.add(m[1])
    }
    expect(used.size).toBeGreaterThan(300)
    const missing = [...used].filter(k => !(k in enFlat)).sort()
    expect(missing).toEqual([])
  })

  it('every parameter, option and section has a translation key', () => {
    for (const p of PARAM_DEFS) {
      const base = `params.${p.category}.${p.key}`
      expect(enFlat[`${base}.label`], base).toBe(p.label)
      expect(enFlat[`${base}.desc`], base).toBe(p.description)
      for (const o of p.options || []) expect(`${base}.opt.${o.value}` in frFlat, `${base}.opt.${o.value}`).toBe(true)
    }
    for (const c of CATEGORIES) expect(`paramCategories.${c.id}` in frFlat, c.id).toBe(true)
    i18n.global.locale.value = 'fr'
    expect(paramLabel(PARAM_INDEX['ga.population_size'])).toBe('Taille de la population')
    expect(paramDescription(PARAM_INDEX['general.cv'])).toMatch(/validation croisée/i)
    i18n.global.locale.value = 'en'
    expect(paramLabel(PARAM_INDEX['ga.population_size'])).toBe('Population size')
  })

  it('chart labels and job statuses follow the language', () => {
    expect(chartKey('Pheromone (τ)')).toBe('charts.pheromoneTau')
    expect(ct('Generation')).toBe('Generation')
    expect(ct('Some label nobody translated')).toBe('Some label nobody translated')
    i18n.global.locale.value = 'fr'
    expect(ct('Generation')).toBe('Génération')
    expect(statusLabel('failed')).toBe(frFlat['common.failed'])
    expect(statusLabel('cancelled')).toBe('annulé')
    i18n.global.locale.value = 'en'
    expect(isLive('running')).toBe(true)
    expect(isLive('completed')).toBe(false)
  })

  it('<html lang> follows the language', async () => {
    const { applyDocumentLang } = await import('../i18n')
    applyDocumentLang('fr')
    expect(document.documentElement.getAttribute('lang')).toBe('fr')
    applyDocumentLang('en')
  })
})
