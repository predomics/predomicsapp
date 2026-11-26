/**
 * Axios setup: timeout, language header, and one place for error reporting.
 *
 * Error channel: when a request fails, the interceptor waits one macrotask.
 * If by then no caller has read the error through apiError()/ignoreError(),
 * a toast is shown. Components that display the message themselves (inline,
 * or their own toast) call apiError(e) and the global toast stays silent —
 * the user never sees the same failure twice, and never sees none.
 *
 * 401 on anything but the auth endpoints means the session expired: the user
 * is logged out and sent to /login?redirect=<where they were>.
 */
import axios from 'axios'
import { extractApiError } from './apiError'

export const DEFAULT_TIMEOUT_MS = 60000
/** For endpoints known to be slow (ordination, networks, exports, uploads). */
export const LONG_TIMEOUT_MS = 300000

const AUTH_PATHS = ['/api/auth/login', '/api/auth/register', '/api/auth/forgot-password', '/api/auth/reset-password']

export function isAuthRequest(config) {
  const url = config?.url || ''
  return AUTH_PATHS.some((p) => url.startsWith(p))
}

let _sessionExpiredAt = 0

export function setupHttp({ router, i18n, addToast, getAuthStore }) {
  axios.defaults.timeout = DEFAULT_TIMEOUT_MS

  const t = (key, fallback) => {
    try {
      return i18n.global.te(key) ? i18n.global.t(key) : fallback
    } catch {
      return fallback
    }
  }

  axios.interceptors.request.use((config) => {
    const loc = i18n?.global?.locale
    const code = typeof loc === 'string' ? loc : loc?.value
    if (code) config.headers['Accept-Language'] = code
    return config
  })

  axios.interceptors.response.use(
    (response) => response,
    (error) => {
      if (axios.isCancel(error)) {
        error._handled = true
        return Promise.reject(error)
      }
      const status = error.response?.status
      const config = error.config || {}

      if (status === 401 && !isAuthRequest(config)) {
        error._handled = true
        const auth = getAuthStore?.()
        const hadSession = !!(auth?.token || localStorage.getItem('token'))
        auth?.logout?.()
        const now = Date.now()
        if (hadSession && now - _sessionExpiredAt > 3000) {
          _sessionExpiredAt = now
          addToast(t('errors.sessionExpired', 'Your session has expired. Please sign in again.'), 'warning')
          const current = router?.currentRoute?.value
          if (current && current.name !== 'Login' && !current.meta?.public) {
            router.push({ name: 'Login', query: { redirect: current.fullPath } }).catch(() => {})
          }
        }
        return Promise.reject(error)
      }

      if (config.silentError) {
        error._handled = true
        return Promise.reject(error)
      }

      setTimeout(() => {
        if (error._handled) return
        error._handled = true
        const type = status === 429 || (status && status < 500) ? 'warning' : 'error'
        const msg = extractApiError(error)
        const context = config.errorContext
        addToast(context ? `${context}: ${msg}` : msg, type)
      }, 0)
      return Promise.reject(error)
    },
  )
}

/** Only allow in-app redirects (no protocol, no //host). */
export function safeRedirect(target, fallback = '/projects') {
  if (typeof target !== 'string' || !target.startsWith('/') || target.startsWith('//')) return fallback
  if (target.startsWith('/login')) return fallback
  return target
}
