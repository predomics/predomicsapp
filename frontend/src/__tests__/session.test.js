/**
 * Session lifetime, WebSocket tickets, incremental logs, email verification,
 * login throttling and the cancelled-job status.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import axios from 'axios'
import i18n from '../i18n'
import { decodeJwt, refreshDelayMs } from '../utils/session'
import { isCancelled, isInterrupted, displayStatus, normalizeJobs } from '../utils/jobStatus'
import { apiError, apiErrorCode, retryAfterSeconds } from '../utils/apiError'

const b64url = (obj) => btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
/** An unsigned JWT with the given issue and expiry times (seconds). */
const jwt = (iat, exp, extra = {}) => `${b64url({ alg: 'HS256' })}.${b64url({ sub: 'u1', iat, exp, ...extra })}.sig`

function httpError(status, data, headers = {}) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true, response: { status, data, headers }, config: { url: '/api/x' },
  })
}

let routes
let calls
let saved
function fakeApi(config) {
  const url = config.url.split('?')[0]
  calls.push({ method: config.method, url, params: config.params, data: config.data ? JSON.parse(config.data) : undefined })
  const handler = routes[`${config.method} ${url}`] ?? routes[url]
  const res = typeof handler === 'function' ? handler(config) : handler
  if (res === undefined) return Promise.reject(Object.assign(httpError(404, { error: { code: 'HTTP_404', message: 'Not found' } }), { config }))
  if (res && res.__error) return Promise.reject(Object.assign(httpError(res.status, res.data, res.headers), { config }))
  return Promise.resolve({ status: 200, statusText: 'OK', headers: {}, config, data: JSON.parse(JSON.stringify(res)) })
}
const fail = (status, data, headers) => ({ __error: true, status, data, headers })

beforeEach(() => {
  localStorage.clear()
  i18n.global.locale.value = 'en'
  routes = {}
  calls = []
  saved = axios.defaults.adapter
  axios.defaults.adapter = fakeApi
  delete axios.defaults.headers.common['Authorization']
})
afterEach(() => {
  axios.defaults.adapter = saved
  vi.useRealTimers()
  document.body.innerHTML = ''
})

// ---------------------------------------------------------------------------
describe('token lifetime', () => {
  it('reads exp and iat from a JWT, and rejects anything else', () => {
    expect(decodeJwt(jwt(100, 200))).toMatchObject({ iat: 100, exp: 200, sub: 'u1' })
    expect(decodeJwt('not-a-token')).toBeNull()
    expect(decodeJwt('a.b.c')).toBeNull()
    expect(decodeJwt(null)).toBeNull()
  })

  it('refresh is due when less than a third of the lifetime remains', () => {
    const iat = 1000, exp = 1000 + 9000 // 9000 s lifetime → refresh at 6000 s in
    const at = (s) => (iat + s) * 1000
    expect(refreshDelayMs(jwt(iat, exp), at(0))).toBe(6000 * 1000)
    expect(refreshDelayMs(jwt(iat, exp), at(5999))).toBe(1000)
    expect(refreshDelayMs(jwt(iat, exp), at(6000))).toBe(0)
    expect(refreshDelayMs(jwt(iat, exp), at(8000))).toBe(0)      // overdue but still valid
    expect(refreshDelayMs(jwt(iat, exp), at(9000))).toBeNull()   // expired: nothing to renew
    expect(refreshDelayMs('garbage', at(0))).toBeNull()
    expect(refreshDelayMs(`${b64url({})}.${b64url({ sub: 'u1' })}.s`, at(0))).toBeNull() // no exp/iat
  })
})

describe('session renewal in the auth store', () => {
  async function storeWith(token) {
    localStorage.setItem('token', token)
    setActivePinia(createPinia())
    const { useAuthStore } = await import('../stores/auth')
    return useAuthStore()
  }

  it('renews the token at two thirds of its lifetime and keeps using the new one', async () => {
    vi.useFakeTimers()
    const now = Math.floor(Date.now() / 1000)
    const fresh = jwt(now + 600, now + 600 + 900)
    routes['post /api/auth/refresh'] = { access_token: fresh }
    const auth = await storeWith(jwt(now, now + 900)) // refresh due after 600 s
    await vi.advanceTimersByTimeAsync(599 * 1000)
    expect(calls.filter(c => c.url === '/api/auth/refresh')).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(2 * 1000)
    expect(calls.filter(c => c.url === '/api/auth/refresh')).toHaveLength(1)
    expect(auth.token).toBe(fresh)
    expect(localStorage.getItem('token')).toBe(fresh)
    expect(axios.defaults.headers.common['Authorization']).toBe(`Bearer ${fresh}`)
  })

  it('a server without the refresh endpoint is asked once, and the session is left alone', async () => {
    vi.useFakeTimers()
    const now = Math.floor(Date.now() / 1000)
    const token = jwt(now - 800, now + 100) // already in the last third
    const auth = await storeWith(token)
    await vi.advanceTimersByTimeAsync(5000)
    expect(calls.filter(c => c.url === '/api/auth/refresh')).toHaveLength(1)
    expect(await auth.refreshSession()).toBe(false)
    expect(calls.filter(c => c.url === '/api/auth/refresh')).toHaveLength(1)
    expect(auth.token).toBe(token)
  })

  it('changing the password stores the token the server hands back', async () => {
    const now = Math.floor(Date.now() / 1000)
    const next = jwt(now, now + 900, { v: 2 })
    routes['put /api/auth/me/password'] = { status: 'password_changed', access_token: next }
    const auth = await storeWith(jwt(now, now + 900))
    await auth.changePassword('old', 'new-password')
    expect(auth.token).toBe(next)
  })

  it('registration that needs email confirmation does not try to log in', async () => {
    routes['post /api/auth/register'] = { id: '', verification_required: true, message: 'Check your inbox.' }
    setActivePinia(createPinia())
    const { useAuthStore } = await import('../stores/auth')
    const res = await useAuthStore().register('new@example.com', 'a-long-password', 'N')
    expect(res).toEqual({ verificationRequired: true, message: 'Check your inbox.' })
    expect(calls.some(c => c.url === '/api/auth/login')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
describe('console: WebSocket ticket and incremental logs', () => {
  let sockets
  beforeEach(() => {
    sockets = []
    globalThis.WebSocket = class {
      constructor(url) { this.url = url; sockets.push(this) }
      close() {}
    }
    routes['get /api/analysis/p1/jobs/j1'] = { job_id: 'j1', status: 'running', config_summary: 'ep=10' }
    routes['get /api/analysis/p1/jobs/j1/progress'] = { points: [] }
  })

  async function mountConsole(token = 'access-token') {
    localStorage.setItem('token', token)
    setActivePinia(createPinia())
    const { default: ConsolePanel } = await import('../components/ConsolePanel.vue')
    return mount(ConsolePanel, { props: { projectId: 'p1', jobId: 'j1' }, global: { plugins: [i18n] } })
  }

  it('opens the socket with a one-time ticket, never with the access token', async () => {
    vi.useFakeTimers()
    routes['post /api/auth/ws-ticket'] = { ticket: 'T-123', expires_in: 30 }
    routes['get /api/analysis/p1/jobs/j1/logs'] = { log: '', status: 'running', offset: 0, next_offset: 0 }
    const wrapper = await mountConsole('SECRET-ACCESS-TOKEN')
    await vi.advanceTimersByTimeAsync(50)
    expect(sockets).toHaveLength(1)
    expect(sockets[0].url).toContain('/ws/jobs/p1/j1?ticket=T-123')
    expect(sockets[0].url).not.toContain('SECRET-ACCESS-TOKEN')
    expect(sockets[0].url).not.toContain('token=')
    wrapper.unmount()
  })

  it('without a ticket endpoint there is no socket: the console polls, asking only for new output', async () => {
    vi.useFakeTimers()
    let n = 0
    routes['get /api/analysis/p1/jobs/j1/logs'] = (config) => {
      n++
      const offset = Number(config.params?.offset || 0)
      if (offset === 0) return { log: 'line 1\n', status: 'running', offset: 0, next_offset: 7 }
      if (offset === 7) return { log: 'line 2\n', status: 'running', offset: 7, next_offset: 14 }
      return { log: '', status: 'running', offset, next_offset: offset }
    }
    const wrapper = await mountConsole()
    await vi.advanceTimersByTimeAsync(50)
    expect(sockets).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(2100)
    const logCalls = calls.filter(c => c.url === '/api/analysis/p1/jobs/j1/logs')
    expect(logCalls[0].params).toBeUndefined()
    expect(logCalls[1].params).toEqual({ offset: 7 })
    expect(logCalls[2].params).toEqual({ offset: 14 })
    expect(n).toBeGreaterThanOrEqual(3)
    expect(wrapper.find('.console-output, pre').text()).toContain('line 1')
    expect(wrapper.find('.console-output, pre').text()).toContain('line 2')
    expect(wrapper.find('.console-output, pre').text().match(/line 1/g)).toHaveLength(1)
    wrapper.unmount()
  })

  it('a job stopped by the user is reported as cancelled, not failed', async () => {
    vi.useFakeTimers()
    routes['get /api/analysis/p1/jobs/j1/logs'] = { log: 'x\n', status: 'failed' }
    routes['get /api/analysis/p1/jobs/j1'] = { job_id: 'j1', status: 'failed', error_message: 'Cancelled by user.' }
    const wrapper = await mountConsole()
    await vi.advanceTimersByTimeAsync(200)
    expect(wrapper.emitted('cancelled')).toHaveLength(1)
    expect(wrapper.emitted('failed')).toBeUndefined()
    expect(wrapper.find('.status-badge').classes()).toContain('cancelled')
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------------------
describe('job status', () => {
  it('"failed" with the cancel message is a cancelled job', () => {
    expect(isCancelled({ status: 'failed', error_message: 'Cancelled by user.' })).toBe(true)
    expect(isCancelled({ status: 'failed', error_message: 'Worker exited with code 1' })).toBe(false)
    expect(isCancelled({ status: 'completed' })).toBe(false)
    expect(isCancelled('failed', 'cancelled by user')).toBe(true)
    expect(displayStatus({ status: 'failed', error_message: 'Cancelled by user.' })).toBe('cancelled')
    expect(displayStatus({ status: 'running' })).toBe('running')
    expect(isInterrupted({ status: 'failed', error_message: 'Interrupted by a server restart' })).toBe(true)
  })

  it('job lists are normalised once, without touching other jobs', () => {
    const jobs = [
      { job_id: 'a', status: 'failed', error_message: 'Cancelled by user.' },
      { job_id: 'b', status: 'failed', error_message: 'boom' },
      { job_id: 'c', status: 'completed' },
    ]
    expect(normalizeJobs(jobs).map(j => j.status)).toEqual(['cancelled', 'failed', 'completed'])
    expect(jobs[0].status).toBe('failed') // input left as received
    expect(normalizeJobs(null)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
describe('error details', () => {
  it('exposes the error code and the Retry-After delay', () => {
    const e = httpError(429, { error: { code: 'TOO_MANY_ATTEMPTS', message: 'Too many attempts.' } }, { 'retry-after': '120' })
    expect(apiErrorCode(e)).toBe('TOO_MANY_ATTEMPTS')
    expect(retryAfterSeconds(e)).toBe(120)
    expect(retryAfterSeconds(httpError(429, {}))).toBe(0)
    expect(apiErrorCode(httpError(500, 'oops'))).toBe('')
  })

  it('a 429 without a message says how long to wait', () => {
    expect(apiError(httpError(429, {}, { 'retry-after': '30' }))).toBe('Too many attempts. Try again in 30 seconds.')
  })

  it('server errors carry the request reference; client errors do not', () => {
    const headers = { 'x-request-id': 'req-42' }
    expect(apiError(httpError(500, { error: { code: 'INTERNAL_ERROR', message: 'An unexpected error occurred' } }, headers)))
      .toBe('An unexpected error occurred (reference: req-42)')
    expect(apiError(httpError(404, { error: { message: 'Project not found' } }, headers))).toBe('Project not found')
    expect(apiError(httpError(413, { error: { code: 'QUOTA_EXCEEDED', message: 'Storage quota exceeded (2 GB).' } })))
      .toBe('Storage quota exceeded (2 GB).')
  })
})

// ---------------------------------------------------------------------------
describe('login screen', () => {
  async function mountLogin() {
    const pinia = createPinia()
    setActivePinia(pinia)
    const stub = { template: '<div />' }
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/login', name: 'Login', component: stub }, { path: '/projects', name: 'Projects', component: stub },
      { path: '/forgot-password', component: stub },
    ] })
    router.push('/login')
    await router.isReady()
    const { default: LoginView } = await import('../views/LoginView.vue')
    const wrapper = mount(LoginView, { global: { plugins: [pinia, i18n, router] }, attachTo: document.body })
    return { wrapper, router }
  }
  async function fill(wrapper, { email = 'a@example.com', password = 'a-long-password' } = {}) {
    await wrapper.find('#login-email').setValue(email)
    await wrapper.find('#login-password').setValue(password)
  }

  it('an unconfirmed address gets "check your inbox" and a working resend', async () => {
    routes['post /api/auth/login'] = fail(403, { error: { code: 'EMAIL_NOT_VERIFIED', message: 'Email not verified' } })
    routes['post /api/auth/resend-verification'] = { status: 'ok' }
    const { wrapper, router } = await mountLogin()
    await fill(wrapper)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const box = wrapper.find('.verify-box')
    expect(box.exists()).toBe(true)
    expect(box.text()).toContain('a@example.com')
    expect(wrapper.find('.error').exists()).toBe(false)
    expect(router.currentRoute.value.path).toBe('/login')
    await box.find('button').trigger('click')
    await flushPromises()
    expect(calls.find(c => c.url === '/api/auth/resend-verification').data).toEqual({ email: 'a@example.com' })
    expect(box.text()).toContain('on its way')
    wrapper.unmount()
  })

  it('registering on a server that requires confirmation shows the server message and stays on the page', async () => {
    routes['post /api/auth/register'] = { id: '', verification_required: true, message: 'We sent you a confirmation link.' }
    const { wrapper, router } = await mountLogin()
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await fill(wrapper)
    await wrapper.find('#login-password2').setValue('a-long-password')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.verify-box').text()).toContain('We sent you a confirmation link.')
    expect(calls.some(c => c.url === '/api/auth/login')).toBe(false)
    expect(router.currentRoute.value.path).toBe('/login')
    wrapper.unmount()
  })

  it('too many attempts: shows the wait, blocks the button, then lets the user retry', async () => {
    vi.useFakeTimers()
    routes['post /api/auth/login'] = fail(429, { error: { code: 'TOO_MANY_ATTEMPTS', message: 'Too many failed attempts.' } }, { 'retry-after': '3' })
    const { wrapper } = await mountLogin()
    await fill(wrapper)
    await wrapper.find('form').trigger('submit')
    await vi.advanceTimersByTimeAsync(10)
    expect(wrapper.find('.error').text()).toBe('Too many failed attempts.')
    expect(wrapper.text()).toContain('You can try again in 3 s.')
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeDefined()
    await vi.advanceTimersByTimeAsync(3100)
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).not.toContain('You can try again')
    wrapper.unmount()
  })
})

describe('email confirmation page', () => {
  async function mountVerify(url) {
    const pinia = createPinia()
    setActivePinia(pinia)
    const stub = { template: '<div />' }
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/verify-email', component: stub }, { path: '/login', component: stub },
    ] })
    router.push(url)
    await router.isReady()
    const { default: VerifyEmailView } = await import('../views/VerifyEmailView.vue')
    const wrapper = mount(VerifyEmailView, { global: { plugins: [pinia, i18n, router] } })
    await flushPromises()
    return wrapper
  }

  it('confirms the token from the link', async () => {
    routes['post /api/auth/verify-email'] = { status: 'verified' }
    const wrapper = await mountVerify('/verify-email?token=abc')
    expect(calls.find(c => c.url === '/api/auth/verify-email').data).toEqual({ token: 'abc' })
    expect(wrapper.text()).toContain('Your email address is confirmed')
  })

  it('a bad token shows the reason and offers to send a new link', async () => {
    routes['post /api/auth/verify-email'] = fail(400, { error: { code: 'INVALID_VERIFICATION_TOKEN', message: 'This link has expired.' } })
    routes['post /api/auth/resend-verification'] = { status: 'ok' }
    const wrapper = await mountVerify('/verify-email?token=old')
    expect(wrapper.find('[role="alert"]').text()).toBe('This link has expired.')
    await wrapper.find('#verify-email').setValue('me@example.com')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(calls.find(c => c.url === '/api/auth/resend-verification').data).toEqual({ email: 'me@example.com' })
  })

  it('a link without a token asks for the address instead of calling the server', async () => {
    const wrapper = await mountVerify('/verify-email')
    expect(calls).toHaveLength(0)
    expect(wrapper.find('#verify-email').exists()).toBe(true)
  })
})
